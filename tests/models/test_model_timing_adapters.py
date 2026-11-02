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
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from litellm import ModelResponse
from litellm.types.utils import ModelResponseStream
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import StatusCode
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from volcenginesdkarkruntime.types.responses import (
    ResponseTextDeltaEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
)

from veadk.models.ark_llm import ArkLlm, ArkLlmClient
from veadk.models.retrying_lite_llm import RetryingLiteLlm
from veadk.models.timed_lite_llm import TimedLiteLLMClient
from veadk.tracing.telemetry import timing


@pytest.fixture
def spans(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("adapter-test")
    monkeypatch.setattr(timing.trace, "get_tracer", lambda *a, **kw: tracer)
    yield tracer, exporter
    provider.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [True, False])
async def test_default_litellm_adapter_records_before_adk_aggregation(
    monkeypatch, spans, stream
):
    tracer, exporter = spans

    async def chunks():
        yield ModelResponseStream(
            model="openai/test",
            choices=[
                {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
            ],
        )
        yield ModelResponseStream(
            model="openai/test",
            choices=[
                {"index": 0, "delta": {"content": "hello"}, "finish_reason": None}
            ],
        )
        yield ModelResponseStream(
            model="openai/test",
            choices=[{"index": 0, "delta": {"content": "!"}, "finish_reason": "stop"}],
        )

    async def complete(self, model, messages, tools, **kwargs):
        assert isinstance(self, TimedLiteLLMClient)
        if kwargs.get("stream"):
            return chunks()
        return ModelResponse(
            model=model,
            choices=[
                {
                    "message": {"role": "assistant", "content": "hello!"},
                    "finish_reason": "stop",
                    "index": 0,
                }
            ],
        )

    monkeypatch.setattr(LiteLLMClient, "acompletion", complete)
    model = RetryingLiteLlm(model="openai/test")
    request = LlmRequest(
        model=model.model,
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
    )
    with tracer.start_as_current_span("call_llm") as owner:
        responses = [
            r async for r in model.generate_content_async(request, stream=stream)
        ]
    assert responses
    attempt = next(
        s for s in exporter.get_finished_spans() if s.name == "model_request"
    )
    assert attempt.attributes["gen_ai.request.stream"] is stream
    ttft = "gen_ai.chat_completions.streaming_time_to_first_token"
    assert (ttft in attempt.attributes) is stream
    if stream:
        assert attempt.attributes[ttft] >= 0
        assert attempt.start_time + attempt.attributes[ttft] * 1e9 <= attempt.end_time
    assert not owner.attributes
    assert not owner.events
    assert (
        len([s for s in exporter.get_finished_spans() if s.name == "model_request"])
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["error", "cancel", "empty", "close", "no_close_method"]
)
async def test_litellm_terminal_paths_close_original_stream(monkeypatch, spans, mode):
    tracer, exporter = spans
    closed = []

    async def chunks():
        try:
            if mode == "error":
                raise RuntimeError("provider failed")
            if mode == "cancel":
                raise asyncio.CancelledError()
            if mode == "empty":
                return
            yield NS(choices=[NS(delta=NS(content="hello"))])
        finally:
            closed.append(True)

    class IteratorOnly:
        def __aiter__(self):
            return chunks()

    async def complete(*args, **kwargs):
        return IteratorOnly() if mode == "no_close_method" else chunks()

    monkeypatch.setattr(LiteLLMClient, "acompletion", complete)
    with tracer.start_as_current_span("call_llm"):
        response = await TimedLiteLLMClient().acompletion("test", [], [], stream=True)
        if mode in {"error", "cancel"}:
            with pytest.raises(
                RuntimeError if mode == "error" else asyncio.CancelledError
            ):
                await anext(response)
        elif mode == "close":
            await anext(response)
            await response.aclose()
        else:
            _ = [r async for r in response]
    attempt = exporter.get_finished_spans()[0]
    assert closed == [True]
    error_type = {"error": "llm_error", "cancel": "cancelled"}.get(mode)
    assert attempt.attributes.get("error.type") == error_type
    assert attempt.status.status_code is (
        StatusCode.ERROR if error_type else StatusCode.UNSET
    )


@pytest.mark.asyncio
async def test_litellm_request_failure_does_not_leak_span(monkeypatch, spans):
    _, exporter = spans

    async def complete(*args, **kwargs):
        raise RuntimeError("request failed")

    monkeypatch.setattr(LiteLLMClient, "acompletion", complete)
    with pytest.raises(RuntimeError, match="request failed"):
        await TimedLiteLLMClient().acompletion("test", [], [], stream=True)
    assert exporter.get_finished_spans()[0].status.status_code is StatusCode.ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["text", "tool_call", "empty", "close", "error", "non_streaming"]
)
async def test_ark_raw_events_and_terminal_paths(monkeypatch, spans, mode):
    tracer, exporter = spans
    closed = []

    async def chunks():
        try:
            yield NS(type="response.created", delta="")
            if mode == "error":
                raise RuntimeError("provider failed")
            if mode == "empty":
                return
            if mode == "tool_call":
                yield ResponseFunctionCallArgumentsDeltaEvent(
                    type="response.function_call_arguments.delta",
                    item_id="item",
                    output_index=0,
                    delta="{",
                )
            yield ResponseTextDeltaEvent(
                type="response.output_text.delta",
                item_id="item",
                output_index=0,
                content_index=0,
                delta="hello",
            )
        finally:
            closed.append(True)

    class Stream:
        def __init__(self):
            self.events = chunks()

        def __aiter__(self):
            return self.events

        async def close(self):
            await self.events.aclose()

    async def responses(*args, **kwargs):
        if mode == "non_streaming":
            return NS()
        return Stream()

    monkeypatch.setattr(ArkLlmClient, "aresponses", responses)
    if mode == "non_streaming":
        from google.adk.models.llm_response import LlmResponse

        monkeypatch.setattr(
            "veadk.models.ark_llm.ark_response_to_generate_content_response",
            lambda _: LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="hello")])
            ),
        )
    model = ArkLlm(model="openai/test")
    with tracer.start_as_current_span("call_llm") as owner:
        stream = model.generate_content_via_responses(
            {"model": "openai/test", "input": []}, stream=mode != "non_streaming"
        )
        if mode == "error":
            with pytest.raises(RuntimeError, match="provider failed"):
                _ = [r async for r in stream]
        elif mode == "close":
            assert (await anext(stream)).content.parts[0].text == "hello"
            await stream.aclose()
        else:
            responses_seen = [r async for r in stream]
            if mode not in {"empty", "non_streaming"}:
                assert responses_seen[0].content.parts[0].text == "hello"
    attempt = exporter.get_finished_spans()[0]
    status = (
        "non_streaming"
        if mode == "non_streaming"
        else "no_output"
        if mode in {"empty", "error"}
        else "observed"
    )
    assert attempt.attributes["gen_ai.request.stream"] is (mode != "non_streaming")
    assert (
        "gen_ai.chat_completions.streaming_time_to_first_token" in attempt.attributes
    ) is (status == "observed")
    assert not owner.attributes
    assert not owner.events
    assert attempt.status.status_code is (
        StatusCode.ERROR if mode == "error" else StatusCode.UNSET
    )
    assert attempt.end_time is not None
    if mode != "non_streaming":
        assert closed == [True]


