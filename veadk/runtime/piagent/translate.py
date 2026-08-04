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
_THINKING_MESSAGE_TYPES = {
    "thinking",
    "thought",
    "reasoning",
    "reasoning_message",
    "assistant_thought",
}


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

    user_text = _content_text(getattr(ctx, "user_content", None))
    if user_text and (not lines or lines[-1] != f"{_USER_PREFIX}: {user_text}"):
        lines.append(f"{_USER_PREFIX}: {user_text}")

    if len(lines) == 1 and lines[0].startswith(f"{_USER_PREFIX}: "):
        return lines[0][len(_USER_PREFIX) + 2 :]

    return "\n".join(lines)


def _content_text(content: Any) -> str:
    if content is None or not getattr(content, "parts", None):
        return ""
    return "".join(
        part.text for part in content.parts if part.text and not part.thought
    ).strip()


def make_text_event(
    text: str,
    author: str,
    invocation_id: str,
    *,
    thought: bool = False,
    partial: bool = False,
) -> Event:
    return make_model_event(
        [types.Part(text=text, thought=thought)],
        author=author,
        invocation_id=invocation_id,
        partial=partial,
    )


def make_model_event(
    parts: list[types.Part],
    *,
    author: str,
    invocation_id: str,
    partial: bool = False,
) -> Event:
    return Event(
        invocation_id=invocation_id,
        author=author,
        partial=partial,
        content=types.Content(role="model", parts=parts),
    )


class PiEventTranslator:
    """Stateful converter for one Pi turn."""

    def __init__(self, *, author: str, invocation_id: str):
        self.author = author
        self.invocation_id = invocation_id
        self.emitted_text = False
        self._thinking_parts: list[str] = []
        self._text_parts: list[str] = []

    def event_to_adk_events(self, event: dict[str, Any]) -> list[Event]:
        event_type = event.get("type")
        if event_type == "message_update":
            return self._message_update_to_events(event)
        if event_type == "tool_execution_start":
            return [self._tool_call_event(event)]
        if event_type == "tool_execution_update":
            return self._tool_update_events(event)
        if event_type == "tool_execution_end":
            return [self._tool_response_event(event)]
        if event_type == "message_end":
            message = event.get("message")
            if _message_is_thinking(message):
                return []
            return self._flush_events(preferred_text=_message_text(message))
        if event_type == "turn_end":
            return self._flush_events()
        if event_type == "agent_end":
            return self._flush_events(
                preferred_text=_last_assistant_text(event.get("messages")),
            )
        if event_type == "agent_settled":
            return self._flush_events()
        return []

    def _message_update_to_events(self, event: dict[str, Any]) -> list[Event]:
        update = event.get("assistantMessageEvent")
        if not isinstance(update, dict):
            return []

        update_type = update.get("type")
        if update_type == "text_delta" and update.get("delta"):
            delta = str(update["delta"])
            self._text_parts.append(delta)
            return [
                make_text_event(
                    delta,
                    author=self.author,
                    invocation_id=self.invocation_id,
                    partial=True,
                )
            ]
        if update_type == "thinking_delta" and update.get("delta"):
            delta = str(update["delta"])
            self._thinking_parts.append(delta)
            return [
                make_text_event(
                    delta,
                    author=self.author,
                    invocation_id=self.invocation_id,
                    thought=True,
                    partial=True,
                )
            ]
        if update_type == "error":
            reason = update.get("reason") or "error"
            raise RuntimeError(f"Pi assistant error: {reason}")
        return []

    def _flush_events(self, *, preferred_text: str = "") -> list[Event]:
        if self.emitted_text:
            self._thinking_parts.clear()
            self._text_parts.clear()
            return []

        if preferred_text:
            text = preferred_text
            self._text_parts.clear()
        else:
            text = self._drain_text()
        if not text:
            return []

        parts = self._drain_pending_parts(include_text=False)
        parts.append(types.Part(text=text, thought=False))
        self.emitted_text = True
        return [
            make_model_event(
                parts,
                author=self.author,
                invocation_id=self.invocation_id,
            )
        ]

    def _drain_pending_parts(self, *, include_text: bool = True) -> list[types.Part]:
        parts: list[types.Part] = []
        thinking = self._drain_thinking()
        if thinking:
            parts.append(types.Part(text=thinking, thought=True))

        if include_text:
            text = self._drain_text()
            if text:
                parts.append(types.Part(text=text, thought=False))

        return parts

    def _drain_thinking(self) -> str:
        text = "".join(self._thinking_parts).strip()
        self._thinking_parts.clear()
        return text

    def _drain_text(self) -> str:
        text = "".join(self._text_parts).strip()
        self._text_parts.clear()
        return text

    def _tool_call_event(self, event: dict[str, Any]) -> Event:
        parts = self._drain_pending_parts()
        parts.append(
            types.Part(
                function_call=types.FunctionCall(
                    id=str(event.get("toolCallId") or ""),
                    name=str(event.get("toolName") or "tool"),
                    args=_dict_or_empty(event.get("args")),
                )
            )
        )
        return Event(
            invocation_id=self.invocation_id,
            author=self.author,
            content=types.Content(role="model", parts=parts),
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

    def _tool_update_events(self, event: dict[str, Any]) -> list[Event]:
        text = _tool_update_text(event)
        if not text:
            return []
        tool_name = str(event.get("toolName") or "tool")
        return [
            make_text_event(
                f"[{tool_name}] {text}",
                author=self.author,
                invocation_id=self.invocation_id,
                thought=True,
                partial=True,
            )
        ]


def _message_text(message: Any) -> str:
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return ""
    if _message_is_thinking(message):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict) or _content_item_is_thinking(item):
            continue
        if item.get("type") in (None, "text", "output_text") and item.get("text"):
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


