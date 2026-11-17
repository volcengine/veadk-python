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
import json
from types import SimpleNamespace as NS

import httpx
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
from openai import AsyncOpenAI
from volcenginesdkarkruntime.types.responses import (
    ResponseTextDeltaEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
)

from veadk.models.ark_llm import ArkLlm, ArkLlmClient
from veadk.models.retrying_lite_llm import RetryingLiteLlm
from veadk.models.timed_lite_llm import TimedLiteLLMClient
from veadk.tracing.telemetry import timing
from veadk.tracing.telemetry import litellm_response_id


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
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("patched", [False, True])
@pytest.mark.parametrize(
    "provider_id",
    [
        None,
        "",
        "omitted",
        "resp-provider",
        "chatcmpl-11111111-1111-4111-8111-111111111111",
    ],
)
async def test_chat_provider_id_survives_sdk_conversion(
    monkeypatch, spans, stream, patched, provider_id
):
    # REQ-003: exercise actual LiteLLM/OpenAI conversion, including generated ids.
    tracer, exporter = spans
    calls = []
    logger_events = []

    def handler(request):
        calls.append(json.loads(request.content))
        result = {
            "model": "test",
            "created": 1700000000,
            "object": "chat.completion.chunk" if stream else "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "delta" if stream else "message": {
                        "role": "assistant",
                        "content": "OK",
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        if provider_id != "omitted":
            result["id"] = provider_id
        if stream:
            return httpx.Response(
                200,
                headers={
                    "content-type": "text/event-stream",
                    "x-request-id": "header-only",
                },
                text="data: " + json.dumps(result) + "\n\ndata: [DONE]\n\n",
            )
        return httpx.Response(200, json=result, headers={"x-request-id": "header-only"})

    if patched:
        # Restore the class and registration flag after testing the legacy path.
        monkeypatch.setattr(LiteLLMClient, "acompletion", LiteLLMClient.acompletion)
        monkeypatch.setattr(litellm_response_id, "_patched", False)
        litellm_response_id.register()
        wrapped = LiteLLMClient.acompletion
        litellm_response_id.register()
        assert LiteLLMClient.acompletion is wrapped

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = AsyncOpenAI(
            api_key="unit-test",
            base_url="http://provider.invalid/v1",
            http_client=http_client,
        )
        with tracer.start_as_current_span("call_llm") as owner:
            response = await TimedLiteLLMClient().acompletion(
                "openai/test",
                [{"role": "user", "content": "hello"}],
                [],
                stream=stream,
                client=client,
                num_retries=0,
                logger_fn=lambda details: logger_events.append(
                    details["log_event_type"]
                ),
            )
            if stream:
                chunks = [chunk async for chunk in response]
                assert (
                    "".join(chunk.choices[0].delta.content or "" for chunk in chunks)
                    == "OK"
                )
            else:
                assert response.choices[0].message.content == "OK"
    attempt = next(
        span for span in exporter.get_finished_spans() if span.name == "model_request"
    )
    expected = provider_id if provider_id not in {None, "", "omitted"} else None
    assert attempt.attributes.get("gen_ai.response.id") == expected
    assert owner.attributes.get("gen_ai.response.id") == expected
    assert len(calls) == 1
    assert "post_api_call" in logger_events


@pytest.mark.asyncio
async def test_raw_provider_ids_are_isolated_across_calls(monkeypatch, spans):
    # REQ-003/REQ-005: raw-id capture is local even on one shared SDK client.
    tracer, exporter = spans

    async def complete(self, model, messages, tools, **kwargs):
        raw = {} if model == "no-id" else {"id": "resp-" + model}
        kwargs["logger_fn"](
            {"log_event_type": "post_api_call", "original_response": raw}
        )
        await asyncio.sleep(0)
        return ModelResponse()  # SDK fallback id must not replace the raw id.

    monkeypatch.setattr(LiteLLMClient, "acompletion", complete)
    client = TimedLiteLLMClient()

    async def call(model):
        with tracer.start_as_current_span(model) as owner:
            await client.acompletion(model, [], [])
        return owner.attributes.get("gen_ai.response.id")

    assert await asyncio.gather(call("a"), call("b")) == ["resp-a", "resp-b"]
    assert await call("no-id") is None
    attempts = [s for s in exporter.get_finished_spans() if s.name == "model_request"]
    assert [s.attributes.get("gen_ai.response.id") for s in attempts] == [
        "resp-a",
        "resp-b",
        None,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [True, False])
async def test_default_litellm_adapter_records_before_adk_aggregation(
    monkeypatch, spans, stream
):
    # REQ-001/REQ-006: both Chat modes preserve output and expose the provider id.
    tracer, exporter = spans

    async def chunks():
        for delta, finish_reason in [
            ({"role": "assistant"}, None),
            ({"content": "hello"}, None),
            ({"content": "!"}, "stop"),
        ]:
            chunk = ModelResponseStream(
                id="resp-stream",
                model="openai/test",
                choices=[{"index": 0, "delta": delta, "finish_reason": finish_reason}],
            )
            # Match LiteLLM's metadata for an id read from the provider chunk.
            chunk._hidden_params = {"received_model_id": "resp-stream"}
            yield chunk

    async def complete(self, model, messages, tools, **kwargs):
        assert isinstance(self, TimedLiteLLMClient)
        if kwargs.get("stream"):
            return chunks()
        kwargs["logger_fn"](
            {
                "log_event_type": "post_api_call",
                "original_response": {"id": "resp-plain"},
            }
        )
        return ModelResponse(
            id="resp-plain",
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
    expected_response_id = "resp-stream" if stream else "resp-plain"
    assert attempt.attributes["gen_ai.response.id"] == expected_response_id
    ttft = "gen_ai.chat_completions.streaming_time_to_first_token"
    assert (ttft in attempt.attributes) is stream
    if stream:
        assert attempt.attributes[ttft] >= 0
        assert attempt.start_time + attempt.attributes[ttft] * 1e9 <= attempt.end_time
    assert owner.attributes["gen_ai.response.id"] == expected_response_id
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


def test_response_id_keeps_first_value_per_attempt_and_isolates_attempts(spans):
    # REQ-003/REQ-004: ignore empty ids, keep the first id per request, isolate retries.
    tracer, exporter = spans

    with tracer.start_as_current_span("call_llm") as owner:
        first = timing.ModelTiming(streaming=True, model="first")
        first.observe_response_id(NS(id=""))
        first.observe_response_id(NS(response=NS(id="resp-first")))
        first.observe_response_id(NS(id="resp-conflict"))
        first.__exit__(None, None, None)

        second = timing.ModelTiming(streaming=False, model="second")
        second.observe_response_id(NS(id="resp-second"))
        second.__exit__(None, None, None)

    attempts = [
        span for span in exporter.get_finished_spans() if span.name == "model_request"
    ]
    assert [span.attributes["gen_ai.response.id"] for span in attempts] == [
        "resp-first",
        "resp-second",
    ]
    assert owner.attributes["gen_ai.response.id"] == "resp-second"


@pytest.mark.asyncio
async def test_response_id_is_isolated_across_concurrent_calls(spans):
    # REQ-005: concurrent calls bind ids to their own request and owner spans.
    tracer, exporter = spans
    ready = asyncio.Event()
    started = 0

    async def record(name, response_id):
        nonlocal started
        with tracer.start_as_current_span(name) as owner:
            request = timing.ModelTiming(streaming=True, model=name)
            started += 1
            if started == 2:
                ready.set()
            await ready.wait()
            request.observe_response_id(NS(id=response_id))
            request.__exit__(None, None, None)
        return owner

    owners = await asyncio.gather(
        record("call-a", "resp-a"),
        record("call-b", "resp-b"),
    )

    assert [owner.attributes["gen_ai.response.id"] for owner in owners] == [
        "resp-a",
        "resp-b",
    ]
    attempts = [
        span for span in exporter.get_finished_spans() if span.name == "model_request"
    ]
    assert {span.attributes["gen_ai.response.id"] for span in attempts} == {
        "resp-a",
        "resp-b",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["text", "tool_call", "empty", "close", "error", "non_streaming"]
)
async def test_ark_raw_events_and_terminal_paths(monkeypatch, spans, mode):
    # REQ-001/REQ-002/REQ-006: capture the earliest Ark id across terminal paths.
    tracer, exporter = spans
    closed = []

    async def chunks():
        try:
            yield NS(
                type="response.created",
                delta="",
                response=NS(id="resp-ark-stream"),
            )
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
            return NS(id="resp-ark-plain")
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
    expected_response_id = (
        "resp-ark-plain" if mode == "non_streaming" else "resp-ark-stream"
    )
    assert attempt.attributes["gen_ai.response.id"] == expected_response_id
    assert (
        "gen_ai.chat_completions.streaming_time_to_first_token" in attempt.attributes
    ) is (status == "observed")
    assert owner.attributes["gen_ai.response.id"] == expected_response_id
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
    # REQ-004: a failed request stays empty and the delivered retry owns its id.
    tracer, exporter = spans
    requests = []

    class RateLimitError(RuntimeError):
        status_code = 429
        response = NS(headers={"Retry-After": "0"})

    async def chunks():
        chunk = ModelResponseStream(
            id="resp-retry-success",
            model="openai/test",
            choices=[
                {"index": 0, "delta": {"content": "hello"}, "finish_reason": "stop"}
            ],
        )
        chunk._hidden_params = {"received_model_id": "resp-retry-success"}
        yield chunk

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
    assert "gen_ai.response.id" not in attempts[0].attributes
    assert attempts[1].attributes["gen_ai.response.id"] == "resp-retry-success"
    assert owner.attributes["gen_ai.response.id"] == "resp-retry-success"
    assert all(s.parent.span_id == owner.context.span_id for s in attempts)
    assert all(
        not any(key.startswith("veadk.") for key in s.attributes) for s in attempts
    )
