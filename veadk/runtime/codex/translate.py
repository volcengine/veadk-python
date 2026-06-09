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

"""Translation between ADK and the Codex SDK.

- :func:`build_prompt` flattens an ADK session into a single prompt string
  (stateless replay; ADK stays the single source of truth). This mirrors the
  ``cc`` runtime's helper but is duplicated here so the ``codex`` package does
  not import ``claude_agent_sdk``.
- :func:`result_to_events` maps a Codex run result into ADK events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from google.adk.events.event import Event
from google.genai import types

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext

_USER_PREFIX = "User"
_ASSISTANT_PREFIX = "Assistant"


def build_prompt(ctx: "InvocationContext") -> str:
    """Render the session into a single prompt string for the Codex SDK.

    Walks ``ctx.session.events`` in order, rendering each turn as a
    ``User:``/``Assistant:`` line; the new user message is the last event the
    ``Runner`` appended, so it terminates the transcript. ``thought`` parts are
    skipped.

    Args:
        ctx (google.adk.agents.invocation_context.InvocationContext): Invocation
            context holding the session.

    Returns:
        str: The flattened transcript (just the message for a single user turn).
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

    if len(lines) == 1 and lines[0].startswith(f"{_USER_PREFIX}: "):
        return lines[0][len(_USER_PREFIX) + 2 :]

    return "\n".join(lines)


def _reasoning_summary(result: Any) -> str:
    """Join the reasoning-summary text from a result's items, if any.

    A reasoning model (e.g. DeepSeek) sometimes ends a turn with only a
    ``reasoning`` item and no final ``agentMessage``, leaving
    ``final_response`` empty. In that case the reasoning summary is the only
    thing the model produced, so we surface it rather than print nothing.
    """
    parts: list[str] = []
    for item in getattr(result, "items", None) or []:
        data = item.model_dump() if hasattr(item, "model_dump") else item
        if not isinstance(data, dict) or "reasoning" not in str(data.get("type", "")):
            continue
        for entry in data.get("summary") or []:
            if isinstance(entry, str):
                parts.append(entry)
            elif isinstance(entry, dict) and entry.get("text"):
                parts.append(str(entry["text"]))
    return "\n".join(p.strip() for p in parts if p and p.strip())


def result_to_events(result: Any, author: str, invocation_id: str) -> list[Event]:
    """Convert a Codex run result into ADK events.

    The Codex SDK's run result exposes the assistant's final text as
    ``final_response``. When a turn ends with reasoning but no final message
    (``final_response`` empty), fall back to the reasoning summary so the
    caller never receives a silently empty turn.

    Args:
        result (Any): The object returned by ``thread.run(...)``.
        author (str): Event author (the agent name).
        invocation_id (str): The ADK invocation id to stamp on the event.

    Returns:
        list[google.adk.events.event.Event]: One text event, or empty if the
        result carried neither a final message nor reasoning.
    """
    text = getattr(result, "final_response", None)
    if not text:
        summary = _reasoning_summary(result)
        if summary:
            text = (
                "[The model produced only reasoning, no final answer this turn]\n\n"
                f"{summary}"
            )
    if not text:
        return []

    return [
        Event(
            invocation_id=invocation_id,
            author=author,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
        )
    ]
