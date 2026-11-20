# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Response-ID contracts using real adapters and stubbed SDK transports."""

import asyncio
import json
from types import SimpleNamespace as NS

import httpx
import pytest
from google.adk.models import Gemini, LlmRequest
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.models import lite_llm as adk_lite_llm
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.genai.models import AsyncModels
from litellm import CustomStreamWrapper, ModelResponse
from litellm.types.utils import ModelResponseStream
from opentelemetry import context as context_api
from opentelemetry import trace as trace_api
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from volcenginesdkarkruntime.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseCreatedEvent,
    ResponseTextDeltaEvent,
)

from veadk.models.ark_llm import ArkLlm, ArkLlmClient
from veadk import Agent
from veadk.config import settings
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.utils.patches import patch_tracer
from veadk.models.retrying_lite_llm import RetryingLiteLlm
from veadk.tracing.telemetry import litellm_response_id as response_ids
from veadk.tracing.telemetry import timing

ID = "gen_ai.response.id"


@pytest.fixture
def tracing(monkeypatch):
    # Restore process-wide patches after every case, including constructors.
    for cls, method in (
        (adk_lite_llm.LiteLLMClient, "acompletion"),
        (AsyncModels, "generate_content"),
        (AsyncModels, "generate_content_stream"),
        (ModelResponse, "__init__"),
        (ModelResponseStream, "__init__"),
        (CustomStreamWrapper, "chunk_creator"),
        (CustomStreamWrapper, "model_response_creator"),
    ):
        monkeypatch.setattr(cls, method, getattr(cls, method))
    monkeypatch.setattr(response_ids, "_patched", False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "true")

    original_send = httpx.AsyncClient.send

    async def reject_network(client, *args, **kwargs):
        if isinstance(client._transport, httpx.MockTransport):
            return await original_send(client, *args, **kwargs)
        raise AssertionError("Response-ID unit tests must not call external services")

    monkeypatch.setattr(httpx.AsyncClient, "send", reject_network)
    provider = TracerProvider()
    monkeypatch.setattr(trace_api, "_TRACER_PROVIDER", provider)
    for key in ("ENABLE_APMPLUS", "ENABLE_COZELOOP", "ENABLE_TLS"):
        monkeypatch.setenv(key, "false")
    monkeypatch.setattr(settings.opentelemetry_config, "inmemory_enabled", True)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("response-id-test")
    monkeypatch.setattr(timing.trace, "get_tracer", lambda *a, **kw: tracer)
    token = context_api.attach(
        context_api.set_value("suppress_language_model_instrumentation", True)
    )
    yield tracer, exporter
    context_api.detach(token)
    provider.shutdown()


def _ark_response(response_id):
    response = Response.model_validate(
        {
            "id": response_id or "fixture-placeholder",
            "created_at": 1,
            "model": "test",
            "status": "completed",
            "object": "response",
            "output": [
                {
                    "id": "message-id",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "OK"}],
                }
            ],
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
        }
    )
    response.id = response_id
    return response


def _gemini_response(response_id, *, final=False):
    return types.GenerateContentResponse(
        response_id=response_id,
        candidates=[
            types.Candidate(
                content=types.ModelContent(parts=[types.Part(text="OK")]),
                finish_reason="STOP" if final else None,
            )
        ],
    )


