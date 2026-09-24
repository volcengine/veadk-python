# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Decision-model judgement for how well a final answer is supported.

The deterministic verifier reads completion markers and asks whether any tool
receipt succeeded, which cannot tell "the deployment receipt proves this" from
"the answer says done and an unrelated tool succeeded". The ``decision``
strategy rates the answer against the receipts, and asks which repair the
answer needs, so a blocked answer comes with guidance instead of one fixed
sentence.

Judgements are optional: when no decision model is configured, the caller keeps
the builtin rules.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from veadk.extensions.decisions import (
    ChoiceAnswer,
    DecisionExtension,
    DecisionModelResponseError,
    ScoreAnswer,
    choice_question,
    get_default_decision_extension,
    score_question,
)
from veadk.extensions.harness.schemas import ToolReceipt
from veadk.extensions.harness.utils import summarize_text
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: 判定问题的 id。
SUPPORT_QUESTION_ID = "support"
REPAIR_QUESTION_ID = "repair"

#: 修复动作的名字，也是判定返回的选项。
RETRY_TOOL_CALL_ACTION = "retry_tool_call"
SOFTEN_CLAIM_ACTION = "soften_claim"
DROP_CLAIM_ACTION = "drop_claim"
ASK_USER_ACTION = "ask_user"

REPAIR_ACTIONS = (
    RETRY_TOOL_CALL_ACTION,
    SOFTEN_CLAIM_ACTION,
    DROP_CLAIM_ACTION,
    ASK_USER_ACTION,
)

#: 动作 -> 交给主模型的修复指引。
REPAIR_GUIDANCE = {
    RETRY_TOOL_CALL_ACTION: (
        "Rerun the tool step that would prove the claim, then answer again with "
        "that receipt."
    ),
    SOFTEN_CLAIM_ACTION: (
        "Restate the claim as what the receipts actually show, and drop "
        "completion wording they cannot back."
    ),
    DROP_CLAIM_ACTION: "Remove the unsupported claim and answer with what the receipts support.",
    ASK_USER_ACTION: (
        "Ask the user for the evidence the claim depends on instead of asserting it."
    ),
}

_DEFAULT_STATE_CHARS = 8000
_DEFAULT_ANSWER_CHARS = 3000
_DEFAULT_RECEIPT_CHARS = 400
_MIN_RECEIPT_CHARS = 120

_SUPPORT_LEVELS = (
    "unsupported: it claims results that no receipt backs",
    "weak: the main claim is plausible but no receipt covers it",
    "partial: the receipts cover the main steps, not every claim",
    "supported: every claim follows from the receipts",
)

_SUPPORT_INSTRUCTIONS = (
    "Rate how well the final answer is supported by the tool receipts of this run."
)

_REPAIR_INSTRUCTIONS = (
    "The answer is not supported well enough. Choose the repair that fits it."
)


@dataclass(frozen=True)
class SupportJudgement:
    """What a decision model judged about one final answer."""

    #: 支撑强度在 0..1 上的位置，越高表示证据越充分。
    support: float
    #: 修复动作，``None`` 表示判定没有给出可用动作。
    action: str | None = None
    #: 判定给所选动作的概率。
    confidence: float = 0.0

    @property
    def guidance(self) -> str:
        """Return the repair guidance of the judged action, if any."""
        return REPAIR_GUIDANCE.get(self.action or "", "")


class SupportJudge(Protocol):
    """Judge how well one final answer is supported by the run's receipts."""

    async def areview(
        self, *, answer: str, receipts: Sequence[ToolReceipt], goal: str = ""
    ) -> SupportJudgement:
        """Return the support judgement for one answer."""
        ...


