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

"""Translation between ADK session/events and Pi RPC events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from google.adk.events.event import Event
from google.genai import types

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext

_USER_PREFIX = "User"
_ASSISTANT_PREFIX = "Assistant"


def build_prompt(ctx: "InvocationContext") -> str:
    """Render ADK session history into a text prompt for Pi RPC Phase 1."""

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


def make_text_event(
    text: str, author: str, invocation_id: str, *, thought: bool = False
) -> Event:
    return Event(
        invocation_id=invocation_id,
        author=author,
        content=types.Content(
            role="model", parts=[types.Part(text=text, thought=thought)]
        ),
    )


class PiEventTranslator:
    """Stateful converter for one Pi turn."""

    def __init__(self, *, author: str, invocation_id: str):
        self.author = author
        self.invocation_id = invocation_id
        self.emitted_text = False

    def event_to_adk_events(self, event: dict[str, Any]) -> list[Event]:
        event_type = event.get("type")
        if event_type == "message_update":
            return self._message_update_to_events(event)
        if event_type == "tool_execution_start":
            return [self._tool_call_event(event)]
        if event_type == "tool_execution_end":
            return [self._tool_response_event(event)]
        if event_type in {"message_end", "turn_end"} and not self.emitted_text:
            text = _message_text(event.get("message"))
            if text:
                self.emitted_text = True
                return [make_text_event(text, self.author, self.invocation_id)]
        if event_type == "agent_end" and not self.emitted_text:
            text = _last_assistant_text(event.get("messages"))
            if text:
                self.emitted_text = True
                return [make_text_event(text, self.author, self.invocation_id)]
        return []

    def _message_update_to_events(self, event: dict[str, Any]) -> list[Event]:
        update = event.get("assistantMessageEvent")
        if not isinstance(update, dict):
            return []

        update_type = update.get("type")
        if update_type == "text_delta" and update.get("delta"):
            self.emitted_text = True
            return [
                make_text_event(str(update["delta"]), self.author, self.invocation_id)
            ]
        if update_type == "thinking_delta" and update.get("delta"):
            return [
                make_text_event(
                    str(update["delta"]),
                    self.author,
                    self.invocation_id,
                    thought=True,
                )
            ]
        if update_type == "error":
            reason = update.get("reason") or "error"
            raise RuntimeError(f"Pi assistant error: {reason}")
        return []

    def _tool_call_event(self, event: dict[str, Any]) -> Event:
        return Event(
            invocation_id=self.invocation_id,
            author=self.author,
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id=str(event.get("toolCallId") or ""),
                            name=str(event.get("toolName") or "tool"),
                            args=_dict_or_empty(event.get("args")),
                        )
                    )
                ],
            ),
        )

    def _tool_response_event(self, event: dict[str, Any]) -> Event:
        name = str(event.get("toolName") or "tool")
        response = {
            "result": _tool_result_to_response(event.get("result")),
            "is_error": bool(event.get("isError")),
        }
        return Event(
            invocation_id=self.invocation_id,
            author=self.author,
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=str(event.get("toolCallId") or ""),
                            name=name,
                            response=response,
                        )
                    )
                ],
            ),
        )


def _message_text(message: Any) -> str:
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            parts.append(str(item["text"]))
    return "".join(parts).strip()


def _last_assistant_text(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        text = _message_text(message)
        if text:
            return text
    return ""


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tool_result_to_response(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    content = result.get("content")
    response: dict[str, Any] = {}
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text") or ""))
        if texts:
            response["content"] = "".join(texts)
    if "structuredContent" in result:
        response["structured_content"] = result["structuredContent"]
    if "details" in result:
        response["details"] = result.get("details") or {}
    if "isError" in result:
        response["is_error"] = bool(result.get("isError"))
    return response or result
