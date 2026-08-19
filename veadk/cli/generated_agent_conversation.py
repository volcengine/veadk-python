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

"""Multi-turn Studio conversation for creating a validated Agent draft."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from google.adk.agents import RunConfig
from google.adk.agents.run_config import StreamingMode
from google.adk.utils.context_utils import Aclosing
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, field_validator

from veadk import Agent, Runner
from veadk.cli.generated_agent_planner import (
    PLANNER_MODEL_NAME,
    GeneratedAgentDraftRequest,
    generate_agent_draft,
)

CONVERSATION_APP_NAME = "studio_agent_builder"
DEFAULT_CONVERSATION_TTL_SECONDS = 30 * 60
DEFAULT_MAX_CONVERSATIONS_PER_OWNER = 20

AGENT_BUILDER_INSTRUCTION = """
你是 VeADK Studio 的智能体配置助手。你的职责是通过自然、多轮的中文对话，
帮助用户把真实需求整理成可以生成 Agent 的完整需求。

在调用 generate_agent 前，必须先确认已有足够信息，包括：
- 使用场景和最终目标；
- 主要输入及期望输出；
- 必要的流程、约束和成功标准；
- 确实需要的工具、外部资源或子 Agent 协作方式。

如果关键信息不足，先用简短、聚焦的问题澄清，一次优先询问最重要的缺口。
不要因为用户只描述了一个模糊方向就生成配置。只有在信息已经足够，或用户明确要求
基于现有信息直接生成时，才调用 generate_agent。你必须把当前对话中已经确认的信息
整理成一份自包含的完整 requirement 传给工具，不能只传用户最近一句话。

generate_agent 成功后，简要说明已经生成或更新的内容以及仍待用户补充的真实资源。
普通追问、解释、确认和致谢不能再次调用工具。只有用户明确提出修改、重建或新增配置，
并且修改所需信息已充分时，才能再次调用 generate_agent。不要向用户索取或复述密钥、
访问令牌等敏感信息；只提示他们稍后在安全的配置控件中填写。
""".strip()


class GeneratedAgentConversationRunRequest(BaseModel):
    """A single user turn in an Agent-builder conversation."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=8000)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("message must not be blank")
        return message


class ConversationNotFoundError(LookupError):
    """Raised when a conversation is absent, expired, or owned by another user."""


class ConversationBusyError(RuntimeError):
    """Raised when a second turn starts while a conversation is already running."""


DraftGenerator = Callable[[str], Awaitable[dict[str, Any]]]
RunnerFactory = Callable[[Callable[[str], Awaitable[dict[str, Any]]]], Any]


@dataclass
class _Conversation:
    conversation_id: str
    owner_id: str
    runner: Any
    expires_at: float
    draft_events: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    running: bool = False