class DecisionSupportJudge:
    """Ask a decision model how well an answer stands on its receipts.

    One request carries both questions, so reviewing an answer costs one
    decision-model call: the rating decides the verdict, and the chosen repair
    only shapes the guidance handed back to the caller.
    """

    def __init__(
        self,
        extension: DecisionExtension,
        *,
        max_state_chars: int = _DEFAULT_STATE_CHARS,
        max_answer_chars: int = _DEFAULT_ANSWER_CHARS,
    ) -> None:
        if max_state_chars < 1:
            raise ValueError("max_state_chars must be positive")
        if max_answer_chars < 1:
            raise ValueError("max_answer_chars must be positive")
        self.extension = extension
        self.max_state_chars = max_state_chars
        self.max_answer_chars = max_answer_chars

    async def areview(
        self, *, answer: str, receipts: Sequence[ToolReceipt], goal: str = ""
    ) -> SupportJudgement:
        """Return the support rating and the repair the answer needs.

        Raises:
            DecisionModelError: If the decision model cannot answer. Callers
                are expected to fall back to the builtin rules.
        """
        result = await self.extension.aevaluate(
            state=self._state(answer, receipts, goal),
            questions={
                SUPPORT_QUESTION_ID: build_support_question(),
                REPAIR_QUESTION_ID: build_repair_question(),
            },
        )
        answer_payload = result.answers.get(SUPPORT_QUESTION_ID)
        if not isinstance(answer_payload, ScoreAnswer):
            raise DecisionModelResponseError("support judge returned no usable rating")
        return SupportJudgement(
            support=answer_payload.score,
            action=_action(result.answers.get(REPAIR_QUESTION_ID)),
            confidence=answer_payload.confidence,
        )

    def _state(self, answer: str, receipts: Sequence[ToolReceipt], goal: str) -> str:
        """Render the state: the goal, the answer, and one line per receipt."""
        per_receipt = max(
            _MIN_RECEIPT_CHARS,
            min(
                _DEFAULT_RECEIPT_CHARS,
                self.max_state_chars // max(1, len(receipts)),
            ),
        )
        lines = [
            "[Answer Review]",
            f"goal: {summarize_text(goal, max_chars=_DEFAULT_RECEIPT_CHARS) or 'unspecified'}",
            f"answer: {summarize_text(answer, max_chars=self.max_answer_chars)}",
            "tool_receipts:",
        ]
        if not receipts:
            lines.append("- none: no tool ran in this run")
        for receipt in receipts:
            summary = summarize_text(receipt.summary, max_chars=per_receipt)
            lines.append(
                f"- {receipt.name} ({receipt.status}): {summary or 'no summary'}"
            )
        lines.append("[/Answer Review]")
        return "\n".join(lines)


def build_support_question() -> dict[str, Any]:
    """Build the support-rating question."""
    return score_question(_SUPPORT_INSTRUCTIONS, _SUPPORT_LEVELS)


def build_repair_question() -> dict[str, Any]:
    """Build the repair-action question."""
    return choice_question(
        _REPAIR_INSTRUCTIONS,
        {
            RETRY_TOOL_CALL_ACTION: (
                "run the tool step again that would prove the claim"
            ),
            SOFTEN_CLAIM_ACTION: (
                "keep the claim but describe only what the receipts show"
            ),
            DROP_CLAIM_ACTION: "remove the claim from the answer",
            ASK_USER_ACTION: ("ask the user for the evidence instead of asserting it"),
        },
    )


def build_support_judge(
    strategy: str,
    *,
    extension: DecisionExtension | None = None,
) -> DecisionSupportJudge | None:
    """Build the judge a strategy asks for.

    Args:
        strategy: ``decision`` builds a judge; anything else returns ``None``.
        extension: Decision model to use instead of the process-wide one.

    Returns:
        A judge, or ``None`` when the strategy is not ``decision`` or no
        decision model is configured. ``None`` keeps the builtin rules.
    """
    if (strategy or "").strip().lower() != "decision":
        return None
    extension = extension or get_default_decision_extension()
    if not extension.enabled:
        logger.warning(
            "verifier strategy is 'decision' but no decision model is "
            "configured; keeping the builtin verification rules"
        )
        return None
    return DecisionSupportJudge(extension)


def _action(answer: Any) -> str | None:
    """Return the judged repair action, ignoring an unusable one.

    The action only selects the guidance handed back, so an answer that names
    no known option keeps the rating instead of discarding the whole review.
    """
    if not isinstance(answer, ChoiceAnswer):
        return None
    if answer.choice not in REPAIR_ACTIONS:
        logger.warning("support judge returned unknown action %r", answer.choice)
        return None
    return answer.choice


__all__ = [
    "ASK_USER_ACTION",
    "DecisionSupportJudge",
    "DROP_CLAIM_ACTION",
    "REPAIR_ACTIONS",
    "REPAIR_GUIDANCE",
    "REPAIR_QUESTION_ID",
    "RETRY_TOOL_CALL_ACTION",
    "SOFTEN_CLAIM_ACTION",
    "SUPPORT_QUESTION_ID",
    "SupportJudge",
    "SupportJudgement",
    "build_repair_question",
    "build_support_judge",
    "build_support_question",
]
