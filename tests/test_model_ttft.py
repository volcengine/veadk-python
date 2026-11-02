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

"""Standard per-SDK-request TTFT span and metric contracts."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import Histogram, InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NoOpTracer

from veadk.tracing.telemetry import portal_metrics, timing

TTFT = "gen_ai.chat_completions.streaming_time_to_first_token"


@pytest.fixture
def telemetry(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple]:
    reader = InMemoryMetricReader()
    metrics = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(portal_metrics.metrics_api, "get_meter", metrics.get_meter)
    recorder = portal_metrics.PortalMetricRecorder()
    monkeypatch.setattr(portal_metrics, "portal_metric_recorder", recorder)
    traces = TracerProvider()
    exporter = InMemorySpanExporter()
    traces.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = traces.get_tracer("ttft-test")
    monkeypatch.setattr(timing.trace, "get_tracer", lambda *args: tracer)
    yield tracer, exporter, reader, recorder
    traces.shutdown()
    metrics.shutdown()


def ttft_points(reader: InMemoryMetricReader) -> list:
    data = reader.get_metrics_data()
    if data is None:
        return []
    points = []
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                if metric.name == TTFT:
                    assert metric.unit == "s"
                    assert isinstance(metric.data, Histogram)
                    points.extend(metric.data.data_points)
    return points


@pytest.mark.parametrize("kind", ["text", "reasoning", "tool_call"])
def test_ttft_seconds_are_recorded_once_without_usage(
    monkeypatch: pytest.MonkeyPatch, telemetry: tuple, kind: str
) -> None:
    tracer, exporter, reader, _ = telemetry
    clock = iter([10_000_000_000, 10_250_000_000])
    monkeypatch.setattr(timing.time, "time_ns", lambda: next(clock))
    with timing.bind_request_start(timing.RequestStart(1, "http")):
        with tracer.start_as_current_span("call_llm") as owner:
            with timing.ModelTiming(streaming=True, model="openai/test") as call:
                call.observe(None)
                call.observe(kind)
                call.observe("text")
            assert TTFT not in owner.attributes
    attempt = exporter.get_finished_spans()[0]
    assert attempt.attributes["gen_ai.span.kind"] == "llm"
    assert attempt.attributes["gen_ai.request.stream"] is True
    assert type(attempt.attributes[TTFT]) is float
    assert attempt.attributes[TTFT] == 0.25
    assert attempt.attributes["veadk.model.first_token_time_unix_ns"] == 10_250_000_000
    points = ttft_points(reader)
    assert len(points) == 1
    assert (points[0].count, points[0].sum) == (1, 0.25)
    assert dict(points[0].attributes) == {
        "gen_ai.request.model": "openai/test",
        "gen_ai.operation.name": "chat",
    }


@pytest.mark.parametrize("mode", ["non_streaming", "empty", "unsupported"])
def test_missing_observation_has_no_ttft(telemetry: tuple, mode: str) -> None:
    tracer, exporter, reader, _ = telemetry
    with tracer.start_as_current_span("call_llm") as owner:
        if mode == "unsupported":
            timing.mark_uninstrumented_model(owner, streaming=True)
            assert "gen_ai.request.stream" not in owner.attributes
        else:
            with timing.ModelTiming(streaming=mode == "empty", model="test") as call:
                call.observe("text" if mode == "non_streaming" else None)
    for span in exporter.get_finished_spans():
        assert TTFT not in span.attributes
        if span.name == "model_request":
            assert span.attributes["gen_ai.request.stream"] is (mode == "empty")
    assert ttft_points(reader) == []


@pytest.mark.parametrize("offset", [-1, 0])
def test_clock_boundary(
    monkeypatch: pytest.MonkeyPatch, telemetry: tuple, offset: int
) -> None:
    _, exporter, reader, _ = telemetry
    diagnostic = Mock()
    monkeypatch.setattr(timing.logger, "warning", diagnostic)
    clock = iter([1_000_000_000, 1_000_000_000 + offset])
    monkeypatch.setattr(timing.time, "time_ns", lambda: next(clock))
    with timing.ModelTiming(streaming=True, model="test") as call:
        call.observe("text")
        call.observe("text")
    attempt = exporter.get_finished_spans()[0]
    assert attempt.attributes["veadk.model.first_token_status"] == "observed"
    assert diagnostic.call_count == int(offset < 0)
    if offset < 0:
        assert TTFT not in attempt.attributes
        assert ttft_points(reader) == []
    else:
        assert attempt.attributes[TTFT] == 0.0
        point = ttft_points(reader)[0]
        assert (point.count, point.sum) == (1, 0.0)


@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError, GeneratorExit])
@pytest.mark.parametrize("observed", [False, True])
def test_interruption_preserves_only_observed_ttft(
    telemetry: tuple, error: type[BaseException], observed: bool
) -> None:
    _, exporter, reader, _ = telemetry
    with pytest.raises(error):
        with timing.ModelTiming(streaming=True, model="test") as call:
            if observed:
                call.observe("text")
            raise error()
    attempt = exporter.get_finished_spans()[0]
    assert attempt.end_time is not None
    assert (TTFT in attempt.attributes) is observed
    points = ttft_points(reader)
    assert len(points) == int(observed)
    if observed:
        assert points[0].count == 1


def test_metrics_do_not_depend_on_recording_spans(
    monkeypatch: pytest.MonkeyPatch, telemetry: tuple
) -> None:
    _, exporter, reader, _ = telemetry
    monkeypatch.setattr(timing.trace, "get_tracer", lambda *args: NoOpTracer())
    with timing.ModelTiming(streaming=True, model="test") as call:
        call.observe("text")
    assert exporter.get_finished_spans() == ()
    assert ttft_points(reader)[0].count == 1


def test_metric_failure_does_not_replace_model_error_or_expose_details(
    monkeypatch: pytest.MonkeyPatch, telemetry: tuple
) -> None:
    _, exporter, _, recorder = telemetry
    record = Mock(side_effect=ValueError("private metric failure details"))
    monkeypatch.setattr(recorder.streaming_time_to_first_token, "record", record)
    diagnostic = Mock()
    monkeypatch.setattr(portal_metrics.logger, "warning", diagnostic)
    with pytest.raises(RuntimeError, match="model failed"):
        with timing.ModelTiming(streaming=True, model="test") as call:
            call.observe("text")
            call.observe("text")
            raise RuntimeError("model failed")
    assert record.call_count == 1
    assert diagnostic.call_count == 1
    assert "private metric failure details" not in str(diagnostic.call_args)
    assert TTFT in exporter.get_finished_spans()[0].attributes


def test_retries_never_reuse_or_duplicate_ttft(
    monkeypatch: pytest.MonkeyPatch, telemetry: tuple
) -> None:
    tracer, exporter, reader, _ = telemetry
    clock = iter(
        [1_000_000_000, 1_100_000_000, 2_000_000_000, 3_000_000_000, 3_500_000_000]
    )
    monkeypatch.setattr(timing.time, "time_ns", lambda: next(clock))
    with tracer.start_as_current_span("call_llm"):
        for model, observed in [
            ("primary", True),
            ("primary", False),
            ("fallback", True),
        ]:
            with timing.ModelTiming(streaming=True, model=model) as call:
                if observed:
                    call.observe("text")
    attempts = [
        span for span in exporter.get_finished_spans() if span.name == "model_request"
    ]
    assert attempts[0].attributes[TTFT] == 0.1
    assert TTFT not in attempts[1].attributes
    assert attempts[2].attributes[TTFT] == 0.5
    assert sorted(
        (p.attributes["gen_ai.request.model"], p.count, p.sum)
        for p in ttft_points(reader)
    ) == [("fallback", 1, 0.5), ("primary", 1, 0.1)]


@pytest.mark.asyncio
async def test_concurrent_requests_keep_metric_models_isolated(
    telemetry: tuple,
) -> None:
    _, exporter, reader, _ = telemetry

    async def run(model: str) -> None:
        with timing.ModelTiming(streaming=True, model=model) as call:
            await asyncio.sleep(0)
            call.observe("text")
            await asyncio.sleep(0)
            call.observe("text")

    await asyncio.gather(run("one"), run("two"))
    points = ttft_points(reader)
    assert {p.attributes["gen_ai.request.model"] for p in points} == {"one", "two"}
    assert all(p.count == 1 for p in points)
    for span in exporter.get_finished_spans():
        point = next(
            p
            for p in points
            if p.attributes["gen_ai.request.model"]
            == span.attributes["gen_ai.request.model"]
        )
        assert point.sum == span.attributes[TTFT]


def test_final_response_callbacks_do_not_duplicate_ttft(telemetry: tuple) -> None:
    from types import SimpleNamespace

    from google.adk.models.llm_request import LlmRequest
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    _, _, reader, recorder = telemetry
    context = SimpleNamespace(
        run_config=None, agent=SimpleNamespace(model_api_base="https://example.invalid")
    )
    with timing.ModelTiming(streaming=True, model="test") as call:
        call.observe("text")
    for usage in (
        None,
        types.GenerateContentResponseUsageMetadata(prompt_token_count=1),
    ):
        recorder.record_call_llm(
            context,
            "event",
            LlmRequest(model="test"),
            LlmResponse(usage_metadata=usage),
        )
    assert ttft_points(reader)[0].count == 1


def test_unconfigured_meter_provider_needs_no_exporter(
    monkeypatch: pytest.MonkeyPatch, telemetry: tuple
) -> None:
    from opentelemetry.metrics import NoOpMeterProvider

    _, exporter, reader, _ = telemetry
    monkeypatch.setattr(
        portal_metrics.metrics_api, "get_meter", NoOpMeterProvider().get_meter
    )
    monkeypatch.setattr(
        portal_metrics, "portal_metric_recorder", portal_metrics.PortalMetricRecorder()
    )
    with timing.ModelTiming(streaming=True, model="test") as call:
        call.observe("text")
    assert TTFT in exporter.get_finished_spans()[0].attributes
    assert ttft_points(reader) == []
