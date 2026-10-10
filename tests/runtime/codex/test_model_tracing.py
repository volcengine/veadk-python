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

"""验证模型请求的真实父子关系、取消和异常脱敏。"""

import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from veadk.runtime.codex.model_tracing import trace_model_request


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, ValueError, asyncio.CancelledError])
async def test_model_request_parent_and_safe_failure(monkeypatch, failure):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)

    async def call():
        await asyncio.sleep(0)
        if failure:
            raise failure("private prompt and credential")
        return "response"

    with provider.get_tracer("test").start_as_current_span("invoke_agent") as parent:
        if failure:
            with pytest.raises(failure):
                await trace_model_request(call)
        else:
            assert await trace_model_request(call) == "response"
    spans = exporter.get_finished_spans()
    model = next(span for span in spans if span.name == "codex.model.request")
    assert model.parent.span_id == parent.get_span_context().span_id
    assert model.context.trace_id == parent.get_span_context().trace_id
    assert model.end_time >= model.start_time
    assert "private" not in model.to_json()
    assert not model.events
    if failure:
        assert model.attributes["error.type"] == failure.__name__
        assert model.status.status_code.name == "ERROR"
    else:
        assert model.status.status_code.name == "UNSET"
    provider.shutdown()


@pytest.mark.asyncio
async def test_model_request_without_tracing(monkeypatch):
    from veadk.runtime.codex import model_tracing

    monkeypatch.setattr(model_tracing, "trace", None)

    async def call():
        return "response"

    assert await model_tracing.trace_model_request(call) == "response"
