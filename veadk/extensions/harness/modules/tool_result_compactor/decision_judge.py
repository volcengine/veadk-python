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

"""Decision-model judgement for compaction candidates.

The compacting policy decides which historical messages may be summarized.
Its builtin rules can only read message roles and sizes, which is not enough
to tell "a stale 20k log dump" from "the exact error text the agent is still
iterating on". The ``decision`` strategy asks the configured decision model
that content question per candidate, so the policy keeps the evidence a run
still needs and summarizes the rest.

Every judge is optional: when no decision model is configured, the policy
keeps the builtin rules.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

from veadk.extensions.decisions import (
    DecisionAnswer,
    DecisionExtension,
    DecisionModelResponseError,
    NoulAnswer,
    UNTRUSTED_NOTICE,
    get_default_decision_extension,
    noul_question,
    untrusted,
)
from veadk.extensions.harness.utils import summarize_text
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from veadk.extensions.harness.modules.tool_result_compactor.compactor import (
        ToolResultCompactorConfig,
    )

logger = get_logger(__name__)

#: 每个候选证据对应的问题 id，形如 ``item_3``。
QUESTION_ID_PREFIX = "item"

_DEFAULT_STATE_CHARS = 12000
_DEFAULT_EVIDENCE_CHARS = 600
_MIN_EVIDENCE_CHARS = 120


class CompactionJudge(Protocol):
    """Judge which historical evidence must survive compaction verbatim."""

    async def aprotect(
        self, *, goal: str, evidence: Mapping[int, str]
    ) -> Mapping[int, float]:
        """Return ``{message_index: probability that it must stay verbatim}``."""
        ...


class DecisionCompactionJudge:
    """Ask a decision model whether each candidate may be summarized.

    One request carries every candidate, so a plan costs one decision-model
    call no matter how many messages it covers.
    """

    def __init__(
        self,
        extension: DecisionExtension,
        *,
        max_state_chars: int = _DEFAULT_STATE_CHARS,
        max_evidence_chars: int = _DEFAULT_EVIDENCE_CHARS,
    ) -> None:
        if max_state_chars < 1:
            raise ValueError("max_state_chars must be positive")
        if max_evidence_chars < 1:
            raise ValueError("max_evidence_chars must be positive")
        self.extension = extension
        self.max_state_chars = max_state_chars
        self.max_evidence_chars = max_evidence_chars

    async def aprotect(
        self, *, goal: str, evidence: Mapping[int, str]
    ) -> Mapping[int, float]:
        """Return the keep probability of every indexed piece of evidence.

        Raises:
            DecisionModelError: If the decision model cannot answer. Callers
                are expected to fall back to their own rules.
        """
        if not evidence:
            return {}
        questions = {
            f"{QUESTION_ID_PREFIX}_{index}": _keep_question(index) for index in evidence
        }
        result = await self.extension.aevaluate(
            state=self._state(goal, evidence),
            questions=questions,
        )
        return _keep_probabilities(result.answers, evidence)

    def _state(self, goal: str, evidence: Mapping[int, str]) -> str:
        """Render the shared state: the goal plus a numbered evidence list.

        The per-item budget is derived from the candidate count, so every item
        a question refers to stays present even when the list is long.
        """
        per_item = max(
            _MIN_EVIDENCE_CHARS,
            min(self.max_evidence_chars, self.max_state_chars // len(evidence)),
        )
        lines = [
            "[Compaction Triage]",
            UNTRUSTED_NOTICE,
            "goal: "
            + untrusted(
                "user_request",
                summarize_text(goal, max_chars=per_item) or "unspecified",
            ),
            "tool_outputs:",
        ]
        for index, content in evidence.items():
            lines.append(
                f"- item {index} ({len(content)} chars): "
                + untrusted(
                    "tool_output",
                    summarize_text(content, max_chars=per_item),
                )
            )
        lines.append("[/Compaction Triage]")
        return "\n".join(lines)


def build_compaction_judge(
    config: ToolResultCompactorConfig,
    *,
    extension: DecisionExtension | None = None,
) -> DecisionCompactionJudge | None:
    """Build the judge a configuration asks for.

    Args:
        config: Compactor settings; only the ``decision`` strategy builds one.
        extension: Decision model to use instead of the process-wide one.

    Returns:
        A judge for the ``decision`` strategy, or ``None`` for the ``builtin``
        strategy or an unconfigured decision model. ``None`` keeps the builtin
        rules, which is the documented degradation path.
    """
    if config.strategy != "decision":
        return None
    extension = extension or get_default_decision_extension()
    if not extension.enabled:
        logger.warning(
            "compaction strategy is 'decision' but no decision model is "
            "configured; keeping the builtin rules"
        )
        return None
    return DecisionCompactionJudge(
        extension,
        max_evidence_chars=config.decision_evidence_chars,
    )


def _keep_question(index: int) -> dict[str, Any]:
    """Build the "must this stay verbatim" question for one candidate."""
    return noul_question(
        f"Does tool output item_{index} still need to stay verbatim in the "
        "conversation?",
        yes="the agent still needs its exact wording to answer or to verify",
        no="a summary keeps every fact the agent still needs",
    )


def _keep_probabilities(
    answers: Mapping[str, DecisionAnswer], evidence: Mapping[int, str]
) -> dict[int, float]:
    """Map answer ids back to message indexes.

    Raises:
        DecisionModelResponseError: If one candidate has no usable answer.
            Callers then keep their own rules instead of acting on a partial
            judgement.
    """
    probabilities: dict[int, float] = {}
    for index in evidence:
        answer = answers.get(f"{QUESTION_ID_PREFIX}_{index}")
        if not isinstance(answer, NoulAnswer):
            raise DecisionModelResponseError(
                f"compaction judge returned no usable answer for index {index}"
            )
        probabilities[index] = answer.noul
    return probabilities


__all__ = [
    "CompactionJudge",
    "DecisionCompactionJudge",
    "build_compaction_judge",
]
