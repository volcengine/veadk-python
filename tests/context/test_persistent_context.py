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

"""Persist actual Runner projections, then reload with fresh model/service objects."""

import asyncio
import copy
import json

import httpx
import pytest
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from litellm import ModelResponse

from veadk import Agent, Runner
from veadk.context.runtime import current_scope, is_summary
from veadk.models.retrying_lite_llm import RetryingLiteLlm

IDENTITY = {
    "app_name": "context_persistence",
    "user_id": "synthetic",
    "session_id": "invoice",
}


def content(role, text):
    return types.Content(role=role, parts=[types.Part(text=text)])


class PersistenceClient(LiteLLMClient):
    def __init__(self):
        self.calls = []

    async def acompletion(self, **kwargs):
        self.calls.append((is_summary.get(), copy.deepcopy(kwargs)))
        if is_summary.get():
            text = json.dumps(
                {
                    "goal": "Reconcile INV-418",
                    "active_constraints": ["Never submit payment"],
                    "decisions": [],
                    "completed_work": [],
                    "pending_work": [],
                    "evidence": ["INV-418 total=187.25 CNY"],
                    "uncertainties": [],
                }
            )
        else:
            text = "INV-418: 187.25 CNY; payment is prohibited."
        return ModelResponse(
            model=kwargs["model"],
            choices=[
                {
                    "message": {"role": "assistant", "content": text},
                }
            ],
        )


def agent_for(client, mode="auto", **policy_updates):
    model = RetryingLiteLlm(
        model="openai/context-test",
        api_key="offline-test",
        llm_client=client,
        context_compression={
            "mode": mode,
            "context_window": 20000,
            "output_reserve": 2000,
            "safety_margin": 256,
            "trigger_ratio": 0.4,
            "summary_trigger_ratio": 0.4,
            "target_ratio": 0.3,
            **policy_updates,
        },
    )
    return Agent(
        name="accountant",
        model=model,
        model_api_key="offline-test",
        instruction="Retain invoice facts and never submit payment.",
    )


