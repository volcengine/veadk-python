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

"""Contract tests for SDK-receipt TPOT and existing model behavior.

Required when upgrading LiteLLM or changing its allowed version range:
    uv run --extra dev pytest tests/test_model_tpot.py

Run against the target version and newly allowed range boundaries. Dependency
resolution alone cannot detect changes to SDK-retained chunks and finish state,
which can silently omit TPOT. Unit Tests CI includes this file for dependency
changes; keep it in that selection.
"""

from types import SimpleNamespace as NS

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from veadk.tracing.telemetry import portal_metrics, timing

TPOT = portal_metrics.Meters.LLM_STREAMING_TIME_PER_OUTPUT_TOKEN
TTFT = portal_metrics.Meters.LLM_STREAMING_TIME_TO_FIRST_TOKEN


@pytest.fixture
def recorded(monkeypatch):
    exporter = InMemorySpanExporter()
    traces = TracerProvider()
    traces.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(timing.trace, "get_tracer", traces.get_tracer)
    reader = InMemoryMetricReader()
    metrics = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(portal_metrics.metrics_api, "get_meter", metrics.get_meter)
    recorder = portal_metrics.PortalMetricRecorder("tpot-test")
    monkeypatch.setattr(portal_metrics, "portal_metric_recorder", recorder)
    clock = NS(now=0)
    monkeypatch.setattr(timing.time, "monotonic_ns", lambda: clock.now)
    yield NS(spans=exporter, reader=reader, clock=clock, recorder=recorder)
    traces.shutdown()
    metrics.shutdown()


def points(recorded, name=TPOT):
    data = recorded.reader.get_metrics_data()
    return (
        [
            point
            for resource in data.resource_metrics
            if data
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == name
            for point in metric.data.data_points
        ]
        if data
        else []
    )


def outputs(call, recorded):
    call.observe("text")
    recorded.clock.now = 990_000_000
    call.observe("text")


def test_tpot_excludes_usage_and_cleanup_tail_and_records_once(recorded):
    with timing.ModelTiming(streaming=True, model="test") as call:
        outputs(call, recorded)
        recorded.clock.now = 10_000_000_000
        call.observe(None)
        call.complete(100)
        assert not points(recorded)
    call.__exit__(None, None, None)
    call.observe("text")
    assert len(recorded.spans.get_finished_spans()) == 1
    span = recorded.spans.get_finished_spans()[0]
    assert span.attributes[TPOT] == pytest.approx(0.01)
    assert TTFT in span.attributes
    [point] = points(recorded)
    assert point.count == 1 and point.sum == pytest.approx(0.01)
    assert dict(point.attributes) == {
        "gen_ai.request.model": "test",
        "gen_ai.operation.name": "chat",
    }


@pytest.mark.parametrize("tokens", [None, 0, 1, -1, True, "100", 100.0])
def test_invalid_counts_do_not_fabricate_tpot(recorded, tokens):
    with timing.ModelTiming(streaming=True, model="test") as call:
        outputs(call, recorded)
        call.complete(tokens)
    assert not points(recorded)
    assert TPOT not in recorded.spans.get_finished_spans()[0].attributes


@pytest.mark.parametrize("count", [0, 1])
def test_insufficient_deltas_omit_tpot(recorded, count):
    with timing.ModelTiming(streaming=True, model="test") as call:
        for _ in range(count):
            call.observe("text")
        call.complete(100)
    assert not points(recorded)


@pytest.mark.parametrize(
    "mode",
    [
        "nonstream",
        "no_terminal",
        "error",
        "cancel",
        "close",
        "duplicate",
        "late_output",
        "clock_backwards",
    ],
)
def test_terminal_and_clock_boundaries_keep_ttft(recorded, mode):
    import asyncio

    call = timing.ModelTiming(streaming=mode != "nonstream", model="test")
    outputs(call, recorded)
    if mode != "no_terminal":
        call.complete(100)
    if mode == "duplicate":
        call.complete(100)
    if mode == "late_output":
        call.observe("text")
    if mode == "clock_backwards":
        recorded.clock.now = -1
        call.observe("text")
    error = {
        "error": RuntimeError("private"),
        "cancel": asyncio.CancelledError(),
        "close": GeneratorExit(),
    }.get(mode)
    call.__exit__(type(error) if error else None, error, None)
    assert not points(recorded)
    span = recorded.spans.get_finished_spans()[0]
    assert (TTFT in span.attributes) is (mode != "nonstream")
    if mode in {"error", "cancel"}:
        assert span.status.status_code.name == "ERROR"


def test_measured_zero_is_valid(recorded):
    with timing.ModelTiming(streaming=True, model="test") as call:
        call.observe("text")
        call.observe("tool_call")
        call.complete(2)
    assert points(recorded)[0].sum == 0


