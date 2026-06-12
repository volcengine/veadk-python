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

from dataclasses import dataclass

from opentelemetry import context as context_api
from opentelemetry.sdk import trace as trace_sdk

from veadk.config import settings
from veadk.tracing.telemetry import telemetry
from veadk.tracing.telemetry.content_tracing import should_trace_content
from veadk.tracing.telemetry.exporters.apmplus_exporter import MeterUploader


@dataclass
class _FakePart:
    text: str | None = None
    function_call: object | None = None
    function_response: object | None = None
    inline_data: object | None = None


class _FakeContent:
    def __init__(self, role: str, parts: list[_FakePart]):
        self.role = role
        self.parts = parts

    def model_dump(self, exclude_none: bool = True):
        return {
            "role": self.role,
            "parts": [{"text": part.text} for part in self.parts if part.text],
        }


class _FakeConfig:
    max_output_tokens = 128
    temperature = 0.5
    top_p = 0.9
    system_instruction = "system secret"


class _FakeUsageMetadata:
    prompt_token_count = 11
    candidates_token_count = 7
    total_token_count = 18
    cached_content_token_count = 0


class _FakeLlmRequest:
    model = "test-model"
    config = _FakeConfig()
    contents = [_FakeContent("user", [_FakePart(text="user secret")])]
    tools_dict = {}

    def model_dump(self, exclude_none: bool = True):
        return {"model": self.model}


class _FakeLlmResponse:
    content = _FakeContent("model", [_FakePart(text="assistant secret")])
    usage_metadata = _FakeUsageMetadata()
    error_code = None

    def model_dump(self, exclude_none: bool = True):
        return {"content": self.content.model_dump(exclude_none=exclude_none)}


class _FakeSession:
    app_name = "app"
    id = "session"


class _FakeAgent:
    name = "agent"
    model_provider = "provider"
    model_name = "model"
    model_api_base = "http://model.test"


class _FakeInvocationContext:
    agent = _FakeAgent()
    app_name = "app"
    user_id = "user"
    session = _FakeSession()
    invocation_id = "invocation"
    run_config = None
    user_content = _FakeContent("user", [_FakePart(text="root user secret")])


class _FakeFunctionResponse:
    def model_dump(self):
        return {
            "id": "call-1",
            "name": "lookup",
            "response": {"result": "tool secret"},
        }


class _FakeFunctionResponseEvent:
    def get_function_responses(self):
        return [_FakeFunctionResponse()]


class _ExplodingFunctionResponseEvent:
    def get_function_responses(self):
        raise AssertionError("tool output content should not be read")


class _FakeTool:
    name = "lookup"
    description = "looks up private data"
    custom_metadata = {}


class _FakeMetricRecorder:
    def __init__(self):
        self.records = []

    def record(self, value, attributes=None):
        self.records.append((value, attributes))


def _start_test_span(name: str):
    provider = trace_sdk.TracerProvider()
    tracer = provider.get_tracer(__name__)
    return tracer.start_as_current_span(name)


def _event_names(span):
    return [event.name for event in span.events]


def setup_function():
    telemetry.meter_uploader = None


def test_trace_call_llm_records_content_by_default(monkeypatch):
    monkeypatch.delenv("OBSERVABILITY_OPENTELEMETRY_TRACE_CONTENT", raising=False)

    with _start_test_span("call_llm") as span:
        telemetry.trace_call_llm(
            _FakeInvocationContext(),
            "event-id",
            _FakeLlmRequest(),
            _FakeLlmResponse(),
        )

        assert span.attributes["gen_ai.request.model"] == "test-model"
        assert span.attributes["gen_ai.prompt.0.content"] == "user secret"
        assert span.attributes["gen_ai.completion.0.content"] == "assistant secret"
        assert "gen_ai.system.message" in _event_names(span)
        assert "gen_ai.user.message" in _event_names(span)
        assert "gen_ai.choice" in _event_names(span)


