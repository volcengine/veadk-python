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

"""Native generation parity and model-aware planning, using actual HTTP JSON."""

import json

import httpx
import pytest
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from veadk.context.budget import ContextBudgetError, check_payload
from veadk.context.config import ContextCompressionConfig
from veadk.models.retrying_lite_llm import RetryingLiteLlm

MODEL = "doubao-seed-2-1-pro-260628"


@pytest.fixture
def wire(monkeypatch):
    captures = []

    async def send(self, request, **kwargs):
        assert request.url.host == "ark.cn-beijing.volces.com"
        body = json.loads(request.content)
        captures.append(body)
        content = "ok"
        if (body.get("response_format") or {}).get("type") == "json_schema":
            content = json.dumps(
                {
                    "goal": "continue",
                    "active_constraints": [],
                    "decisions": [],
                    "completed_work": ["recorded synthetic fact"],
                    "pending_work": [],
                    "evidence": ["synthetic fact"],
                    "uncertainties": [],
                }
            )
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "synthetic",
                "created": 0,
                "object": "chat.completion",
                "model": MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
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
    return captures


async def call(adapter, *, policy=None, additional=None, request_output=None):
    kwargs = dict(additional or {})
    if adapter is RetryingLiteLlm:
        kwargs["context_compression"] = policy
    model = adapter(
        model="openai/" + MODEL,
        api_base="https://ark.cn-beijing.volces.com/api/v3",
        api_key="synthetic-offline",
        **kwargs,
    )
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
        config=types.GenerateContentConfig(max_output_tokens=request_output),
    )
    _ = [r async for r in model.generate_content_async(request)]
    assert request.config.max_output_tokens == request_output
    return model


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "off"])
@pytest.mark.parametrize("reserve", [None, 20000])
@pytest.mark.parametrize("thinking", [None, "disabled"])
async def test_planning_reserve_must_not_inject_a_generation_cap(
    wire, mode, reserve, thinking
):
    additional = {"extra_body": {"thinking": {"type": thinking}}} if thinking else {}
    await call(LiteLlm, additional=additional)
    await call(
        RetryingLiteLlm,
        policy={"mode": mode, "output_reserve": reserve},
        additional=additional,
    )
    assert len(wire) == 2
    assert wire[1] == wire[0]
    assert "max_completion_tokens" not in wire[1] and "max_tokens" not in wire[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "additional,request_output",
    [
        ({"max_completion_tokens": 4096}, None),
        ({"max_tokens": 4096}, None),
        ({}, 8192),
        ({"extra_body": {"thinking": {"type": "disabled"}}, "max_tokens": 4096}, None),
    ],
)
async def test_explicit_provider_limits_and_thinking_remain_identical(
    wire, additional, request_output
):
    await call(LiteLlm, additional=additional, request_output=request_output)
    await call(
        RetryingLiteLlm,
        policy={"output_reserve": 20000},
        additional=additional,
        request_output=request_output,
    )
    assert len(wire) == 2 and wire[0] == wire[1]


def payload(**kwargs):
    return {"model": "openai/" + MODEL, "messages": [], **kwargs}


def test_native_thinking_reserves_space_without_claiming_answer_limit_is_total():
    budget = check_payload(payload(), ContextCompressionConfig())
    assert budget.output == 16384
    assert budget.available + budget.output + 1024 == 256000


def test_answer_limit_also_reserves_reasoning_space():
    budget = check_payload(payload(max_tokens=8000), ContextCompressionConfig())
    assert budget.output == 8000 + 12288


def test_explicit_total_limit_already_includes_reasoning():
    budget = check_payload(
        payload(max_completion_tokens=8000), ContextCompressionConfig()
    )
    assert budget.output == 8000


def test_disabled_thinking_needs_only_answer_reservation():
    budget = check_payload(
        payload(max_tokens=8000, extra_body={"thinking": {"type": "disabled"}}),
        ContextCompressionConfig(),
    )
    assert budget.output == 8000


@pytest.mark.parametrize("total_key", ["max_output_tokens", "max_completion_tokens"])
def test_ark_mutually_exclusive_limits_rejected_even_if_equal(total_key):
    with pytest.raises(ContextBudgetError, match="conflicting_output_limits"):
        check_payload(
            payload(max_tokens=4096, **{total_key: 4096}), ContextCompressionConfig()
        )


def test_answer_only_large_input_does_not_use_answer_as_total_reservation():
    with pytest.raises(ContextBudgetError, match="input_too_large"):
        check_payload(
            payload(
                max_tokens=4096, messages=[{"role": "user", "content": "x" * 245000}]
            ),
            ContextCompressionConfig(),
        )


def test_explicit_total_budget_accepts_input_that_really_fits():
    budget = check_payload(
        payload(
            max_completion_tokens=4096,
            messages=[{"role": "user", "content": "x" * 245000}],
        ),
        ContextCompressionConfig(),
    )
    assert budget.output == 4096


def test_unknown_model_answer_semantics_not_inferred_from_similar_name():
    p = {
        "model": "openai/doubao-seed-2-1-pro-other",
        "messages": [],
        "max_tokens": 4096,
    }
    budget = check_payload(p, ContextCompressionConfig(context_window=256000))
    assert budget.output == 4096


@pytest.mark.asyncio
async def test_small_explicit_total_does_not_use_larger_default_reserve(wire):
    await call(
        RetryingLiteLlm,
        policy={"context_window": 10000},
        additional={"max_completion_tokens": 512},
    )
    assert wire[0]["max_completion_tokens"] == 512


@pytest.mark.asyncio
@pytest.mark.parametrize("reserve", [None, 20000])
@pytest.mark.parametrize("explicit", [None, 8192])
async def test_responses_keeps_native_or_explicit_generation_limit(reserve, explicit):
    from veadk.models.ark_llm import ArkLlm, ArkLlmClient

    class Recorder(ArkLlmClient):
        def __init__(self):
            self.requests = []

        async def aresponses(self, **kwargs):
            self.requests.append(kwargs)
            raise RuntimeError("synthetic transport end")

    client = Recorder()
    model = ArkLlm(
        model="openai/" + MODEL,
        llm_client=client,
        context_compression={"output_reserve": reserve},
    )
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
        config=types.GenerateContentConfig(max_output_tokens=explicit),
    )
    with pytest.raises(RuntimeError, match="synthetic transport end"):
        _ = [r async for r in model.generate_content_async(request)]
    assert len(client.requests) == 1
    assert client.requests[0].get("max_output_tokens") == explicit
    assert request.config.max_output_tokens == explicit


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["max_tokens", "max_completion_tokens"])
async def test_summary_has_its_own_limit_without_mutating_main_settings(wire, key):
    import copy

    from veadk.context.summary import summarize

    model = await call(RetryingLiteLlm, additional={key: 8192})
    before = copy.deepcopy(model._additional_args)
    result = await summarize(
        [types.Content(role="user", parts=[types.Part(text="synthetic fact")])],
        model,
        ContextCompressionConfig(),
    )
    assert "synthetic fact" in result
    assert model._additional_args == before
    assert len(wire) == 2
    assert wire[0][key] == 8192
    assert wire[1]["max_completion_tokens"] == 2048
    assert wire[1].get("max_tokens") is None
    assert wire[1]["thinking"] == {"type": "disabled"}
