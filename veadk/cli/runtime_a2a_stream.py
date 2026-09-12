"""Incremental A2A SSE to Studio ADK event conversion."""

from __future__ import annotations

import json
import codecs
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

_MAX_EVENT_TEXT_CHARS = 64_000


class A2AStreamDecoder:
    def __init__(self) -> None:
        self._buffer = ""
        self._utf8_decoder = codecs.getincrementaldecoder("utf-8")()
        self._seen_event_ids: set[tuple[str, str]] = set()
        self._partial_text = ""
        self._heartbeat_states: set[tuple[str, str]] = set()

    def feed(self, chunk: str | bytes) -> list[dict[str, Any]]:
        text = (
            self._utf8_decoder.decode(chunk, final=False)
            if isinstance(chunk, bytes)
            else chunk
        )
        self._buffer += text.replace("\r\n", "\n")
        frames: list[dict[str, Any]] = []
        while "\n\n" in self._buffer:
            raw, self._buffer = self._buffer.split("\n\n", 1)
            payload = _frame_payload(raw)
            if payload is not None and self._is_new(payload):
                frames.append(payload)
        return frames

    def finish(self) -> list[dict[str, Any]]:
        self._buffer += self._utf8_decoder.decode(b"", final=True)
        payload = _frame_payload(self._buffer) if self._buffer.strip() else None
        self._buffer = ""
        return [payload] if payload is not None and self._is_new(payload) else []

    def _is_new(self, envelope: Mapping[str, Any]) -> bool:
        result = envelope.get("result")
        if not isinstance(result, Mapping):
            return True
        task_id = str(result.get("taskId") or result.get("id") or "")
        event_id = _a2a_event_id(result)
        if not event_id:
            return True
        key = (task_id, event_id)
        if key in self._seen_event_ids:
            return False
        self._seen_event_ids.add(key)
        return True

    def project(self, event: Any, *, author: str) -> list[dict[str, Any]]:
        """Project one A2A event and suppress cumulative partial replays."""
        projected = a2a_event_to_studio_events(event, author=author)
        task_id = (
            str(event.get("taskId") or event.get("id") or "unknown")
            if isinstance(event, Mapping)
            else "unknown"
        )
        metadata = event.get("metadata") if isinstance(event, Mapping) else None
        cumulative_snapshot = (
            isinstance(event, Mapping)
            and event.get("kind") == "status-update"
            and isinstance(metadata, Mapping)
            and "adk_usage_metadata" in metadata
        )
        output: list[dict[str, Any]] = []
        for item in projected:
            item_metadata = item.get("customMetadata")
            heartbeat_state = (
                str(item_metadata.get("a2aStatus") or "")
                if isinstance(item_metadata, Mapping)
                else ""
            )
            if heartbeat_state:
                heartbeat_key = (task_id, heartbeat_state)
                if heartbeat_key in self._heartbeat_states:
                    continue
                self._heartbeat_states.add(heartbeat_key)
            if item.get("partial") is not True:
                output.append(item)
                continue
            parts = item.get("content", {}).get("parts", [])
            if len(parts) != 1 or not isinstance(parts[0], Mapping):
                output.append(item)
                continue
            text = str(parts[0].get("text") or "")
            if not text:
                output.append(item)
                continue
            if cumulative_snapshot and text == self._partial_text:
                continue
            if (
                cumulative_snapshot
                and self._partial_text
                and text.startswith(self._partial_text)
            ):
                suffix = text[len(self._partial_text) :]
                self._partial_text = text
                if not suffix:
                    continue
                item = {
                    **item,
                    "content": {
                        **item["content"],
                        "parts": [{**parts[0], "text": suffix}],
                    },
                }
            else:
                self._partial_text += text
            output.append(item)
        return output


def _frame_payload(frame: str) -> dict[str, Any] | None:
    data = "\n".join(
        line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:")
    )
    if not data:
        return None
    value = json.loads(data)
    return value if isinstance(value, dict) else None


def _a2a_event_id(result: Mapping[str, Any]) -> str:
    artifact = result.get("artifact")
    if not isinstance(artifact, Mapping):
        return ""
    for part in artifact.get("parts") or []:
        if not isinstance(part, Mapping):
            continue
        data = part.get("data")
        if isinstance(data, Mapping) and data.get("eventId"):
            return str(data["eventId"])
    return ""


def is_method_not_supported(payload: Any) -> bool:
    error = payload.get("error") if isinstance(payload, Mapping) else None
    return isinstance(error, Mapping) and error.get("code") in {-32601, -32004}


def a2a_error_message(payload: Any) -> str:
    error = payload.get("error") if isinstance(payload, Mapping) else None
    if not isinstance(error, Mapping):
        return ""
    return str(error.get("message") or error.get("code") or "A2A stream error")


