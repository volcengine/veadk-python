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

"""A shared summary deadline must leave time for the main model request."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from veadk.context.attempts import AttemptLedger, current_attempts
from veadk.context.budget import ContextBudgetError
from veadk.context.config import ContextCompressionConfig
from veadk.context.manager import prepare_context
from veadk.context.runtime import is_summary
from veadk.context.summary import summarize_history


def content(role, text):
    return types.Content(role=role, parts=[types.Part(text=text)])


def history():
    return [
        item
        for i in range(8)
        for item in (content("user", f"Read record {i}"), content("model", "x" * 1200))
    ]


class TimedSummary:
    model = "offline-budget-model"

    def __init__(self, clock, steps):
        self.clock = clock
        self.steps = iter(steps)
        self.requests = []
        self.closed = 0

    async def generate_content_async(self, request, stream=False):
        self.requests.append(request)
        try:
            elapsed, fail = next(self.steps)
            self.clock.now += elapsed
            if fail:
                raise asyncio.TimeoutError
            text = json.dumps(
                {
                    "goal": "Continue task",
                    "active_constraints": [],
                    "decisions": [],
                    "completed_work": [],
                    "pending_work": [],
                    "evidence": ["offset 0.004 mm"],
                    "uncertainties": [],
                }
            )
            yield LlmResponse(content=content("model", text))
        finally:
            self.closed += 1


@pytest.fixture
def timed_parent(monkeypatch):
    from veadk.context import attempts, summary

    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(attempts, "time", SimpleNamespace(monotonic=lambda: clock.now))
    timeouts = []
    original_wait_for = asyncio.wait_for

    async def record_timeout(coro, timeout):
        timeouts.append(timeout)
        return await original_wait_for(coro, timeout)

    monkeypatch.setattr(
        summary,
        "asyncio",
        SimpleNamespace(wait_for=record_timeout, TimeoutError=asyncio.TimeoutError),
    )
    ledger = AttemptLedger(3, 120, started=0)
    token = current_attempts.set(ledger)
    yield clock, ledger, timeouts
    current_attempts.reset(token)


@pytest.mark.asyncio
async def test_chunk_timeouts_share_deadline_and_preserve_main_budget(timed_parent):
    clock, parent, timeouts = timed_parent
    model = TimedSummary(clock, [(50, False), (40, True)])
    with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
        await summarize_history(
            history(),
            model,
            ContextCompressionConfig(
                context_window=9000, summary_max_tokens=512, safety_margin=256
            ),
        )
    assert timeouts == [60, 40]
    assert parent.remaining() == 30
    assert model.closed == 2
    assert not is_summary.get()
    assert current_attempts.get() is parent


@pytest.mark.asyncio
async def test_merge_uses_remaining_shared_summary_budget(timed_parent):
    clock, parent, timeouts = timed_parent
    model = TimedSummary(clock, [(20, False), (20, False), (50, True)])
    with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
        await summarize_history(
            history(),
            model,
            ContextCompressionConfig(
                context_window=9000, summary_max_tokens=512, safety_margin=256
            ),
        )
    assert timeouts == [60, 60, 50]
    assert (
        "Historical partial summaries" in model.requests[-1].contents[0].parts[0].text
    )
    assert parent.remaining() == 30
    assert model.closed == 3


@pytest.mark.asyncio
async def test_second_summary_stage_cannot_reset_the_parent_deadline(timed_parent):
    clock, parent, timeouts = timed_parent
    model = TimedSummary(clock, [(60, False), (30, True)])
    config = ContextCompressionConfig(context_window=12000)
    await summarize_history(history()[:2], model, config)
    with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
        await summarize_history(history()[:2], model, config)
    assert timeouts == [60, 30]
    assert parent.remaining() == 30


@pytest.mark.asyncio
async def test_late_success_cannot_install_summary_after_shared_deadline(timed_parent):
    clock, parent, _ = timed_parent
    model = TimedSummary(clock, [(95, False)])
    with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
        await summarize_history(
            history()[:2], model, ContextCompressionConfig(context_window=12000)
        )
    assert parent.remaining() == 25


@pytest.mark.asyncio
@pytest.mark.parametrize("fits_original", [True, False])
async def test_exhausted_summary_budget_falls_back_only_if_original_fits(
    timed_parent, fits_original
):
    clock, parent, _ = timed_parent
    clock.now = 90
    model = TimedSummary(clock, [(0, False)] * 4)
    request = LlmRequest(
        model=model.model,
        contents=history()
        + [
            content("user", "Retain calibration facts"),
            content("model", "Acknowledged"),
            content("user", "Return offset"),
        ],
    )
    original = request.model_dump(mode="json")
    config = ContextCompressionConfig(
        context_window=30000 if fits_original else 9000,
        output_reserve=512,
        summary_max_tokens=512,
        safety_margin=256,
    )
    if fits_original:
        await prepare_context(request, model, config, {}, force=True)
        assert request.model_dump(mode="json") == original
        assert parent.claim() == 30
    else:
        with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
            await prepare_context(request, model, config, {}, force=True)
    assert model.requests == []


def test_default_summary_fraction_leaves_one_quarter_for_main_response():
    assert ContextCompressionConfig().summary_time_budget_ratio == 0.75


@pytest.mark.asyncio
async def test_standalone_chunks_share_one_local_deadline(timed_parent, monkeypatch):
    from veadk.context import summary

    clock, _, timeouts = timed_parent
    monkeypatch.setattr(
        summary,
        "AttemptLedger",
        lambda maximum, timeout, **kwargs: AttemptLedger(
            maximum, timeout, started=clock.now, **kwargs
        ),
    )
    token = current_attempts.set(None)
    model = TimedSummary(clock, [(50, False), (40, True)])
    try:
        with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
            await summarize_history(
                history(),
                model,
                ContextCompressionConfig(
                    context_window=9000, summary_max_tokens=512, safety_margin=256
                ),
            )
        assert timeouts == [60, 40]
        assert current_attempts.get() is None
        assert model.closed == 2
    finally:
        current_attempts.reset(token)


@pytest.mark.asyncio
async def test_single_call_timeout_keeps_distinct_classification(timed_parent):
    clock, parent, timeouts = timed_parent
    model = TimedSummary(clock, [(60, True)])
    with pytest.raises(ContextBudgetError, match="summary_timeout") as caught:
        await summarize_history(
            history()[:2], model, ContextCompressionConfig(context_window=12000)
        )
    assert caught.value.code == "summary_timeout"
    assert timeouts == [60]
    assert parent.remaining() == 60


@pytest.mark.asyncio
async def test_real_summary_deadline_cancels_and_closes_stream():
    closed = asyncio.Event()

    class WaitingSummary:
        model = "offline-budget-model"

        async def generate_content_async(self, request, stream=False):
            try:
                await asyncio.Event().wait()
                yield
            finally:
                closed.set()

    parent = AttemptLedger(3, 2)
    token = current_attempts.set(parent)
    try:
        with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
            await summarize_history(
                history()[:2],
                WaitingSummary(),
                ContextCompressionConfig(
                    context_window=12000, summary_time_budget_ratio=0.05
                ),
            )
        assert closed.is_set()
        assert parent.remaining() > 1
        assert current_attempts.get() is parent
        assert not is_summary.get()
    finally:
        current_attempts.reset(token)


@pytest.mark.parametrize("ratio", [0, -0.1, 1.01, float("nan"), float("inf")])
def test_invalid_summary_budget_ratio_is_rejected(ratio):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ContextCompressionConfig(summary_time_budget_ratio=ratio)


def test_summary_budget_uses_request_start_not_summary_start(timed_parent):
    clock, parent, _ = timed_parent
    clock.now = 80
    assert parent.summary_remaining(0.75) == 10
    assert parent.remaining() == 40
    clock.now = 120
    with pytest.raises(ContextBudgetError, match="request_time_budget_exhausted"):
        parent.summary_remaining(0.75)
