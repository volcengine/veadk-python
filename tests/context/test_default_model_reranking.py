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

"""Default embedding preparation and user-model extraction; all I/O is synthetic."""

import asyncio
import copy
import json
import time
from types import SimpleNamespace

import httpx
import pytest
from google.genai import types

from veadk.context import defaults
from veadk.context.config import ContextCompressionConfig
from veadk.models.retrying_lite_llm import RetryingLiteLlm

BASE = "https://ark.cn-beijing.volces.com/api/v3"
MODELS = [
    "deepseek-v4-1-pro-260910",
    "doubao-seed-2-1-pro-260628",
    "ep-user-extraction",
]


def make_model(name=MODELS[0], **kwargs):
    return RetryingLiteLlm(
        model="openai/" + name,
        api_base=BASE,
        api_key="synthetic-offline",
        context_compression={"context_window": 256000, "output_reserve": 2048},
        **kwargs,
    )


@pytest.fixture
def wire(monkeypatch):
    captures = []

    async def send(self, request, **kwargs):
        assert request.url.host == "ark.cn-beijing.volces.com"
        body = json.loads(request.content)
        captures.append(body)
        result = {"ids": [1, 0]}
        if (body.get("response_format") or {}).get("type") == "json_schema":
            result = dict(
                goal="continue",
                active_constraints=[],
                decisions=[],
                completed_work=[],
                pending_work=[],
                evidence=["invoice 418: 187.25 CNY"],
                uncertainties=[],
            )
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "synthetic",
                "created": 0,
                "object": "chat.completion",
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(result),
                        },
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


def test_default_quality_regression_prepare_enabled():
    policy = ContextCompressionConfig()
    assert policy.prepare_index, "embedding preparation is not enabled by default"
    assert policy.rerank
    assert not ContextCompressionConfig(prepare_index=False, rerank=False).rerank


@pytest.mark.asyncio
async def test_default_quality_regression_auto_binding(monkeypatch):
    from veadk.context.reranking import EvidenceRerankingRetriever

    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "synthetic-offline")
    model = make_model()
    async with defaults.invocation_retriever(
        SimpleNamespace(model=model), ContextCompressionConfig()
    ) as value:
        assert isinstance(value, EvidenceRerankingRetriever), (
            "embedding does not enable reranking"
        )
        assert value.uses_default_preparation
        assert value._selector._model is model
        assert not value._retriever._initialized


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MODELS)
async def test_default_quality_regression_user_summary_model(wire, name):
    from veadk.context.summary import summarize

    model = make_model(name, extra_body={"thinking": {"type": "enabled"}})
    original = copy.deepcopy(model._additional_args)
    await summarize(
        [
            types.Content(
                role="user", parts=[types.Part(text="invoice 418: 187.25 CNY")]
            )
        ],
        model,
        model._context_config,
    )
    assert len(wire) == 1 and wire[0]["model"] == name
    assert wire[0]["thinking"] == {"type": "disabled"}, (
        "user model summary still has thinking enabled"
    )
    assert model._additional_args == original


@pytest.mark.asyncio
@pytest.mark.parametrize("name", MODELS)
async def test_user_model_reranking_has_isolated_wire(wire, name):
    from veadk.context.model_reranking import ModelEvidenceSelector
    from veadk.context.runtime import is_auxiliary

    model = make_model(
        name,
        max_tokens=9999,
        stop=["ids"],
        extra_body={
            "thinking": {"type": "enabled"},
            "previous_response_id": "business-chain",
            "response_format": {"type": "json_object"},
        },
        fallbacks=["openai/ep-other"],
    )
    original = copy.deepcopy(model._additional_args)
    selector = ModelEvidenceSelector(model, model._context_config)
    ids = await selector(
        "invoice", ("other", "invoice 418: 187.25 CNY"), deadline=time.monotonic() + 10
    )
    assert ids == [1, 0], selector.last_status
    assert len(wire) == 1 and wire[0]["model"] == name
    assert wire[0]["thinking"] == {"type": "disabled"}
    assert wire[0]["max_completion_tokens"] == 256
    for key in (
        "tools",
        "tool_choice",
        "response_format",
        "previous_response_id",
        "stop",
        "max_tokens",
    ):
        assert key not in wire[0]
    assert model._additional_args == original
    assert not is_auxiliary()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled,policy",
    [
        (False, {}),
        (True, {"rerank": False}),
        (True, {"retrieval": "lexical"}),
        (True, {"mode": "off"}),
    ],
)
async def test_default_optouts_and_no_embedding_make_no_calls(
    monkeypatch, tmp_path, enabled, policy
):
    from veadk.context.reranking import EvidenceRerankingRetriever

    monkeypatch.chdir(tmp_path)
    if enabled:
        monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "synthetic-offline")
    else:
        monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    monkeypatch.setattr(
        defaults, "create_embedder", lambda *_: pytest.fail("unexpected embedding I/O")
    )
    async with defaults.invocation_retriever(
        SimpleNamespace(model=make_model()), ContextCompressionConfig(**policy)
    ) as value:
        assert not isinstance(value, EvidenceRerankingRetriever)
    assert not (tmp_path / ".adk").exists()


