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

from types import SimpleNamespace

import pytest
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from veadk import Agent
from veadk.agents.sequential_agent import SequentialAgent
from veadk.runtime.output_state import maybe_save_output_to_state


def _text_event(
    text: str,
    *,
    author: str = "agent",
    thought: bool = False,
    partial: bool = False,
) -> Event:
    return Event(
        invocation_id="inv-1",
        author=author,
        partial=partial,
        content=types.Content(
            role="model",
            parts=[types.Part(text=text, thought=thought)],
        ),
    )


def test_maybe_save_output_to_state_writes_final_text() -> None:
    agent = SimpleNamespace(name="agent", output_key="answer", output_schema=None)
    event = _text_event("done")

    maybe_save_output_to_state(agent, event)

    assert event.actions.state_delta == {"answer": "done"}


def test_maybe_save_output_to_state_preserves_adk_empty_text_behavior() -> None:
    agent = SimpleNamespace(name="agent", output_key="answer", output_schema=None)
    event = _text_event("")

    maybe_save_output_to_state(agent, event)

    assert event.actions.state_delta == {"answer": ""}


@pytest.mark.parametrize(
    "event",
    [
        _text_event("partial", partial=True),
        _text_event("thought", thought=True),
        _text_event("other author", author="other"),
        Event(
            invocation_id="inv-1",
            author="agent",
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id="call-1",
                            name="tool",
                            args={},
                        )
                    )
                ],
            ),
        ),
        Event(
            invocation_id="inv-1",
            author="agent",
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id="call-1",
                            name="tool",
                            response={"ok": True},
                        )
                    )
                ],
            ),
        ),
    ],
)
def test_maybe_save_output_to_state_ignores_non_final_model_text(event: Event) -> None:
    agent = SimpleNamespace(name="agent", output_key="answer", output_schema=None)

    maybe_save_output_to_state(agent, event)

    assert event.actions.state_delta == {}


def test_maybe_save_output_to_state_validates_output_schema() -> None:
    class Result(BaseModel):
        answer: str

    agent = SimpleNamespace(name="agent", output_key="result", output_schema=Result)
    event = _text_event('{"answer": "done"}')

    maybe_save_output_to_state(agent, event)

    assert event.actions.state_delta == {"result": {"answer": "done"}}


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime", ["codex", "piagent"])
async def test_non_adk_runtime_saves_output_key(monkeypatch, runtime: str) -> None:
    final_event = _text_event("runtime result", author="worker")

    class FakeRuntime:
        async def run_async(self, agent, ctx):
            yield final_event

    monkeypatch.setattr("veadk.runtime.get_runtime", lambda name: FakeRuntime())
    agent = Agent(
        name="worker",
        runtime=runtime,
        model_api_key="test-key",
        output_key="result",
    )

    events = [event async for event in agent._run_async_impl(SimpleNamespace())]

    assert events == [final_event]
    assert final_event.actions.state_delta == {"result": "runtime result"}


@pytest.mark.asyncio
async def test_sequential_non_adk_runtime_output_key_updates_session_state(
    monkeypatch,
) -> None:
    writer_seen_plan: list[str | None] = []

    class FakeRuntime:
        async def run_async(self, agent, ctx):
            if agent.name == "planner":
                text = "outline"
            else:
                writer_seen_plan.append(ctx.session.state.get("plan"))
                text = f"writer saw {ctx.session.state.get('plan')}"
            yield _text_event(text, author=agent.name)

    monkeypatch.setattr("veadk.runtime.get_runtime", lambda name: FakeRuntime())
    root = SequentialAgent(
        name="pipeline",
        sub_agents=[
            Agent(
                name="planner",
                runtime="codex",
                model_api_key="test-key",
                output_key="plan",
            ),
            Agent(
                name="writer",
                runtime="piagent",
                model_api_key="test-key",
                output_key="draft",
            ),
        ],
    )
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="app",
        user_id="user",
        session_id="session",
    )
    runner = Runner(
        app_name="app",
        agent=root,
        session_service=session_service,
    )

    events = [
        event
        async for event in runner.run_async(
            user_id="user",
            session_id="session",
            new_message=types.Content(role="user", parts=[types.Part(text="go")]),
        )
    ]
    session = await session_service.get_session(
        app_name="app",
        user_id="user",
        session_id="session",
    )

    assert [event.author for event in events if event.content] == ["planner", "writer"]
    assert writer_seen_plan == ["outline"]
    assert session.state["plan"] == "outline"
    assert session.state["draft"] == "writer saw outline"
