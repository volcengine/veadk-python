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

"""Compression must not silently shorten native main-response timeouts."""

import asyncio
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from veadk.context.attempts import AttemptLedger, current_attempts, next_with_deadline
from veadk.context.budget import ContextBudgetError
from veadk.context.config import ContextCompressionConfig
from veadk.models.ark_llm import ArkLlm
from veadk.models.retrying_lite_llm import RetryingLiteLlm


@pytest.fixture
def elapsed_clock(monkeypatch):
    from veadk.context import attempts

    clock = SimpleNamespace(now=time.monotonic())
    monkeypatch.setattr(attempts, "time", SimpleNamespace(monotonic=lambda: clock.now))
    return clock


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [RetryingLiteLlm, ArkLlm])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("summary_seconds,main_seconds", [(0, 130), (33, 90)])
async def test_default_does_not_add_total_timeout(
    monkeypatch, elapsed_clock, adapter, stream, summary_seconds, main_seconds
):
    """Simulate native calls exceeding 120 s, including the observed 33+90 case."""
    observed = []

    async def managed(self, request, streaming):
        assert streaming is stream
        elapsed_clock.now += summary_seconds
        ledger = current_attempts.get()
        observed.append(ledger.claim())
        elapsed_clock.now += main_seconds
        yield LlmResponse(content=types.Content(parts=[types.Part(text="done")]))

    monkeypatch.setattr(adapter, "_generate_managed", managed)
    model = adapter(model="openai/offline-model")
    responses = [r async for r in model.generate_content_async(LlmRequest(), stream)]
    assert len(responses) == 1
    assert observed == [None]
    assert current_attempts.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [RetryingLiteLlm, ArkLlm])
async def test_explicit_total_deadline_still_includes_summary(
    monkeypatch, elapsed_clock, adapter
):
    async def managed(self, request, stream):
        elapsed_clock.now += 33
        assert 86 < current_attempts.get().claim() <= 88
        elapsed_clock.now += 90
        yield LlmResponse()

    monkeypatch.setattr(adapter, "_generate_managed", managed)
    model = adapter(
        model="openai/offline-model",
        context_compression={"request_timeout_seconds": 120},
    )
    with pytest.raises(ContextBudgetError, match="request_time_budget_exhausted"):
        _ = [r async for r in model.generate_content_async(LlmRequest())]
    assert current_attempts.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [None, 120])
async def test_provider_timeout_is_not_reported_as_exhausted_sdk_deadline(limit):
    error = asyncio.TimeoutError("synthetic native timeout")

    async def iterator():
        raise error
        yield

    with pytest.raises(asyncio.TimeoutError) as caught:
        await next_with_deadline(iterator(), AttemptLedger(3, limit))
    assert caught.value is error


@pytest.mark.asyncio
@pytest.mark.parametrize("configured", [None, 17.0, "phase_timeouts"])
async def test_native_http_timeouts_and_body_are_preserved(monkeypatch, configured):
    captures = []

    async def send(self, request, **kwargs):
        captures.append((request.extensions["timeout"], json.loads(request.content)))
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "synthetic",
                "created": 0,
                "model": "offline-model",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    additional = {}
    if configured is not None:
        additional["timeout"] = (
            httpx.Timeout(connect=3, read=170, write=11, pool=13)
            if configured == "phase_timeouts"
            else configured
        )
    for adapter in (LiteLlm, RetryingLiteLlm):
        model = adapter(
            model="openai/offline-model",
            api_key="synthetic-offline",
            api_base="https://ark.cn-beijing.volces.com/api/v3",
            **additional,
        )
        request = LlmRequest(contents=[types.Content(parts=[types.Part(text="hello")])])
        _ = [r async for r in model.generate_content_async(request)]
    assert len(captures) == 2 and captures[0] == captures[1]


def test_summary_stays_bounded_without_a_main_deadline(elapsed_clock):
    ledger = AttemptLedger(3, None, started=elapsed_clock.now)
    elapsed_clock.now += 50
    assert ledger.summary_remaining(0.75) == 40
    assert ledger.remaining() is None
    elapsed_clock.now += 40
    with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
        ledger.summary_remaining(0.75)
    assert ledger.claim() is None


def test_attempt_budget_stays_bounded_without_a_main_deadline():
    ledger = AttemptLedger(1, None)
    assert ledger.claim() is None
    with pytest.raises(ContextBudgetError, match="model_attempt_budget_exhausted"):
        ledger.claim()


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [RetryingLiteLlm, ArkLlm])
async def test_custom_summary_budget_reaches_adapter_ledger(
    monkeypatch, elapsed_clock, adapter
):
    async def managed(self, request, stream):
        ledger = current_attempts.get()
        elapsed_clock.now += 20
        assert 24 < ledger.summary_remaining(0.75) < 26
        elapsed_clock.now += 26
        with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
            ledger.summary_remaining(0.75)
        assert ledger.claim() is None
        yield LlmResponse()

    monkeypatch.setattr(adapter, "_generate_managed", managed)
    model = adapter(
        model="openai/offline-model",
        context_compression={"summary_time_budget_seconds": 45},
    )
    assert len([r async for r in model.generate_content_async(LlmRequest())]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [RetryingLiteLlm, ArkLlm])
async def test_caller_cancellation_still_closes_default_stream(monkeypatch, adapter):
    started, closed = asyncio.Event(), asyncio.Event()

    async def managed(self, request, stream):
        try:
            started.set()
            await asyncio.Event().wait()
            yield
        finally:
            closed.set()

    monkeypatch.setattr(adapter, "_generate_managed", managed)
    model = adapter(model="openai/offline-model")

    async def collect():
        return [r async for r in model.generate_content_async(LlmRequest(), True)]

    task = asyncio.create_task(collect())
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    assert current_attempts.get() is None


@pytest.mark.asyncio
async def test_summary_deadline_cancels_without_an_explicit_request_limit():
    from veadk.context.runtime import is_summary
    from veadk.context.summary import summarize_history

    closed = asyncio.Event()

    class WaitingSummary:
        model = "offline-model"

        async def generate_content_async(self, request, stream=False):
            try:
                await asyncio.Event().wait()
                yield
            finally:
                closed.set()

    with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
        await summarize_history(
            [types.Content(role="user", parts=[types.Part(text="synthetic history")])],
            WaitingSummary(),
            ContextCompressionConfig(
                context_window=12000,
                summary_time_budget_seconds=0.05,
            ),
        )
    assert closed.is_set()
    assert not is_summary.get() and current_attempts.get() is None


@pytest.mark.parametrize(
    "field", ["request_timeout_seconds", "summary_time_budget_seconds"]
)
@pytest.mark.parametrize("value", [0, -1, 601, float("inf"), float("nan")])
def test_invalid_time_limits_are_rejected(field, value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ContextCompressionConfig(**{field: value})
