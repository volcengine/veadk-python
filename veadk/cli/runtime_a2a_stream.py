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

"""Incremental A2A SSE to Studio ADK event conversion."""

from __future__ import annotations

import codecs
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

_MAX_EVENT_TEXT_CHARS = 64_000


@dataclass
class _ReasoningSegment:
    text: str = ""
    deltas: int = 0
    index: int = 0


class A2AStreamDecoder:
    def __init__(self, *, mpa_a2a: bool = False) -> None:
        self._mpa_a2a = mpa_a2a
        self._mpa_reasoning: dict[tuple[str, str, str], _ReasoningSegment] = {}
        self._buffer = ""
        self._utf8_decoder = codecs.getincrementaldecoder("utf-8")()
        self._seen_event_ids: set[tuple[str, str]] = set()
        self._projected_event_id_counts: dict[str, int] = {}
        self._partial_text = {"answer": "", "thought": ""}
        self._reasoning_text_by_source: dict[tuple[str, str], str] = {}
        self._heartbeat_states: set[tuple[str, str]] = set()
        self._usage_snapshots: dict[str, dict[str, int]] = {}
        self._terminal_state = ""
        self._sandbox_final_answers: dict[str, set[str]] = {}
        self._projected_sandbox_ids: set[tuple[str, str, str, str]] = set()

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
        projected = a2a_event_to_studio_events(
            _coalesce_mpa_thought_parts(event) if self._mpa_a2a else event,
            author=author,
        )
        task_id = (
            str(event.get("taskId") or event.get("id") or "unknown")
            if isinstance(event, Mapping)
            else "unknown"
        )
        metadata = event.get("metadata") if isinstance(event, Mapping) else None
        if isinstance(event, Mapping) and (
            (event.get("kind") == "status-update" and event.get("final") is True)
            or event.get("kind") == "task"
        ):
            status = event.get("status")
            self._terminal_state = (
                str(status.get("state") or "").lower()
                if isinstance(status, Mapping)
                else ""
            )
        cumulative_snapshot = (
            isinstance(event, Mapping)
            and event.get("kind") == "status-update"
            and isinstance(metadata, Mapping)
            and "adk_usage_metadata" in metadata
        )
        if isinstance(metadata, Mapping):
            usage = metadata.get("adk_usage_metadata")
            usage_event = self._usage_event(
                usage,
                author=author,
                event_id=f"a2a-{task_id}-usage",
                source_key=f"primary:{task_id}",
            )
            if usage_event is not None:
                projected.append(usage_event)
        output: list[dict[str, Any]] = []
        for item in projected:
            item_metadata = item.get("customMetadata")
            is_sandbox = (
                isinstance(item_metadata, Mapping)
                and item_metadata.get("source") == "sandbox"
            )
            parts = item.get("content", {}).get("parts", [])
            if is_sandbox and isinstance(item_metadata, Mapping):
                source_id = str(item_metadata.get("sourceEventId") or "")
                if source_id and task_id != "unknown":
                    sandbox_key = (
                        task_id,
                        str(item.get("invocationId") or ""),
                        str(item_metadata.get("eventType") or ""),
                        source_id,
                    )
                    if sandbox_key in self._projected_sandbox_ids:
                        continue
                    self._projected_sandbox_ids.add(sandbox_key)
                if (
                    item_metadata.get("eventType") == "invocation.completed"
                    and task_id != "unknown"
                ):
                    answers = self._sandbox_final_answers.setdefault(task_id, set())
                    answers.update(
                        str(part["text"]).strip()
                        for part in parts
                        if isinstance(part, Mapping) and part.get("text")
                    )
            elif (
                task_id in self._sandbox_final_answers and item.get("partial") is False
            ):
                # Complete exact mirrors may be omitted. Deltas and extended
                # explanations stay intact: a matching prefix is not a duplicate.
                answers = self._sandbox_final_answers[task_id]
                retained = [
                    part
                    for part in parts
                    if not (
                        isinstance(part, Mapping)
                        and part.get("thought") is not True
                        and isinstance(part.get("text"), str)
                        and str(part["text"]).strip() in answers
                    )
                ]
                if len(retained) != len(parts):
                    item = {**item, "content": {**item["content"], "parts": retained}}
                    if (
                        not retained
                        and not item.get("usageMetadata")
                        and not item.get("actions")
                    ):
                        continue
            event_id = str(item.get("id") or uuid4())
            occurrence = self._projected_event_id_counts.get(event_id, 0)
            self._projected_event_id_counts[event_id] = occurrence + 1
            if occurrence:
                item = {**item, "id": f"{event_id}-{occurrence}"}
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
            item_usage = item.get("usageMetadata")
            if (
                isinstance(item_usage, Mapping)
                and isinstance(item_metadata, Mapping)
                and item_metadata.get("source") == "sandbox"
            ):
                source_key = "sandbox:" + str(
                    item_metadata.get("requestId")
                    or item.get("invocationId")
                    or item.get("modelVersion")
                    or "unknown"
                )
                normalized = _normalize_usage(item_usage)
                previous = self._usage_snapshots.get(source_key, {})
                delta = {
                    key: max(0, value - previous.get(key, 0))
                    for key, value in normalized.items()
                }
                self._usage_snapshots[source_key] = normalized
                if not any(delta.values()):
                    continue
                item = {**item, "usageMetadata": delta}
            if self._mpa_a2a:
                item = self._normalize_mpa_reasoning(item, task_id, cumulative_snapshot)
                if item is None:
                    continue
                if any(
                    p.get("thought") is True
                    for p in item.get("content", {}).get("parts", [])
                ):
                    output.append(item)
                    continue
            if item.get("partial") is not True:
                parts = item.get("content", {}).get("parts", [])
                if any(
                    isinstance(part, Mapping)
                    and part.get("thought") is not True
                    and str(part.get("text") or "")
                    for part in parts
                ):
                    self._partial_text["answer"] = ""
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
            stream = "thought" if parts[0].get("thought") is True else "answer"
            if stream == "thought":
                item_metadata = item.get("customMetadata")
                item_metadata = (
                    dict(item_metadata) if isinstance(item_metadata, Mapping) else {}
                )
                item_metadata.setdefault("thoughtKind", "reasoning")
                item = {**item, "customMetadata": item_metadata}
                projection_source = str(
                    item_metadata.get("projectionSource") or "unknown"
                )
                source_key = (task_id, projection_source)
                source_text = self._reasoning_text_by_source.get(source_key, "")
                other_texts = [
                    value
                    for (
                        seen_task,
                        seen_source,
                    ), value in self._reasoning_text_by_source.items()
                    if seen_task == task_id and seen_source != projection_source
                ]
                if (source_text and source_text.endswith(text)) or any(
                    other == text or other.startswith(text) for other in other_texts
                ):
                    self._reasoning_text_by_source[source_key] = text
                    continue
                cross_prefix = max(
                    (other for other in other_texts if text.startswith(other)),
                    key=len,
                    default="",
                )
                cumulative = projection_source == "a2a-status" or cumulative_snapshot
                prefix = (
                    source_text
                    if cumulative and text.startswith(source_text)
                    else cross_prefix
                )
                self._reasoning_text_by_source[source_key] = (
                    text if cumulative or cross_prefix else source_text + text
                )
                if prefix:
                    suffix = text[len(prefix) :]
                    if not suffix:
                        continue
                    text = suffix
                    item = {
                        **item,
                        "content": {
                            **item["content"],
                            "parts": [{**parts[0], "text": suffix}],
                        },
                    }
            previous_text = self._partial_text[stream]
            if cumulative_snapshot and text == previous_text:
                continue
            if cumulative_snapshot and previous_text and text.startswith(previous_text):
                suffix = text[len(previous_text) :]
                self._partial_text[stream] = text
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
                self._partial_text[stream] += text
            output.append(item)
        return output

    def _normalize_mpa_reasoning(
        self, item: dict[str, Any], task_id: str, cumulative: bool
    ) -> dict[str, Any] | None:
        metadata = item.get("customMetadata", {})
        sandbox = metadata.get("source") == "sandbox"
        key = (
            task_id,
            "sandbox" if sandbox else "outer",
            str(item.get("invocationId") or ""),
        )
        state = self._mpa_reasoning.setdefault(key, _ReasoningSegment())
        if sandbox and metadata.get("eventType") in {
            "tool.result",
            "tool.error",
            "message.delta",
            "invocation.completed",
        }:
            if state.text:
                state.text = ""
                state.deltas = 0
                state.index += 1
        parts = item.get("content", {}).get("parts", [])
        if len(parts) != 1 or parts[0].get("thought") is not True:
            return item
        text = str(parts[0].get("text") or "")
        snapshot = (
            cumulative
            or metadata.get("reasoningSnapshot") is True
            or (
                item.get("partial") is False
                and metadata.get("reasoningSnapshot") is not False
            )
            or (
                sandbox
                and state.deltas > 1
                and bool(state.text)
                and text.startswith(state.text)
            )
        )
        if snapshot and state.text and text.startswith(state.text):
            suffix = text[len(state.text) :]
            state.text = text
            text = suffix
        elif snapshot:
            if state.text:
                state.index += 1
            state.text = text
            state.deltas = 0
        else:
            state.text += text
            state.deltas += 1
        if not text:
            return None
        return {
            **item,
            # Snapshot prefixes have already been emitted as deltas.
            "partial": True,
            "content": {**item["content"], "parts": [{**parts[0], "text": text}]},
            "customMetadata": {
                **metadata,
                "reasoningSegmentId": json.dumps([*key, state.index]),
            },
        }

    def _usage_event(
        self,
        usage: Any,
        *,
        author: str,
        event_id: str,
        source_key: str,
        invocation_id: str = "",
        model: str = "",
    ) -> dict[str, Any] | None:
        normalized = _normalize_usage(usage)
        if not normalized:
            return None
        previous = self._usage_snapshots.get(source_key, {})
        delta = {
            key: max(0, value - previous.get(key, 0))
            for key, value in normalized.items()
        }
        self._usage_snapshots[source_key] = normalized
        if not any(delta.values()):
            return None
        return {
            "id": event_id,
            "author": author,
            "invocationId": invocation_id,
            "partial": True,
            "content": {"role": "model", "parts": []},
            "modelVersion": model,
            "usageMetadata": delta,
        }

    def finalize_projection(self, *, author: str) -> list[dict[str, Any]]:
        """Finalize streamed answer deltas when A2A ends without final text."""
        answer = self._partial_text["answer"]
        if not answer or self._terminal_state != "completed":
            return []
        self._partial_text["answer"] = ""
        return [
            _text_event(
                answer,
                author=author,
                event_id="a2a-final-answer",
                partial=False,
                turn_complete=True,
            )
        ]


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
    # MPA frames can bundle new events with replayed parts, and one source ID
    # can produce both usage and completion. Deduplicate these per event in
    # project(), rather than dropping the whole frame using its first part.
    if any(
        isinstance(part, Mapping)
        and isinstance(part.get("metadata"), Mapping)
        and part["metadata"].get("schemaVersion") == "mpa.sandbox-event.v1"
        for part in artifact.get("parts") or []
    ):
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