@pytest.mark.asyncio
async def test_embedding_defaults_preserve_caller_owned_retriever(monkeypatch):
    from veadk.context.retrieval import use_context_retriever

    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "synthetic-offline")
    supplied = SimpleNamespace()
    with use_context_retriever(supplied):
        async with defaults.invocation_retriever(
            SimpleNamespace(model=make_model()), ContextCompressionConfig()
        ) as value:
            assert value is supplied


@pytest.mark.asyncio
async def test_default_pressure_prepares_and_reranks_original_evidence(
    wire, monkeypatch, tmp_path
):
    from test_hybrid_index import FakeEmbedding
    from test_preview_admission import example
    from veadk.context.budget import count_input, request_payload
    from veadk.context.manager import prepare_context
    from veadk.context.runtime import current_scope

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "synthetic-offline")
    embeddings = []

    def create(_agent, config):
        embedding = FakeEmbedding()
        embeddings.append((config.embedding_max_calls, embedding))
        return embedding

    monkeypatch.setattr(defaults, "create_embedder", create)
    text, request, scope, policy, before = example(16000)
    original = copy.deepcopy(scope.session.events)
    from veadk import Agent

    agent = Agent(
        name="pressure_default",
        model_name=MODELS[0],
        model_api_key="synthetic-offline",
        model_api_base=BASE,
        context_compression=policy,
    )
    model = agent.model
    async with defaults.invocation_retriever(agent, policy) as retriever:
        scope.evidence_retriever = retriever
        token = current_scope.set(scope)
        try:
            await prepare_context(request, model, policy, {})
        finally:
            current_scope.reset(token)
        assert scope.evidence_rankings and wire
        assert scope.reranking_calls == len(wire)
        assert scope.reranking_status == "complete"
    assert any(budget == 512 and embedding.calls for budget, embedding in embeddings)
    assert count_input(request_payload(request), policy) < before
    assert scope.session.events == original
    assert all(
        body["model"] == MODELS[0] and body["thinking"] == {"type": "disabled"}
        for body in wire
    )


@pytest.mark.parametrize(
    "value",
    [
        '{"ids":[true]}',
        '{"ids":[-1]}',
        '{"ids":[2]}',
        '{"ids":[0,0]}',
        '{"ids":[],"ids":[0]}',
        '{"ids":[0],"text":"invented"}',
        '```json\n{"ids":[0]}\n```',
        '{"ids":"0"}',
        "[]",
        '{"ids":[0,1,2,3,4,5,6,7,8,9,10,11,12]}',
    ],
)
def test_selector_rejects_untrusted_ids(value):
    from veadk.context.model_reranking import _parse_ids

    with pytest.raises(ValueError):
        _parse_ids(value, 2)