@pytest.mark.parametrize("component", ["clock", "span", "recorder", "histogram"])
def test_new_telemetry_failures_do_not_replace_output(recorded, monkeypatch, component):
    def fail(*args, **kwargs):
        raise RuntimeError("sensitive backend detail")

    with timing.ModelTiming(streaming=True, model="test") as call:
        if component == "clock":
            monkeypatch.setattr(timing.time, "monotonic_ns", fail)
        outputs(call, recorded)
        call.complete(100)
        if component == "span":
            monkeypatch.setattr(call.span, "set_attribute", fail)
        elif component == "recorder":
            monkeypatch.setattr(recorded.recorder, "record_model_tpot", fail)
        elif component == "histogram":
            monkeypatch.setattr(
                recorded.recorder.streaming_time_per_output_token, "record", fail
            )
    assert recorded.spans.get_finished_spans()[0].end_time
    assert not points(recorded)


def test_metrics_do_not_require_sampled_trace(recorded, monkeypatch):
    from opentelemetry.trace import NoOpTracerProvider

    monkeypatch.setattr(timing.trace, "get_tracer", NoOpTracerProvider().get_tracer)
    with timing.ModelTiming(streaming=True, model="test") as call:
        outputs(call, recorded)
        call.complete(100)
    assert not recorded.spans.get_finished_spans()
    assert points(recorded)[0].count == 1


@pytest.mark.parametrize(
    "details,seen,expected",
    [
        ({}, False, 100),
        ({"reasoning_tokens": 10}, True, 100),
        ({"reasoning_tokens": 10}, False, None),
        ({"reasoning_tokens": -1}, True, None),
        ({"reasoning_tokens": 101}, True, None),
        ({"reasoning_tokens": True}, True, None),
        ({"reasoning_tokens": "10"}, True, None),
        ({"reasoning_tokens": None}, False, 100),
        ({"audio_tokens": 1}, False, None),
    ],
)
def test_usage_components_match_observed_generation(details, seen, expected):
    usage = {"output_tokens": 100, "output_tokens_details": details}
    assert timing.output_tokens_for_tpot(usage, "output_tokens", seen) == expected


async def sdk_stream(
    recorded, *, usage=True, terminal="stop", kind="text", fail=None, provider="openai"
):
    """Use the real supported LiteLLM wrapper; only upstream I/O is controlled."""
    import datetime
    from unittest.mock import AsyncMock, Mock
    from litellm import CustomStreamWrapper
    from litellm.litellm_core_utils.litellm_logging import Logging
    from openai.types.chat import ChatCompletionChunk

    log = Logging(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "test"}],
        stream=True,
        call_type="acompletion",
        start_time=datetime.datetime.now(),
        litellm_call_id="tpot-test",
        function_id="tpot-test",
    )
    log.success_handler = Mock()
    log.async_success_handler = AsyncMock()

    async def upstream():
        for i, text in enumerate(["hello", " world"]):
            recorded.clock.now = i * 990_000_000
            delta = {"content": text} if kind == "text" else {"reasoning_content": text}
            yield ChatCompletionChunk(
                id="tpot-test",
                model="gpt-4o-mini",
                object="chat.completion.chunk",
                created=1,
                choices=[{"index": 0, "delta": delta, "finish_reason": None}],
            )
        if fail:
            raise fail
        if terminal:
            yield ChatCompletionChunk(
                id="tpot-test",
                model="gpt-4o-mini",
                object="chat.completion.chunk",
                created=1,
                choices=[{"index": 0, "delta": {}, "finish_reason": terminal}],
            )
        recorded.clock.now = 50_000_000_000
        if usage:
            yield ChatCompletionChunk(
                id="tpot-test",
                model="gpt-4o-mini",
                object="chat.completion.chunk",
                created=1,
                choices=[],
                usage={
                    "prompt_tokens": 1,
                    "completion_tokens": 100,
                    "total_tokens": 101,
                    "completion_tokens_details": {
                        "reasoning_tokens": 20 if kind != "text" else 0
                    },
                },
            )

    return CustomStreamWrapper(
        completion_stream=upstream(),
        model="gpt-4o-mini",
        logging_obj=log,
        custom_llm_provider=provider,
        stream_options={"include_usage": True},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "normal",
        "reasoning",
        "no_usage",
        "no_terminal",
        "length",
        "n2",
        "close",
        "close_error",
        "metadata_error",
        "cached",
        "unsupported",
    ],
)
async def test_litellm_real_sdk_contract_and_unchanged_chunks(
    recorded, monkeypatch, scenario
):
    import asyncio
    from google.adk.models.lite_llm import LiteLLMClient
    from veadk.models.timed_lite_llm import TimedLiteLLMClient

    response = await sdk_stream(
        recorded,
        usage=scenario != "no_usage",
        terminal=None
        if scenario == "no_terminal"
        else "length"
        if scenario == "length"
        else "stop",
        kind="reasoning" if scenario == "reasoning" else "text",
    )
    delivered = []
    original_next = response.__class__.__anext__

    async def next_chunk(self):
        chunk = await original_next(self)
        delivered.append(chunk)
        return chunk

    monkeypatch.setattr(response.__class__, "__anext__", next_chunk)
    if scenario in {"close_error", "metadata_error", "cached", "unsupported"}:
        close = response.aclose

        async def close_response():
            await close()
            if scenario == "close_error":
                raise RuntimeError("original close failure")
            if scenario == "metadata_error":
                response.chunks = None
            elif scenario == "cached":
                response.custom_llm_provider = "cached_response"
            else:
                response.custom_llm_provider = "unknown"

        monkeypatch.setattr(response, "aclose", close_response)

    async def complete(*args, **kwargs):
        return response

    monkeypatch.setattr(LiteLLMClient, "acompletion", complete)
    stream = await TimedLiteLLMClient().acompletion(
        "test", [], [], stream=True, n=2 if scenario == "n2" else 1
    )
    if scenario == "close":
        assert await anext(stream) is delivered[0]
        await stream.aclose()
    elif scenario == "close_error":
        with pytest.raises(RuntimeError, match="original close failure"):
            _ = [chunk async for chunk in stream]
    else:
        received = [chunk async for chunk in stream]
        assert len(received) == len(delivered)
        assert all(a is b for a, b in zip(received, delivered))
    await stream.aclose()
    await asyncio.sleep(0)
    if scenario in {"normal", "reasoning"}:
        assert points(recorded)[0].sum == pytest.approx(0.01)
        assert points(recorded)[0].count == 1
    else:
        assert not points(recorded)
    assert TTFT in recorded.spans.get_finished_spans()[0].attributes


