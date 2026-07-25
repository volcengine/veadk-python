# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Translate an ADK Session into an AgentKit evaluation feedback sample."""

from __future__ import annotations

import hashlib

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeedbackSample:
    """Server-derived content associated with one assistant Event."""

    input: str
    output: str
    agent_name: str
    session_id: str
    message_id: str
    runtime_id: str
    invocation_id: str
    user_id: str
    created_at: str

    def fields(self, *, rating: str, comment: str = "") -> dict[str, str]:
        """Return field values matching the Studio feedback-set schema."""
        if rating not in {"good", "bad"}:
            raise ValueError(f"unsupported feedback rating: {rating}")
        return {
            "input": self.input,
            "reference_output": self.output if rating == "good" else "",
            "output": self.output,
            "feedback_comment": comment,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "runtime_id": self.runtime_id,
            "invocation_id": self.invocation_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
        }


def feedback_state_key(message_id: str) -> str:
    """Return the Session-state key containing the latest feedback snapshot."""
    return f"veadk_feedback:{message_id}"


def feedback_item_key(
    *,
    project_name: str,
    runtime_id: str,
    session_id: str,
    message_id: str,
) -> str:
    """Return the deterministic AgentKit evaluation item key."""
    source = "\x00".join((project_name, runtime_id, session_id, message_id))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def extract_feedback_sample(
    session: dict[str, Any],
    *,
    target_event_id: str,
    runtime_id: str,
    agent_name: str,
    user_id: str,
) -> FeedbackSample:
    """Extract the user input and visible answer ending at ``target_event_id``."""
    events = session.get("events")
    if not isinstance(events, list):
        raise ValueError("Session does not contain events")
    target_index = next(
        (
            index
            for index, event in enumerate(events)
            if isinstance(event, dict) and str(event.get("id") or "") == target_event_id
        ),
        -1,
    )
    if target_index < 0:
        raise ValueError("The assistant Event does not exist in this Session")
    target = events[target_index]
    if str(target.get("author") or "") == "user":
        raise ValueError("Feedback can only target an assistant Event")

    user_index = -1
    user_text = ""
    for index in range(target_index - 1, -1, -1):
        event = events[index]
        if not isinstance(event, dict) or str(event.get("author") or "") != "user":
            continue
        text = _visible_event_text(event)
        if text:
            user_index = index
            user_text = text
            break
    if user_index < 0:
        raise ValueError("No user message precedes the assistant Event")

    output = "".join(
        _visible_event_text(event)
        for event in events[user_index + 1 : target_index + 1]
        if isinstance(event, dict) and str(event.get("author") or "") != "user"
    ).strip()
    if not output:
        raise ValueError("The assistant Event has no visible answer")

    invocation_id = str(target.get("invocationId") or target.get("invocation_id") or "")
    created_at = str(target.get("timestamp") or "")
    session_id = str(session.get("id") or "")
    if not session_id:
        raise ValueError("Session does not contain an ID")
    return FeedbackSample(
        input=user_text,
        output=output,
        agent_name=agent_name,
        session_id=session_id,
        message_id=target_event_id,
        runtime_id=runtime_id,
        invocation_id=invocation_id,
        user_id=user_id,
        created_at=created_at,
    )


def _visible_event_text(event: dict[str, Any]) -> str:
    content = event.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    text_parts: list[str] = []
    for part in parts:
        if not isinstance(part, dict) or part.get("thought") is True:
            continue
        metadata = part.get("partMetadata") or part.get("part_metadata") or {}
        transport = metadata.get("veadkTransport") if isinstance(metadata, dict) else {}
        if isinstance(transport, dict) and transport.get("hideText") is True:
            continue
        text = part.get("text")
        if isinstance(text, str):
            text_parts.append(text)
    return "".join(text_parts).strip()
