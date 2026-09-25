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
strategy reads the answer together with the receipts and answers four questions
in one request:

* ``verdict``: one mutually exclusive outcome — supported, partial, or
  unsupported. Mutually exclusive outcomes belong in one choice, and the
  probability of ``supported`` is the rating the caller compares against its
  threshold.
* ``coverage`` and ``overclaim``: the two checks that read the same answer from
  different angles. Splitting a fuzzy rating into orthogonal checks is what
  makes the judgement catch an answer the builtin rules cannot see through, so
  a judged overclaim overrides a ``supported`` verdict.
* ``repair``: which repair the answer needs, which only shapes the guidance
  handed back to the caller.

A judgement that names an outcome with too little confidence is not evidence
about the answer, so the judge refuses to give one and the caller keeps the
builtin rules; see ``min_confidence``.

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
    DecisionModelLowConfidenceError,
    DecisionModelResponseError,
    NoulAnswer,
    UNTRUSTED_NOTICE,
    choice_question,
    get_default_decision_extension,
    noul_question,
    untrusted,
)
from veadk.extensions.harness.schemas import ToolReceipt
from veadk.extensions.harness.utils import summarize_text
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: 判定问题的 id。
VERDICT_QUESTION_ID = "verdict"
COVERAGE_QUESTION_ID = "coverage"
OVERCLAIM_QUESTION_ID = "overclaim"
REPAIR_QUESTION_ID = "repair"

#: 三选一的判定结果，互斥。
SUPPORTED_VERDICT = "supported"
PARTIAL_VERDICT = "partial"
UNSUPPORTED_VERDICT = "unsupported"

SUPPORT_VERDICTS = (SUPPORTED_VERDICT, PARTIAL_VERDICT, UNSUPPORTED_VERDICT)

#: 判定没有给出概率分布时，三选一结果对应的支撑度。
_VERDICT_SUPPORT = {
    SUPPORTED_VERDICT: 1.0,
    PARTIAL_VERDICT: 0.5,
    UNSUPPORTED_VERDICT: 0.0,
}

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

_VERDICT_INSTRUCTIONS = (
    "The agent has just written its final answer for this run. Decide how well "
    "the tool receipts support it: pick the outcome that fits the whole answer."
)

_VERDICT_OPTIONS = {
    SUPPORTED_VERDICT: "every claim in the answer follows from the receipts",
    PARTIAL_VERDICT: (
        "the receipts cover the main steps, but not every claim in the answer"
    ),
    UNSUPPORTED_VERDICT: "the answer claims results that no receipt backs",
}

_COVERAGE_INSTRUCTIONS = (
    "Do the tool receipts show the result the main claim of the answer describes?"
)

_OVERCLAIM_INSTRUCTIONS = (
    "Does the answer claim more than the receipts show, such as completed "
    "steps, results, or values that no receipt contains?"
)

_REPAIR_INSTRUCTIONS = (
    "The answer is not supported well enough. Choose the repair that fits it."
)


