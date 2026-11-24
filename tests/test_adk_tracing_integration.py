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

"""Exercise real ADK scope lifetimes without model or exporter network calls."""

import asyncio
import json
from pathlib import Path

import pytest
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from opentelemetry import context as context_api
from opentelemetry import trace as trace_api
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.util._once import Once

from veadk import Agent
from veadk.config import settings
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.utils.patches import patch_tracer


class _ToolModel(BaseLlm):
    async def generate_content_async(self, llm_request, stream=False):
        await asyncio.sleep(0)
        if stream:
            yield LlmResponse(
                content=types.ModelContent(parts=[types.Part(text="working")]),
                partial=True,
            )
        has_response = any(
            part.function_response
            for content in llm_request.contents
            for part in content.parts or []
        )
        part = (
            types.Part(text="done")
            if has_response
            else types.Part(
                function_call=types.FunctionCall(id="echo-1", name="echo", args={})
            )
        )
        yield LlmResponse(
            content=types.ModelContent(parts=[part]),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=3, candidates_token_count=2, total_token_count=5
            ),
        )


@pytest.fixture(params=["", "otel_semconv_1_36"], ids=["default", "legacy"])
def tracing(monkeypatch, request):
    monkeypatch.setenv("ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN", request.param)
    monkeypatch.setenv("ENABLE_APMPLUS", "false")
    monkeypatch.setenv("ENABLE_COZELOOP", "false")
    monkeypatch.setenv("ENABLE_TLS", "false")
    monkeypatch.setattr(settings.opentelemetry_config, "inmemory_enabled", True)
    monkeypatch.setattr(trace_api, "_TRACER_PROVIDER", None)
    monkeypatch.setattr(trace_api, "_TRACER_PROVIDER_SET_ONCE", Once())
    provider = TracerProvider()
    exported = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exported))
    trace_api.set_tracer_provider(provider)
    tracer = OpentelemetryTracer()
    # ADK's module-level tracers must follow this test's replacement provider.
    patch_tracer()
    yield tracer, exported
    provider.shutdown()


def _runner(model, tracer, tools=()):
    agent = Agent(
        name="tracing_agent",
        model=model,
        model_api_key="test-key",
        tools=list(tools),
        tracers=[tracer],
    )
    return InMemoryRunner(agent=agent, app_name="tracing-test")


async def _run(runner, session_id, stream=False):
    await runner.session_service.create_session(
        app_name=runner.app_name, user_id="test-user", session_id=session_id
    )
    return [
        event
        async for event in runner.run_async(
            user_id="test-user",
            session_id=session_id,
            new_message=types.UserContent(parts=[types.Part(text="run")]),
            run_config=RunConfig(
                streaming_mode=StreamingMode.SSE if stream else StreamingMode.NONE
            ),
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_concurrent_runs_keep_complete_session_traces(tracing, tmp_path, stream):
    tracer, exported = tracing

    async def echo() -> str:
        await asyncio.sleep(0)
        return "ok"

    runner = _runner(_ToolModel(model="local"), tracer, [echo])
    before = context_api.get_current()
    try:
        runs = await asyncio.gather(
            _run(runner, "one", stream), _run(runner, "two", stream)
        )
    finally:
        await runner.close()
    assert context_api.get_current() == before
    assert all(
        any(
            part.text == "done" for e in events if e.content for part in e.content.parts
        )
        for events in runs
    )
    assert not any(
        s.name.startswith("generate_content") for s in exported.get_finished_spans()
    )
    trace_ids = []
    for session_id in ("one", "two"):
        spans = tracer._inmemory_exporter._exporter.get_finished_spans(session_id)
        model_spans = [s for s in spans if s.name == "call_llm"]
        assert len(model_spans) == 2
        roots = [s for s in spans if s.attributes.get("gen_ai.span.kind") == "workflow"]
        assert len(roots) == 1
        assert roots[0].attributes["gen_ai.usage.total_tokens"] == 10
        assert all(s.attributes.get("gen_ai.session.id") == session_id for s in spans)
        assert (
            len([s for s in spans if s.attributes.get("gen_ai.span.kind") == "agent"])
            == 1
        )
        assert (
            len([s for s in spans if s.attributes.get("gen_ai.span.kind") == "tool"])
            == 1
        )
        trace_ids.append({s.context.trace_id for s in spans})
        path = tracer.dump(
            user_id="test-user", session_id=session_id, path=str(tmp_path)
        )
        assert json.loads(Path(path).read_text())
    assert trace_ids[0].isdisjoint(trace_ids[1])


class _WaitingModel(BaseLlm):
    entered: asyncio.Event

    async def generate_content_async(self, llm_request, stream=False):
        self.entered.set()
        await asyncio.Event().wait()
        yield LlmResponse()


@pytest.mark.asyncio
async def test_closed_stream_ends_spans_and_restores_context(tracing, caplog):
    tracer, exported = tracing
    runner = _runner(_ToolModel(model="local"), tracer)
    await runner.session_service.create_session(
        app_name=runner.app_name, user_id="test-user", session_id="closed"
    )
    before = context_api.get_current()
    events = runner.run_async(
        user_id="test-user",
        session_id="closed",
        new_message=types.UserContent(parts=[types.Part(text="run")]),
        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
    )
    try:
        assert (await anext(events)).partial
    finally:
        await events.aclose()
        await runner.close()
    assert context_api.get_current() == before
    names = [s.name for s in exported.get_finished_spans()]
    assert "call_llm" in names
    assert any(name.startswith("invoke_agent") for name in names)
    assert "Failed to detach context" not in caplog.text


@pytest.mark.asyncio
async def test_cancelled_run_ends_spans_and_restores_context(tracing, caplog):
    tracer, exported = tracing
    entered = asyncio.Event()
    runner = _runner(_WaitingModel(model="local", entered=entered), tracer)
    before = context_api.get_current()
    task = asyncio.create_task(_run(runner, "cancelled"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runner.close()
    assert context_api.get_current() == before
    names = [s.name for s in exported.get_finished_spans()]
    assert "call_llm" in names
    assert any(name.startswith("invoke_agent") for name in names)
    assert "Failed to detach context" not in caplog.text


class _FailingModel(BaseLlm):
    async def generate_content_async(self, llm_request, stream=False):
        raise RuntimeError("model failed")
        yield LlmResponse()


@pytest.mark.asyncio
async def test_model_failure_propagates_and_closes_trace(tracing, caplog):
    tracer, exported = tracing
    runner = _runner(_FailingModel(model="local"), tracer)
    before = context_api.get_current()
    try:
        with pytest.raises(RuntimeError, match="model failed"):
            await _run(runner, "failed")
    finally:
        await runner.close()
    assert context_api.get_current() == before
    calls = [s for s in exported.get_finished_spans() if s.name == "call_llm"]
    assert len(calls) == 1
    assert calls[0].status.is_ok is False
    assert "Failed to detach context" not in caplog.text