def _install_transport(
    monkeypatch, protocol, stream, response_id, closed, terminal=None, calls=None
):
    async def chunks():
        try:
            if protocol == "chat":
                yield ModelResponseStream(
                    id=response_id,
                    choices=[{"delta": {"content": "OK"}, "index": 0}],
                )
            elif protocol == "ark":
                yield ResponseCreatedEvent(
                    type="response.created", response=_ark_response(response_id)
                )
                yield ResponseTextDeltaEvent(
                    type="response.output_text.delta",
                    delta="OK",
                    item_id="message-id",
                    output_index=0,
                    content_index=0,
                )
            else:
                yield _gemini_response(response_id)
            if terminal is not None:
                raise terminal
            if protocol == "chat":
                # No provider ID on subsequent deltas; LiteLLM synthesizes one.
                yield ModelResponseStream(
                    choices=[{"delta": {}, "index": 0, "finish_reason": "stop"}]
                )
            elif protocol == "ark":
                yield ResponseCompletedEvent(
                    type="response.completed", response=_ark_response(response_id)
                )
            else:
                yield types.GenerateContentResponse(
                    candidates=[types.Candidate(finish_reason="STOP")]
                )
        finally:
            closed.append(True)

    async def complete(*args, **kwargs):
        if calls is not None:
            calls.append(True)
        if stream:
            iterator = chunks()
            if protocol == "ark":
                return _ArkStream(iterator)
            return iterator
        if protocol == "chat":
            return ModelResponse(
                id=response_id,
                choices=[
                    {
                        "message": {"role": "assistant", "content": "OK"},
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
            )
        if protocol == "ark":
            return _ark_response(response_id)
        return _gemini_response(response_id, final=True)

    if protocol == "chat":
        ensure = getattr(adk_lite_llm, "_ensure_litellm_imported", None)
        if ensure is not None:
            ensure()
        monkeypatch.setattr(adk_lite_llm, "acompletion", complete)
        model = RetryingLiteLlm(model="openai/test", api_key="test-key")
    elif protocol == "ark":
        monkeypatch.setattr(ArkLlmClient, "aresponses", complete)
        model = ArkLlm(model="openai/test", api_key="test-key")
    else:
        method = "_generate_content_stream" if stream else "_generate_content"
        monkeypatch.setattr(AsyncModels, method, complete)
        model = Gemini(model="gemini-2.5-flash")
    response_ids.register()
    return model


class _ArkStream:
    def __init__(self, iterator):
        self.iterator = iterator

    def __aiter__(self):
        return self.iterator

    async def close(self):
        await self.iterator.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["chat", "ark", "gemini"])
@pytest.mark.parametrize("stream", [False, True])
async def test_six_adapter_paths_preserve_provider_id(
    monkeypatch, tracing, protocol, stream
):
    """REQ-001/002/008: raw ID survives aggregation without altering output."""
    tracer, exporter = tracing
    closed = []
    expected = f"provider-{protocol}-{stream}"
    model = _install_transport(monkeypatch, protocol, stream, expected, closed)
    request = LlmRequest(
        model=model.model,
        contents=[types.UserContent(parts=[types.Part(text="hello")])],
    )
    with tracer.start_as_current_span("invocation") as parent:
        with tracer.start_as_current_span("call_llm"):
            responses = [
                r async for r in model.generate_content_async(request, stream=stream)
            ]
    spans = exporter.get_finished_spans()
    owner = next(s for s in spans if s.name == "call_llm")
    assert owner.attributes.get(ID) == expected
    assert ID not in parent.attributes
    assert any(p.text == "OK" for r in responses if r.content for p in r.content.parts)
    if stream:
        assert closed == [True]
    for attempt in (s for s in spans if s.name == "model_request"):
        assert attempt.attributes.get(ID) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["chat", "ark", "gemini"])