def _coalesce_mpa_thought_parts(event: Any) -> Any:
    """Normalize adjacent thought parts before splitting a message into events."""
    if not isinstance(event, Mapping):
        return event

    def coalesce(container: Any, *, snapshot: bool | None) -> Any:
        if not isinstance(container, Mapping):
            return container
        parts: list[Any] = []
        for part in container.get("parts") or []:
            metadata = part.get("metadata") if isinstance(part, Mapping) else None
            previous_metadata = (
                parts[-1].get("metadata")
                if parts and isinstance(parts[-1], Mapping)
                else None
            )
            if isinstance(metadata, Mapping) and metadata.get("adk_thought") is True:
                if snapshot is not None:
                    part = {
                        **part,
                        "metadata": {**metadata, "reasoningSnapshot": snapshot},
                    }
                if (
                    isinstance(previous_metadata, Mapping)
                    and previous_metadata.get("adk_thought") is True
                ):
                    previous = parts[-1]
                    parts[-1] = {
                        **previous,
                        "text": str(previous.get("text") or "")
                        + str(part.get("text") or ""),
                        "metadata": {
                            **previous_metadata,
                            "reasoningSnapshot": snapshot
                            if snapshot is not None
                            else True,
                        },
                    }
                    continue
            parts.append(part)
        return {**container, "parts": parts}

    kind = event.get("kind")
    if kind == "status-update":
        status = event.get("status")
        if not isinstance(status, Mapping):
            return event
        return {
            **event,
            "status": {
                **status,
                "message": coalesce(status.get("message"), snapshot=None),
            },
        }
    if kind == "artifact-update":
        return {
            **event,
            "artifact": coalesce(
                event.get("artifact"), snapshot=event.get("append") is not True
            ),
        }
    if kind == "task":
        return {
            **event,
            "artifacts": [
                coalesce(artifact, snapshot=True)
                for artifact in event.get("artifacts") or []
            ],
        }
    return event