def ark_terminal(kind="completed", usage=True, reasoning=0):
    from volcenginesdkarkruntime.types.responses import (
        ResponseCompletedEvent,
        ResponseIncompleteEvent,
    )

    raw = {
        "id": "response-test",
        "created_at": 1,
        "model": "test",
        "object": "response",
        "tools": [],
        "status": kind,
        "output": [
            {
                "id": "message-test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "hello world", "annotations": []}
                ],
            }
        ],
        "usage": {
            "input_tokens": 1,
            "output_tokens": 100,
            "total_tokens": 101,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": reasoning},
            "tool_usage": None,
            "tool_usage_details": None,
        }
        if usage
        else None,
    }
    if kind == "incomplete":
        raw["incomplete_details"] = {"reason": "length"}
    cls = ResponseCompletedEvent if kind == "completed" else ResponseIncompleteEvent
    return cls.model_validate({"type": f"response.{kind}", "response": raw})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "text",
        "tool",
        "full_reasoning",
        "summary",
        "hidden_reasoning",
        "incomplete",
        "no_usage",
        "no_terminal",
        "duplicate",
        "late_output",
        "error",
        "cancel",
        "close_error",
        "close_after_complete",
        "error_after_complete",
        "unsupported_delta",
        "bad_metadata",
    ],
)
async def test_ark_metadata_and_terminal_boundaries(recorded, monkeypatch, scenario):
    import asyncio
    from veadk.models.ark_llm import ArkLlm, ArkLlmClient
    from volcenginesdkarkruntime.types.responses import ResponseTextDeltaEvent

    event_type = {
        "summary": "response.reasoning_summary_text.delta",
        "full_reasoning": "response.reasoning_text.delta",
        "tool": "response.function_call_arguments.delta",
        "unsupported_delta": "response.output_audio.delta",
    }.get(scenario, "response.output_text.delta")
    closed = []
    error = (
        asyncio.CancelledError()
        if scenario == "cancel"
        else RuntimeError("original provider failure")
    )

    def delta(text):
        if event_type == "response.output_text.delta":
            return ResponseTextDeltaEvent(
                type=event_type,
                delta=text,
                item_id="message-test",
                output_index=0,
                content_index=0,
            )
        return NS(type=event_type, delta=text)

    async def events():
        for i, text in enumerate(["hello", " world"]):
            recorded.clock.now = i * 990_000_000
            yield delta(text)
        if scenario in {"error", "cancel"}:
            raise error
        recorded.clock.now = 50_000_000_000
        if scenario == "no_terminal":
            return
        if scenario == "bad_metadata":

            class Broken:
                status = "completed"

                @property
                def usage(self):
                    raise RuntimeError("private metadata")

            yield NS(type="response.completed", response=Broken())
            return
        terminal = ark_terminal(
            "incomplete" if scenario == "incomplete" else "completed",
            usage=scenario != "no_usage",
            reasoning=10 if "reasoning" in scenario or scenario == "summary" else 0,
        )
        yield terminal
        if scenario == "duplicate":
            yield terminal
        if scenario == "late_output":
            yield delta("late")
        if scenario == "error_after_complete":
            raise error

    class Stream:
        def __init__(self):
            self.iterator = events()

        def __aiter__(self):
            return self.iterator

        async def close(self):
            await self.iterator.aclose()
            closed.append(True)
            if scenario == "close_error":
                raise RuntimeError("original close failure")

    async def responses(*args, **kwargs):
        return Stream()

    monkeypatch.setattr(ArkLlmClient, "aresponses", responses)
    stream = ArkLlm(model="openai/test").generate_content_via_responses(
        {"model": "openai/test", "input": []}, stream=True
    )
    if scenario in {"error", "cancel", "error_after_complete"}:
        with pytest.raises(type(error)) as caught:
            _ = [r async for r in stream]
        assert caught.value is error
    elif scenario == "close_error":
        with pytest.raises(RuntimeError, match="original close failure"):
            _ = [r async for r in stream]
    elif scenario == "close_after_complete":
        for _ in range(3):
            await anext(stream)
        await stream.aclose()
    else:
        received = [r async for r in stream]
        if scenario == "text":
            assert [r.content.parts[0].text for r in received] == [
                "hello",
                " world",
                "hello world",
            ]
    assert closed == [True]
    if scenario in {"text", "tool", "full_reasoning"}:
        assert points(recorded)[0].sum == pytest.approx(0.01)
    else:
        assert not points(recorded)
    assert (
        TTFT in recorded.spans.get_finished_spans()[0].attributes
        or scenario == "unsupported_delta"
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "multiple_choices",
        "index",
        "audio",
        "refusal",
        "encrypted",
        "content",
        "missing_usage",
        "missing_count",
        "hidden_reasoning",
    ],
)
def test_chat_unsupported_metadata_is_omitted(scenario):
    from litellm import CustomStreamWrapper
    from veadk.models.timed_lite_llm import _stream_output_tokens

    response = object.__new__(CustomStreamWrapper)
    response.custom_llm_provider = "openai"
    response.received_finish_reason = "stop"
    delta = {"content": "test"}
    if scenario in {"audio", "refusal"}:
        delta[scenario] = "value"
    if scenario == "encrypted":
        delta["reasoning_content_encrypted"] = "value"
    if scenario == "content":
        delta["content"] = ["multimodal"]
    choices = [{"index": 1 if scenario == "index" else 0, "delta": delta}]
    if scenario == "multiple_choices":
        choices *= 2
    usage = {
        "completion_tokens": 100,
        "completion_tokens_details": {
            "reasoning_tokens": 10 if scenario == "hidden_reasoning" else 0
        },
    }
    if scenario == "missing_count":
        usage.pop("completion_tokens")
    response.chunks = [
        {"choices": choices, "usage": None if scenario == "missing_usage" else usage}
    ]
    assert _stream_output_tokens(response) is None