@pytest.mark.parametrize(
    "terminal", [RuntimeError("stream failed"), asyncio.CancelledError()]
)
async def test_early_id_survives_stream_failure(
    monkeypatch, tracing, protocol, terminal
):
    """REQ-002/003: observe the ID before consuming a terminal event."""
    tracer, exporter = tracing
    closed = []
    model = _install_transport(
        monkeypatch, protocol, True, "early-id", closed, terminal
    )
    request = LlmRequest(
        model=model.model,
        contents=[types.UserContent(parts=[types.Part(text="hello")])],
    )
    with tracer.start_as_current_span("call_llm") as owner:
        generator = model.generate_content_async(request, stream=True)
        await anext(generator)
        assert owner.attributes.get(ID) == "early-id"
        with pytest.raises(type(terminal)):
            await anext(generator)
        await generator.aclose()
    assert closed == [True]
    assert (
        next(
            s for s in exporter.get_finished_spans() if s.name == "call_llm"
        ).attributes[ID]
        == "early-id"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["chat", "ark", "gemini"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("response_id", [None, "", "   "])
async def test_missing_id_is_not_synthesized(
    monkeypatch, tracing, protocol, stream, response_id
):
    """REQ-004: SDK-generated, empty and missing IDs are not response IDs."""
    tracer, exporter = tracing
    model = _install_transport(monkeypatch, protocol, stream, response_id, [])
    request = LlmRequest(
        model=model.model,
        contents=[types.UserContent(parts=[types.Part(text="hello")])],
    )
    with tracer.start_as_current_span("call_llm"):
        assert [r async for r in model.generate_content_async(request, stream=stream)]
    assert all(ID not in s.attributes for s in exporter.get_finished_spans())


@pytest.mark.asyncio
async def test_stream_is_bound_to_producer_not_consumer(monkeypatch, tracing):
    """REQ-005: advancing under another context must not redirect the ID."""
    tracer, exporter = tracing
    ensure = getattr(adk_lite_llm, "_ensure_litellm_imported", None)
    if ensure is not None:
        ensure()

    async def complete(*args, **kwargs):
        async def chunks():
            await asyncio.sleep(0)
            yield ModelResponseStream(id=kwargs["model"])

        return chunks()

    monkeypatch.setattr(adk_lite_llm, "acompletion", complete)
    response_ids.register()
    client = adk_lite_llm.LiteLLMClient()
    owners, streams = [], []
    for name in ("one", "two"):
        owner = tracer.start_span("call_llm")
        owners.append(owner)
        with timing.trace.use_span(owner, end_on_exit=False):
            streams.append(await client.acompletion(name, [], [], stream=True))
    with tracer.start_as_current_span("consumer") as consumer:
        await asyncio.gather(*(anext(s) for s in streams))
        await asyncio.gather(*(s.aclose() for s in streams))
    for owner in owners:
        owner.end()
    assert [s.attributes.get(ID) for s in owners] == ["one", "two"]
    assert ID not in consumer.attributes
    assert len(exporter.get_finished_spans()) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("successful_id", ["fallback-id", None])
async def test_ark_fallback_separates_failed_and_delivered_ids(
    monkeypatch, tracing, successful_id
):
    """REQ-006: a failed created event is retained only by its attempt."""
    tracer, exporter = tracing
    model = ArkLlm(
        model="openai/primary", fallbacks=["openai/fallback"], api_key="test-key"
    )
    calls = []
    closed = []

    async def complete(self, **kwargs):
        calls.append(kwargs["model"])

        async def chunks():
            try:
                if len(calls) == 1:
                    yield ResponseCreatedEvent(
                        type="response.created", response=_ark_response("failed-id")
                    )
                    raise RuntimeError("failure before output")
                yield ResponseCreatedEvent(
                    type="response.created", response=_ark_response(successful_id)
                )
                yield ResponseCompletedEvent(
                    type="response.completed", response=_ark_response(successful_id)
                )
            finally:
                closed.append(True)

        return _ArkStream(chunks())

    monkeypatch.setattr(ArkLlmClient, "aresponses", complete)
    response_ids.register()
    with tracer.start_as_current_span("call_llm"):
        responses = [
            r
            async for r in model._generate_content_with_fallbacks(
                {"input": []}, stream=True
            )
        ]
    spans = exporter.get_finished_spans()
    owner = next(s for s in spans if s.name == "call_llm")
    attempts = [s for s in spans if s.name == "model_request"]
    assert owner.attributes.get(ID) == successful_id
    assert attempts[0].attributes[ID] == "failed-id"
    assert attempts[0].status.status_code.name == "ERROR"
    assert attempts[1].attributes.get(ID) == successful_id
    assert responses[-1].interaction_id == successful_id
    assert calls == ["primary", "fallback"]
    assert closed == [True, True]


@pytest.mark.asyncio
async def test_registration_and_missing_id_next_call(monkeypatch, tracing):
    """REQ-004/007: no double calls and no ID carried to the next request."""
    tracer, exporter = tracing
    calls = []
    ensure = getattr(adk_lite_llm, "_ensure_litellm_imported", None)
    if ensure is not None:
        ensure()

    async def complete(*args, **kwargs):
        calls.append(True)
        return ModelResponse(id="first-id" if len(calls) == 1 else None)

    monkeypatch.setattr(adk_lite_llm, "acompletion", complete)
    response_ids.register()
    first = adk_lite_llm.LiteLLMClient.acompletion
    response_ids.register()
    assert adk_lite_llm.LiteLLMClient.acompletion is first
    client = adk_lite_llm.LiteLLMClient()
    for _ in range(2):
        with tracer.start_as_current_span("call_llm"):
            await client.acompletion("test", [], [])
    assert calls == [True, True]
    assert [s.attributes.get(ID) for s in exporter.get_finished_spans()] == [
        "first-id",
        None,
    ]


def test_generated_id_marker_does_not_change_serialization(tracing):
    response_ids.register()
    for cls in (ModelResponse, ModelResponseStream):
        response = cls()
        assert response.id
        assert response_ids._GENERATED_ID not in response.model_dump()
        # A real provider may also use UUIDs; provenance, not format, decides.
        provider_id = "e5e81c15-50a7-42c6-82a0-4bd154b1f72b"
        response.id = provider_id
        tracer, _ = tracing
        with tracer.start_as_current_span("call_llm") as owner:
            response_ids.ResponseIdRecorder().observe(response)
        assert owner.attributes[ID] == provider_id


@pytest.mark.parametrize("provider_id", [None, "", "provider-id"])
@pytest.mark.parametrize("stream", [False, True])
def test_litellm_normalization_distinguishes_generated_ids(
    tracing, provider_id, stream
):
    """REQ-004: exercise SDK conversion, including a different request ID."""
    from litellm import CustomStreamWrapper
    from litellm.utils import convert_to_model_response_object

    response_ids.register()
    if stream:
        wrapper = CustomStreamWrapper(
            completion_stream=iter([]),
            model="openai/test",
            custom_llm_provider="openai",
            logging_obj=NS(model_call_details={"custom_llm_provider": "openai"}),
            _response_headers={"x-request-id": "request-id"},
        )
        from openai.types.chat import ChatCompletionChunk

        raw = ChatCompletionChunk(
            id="fixture-placeholder",
            created=1,
            model="fixture",
            object="chat.completion.chunk",
            choices=[{"index": 0, "delta": {"content": "OK"}, "finish_reason": None}],
        )
        raw.id = provider_id
        response = wrapper.chunk_creator(raw)
    else:
        response = convert_to_model_response_object(
            response_object={
                "id": provider_id,
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "OK"},
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
            },
            model_response_object=ModelResponse(),
            hidden_params={"headers": {"x-request-id": "request-id"}},
        )
    tracer, _ = tracing
    with tracer.start_as_current_span("call_llm") as owner:
        response_ids.ResponseIdRecorder().observe(response)
    assert owner.attributes.get(ID) == (provider_id or None)


@pytest.mark.parametrize("stream", [False, True])
def test_ark_chat_prefers_x_request_id_over_body_id(tracing, stream):
    """REQ-009: Ark chat correlation follows the response header request ID."""
    from litellm import CustomStreamWrapper
    from litellm.utils import convert_to_model_response_object

    response_ids.register()
    headers = {"x-request-id": "ark-header-request-id"}
    api_base = "https://ark.cn-beijing.volces.com/api/v3/"
    if stream:
        wrapper = CustomStreamWrapper(
            completion_stream=iter([]),
            model="openai/test",
            custom_llm_provider="openai",
            logging_obj=NS(
                model_call_details={
                    "custom_llm_provider": "openai",
                    "litellm_params": {"api_base": api_base},
                }
            ),
            _response_headers=headers,
        )
        from openai.types.chat import ChatCompletionChunk

        raw = ChatCompletionChunk(
            id="body-id",
            created=1,
            model="fixture",
            object="chat.completion.chunk",
            choices=[{"index": 0, "delta": {"content": "OK"}, "finish_reason": None}],
        )
        response = wrapper.chunk_creator(raw)
    else:
        response = convert_to_model_response_object(
            response_object={
                "id": "body-id",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "OK"},
                        "index": 0,
                        "finish_reason": "stop",
                    }
                ],
            },
            model_response_object=ModelResponse(),
            hidden_params={"headers": headers, "api_base": api_base},
        )
    tracer, _ = tracing
    with tracer.start_as_current_span("call_llm") as owner:
        response_ids.ResponseIdRecorder().observe(response)
    assert owner.attributes[ID] == "ark-header-request-id"


