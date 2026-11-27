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

"""Protocol response-ID capture for Responses, Chat and Messages formats."""

import json
import sys
from types import SimpleNamespace as NS

import httpx
import pytest
from anthropic.types import Message as AnthropicMessage
from litellm import ModelResponse
from litellm.llms.anthropic.chat.handler import ModelResponseIterator
from litellm.llms.anthropic.chat.transformation import AnthropicConfig
from litellm.types.utils import ModelResponseStream
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
from veadk.models.timed_lite_llm import TimedLiteLLMClient
from veadk.tracing.telemetry import protocol_response_id as protocol
from veadk.tracing.telemetry import timing

ATTR = protocol.RESPONSE_ID_ATTRIBUTE


@pytest.fixture
def tracing(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("protocol-response-id-test")
    monkeypatch.setattr(trace_api, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(timing.trace, "get_tracer", lambda *args, **kwargs: tracer)
    yield tracer, exporter
    provider.shutdown()


@pytest.fixture
def messages(monkeypatch):
    captured = []
    monkeypatch.setattr(
        protocol.logger,
        "info",
        lambda message, *args, **kwargs: captured.append(message),
    )
    return captured


@pytest.fixture
def mock_http(monkeypatch):
    """Route LiteLLM's httpx traffic to a mock handler; reject real network."""

    original = httpx.AsyncClient.send

    def install(handler):
        transport = httpx.MockTransport(handler)

        async def send(client, request, **kwargs):
            if not str(request.url).startswith("https://mock.local"):
                raise AssertionError(f"unexpected network call: {request.url}")
            return await transport.handle_async_request(request)

        monkeypatch.setattr(httpx.AsyncClient, "send", send)

    yield install
    monkeypatch.setattr(httpx.AsyncClient, "send", original)


@pytest.fixture(autouse=True)
def restore_litellm_seams(monkeypatch):
    monkeypatch.setattr(protocol, "_patched", False)
    for owner, name in (
        (ModelResponseIterator, "chunk_parser"),
        (AnthropicConfig, "transform_parsed_response"),
    ):
        monkeypatch.setattr(owner, name, getattr(owner, name))
    yield


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


def _chat_body(response_id="chat-id"):
    return {
        "id": response_id,
        "object": "chat.completion",
        "created": 1,
        "model": "test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "OK"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _chat_chunk(response_id="chat-id"):
    return {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test",
        "choices": [{"index": 0, "delta": {"content": "OK"}, "finish_reason": None}],
    }


def _anthropic_body(message_id="msg-id"):
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": "test",
        "content": [{"type": "text", "text": "OK"}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def _anthropic_sse(message_id):
    return (
        "event: message_start\n"
        f"data: {json.dumps({'type': 'message_start', 'message': {'id': message_id, 'type': 'message', 'role': 'assistant', 'model': 'test', 'content': [], 'stop_reason': None, 'stop_sequence': None, 'usage': {'input_tokens': 1, 'output_tokens': 0}}})}\n\n"
        "event: content_block_start\n"
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
        "event: content_block_delta\n"
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"OK"}}\n\n'
        "event: content_block_stop\n"
        'data: {"type":"content_block_stop","index":0}\n\n'
        "event: message_delta\n"
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":1}}\n\n'
        "event: message_stop\n"
        'data: {"type":"message_stop"}\n\n'
    )


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (NS(type="message_start", message=NS(id="msg-1")), ("messages", "msg-1")),
        ({"type": "message_start", "message": {"id": "msg-2"}}, ("messages", "msg-2")),
        (
            NS(type="response.created", response=NS(id="resp-1")),
            ("responses", "resp-1"),
        ),
        (
            ResponseCreatedEvent(
                type="response.created", response=_ark_response("resp-2")
            ),
            ("responses", "resp-2"),
        ),
        (NS(object="response", id="resp-3"), ("responses", "resp-3")),
        (ModelResponse(id="chat-1", choices=[]), ("chat", "chat-1")),
        (ModelResponseStream(id="chat-2", choices=[]), ("chat", "chat-2")),
        (_chat_body("chat-3"), ("chat", "chat-3")),
        (_chat_chunk("chat-4"), ("chat", "chat-4")),
        (
            AnthropicMessage.model_validate(_anthropic_body("msg-3")),
            ("messages", "msg-3"),
        ),
        ({"id": "chat-5", "created": 1, "choices": []}, ("chat", "chat-5")),
    ],
)
def test_extracts_body_ids_from_all_protocols(value, expected):
    assert protocol.extract_response_id(value) == protocol.ProtocolResponseId(*expected)


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"id": "x"},
        {
            "type": "message",
            "id": "item-id",
            "role": "assistant",
            "status": "completed",
        },
        {"type": "message_start", "message": None},
        {"type": "message_start", "message": {}},
        {"type": "message_delta", "delta": {}, "usage": {}},
        {"type": "response.created", "response": None},
        {"type": "response.created", "response": {}},
        {"type": "response.output_text.delta", "delta": "OK"},
        NS(type="response.completed", response=None),
        {"object": "chat.completion", "id": None},
        {"created": 1, "choices": []},
        # Blank, non-string and missing IDs must never be published.
        {"object": "response", "id": ""},
        {"object": "response", "id": "   "},
        {"object": "response", "id": 123},
        {"object": "response"},
        {"type": "message_start", "message": {"id": ""}},
        {"type": "message_start", "message": {"id": 7}},
        {"type": "message", "model": "m", "stop_reason": None, "id": ""},
        {"type": "message", "id": "msg-1", "stop_reason": None},
        {"type": "message", "model": None, "stop_reason": None, "id": "msg-1"},
        {"created": 1, "choices": [{"index": 0}]},
        [],
        "not-an-object",
        42,
    ],
)
def test_ignores_values_without_a_protocol_response_id(value):
    assert protocol.extract_response_id(value) is None


