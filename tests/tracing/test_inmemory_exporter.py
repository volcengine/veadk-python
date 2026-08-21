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

import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider, sampling

from veadk.tracing.telemetry.exporters.inmemory_exporter import (
    _InMemoryExporter,
    _InMemorySpanProcessor,
)


def test_processor_preserves_nested_agent_trace_context():
    exporter = _InMemoryExporter()
    provider = TracerProvider()
    provider.add_span_processor(_InMemorySpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)
    initial_span = trace.get_current_span()

    invocation_span = tracer.start_span("invocation root")
    try:
        assert trace.get_current_span() is invocation_span
        parent_span = tracer.start_span("agent_run parent")
        try:
            assert trace.get_current_span() is parent_span
            child_span = tracer.start_span("agent_run child")
            try:
                assert trace.get_current_span() is child_span
                assert child_span.parent == parent_span.get_span_context()
                assert parent_span.parent == invocation_span.get_span_context()
                assert child_span.get_span_context().trace_id == (
                    parent_span.get_span_context().trace_id
                )
                assert parent_span.get_span_context().trace_id == (
                    invocation_span.get_span_context().trace_id
                )
            finally:
                child_span.end()
            assert trace.get_current_span() is parent_span
        finally:
            parent_span.end()
        assert trace.get_current_span() is invocation_span
    finally:
        invocation_span.end()

    assert trace.get_current_span() is initial_span


def test_processor_isolates_concurrent_agent_contexts():
    exporter = _InMemoryExporter()
    processor = _InMemorySpanProcessor(exporter)
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer(__name__)
    initial_span = trace.get_current_span()

    async def exercise():
        both_started = asyncio.Event()
        started = 0

        async def run_agent(name: str):
            nonlocal started
            span = tracer.start_span(f"agent_run {name}")
            try:
                assert trace.get_current_span() is span
                started += 1
                if started == 2:
                    both_started.set()
                await both_started.wait()
                await asyncio.sleep(0)
                assert trace.get_current_span() is span
                trace_id = span.get_span_context().trace_id
            finally:
                span.end()
            assert trace.get_current_span() is initial_span
            return trace_id

        return await asyncio.gather(run_agent("one"), run_agent("two"))

    trace_ids = asyncio.run(exercise())

    assert trace_ids[0] != trace_ids[1]
    assert trace.get_current_span() is initial_span
    assert processor._context_tokens == {}


def test_processor_restores_context_when_agent_run_raises():
    exporter = _InMemoryExporter()
    processor = _InMemorySpanProcessor(exporter)
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer(__name__)
    initial_span = trace.get_current_span()

    with pytest.raises(RuntimeError, match="agent failed"):
        span = tracer.start_span("agent_run failing")
        try:
            raise RuntimeError("agent failed")
        finally:
            span.end()

    assert trace.get_current_span() is initial_span
    assert processor._context_tokens == {}


def test_processor_keeps_agent_current_for_non_agent_span():
    exporter = _InMemoryExporter()
    processor = _InMemorySpanProcessor(exporter)
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer(__name__)
    initial_span = trace.get_current_span()

    agent_span = tracer.start_span("agent_run parent")
    try:
        non_agent_span = tracer.start_span("call_llm")
        try:
            assert trace.get_current_span() is agent_span
            assert non_agent_span.parent == agent_span.get_span_context()
        finally:
            non_agent_span.end()
        assert trace.get_current_span() is agent_span
    finally:
        agent_span.end()

    assert trace.get_current_span() is initial_span
    assert processor._context_tokens == {}


def test_processor_cleans_up_record_only_span():
    exporter = _InMemoryExporter()
    processor = _InMemorySpanProcessor(exporter)
    provider = TracerProvider(
        sampler=sampling.StaticSampler(sampling.Decision.RECORD_ONLY)
    )
    provider.add_span_processor(processor)
    tracer = provider.get_tracer(__name__)
    initial_span = trace.get_current_span()

    span = tracer.start_span("agent_run unsampled")
    assert trace.get_current_span() is span
    span.end()

    assert trace.get_current_span() is initial_span
    assert processor._context_tokens == {}
    assert exporter._spans == []


def test_processor_uses_readable_span_to_clean_up_context():
    exporter = _InMemoryExporter()
    processor = _InMemorySpanProcessor(exporter)
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer(__name__)
    initial_span = trace.get_current_span()

    span = tracer.start_span("agent_run readable")
    span.end()

    assert len(exporter._spans) == 1
    assert isinstance(exporter._spans[0], ReadableSpan)
    assert exporter._spans[0] is not span
    assert trace.get_current_span() is initial_span
    assert processor._context_tokens == {}