def test_non_ark_chat_keeps_body_id_when_x_request_id_exists(tracing):
    """REQ-009: generic OpenAI-compatible services keep response-body IDs."""
    from litellm.utils import convert_to_model_response_object

    response_ids.register()
    response = convert_to_model_response_object(
        response_object={
            "id": "body-id",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "OK"},
                    "index": 0,
                    "finish_reason": "stop",
                }
            ],
        },
        model_response_object=ModelResponse(),
        hidden_params={
            "headers": {"x-request-id": "non-ark-header-request-id"},
            "api_base": "https://model.test/v1",
        },
    )
    tracer, _ = tracing
    with tracer.start_as_current_span("call_llm") as owner:
        response_ids.ResponseIdRecorder().observe(response)
    assert owner.attributes[ID] == "body-id"


@pytest.mark.parametrize("enabled", [False, True])
def test_no_tracer_or_parent_span_is_not_annotated(monkeypatch, tracing, enabled):
    """REQ-007: collection neither creates spans nor annotates invocation."""
    tracer, exporter = tracing
    monkeypatch.setattr(response_ids, "_patched", enabled)
    with tracer.start_as_current_span("invocation") as parent:
        response_ids.ResponseIdRecorder().observe(
            NS(id="provider-id", _request_id="request-id")
        )
    response_ids.ResponseIdRecorder().observe(NS(id="provider-id"))
    assert ID not in parent.attributes
    assert len(exporter.get_finished_spans()) == 1