def test_blank_id_is_never_captured(messages):
    capture = protocol.ProtocolResponseCapture(model="m", stream=False)
    capture.observe(NS(object="chat.completion", id="   "))
    assert capture.response_id is None
    assert messages == []


def test_extraction_failure_is_swallowed(monkeypatch, messages):
    debug = []
    monkeypatch.setattr(
        protocol.logger, "debug", lambda message, *args, **kwargs: debug.append(message)
    )

    class Exploding:
        def __getattribute__(self, name):
            raise RuntimeError("boom")

    assert protocol.extract_response_id(Exploding()) is None
    assert debug


def test_has_field_supports_mappings_and_objects():
    assert protocol._has_field({"stop_reason": None}, "stop_reason")
    assert not protocol._has_field({}, "stop_reason")
    assert protocol._has_field(NS(stop_reason=None), "stop_reason")
    assert not protocol._has_field(NS(), "stop_reason")


# ---------------------------------------------------------------------------
# Capture publication
# ---------------------------------------------------------------------------


def test_capture_sets_span_attributes_and_logs_once(tracing, messages):
    tracer, exporter = tracing
    with tracer.start_as_current_span("call_llm") as owner:
        attempt = tracer.start_span("model_request")
        capture = protocol.ProtocolResponseCapture(
            model="test-model", stream=True, attempt_span=attempt
        )
        capture.observe(NS(type="message_start", message=NS(id="msg-1")))
        capture.observe(NS(type="message_start", message=NS(id="msg-1")))
        capture.observe(NS(object="chat.completion.chunk", id="other"))
        attempt.end()

    assert owner.attributes[ATTR] == "msg-1"
    assert attempt.attributes[ATTR] == "msg-1"
    assert len(messages) == 1
    assert "api=messages" in messages[0]
    assert "stream=True" in messages[0]
    assert "response_id=msg-1" in messages[0]


def test_observe_ignores_events_without_an_id(messages):
    capture = protocol.ProtocolResponseCapture(model="m", stream=True)
    for value in (
        NS(type="response.output_text.delta", delta="OK"),
        None,
        {},
        NS(type="response.created", response={}),
    ):
        capture.observe(value)
    assert capture.response_id is None
    assert messages == []


