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

"""Decision-model judgement for long-run convergence.

The long-run control plugin steers a run towards a final answer once it has
used many model calls. A call count cannot tell "still collecting the evidence
this task needs" from "already has everything and keeps going", so the
``decision`` strategy asks the configured decision model whether the
trajectory already holds what the final answer needs.

Judgements are optional: when no decision model is configured, callers keep
their own rules.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from veadk.extensions.decisions import (
    DecisionExtension,
    DecisionModelResponseError,
    NoulAnswer,
    get_default_decision_extension,
    noul_question,
)
from veadk.extensions.harness.schemas import ConversationMessage
from veadk.extensions.harness.utils import summarize_text
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: 判定问题的 id。
READY_QUESTION_ID = "ready"

_DEFAULT_STATE_CHARS = 12000
_DEFAULT_TRAJECTORY_MESSAGES = 20
_MIN_MESSAGE_CHARS = 120

_READY_INSTRUCTIONS = (
    "The agent has spent many model calls on this run. Decide whether the "
    "trajectory already contains the evidence and results the final answer "
    "needs, so that no further tool call is required."
)


class ConvergenceJudge(Protocol):
    """Judge whether a run already has what a final answer needs."""

    async def aready_probability(self, *, goal: str, trajectory: str) -> float:
        """Return the probability that the run can answer now."""
        ...


class DecisionConvergenceJudge:
    """Ask a decision model whether the run has converged."""

    def __init__(
        self,
        extension: DecisionExtension,
        *,
        max_state_chars: int = _DEFAULT_STATE_CHARS,
    ) -> None:
        if max_state_chars < 1:
            raise ValueError("max_state_chars must be positive")
        self.extension = extension
        self.max_state_chars = max_state_chars

    async def aready_probability(self, *, goal: str, trajectory: str) -> float:
        """Return the probability that the run already holds its answer.

        Raises:
            DecisionModelError: If the decision model cannot answer. Callers
                are expected to fall back to their own rules.
        """
        result = await self.extension.aevaluate(
            state=self._state(goal, trajectory),
            questions={READY_QUESTION_ID: build_ready_question()},
        )
        answer = result.answers.get(READY_QUESTION_ID)
        if not isinstance(answer, NoulAnswer):
            raise DecisionModelResponseError("long-run judge returned no usable answer")
        return answer.noul

    def _state(self, goal: str, trajectory: str) -> str:
        """Render the judgement state within the configured budget."""
        goal_text = summarize_text(goal, max_chars=_MIN_MESSAGE_CHARS)
        return "\n".join(
            [
                "[Long Run Check]",
                f"goal: {goal_text or 'unspecified'}",
                "trajectory:",
                summarize_text(
                    trajectory,
                    max_chars=max(
                        _MIN_MESSAGE_CHARS, self.max_state_chars - len(goal_text)
                    ),
                ),
                "[/Long Run Check]",
            ]
        )


def build_ready_question() -> dict[str, Any]:
    """Build the convergence question."""
    return noul_question(
        _READY_INSTRUCTIONS,
        yes="the final answer can be written now from what was collected",
        no="at least one more tool call or step is needed first",
    )


def trajectory_text(
    messages: Sequence[ConversationMessage],
    *,
    max_chars: int = _DEFAULT_STATE_CHARS,
    max_messages: int = _DEFAULT_TRAJECTORY_MESSAGES,
) -> str:
    """Render the most recent messages as a bounded trajectory.

    The tail of a run carries the current state, so earlier messages are
    dropped before any message is truncated.
    """
    recent = list(messages)[-max_messages:]
    per_message = max(_MIN_MESSAGE_CHARS, max_chars // max(1, len(recent)))
    return "\n".join(
        f"{message.role}: {summarize_text(message.content, max_chars=per_message)}"
        for message in recent
    )


def build_convergence_judge(
    strategy: str,
    *,
    extension: DecisionExtension | None = None,
) -> DecisionConvergenceJudge | None:
    """Build the judge a strategy asks for.

    Args:
        strategy: ``decision`` builds a judge; anything else returns ``None``.
        extension: Decision model to use instead of the process-wide one.

    Returns:
        A judge, or ``None`` when the strategy is not ``decision`` or no
        decision model is configured. ``None`` keeps the caller's own rules.
    """
    if strategy != "decision":
        return None
    extension = extension or get_default_decision_extension()
    if not extension.enabled:
        logger.warning(
            "long-run strategy is 'decision' but no decision model is "
            "configured; keeping the call-count rule"
        )
        return None
    return DecisionConvergenceJudge(extension)


__all__ = [
    "ConvergenceJudge",
    "DecisionConvergenceJudge",
    "build_convergence_judge",
    "build_ready_question",
    "trajectory_text",
]
