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

"""Decision-model judgement for which sub-agent a request belongs to.

Routing is a choice among the agents a run may transfer to, so the ``decision``
strategy asks one ``choice`` question whose options are the agents and whose
option descriptions are the agent descriptions the caller advertises. The
judgement replaces the model's choice only when it clears the confidence
threshold; anything less certain is left to the model, which still sees the full
transfer instructions.

Judgements are optional: when no decision model is configured, callers keep
leaving the choice to the model.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from veadk.extensions.decisions import (
    ChoiceAnswer,
    DecisionExtension,
    DecisionModelResponseError,
    choice_question,
    get_default_decision_extension,
)
from veadk.extensions.harness.utils import summarize_text
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: 判定问题的 id。
ROUTE_QUESTION_ID = "target"

_DEFAULT_STATE_CHARS = 4000
_NO_DESCRIPTION = "this agent has no description"

_INSTRUCTIONS = (
    "Which agent should handle the user's request? Pick the agent whose "
    "description fits the request best."
)


class AgentRouter(Protocol):
    """Judge which transfer target one request belongs to."""

    async def aroute(self, *, user_input: str, agents: Mapping[str, str]) -> str | None:
        """Return the agent to transfer to, or ``None`` when it is not clear."""
        ...


class DecisionAgentRouter:
    """Ask a decision model which agent a request belongs to."""

    def __init__(
        self,
        extension: DecisionExtension,
        *,
        confidence_threshold: float = 0.5,
        max_state_chars: int = _DEFAULT_STATE_CHARS,
    ) -> None:
        if max_state_chars < 1:
            raise ValueError("max_state_chars must be positive")
        self.extension = extension
        self.confidence_threshold = confidence_threshold
        self.max_state_chars = max_state_chars

    async def aroute(self, *, user_input: str, agents: Mapping[str, str]) -> str | None:
        """Return the judged transfer target, or ``None`` when none is clear.

        Raises:
            DecisionModelError: If the decision model cannot answer. Callers
                are expected to leave the choice to the model.
        """
        if not agents:
            return None
        result = await self.extension.aevaluate(
            state=self._state(user_input),
            questions={ROUTE_QUESTION_ID: build_route_question(agents)},
        )
        answer = result.answers.get(ROUTE_QUESTION_ID)
        if not isinstance(answer, ChoiceAnswer):
            raise DecisionModelResponseError("agent router returned no usable answer")
        if answer.choice not in agents:
            logger.warning("agent router named unknown target %r", answer.choice)
            return None
        probability = answer.probabilities.get(answer.choice, answer.confidence)
        if probability < self.confidence_threshold:
            logger.info(
                "agent router is not confident about %r (%s < %s); "
                "letting the model route",
                answer.choice,
                probability,
                self.confidence_threshold,
            )
            return None
        return answer.choice

    def _state(self, user_input: str) -> str:
        """Render the judgement state: only the request being routed."""
        request = summarize_text(user_input, max_chars=self.max_state_chars)
        return "\n".join(
            [
                "[Agent Routing]",
                f"user_request: {request or 'unspecified'}",
                "[/Agent Routing]",
            ]
        )


def build_route_question(agents: Mapping[str, str]) -> dict[str, Any]:
    """Build the routing question for one set of transfer targets."""
    return choice_question(
        _INSTRUCTIONS,
        {name: description or _NO_DESCRIPTION for name, description in agents.items()},
    )


def build_agent_router(
    strategy: str,
    *,
    extension: DecisionExtension | None = None,
    confidence_threshold: float = 0.5,
) -> DecisionAgentRouter | None:
    """Build the router a strategy asks for.

    Args:
        strategy: ``decision`` builds a router; anything else returns ``None``.
        extension: Decision model to use instead of the process-wide one.
        confidence_threshold: Probability below which the model keeps routing.

    Returns:
        A router, or ``None`` when the strategy is not ``decision`` or no
        decision model is configured. ``None`` leaves the choice with the
        model, which is the documented degradation path.
    """
    if strategy != "decision":
        return None
    extension = extension or get_default_decision_extension()
    if not extension.enabled:
        logger.warning(
            "routing strategy is 'decision' but no decision model is "
            "configured; letting the model route"
        )
        return None
    return DecisionAgentRouter(
        extension,
        confidence_threshold=confidence_threshold,
    )


__all__ = [
    "AgentRouter",
    "DecisionAgentRouter",
    "ROUTE_QUESTION_ID",
    "build_agent_router",
    "build_route_question",
]
