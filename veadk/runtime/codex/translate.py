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

import json
from enum import Enum
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


def _item_dict(item: Any) -> dict[str, Any]:
    """Best-effort plain-dict view of a Codex result item."""
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return {}


def _scalar(value: Any) -> Any:
    """Normalize an enum/pydantic value to a JSON-friendly scalar."""
    if isinstance(value, Enum):
        return value.value
    return getattr(value, "value", value)


def _join(entries: Any) -> str:
    """Join a ``list[str]`` (or list of ``{"text": ...}``) into one string."""
    parts: list[str] = []
    for entry in entries or []:
        if isinstance(entry, str):
            parts.append(entry)
        elif isinstance(entry, dict) and entry.get("text"):
            parts.append(str(entry["text"]))
    return "\n".join(p.strip() for p in parts if p and p.strip())


def _parse_args(raw: Any) -> dict[str, Any]:
    """Coerce a tool-call ``arguments`` value into a dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"input": parsed}
        except json.JSONDecodeError:
            return {"input": raw}
    return {}


def _tool_call(
    data: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """Map a tool-call thread item to ``(name, args, response)``.

    Covers every tool item type the Codex SDK can surface; returns ``None`` for
    non-tool items.
    """
    itype = data.get("type")
    status = _scalar(data.get("status"))
    if itype == "commandExecution":
        return (
            "exec_command",
            {"command": data.get("command", ""), "cwd": data.get("cwd")},
            {
                "output": data.get("aggregated_output", ""),
                "exit_code": data.get("exit_code"),
                "status": status,
            },
        )
    if itype == "mcpToolCall":
        name = ".".join(p for p in (data.get("server"), data.get("tool")) if p)
        return (
            name or "mcp_tool",
            _parse_args(data.get("arguments")),
            {
                "result": data.get("result"),
                "error": data.get("error"),
                "status": status,
            },
        )
    if itype == "dynamicToolCall":
        name = ".".join(p for p in (data.get("namespace"), data.get("tool")) if p)
        return (
            name or "tool",
            _parse_args(data.get("arguments")),
            {
                "content": data.get("content_items"),
                "success": data.get("success"),
                "status": status,
            },
        )
    if itype == "fileChange":
        return (
            "apply_patch",
            {"changes": data.get("changes")},
            {"status": status},
        )
    if itype == "webSearch":
        return (
            "web_search",
            {"query": data.get("query"), "action": data.get("action")},
            {"status": "completed"},
        )
    return None


def _event(author: str, invocation_id: str, role: str, part: types.Part) -> Event:
    return Event(
        invocation_id=invocation_id,
        author=author,
        content=types.Content(role=role, parts=[part]),
    )


def result_to_events(result: Any, author: str, invocation_id: str) -> list[Event]:
    """Convert a Codex run result into ADK events, faithfully and in order.

    A Codex turn is multi-step. Rather than collapse it to ``final_response``,
    walk ``result.items`` and forward each step as its own ADK event, mapping
    Codex thread items onto the genai part the matching ADK event expects:

    - ``reasoning`` -> a thought text part,
    - tool calls (``commandExecution`` / ``mcpToolCall`` / ``dynamicToolCall``
      / ``fileChange`` / ``webSearch``) -> a ``function_call`` part plus a
      matching ``function_response`` part carrying the tool's output,
    - ``agentMessage`` / ``plan`` / any other text-bearing item -> a text part,
    - ``userMessage`` -> skipped (ADK already owns the user turn).

    If nothing maps, fall back to ``final_response`` so a turn is never empty.

    Args:
        result (Any): The object returned by ``thread.run(...)``.
        author (str): Event author (the agent name).
        invocation_id (str): The ADK invocation id to stamp on each event.

    Returns:
        list[google.adk.events.event.Event]: The turn's events in order.
    """
    events: list[Event] = []
    for item in getattr(result, "items", None) or []:
        data = _item_dict(item)
        itype = str(data.get("type", ""))

        if itype == "userMessage":
            continue

        if itype == "reasoning":
            text = _join(data.get("summary")) or _join(data.get("content"))
            if text:
                events.append(
                    _event(
                        author,
                        invocation_id,
                        "model",
                        types.Part(text=text, thought=True),
                    )
                )
            continue

        call = _tool_call(data)
        if call is not None:
            name, args, response = call
            call_id = data.get("id") or f"call_{len(events)}"
            events.append(
                _event(
                    author,
                    invocation_id,
                    "model",
                    types.Part(
                        function_call=types.FunctionCall(
                            id=call_id, name=name, args=args
                        )
                    ),
                )
            )
            events.append(
                _event(
                    author,
                    invocation_id,
                    "user",
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call_id, name=name, response=response
                        )
                    ),
                )
            )
            continue

        if data.get("text"):  # agentMessage, plan, and any text-bearing item
            events.append(
                _event(
                    author, invocation_id, "model", types.Part(text=str(data["text"]))
                )
            )

    if events:
        return events

    # Fallback: never emit nothing.
    text = getattr(result, "final_response", None)
    if not text:
        return []
    return [_event(author, invocation_id, "model", types.Part(text=text))]
