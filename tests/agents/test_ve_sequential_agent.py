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

"""Testings for the Veadk SequentialAgent."""

from typing import AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.sequential_agent import SequentialAgentState
from google.adk.apps import ResumabilityConfig
from google.adk.events.event import Event
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
import pytest
from typing_extensions import override

from veadk.agents.sequential_agent import SequentialAgent


class _TestingAgent(BaseAgent):
    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(
                parts=[types.Part(text=f"Hello, async {self.name}!")]
            ),
        )

    @override
    async def _run_live_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(parts=[types.Part(text=f"Hello, live {self.name}!")]),
        )


async def _create_parent_invocation_context(
    test_name: str, agent: BaseAgent, resumable: bool = False
) -> InvocationContext:
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="test_app", user_id="test_user"
    )
    return InvocationContext(
        invocation_id=f"{test_name}_invocation_id",
        agent=agent,
        session=session,
        session_service=session_service,
        resumability_config=ResumabilityConfig(is_resumable=resumable),
    )


@pytest.mark.asyncio
async def test_run_async(request: pytest.FixtureRequest):
    agent_1 = _TestingAgent(name=f"{request.function.__name__}_test_agent_1")
    agent_2 = _TestingAgent(name=f"{request.function.__name__}_test_agent_2")
    sequential_agent = SequentialAgent(
        name=f"{request.function.__name__}_test_agent",
        sub_agents=[
            agent_1,
            agent_2,
        ],
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, sequential_agent
    )
    events = [e async for e in sequential_agent.run_async(parent_ctx)]

    assert len(events) == 2
    assert events[0].author == agent_1.name
    assert events[1].author == agent_2.name
    assert events[0].content.parts[0].text == f"Hello, async {agent_1.name}!"
    assert events[1].content.parts[0].text == f"Hello, async {agent_2.name}!"


@pytest.mark.asyncio
async def test_run_async_skip_if_no_sub_agent(request: pytest.FixtureRequest):
    sequential_agent = SequentialAgent(
        name=f"{request.function.__name__}_test_agent",
        sub_agents=[],
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, sequential_agent
    )
    events = [e async for e in sequential_agent.run_async(parent_ctx)]

    assert not events


@pytest.mark.asyncio
async def test_run_async_with_resumability(request: pytest.FixtureRequest):
    agent_1 = _TestingAgent(name=f"{request.function.__name__}_test_agent_1")
    agent_2 = _TestingAgent(name=f"{request.function.__name__}_test_agent_2")
    sequential_agent = SequentialAgent(
        name=f"{request.function.__name__}_test_agent",
        sub_agents=[
            agent_1,
            agent_2,
        ],
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, sequential_agent, resumable=True
    )
    events = [e async for e in sequential_agent.run_async(parent_ctx)]

    # 5 events:
    # 1. SequentialAgent checkpoint event for agent 1
    # 2. Agent 1 event
    # 3. SequentialAgent checkpoint event for agent 2
    # 4. Agent 2 event
    # 5. SequentialAgent final checkpoint event
    assert len(events) == 5
    assert events[0].author == sequential_agent.name
    assert not events[0].actions.end_of_agent
    assert events[0].actions.agent_state["current_sub_agent"] == agent_1.name

    assert events[1].author == agent_1.name
    assert events[1].content.parts[0].text == f"Hello, async {agent_1.name}!"

    assert events[2].author == sequential_agent.name
    assert not events[2].actions.end_of_agent
    assert events[2].actions.agent_state["current_sub_agent"] == agent_2.name

    assert events[3].author == agent_2.name
    assert events[3].content.parts[0].text == f"Hello, async {agent_2.name}!"

    assert events[4].author == sequential_agent.name
    assert events[4].actions.end_of_agent


@pytest.mark.asyncio
async def test_resume_async(request: pytest.FixtureRequest):
    agent_1 = _TestingAgent(name=f"{request.function.__name__}_test_agent_1")
    agent_2 = _TestingAgent(name=f"{request.function.__name__}_test_agent_2")
    sequential_agent = SequentialAgent(
        name=f"{request.function.__name__}_test_agent",
        sub_agents=[
            agent_1,
            agent_2,
        ],
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, sequential_agent, resumable=True
    )
    parent_ctx.agent_states[sequential_agent.name] = SequentialAgentState(
        current_sub_agent=agent_2.name
    ).model_dump(mode="json")

    events = [e async for e in sequential_agent.run_async(parent_ctx)]

    # 2 events:
    # 1. Agent 2 event
    # 2. SequentialAgent final checkpoint event
    assert len(events) == 2
    assert events[0].author == agent_2.name
    assert events[0].content.parts[0].text == f"Hello, async {agent_2.name}!"

    assert events[1].author == sequential_agent.name
    assert events[1].actions.end_of_agent


@pytest.mark.asyncio
async def test_run_live(request: pytest.FixtureRequest):
    agent_1 = _TestingAgent(name=f"{request.function.__name__}_test_agent_1")
    agent_2 = _TestingAgent(name=f"{request.function.__name__}_test_agent_2")
    sequential_agent = SequentialAgent(
        name=f"{request.function.__name__}_test_agent",
        sub_agents=[
            agent_1,
            agent_2,
        ],
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, sequential_agent
    )
    events = [e async for e in sequential_agent.run_live(parent_ctx)]

    assert len(events) == 2
    assert events[0].author == agent_1.name
    assert events[1].author == agent_2.name
    assert events[0].content.parts[0].text == f"Hello, live {agent_1.name}!"
    assert events[1].content.parts[0].text == f"Hello, live {agent_2.name}!"


@pytest.mark.asyncio
async def test_veadk_sequential_agent_initialization():
    """Test that Veadk SequentialAgent initializes correctly with default values."""
    sequential_agent = SequentialAgent()

    # Check default values
    assert sequential_agent.name == "veSequentialAgent"
    assert sequential_agent.sub_agents == []
    assert sequential_agent.tracers == []
    assert hasattr(sequential_agent, "description")
    assert hasattr(sequential_agent, "instruction")


@pytest.mark.asyncio
async def test_veadk_sequential_agent_with_custom_values():
    """Test that Veadk SequentialAgent initializes correctly with custom values."""
    agent_1 = _TestingAgent(name="custom_agent_1")
    agent_2 = _TestingAgent(name="custom_agent_2")

    custom_name = "MyCustomSequentialAgent"
    custom_description = "This is a custom sequential agent"
    custom_instruction = "Follow these instructions carefully"

    sequential_agent = SequentialAgent(
        name=custom_name,
        description=custom_description,
        instruction=custom_instruction,
        sub_agents=[agent_1, agent_2],
    )

    # Check custom values
    assert sequential_agent.name == custom_name
    assert sequential_agent.description == custom_description
    assert sequential_agent.instruction == custom_instruction
    assert len(sequential_agent.sub_agents) == 2
    assert sequential_agent.sub_agents[0] == agent_1
    assert sequential_agent.sub_agents[1] == agent_2


@pytest.mark.asyncio
async def test_veadk_sequential_agent_inheritance():
    """Test that Veadk SequentialAgent has the correct class name and attributes."""
    sequential_agent = SequentialAgent()

    # Check class name and attributes
    assert sequential_agent.__class__.__name__ == "SequentialAgent"
    assert hasattr(sequential_agent, "name")
    assert hasattr(sequential_agent, "description")
    assert hasattr(sequential_agent, "instruction")
    assert hasattr(sequential_agent, "sub_agents")
    assert hasattr(sequential_agent, "tracers")
    assert hasattr(sequential_agent, "model_post_init")
