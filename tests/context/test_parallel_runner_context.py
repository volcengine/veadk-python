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

"""Exercise branch isolation through real ParallelAgent, Runner and Session."""

import asyncio
import copy
import json
from contextlib import suppress

import httpx
import pytest
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.sessions import InMemorySessionService
from google.genai import types
from litellm import ModelResponse

from veadk import Agent, Runner
from veadk.agents.parallel_agent import ParallelAgent
from veadk.context.runtime import current_scope, is_summary
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm

IDENTITY = {
    "app_name": "parallel_context",
    "user_id": "synthetic",
    "session_id": "shared",
}
FACTS = {"left": "LEFT-418 amount=187.25 CNY", "right": "RIGHT-602 amount=932.10 CNY"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("parallel context contracts must stay offline")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)


def content(role, text):
    return types.Content(role=role, parts=[types.Part(text=text)])


class ParallelClient(LiteLLMClient):
    def __init__(self, hold_summaries=False):
        self.calls = []
        self.scopes = {}
        self.ready = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = asyncio.Event()
        self.active_summaries = set()
        if not hold_summaries:
            self.release.set()

    async def acompletion(self, **kwargs):
        scope = current_scope.get()
        assert scope is not None
        name = scope.agent_name
        assert scope.branch == "team." + name
        self.scopes[name] = scope
        summary = is_summary.get()
        self.calls.append((name, summary, copy.deepcopy(kwargs)))
        if summary:
            self.active_summaries.add(name)
            if len(self.active_summaries) == 2:
                self.ready.set()
            try:
                # Neither branch can finish until both summaries are active.
                await asyncio.wait_for(self.ready.wait(), timeout=5)
                await self.release.wait()
            finally:
                self.active_summaries.remove(name)
                if not self.active_summaries:
                    self.closed.set()
            text = json.dumps(
                {
                    "goal": "Reconcile branch report",
                    "active_constraints": ["Never submit payment"],
                    "decisions": [],
                    "completed_work": [],
                    "pending_work": [],
                    "evidence": [FACTS[name]],
                    "uncertainties": [],
                }
            )
        else:
            text = FACTS[name] + "; payment prohibited."
        return ModelResponse(
            model=kwargs["model"],
            choices=[{"message": {"role": "assistant", "content": text}}],
        )


def team(client, mode="auto"):
    children = []
    for name, window in [("left", 20000), ("right", 22000)]:
        model = RetryingLiteLlm(
            model="openai/context-test",
            api_key="offline-test",
            llm_client=client,
            context_compression={
                "mode": mode,
                "context_window": window,
                "output_reserve": 2000,
                "safety_margin": 256,
                "trigger_ratio": 0.4,
                "summary_trigger_ratio": 0.4,
                "target_ratio": 0.3,
                "protected_context": (FACTS[name],),
            },
        )
        children.append(
            Agent(
                name=name,
                model=model,
                model_api_key="offline-test",
                instruction="Reconcile your branch; never submit payment.",
            )
        )
    return ParallelAgent(name="team", sub_agents=children)


async def seed(service):
    session = await service.create_session(**IDENTITY)
    for index in range(8):
        await service.append_event(
            session,
            Event(
                author="user",
                invocation_id=f"history-{index}",
                content=content(
                    "user", f"Reconcile round {index}. Never submit payment."
                ),
            ),
        )
        for name, fact in FACTS.items():
            await service.append_event(
                session,
                Event(
                    author=name,
                    branch="team." + name,
                    invocation_id=f"history-{index}",
                    content=content("model", "Historical explanation. " * 45 + fact),
                ),
            )
    return [event.model_dump(mode="json") for event in session.events]


async def run(service, client, mode="auto"):
    runner = Runner(
        agent=team(client, mode),
        short_term_memory=ShortTermMemory(),
        app_name=IDENTITY["app_name"],
        session_service=service,
    )
    return [
        event
        async for event in runner.run_async(
            user_id=IDENTITY["user_id"],
            session_id=IDENTITY["session_id"],
            new_message=content("user", "Restate your exact amount; do not pay."),
        )
    ]


