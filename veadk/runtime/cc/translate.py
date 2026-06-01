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

"""Translation between ADK and the Claude Code SDK.

Two directions:

- :func:`build_prompt` flattens an ADK session (history + current message) into a
  single prompt string for the SDK. ADK remains the single source of truth for
  conversation state (stateless replay), which keeps multi-tenancy clean.
- :func:`sdk_message_to_events` maps SDK stream messages back into ADK
  :class:`~google.adk.events.event.Event` objects so the surrounding ``Runner``
  can persist them unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from claude_agent_sdk import (
    AssistantMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from google.adk.events.event import Event
from google.genai import types

if TYPE_CHECKING:
    from claude_agent_sdk import Message
    from google.adk.agents.invocation_context import InvocationContext

_USER_PREFIX = "User"
_ASSISTANT_PREFIX = "Assistant"


def build_prompt(ctx: "InvocationContext") -> str:
    """Render the session into a single prompt string for the SDK.

    Walks ``ctx.session.events`` in order and renders each turn as a
    ``User:``/``Assistant:`` line. The new user message is already the last event
    appended by the ``Runner``, so it naturally terminates the transcript.
    ``thought`` parts are skipped; only ``text`` parts contribute.

    Args:
        ctx (google.adk.agents.invocation_context.InvocationContext): Invocation
            context holding the session.

    Returns:
        str: The flattened transcript. When the session has a single user turn
        this is just that message.
    """
    lines: list[str] = []
    for event in ctx.session.events:
        if event.content is None or not event.content.parts:
            continue
        text = "".join(
            part.text for part in event.content.parts if part.text and not part.thought
        ).strip()
        if not text:
            continue
        prefix = _USER_PREFIX if event.author == "user" else _ASSISTANT_PREFIX
        lines.append(f"{prefix}: {text}")

    # Single user turn: pass the raw message instead of a labelled transcript.
    if len(lines) == 1 and lines[0].startswith(f"{_USER_PREFIX}: "):
        return lines[0][len(_USER_PREFIX) + 2 :]

    return "\n".join(lines)


def sdk_message_to_events(
    message: "Message", author: str, invocation_id: str
) -> list[Event]:
    """Convert one SDK stream message into ADK events.

    Only :class:`~claude_agent_sdk.AssistantMessage` carries renderable content
    and is translated; other message types (user/system/result) produce no
    events here. Final usage/session bookkeeping is handled by the caller.

    Args:
        message (claude_agent_sdk.Message): A message yielded by the SDK stream.
        author (str): Event author (the agent name).
        invocation_id (str): The ADK invocation id to stamp on each event.

    Returns:
        list[google.adk.events.event.Event]: Zero or more events for this message.
    """
    if not isinstance(message, AssistantMessage):
        return []

    events: list[Event] = []
    for block in message.content:
        part: types.Part | None = None
        if isinstance(block, TextBlock):
            part = types.Part(text=block.text)
        elif isinstance(block, ThinkingBlock):
            part = types.Part(text=block.thinking, thought=True)
        elif isinstance(block, ToolUseBlock):
            part = types.Part(
                function_call=types.FunctionCall(
                    id=block.id, name=block.name, args=block.input
                )
            )

        if part is None:
            continue

        events.append(
            Event(
                invocation_id=invocation_id,
                author=author,
                content=types.Content(role="model", parts=[part]),
            )
        )

    return events
