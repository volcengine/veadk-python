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

from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from veadk.tracing.telemetry import timing


@pytest.fixture
def spans(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("timing-test")
    monkeypatch.setattr(timing.trace, "get_tracer", lambda *a, **kw: tracer)
    yield tracer, exporter
    provider.shutdown()


@pytest.mark.parametrize("kind", ["text", "reasoning", "tool_call"])
def test_first_output_is_latched_without_usage(monkeypatch, spans, kind):
    tracer, exporter = spans
    clock = iter([100, 200, 300])
    monkeypatch.setattr(timing.time, "time_ns", lambda: next(clock))
    with timing.bind_request_start(timing.RequestStart(50, "http")):
        with tracer.start_as_current_span("call_llm") as owner:
            with timing.ModelTiming(streaming=True, model="openai/test") as call:
                call.observe(None)
                call.observe(kind)
                call.observe("text")
            assert owner.attributes["veadk.request.start_time_unix_ns"] == 50
            assert owner.attributes["veadk.model.start_time_unix_ns"] == 100
            assert owner.attributes["veadk.model.first_token_time_unix_ns"] == 200
            assert owner.attributes["veadk.model.first_token_type"] == kind
            assert owner.attributes["veadk.model.first_token_status"] == "observed"
            assert len(owner.events) == 1
            assert owner.events[0].timestamp == 200
    attempt = next(
        s for s in exporter.get_finished_spans() if s.name == "model_request"
    )
    assert attempt.parent.span_id == owner.context.span_id
    assert attempt.attributes["veadk.model.request_scope"] == "sdk_request"
    assert attempt.attributes["veadk.model.outcome"] == "completed"
    assert "content" not in str(dict(attempt.attributes))


@pytest.mark.parametrize(
    "streaming,status", [(False, "non_streaming"), (True, "no_output")]
)
def test_no_first_token_is_fabricated(spans, streaming, status):
    tracer, exporter = spans
    with tracer.start_as_current_span("call_llm") as owner:
        with timing.ModelTiming(streaming=streaming, model="test") as call:
            if not streaming:
                call.observe("text")
        assert owner.attributes["veadk.model.first_token_status"] == status
        assert "veadk.model.first_token_time_unix_ns" not in owner.attributes
    assert len(exporter.get_finished_spans()) == 2


@pytest.mark.parametrize(
    "error,outcome",
    [
        (RuntimeError("failed"), "error"),
        (asyncio.CancelledError(), "cancelled"),
        (GeneratorExit(), "cancelled"),
    ],
)
def test_interrupted_attempt_retains_output_and_ends(spans, error, outcome):
    tracer, exporter = spans
    with tracer.start_as_current_span("call_llm"):
        with pytest.raises(type(error)):
            with timing.ModelTiming(streaming=True, model="test") as call:
                call.observe("text")
                raise error
    attempt = exporter.get_finished_spans()[0]
    assert attempt.end_time is not None
    assert attempt.attributes["veadk.model.first_token_status"] == "observed"
    assert attempt.attributes["veadk.model.outcome"] == outcome


def test_retry_attempts_have_independent_timestamps(spans):
    tracer, exporter = spans
    with tracer.start_as_current_span("call_llm") as owner:
        with pytest.raises(RuntimeError):
            with timing.ModelTiming(streaming=True, model="primary"):
                raise RuntimeError("retry")
        with timing.ModelTiming(streaming=True, model="fallback") as call:
            call.observe("text")
    attempts = [s for s in exporter.get_finished_spans() if s.name == "model_request"]
    assert len(attempts) == 2
    assert attempts[0].attributes["veadk.model.first_token_status"] == "no_output"
    assert "veadk.model.first_token_time_unix_ns" not in attempts[0].attributes
    assert attempts[1].attributes["veadk.model.first_token_status"] == "observed"
    assert (
        owner.attributes["veadk.model.start_time_unix_ns"]
        == attempts[1].attributes["veadk.model.start_time_unix_ns"]
    )


@pytest.mark.parametrize(
    "streaming,status", [(True, "unsupported"), (False, "non_streaming")]
)
def test_unsupported_models_do_not_use_invocation_start(spans, streaming, status):
    tracer, _ = spans
    with tracer.start_as_current_span("call_llm") as owner:
        timing.mark_uninstrumented_model(owner, streaming=streaming)
        assert owner.attributes["veadk.model.first_token_status"] == status
        assert "veadk.model.start_time_unix_ns" not in owner.attributes
        assert owner.attributes["veadk.model.streaming"] is streaming
        with timing.ModelTiming(streaming=True, model="test") as call:
            call.observe("text")
        timing.mark_uninstrumented_model(owner, streaming=False)
        assert owner.attributes["veadk.model.first_token_status"] == "observed"


@pytest.mark.parametrize(
    "delta,expected",
    [
        ({}, None),
        ({"role": "assistant"}, None),
        ({"content": ""}, None),
        ({"content": " "}, "text"),
        ({"content": "hello"}, "text"),
        ({"reasoning_content": "think"}, "reasoning"),
        ({"reasoning": "think"}, "reasoning"),
        ({"thinking_blocks": [{"type": "thinking", "thinking": "think"}]}, "reasoning"),
        ({"thinking_blocks": [{"type": "thinking", "signature": "metadata"}]}, None),
        ({"tool_calls": [{"id": "metadata"}]}, None),
        (
            {"tool_calls": [{"function": {"name": "search", "arguments": ""}}]},
            "tool_call",
        ),
        ({"tool_calls": [{"function": {"arguments": "{"}}]}, "tool_call"),
        ({"function_call": {"arguments": "{"}}, "tool_call"),
    ],
)
def test_litellm_delta_classification(delta, expected):
    assert timing.litellm_output_type(NS(choices=[NS(delta=delta)])) == expected


def test_litellm_metadata_and_object_shapes():
    assert timing.litellm_output_type(NS(choices=[])) is None
    assert timing.litellm_output_type(NS(choices=[NS(delta=None)])) is None
    assert (
        timing.litellm_output_type(NS(choices=[NS(delta=NS(content="text"))])) == "text"
    )
    assert (
        timing.litellm_output_type(
            {"choices": [{"delta": {"reasoning_content": "think"}}]}
        )
        == "reasoning"
    )


@pytest.mark.parametrize(
    "event_type,delta,expected",
    [
        ("response.output_text.delta", "hello", "text"),
        ("response.reasoning_summary_text.delta", "think", "reasoning"),
        ("response.reasoning_text.delta", "think", "reasoning"),
        ("response.function_call_arguments.delta", "{", "tool_call"),
        ("response.output_text.delta", "", None),
        ("response.completed", "full", None),
        ("response.output_item.added", "", None),
    ],
)
def test_ark_delta_classification(event_type, delta, expected):
    assert timing.ark_output_type(NS(type=event_type, delta=delta)) == expected


@pytest.mark.asyncio
async def test_request_context_is_isolated_across_yields_and_tasks():
    async def events(expected):
        assert timing.current_request_start() == expected
        yield expected.time_ns
        await asyncio.sleep(0)
        assert timing.current_request_start() == expected
        yield expected.source

    first = timing.RequestStart(1, "runner")
    second = timing.RequestStart(2, "http")
    a = timing.with_request_timing(events(first), first)
    b = timing.with_request_timing(events(second), second)
    assert await asyncio.gather(anext(a), anext(b)) == [1, 2]
    assert timing.current_request_start() is None
    assert await asyncio.gather(anext(a), anext(b)) == ["runner", "http"]
    assert timing.current_request_start() is None
    await a.aclose()
    await b.aclose()


@pytest.mark.asyncio
async def test_request_context_restored_on_error_and_close():
    inner = timing.RequestStart(2, "runner")
    closed = []

    async def events():
        try:
            yield 1
            raise ValueError("original")
        finally:
            closed.append(timing.current_request_start())

    with timing.bind_request_start(timing.RequestStart(1, "http")) as outer:
        wrapped = timing.with_request_timing(events(), inner)
        assert await anext(wrapped) == 1
        assert timing.current_request_start() == outer
        with pytest.raises(ValueError, match="original"):
            await anext(wrapped)
        assert timing.current_request_start() == outer
        assert closed == [inner]
        wrapped = timing.with_request_timing(events(), inner)
        await anext(wrapped)
        await wrapped.aclose()
        assert closed == [inner, inner]
    assert timing.current_request_start() is None


@pytest.mark.asyncio
async def test_timed_runner_uses_inherited_or_local_start(monkeypatch):
    monkeypatch.setattr(timing.time, "time_ns", lambda: 100)

    @timing.timed_runner
    async def run(value):
        yield (value, timing.current_request_start())

    assert [e async for e in run("hello")] == [
        ("hello", timing.RequestStart(100, "runner"))
    ]
    with timing.bind_request_start(timing.RequestStart(50, "http")):
        generator = run("http")
        assert await anext(generator) == ("http", timing.RequestStart(50, "http"))
        await generator.aclose()
    assert timing.current_request_start() is None


@pytest.mark.asyncio
async def test_http_boundary_is_before_body_parsing_and_install_is_idempotent(
    monkeypatch,
):
    monkeypatch.setattr(timing.time, "time_ns", lambda: 100)
    app = FastAPI()

    @app.post("/run")
    async def run(payload: dict):
        start = timing.current_request_start()
        return {
            "start": start.time_ns,
            "source": start.source,
            "value": payload["value"],
        }

    timing.install_request_timing(app)
    timing.install_request_timing(app)
    assert len(app.user_middleware) == 1
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/run", json={"value": "hello"})
    assert response.json() == {"start": 100, "source": "http", "value": "hello"}
    assert timing.current_request_start() is None


@pytest.mark.asyncio
async def test_non_http_scopes_and_failures_preserve_context():
    received = []

    async def app(scope, receive, send):
        received.append(timing.current_request_start())
        if scope["type"] == "http":
            raise RuntimeError("original")

    middleware = timing.RequestTimingMiddleware(app)
    await middleware({"type": "lifespan"}, None, None)
    assert received == [None]
    with pytest.raises(RuntimeError, match="original"):
        await middleware({"type": "http"}, None, None)
    assert received[1].source == "http"
    assert timing.current_request_start() is None


def test_without_recording_tracer():
    with trace.use_span(trace.INVALID_SPAN):
        with timing.ModelTiming(streaming=True, model="test") as call:
            call.observe("text")
        timing.mark_uninstrumented_model(trace.INVALID_SPAN, streaming=True)
