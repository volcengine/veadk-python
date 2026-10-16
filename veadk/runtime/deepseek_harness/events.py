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

"""Translate DeepSeek Harness session events into ADK events."""

from __future__ import annotations

import json
from typing import Any

from google.adk.events.event import Event
from google.genai import types


class DeepSeekHarnessEventTranslator:
    """Stateful DSH event to ADK event translator for one VeADK turn."""

    def __init__(
        self,
        *,
        author: str,
        invocation_id: str,
        bridged_tool_names: set[str] | None = None,
    ) -> None:
        self.author = author
        self.invocation_id = invocation_id
        self.bridged_tool_names = set(bridged_tool_names or ())
        self._seen: set[tuple[str, str]] = set()
        self._tool_names_by_call_id: dict[str, str] = {}

    def notification_to_adk_events(self, notification: Any) -> list[Event]:
        method = getattr(notification, "method", "")
        payload = getattr(notification, "payload", None)
        if method != "session.event" or not isinstance(payload, dict):
            return []
        event = payload.get("event")
        if not isinstance(event, dict):
            return []
        session_id = str(payload.get("sessionId") or "")
        return self.event_to_adk_events(event, session_id=session_id)

    def result_events_to_adk_events(self, events: list[dict[str, Any]]) -> list[Event]:
        output: list[Event] = []
        for event in events:
            output.extend(self.event_to_adk_events(event, session_id=""))
        return output

    def event_to_adk_events(
        self, event: dict[str, Any], *, session_id: str = ""
    ) -> list[Event]:
        if not self._mark_seen(event, session_id=session_id):
            return []
        event_type = str(event.get("type") or "")
        if event_type == "agent/assistant-stream":
            return self._assistant_stream_event(event)
        if event_type == "assistant/message":
            return self._assistant_message_stream_events(event)
        if event_type == "tool/call":
            return self._tool_call_event(event)
        if event_type == "tool/result":
            return self._tool_result_event(event)
        return []

    def _mark_seen(self, event: dict[str, Any], *, session_id: str) -> bool:
        seq = event.get("seq")
        if isinstance(seq, int):
            key = (session_id, str(seq))
        else:
            key = (session_id, json.dumps(event, sort_keys=True, default=str))
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def _assistant_stream_event(self, event: dict[str, Any]) -> list[Event]:
        data = event.get("data")
        if not isinstance(data, dict):
            return []
        frame = data.get("frame")
        if not isinstance(frame, dict) or frame.get("type") != "chunk":
            return []
        chunk = frame.get("chunk")
        if not isinstance(chunk, dict):
            return []

        chunk_type = chunk.get("type")
        text = ""
        thought = False
        if chunk_type == "text-delta":
            text = str(chunk.get("text") or "")
        elif chunk_type == "reasoning-delta":
            text = str(chunk.get("text") or "")
            thought = True
        elif chunk_type in ("text-chunks", "reasoning-chunks"):
            texts = chunk.get("texts")
            if isinstance(texts, list):
                text = "".join(str(item) for item in texts)
            thought = chunk_type == "reasoning-chunks"
        if not text:
            return []

        return [
            Event(
                invocation_id=self.invocation_id,
                author=self.author,
                partial=True,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=text, thought=thought)],
                ),
            )
        ]

    def _assistant_message_stream_events(self, event: dict[str, Any]) -> list[Event]:
        data = event.get("data")
        if not isinstance(data, dict):
            return []
        stream = data.get("stream")
        if not isinstance(stream, list):
            return []

        output: list[Event] = []
        for item in stream:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "")
            if item_type == "chunk":
                chunk = item.get("chunk")
                text, thought = _stream_chunk_text(chunk)
            elif item_type in ("text-chunks", "reasoning-chunks"):
                text, thought = _stream_chunk_text(item)
            else:
                continue
            if not text:
                continue
            output.append(
                Event(
                    invocation_id=self.invocation_id,
                    author=self.author,
                    partial=True,
                    content=types.Content(
                        role="model",
                        parts=[types.Part(text=text, thought=thought)],
                    ),
                )
            )
        return output

    def _tool_call_event(self, event: dict[str, Any]) -> list[Event]:
        data = event.get("data")
        if not isinstance(data, dict):
            return []
        name = str(data.get("name") or "")
        if not name or name in self.bridged_tool_names:
            return []
        call_id = str(data.get("callId") or "")
        if call_id:
            self._tool_names_by_call_id[call_id] = name
        args = _parse_arguments(data.get("arguments"))
        return [
            Event(
                invocation_id=self.invocation_id,
                author=self.author,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id=call_id,
                                name=name,
                                args=args,
                            )
                        )
                    ],
                ),
            )
        ]

    def _tool_result_event(self, event: dict[str, Any]) -> list[Event]:
        data = event.get("data")
        if not isinstance(data, dict):
            return []
        message = data.get("message")
        owner = message if isinstance(message, dict) else data
        call_id = str(owner.get("toolCallId") or data.get("callId") or "")
        name = str(
            owner.get("name")
            or data.get("name")
            or self._tool_names_by_call_id.get(call_id, "")
        )
        if name and name in self.bridged_tool_names:
            return []
        response = _content_response(owner.get("content"))
        if owner.get("isError") or data.get("error"):
            response = {
                "status": "failed",
                "response": response,
                "error": data.get("error"),
            }
        return [
            Event(
                invocation_id=self.invocation_id,
                author=self.author,
                content=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=call_id,
                                name=name,
                                response=response,
                            )
                        )
                    ],
                ),
            )
        ]


def _parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"arguments": value}
    return {}


def _content_response(content: Any) -> dict[str, Any]:
    if isinstance(content, list):
        texts = [
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if texts:
            return {"content": "".join(texts)}
        return {"content": content}
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        return {"content": content}
    return {}


def _stream_chunk_text(chunk: Any) -> tuple[str, bool]:
    if not isinstance(chunk, dict):
        return "", False

    chunk_type = str(chunk.get("type") or "")
    if chunk_type == "text-delta":
        return str(chunk.get("text") or ""), False
    if chunk_type == "reasoning-delta":
        return str(chunk.get("text") or ""), True
    if chunk_type in ("text-chunks", "reasoning-chunks"):
        texts = chunk.get("texts")
        if isinstance(texts, list):
            return "".join(str(item) for item in texts), (
                chunk_type == "reasoning-chunks"
            )
    return "", False
