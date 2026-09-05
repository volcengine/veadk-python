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
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService, Session
from google.genai import types
from packaging.version import Version

import veadk.utils.patches as patches
from veadk import Agent
from veadk.agents.loop_agent import LoopAgent
from veadk.agents.parallel_agent import ParallelAgent
from veadk.agents.sequential_agent import SequentialAgent
from veadk.utils.adk_compat import get_adk_version


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


class _TransferLlm(BaseLlm):
    async def generate_content_async(
        self, llm_request, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id="transfer-worker",
                            name="transfer_to_agent",
                            args={"agent_name": "worker"},
                        )
                    )
                ],
            )
        )


class _DirectLlm(BaseLlm):
    async def generate_content_async(
        self, llm_request, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="worker-ok")],
            )
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


def _workflow_peer(agent_type: str, tracker: _ExecutionTracker) -> BaseAgent:
    leaf = _DeterministicAgent(
        name=f"{agent_type}_peer_leaf",
        tracker=tracker,
        escalate_on_call=1 if agent_type == "loop" else None,
    )
    if agent_type == "parallel":
        return ParallelAgent(name="transfer_peer", sub_agents=[leaf])
    if agent_type == "sequential":
        return SequentialAgent(name="transfer_peer", sub_agents=[leaf])
    if agent_type == "loop":
        return LoopAgent(name="transfer_peer", sub_agents=[leaf], max_iterations=2)
    return _DeterministicAgent(name="transfer_peer", tracker=tracker)


def test_adk_2_0_to_2_1_workflow_mode_compat_does_not_change_serialization() -> None:
    if not Version("2.0.0") <= get_adk_version() < Version("2.2.0"):
        pytest.skip("The compatibility attribute is limited to ADK 2.0 and 2.1")

    for workflow in (
        ParallelAgent(name="parallel", sub_agents=[]),
        SequentialAgent(name="sequential", sub_agents=[]),
        LoopAgent(name="loop", sub_agents=[], max_iterations=1),
        _DeterministicAgent(name="custom", tracker=_ExecutionTracker()),
    ):
        assert workflow.mode is None
        assert "mode" not in workflow.model_dump()


@pytest.mark.parametrize("adk_version", ("2.0.0", "2.1.0", "2.1.99"))
def test_workflow_mode_patch_covers_all_affected_adk_versions(
    monkeypatch: pytest.MonkeyPatch,
    adk_version: str,
) -> None:
    import google.adk.agents as adk_agents

    base_agent = type("BaseAgent", (), {})
    workflow_types = [
        type(name, (base_agent,), {})
        for name in ("ParallelAgent", "SequentialAgent", "LoopAgent", "CustomAgent")
    ]
    preconfigured_agent = type("PreconfiguredAgent", (base_agent,), {"mode": "task"})
    monkeypatch.setattr(
        patches,
        "get_adk_version",
        lambda: Version(adk_version),
    )
    monkeypatch.setattr(adk_agents, "BaseAgent", base_agent)

    patches.patch_adk_workflow_agent_mode()
    patches.patch_adk_workflow_agent_mode()

    assert base_agent.mode is None
    assert all(agent_type.mode is None for agent_type in workflow_types)
    assert preconfigured_agent.mode == "task"


@pytest.mark.parametrize("adk_version", ("1.34.3", "2.2.0", "3.0.0"))
def test_workflow_mode_patch_does_not_touch_unaffected_adk_versions(
    monkeypatch: pytest.MonkeyPatch,
    adk_version: str,
) -> None:
    import google.adk.agents as adk_agents

    base_agent = type("BaseAgent", (), {})
    agent_types = [
        type(name, (base_agent,), {})
        for name in ("ParallelAgent", "SequentialAgent", "LoopAgent", "CustomAgent")
    ]
    monkeypatch.setattr(
        patches,
        "get_adk_version",
        lambda: Version(adk_version),
    )
    monkeypatch.setattr(adk_agents, "BaseAgent", base_agent)

    patches.patch_adk_workflow_agent_mode()

    assert not hasattr(base_agent, "mode")
    assert all(not hasattr(agent_type, "mode") for agent_type in agent_types)


@pytest.mark.parametrize("peer_type", ("parallel", "sequential", "loop", "custom"))
@pytest.mark.asyncio
async def test_runner_handles_deep_mixed_workflow_peer_transfer(
    peer_type: str,
) -> None:
    """Delegated LLMs support every workflow peer affected before ADK 2.2."""
    tracker = _ExecutionTracker()
    worker = Agent(
        name="worker",
        model=_DirectLlm(model="worker-model"),
        model_api_key="test-key",
    )
    transfer_peer = _workflow_peer(peer_type, tracker)
    executed_workflow = ParallelAgent(
        name="executed_parallel",
        sub_agents=[
            SequentialAgent(
                name="sequence",
                sub_agents=[
                    _DeterministicAgent(name="sequence_first", tracker=tracker),
                    _DeterministicAgent(name="sequence_second", tracker=tracker),
                ],
            ),
            LoopAgent(
                name="loop",
                sub_agents=[
                    _DeterministicAgent(
                        name="loop_stop",
                        tracker=tracker,
                        escalate_on_call=1,
                    )
                ],
                max_iterations=3,
            ),
        ],
    )
    root = Agent(
        name="root",
        model=_TransferLlm(model="root-model"),
        model_api_key="test-key",
        sub_agents=[worker, transfer_peer],
    )
    scenario = SequentialAgent(
        name="scenario",
        sub_agents=[root, executed_workflow],
    )
    runner = InMemoryRunner(agent=scenario, app_name="mixed-workflow")
    session = await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="test-user",
    )

    events = [
        event
        async for event in runner.run_async(
            user_id="test-user",
            session_id=session.id,
            new_message=types.UserContent(parts=[types.Part(text="delegate")]),
        )
    ]

    assert any(
        event.author == "worker"
        and event.content
        and any(part.text == "worker-ok" for part in (event.content.parts or []))
        for event in events
    )
    assert set(tracker.calls) == {"sequence_first", "sequence_second", "loop_stop"}


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