def a2a_event_to_studio_events(event: Any, *, author: str) -> list[dict[str, Any]]:
    if not isinstance(event, Mapping):
        return []
    if event.get("kind") == "status-update":
        status = event.get("status")
        if not isinstance(status, Mapping) or event.get("final") is True:
            return []
        state = str(status.get("state") or "")
        if state not in {"submitted", "working"}:
            return []
        message = status.get("message")
        if isinstance(message, Mapping) and message.get("role") == "user":
            return []
        if state == "working" and isinstance(message, Mapping):
            projected = (
                _message_to_partial_events(message, author=author)
                if message.get("role") == "agent"
                else []
            )
            if projected:
                return projected
        task_id = str(event.get("taskId") or event.get("id") or "unknown")
        return [
            {
                "id": f"a2a-{task_id}-{state}",
                "author": author,
                "partial": True,
                "content": {"role": "model", "parts": []},
                "customMetadata": {"a2aStatus": state},
            }
        ]
    if event.get("kind") == "task":
        events: list[dict[str, Any]] = []
        for artifact in event.get("artifacts") or []:
            events.extend(
                _artifact_to_studio_events(
                    artifact,
                    author=author,
                    turn_complete=True,
                )
            )
        return events
    if event.get("kind") != "artifact-update":
        return []
    return _artifact_to_studio_events(
        event.get("artifact"),
        author=author,
        turn_complete=event.get("lastChunk") is True,
    )


def _message_to_partial_events(
    message: Mapping[str, Any], *, author: str
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    message_id = str(message.get("messageId") or uuid4())
    for index, part in enumerate(message.get("parts") or []):
        if not isinstance(part, Mapping):
            continue
        metadata = part.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("adk_thought"):
            continue
        text = str(part.get("text") or "")[:_MAX_EVENT_TEXT_CHARS]
        if not text:
            continue
        events.append(
            _text_event(
                text,
                author=author,
                event_id=f"{message_id}-{index}",
                partial=True,
            )
        )
    return events


def _artifact_to_studio_events(
    artifact: Any, *, author: str, turn_complete: bool
) -> list[dict[str, Any]]:
    if not isinstance(artifact, Mapping):
        return []
    events: list[dict[str, Any]] = []
    for part in artifact.get("parts") or []:
        if not isinstance(part, Mapping):
            continue
        metadata = part.get("metadata")
        text = str(part.get("text") or "").strip()
        if text and not (isinstance(metadata, Mapping) and metadata.get("adk_thought")):
            events.append(
                _text_event(
                    text,
                    author=author,
                    event_id=str(artifact.get("artifactId") or uuid4()),
                    partial=not turn_complete,
                    turn_complete=turn_complete,
                )
            )
            continue
        data = part.get("data")
        if (
            isinstance(metadata, Mapping)
            and metadata.get("schemaVersion") == "mpa.sandbox-event.v1"
            and isinstance(data, Mapping)
        ):
            projected = _sandbox_event(data, author=author)
            if projected is not None:
                events.append(projected)
            continue
        if not isinstance(data, Mapping):
            continue
        response = data.get("response")
        result = response.get("result") if isinstance(response, Mapping) else None
        text = str(result or "").strip()[:_MAX_EVENT_TEXT_CHARS]
        if text:
            events.append(
                _text_event(
                    text,
                    author=author,
                    event_id=str(artifact.get("artifactId") or uuid4()),
                    partial=False,
                    turn_complete=turn_complete,
                )
            )
    return events


def _sandbox_event(data: Mapping[str, Any], *, author: str) -> dict[str, Any] | None:
    event_type = str(data.get("eventType") or "")
    event_id = str(data.get("eventId") or uuid4())
    invocation_id = str(data.get("invocationId") or "")
    payload = data.get("payload")
    payload = dict(payload) if isinstance(payload, Mapping) else {}
    for key in ("text", "output", "finalMessage", "message"):
        if isinstance(payload.get(key), str):
            payload[key] = payload[key][:_MAX_EVENT_TEXT_CHARS]
    common = {
        "id": event_id,
        "author": author,
        "invocationId": invocation_id,
        "customMetadata": {
            "source": "sandbox",
            "eventType": event_type,
            "sourceEventId": event_id,
        },
    }
    if event_type == "message.delta":
        text = str(payload.get("text") or "")[:_MAX_EVENT_TEXT_CHARS]
        return (
            _text_event(
                text,
                author=author,
                event_id=event_id,
                invocation_id=invocation_id,
                partial=True,
                custom_metadata=common["customMetadata"],
            )
            if text
            else None
        )
    if event_type == "tool.call":
        return {
            **common,
            "partial": False,
            "content": {
                "role": "model",
                "parts": [
                    {
                        "functionCall": {
                            "id": str(payload.get("commandId") or ""),
                            "name": str(payload.get("name") or "command"),
                            "args": payload,
                        }
                    }
                ],
            },
        }
    if event_type in {"tool.output", "tool.result", "tool.error"}:
        return {
            **common,
            "partial": event_type == "tool.output",
            "content": {
                "role": "model",
                "parts": [
                    {
                        "functionResponse": {
                            "id": str(payload.get("commandId") or ""),
                            "name": str(payload.get("name") or "command"),
                            "response": payload,
                        }
                    }
                ],
            },
        }
    text = str(payload.get("text") or payload.get("message") or "")[
        :_MAX_EVENT_TEXT_CHARS
    ]
    if text:
        return _text_event(
            text,
            author=author,
            event_id=event_id,
            invocation_id=invocation_id,
            partial=event_type.endswith(".delta"),
            custom_metadata=common["customMetadata"],
        )
    return None


def _text_event(
    text: str,
    *,
    author: str,
    event_id: str,
    invocation_id: str = "",
    partial: bool,
    turn_complete: bool = False,
    custom_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": event_id,
        "author": author,
        "partial": partial,
        "content": {"role": "model", "parts": [{"text": text}]},
    }
    if invocation_id:
        event["invocationId"] = invocation_id
    if turn_complete:
        event["turnComplete"] = True
    if custom_metadata:
        event["customMetadata"] = dict(custom_metadata)
    return event