def test_interleaved_model_requests_do_not_share_state(recorded):
    first = timing.ModelTiming(streaming=True, model="first")
    second = timing.ModelTiming(streaming=True, model="second")
    first.observe("text")
    recorded.clock.now = 100_000_000
    second.observe("tool_call")
    recorded.clock.now = 990_000_000
    first.observe("text")
    recorded.clock.now = 2_080_000_000
    second.observe("tool_call")
    first.complete(100)
    second.complete(100)
    second.__exit__(None, None, None)
    first.__exit__(None, None, None)
    values = {p.attributes["gen_ai.request.model"]: p.sum for p in points(recorded)}
    assert values == pytest.approx({"first": 0.01, "second": 0.02})


@pytest.mark.asyncio
async def test_retry_preserves_response_and_separates_tpot_samples(
    recorded, monkeypatch
):
    from google.adk.models.lite_llm import LiteLLMClient
    from google.adk.models.llm_request import LlmRequest
    from google.genai import types
    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    calls = []

    class RateLimitError(RuntimeError):
        status_code = 429
        response = NS(headers={"Retry-After": "0"})

    async def complete(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise RateLimitError("quota")
        return await sdk_stream(recorded)

    monkeypatch.setattr(LiteLLMClient, "acompletion", complete)
    request = LlmRequest(
        model="openai/test",
        contents=[types.Content(role="user", parts=[types.Part(text="test")])],
    )
    result = [
        r
        async for r in RetryingLiteLlm(model="openai/test").generate_content_async(
            request, stream=True
        )
    ]
    assert result[-1].content.parts[0].text == "hello world"
    attempts = [
        s for s in recorded.spans.get_finished_spans() if s.name == "model_request"
    ]
    assert len(attempts) == 2
    assert TPOT not in attempts[0].attributes
    assert attempts[1].attributes[TPOT] == pytest.approx(0.01)
    assert points(recorded)[0].count == 1