def test_log_sanitizes_control_characters_but_span_keeps_raw(tracing, messages):
    tracer, _ = tracing
    span = tracer.start_span("model_request")
    raw = "resp\nid\x00with\x1fcontrols"
    capture = protocol.ProtocolResponseCapture(
        model="m", stream=False, attempt_span=span
    )
    capture.observe(NS(object="response", id=raw))

    assert span.attributes[ATTR] == raw
    assert len(messages) == 1
    assert not any(char in messages[0] for char in "\n\x00\x1f")
    assert "resp?id?with?controls" in messages[0]


def test_log_truncates_long_ids(messages):
    raw = "i" * 200
    capture = protocol.ProtocolResponseCapture(model="m", stream=False)
    capture.observe(NS(object="response", id=raw))
    logged = messages[0].rsplit("response_id=", 1)[1]
    assert logged == "i" * protocol._LOG_ID_LIMIT


def test_capture_without_spans_still_logs(messages):
    capture = protocol.ProtocolResponseCapture(model="test-model", stream=False)
    capture.observe(NS(object="response", id="resp-1"))
    assert len(messages) == 1
    assert "api=responses" in messages[0]


def test_capture_attaches_to_adk_model_span(tracing, messages):
    tracer, _ = tracing
    with tracer.start_as_current_span("generate_content openai/test") as owner:
        protocol.ProtocolResponseCapture(model="m", stream=False).observe(
            NS(object="response", id="resp-1")
        )
    assert owner.attributes[ATTR] == "resp-1"


def test_capture_ignores_unrelated_caller_span(tracing, messages):
    tracer, _ = tracing
    with tracer.start_as_current_span("invoke_agent") as span:
        protocol.ProtocolResponseCapture(model="m", stream=False).observe(
            NS(object="response", id="resp-1")
        )
    assert ATTR not in span.attributes
    assert messages


def test_capture_clears_previous_attempt_value(tracing, messages):
    tracer, _ = tracing
    with tracer.start_as_current_span("call_llm") as owner:
        owner.set_attribute(ATTR, "stale")
        protocol.ProtocolResponseCapture(model="m", stream=False)
        assert ATTR not in owner.attributes


def test_capture_survives_attribute_cleanup_failure(monkeypatch, messages):
    debug = []
    monkeypatch.setattr(
        protocol.logger, "debug", lambda message, *args, **kwargs: debug.append(message)
    )

    def broken_clear(span, key):
        raise RuntimeError("span internals changed")

    monkeypatch.setattr(protocol, "_clear_attribute", broken_clear)
    capture = protocol.ProtocolResponseCapture(model="m", stream=False)
    assert capture.response_id is None
    assert debug


def test_capture_ignores_non_recording_spans(tracing, messages):
    tracer, _ = tracing
    span = tracer.start_span("model_request")
    span.end()
    capture = protocol.ProtocolResponseCapture(
        model="m", stream=False, attempt_span=span
    )
    capture.observe(NS(object="response", id="resp-1"))
    assert ATTR not in span.attributes
    assert messages


def test_capture_survives_span_attribute_failure(messages):
    class BrokenSpan:
        def is_recording(self):
            return True

        def set_attribute(self, *args, **kwargs):
            raise RuntimeError("span is closed")

    capture = protocol.ProtocolResponseCapture(
        model="m", stream=False, attempt_span=BrokenSpan()
    )
    capture.observe(NS(object="chat.completion", id="chat-1"))
    assert messages


def test_broken_owner_span_does_not_block_attempt_span(tracing, messages):
    class BrokenSpan:
        def is_recording(self):
            return True

        def set_attribute(self, *args, **kwargs):
            raise RuntimeError("span is closed")

    tracer, _ = tracing
    attempt = tracer.start_span("model_request")
    capture = protocol.ProtocolResponseCapture(model="m", stream=False)
    capture.owner_span = BrokenSpan()
    capture.attempt_span = attempt
    capture.observe(NS(object="response", id="resp-1"))
    assert attempt.attributes[ATTR] == "resp-1"
    assert messages


def test_clear_attribute_tolerates_non_sdk_span():
    class RecordingSpan:
        def is_recording(self):
            return True

    protocol._clear_attribute(RecordingSpan(), ATTR)