def assert_isolated_calls(client):
    for name, summary, request in client.calls:
        messages = json.dumps(request["messages"], ensure_ascii=False)
        other = "right" if name == "left" else "left"
        assert FACTS[name] in messages
        assert FACTS[other] not in messages
        if not summary:
            assert "Restate your exact amount; do not pay." in messages


@pytest.mark.asyncio
@pytest.mark.parametrize("resume_mode", ["auto", "off"])
async def test_parallel_runner_keeps_branch_summaries_separate_on_resume(resume_mode):
    service = InMemorySessionService()
    originals = await seed(service)
    first = ParallelClient()
    events = await asyncio.wait_for(run(service, first), timeout=10)
    assert first.ready.is_set() and first.closed.is_set()
    assert len(first.calls) == 4
    assert_isolated_calls(first)
    assert current_scope.get() is None
    assert len({id(scope) for scope in first.scopes.values()}) == 2
    assert all(
        scope.summary_calls == 1 and not scope.pending_state
        for scope in first.scopes.values()
    )
    deltas = {
        event.author: {
            k: v
            for k, v in event.actions.state_delta.items()
            if k.startswith("veadk:context:")
        }
        for event in events
        if any(k.startswith("veadk:context:") for k in event.actions.state_delta)
    }
    assert set(deltas) == set(FACTS)
    assert all(len(delta) == 1 for delta in deltas.values())
    assert set(deltas["left"]).isdisjoint(deltas["right"])
    for name, delta in deltas.items():
        record = next(iter(delta.values()))
        assert FACTS[name] in record["summary"]
        assert record["input_after"] < record["input_before"]
        assert record["input_after"] <= record["budget"]
    assert (
        next(iter(deltas["left"].values()))["budget"]
        < next(iter(deltas["right"].values()))["budget"]
    )
    session = await service.get_session(**IDENTITY)
    cache = {
        k: copy.deepcopy(v)
        for k, v in session.state.items()
        if k.startswith("veadk:context:")
    }
    assert len(cache) == 2
    assert [
        event.model_dump(mode="json") for event in session.events[: len(originals)]
    ] == originals

    # Recreate the complete agent tree; only Session state may carry summaries.
    resumed = ParallelClient()
    await asyncio.wait_for(run(service, resumed, resume_mode), timeout=10)
    assert len(resumed.calls) == 2
    assert not any(summary for _, summary, _ in resumed.calls)
    assert_isolated_calls(resumed)
    for _, _, request in resumed.calls:
        messages = json.dumps(request["messages"])
        assert ("Summary of earlier conversation" in messages) == (
            resume_mode == "auto"
        )
        assert "Historical explanation." in messages  # recent original turns survive
    saved = await service.get_session(**IDENTITY)
    assert {
        k: v for k, v in saved.state.items() if k.startswith("veadk:context:")
    } == cache
    assert [
        event.model_dump(mode="json") for event in saved.events[: len(originals)]
    ] == originals
    assert current_scope.get() is None


@pytest.mark.asyncio
async def test_parallel_runner_cancellation_cleans_both_summaries_without_installing():
    service = InMemorySessionService()
    originals = await seed(service)
    client = ParallelClient(hold_summaries=True)
    task = asyncio.create_task(run(service, client))
    try:
        await asyncio.wait_for(client.ready.wait(), timeout=5)
        assert client.active_summaries == set(FACTS)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(client.closed.wait(), timeout=2)
        assert not client.active_summaries
        assert len(client.calls) == 2 and all(summary for _, summary, _ in client.calls)
        assert all(not scope.pending_state for scope in client.scopes.values())
        saved = await service.get_session(**IDENTITY)
        assert not any(k.startswith("veadk:context:") for k in saved.state)
        assert [
            event.model_dump(mode="json") for event in saved.events[: len(originals)]
        ] == originals
        assert current_scope.get() is None
    finally:
        client.release.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