class GeneratedAgentConversationService:
    """Own isolated, expiring Agent-builder conversations.

    The HTTP layer only validates and streams requests. This service owns session
    isolation, the model tool, and the rule that a draft event is emitted only
    after the strict planner succeeds.
    """

    def __init__(
        self,
        *,
        draft_generator: DraftGenerator = generate_agent_draft,
        runner_factory: RunnerFactory | None = None,
        ttl_seconds: int = DEFAULT_CONVERSATION_TTL_SECONDS,
        max_conversations_per_owner: int = DEFAULT_MAX_CONVERSATIONS_PER_OWNER,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._draft_generator = draft_generator
        self._runner_factory = runner_factory or self._build_runner
        self._ttl_seconds = max(60, ttl_seconds)
        self._max_conversations_per_owner = max(1, max_conversations_per_owner)
        self._clock = clock
        self._conversations: dict[str, _Conversation] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _build_runner(
        generate_agent: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> Runner:
        agent = Agent(
            name="studio_agent_builder",
            description="Clarifies a user's scenario before creating an Agent draft.",
            instruction=AGENT_BUILDER_INSTRUCTION,
            model_name=PLANNER_MODEL_NAME,
            tools=[generate_agent],
            # The conversation needs incremental text and function-call events.
            # Ark's Responses streaming SDK is not compatible with Python 3.14;
            # the supported Chat Completions path provides both without changing
            # the strict Responses-based draft planner used by generate_agent.
            enable_responses=False,
            enable_responses_cache=False,
            model_extra_config={"extra_body": {"thinking": {"type": "disabled"}}},
        )
        return Runner(agent=agent, app_name=CONVERSATION_APP_NAME)

    def create(self, owner_id: str) -> dict[str, str | float]:
        """Create a conversation and return its public identifier and expiry."""

        now = self._clock()
        with self._lock:
            self._cleanup_expired_locked(now)
            owner_conversations = sorted(
                (
                    item
                    for item in self._conversations.values()
                    if item.owner_id == owner_id and not item.running
                ),
                key=lambda item: item.expires_at,
            )
            while (
                self._owner_count_locked(owner_id) >= self._max_conversations_per_owner
                and owner_conversations
            ):
                oldest = owner_conversations.pop(0)
                self._conversations.pop(oldest.conversation_id, None)

            conversation_id = f"agent-builder-{uuid4().hex}"
            draft_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            async def generate_agent(requirement: str) -> dict[str, Any]:
                """Generate or update the Agent configuration when requirements are complete.

                Use this only after the conversation has established the scenario,
                goal, inputs, outputs, constraints, and required capabilities. Pass a
                self-contained requirement that includes all decisions from the full
                conversation, not only the latest user message.

                Args:
                    requirement: Complete, consolidated Agent requirements.

                Returns:
                    The validated Agent draft, summary, and unresolved resource items.
                """

                payload = GeneratedAgentDraftRequest.model_validate(
                    {"requirement": requirement.strip()}
                )
                result = await self._draft_generator(payload.requirement)
                event = {
                    "type": "agent_draft",
                    "draft": result["draft"],
                    "summary": str(result.get("summary", "")),
                    "unresolvedItems": list(result.get("unresolvedItems", [])),
                }
                draft_events.put_nowait(event)
                return result

            conversation = _Conversation(
                conversation_id=conversation_id,
                owner_id=owner_id,
                runner=self._runner_factory(generate_agent),
                expires_at=now + self._ttl_seconds,
                draft_events=draft_events,
            )
            self._conversations[conversation_id] = conversation
            return {
                "conversationId": conversation_id,
                "expiresAt": conversation.expires_at,
            }

    def reserve(self, conversation_id: str, owner_id: str) -> _Conversation:
        """Reserve a conversation for one turn without waiting behind another run."""

        now = self._clock()
        with self._lock:
            self._cleanup_expired_locked(now)
            conversation = self._conversations.get(conversation_id)
            if conversation is None or conversation.owner_id != owner_id:
                raise ConversationNotFoundError(conversation_id)
            if conversation.running:
                raise ConversationBusyError(conversation_id)
            conversation.running = True
            conversation.expires_at = now + self._ttl_seconds
            self._discard_draft_events(conversation)
            return conversation

    def release(self, conversation: _Conversation) -> None:
        """Release a reserved conversation and refresh its expiry."""

        with self._lock:
            current = self._conversations.get(conversation.conversation_id)
            if current is conversation:
                conversation.running = False
                conversation.expires_at = self._clock() + self._ttl_seconds

    async def stream_turn(
        self,
        conversation: _Conversation,
        message: str,
    ) -> AsyncIterator[str]:
        """Yield serialized ADK events and the dedicated draft/done events."""

        await self._ensure_session(conversation)
        content = types.Content(role="user", parts=[types.Part(text=message)])
        async with Aclosing(
            conversation.runner.run_async(
                user_id=conversation.owner_id,
                session_id=conversation.conversation_id,
                new_message=content,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        ) as events:
            async for event in events:
                yield event.model_dump_json(exclude_none=True, by_alias=True)
                async for draft_event in self._drain_draft_events(conversation):
                    yield json.dumps(draft_event, ensure_ascii=False)

        async for draft_event in self._drain_draft_events(conversation):
            yield json.dumps(draft_event, ensure_ascii=False)
        yield json.dumps({"type": "done"})

    async def _ensure_session(self, conversation: _Conversation) -> None:
        runner = conversation.runner
        session = await runner.session_service.get_session(
            app_name=runner.app_name,
            user_id=conversation.owner_id,
            session_id=conversation.conversation_id,
        )
        if session is None:
            await runner.session_service.create_session(
                app_name=runner.app_name,
                user_id=conversation.owner_id,
                session_id=conversation.conversation_id,
            )

    @staticmethod
    async def _drain_draft_events(
        conversation: _Conversation,
    ) -> AsyncIterator[dict[str, Any]]:
        while True:
            try:
                yield conversation.draft_events.get_nowait()
            except asyncio.QueueEmpty:
                return

    @staticmethod
    def _discard_draft_events(conversation: _Conversation) -> None:
        while True:
            try:
                conversation.draft_events.get_nowait()
            except asyncio.QueueEmpty:
                return

    def _cleanup_expired_locked(self, now: float) -> None:
        expired = [
            conversation_id
            for conversation_id, conversation in self._conversations.items()
            if not conversation.running and conversation.expires_at <= now
        ]
        for conversation_id in expired:
            self._conversations.pop(conversation_id, None)

    def _owner_count_locked(self, owner_id: str) -> int:
        return sum(item.owner_id == owner_id for item in self._conversations.values())
