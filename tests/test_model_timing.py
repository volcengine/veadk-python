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
from opentelemetry.trace import SpanKind, StatusCode
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
def test_first_output_is_latched_without_usage(
    monkeypatch: pytest.MonkeyPatch, spans: tuple, kind: str
) -> None:
    tracer, exporter = spans
    clock = iter([100, 200, 300])
    monkeypatch.setattr(timing.time, "time_ns", lambda: next(clock))
    with tracer.start_as_current_span("call_llm") as owner:
        with timing.ModelTiming(streaming=True, model="openai/test") as call:
            call.observe(None)
            call.observe(kind)
            call.observe("text")
        assert not owner.attributes
        assert not owner.events
    attempt = exporter.get_finished_spans()[0]
    assert attempt.parent.span_id == owner.context.span_id
    assert attempt.start_time == 100
    assert attempt.kind is SpanKind.CLIENT
    assert (
        attempt.attributes["gen_ai.chat_completions.streaming_time_to_first_token"]
        == 1e-7
    )
    assert attempt.status.status_code is StatusCode.UNSET
    assert not any(key.startswith("veadk.") for key in attempt.attributes)
    assert not attempt.events


@pytest.mark.parametrize("streaming", [False, True])
def test_no_first_token_is_fabricated(spans: tuple, streaming: bool) -> None:
    tracer, exporter = spans
    with tracer.start_as_current_span("call_llm") as owner:
        with timing.ModelTiming(streaming=streaming, model="test") as call:
            if not streaming:
                call.observe("text")
        assert not owner.attributes
    attempt = exporter.get_finished_spans()[0]
    assert attempt.attributes["gen_ai.request.stream"] is streaming
    assert (
        "gen_ai.chat_completions.streaming_time_to_first_token"
        not in attempt.attributes
    )
    assert len(exporter.get_finished_spans()) == 2


@pytest.mark.parametrize(
    "error,error_type",
    [
        (RuntimeError("failed"), "llm_error"),
        (asyncio.CancelledError(), "cancelled"),
        (GeneratorExit(), None),
    ],
)
def test_interrupted_attempt_retains_output_and_ends(
    spans: tuple, error: BaseException, error_type: str | None
) -> None:
    tracer, exporter = spans
    with tracer.start_as_current_span("call_llm"):
        with pytest.raises(type(error)):
            with timing.ModelTiming(streaming=True, model="test") as call:
                call.observe("text")
                raise error
    attempt = exporter.get_finished_spans()[0]
    assert attempt.end_time is not None
    assert "gen_ai.chat_completions.streaming_time_to_first_token" in attempt.attributes
    assert attempt.attributes.get("error.type") == error_type
    assert attempt.status.status_code is (
        StatusCode.ERROR if error_type else StatusCode.UNSET
    )


def test_retry_attempts_have_independent_timestamps(spans: tuple) -> None:
    tracer, exporter = spans
    with tracer.start_as_current_span("call_llm") as owner:
        with pytest.raises(RuntimeError):
            with timing.ModelTiming(streaming=True, model="primary"):
                raise RuntimeError("retry")
        with timing.ModelTiming(streaming=True, model="fallback") as call:
            call.observe("text")
    attempts = [s for s in exporter.get_finished_spans() if s.name == "model_request"]
    assert len(attempts) == 2
    ttft = "gen_ai.chat_completions.streaming_time_to_first_token"
    assert ttft not in attempts[0].attributes
    assert attempts[0].status.status_code is StatusCode.ERROR
    assert ttft in attempts[1].attributes
    assert attempts[1].status.status_code is StatusCode.UNSET
    assert attempts[0].start_time <= attempts[1].start_time
    assert not owner.attributes


@pytest.mark.parametrize("streaming", [True, False])
def test_model_timing_does_not_mutate_owner(spans: tuple, streaming: bool) -> None:
    tracer, _ = spans
    with tracer.start_as_current_span("call_llm") as owner:
        with timing.ModelTiming(streaming=streaming, model="test") as call:
            call.observe("text")
        assert not owner.attributes
        assert not owner.events


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
def test_litellm_delta_classification(delta: dict, expected: str | None) -> None:
    assert timing.litellm_output_type(NS(choices=[NS(delta=delta)])) == expected


def test_litellm_metadata_and_object_shapes() -> None:
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
def test_ark_delta_classification(
    event_type: str, delta: dict, expected: str | None
) -> None:
    assert timing.ark_output_type(NS(type=event_type, delta=delta)) == expected


@pytest.mark.asyncio
async def test_request_context_is_isolated_across_yields_and_tasks(
    spans: tuple,
) -> None:
    tracer, _ = spans

    async def events(expected):
        assert timing.current_request_span() is expected
        assert trace.get_current_span() is expected
        yield expected.name
        await asyncio.sleep(0)
        assert timing.current_request_span() is expected
        yield expected.name

    first, second = tracer.start_span("one"), tracer.start_span("two")
    a = timing.with_request_timing(events(first), first)
    b = timing.with_request_timing(events(second), second)
    assert await asyncio.gather(anext(a), anext(b)) == ["one", "two"]
    assert timing.current_request_span() is None
    assert await asyncio.gather(anext(a), anext(b)) == ["one", "two"]
    assert timing.current_request_span() is None
    await a.aclose()
    await b.aclose()
    first.end()
    second.end()