@pytest.mark.asyncio
async def test_litellm_close_before_iteration_ends_attempt(monkeypatch, spans):
    _, exporter = spans
    closed = []

    class Stream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise AssertionError("must not consume")

        async def aclose(self):
            closed.append(True)

    async def complete(*args, **kwargs):
        return Stream()

    monkeypatch.setattr(LiteLLMClient, "acompletion", complete)
    response = await TimedLiteLLMClient().acompletion("test", [], [], stream=True)
    await response.aclose()
    await response.aclose()
    assert closed == [True]
    attempt = exporter.get_finished_spans()[0]
    assert attempt.status.status_code is StatusCode.UNSET
    assert (
        "gen_ai.chat_completions.streaming_time_to_first_token"
        not in attempt.attributes
    )
    with pytest.raises(StopAsyncIteration):
        await anext(response)


@pytest.mark.asyncio
async def test_litellm_close_failure_propagates_and_ends_span(monkeypatch, spans):
    _, exporter = spans

    class Stream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def aclose(self):
            raise RuntimeError("close failed")

    async def complete(*args, **kwargs):
        return Stream()

    monkeypatch.setattr(LiteLLMClient, "acompletion", complete)
    response = await TimedLiteLLMClient().acompletion("test", [], [], stream=True)
    with pytest.raises(RuntimeError, match="close failed"):
        await anext(response)
    assert exporter.get_finished_spans()[0].status.status_code is StatusCode.ERROR


@pytest.mark.asyncio
async def test_veadk_retry_exports_distinct_sdk_attempts(monkeypatch, spans):
    tracer, exporter = spans
    requests = []

    class RateLimitError(RuntimeError):
        status_code = 429
        response = NS(headers={"Retry-After": "0"})

    async def chunks():
        yield ModelResponseStream(
            model="openai/test",
            choices=[
                {"index": 0, "delta": {"content": "hello"}, "finish_reason": "stop"}
            ],
        )

    async def complete(self, model, messages, tools, **kwargs):
        requests.append(model)
        if len(requests) == 1:
            raise RateLimitError("pre-output quota failure")
        return chunks()

    monkeypatch.setattr(LiteLLMClient, "acompletion", complete)
    model = RetryingLiteLlm(model="openai/test")
    request = LlmRequest(
        model=model.model,
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
    )
    with tracer.start_as_current_span("runner_request"):
        with tracer.start_as_current_span("call_llm") as owner:
            responses = [
                r async for r in model.generate_content_async(request, stream=True)
            ]
    assert responses and requests == ["openai/test", "openai/test"]
    attempts = [s for s in exporter.get_finished_spans() if s.name == "model_request"]
    assert len(attempts) == 2
    assert attempts[0].status.status_code is StatusCode.ERROR
    assert attempts[0].attributes["error.type"] == "llm_error"
    ttft = "gen_ai.chat_completions.streaming_time_to_first_token"
    assert ttft not in attempts[0].attributes
    assert attempts[1].status.status_code is StatusCode.UNSET
    assert ttft in attempts[1].attributes
    assert not owner.attributes
    assert all(s.parent.span_id == owner.context.span_id for s in attempts)
    assert all(
        not any(key.startswith("veadk.") for key in s.attributes) for s in attempts
    )
