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

"""Every runtime waits for the complete external-tool batch before modeling."""

import pytest
from google.adk.apps.app import App, ResumabilityConfig
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.adk.tools.long_running_tool import LongRunningFunctionTool
from google.genai import types

from conformance_harness import Round


@pytest.mark.asyncio
@pytest.mark.parametrize("response_order", [("a", "b"), ("b", "a")])
@pytest.mark.parametrize("packed_calls", [False, True])
@pytest.mark.parametrize("resumable", [False, True])
async def test_partial_tool_results_do_not_invoke_model(
    harness, response_order, packed_calls, resumable
):
    executed = []

    async def external_job(value: str) -> None:
        """Start an operation whose result is supplied later."""
        executed.append(value)

    scripted = harness.adapter.build(
        [Round(text="Both results received.")],
        tools=[LongRunningFunctionTool(external_job)],
    )
    if resumable:
        runner = Runner(
            app=App(
                name=harness.APP_NAME,
                root_agent=scripted.agent,
                resumability_config=ResumabilityConfig(is_resumable=True),
            ),
            session_service=harness.session_service,
        )
    else:
        runner = Runner(
            app_name=harness.APP_NAME,
            agent=scripted.agent,
            session_service=harness.session_service,
        )
    session_id = await harness.new_session()
    session = await harness.session_service.get_session(
        app_name=harness.APP_NAME, user_id=harness.USER_ID, session_id=session_id
    )
    invocation = "inv-external-batch"

    async def append(event):
        await harness.session_service.append_event(session, event)

    await append(
        Event(
            invocation_id=invocation,
            author="user",
            content=types.Content(
                role="user", parts=[types.Part(text="Start both jobs.")]
            ),
        )
    )
    calls = [
        types.Part(
            function_call=types.FunctionCall(
                id=call_id, name="external_job", args={"value": call_id}
            )
        )
        for call_id in ["a", "b"]
    ]
    for parts in [calls] if packed_calls else [[part] for part in calls]:
        await append(
            Event(
                invocation_id=invocation,
                author=scripted.agent.name,
                long_running_tool_ids={part.function_call.id for part in parts},
                content=types.Content(role="model", parts=parts),
            )
        )

    async def send(call_id, *, will_continue=None):
        message = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=call_id,
                        name="external_job",
                        response={"value": f"result-{call_id}", "isFinal": True},
                        will_continue=will_continue,
                    )
                )
            ],
        )
        return [
            event
            async for event in runner.run_async(
                user_id=harness.USER_ID,
                session_id=session_id,
                new_message=message,
            )
        ]

    first, last = response_order
    assert await send(first) == []
    assert harness.adapter.requests() == []
    assert await send(last, will_continue=True) == []
    assert harness.adapter.requests() == []
    events = await send(last, will_continue=False)
    assert len(harness.adapter.requests()) == 1
    assert any(
        event.content
        and any(
            part.text == "Both results received." for part in event.content.parts or []
        )
        for event in events
    )
    assert not any(event.get_function_calls() for event in events)
    assert executed == []
    saved = await harness.session_service.get_session(
        app_name=harness.APP_NAME, user_id=harness.USER_ID, session_id=session_id
    )
    assert [
        response.id
        for event in saved.events
        for response in event.get_function_responses()
    ] == [first, last, last]

    # A new user turn after a cancelled/abandoned tool invocation stays runnable.
    session = saved
    await append(
        Event(
            invocation_id="abandoned-invocation",
            author=scripted.agent.name,
            long_running_tool_ids={"abandoned"},
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id="abandoned",
                            name="external_job",
                            args={"value": "abandoned"},
                        )
                    )
                ],
            ),
        )
    )
    async for _ in runner.run_async(
        user_id=harness.USER_ID,
        session_id=session_id,
        new_message=types.Content(
            role="user", parts=[types.Part(text="Start a different task.")]
        ),
    ):
        pass
    assert len(harness.adapter.requests()) == 2


@pytest.mark.asyncio
async def test_pending_agent_does_not_stop_parallel_sibling(harness):
    from google.adk.agents.parallel_agent import ParallelAgent

    async def external_job(value: str) -> None:
        """Wait for an external result."""
        raise AssertionError("Saved pending calls must not execute again")

    waiting = harness.adapter.build(
        [Round(text="waiting finished")],
        key="waiting",
        tools=[LongRunningFunctionTool(external_job)],
    )
    active = harness.adapter.build([Round(text="sibling finished")], key="active")
    waiting.agent.name = "waiting"
    active.agent.name = "active"
    parallel = ParallelAgent(name="parallel", sub_agents=[waiting.agent, active.agent])
    runner = Runner(
        app=App(
            name=harness.APP_NAME,
            root_agent=parallel,
            resumability_config=ResumabilityConfig(is_resumable=True),
        ),
        session_service=harness.session_service,
    )
    session_id = await harness.new_session()
    session = await harness.session_service.get_session(
        app_name=harness.APP_NAME, user_id=harness.USER_ID, session_id=session_id
    )
    invocation = "inv-parallel"
    await harness.session_service.append_event(
        session,
        Event(
            author="user",
            invocation_id=invocation,
            content=types.Content(
                role="user", parts=[types.Part(text="Run both branches.")]
            ),
        ),
    )
    await harness.session_service.append_event(
        session,
        Event(
            author="waiting",
            invocation_id=invocation,
            branch="parallel.waiting",
            long_running_tool_ids={"pending"},
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id="pending", name="external_job", args={"value": "pending"}
                        )
                    )
                ],
            ),
        ),
    )
    events = [
        event
        async for event in runner.run_async(
            user_id=harness.USER_ID, session_id=session_id, invocation_id=invocation
        )
    ]
    assert harness.adapter.requests("waiting") == []
    assert len(harness.adapter.requests("active")) == 1
    assert any(
        event.author == "active"
        and event.content
        and any(part.text == "sibling finished" for part in event.content.parts or [])
        for event in events
    )
    resumed = [
        event
        async for event in runner.run_async(
            user_id=harness.USER_ID,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id="pending",
                            name="external_job",
                            response={"value": "completed"},
                        )
                    )
                ],
            ),
        )
    ]
    assert len(harness.adapter.requests("waiting")) == 1
    assert len(harness.adapter.requests("active")) == 1
    assert any(
        event.author == "waiting"
        and event.content
        and any(part.text == "waiting finished" for part in event.content.parts or [])
        for event in resumed
    )