def _message_is_thinking(message: Any) -> bool:
    if not isinstance(message, dict):
        return False

    if _truthy_flag(
        message,
        "thought",
        "isThought",
        "is_thought",
        "thinking",
        "isThinking",
        "is_thinking",
    ):
        return True

    message_type = _normalized_type(
        message.get("type") or message.get("messageType") or message.get("message_type")
    )
    if _is_thinking_type(message_type):
        return True

    content = message.get("content")
    if not isinstance(content, list):
        return False

    text_items = [
        item for item in content if isinstance(item, dict) and item.get("text")
    ]
    return bool(text_items) and all(
        _content_item_is_thinking(item) for item in text_items
    )


def _content_item_is_thinking(item: dict[str, Any]) -> bool:
    if _truthy_flag(
        item,
        "thought",
        "isThought",
        "is_thought",
        "thinking",
        "isThinking",
        "is_thinking",
    ):
        return True
    item_type = _normalized_type(
        item.get("type") or item.get("contentType") or item.get("content_type")
    )
    return _is_thinking_type(item_type)


def _truthy_flag(data: dict[str, Any], *keys: str) -> bool:
    return any(bool(data.get(key)) for key in keys)


def _normalized_type(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_thinking_type(value: str) -> bool:
    return (
        value in _THINKING_MESSAGE_TYPES or "thinking" in value or "reasoning" in value
    )


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tool_result_to_response(result: Any) -> Any:
    if isinstance(result, str):
        return {"content": result}
    if not isinstance(result, dict):
        return result
    content = result.get("content")
    response: dict[str, Any] = {}
    details: dict[str, Any] = {}
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text") or ""))
        if texts:
            response["content"] = "".join(texts)
    elif isinstance(content, str):
        response["content"] = content
    for key in ("text", "output", "message"):
        if not response.get("content") and result.get(key) is not None:
            response["content"] = str(result[key])
    if not response.get("content"):
        shell_parts: list[str] = []
        if result.get("stdout"):
            shell_parts.append(str(result["stdout"]))
        if result.get("stderr"):
            shell_parts.append(str(result["stderr"]))
        if shell_parts:
            response["content"] = "\n".join(shell_parts)
    if "structuredContent" in result:
        response["structured_content"] = result["structuredContent"]
    if isinstance(result.get("details"), dict):
        details.update(result["details"])
    for key in (
        "stdout",
        "stderr",
        "exitCode",
        "exit_code",
        "code",
        "path",
        "diff",
        "oldText",
        "newText",
        "bytes",
    ):
        if key in result:
            details[key] = result[key]
    if details:
        response["details"] = details
    if "isError" in result:
        response["is_error"] = bool(result.get("isError"))
    return response or result


def _tool_update_text(event: dict[str, Any]) -> str:
    for key in ("delta", "message", "stdout", "stderr", "text", "output"):
        value = event.get(key)
        if value:
            return str(value).strip()

    for key in ("partialResult", "result", "update"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            text = _tool_update_text(value)
            if text:
                return text
    return ""