def test_clear_attribute_tolerates_span_without_attribute_state(tracing):
    tracer, _ = tracing
    span = tracer.start_span("model_request")
    span._attributes = None
    protocol._clear_attribute(span, ATTR)
    assert span.attributes == {}


def test_observe_response_requires_active_capture(messages):
    protocol.observe_response(NS(object="response", id="resp-1"))
    assert messages == []
    with protocol.ProtocolResponseCapture(model="m", stream=False):
        protocol.observe_response(NS(object="response", id="resp-1"))
    assert len(messages) == 1


# ---------------------------------------------------------------------------
# LiteLLM transports (Chat / Messages)
# ---------------------------------------------------------------------------


def _install_http(mock_http, *, body=None, sse=None):
    def handler(request):
        if sse is not None:
            return httpx.Response(
                200,
                request=request,
                headers={"content-type": "text/event-stream"},
                content=sse.encode(),
            )
        return httpx.Response(200, request=request, json=body)

    mock_http(handler)


async def _call_litellm(tracer, *, model, api_base, stream):
    client = TimedLiteLLMClient()
    with tracer.start_as_current_span("call_llm") as owner:
        response = await client.acompletion(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            api_key="test-key",
            api_base=api_base,
            stream=stream,
        )
        if stream:
            async for _ in response:
                pass
    return owner


@pytest.mark.asyncio
async def test_chat_non_stream_capture(tracing, messages, mock_http):
    tracer, _ = tracing
    _install_http(mock_http, body=_chat_body("chat-real"))
    owner = await _call_litellm(
        tracer, model="openai/test", api_base="https://mock.local/v1", stream=False
    )
    assert owner.attributes[ATTR] == "chat-real"
    assert any("api=chat" in message for message in messages)


@pytest.mark.asyncio
async def test_chat_stream_capture(tracing, messages, mock_http):
    tracer, _ = tracing
    sse = f"data: {json.dumps(_chat_chunk('chat-stream'))}\n\ndata: [DONE]\n\n"
    _install_http(mock_http, sse=sse)
    owner = await _call_litellm(
        tracer, model="openai/test", api_base="https://mock.local/v1", stream=True
    )
    assert owner.attributes[ATTR] == "chat-stream"
    assert any(
        "api=chat" in message and "stream=True" in message for message in messages
    )


@pytest.mark.asyncio
async def test_messages_non_stream_capture_uses_real_message_id(
    tracing, messages, mock_http
):
    tracer, _ = tracing
    _install_http(mock_http, body=_anthropic_body("msg-real"))
    owner = await _call_litellm(
        tracer, model="anthropic/test", api_base="https://mock.local", stream=False
    )
    assert owner.attributes[ATTR] == "msg-real"
    assert any("api=messages" in message for message in messages)


@pytest.mark.asyncio
async def test_messages_stream_capture_uses_message_start(tracing, messages, mock_http):
    tracer, _ = tracing
    _install_http(mock_http, sse=_anthropic_sse("msg-stream"))
    owner = await _call_litellm(
        tracer, model="anthropic/test", api_base="https://mock.local", stream=True
    )
    assert owner.attributes[ATTR] == "msg-stream"
    assert any(
        "api=messages" in message and "stream=True" in message for message in messages
    )


# ---------------------------------------------------------------------------
# Ark Responses transport
# ---------------------------------------------------------------------------


class _ArkStream:
    def __init__(self, events, error=None):
        self._events = events
        self._error = error
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._events:
            return self._events.pop(0)
        if self._error is not None:
            raise self._error
        raise StopAsyncIteration

    async def close(self):
        self.closed = True


def _responses_args():
    return {"model": "openai/test-model", "input": [], "api_key": "k"}


@pytest.mark.asyncio
async def test_ark_responses_non_stream_capture(tracing, messages, monkeypatch):
    tracer, _ = tracing
    model = ArkLlm(model="openai/test-model", api_key="k")

    async def aresponses(self, **kwargs):
        return _ark_response("resp-real")

    monkeypatch.setattr(ArkLlmClient, "aresponses", aresponses)
    with tracer.start_as_current_span("call_llm") as owner:
        _ = [
            item
            async for item in model.generate_content_via_responses(_responses_args())
        ]

    assert owner.attributes[ATTR] == "resp-real"
    assert any("api=responses" in message for message in messages)


