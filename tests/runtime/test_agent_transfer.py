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

from __future__ import annotations

import pytest
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.genai import types

from veadk.runtime.agent_transfer import append_transfer_instructions
from veadk.runtime.agent_transfer import get_transfer_targets
from veadk.runtime.agent_transfer import run_transferred_agent


class _TextAgent(BaseAgent):
    marker: str
    output_key: str = ""
    output_schema: object | None = None

    async def _run_async_impl(self, ctx: InvocationContext):
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=types.ModelContent(parts=[types.Part(text=self.marker)]),
        )


def _ctx(agent: BaseAgent) -> InvocationContext:
    return InvocationContext(
        session_service=InMemorySessionService(),
        invocation_id="inv-transfer",
        agent=agent,
        session=Session(
            id="session-transfer",
            appName="app",
            userId="user",
            state={},
            events=[],
        ),
    )


def _names(agents: list[BaseAgent]) -> list[str]:
    return [agent.name for agent in agents]


def test_get_transfer_targets_matches_adk_tree_rules() -> None:
    planner = LlmAgent(name="planner", model="gemini-2.5-flash")
    writer = LlmAgent(name="writer", model="gemini-2.5-flash")
    task = LlmAgent(name="task", model="gemini-2.5-flash", mode="task")
    root = LlmAgent(
        name="root",
        model="gemini-2.5-flash",
        sub_agents=[planner, writer, task],
    )

    assert _names(get_transfer_targets(root)) == ["planner", "writer"]
    assert _names(get_transfer_targets(planner)) == ["root", "writer"]

    planner.disallow_transfer_to_parent = True
    planner.disallow_transfer_to_peers = True

    assert get_transfer_targets(planner) == []


def test_append_transfer_instructions_lists_available_agents() -> None:
    worker = LlmAgent(
        name="worker",
        model="gemini-2.5-flash",
        description="Handles implementation work.",
    )
    root = LlmAgent(
        name="root",
        model="gemini-2.5-flash",
        sub_agents=[worker],
    )
    llm_request = LlmRequest(model="gemini-2.5-flash")

    append_transfer_instructions(root, llm_request)

    instruction = str(llm_request.config.system_instruction)
    assert "transfer_to_agent" in instruction
    assert "`worker`" in instruction
    assert "Handles implementation work." in instruction


@pytest.mark.asyncio
async def test_run_transferred_agent_executes_target_and_saves_output_key() -> None:
    worker = _TextAgent(name="worker", marker="done", output_key="worker_answer")
    root = LlmAgent(
        name="root",
        model="gemini-2.5-flash",
        sub_agents=[worker],
    )
    ctx = _ctx(root)
    transfer_event = Event(
        invocation_id=ctx.invocation_id,
        author=root.name,
        actions=EventActions(transfer_to_agent="worker"),
    )

    events = [event async for event in run_transferred_agent(ctx, transfer_event)]

    assert [event.author for event in events] == ["worker"]
    assert events[0].actions.state_delta == {"worker_answer": "done"}
