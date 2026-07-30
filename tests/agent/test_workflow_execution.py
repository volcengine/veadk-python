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

"""Execution-level tests for VeADK workflow agents.

The test agents are deterministic and do not call a model. This keeps the
tests fast while exercising the real Google ADK workflow implementations
through VeADK's wrappers.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.sessions import InMemorySessionService, Session

from veadk.agents.loop_agent import LoopAgent
from veadk.agents.parallel_agent import ParallelAgent
from veadk.agents.sequential_agent import SequentialAgent


class _ExecutionTracker:
    def __init__(self) -> None:
        self.calls: list[str] = []


class _StartBarrier:
    def __init__(self, expected: int) -> None:
        self.expected = expected
        self.started: set[str] = set()
        self.ready = asyncio.Event()

    async def arrive(self, agent_name: str) -> None:
        self.started.add(agent_name)
        if len(self.started) == self.expected:
            self.ready.set()
        await asyncio.wait_for(self.ready.wait(), timeout=0.5)


class _DeterministicAgent(BaseAgent):
    tracker: Any
    barrier: Any = None
    escalate_on_call: int | None = None
    call_count: int = 0

    async def _run_async_impl(self, ctx: InvocationContext):
        self.call_count += 1
        self.tracker.calls.append(self.name)

        if self.barrier is not None:
            await self.barrier.arrive(self.name)

        yield Event(
            author=self.name,
            actions=EventActions(
                escalate=self.call_count == self.escalate_on_call,
            ),
        )


def _invocation_context(agent: BaseAgent) -> InvocationContext:
    return InvocationContext(
        session_service=InMemorySessionService(),
        invocation_id="test-invocation",
        agent=agent,
        session=Session(
            id="test-session",
            appName="test-app",
            userId="test-user",
            state={},
            events=[],
        ),
    )


async def _run(agent: BaseAgent) -> list[Event]:
    return [event async for event in agent.run_async(_invocation_context(agent))]


@pytest.mark.asyncio
async def test_sequential_agent_executes_children_in_declared_order() -> None:
    tracker = _ExecutionTracker()
    workflow = SequentialAgent(
        sub_agents=[
            _DeterministicAgent(name="first", tracker=tracker),
            _DeterministicAgent(name="second", tracker=tracker),
            _DeterministicAgent(name="third", tracker=tracker),
        ]
    )

    events = await _run(workflow)

    assert tracker.calls == ["first", "second", "third"]
    assert [event.author for event in events] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_parallel_agent_starts_children_concurrently() -> None:
    tracker = _ExecutionTracker()
    barrier = _StartBarrier(expected=2)
    workflow = ParallelAgent(
        sub_agents=[
            _DeterministicAgent(name="left", tracker=tracker, barrier=barrier),
            _DeterministicAgent(name="right", tracker=tracker, barrier=barrier),
        ]
    )

    events = await _run(workflow)

    assert barrier.started == {"left", "right"}
    assert {event.author for event in events} == {"left", "right"}


@pytest.mark.asyncio
async def test_loop_agent_repeats_until_a_child_escalates() -> None:
    tracker = _ExecutionTracker()
    workflow = LoopAgent(
        sub_agents=[
            _DeterministicAgent(name="planner", tracker=tracker),
            _DeterministicAgent(
                name="reviewer",
                tracker=tracker,
                escalate_on_call=2,
            ),
        ],
        max_iterations=5,
    )

    events = await _run(workflow)

    assert tracker.calls == ["planner", "reviewer", "planner", "reviewer"]
    assert events[-1].actions.escalate is True


@pytest.mark.asyncio
async def test_loop_agent_stops_at_max_iterations_without_escalation() -> None:
    tracker = _ExecutionTracker()
    workflow = LoopAgent(
        sub_agents=[
            _DeterministicAgent(name="worker", tracker=tracker),
        ],
        max_iterations=3,
    )

    await _run(workflow)

    assert tracker.calls == ["worker", "worker", "worker"]