@pytest.mark.asyncio
async def test_request_context_restored_on_error_and_close(spans: tuple) -> None:
    tracer, _ = spans
    inner, outer = tracer.start_span("inner"), tracer.start_span("outer")
    closed = []

    async def events():
        try:
            yield 1
            raise ValueError("original")
        finally:
            closed.append(timing.current_request_span())

    with timing.bind_request_span(outer):
        wrapped = timing.with_request_timing(events(), inner)
        assert await anext(wrapped) == 1
        assert timing.current_request_span() is outer
        with pytest.raises(ValueError, match="original"):
            await anext(wrapped)
        assert trace.get_current_span() is outer
        assert closed == [inner]
        wrapped = timing.with_request_timing(events(), inner)
        await anext(wrapped)
        await wrapped.aclose()
        assert closed == [inner, inner]
    assert timing.current_request_span() is None
    inner.end()
    outer.end()


@pytest.mark.asyncio
async def test_timed_runner_uses_inherited_or_local_span(spans: tuple) -> None:
    tracer, exporter = spans

    @timing.timed_runner
    async def run(value):
        with timing.ModelTiming(streaming=False, model="test"):
            yield (value, timing.current_request_span())

    result = [e async for e in run("hello")]
    assert result[0][0] == "hello"
    request = result[0][1]
    assert request.name == "runner_request"
    assert request.end_time is not None
    assert exporter.get_finished_spans()[0].parent.span_id == request.context.span_id
    with tracer.start_as_current_span("http_request") as inherited:
        with timing.bind_request_span(inherited):
            generator = run("http")
            assert await anext(generator) == ("http", inherited)
            await generator.aclose()
            assert inherited.is_recording()
    assert timing.current_request_span() is None
    assert (
        len([s for s in exporter.get_finished_spans() if s.name == "runner_request"])
        == 1
    )


@pytest.mark.asyncio
async def test_http_boundary_is_before_body_parsing_and_install_is_idempotent(
    spans: tuple,
) -> None:
    _, exporter = spans
    app = FastAPI()

    @app.post("/run")
    async def run(payload: dict):
        span = timing.current_request_span()
        assert span.name == "http_request" and span.is_recording()
        with timing.ModelTiming(streaming=False, model="test"):
            return {"value": payload["value"]}

    timing.install_request_timing(app)
    timing.install_request_timing(app)
    assert len(app.user_middleware) == 1
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def body():
            request = timing.current_request_span()
            assert request is not None and request.name == "http_request"
            assert request.is_recording()
            yield b'{"value": "hello"}'

        response = await client.post(
            "/run", content=body(), headers={"content-type": "application/json"}
        )
    assert response.json() == {"value": "hello"}
    model, request = exporter.get_finished_spans()
    assert request.kind is SpanKind.SERVER
    assert request.start_time <= model.start_time <= model.end_time <= request.end_time
    assert model.parent.span_id == request.context.span_id
    assert not request.attributes
    assert timing.current_request_span() is None


@pytest.mark.asyncio
async def test_non_http_scopes_and_failures_preserve_context(spans: tuple) -> None:
    _, exporter = spans
    received = []

    async def app(scope, receive, send):
        received.append(timing.current_request_span())
        if scope["type"] == "http":
            raise RuntimeError("original")

    middleware = timing.RequestTimingMiddleware(app)
    await middleware({"type": "lifespan"}, None, None)
    assert received == [None]
    with pytest.raises(RuntimeError, match="original"):
        await middleware({"type": "http"}, None, None)
    assert received[1].name == "http_request"
    assert timing.current_request_span() is None
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["error.type"] == "request_error"
    assert not span.events


@pytest.mark.asyncio
async def test_http_server_error_response_is_recorded(spans: tuple) -> None:
    _, exporter = spans
    sent = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 503, "headers": []})
        await send({"type": "http.response.body", "body": b"unavailable"})

    async def send(message):
        sent.append(message)

    await timing.RequestTimingMiddleware(app)({"type": "http"}, None, send)
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["error.type"] == "http_error"
    assert sent[1]["body"] == b"unavailable"


def test_without_recording_tracer() -> None:
    with trace.use_span(trace.INVALID_SPAN):
        with timing.ModelTiming(streaming=True, model="test") as call:
            call.observe("text")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,error_type",
    [
        (RuntimeError, "request_error"),
        (TimeoutError, "timeout"),
        (asyncio.CancelledError, "cancelled"),
    ],
)
async def test_runner_failure_sets_status_and_releases_context(
    spans: tuple, error: type[BaseException], error_type: str
) -> None:
    _, exporter = spans
    closed = []

    @timing.timed_runner
    async def run():
        try:
            yield 1
            raise error("private")
        finally:
            closed.append(timing.current_request_span())

    events = run()
    assert await anext(events) == 1
    assert timing.current_request_span() is None
    with pytest.raises(error):
        await anext(events)
    request = exporter.get_finished_spans()[0]
    assert request.status.status_code is StatusCode.ERROR
    assert request.attributes["error.type"] == error_type
    assert not request.events
    assert closed[0].get_span_context().span_id == request.context.span_id
    assert timing.current_request_span() is None


@pytest.mark.asyncio
async def test_runner_close_failure_ends_span(spans: tuple) -> None:
    _, exporter = spans

    @timing.timed_runner
    async def run():
        try:
            yield 1
        finally:
            raise RuntimeError("close failed")

    events = run()
    assert await anext(events) == 1
    with pytest.raises(RuntimeError, match="close failed"):
        await events.aclose()
    request = exporter.get_finished_spans()[0]
    assert request.status.status_code is StatusCode.ERROR
    assert request.attributes["error.type"] == "request_error"
    assert timing.current_request_span() is None