def test_content_tracing_uses_veadk_config_when_env_missing(monkeypatch):
    monkeypatch.delenv("OBSERVABILITY_OPENTELEMETRY_TRACE_CONTENT", raising=False)
    monkeypatch.setattr(settings.opentelemetry_config, "trace_content", False)

    assert should_trace_content() is False


def test_trace_call_llm_skips_content_when_env_false(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_OPENTELEMETRY_TRACE_CONTENT", "false")

    with _start_test_span("call_llm") as span:
        telemetry.trace_call_llm(
            _FakeInvocationContext(),
            "event-id",
            _FakeLlmRequest(),
            _FakeLlmResponse(),
        )

        assert span.attributes["gen_ai.request.model"] == "test-model"
        assert span.attributes["gen_ai.usage.total_tokens"] == 18
        assert not any(k.startswith("gen_ai.prompt.") for k in span.attributes)
        assert not any(k.startswith("gen_ai.completion.") for k in span.attributes)
        assert "gen_ai.system.message" not in _event_names(span)
        assert "gen_ai.user.message" not in _event_names(span)
        assert "gen_ai.tool.message" not in _event_names(span)
        assert "gen_ai.assistant.message" not in _event_names(span)
        assert "gen_ai.choice" not in _event_names(span)


def test_trace_tool_call_skips_content_when_env_false(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_OPENTELEMETRY_TRACE_CONTENT", "false")

    with _start_test_span("execute_tool lookup") as span:
        telemetry.trace_tool_call(
            _FakeTool(),
            {"query": "tool input secret"},
            _FakeFunctionResponseEvent(),
        )

        assert span.attributes["gen_ai.operation.name"] == "execute_tool"
        assert span.attributes["gen_ai.tool.name"] == "lookup"
        assert span.attributes["gen_ai.span.kind"] == "tool"
        assert "gen_ai.tool.input" not in span.attributes
        assert "gen_ai.tool.output" not in span.attributes
        assert "cozeloop.input" not in span.attributes
        assert "cozeloop.output" not in span.attributes
        assert "gen_ai.input" not in span.attributes
        assert "gen_ai.output" not in span.attributes


def test_apmplus_tool_metrics_skip_token_usage_when_tool_content_missing():
    meter_uploader = object.__new__(MeterUploader)
    meter_uploader.apmplus_span_latency = _FakeMetricRecorder()
    meter_uploader.apmplus_tool_token_usage = _FakeMetricRecorder()

    with _start_test_span("execute_tool lookup"):
        meter_uploader.record_tool_call(
            _FakeTool(),
            {"query": "tool input secret"},
            _ExplodingFunctionResponseEvent(),
        )

    assert len(meter_uploader.apmplus_span_latency.records) == 1
    assert meter_uploader.apmplus_tool_token_usage.records == []


def test_agent_root_span_skips_content_when_env_false(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_OPENTELEMETRY_TRACE_CONTENT", "false")

    with _start_test_span("invocation") as span:
        telemetry._set_agent_input_attribute(span, _FakeInvocationContext())
        telemetry._set_agent_output_attribute(span, _FakeLlmResponse())

        assert "gen_ai.input" not in span.attributes
        assert "gen_ai.output" not in span.attributes
        assert "gen_ai.user.message" not in _event_names(span)
        assert "gen_ai.choice" not in _event_names(span)


def test_content_tracing_context_override_allows_content(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_OPENTELEMETRY_TRACE_CONTENT", "false")
    token = context_api.attach(
        context_api.set_value("override_enable_content_tracing", True)
    )
    try:
        with _start_test_span("call_llm") as span:
            telemetry.trace_call_llm(
                _FakeInvocationContext(),
                "event-id",
                _FakeLlmRequest(),
                _FakeLlmResponse(),
            )

            assert span.attributes["gen_ai.prompt.0.content"] == "user secret"
            assert span.attributes["gen_ai.completion.0.content"] == "assistant secret"
    finally:
        context_api.detach(token)
