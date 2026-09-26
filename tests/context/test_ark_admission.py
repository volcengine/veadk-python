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

"""Ark normalization must not erase evidence used by admission checks."""

import asyncio

import pytest

from veadk.context.budget import ContextBudgetError
from veadk.models.ark_llm import ArkLlm, ArkLlmClient


class RecordingArkClient(ArkLlmClient):
    def __init__(self):
        self.requests = []

    async def aresponses(self, **kwargs):
        self.requests.append(kwargs)
        raise RuntimeError("synthetic transport failure")


def model(client, **kwargs):
    return ArkLlm(
        model="openai/primary",
        llm_client=client,
        context_compression={
            "context_window": 10000,
            "output_reserve": 1000,
            "safety_margin": 100,
        },
        **kwargs,
    )


@pytest.mark.asyncio
async def test_disabled_cache_must_not_drop_unaccounted_server_history():
    client = RecordingArkClient()
    llm = model(client, enable_responses_cache=False)
    with pytest.raises(ContextBudgetError, match="unaccounted_server_history"):
        _ = [
            r
            async for r in llm.generate_content_via_responses(
                {
                    "model": llm.model,
                    "input": [],
                    "previous_response_id": "synthetic-chain",
                }
            )
        ]
    assert client.requests == []


@pytest.mark.asyncio
async def test_ark_smaller_fallback_is_checked_before_sending(monkeypatch):
    monkeypatch.setattr(
        "veadk.context.budget.model_limits",
        lambda name: (
            {
                "max_input_tokens": 2000,
                "max_output_tokens": 1000,
            }
            if name.endswith("smaller")
            else {}
        ),
    )
    client = RecordingArkClient()
    llm = model(client, fallbacks=["openai/smaller"])
    with pytest.raises(ContextBudgetError, match="input_too_large"):
        _ = [
            r
            async for r in llm._generate_content_with_fallbacks(
                {
                    "input": [{"role": "user", "content": "x" * 4000}],
                }
            )
        ]
    assert [r["model"] for r in client.requests] == ["primary"]


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["instructions", "tools", "text"])
async def test_ark_protected_payload_is_checked_before_field_conversion(key):
    client = RecordingArkClient()
    llm = model(client)
    with pytest.raises(ContextBudgetError, match="input_too_large"):
        _ = [
            r
            async for r in llm.generate_content_via_responses(
                {
                    "model": llm.model,
                    "input": [],
                    key: "大内容" * 5000,
                }
            )
        ]
    assert client.requests == []


def test_known_window_uses_local_history_even_when_compression_is_off():
    llm = ArkLlm(
        model="openai/primary",
        context_compression={
            "mode": "off",
            "context_window": 10000,
            "output_reserve": 1000,
        },
    )
    assert llm.use_interactions_api is False


@pytest.mark.asyncio
async def test_ark_transport_stream_is_closed_after_a_stall(monkeypatch):
    from google.adk.models.llm_response import LlmResponse

    class Stream:
        closed = False
        reads = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            self.reads += 1
            if self.reads == 1:
                return object()
            await asyncio.Event().wait()

        async def close(self):
            self.closed = True

    stream = Stream()

    class StreamingClient(RecordingArkClient):
        async def aresponses(self, **kwargs):
            self.requests.append(kwargs)
            return stream

    client = StreamingClient()
    llm = ArkLlm(
        model="openai/synthetic",
        llm_client=client,
        context_compression={"request_timeout_seconds": 0.02},
    )
    monkeypatch.setattr(
        "veadk.models.ark_llm.event_to_generate_content_response",
        lambda **kwargs: LlmResponse(partial=True),
    )

    async def collect():
        return [
            r
            async for r in llm.generate_content_via_responses(
                {"model": llm.model, "input": []}, stream=True
            )
        ]

    with pytest.raises(ContextBudgetError, match="request_time_budget_exhausted"):
        await asyncio.wait_for(collect(), timeout=0.5)
    assert stream.closed and stream.reads == 2 and len(client.requests) == 1
