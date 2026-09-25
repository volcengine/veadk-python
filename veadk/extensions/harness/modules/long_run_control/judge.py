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

"""Decision-model judgement for long-run convergence and steering.

The long-run control plugin steers a run towards a final answer once it has
used many model calls. A call count cannot tell "still collecting the evidence
this task needs" from "already has everything and keeps going", so the
``decision`` strategy asks the configured decision model whether the
trajectory already holds what the final answer needs.

A second question picks the steering action: how hard to push the run towards
its answer is a choice among a few kinds of guidance, not a yes/no, so the
judgement returns one option and the plugin injects the matching text.

Judgements are optional: when no decision model is configured, callers keep
their own rules.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from veadk.extensions.decisions import (
    ChoiceAnswer,
    DecisionExtension,
    DecisionModelResponseError,
    NoulAnswer,
    UNTRUSTED_NOTICE,
    choice_question,
    get_default_decision_extension,
    noul_question,
    untrusted,
)
from veadk.extensions.harness.schemas import ConversationMessage
from veadk.extensions.harness.utils import summarize_text
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: 判定问题的 id。
READY_QUESTION_ID = "ready"
ACTION_QUESTION_ID = "action"

#: 引导动作的名字，也是判定返回的选项。
NARROW_SCOPE_ACTION = "narrow_scope"
NUDGE_TO_FINISH_ACTION = "nudge_to_finish"
FORCE_FINISH_ACTION = "force_finish"

STEERING_ACTIONS = (
    NARROW_SCOPE_ACTION,
    NUDGE_TO_FINISH_ACTION,
    FORCE_FINISH_ACTION,
)

_DEFAULT_STATE_CHARS = 12000
_DEFAULT_TRAJECTORY_MESSAGES = 20
_MIN_MESSAGE_CHARS = 120

_READY_INSTRUCTIONS = (
    "The agent has spent many model calls on this run. Decide whether the "
    "trajectory already contains the evidence and results the final answer "
    "needs, so that no further tool call is required."
)

_ACTION_INSTRUCTIONS = (
    "The agent has spent many model calls on this run. Choose how it should be "
    "steered through the remaining budget: pick the mildest steering that "
    "still fits the trajectory."
)


@dataclass(frozen=True)
class LongRunJudgement:
    """What a decision model judged about one long run."""

    #: Probability that the run already holds what the final answer needs.
    ready: float
    #: Steering action, or ``None`` when the judgement named no usable one.
    action: str | None = None
    #: Probability the decision model assigned to the chosen action.
    confidence: float = 0.0


class ConvergenceJudge(Protocol):
    """Judge whether a run already has what a final answer needs, and how to steer it."""

    async def ajudge(self, *, goal: str, trajectory: str) -> LongRunJudgement:
        """Return the convergence judgement for one run."""
        ...


class DecisionConvergenceJudge:
    """Ask a decision model whether the run has converged."""

    def __init__(
        self,
        extension: DecisionExtension,
        *,
        max_state_chars: int = _DEFAULT_STATE_CHARS,
        min_confidence: float = 0.0,
    ) -> None:
        if max_state_chars < 1:
            raise ValueError("max_state_chars must be positive")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be within [0, 1]")
        self.extension = extension
        self.max_state_chars = max_state_chars
        self.min_confidence = min_confidence

    async def ajudge(self, *, goal: str, trajectory: str) -> LongRunJudgement:
        """Return the convergence probability and the steering action.

        Raises:
            DecisionModelError: If the decision model cannot answer. Callers
                are expected to fall back to their own rules.
        """
        result = await self.extension.aevaluate(
            state=self._state(goal, trajectory),
            questions={
                READY_QUESTION_ID: build_ready_question(),
                ACTION_QUESTION_ID: build_action_question(),
            },
        )
        answer = result.answers.get(READY_QUESTION_ID)
        if not isinstance(answer, NoulAnswer):
            raise DecisionModelResponseError("long-run judge returned no usable answer")
        action_answer = result.answers.get(ACTION_QUESTION_ID)
        return LongRunJudgement(
            ready=answer.noul,
            action=_confident_action(action_answer, self.min_confidence),
            confidence=_choice_confidence(action_answer),
        )

    def _state(self, goal: str, trajectory: str) -> str:
        """Render the judgement state within the configured budget."""
        goal_text = summarize_text(goal, max_chars=_MIN_MESSAGE_CHARS)
        return "\n".join(
            [
                "[Long Run Check]",
                UNTRUSTED_NOTICE,
                "goal: " + untrusted("user_request", goal_text or "unspecified"),
                "trajectory: "
                + untrusted(
                    "run_trajectory",
                    summarize_text(
                        trajectory,
                        max_chars=max(
                            _MIN_MESSAGE_CHARS, self.max_state_chars - len(goal_text)
                        ),
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


def build_action_question() -> dict[str, Any]:
    """Build the steering-action question."""
    return choice_question(
        _ACTION_INSTRUCTIONS,
        {
            NARROW_SCOPE_ACTION: (
                "keep working, but drop optional or exploratory sub-goals and "
                "finish the core question"
            ),
            NUDGE_TO_FINISH_ACTION: (
                "keep working while converging: answer as soon as the evidence "
                "is enough"
            ),
            FORCE_FINISH_ACTION: (
                "answer now from the evidence already collected, naming "
                "anything that could not be verified"
            ),
        },
    )


def _action(answer: Any) -> str | None:
    """Return the judged steering action, ignoring an unusable one.

    The action only selects the wording of the guidance, so an answer that
    names no known option falls back to the default wording instead of
    discarding the convergence probability that came with it.
    """
    if not isinstance(answer, ChoiceAnswer):
        return None
    if answer.choice not in STEERING_ACTIONS:
        logger.warning("long-run judge returned unknown action %r", answer.choice)
        return None
    return answer.choice


def _choice_confidence(answer: Any) -> float:
    """Return the probability the judge gave to the option it named."""
    return answer.confidence if isinstance(answer, ChoiceAnswer) else 0.0


def _confident_action(answer: Any, min_confidence: float) -> str | None:
    """Return the judged action, or ``None`` when the judge is unsure of it.

    Steering a run towards its answer is the judgement that changes behaviour,
    so an action the judge is not sure about keeps the default wording: the
    convergence probability that came with it still counts.
    """
    action = _action(answer)
    if action is None or min_confidence <= 0.0:
        return action
    confidence = _choice_confidence(answer)
    if confidence < min_confidence:
        logger.info(
            "long-run judge is not confident about %r (%s < %s); "
            "keeping the default steering wording",
            action,
            confidence,
            min_confidence,
        )
        return None
    return action


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
    min_confidence: float = 0.0,
) -> DecisionConvergenceJudge | None:
    """Build the judge a strategy asks for.

    Args:
        strategy: ``decision`` builds a judge; anything else returns ``None``.
        extension: Decision model to use instead of the process-wide one.
        min_confidence: Smallest confidence a steering action needs to be used.

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
    return DecisionConvergenceJudge(extension, min_confidence=min_confidence)


__all__ = [
    "ConvergenceJudge",
    "DecisionConvergenceJudge",
    "FORCE_FINISH_ACTION",
    "LongRunJudgement",
    "NARROW_SCOPE_ACTION",
    "NUDGE_TO_FINISH_ACTION",
    "build_convergence_judge",
    "build_action_question",
    "build_ready_question",
    "trajectory_text",
]