async def run(service, agent, question):
    runner = Runner(agent=agent, app_name=IDENTITY["app_name"], session_service=service)
    return [
        event
        async for event in runner.run_async(
            user_id=IDENTITY["user_id"],
            session_id=IDENTITY["session_id"],
            new_message=content("user", question),
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("resume_mode", ["auto", "off"])
async def test_sqlite_reload_reuses_verified_summary_or_restores_originals(
    tmp_path, resume_mode
):
    url = "sqlite+aiosqlite:///" + str(tmp_path / "sessions.sqlite")
    service = DatabaseSessionService(db_url=url)
    first_client = PersistenceClient()
    try:
        session = await service.create_session(**IDENTITY)
        for index in range(8):
            for author, value in [
                (
                    "user",
                    content(
                        "user", f"Invoice INV-418 step {index}. Never submit payment."
                    ),
                ),
                (
                    "accountant",
                    content(
                        "model", "Historical explanation. " * 35 + "Total 187.25 CNY."
                    ),
                ),
            ]:
                await service.append_event(
                    session,
                    Event(
                        author=author,
                        invocation_id=f"history-{index}",
                        content=value,
                    ),
                )
        originals = [e.content.model_dump(mode="json") for e in session.events]
        await run(
            service, agent_for(first_client), "Explain the discrepancy; do not pay."
        )
        saved = await service.get_session(**IDENTITY)
        cache = {k: v for k, v in saved.state.items() if k.startswith("veadk:context:")}
        assert len(cache) == 1
        assert [summary for summary, _ in first_client.calls] == [True, False]
        assert [
            e.content.model_dump(mode="json") for e in saved.events[: len(originals)]
        ] == originals
        record = next(iter(cache.values()))
        assert record["input_after"] < record["input_before"]
        assert record["input_after"] <= record["budget"]
    finally:
        await service.close()

    # Reload from SQLite, not from a copied in-memory Session or shared model.
    resumed_service = DatabaseSessionService(db_url=url)
    resumed_client = PersistenceClient()
    try:
        reloaded = await resumed_service.get_session(**IDENTITY)
        assert {
            k: v for k, v in reloaded.state.items() if k.startswith("veadk:context:")
        } == cache
        await run(
            resumed_service,
            agent_for(resumed_client, resume_mode),
            "Restate the exact amount and the payment restriction.",
        )
        assert len(resumed_client.calls) == 1
        summary, request = resumed_client.calls[0]
        assert not summary
        texts = [m.get("content", "") for m in request["messages"]]
        marker = "Summary of earlier conversation"
        if resume_mode == "auto":
            assert any(marker in text for text in texts)
            assert not any("Invoice INV-418 step 0" in text for text in texts)
        else:
            assert not any(marker in text for text in texts)
            assert any("Invoice INV-418 step 0" in text for text in texts)
        assert any("187.25 CNY" in text for text in texts)
        assert any("Never submit payment" in text for text in texts)
        after = await resumed_service.get_session(**IDENTITY)
        assert [
            e.content.model_dump(mode="json") for e in after.events[: len(originals)]
        ] == originals
        assert {
            k: v for k, v in after.state.items() if k.startswith("veadk:context:")
        } == cache
        assert current_scope.get() is None
    finally:
        await resumed_service.close()


@pytest.mark.asyncio
async def test_rolling_sqlite_sessions_rebuild_original_history_at_depth_limit(
    tmp_path,
):
    url = "sqlite+aiosqlite:///" + str(tmp_path / "rolling.sqlite")
    depths = []
    previous_source_count = 0
    for round_number in range(6):
        # Each turn uses a new database connection and model. Only persisted
        # events/state may carry the rolling summary across these boundaries.
        service = DatabaseSessionService(db_url=url)
        client = PersistenceClient()
        try:
            session = (
                await service.create_session(**IDENTITY)
                if round_number == 0
                else await service.get_session(**IDENTITY)
            )
            for index in range(2):
                for author, value in [
                    (
                        "user",
                        content(
                            "user",
                            f"Archive round {round_number} step {index}. "
                            "INV-418 total=187.25 CNY. Never submit payment.",
                        ),
                    ),
                    (
                        "accountant",
                        content("model", "Historical explanation. " * 110),
                    ),
                ]:
                    await service.append_event(
                        session,
                        Event(
                            author=author,
                            invocation_id=f"archive-{round_number}-{index}",
                            content=value,
                        ),
                    )
            originals = [e.content.model_dump(mode="json") for e in session.events]
            question = f"Current task {round_number}: restate amount, never pay."
            await run(
                service,
                agent_for(
                    client,
                    max_summary_depth=2,
                    keep_recent_turns=1,
                    trigger_ratio=0.15,
                    summary_trigger_ratio=0.15,
                    target_ratio=0.1,
                ),
                question,
            )
            saved = await service.get_session(**IDENTITY)
            records = [
                value
                for key, value in saved.state.items()
                if key.startswith("veadk:context:")
            ]
            assert len(records) == 1
            record = records[0]
            depths.append(record["depth"])
            assert record["source_count"] > previous_source_count
            previous_source_count = record["source_count"]
            assert record["input_after"] < record["input_before"]
            assert record["input_after"] <= record["budget"]
            assert [
                e.content.model_dump(mode="json")
                for e in saved.events[: len(originals)]
            ] == originals
            summary_input = json.dumps(
                [request["messages"] for summary, request in client.calls if summary]
            )
            assert summary_input != "[]"
            if round_number % 2 == 0:
                assert "Archive round 0 step 0" in summary_input
                assert "Summary of earlier conversation" not in summary_input
            else:
                assert "Summary of earlier conversation" in summary_input
                assert "Archive round 0 step 0" not in summary_input
            main_requests = [
                request for summary, request in client.calls if not summary
            ]
            assert len(main_requests) == 1
            final_input = json.dumps(main_requests[0]["messages"])
            assert question in final_input
            assert "187.25 CNY" in final_input
            assert "Never submit payment" in final_input
            assert current_scope.get() is None
        finally:
            await service.close()
    assert depths == [1, 2, 1, 2, 1, 2]


class OrderedCompletionClient(PersistenceClient):
    def __init__(self, label, hold=False):
        super().__init__()
        self.label = label
        self.ready = asyncio.Event()
        self.release = asyncio.Event()
        if not hold:
            self.release.set()

    async def acompletion(self, **kwargs):
        if is_summary.get():
            self.ready.set()
            await self.release.wait()
        response = await super().acompletion(**kwargs)
        if is_summary.get():
            value = json.loads(response.choices[0].message.content)
            value["completed_work"] = [self.label]
            response.choices[0].message.content = json.dumps(value)
        return response


@pytest.mark.asyncio
async def test_out_of_order_runner_completion_reuses_newest_verified_projection(
    monkeypatch,
):
    from google.adk.sessions import InMemorySessionService

    def reject(*args, **kwargs):
        raise AssertionError("concurrent session regression must stay offline")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    service = InMemorySessionService()
    session = await service.create_session(**IDENTITY)
    for index in range(8):
        for author, value in [
            ("user", content("user", f"Round {index}; never submit payment.")),
            ("accountant", content("model", "Historical explanation. " * 35)),
        ]:
            await service.append_event(
                session,
                Event(author=author, invocation_id=f"history-{index}", content=value),
            )
    original_events = [e.model_dump(mode="json") for e in session.events]
    old = OrderedCompletionClient("OLDER_SNAPSHOT", hold=True)
    old_task = asyncio.create_task(run(service, agent_for(old), "Earlier request"))
    try:
        await asyncio.wait_for(old.ready.wait(), timeout=5)
        new = OrderedCompletionClient("NEWER_SNAPSHOT")
        latest_request = "Latest request: retain payment prohibition and invoice facts."
        await run(service, agent_for(new), latest_request)
        before = await service.get_session(**IDENTITY)
        before_events = [e.model_dump(mode="json") for e in before.events]
        new_record = next(
            v for k, v in before.state.items() if k.startswith("veadk:context:")
        )

        old.release.set()
        await asyncio.wait_for(old_task, timeout=5)
        after = await service.get_session(**IDENTITY)
        # The backend uses last-writer-wins state. Immutable event records must
        # let the next invocation recover the most advanced valid projection.
        old_record = next(
            v for k, v in after.state.items() if k.startswith("veadk:context:")
        )
        assert old_record["source_count"] < new_record["source_count"]
        assert [
            e.model_dump(mode="json") for e in after.events[: len(before_events)]
        ] == before_events

        followup = PersistenceClient()
        await run(service, agent_for(followup), "Restate the latest request.")
        assert len(followup.calls) == 1
        summary, payload = followup.calls[0]
        assert summary is False
        text = json.dumps(payload["messages"])
        assert "NEWER_SNAPSHOT" in text
        assert "OLDER_SNAPSHOT" not in text
        assert latest_request in text
        final = await service.get_session(**IDENTITY)
        assert [
            e.model_dump(mode="json") for e in final.events[: len(original_events)]
        ] == original_events
        assert current_scope.get() is None
    finally:
        old.release.set()
        if not old_task.done():
            old_task.cancel()
        await asyncio.gather(old_task, return_exceptions=True)