@pytest.mark.asyncio
async def test_unrecorded_call_returns_original_sdk_stream(monkeypatch, tracing):
    """REQ-007: installed patches are a no-op without a recording call span."""

    async def chunks():
        yield ModelResponseStream(id="provider-id")

    original_stream = chunks()
    ensure = getattr(adk_lite_llm, "_ensure_litellm_imported", None)
    if ensure is not None:
        ensure()

    async def complete(*args, **kwargs):
        return original_stream

    monkeypatch.setattr(adk_lite_llm, "acompletion", complete)
    response_ids.register()
    context = trace_api.SpanContext(trace_id=1, span_id=1, is_remote=False)
    with trace_api.use_span(trace_api.NonRecordingSpan(context)):
        returned = await adk_lite_llm.LiteLLMClient().acompletion(
            "test", [], [], stream=True
        )
    assert returned is original_stream
    await returned.aclose()
    assert not tracing[1].get_finished_spans()


@pytest.mark.asyncio
async def test_tool_rounds_in_concurrent_sessions_keep_distinct_ids(
    monkeypatch, tracing
):
    """REQ-005/008: real Tool round trips must keep Session and ID ownership."""
    _, exporter = tracing
    ensure = getattr(adk_lite_llm, "_ensure_litellm_imported", None)
    if ensure is not None:
        ensure()
    calls = []

    async def complete(*args, **kwargs):
        await asyncio.sleep(0)
        messages = kwargs["messages"]
        session = next(m["content"] for m in messages if m["role"] == "user")
        has_tool_response = any(m["role"] == "tool" for m in messages)
        response_id = f"provider-{session}-{has_tool_response}"
        calls.append(response_id)
        message = (
            {"role": "assistant", "content": "OK"}
            if has_tool_response
            else {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "tool-call-id",
                        "type": "function",
                        "function": {"name": "echo", "arguments": "{}"},
                    }
                ],
            }
        )
        return ModelResponse(
            id=response_id,
            choices=[
                {
                    "message": message,
                    "index": 0,
                    "finish_reason": "stop" if has_tool_response else "tool_calls",
                }
            ],
        )

    def echo() -> str:
        return "ok"

    monkeypatch.setattr(adk_lite_llm, "acompletion", complete)
    tracer = OpentelemetryTracer()
    patch_tracer()
    runner = InMemoryRunner(
        app_name="response-id-test",
        agent=Agent(
            name="tool_id_agent",
            model=RetryingLiteLlm(model="openai/test", api_key="test-key"),
            model_api_key="test-key",
            tools=[echo],
            tracers=[tracer],
        ),
    )

    async def run(session):
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id="test-user", session_id=session
        )
        return [
            e
            async for e in runner.run_async(
                user_id="test-user",
                session_id=session,
                new_message=types.UserContent(parts=[types.Part(text=session)]),
            )
        ]

    try:
        results = await asyncio.gather(run("one"), run("two"))
    finally:
        await runner.close()
    assert len(calls) == 4
    assert all(
        any(p.text == "OK" for e in events if e.content for p in e.content.parts)
        for events in results
    )
    for session in ("one", "two"):
        owners = [
            s
            for s in exporter.get_finished_spans()
            if s.name == "call_llm" and s.attributes["gen_ai.session.id"] == session
        ]
        assert {s.attributes[ID] for s in owners} == {
            f"provider-{session}-False",
            f"provider-{session}-True",
        }
        assert len(owners) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["chat", "ark", "gemini"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("capture_content", [False, True])
async def test_runner_records_id_on_owning_call_span(
    monkeypatch, tracing, protocol, stream, capture_content
):
    """REQ-001/005/007: real Agent/Runner and OTel with stubbed SDK I/O."""
    _, exporter = tracing
    monkeypatch.setattr(settings.opentelemetry_config, "trace_content", capture_content)
    expected = f"runner-{protocol}-{stream}"
    calls, closed = [], []
    model = _install_transport(
        monkeypatch, protocol, stream, expected, closed, calls=calls
    )
    tracer = OpentelemetryTracer()
    OpentelemetryTracer()  # Reinitialization must not duplicate SDK calls.
    patch_tracer()
    runner = InMemoryRunner(
        app_name="response-id-test",
        agent=Agent(
            name="response_id_agent",
            model=model,
            model_api_key="test-key",
            tracers=[tracer],
        ),
    )
    try:
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id="test-user", session_id="id-session"
        )
        events = [
            event
            async for event in runner.run_async(
                user_id="test-user",
                session_id="id-session",
                new_message=types.UserContent(parts=[types.Part(text="hello")]),
                run_config=RunConfig(
                    streaming_mode=StreamingMode.SSE if stream else StreamingMode.NONE
                ),
            )
        ]
    finally:
        await runner.close()
    model_spans = [s for s in exporter.get_finished_spans() if s.name == "call_llm"]
    assert len(model_spans) == 1
    assert model_spans[0].attributes[ID] == expected
    assert model_spans[0].attributes["gen_ai.session.id"] == "id-session"
    assert not any(
        ID in s.attributes
        for s in exporter.get_finished_spans()
        if s.name.startswith("invocation")
    )
    assert any(p.text == "OK" for e in events if e.content for p in e.content.parts)
    assert calls == [True]
    if stream:
        assert closed == [True]


