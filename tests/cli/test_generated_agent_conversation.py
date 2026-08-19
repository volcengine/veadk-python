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

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
from pydantic import ValidationError

import veadk.cli.generated_agent_conversation as conversation_module
from veadk.cli.generated_agent_conversation import (
    AGENT_BUILDER_INSTRUCTION,
    ConversationBusyError,
    ConversationNotFoundError,
    GeneratedAgentConversationRunRequest,
    GeneratedAgentConversationService,
)


class _FakeEvent:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump_json(self, **_: Any) -> str:
        return json.dumps(self.payload)


class _FakeSessionService:
    def __init__(self) -> None:
        self.sessions: set[tuple[str, str, str]] = set()

    async def get_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> object | None:
        key = (app_name, user_id, session_id)
        return object() if key in self.sessions else None

    async def create_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> object:
        self.sessions.add((app_name, user_id, session_id))
        return object()


class _FakeRunner:
    app_name = "test_agent_builder"

    def __init__(
        self,
        tool: Callable[[str], Awaitable[dict[str, Any]]],
        *,
        invoke_tool: bool,
    ) -> None:
        self.tool = tool
        self.invoke_tool = invoke_tool
        self.session_service = _FakeSessionService()

    async def run_async(self, **_: Any) -> AsyncIterator[_FakeEvent]:
        yield _FakeEvent({"author": "studio_agent_builder", "text": "clarify"})
        if self.invoke_tool:
            result = await self.tool("完整的场景、输入、输出和约束")
            yield _FakeEvent(
                {
                    "author": "studio_agent_builder",
                    "functionResponse": {
                        "name": "generate_agent",
                        "response": result,
                    },
                }
            )


def _draft_result() -> dict[str, Any]:
    return {
        "draft": {"name": "support_agent", "agentType": "llm"},
        "summary": "客服 Agent",
        "unresolvedItems": ["知识库 ID"],
    }


def test_run_request_rejects_empty_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        GeneratedAgentConversationRunRequest(message="")
    with pytest.raises(ValidationError):
        GeneratedAgentConversationRunRequest(message="   ")
    with pytest.raises(ValidationError):
        GeneratedAgentConversationRunRequest.model_validate(
            {"message": "hello", "extra": True}
        )

    request = GeneratedAgentConversationRunRequest(message="  hello  ")
    assert request.message == "hello"


def test_builder_instruction_gates_generation_until_requirements_are_complete() -> None:
    assert "必须先确认已有足够信息" in AGENT_BUILDER_INSTRUCTION
    assert "不要因为用户只描述了一个模糊方向就生成配置" in AGENT_BUILDER_INSTRUCTION
    assert "普通追问、解释、确认和致谢不能再次调用工具" in AGENT_BUILDER_INSTRUCTION
    assert "自包含的完整 requirement" in AGENT_BUILDER_INSTRUCTION


def test_builder_uses_chat_completions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_options: dict[str, Any] = {}

    class _CapturedAgent:
        def __init__(self, **kwargs: Any) -> None:
            agent_options.update(kwargs)

    class _CapturedRunner:
        def __init__(self, **_: Any) -> None:
            pass

    async def generate_agent(_: str) -> dict[str, Any]:
        return _draft_result()

    monkeypatch.setattr(conversation_module, "Agent", _CapturedAgent)
    monkeypatch.setattr(conversation_module, "Runner", _CapturedRunner)

    GeneratedAgentConversationService._build_runner(generate_agent)

    assert agent_options["enable_responses"] is False
    assert agent_options["enable_responses_cache"] is False


@pytest.mark.asyncio
async def test_clarifying_turn_does_not_generate_a_draft() -> None:
    planner_calls: list[str] = []

    async def planner(requirement: str) -> dict[str, Any]:
        planner_calls.append(requirement)
        return _draft_result()

    service = GeneratedAgentConversationService(
        draft_generator=planner,
        runner_factory=lambda tool: _FakeRunner(tool, invoke_tool=False),
    )
    created = service.create("owner-a")
    conversation = service.reserve(str(created["conversationId"]), "owner-a")

    events = [event async for event in service.stream_turn(conversation, "做个助手")]
    service.release(conversation)

    assert planner_calls == []
    assert [json.loads(event).get("type") for event in events] == [None, "done"]


@pytest.mark.asyncio
async def test_tool_success_emits_draft_only_after_the_function_response() -> None:
    planner_calls: list[str] = []

    async def planner(requirement: str) -> dict[str, Any]:
        planner_calls.append(requirement)
        return _draft_result()

    service = GeneratedAgentConversationService(
        draft_generator=planner,
        runner_factory=lambda tool: _FakeRunner(tool, invoke_tool=True),
    )
    created = service.create("owner-a")
    conversation = service.reserve(str(created["conversationId"]), "owner-a")

    events = [
        json.loads(event)
        async for event in service.stream_turn(
            conversation,
            "输入输出和约束都已经补充完整，请生成",
        )
    ]
    service.release(conversation)

    assert planner_calls == ["完整的场景、输入、输出和约束"]
    assert events[1]["functionResponse"]["name"] == "generate_agent"
    assert events[2] == {"type": "agent_draft", **_draft_result()}
    assert events[-1] == {"type": "done"}


def test_conversations_are_owner_scoped_and_reject_overlapping_turns() -> None:
    service = GeneratedAgentConversationService(
        runner_factory=lambda tool: _FakeRunner(tool, invoke_tool=False)
    )
    created = service.create("owner-a")
    conversation_id = str(created["conversationId"])

    conversation = service.reserve(conversation_id, "owner-a")
    with pytest.raises(ConversationBusyError):
        service.reserve(conversation_id, "owner-a")
    with pytest.raises(ConversationNotFoundError):
        service.reserve(conversation_id, "owner-b")

    service.release(conversation)
    assert service.reserve(conversation_id, "owner-a") is conversation


def test_expired_conversation_is_removed() -> None:
    now = [100.0]
    service = GeneratedAgentConversationService(
        runner_factory=lambda tool: _FakeRunner(tool, invoke_tool=False),
        ttl_seconds=60,
        clock=lambda: now[0],
    )
    created = service.create("owner-a")
    now[0] = 161.0

    with pytest.raises(ConversationNotFoundError):
        service.reserve(str(created["conversationId"]), "owner-a")
