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

"""Decision-model judgement for writing a session to long-term memory.

The session callback throttles writes with a message count and a time window.
Those thresholds cannot tell a turn that stated a durable preference from one
that only exchanged greetings, so the ``decision`` strategy asks the configured
decision model whether the new events are worth remembering.

Judgements are optional: when no decision model is configured, the caller keeps
its thresholds.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from google.adk.events import Event

from veadk.extensions.decisions import (
    DecisionExtension,
    DecisionModelResponseError,
    NoulAnswer,
    get_default_decision_extension,
    noul_question,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: 判定问题的 id。
WORTH_QUESTION_ID = "worth"

MAX_EVENTS = 40
MAX_EVENTS_CHARS = 4000
_MIN_EVENT_CHARS = 80

_WORTH_INSTRUCTIONS = (
    "The agent has just finished a turn. Decide whether the new events contain "
    "something durable that belongs in the user's long-term memory: a stated "
    "preference, a personal or project fact, a decision, a constraint, or a "
    "correction the agent has to respect later."
)


class MemorySaveJudge(Protocol):
    """Judge whether new session events are worth remembering."""

    async def aworth_saving(self, *, events_text: str) -> float:
        """Return the probability that the events belong in long-term memory."""
        ...


class DecisionMemorySaveJudge:
    """Ask a decision model whether a turn is worth remembering."""

    def __init__(self, extension: DecisionExtension) -> None:
        self.extension = extension

    async def aworth_saving(self, *, events_text: str) -> float:
        """Return the probability that the events belong in memory.

        Raises:
            DecisionModelError: If the decision model cannot answer. Callers
                are expected to fall back to their thresholds.
        """
        result = await self.extension.aevaluate(
            state=f"[Memory Triage]\nnew_events: {events_text}\n[/Memory Triage]",
            questions={WORTH_QUESTION_ID: build_worth_question()},
        )
        answer = result.answers.get(WORTH_QUESTION_ID)
        if not isinstance(answer, NoulAnswer):
            raise DecisionModelResponseError(
                "memory save judge returned no usable answer"
            )
        return answer.noul


def build_worth_question() -> dict[str, Any]:
    """Build the "is this worth remembering" question."""
    return noul_question(
        _WORTH_INSTRUCTIONS,
        yes="the events carry a durable fact the agent should recall later",
        no="the events are only transient dialogue or progress chatter",
    )


def events_text(
    events: Iterable[Event],
    *,
    max_events: int = MAX_EVENTS,
    max_chars: int = MAX_EVENTS_CHARS,
) -> str:
    """Render the newest events as text for a judgement.

    Only the tail of a session is rendered: earlier events were already
    offered to previous judgements. The budget is split evenly between the
    rendered events, so a long message cannot hide the ones after it.
    """
    rendered = [
        (str(getattr(event, "author", "") or "unknown"), _event_text(event))
        for event in list(events)[-max_events:]
    ]
    rendered = [item for item in rendered if item[1]]
    if not rendered:
        return ""
    per_event = max(_MIN_EVENT_CHARS, max_chars // len(rendered))
    return "\n".join(
        f"{author}: {_truncate(text, per_event)}" for author, text in rendered
    )


def build_memory_save_judge(
    strategy: str,
    *,
    extension: DecisionExtension | None = None,
) -> DecisionMemorySaveJudge | None:
    """Build the judge a strategy asks for.

    Args:
        strategy: ``decision`` builds a judge; anything else returns ``None``.
        extension: Decision model to use instead of the process-wide one.

    Returns:
        A judge, or ``None`` when the strategy is not ``decision`` or no
        decision model is configured. ``None`` keeps the caller's thresholds.
    """
    if strategy.strip().lower() != "decision":
        return None
    extension = extension or get_default_decision_extension()
    if not extension.enabled:
        logger.warning(
            "memory save strategy is 'decision' but no decision model is "
            "configured; keeping the save thresholds"
        )
        return None
    return DecisionMemorySaveJudge(extension)


def _event_text(event: Event) -> str:
    """Return the readable text of one event, naming the tools it called."""
    content = getattr(event, "content", None)
    values: list[str] = []
    for part in getattr(content, "parts", None) or []:
        if getattr(part, "text", None):
            values.append(str(part.text))
        function_call = getattr(part, "function_call", None)
        if function_call is not None:
            values.append(f"[tool_call {getattr(function_call, 'name', '')}]")
    return " ".join(values).strip()


def _truncate(text: str, max_chars: int) -> str:
    """Keep a judgement state within budget."""
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    omitted = len(normalized) - max_chars
    return f"{normalized[:max_chars]} ... [truncated {omitted} chars]"


__all__ = [
    "DecisionMemorySaveJudge",
    "MemorySaveJudge",
    "build_memory_save_judge",
    "build_worth_question",
    "events_text",
]