@pytest.mark.asyncio
async def test_litellm_retry_clears_failed_id_when_success_has_no_id(
    monkeypatch, tracing
):
    """REQ-006: a pre-output 429 starts a fresh SDK attempt."""
    from veadk.models import retrying_lite_llm

    tracer, exporter = tracing
    ensure = getattr(adk_lite_llm, "_ensure_litellm_imported", None)
    if ensure is not None:
        ensure()
    calls, closed = [], []

    class QuotaError(RuntimeError):
        status_code = 429

    async def complete(*args, **kwargs):
        calls.append(True)

        async def chunks():
            try:
                if len(calls) == 1:
                    yield ModelResponseStream(
                        id="failed-chat-id",
                        choices=[{"delta": {"role": "assistant"}, "index": 0}],
                    )
                    raise QuotaError("quota race")
                yield ModelResponseStream(
                    choices=[
                        {
                            "delta": {"content": "OK"},
                            "index": 0,
                            "finish_reason": "stop",
                        }
                    ]
                )
            finally:
                closed.append(True)

        return chunks()

    monkeypatch.setattr(adk_lite_llm, "acompletion", complete)
    monkeypatch.setattr(retrying_lite_llm, "_retry_delay_seconds", lambda error: 0)
    response_ids.register()
    model = RetryingLiteLlm(model="openai/test", api_key="test-key")
    request = LlmRequest(
        model=model.model,
        contents=[types.UserContent(parts=[types.Part(text="hello")])],
    )
    with tracer.start_as_current_span("call_llm") as owner:
        responses = [
            r async for r in model.generate_content_async(request, stream=True)
        ]
    attempts = [s for s in exporter.get_finished_spans() if s.name == "model_request"]
    assert ID not in owner.attributes
    assert attempts[0].attributes[ID] == "failed-chat-id"
    assert ID not in attempts[1].attributes
    assert len(responses) > 0
    assert calls == closed == [True, True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_id,retry,capture_content,use_timing",
    [
        (None, False, False, True),
        (None, False, True, True),
        (None, True, False, True),
        ("e5e81c15-50a7-42c6-82a0-4bd154b1f72b", False, False, True),
        ("chatcmpl-real-provider-id", False, False, True),
        (None, False, False, False),
        ("e5e81c15-50a7-42c6-82a0-4bd154b1f72b", False, False, False),
    ],
    ids=[
        "chat_missing_stream_0",
        "chat_missing_stream_1",
        "chat_retry_noid_stream_0",
        "real_uuid",
        "real_chatcmpl",
        "adk_litellm_missing",
        "adk_litellm_uuid",
    ],
)
@pytest.mark.parametrize("terminal", ["finish_usage", "usage_only", "synthetic_stop"])
async def test_real_chat_conversion_preserves_id_source(
    monkeypatch, tracing, provider_id, retry, capture_content, use_timing, terminal
):
    """F-001 / REQ-004/006: consume real SDK conversion through the final chunk."""
    from openai import AsyncOpenAI

    _, exporter = tracing
    monkeypatch.setattr(settings.opentelemetry_config, "trace_content", capture_content)
    requests = []
    responses = []

    def respond(request):
        requests.append(json.loads(request.content))
        if retry and len(requests) == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "0"},
                json={
                    "error": {
                        "message": "quota fixture",
                        "type": "rate_limit_error",
                        "code": "rate_limit_exceeded",
                    }
                },
            )
        events = [
            {
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "fixture",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "OK"},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "fixture",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        ]
        if provider_id is not None:
            events[0]["id"] = provider_id
        if terminal == "usage_only":
            events[1]["choices"] = []
        elif terminal == "synthetic_stop":
            events.pop()
        payload = (
            "".join("data: " + json.dumps(e) + "\n\n" for e in events)
            + "data: [DONE]\n\n"
        )
        response = httpx.Response(
            200,
            headers={
                "content-type": "text/event-stream",
                "x-request-id": "different-request-id",
            },
            content=payload.encode(),
        )
        responses.append(response)
        return response

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://model.test/v1",
        http_client=http_client,
        max_retries=0,
    )
    model_class = RetryingLiteLlm if use_timing else adk_lite_llm.LiteLlm
    model = model_class(model="openai/fixture", client=client, num_retries=0)
    tracer = OpentelemetryTracer()
    patch_tracer()
    runner = InMemoryRunner(
        app_name="response-id-test",
        agent=Agent(
            name="chat_conversion_agent",
            model=model,
            model_api_key="test-key",
            tracers=[tracer],
        ),
    )
    try:
        await runner.session_service.create_session(
            app_name=runner.app_name,
            user_id="test-user",
            session_id="conversion-session",
        )
        events = [
            e
            async for e in runner.run_async(
                user_id="test-user",
                session_id="conversion-session",
                new_message=types.UserContent(parts=[types.Part(text="hello")]),
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            )
        ]
    finally:
        await runner.close()
        await client.close()
    spans = exporter.get_finished_spans()
    owners = [s for s in spans if s.name == "call_llm"]
    attempts = [s for s in spans if s.name == "model_request"]
    assert len(owners) == 1
    assert len(attempts) == ((2 if retry else 1) if use_timing else 0)
    assert len(requests) == (2 if retry else 1)
    assert any(p.text == "OK" for e in events if e.content for p in e.content.parts)
    assert owners[0].attributes.get(ID) == provider_id
    if attempts:
        assert attempts[-1].attributes.get(ID) == provider_id
    if provider_id is None:
        assert all(ID not in s.attributes for s in owners + attempts)
    if retry:
        assert attempts[0].status.status_code.name == "ERROR"
    assert all(r.is_closed for r in responses)


