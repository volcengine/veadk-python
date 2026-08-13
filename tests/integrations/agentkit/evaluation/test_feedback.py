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

from __future__ import annotations

from veadk.integrations.agentkit.evaluation.feedback import (
    extract_feedback_sample,
    feedback_item_key,
    feedback_state_key,
)


def test_extract_feedback_sample_uses_visible_turn_content() -> None:
    session = {
        "id": "session-1",
        "events": [
            {
                "id": "user-1",
                "author": "user",
                "content": {"parts": [{"text": "敦煌有哪些著名石窟？"}]},
            },
            {
                "id": "tool-1",
                "author": "search_agent",
                "invocationId": "inv-1",
                "content": {"parts": [{"thought": True, "text": "先检索知识库"}]},
            },
            {
                "id": "assistant-1",
                "author": "search_agent",
                "invocationId": "inv-1",
                "content": {"parts": [{"text": "最著名的是莫高窟。"}]},
            },
            {
                "id": "assistant-2",
                "author": "root_agent",
                "invocationId": "inv-1",
                "content": {"parts": [{"text": "此外还有榆林窟。"}]},
            },
        ],
    }

    sample = extract_feedback_sample(
        session,
        target_event_id="assistant-2",
        runtime_id="runtime-1",
        agent_name="敦煌助手",
        user_id="user-1",
    )

    assert sample.input == "敦煌有哪些著名石窟？"
    assert sample.output == "最著名的是莫高窟。此外还有榆林窟。"
    assert sample.invocation_id == "inv-1"
    assert sample.session_id == "session-1"
    assert sample.message_id == "assistant-2"


def test_extract_feedback_sample_stops_at_annotated_assistant_turn() -> None:
    events: list[dict[str, object]] = []
    for index in range(1, 5):
        events.extend(
            [
                {
                    "id": f"user-{index}",
                    "author": "user",
                    "content": {"parts": [{"text": f"问题 {index}"}]},
                },
                {
                    "id": f"assistant-{index}",
                    "author": "agent",
                    "invocationId": f"invocation-{index}",
                    "content": {"parts": [{"text": f"回答 {index}"}]},
                },
            ]
        )

    sample = extract_feedback_sample(
        {"id": "session-1", "events": events},
        target_event_id="assistant-3",
        runtime_id="runtime-1",
        agent_name="测试助手",
        user_id="user-1",
    )

    assert sample.input == "问题 3"
    assert sample.output == "回答 3"
    assert sample.message_id == "assistant-3"
    assert "问题 4" not in sample.input
    assert "回答 4" not in sample.output


def test_feedback_identifiers_are_stable() -> None:
    assert feedback_state_key("event-1") == "veadk_feedback:event-1"
    assert feedback_item_key(
        project_name="default",
        runtime_id="runtime-1",
        session_id="session-1",
        message_id="event-1",
    ) == feedback_item_key(
        project_name="default",
        runtime_id="runtime-1",
        session_id="session-1",
        message_id="event-1",
    )