@pytest.mark.asyncio
async def test_ark_responses_stream_capture(tracing, messages, monkeypatch):
    tracer, _ = tracing
    model = ArkLlm(model="openai/test-model", api_key="k")

    async def aresponses(self, **kwargs):
        return _ArkStream(
            [
                ResponseCreatedEvent(
                    type="response.created", response=_ark_response("resp-stream")
                ),
                ResponseTextDeltaEvent(
                    type="response.output_text.delta",
                    delta="OK",
                    item_id="message-id",
                    output_index=0,
                    content_index=0,
                ),
                ResponseCompletedEvent(
                    type="response.completed", response=_ark_response("resp-stream")
                ),
            ]
        )

    monkeypatch.setattr(ArkLlmClient, "aresponses", aresponses)
    with tracer.start_as_current_span("call_llm") as owner:
        _ = [
            item
            async for item in model.generate_content_via_responses(
                _responses_args(), stream=True
            )
        ]

    assert owner.attributes[ATTR] == "resp-stream"
    assert any("api=responses" in message for message in messages)


@pytest.mark.asyncio
async def test_stream_failure_keeps_first_observed_id(tracing, messages, monkeypatch):
    tracer, _ = tracing
    model = ArkLlm(model="openai/test-model", api_key="k")

    async def aresponses(self, **kwargs):
        return _ArkStream(
            [
                ResponseCreatedEvent(
                    type="response.created", response=_ark_response("resp-early")
                )
            ],
            error=RuntimeError("stream broke"),
        )

    monkeypatch.setattr(ArkLlmClient, "aresponses", aresponses)
    with tracer.start_as_current_span("call_llm") as owner:
        with pytest.raises(RuntimeError, match="stream broke"):
            async for _ in model.generate_content_via_responses(
                _responses_args(), stream=True
            ):
                pass

    assert owner.attributes[ATTR] == "resp-early"
    assert any("response_id=resp-early" in message for message in messages)


# ---------------------------------------------------------------------------
# Patch registration
# ---------------------------------------------------------------------------


def test_register_is_idempotent(monkeypatch):
    monkeypatch.setattr(protocol, "_patched", False)
    protocol.register_litellm_protocol_patches()
    first = ModelResponseIterator.chunk_parser
    protocol.register_litellm_protocol_patches()
    assert ModelResponseIterator.chunk_parser is first
    assert getattr(first, protocol._WRAPPED)


def test_register_rechecks_after_waiting_for_the_lock(monkeypatch):
    """A concurrent registration that won the race must not wrap twice."""

    monkeypatch.setattr(protocol, "_patched", False)

    class RacingLock:
        def __enter__(self):
            protocol._patched = True

        def __exit__(self, *exc_info):
            return False

    monkeypatch.setattr(protocol, "_register_lock", RacingLock())
    protocol.register_litellm_protocol_patches()
    assert protocol._patched is True


def test_register_tolerates_missing_litellm_seams(monkeypatch):
    monkeypatch.setattr(protocol, "_patched", False)
    monkeypatch.setitem(sys.modules, "litellm.llms.anthropic.chat.handler", None)
    protocol.register_litellm_protocol_patches()
    assert protocol._patched is False


def test_wrap_method_ignores_missing_attribute():
    owner = type("Owner", (), {})
    protocol._wrap_method(owner, "missing")
    assert not hasattr(owner, "missing")


def test_wrap_method_does_not_double_wrap():
    calls = []

    class Owner:
        def method(self, completion_response):
            calls.append(completion_response)

    protocol._wrap_method(Owner, "method")
    first = Owner.method
    protocol._wrap_method(Owner, "method")
    assert Owner.method is first
    Owner().method("original")
    assert calls == ["original"]


def test_no_capture_leaves_litellm_id_untouched(monkeypatch):
    """Installed seams are inert without an active capture context."""

    monkeypatch.setattr(protocol, "_patched", False)
    protocol.register_litellm_protocol_patches()
    protocol.observe_response({"type": "message_start", "message": {"id": "msg"}})