@dataclass(frozen=True)
class SupportJudgement:
    """What a decision model judged about one final answer."""

    #: 支撑度：判定给出概率分布时是 covered 的概率，否则是三选一结果对应的档位。
    support: float
    #: 三选一结果：``supported`` / ``partial`` / ``unsupported``。
    verdict: str | None = None
    #: 回执覆盖主要结论的概率。
    coverage: float = 0.0
    #: 回答超出回执范围的概率，用作否决位。
    overclaim: float = 0.0
    #: 修复动作，``None`` 表示判定没有给出可用动作。
    action: str | None = None
    #: 判定给所选结果的概率，供调用方做置信级联。
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

    One request carries all four questions, so reviewing an answer costs one
    decision-model call: the verdict decides the outcome, the two checks guard
    it, and the chosen repair only shapes the guidance handed back.
    """

    def __init__(
        self,
        extension: DecisionExtension,
        *,
        max_state_chars: int = _DEFAULT_STATE_CHARS,
        max_answer_chars: int = _DEFAULT_ANSWER_CHARS,
        min_confidence: float = 0.0,
    ) -> None:
        if max_state_chars < 1:
            raise ValueError("max_state_chars must be positive")
        if max_answer_chars < 1:
            raise ValueError("max_answer_chars must be positive")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be within [0, 1]")
        self.extension = extension
        self.max_state_chars = max_state_chars
        self.max_answer_chars = max_answer_chars
        self.min_confidence = min_confidence

    async def areview(
        self, *, answer: str, receipts: Sequence[ToolReceipt], goal: str = ""
    ) -> SupportJudgement:
        """Return the judged verdict, its checks, and the repair the answer needs.

        Raises:
            DecisionModelLowConfidenceError: If the verdict is less confident
                than ``min_confidence``. Callers keep the builtin rules.
            DecisionModelError: If the decision model cannot answer. Callers
                are expected to fall back to the builtin rules.
        """
        result = await self.extension.aevaluate(
            state=self._state(answer, receipts, goal),
            questions={
                VERDICT_QUESTION_ID: build_verdict_question(),
                COVERAGE_QUESTION_ID: build_coverage_question(),
                OVERCLAIM_QUESTION_ID: build_overclaim_question(),
                REPAIR_QUESTION_ID: build_repair_question(),
            },
        )
        verdict = result.answers.get(VERDICT_QUESTION_ID)
        if (
            not isinstance(verdict, ChoiceAnswer)
            or verdict.choice not in SUPPORT_VERDICTS
        ):
            raise DecisionModelResponseError("support judge returned no usable verdict")
        if self.min_confidence > 0.0 and verdict.confidence < self.min_confidence:
            raise DecisionModelLowConfidenceError(
                f"support judge is not confident about {verdict.choice!r} "
                f"(confidence={verdict.confidence:.2f} < {self.min_confidence}); "
                "keeping the builtin verification rules"
            )
        return SupportJudgement(
            support=_support_probability(verdict),
            verdict=verdict.choice,
            coverage=_probability(result.answers.get(COVERAGE_QUESTION_ID)),
            overclaim=_probability(result.answers.get(OVERCLAIM_QUESTION_ID)),
            action=_action(result.answers.get(REPAIR_QUESTION_ID)),
            confidence=verdict.confidence,
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
            UNTRUSTED_NOTICE,
            "goal: "
            + untrusted(
                "user_request",
                summarize_text(goal, max_chars=_DEFAULT_RECEIPT_CHARS) or "unspecified",
            ),
            "answer: "
            + untrusted(
                "agent_answer",
                summarize_text(answer, max_chars=self.max_answer_chars),
            ),
            "tool_receipts:",
        ]
        if not receipts:
            lines.append("- none: no tool ran in this run")
        for receipt in receipts:
            summary = summarize_text(receipt.summary, max_chars=per_receipt)
            lines.append(
                f"- {receipt.name} ({receipt.status}): "
                + untrusted(
                    "tool_receipt",
                    summary or "no summary",
                    name=receipt.name,
                )
            )
        lines.append("[/Answer Review]")
        return "\n".join(lines)


def build_verdict_question() -> dict[str, Any]:
    """Build the mutually exclusive outcome question."""
    return choice_question(_VERDICT_INSTRUCTIONS, _VERDICT_OPTIONS)


def build_coverage_question() -> dict[str, Any]:
    """Build the check that the receipts cover the main claim."""
    return noul_question(
        _COVERAGE_INSTRUCTIONS,
        yes="a receipt shows that result",
        no="no receipt shows it",
    )


def build_overclaim_question() -> dict[str, Any]:
    """Build the check that the answer stays inside what the receipts show."""
    return noul_question(
        _OVERCLAIM_INSTRUCTIONS,
        yes="the answer goes beyond the receipts",
        no="the answer stays inside them",
    )


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
    min_confidence: float = 0.0,
) -> DecisionSupportJudge | None:
    """Build the judge a strategy asks for.

    Args:
        strategy: ``decision`` builds a judge; anything else returns ``None``.
        extension: Decision model to use instead of the process-wide one.
        min_confidence: Smallest confidence a verdict needs to be acted on.

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
    return DecisionSupportJudge(extension, min_confidence=min_confidence)


def _support_probability(verdict: ChoiceAnswer) -> float:
    """Return the probability that the answer is supported.

    A gateway that reports the whole option distribution keeps the graded
    probability; one that reports only the chosen option falls back to the level
    the verdict names.
    """
    reported = verdict.probabilities.get(SUPPORTED_VERDICT)
    if reported is not None:
        return float(reported)
    return _VERDICT_SUPPORT[verdict.choice]


def _probability(answer: Any) -> float:
    """Return the ``yes`` probability of one check, ``0.0`` when unusable.

    An unanswered check adds no signal: the check that starts from "no" keeps
    the answer inside the receipts, the one that starts from "yes" finds no
    overlap. Both leave the verdict alone rather than inventing evidence.
    """
    if not isinstance(answer, NoulAnswer):
        logger.warning("support judge returned no usable answer for a check")
        return 0.0
    return answer.noul


def _action(answer: Any) -> str | None:
    """Return the judged repair action, ignoring an unusable one.

    The action only selects the guidance handed back, so an answer that names
    no known option keeps the verdict instead of discarding the whole review.
    """
    if not isinstance(answer, ChoiceAnswer):
        return None
    if answer.choice not in REPAIR_ACTIONS:
        logger.warning("support judge returned unknown action %r", answer.choice)
        return None
    return answer.choice


__all__ = [
    "ASK_USER_ACTION",
    "COVERAGE_QUESTION_ID",
    "DecisionSupportJudge",
    "DROP_CLAIM_ACTION",
    "OVERCLAIM_QUESTION_ID",
    "PARTIAL_VERDICT",
    "REPAIR_ACTIONS",
    "REPAIR_GUIDANCE",
    "REPAIR_QUESTION_ID",
    "RETRY_TOOL_CALL_ACTION",
    "SOFTEN_CLAIM_ACTION",
    "SUPPORTED_VERDICT",
    "SUPPORT_VERDICTS",
    "SupportJudge",
    "SupportJudgement",
    "UNSUPPORTED_VERDICT",
    "VERDICT_QUESTION_ID",
    "build_coverage_question",
    "build_overclaim_question",
    "build_repair_question",
    "build_support_judge",
    "build_verdict_question",
]