@pytest.mark.asyncio
async def test_raw_chat_id_is_recorded_before_output_and_cancellation(
    monkeypatch, tracing
):
    """REQ-002/003: a dropped role-only chunk still carries provider provenance."""
    from openai import AsyncOpenAI

    tracer, exporter = tracing
    blocked = asyncio.Event()
    release = asyncio.Event()
    closed = []

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            raw = {
                "id": "early-raw-id",
                "created": 1,
                "model": "fixture",
                "object": "chat.completion.chunk",
                "choices": [
                    {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
                ],
            }
            yield ("data: " + json.dumps(raw) + "\n\n").encode()
            blocked.set()
            await release.wait()

        async def aclose(self):
            closed.append(True)

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Body()
            )
        )
    )
    client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://model.test/v1",
        http_client=http_client,
        max_retries=0,
    )
    model = RetryingLiteLlm(model="openai/fixture", client=client, num_retries=0)
    response_ids.register()
    request = LlmRequest(
        model=model.model,
        contents=[types.UserContent(parts=[types.Part(text="hello")])],
    )
    try:
        with tracer.start_as_current_span("call_llm") as owner:
            generator = model.generate_content_async(request, stream=True)
            pending = asyncio.create_task(anext(generator))
            try:
                await asyncio.wait_for(blocked.wait(), timeout=5)
                assert not pending.done()
                assert owner.attributes[ID] == "early-raw-id"
            finally:
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
                await generator.aclose()
    finally:
        await client.close()
    attempts = [s for s in exporter.get_finished_spans() if s.name == "model_request"]
    assert len(attempts) == 1
    assert attempts[0].attributes[ID] == owner.attributes[ID] == "early-raw-id"
    assert attempts[0].attributes["error.type"] == "cancelled"
    assert closed == [True]