@pytest.mark.asyncio
async def test_selector_budget_is_shared_across_calls(wire):
    from veadk.context.model_reranking import ModelEvidenceSelector

    policy = ContextCompressionConfig(reranking_max_calls=1)
    selector = ModelEvidenceSelector(make_model(), policy)
    assert await selector("q", ("a", "b"), deadline=time.monotonic() + 10) == [1, 0]
    assert await selector("q", ("a", "b"), deadline=time.monotonic() + 10) == []
    assert selector.last_status == "budget_exhausted" and len(wire) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_selector_timeout_and_cancel_drain_request(monkeypatch, cancel):
    from veadk.context.model_reranking import ModelEvidenceSelector
    from veadk.context.runtime import is_auxiliary, is_reranking

    started, drained = asyncio.Event(), asyncio.Event()

    async def slow(self, request, stream=False):
        assert is_reranking.get() and is_auxiliary()
        started.set()
        try:
            await asyncio.Event().wait()
            yield None
        finally:
            drained.set()

    monkeypatch.setattr(RetryingLiteLlm, "generate_content_async", slow)
    policy = ContextCompressionConfig(reranking_timeout_seconds=0.2)
    selector = ModelEvidenceSelector(make_model(), policy)
    task = asyncio.create_task(
        selector("q", ("a", "b"), deadline=time.monotonic() + 10)
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert selector.last_status == "cancelled"
    else:
        assert await task == []
        assert selector.last_status == "timeout"
    assert drained.is_set() and not is_auxiliary()


@pytest.mark.asyncio
async def test_selector_fails_closed_for_unknown_capacity_without_model_io(wire):
    from veadk.context.model_reranking import ModelEvidenceSelector

    model = RetryingLiteLlm(
        model="openai/ep-unknown", api_base=BASE, api_key="synthetic-offline"
    )
    selector = ModelEvidenceSelector(model, ContextCompressionConfig())
    assert await selector("q", ("a", "b"), deadline=time.monotonic() + 10) == []
    assert selector.last_status == "model_capacity_required" and not wire


@pytest.mark.asyncio
@pytest.mark.parametrize("transport_error", [False, True])
async def test_responses_extraction_disables_thinking_and_preserves_borrowed_client(
    transport_error,
):
    from veadk.context.auxiliary import extraction_model
    from veadk.context.model_reranking import ModelEvidenceSelector
    from veadk.models.ark_llm import (
        ArkLlm,
        ArkLlmClient,
        ArkTypeResponse,
        ResponseOutputMessage,
        ResponseOutputText,
    )

    class Recorder(ArkLlmClient):
        def __init__(self):
            self.requests = []

        async def aresponses(self, **kwargs):
            self.requests.append(kwargs)
            if transport_error:
                raise RuntimeError("synthetic transport end")
            return ArkTypeResponse.model_construct(
                id="synthetic",
                model=MODELS[1],
                status="completed",
                output=[
                    ResponseOutputMessage.model_construct(
                        content=[
                            ResponseOutputText.model_construct(text='{"ids":[1,0]}'),
                        ]
                    )
                ],
                incomplete_details=None,
                usage=None,
                error=None,
            )

    client = Recorder()
    model = ArkLlm(
        model="openai/" + MODELS[1],
        llm_client=client,
        thinking={"type": "enabled"},
        reasoning={"effort": "high"},
        previous_response_id="business-chain",
        max_output_tokens=8192,
        fallbacks=["ep-other"],
        enable_responses_cache=True,
    )
    original = copy.deepcopy(model._additional_args)
    cloned = extraction_model(model)
    assert cloned.llm_client is model.llm_client
    selector = ModelEvidenceSelector(model, ContextCompressionConfig())
    result = await selector("q", ("a", "b"), deadline=time.monotonic() + 10)
    assert result == ([] if transport_error else [1, 0]), selector.last_status
    assert len(client.requests) == 1
    packet = client.requests[0]
    assert packet["model"] == MODELS[1]
    assert packet["thinking"] == {"type": "disabled"}
    for key in ("reasoning", "previous_response_id", "tools", "context_management"):
        assert key not in packet
    assert packet["max_output_tokens"] == 256
    assert model._additional_args == original and model.enable_responses_cache


def test_unverified_reasoning_dialect_is_not_silently_sent():
    from veadk.context.auxiliary import disable_thinking
    from veadk.context.budget import ContextBudgetError

    for extra in ({"reasoning_effort": "high"}, {"thinking": {"type": "custom"}}):
        with pytest.raises(ContextBudgetError, match="auxiliary_thinking_unsupported"):
            disable_thinking({"model": "openai/unknown", **extra})
    assert disable_thinking({"model": "openai/gpt-4o"}) == {"model": "openai/gpt-4o"}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["thought", "tool", "truncated", "malformed"])
async def test_selector_rejects_invalid_model_response(monkeypatch, kind):
    from google.adk.models.llm_response import LlmResponse
    from veadk.context.model_reranking import ModelEvidenceSelector

    async def invalid(self, request, stream=False):
        part = types.Part(text='{"ids":[0]}')
        finish = types.FinishReason.STOP
        if kind == "thought":
            part.thought = True
        elif kind == "tool":
            part = types.Part(function_call=types.FunctionCall(name="execute", args={}))
        elif kind == "truncated":
            finish = types.FinishReason.MAX_TOKENS
        else:
            part.text = '{"ids":[99]}'
        yield LlmResponse(
            content=types.Content(role="model", parts=[part]), finish_reason=finish
        )

    monkeypatch.setattr(RetryingLiteLlm, "generate_content_async", invalid)
    model = make_model()
    selector = ModelEvidenceSelector(model, model._context_config)
    assert await selector("q", ("a", "b"), deadline=time.monotonic() + 10) == []
    assert selector.last_status == "fallback"
