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

"""Bounded model-only recovery, fallback and streaming regression contracts."""

import asyncio
import copy
import json

import pytest
from google.adk.models.lite_llm import LiteLlm, LiteLLMClient
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from litellm import ContextWindowExceededError, ModelResponse

from veadk.context.attempts import current_attempts
from veadk.context.budget import ContextBudgetError
from veadk.models.retrying_lite_llm import RetryingLiteLlm

SUMMARY = json.dumps(
    {
        "goal": "Explain INV-418",
        "active_constraints": ["Never pay"],
        "decisions": ["Use corrected total"],
        "completed_work": ["Read invoice"],
        "pending_work": ["Explain total"],
        "evidence": ["187.25 CNY"],
        "uncertainties": [],
    }
)


def overflow():
    return ContextWindowExceededError(
        message="synthetic context overflow",
        model="context-test",
        llm_provider="openai",
    )


def request():
    contents = []
    for _ in range(5):
        contents.extend(
            [
                types.Content(
                    role="user", parts=[types.Part(text="Reconcile INV-418; never pay")]
                ),
                types.Content(
                    role="model", parts=[types.Part(text="Prior analysis. " * 50)]
                ),
            ]
        )
    contents.append(
        types.Content(role="user", parts=[types.Part(text="Explain the total")])
    )
    return LlmRequest(contents=contents)


class RecoveryClient(LiteLLMClient):
    def __init__(self, always_fail=False):
        self.requests = []
        self.always_fail = always_fail

    async def acompletion(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        if kwargs.get("response_format"):
            text = SUMMARY
        elif len(self.requests) == 1 or self.always_fail:
            raise overflow()
        else:
            text = "187.25 CNY; no payment submitted."
        return ModelResponse(
            model="openai/context-test",
            choices=[
                {
                    "message": {"role": "assistant", "content": text},
                }
            ],
        )


def model(client, **overrides):
    return RetryingLiteLlm(
        model="openai/context-test",
        llm_client=client,
        context_compression={
            "context_window": 30000,
            "output_reserve": 2000,
            **overrides,
        },
    )


@pytest.mark.asyncio
async def test_structured_overflow_forces_one_strictly_smaller_model_retry():
    client = RecoveryClient()
    original = request()
    snapshot = original.model_dump()
    responses = [r async for r in model(client).generate_content_async(original)]
    assert len(responses) == 1
    assert len(client.requests) == 3  # inference, summary, smaller inference
    assert len(json.dumps(client.requests[-1]["messages"])) < len(
        json.dumps(client.requests[0]["messages"])
    )
    assert original.model_dump() == snapshot
    assert current_attempts.get() is None


@pytest.mark.asyncio
async def test_second_overflow_is_terminal_and_does_not_loop():
    client = RecoveryClient(always_fail=True)
    with pytest.raises(ContextBudgetError, match="provider_context_limit"):
        _ = [r async for r in model(client).generate_content_async(request())]
    assert len(client.requests) == 3


@pytest.mark.asyncio
async def test_recovery_without_smaller_input_does_not_resend():
    client = RecoveryClient()
    short = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])]
    )
    with pytest.raises(ContextBudgetError, match="provider_context_limit"):
        _ = [r async for r in model(client).generate_content_async(short)]
    assert len(client.requests) == 1


@pytest.mark.asyncio
async def test_overflow_after_visible_output_never_replays(monkeypatch):
    attempts = 0

    async def stream(_self, _request, stream=False):
        nonlocal attempts
        attempts += 1
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="visible")]),
            partial=True,
        )
        raise overflow()

    monkeypatch.setattr(LiteLlm, "generate_content_async", stream)
    with pytest.raises(ContextWindowExceededError):
        _ = [
            r
            async for r in model(RecoveryClient()).generate_content_async(
                request(), stream=True
            )
        ]
    assert attempts == 1


@pytest.mark.asyncio
async def test_quota_retry_and_fallback_share_one_attempt_limit(monkeypatch):
    class RateLimited(LiteLLMClient):
        def __init__(self):
            self.requests = []

        async def acompletion(self, **kwargs):
            self.requests.append(kwargs)
            error = RuntimeError("synthetic quota failure")
            error.status_code = 429
            raise error

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("veadk.models.retrying_lite_llm.asyncio.sleep", no_sleep)
    client = RateLimited()
    llm = RetryingLiteLlm(
        model="unknown-primary",
        llm_client=client,
        fallbacks=["unknown-fallback"],
        context_compression={"max_model_attempts": 3},
    )
    with pytest.raises(ContextBudgetError, match="model_attempt_budget_exhausted"):
        _ = [r async for r in llm.generate_content_async(request())]
    assert len(client.requests) == 3
    assert all(r["num_retries"] == 0 for r in client.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", ["lite", "ark"])
async def test_stream_stall_respects_deadline_and_closes_without_replay(
    monkeypatch, adapter
):
    from veadk.models.ark_llm import ArkLlm

    calls = 0
    closed = False

    async def stalled(*args, **kwargs):
        nonlocal calls, closed
        calls += 1
        try:
            yield LlmResponse(
                partial=True, content=types.Content(parts=[types.Part(text="visible")])
            )
            await asyncio.Event().wait()
        finally:
            closed = True

    if adapter == "lite":
        monkeypatch.setattr(LiteLlm, "generate_content_async", stalled)
        llm = model(RecoveryClient(), request_timeout_seconds=0.02)
    else:
        monkeypatch.setattr(ArkLlm, "_generate_prepared", stalled)
        llm = ArkLlm(
            model="openai/synthetic",
            context_compression={"request_timeout_seconds": 0.02},
        )
    emitted = []

    async def collect():
        async for item in llm.generate_content_async(LlmRequest(), stream=True):
            emitted.append(item)

    with pytest.raises(ContextBudgetError, match="request_time_budget_exhausted"):
        await asyncio.wait_for(collect(), timeout=0.5)
    assert len(emitted) == 1 and calls == 1 and closed
    assert current_attempts.get() is None
