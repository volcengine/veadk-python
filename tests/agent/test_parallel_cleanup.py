# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0

"""Offline contracts for task ownership, backpressure and resumable workflows."""

import asyncio
from contextlib import aclosing
from contextvars import ContextVar
from typing import Any

import pytest
from google.adk.agents import BaseAgent
from google.adk.agents.base_agent import BaseAgentState
from google.adk.agents.invocation_context import InvocationContext
from google.adk.apps import ResumabilityConfig
from google.adk.events import Event
from google.adk.sessions import InMemorySessionService, Session
from google.genai import types

from veadk.agents.parallel_agent import ParallelAgent, _merge_agent_runs


@pytest.mark.asyncio
async def test_merge_waits_for_event_acknowledgement():
    steps = []

    async def child():
        steps.append("first")
        yield Event(author="child", id="first")
        steps.append("second")
        yield Event(author="child", id="second")
        steps.append("finished")

    async with aclosing(_merge_agent_runs([child()])) as events:
        assert (await anext(events)).id == "first"
        await asyncio.sleep(0)
        assert steps == ["first"]
        assert (await anext(events)).id == "second"
        await asyncio.sleep(0)
        assert steps == ["first", "second"]
        with pytest.raises(StopAsyncIteration):
            await anext(events)
    assert steps == ["first", "second", "finished"]


@pytest.mark.asyncio
async def test_merge_early_close_awaits_cleanup_in_each_owning_task():
    owners = {}
    cleaned = set()
    ready = asyncio.Event()
    context = ContextVar("parallel_cleanup_owner")

    async def child(name):
        owner = asyncio.current_task()
        owners[name] = owner
        token = context.set(name)
        if len(owners) == 2:
            ready.set()
        try:
            await ready.wait()
            yield Event(author=name)
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            assert asyncio.current_task() is owner
            assert context.get() == name
            context.reset(token)
            cleaned.add(name)

    async with aclosing(_merge_agent_runs([child("left"), child("right")])) as events:
        await asyncio.wait_for(anext(events), timeout=2)
    assert cleaned == {"left", "right"}
    assert all(task.done() for task in owners.values())
    assert context.get(None) is None


@pytest.mark.asyncio
async def test_merge_child_error_cancels_and_awaits_blocked_sibling():
    started = asyncio.Event()
    cleaned = asyncio.Event()
    owners = []
    failure = ValueError("synthetic child failure")

    async def blocked():
        owners.append(asyncio.current_task())
        try:
            started.set()
            await asyncio.Event().wait()
            yield Event(author="blocked")
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    async def broken():
        await started.wait()
        raise failure
        yield Event(author="broken")  # pragma: no cover

    async with aclosing(_merge_agent_runs([blocked(), broken()])) as events:
        with pytest.raises(ValueError) as caught:
            await asyncio.wait_for(anext(events), timeout=2)
    assert caught.value is failure
    assert cleaned.is_set()
    assert owners[0].done()


@pytest.mark.asyncio
async def test_merge_cancellation_awaits_all_children():
    owners = []
    cleaned = []
    ready = asyncio.Event()

    async def child(name):
        owners.append(asyncio.current_task())
        if len(owners) == 2:
            ready.set()
        try:
            await asyncio.Event().wait()
            yield Event(author=name)
        finally:
            await asyncio.sleep(0)
            cleaned.append(name)

    async def run():
        async with aclosing(
            _merge_agent_runs([child("left"), child("right")])
        ) as events:
            async for _ in events:
                pass

    task = asyncio.create_task(run())
    await asyncio.wait_for(ready.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert set(cleaned) == {"left", "right"}
    assert all(owner.done() for owner in owners)


class ResumableChild(BaseAgent):
    calls: Any
    pause: bool = False
    mark_done_on_pause: bool = False

    async def _run_async_impl(self, ctx):
        self.calls.append((self.name, ctx.branch))
        if self.pause:
            if self.mark_done_on_pause:
                ctx.set_agent_state(self.name, end_of_agent=True)
            yield Event(
                author=self.name,
                long_running_tool_ids={"approval"},
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id="approval", name="request_approval", args={}
                            )
                        )
                    ],
                ),
            )
        else:
            ctx.set_agent_state(self.name, end_of_agent=True)
            yield Event(author=self.name)


def invocation(agent):
    return InvocationContext(
        session_service=InMemorySessionService(),
        invocation_id="offline-parallel",
        agent=agent,
        branch="outer",
        session=Session(id="session", app_name="offline", user_id="synthetic"),
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


@pytest.mark.asyncio
async def test_parallel_resume_skips_completed_child_and_finishes_parent():
    calls = []
    workflow = ParallelAgent(
        name="team",
        sub_agents=[
            ResumableChild(name="left", calls=calls),
            ResumableChild(name="right", calls=calls),
        ],
    )
    ctx = invocation(workflow)
    ctx.set_agent_state("team", agent_state=BaseAgentState())
    ctx.set_agent_state("left", end_of_agent=True)
    events = [event async for event in workflow.run_async(ctx)]
    assert calls == [("right", "outer.team.right")]
    assert ctx.end_of_agents == {"left": True, "right": True, "team": True}
    assert "team" not in ctx.agent_states
    assert [event.author for event in events] == ["right", "team"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mark_done_on_pause", [False, True])
async def test_parallel_pause_does_not_finish_parent_and_can_resume(mark_done_on_pause):
    calls = []
    left = ResumableChild(
        name="left", calls=calls, pause=True, mark_done_on_pause=mark_done_on_pause
    )
    workflow = ParallelAgent(
        name="team",
        sub_agents=[
            left,
            ResumableChild(name="right", calls=calls),
        ],
    )
    ctx = invocation(workflow)
    events = [event async for event in workflow.run_async(ctx)]
    assert set(calls) == {("left", "outer.team.left"), ("right", "outer.team.right")}
    assert events[0].author == "team"
    assert len(events) == 3
    assert ctx.end_of_agents["team"] is False
    assert ctx.end_of_agents["right"] is True
    assert "team" in ctx.agent_states
    assert any(ctx.should_pause_invocation(event) for event in events)

    calls.clear()
    left.pause = False
    resumed = [event async for event in workflow.run_async(ctx)]
    assert calls == ([] if mark_done_on_pause else [("left", "outer.team.left")])
    assert resumed[-1].author == "team"
    assert ctx.end_of_agents == {"left": True, "right": True, "team": True}
    assert "team" not in ctx.agent_states


@pytest.mark.asyncio
async def test_parallel_empty_workflow_does_not_create_resume_state():
    workflow = ParallelAgent(name="empty")
    ctx = invocation(workflow)
    assert [event async for event in workflow.run_async(ctx)] == []
    assert ctx.agent_states == ctx.end_of_agents == {}