@pytest.mark.parametrize(
    "provider_id",
    [None, "e5e81c15-50a7-42c6-82a0-4bd154b1f72b", "chatcmpl-real-provider-id"],
)
def test_sdk_parser_and_rebuild_keep_stream_provenance(tracing, provider_id):
    """F-001: intermediate SDK synthesis is not a raw provider ID."""
    from litellm.llms.openai.chat.gpt_transformation import (
        OpenAIChatCompletionStreamingHandler,
    )

    response_ids.register()
    wrapper = CustomStreamWrapper(
        completion_stream=iter([]),
        model="openai/test",
        custom_llm_provider="openai",
        logging_obj=NS(model_call_details={"custom_llm_provider": "openai"}),
    )
    # The official parser can itself produce ModelResponseStream.id before the
    # raw chunk reaches CustomStreamWrapper; preserve that negative provenance.
    parser = OpenAIChatCompletionStreamingHandler.__new__(
        OpenAIChatCompletionStreamingHandler
    )
    raw = parser.chunk_parser(
        {
            "id": provider_id,
            "created": 1,
            "model": "fixture",
            "choices": [
                {"index": 0, "delta": {"content": "OK"}, "finish_reason": None}
            ],
        }
    )
    wrapper.chunk_creator(raw)
    tail = parser.chunk_parser(
        {
            "created": 1,
            "model": "fixture",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )
    normalized = wrapper.chunk_creator(tail)
    serialized = normalized.model_dump()
    assert response_ids._PROVIDER_ID not in serialized
    assert response_ids._GENERATED_ID not in serialized
    rebuilt = wrapper.model_response_creator(
        chunk=serialized, hidden_params=normalized._hidden_params
    )
    tracer, _ = tracing
    for response in (normalized, rebuilt, rebuilt.model_copy(deep=True)):
        with tracer.start_as_current_span("call_llm") as owner:
            response_ids.ResponseIdRecorder().observe(response)
        assert owner.attributes.get(ID) == provider_id