def _message_to_partial_events(
    message: Mapping[str, Any], *, author: str
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    message_id = str(message.get("messageId") or uuid4())
    for index, part in enumerate(message.get("parts") or []):
        if not isinstance(part, Mapping):
            continue
        metadata = part.get("metadata")
        thought = isinstance(metadata, Mapping) and metadata.get("adk_thought") is True
        text = str(part.get("text") or "")[:_MAX_EVENT_TEXT_CHARS]
        if not text:
            continue
        events.append(
            _text_event(
                text,
                author=author,
                event_id=f"{message_id}-{index}",
                partial=True,
                thought=thought,
                custom_metadata={
                    "thoughtKind": "reasoning",
                    "projectionSource": "a2a-status",
                    **(
                        {"reasoningSnapshot": True}
                        if isinstance(metadata, Mapping)
                        and metadata.get("reasoningSnapshot") is True
                        else {}
                    ),
                }
                if thought
                else None,
            )
        )
    return events


def _artifact_to_studio_events(
    artifact: Any, *, author: str, turn_complete: bool
) -> list[dict[str, Any]]:
    if not isinstance(artifact, Mapping):
        return []
    events: list[dict[str, Any]] = []
    artifact_id = str(artifact.get("artifactId") or uuid4())
    for index, part in enumerate(artifact.get("parts") or []):
        if not isinstance(part, Mapping):
            continue
        metadata = part.get("metadata")
        thought = isinstance(metadata, Mapping) and metadata.get("adk_thought") is True
        normalized_thought = (
            thought
            and isinstance(metadata, Mapping)
            and "reasoningSnapshot" in metadata
        )
        raw_text = str(part.get("text") or "")
        text = raw_text if normalized_thought else raw_text.strip()
        if text:
            events.append(
                _text_event(
                    text,
                    author=author,
                    event_id=f"{artifact_id}-{index}",
                    partial=not turn_complete,
                    turn_complete=turn_complete,
                    thought=thought,
                    custom_metadata={
                        "thoughtKind": "reasoning",
                        "projectionSource": "a2a-artifact",
                        **(
                            {"reasoningSnapshot": metadata["reasoningSnapshot"]}
                            if normalized_thought and isinstance(metadata, Mapping)
                            else {}
                        ),
                    }
                    if thought
                    else None,
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
                    event_id=f"{artifact_id}-{index}",
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
            **(
                {"requestId": str(payload["requestId"])}
                if payload.get("requestId")
                else {}
            ),
        },
    }
    if event_type == "invocation.completed":
        text = str(
            payload.get("finalMessage")
            or payload.get("text")
            or payload.get("message")
            or ""
        )
        if not text.strip():
            return None
        return _text_event(
            text,
            author=author,
            event_id=event_id,
            invocation_id=invocation_id,
            partial=False,
            turn_complete=True,
            custom_metadata=common["customMetadata"],
        )
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
    if event_type == "usage.updated":
        usage = {
            target: int(value)
            for source, target in (
                ("inputTokens", "promptTokenCount"),
                ("outputTokens", "candidatesTokenCount"),
                ("totalTokens", "totalTokenCount"),
                ("cachedTokens", "cachedContentTokenCount"),
                ("reasoningTokens", "thoughtsTokenCount"),
            )
            if isinstance((value := payload.get(source)), int) and value >= 0
        }
        if not usage:
            return None
        return {
            **common,
            "partial": True,
            "content": {"role": "model", "parts": []},
            "modelVersion": str(payload.get("modelId") or ""),
            "usageMetadata": usage,
        }
    if event_type == "thought.delta":
        text = str(payload.get("text") or "")[:_MAX_EVENT_TEXT_CHARS]
        return (
            _text_event(
                text,
                author=author,
                event_id=event_id,
                invocation_id=invocation_id,
                partial=True,
                thought=True,
                custom_metadata=common["customMetadata"],
            )
            if text
            else None
        )
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


def _normalize_usage(usage: Any) -> dict[str, int]:
    if not isinstance(usage, Mapping):
        return {}
    aliases = (
        ("promptTokenCount", "inputTokens"),
        ("candidatesTokenCount", "outputTokens"),
        ("totalTokenCount", "totalTokens"),
        ("cachedContentTokenCount", "cachedTokens"),
        ("thoughtsTokenCount", "reasoningTokens"),
    )
    normalized: dict[str, int] = {}
    for target, source in aliases:
        value = usage.get(target, usage.get(source))
        if isinstance(value, int) and value >= 0:
            normalized[target] = value
    return normalized


def _text_event(
    text: str,
    *,
    author: str,
    event_id: str,
    invocation_id: str = "",
    partial: bool,
    thought: bool = False,
    turn_complete: bool = False,
    custom_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": event_id,
        "author": author,
        "partial": partial,
        "content": {
            "role": "model",
            "parts": [{"text": text, **({"thought": True} if thought else {})}],
        },
    }
    if invocation_id:
        event["invocationId"] = invocation_id
    if turn_complete:
        event["turnComplete"] = True
    if custom_metadata:
        event["customMetadata"] = dict(custom_metadata)
    return event
