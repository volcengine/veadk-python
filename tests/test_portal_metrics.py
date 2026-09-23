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

import time
from types import SimpleNamespace

import pytest
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from opentelemetry import metrics as metrics_api
from opentelemetry.metrics import _internal as metrics_internal
from opentelemetry.sdk import metrics as metrics_sdk
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.util._once import Once

from veadk.tools.skills_tools.skills_tool import SkillsTool
from veadk.tracing.telemetry import portal_metrics, telemetry
from veadk.tracing.telemetry.exporters import (
    apmplus_exporter as apmplus_exporter_module,
)
from veadk.tracing.telemetry.exporters.apmplus_exporter import (
    APMPlusExporter,
    APMPlusExporterConfig,
    ensure_apmplus_meter_provider,
)
from veadk.tracing.telemetry.portal_metrics import PortalMetricRecorder


class FakePortalMetricRecorder:
    def __init__(self):
        self.llm_calls = []
        self.tool_calls = []
        self.skill_calls = []

    def record_call_llm(self, *args):
        self.llm_calls.append(args)

    def record_tool_call(self, *args):
        self.tool_calls.append(args)

    def record_skill_call(self, *args):
        self.skill_calls.append(args)


@pytest.fixture
def fresh_global_meter_provider(monkeypatch):
    proxy_provider = metrics_internal._PROXY_METER_PROVIDER
    monkeypatch.setattr(metrics_internal, "_METER_PROVIDER", None)
    monkeypatch.setattr(metrics_internal, "_METER_PROVIDER_SET_ONCE", Once())
    monkeypatch.setattr(proxy_provider, "_real_meter_provider", None)
    monkeypatch.setattr(proxy_provider, "_meters", [])

    yield

    provider = metrics_internal._METER_PROVIDER
    if isinstance(provider, metrics_sdk.MeterProvider):
        provider.shutdown()


def test_portal_metrics_are_recorded_without_apmplus_exporter(
    monkeypatch,
):
    recorder = FakePortalMetricRecorder()
    monkeypatch.setattr(portal_metrics, "portal_metric_recorder", recorder)

    telemetry._upload_call_llm_metrics(None, "event", "request", "response")
    telemetry._upload_tool_call_metrics("tool", {}, "response")

    skills_tool = SkillsTool({})
    span = SimpleNamespace(start_time=time.time_ns())
    skills_tool._upload_skill_metrics(span, "missing-skill", "ok")

    assert len(recorder.llm_calls) == 1
    assert len(recorder.tool_calls) == 1
    assert len(recorder.skill_calls) == 1


def test_portal_recorder_uses_default_proxy_without_installing_provider(
    fresh_global_meter_provider,
):
    default_provider = metrics_api.get_meter_provider()

    recorder = PortalMetricRecorder(name="test-default-proxy")
    recorder.llm_invoke_counter.add(1)

    assert isinstance(default_provider, metrics_internal._ProxyMeterProvider)
    assert metrics_api.get_meter_provider() is default_provider


def test_portal_recorder_uses_preconfigured_global_provider(
    fresh_global_meter_provider,
):
    reader = InMemoryMetricReader()
    provider = metrics_sdk.MeterProvider(metric_readers=[reader])
    metrics_api.set_meter_provider(provider)

    recorder = PortalMetricRecorder(name="test-preconfigured-provider")
    recorder.llm_invoke_counter.add(1)
    provider.force_flush()

    assert recorder.provider is provider
    assert reader.get_metrics_data() is not None


def test_proxy_instruments_follow_provider_installed_later(
    fresh_global_meter_provider,
):
    recorder = PortalMetricRecorder(name="test-late-provider")
    recorder.llm_invoke_counter.add(1, {"phase": "before"})

    reader = InMemoryMetricReader()
    provider = metrics_sdk.MeterProvider(metric_readers=[reader])
    metrics_api.set_meter_provider(provider)
    recorder.llm_invoke_counter.add(2, {"phase": "after"})
    provider.force_flush()

    metrics_data = reader.get_metrics_data()
    points = [
        point
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name == "gen_ai.chat.count"
        for point in metric.data.data_points
    ]

    assert [(dict(point.attributes), point.value) for point in points] == [
        ({"phase": "after"}, 2)
    ]


@pytest.mark.parametrize(
    "server_address",
    [
        "https://ark.cn-beijing.volces.com/api/v3/",
        "https://ark.ap-southeast.bytepluses.com/api/v3",
    ],
    ids=["volcengine", "byteplus"],
)
@pytest.mark.parametrize("streaming_mode", [StreamingMode.NONE, StreamingMode.SSE])
@pytest.mark.parametrize("cached_tokens", [600, 0, None])
def test_cache_read_token_metrics_preserve_input_usage(
    fresh_global_meter_provider, server_address, streaming_mode, cached_tokens
):
    reader = InMemoryMetricReader()
    metrics_api.set_meter_provider(metrics_sdk.MeterProvider(metric_readers=[reader]))
    recorder = PortalMetricRecorder(name="test-cache-read")
    context = SimpleNamespace(
        agent=SimpleNamespace(model_api_base=server_address),
        run_config=RunConfig(streaming_mode=streaming_mode),
    )
    request = LlmRequest(model="test-model")

    if streaming_mode == StreamingMode.SSE:
        recorder.record_call_llm(context, "partial", request, LlmResponse(partial=True))

    recorder.record_call_llm(
        context,
        "final",
        request,
        LlmResponse(
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=1000,
                candidates_token_count=200,
                total_token_count=1200,
                cached_content_token_count=cached_tokens,
            ),
        ),
    )

    metrics_data = reader.get_metrics_data()
    recorded_metrics = {
        metric.name: list(metric.data.data_points)
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }
    points = recorded_metrics["gen_ai.client.token.usage"]
    expected = {"input": 1000, "output": 200}
    if cached_tokens is not None:
        expected["cache_read"] = cached_tokens
    assert {point.attributes["gen_ai_token_type"]: point.sum for point in points} == (
        expected
    )
    assert len(points) == len(expected)
    for point in points:
        assert point.count == 1
        assert point.attributes["server_address"] == server_address
        assert point.attributes["stream"] == (streaming_mode == StreamingMode.SSE)
        assert point.attributes["gen_ai_response_model"] == "test-model"
    assert [point.value for point in recorded_metrics["gen_ai.chat.count"]] == [1]


def test_missing_usage_does_not_record_token_metrics(fresh_global_meter_provider):
    reader = InMemoryMetricReader()
    metrics_api.set_meter_provider(metrics_sdk.MeterProvider(metric_readers=[reader]))
    recorder = PortalMetricRecorder(name="test-missing-usage")
    context = SimpleNamespace(agent=SimpleNamespace(), run_config=None)

    recorder.record_call_llm(context, "event", LlmRequest(), LlmResponse())

    assert reader.get_metrics_data() is None


def test_apmplus_reuses_preconfigured_global_provider(
    fresh_global_meter_provider,
    monkeypatch,
):
    provider = metrics_sdk.MeterProvider()
    metrics_api.set_meter_provider(provider)

    def fail_if_exporter_is_created(**kwargs):
        raise AssertionError("APMPlus must not modify an existing global provider")

    monkeypatch.setattr(
        apmplus_exporter_module,
        "OTLPMetricExporter",
        fail_if_exporter_is_created,
    )

    resolved_provider = ensure_apmplus_meter_provider(
        endpoint="http://localhost:4319",
        headers={"x-byteapm-appkey": "test"},
        resource_attributes={"service.name": "test-service"},
    )

    assert resolved_provider is provider
    assert provider._sdk_config.metric_readers == ()


def test_apmplus_installs_global_provider_when_none_exists(
    fresh_global_meter_provider,
    monkeypatch,
):
    reader = InMemoryMetricReader()
    exporter_kwargs = {}
    monkeypatch.setattr(
        apmplus_exporter_module,
        "OTLPMetricExporter",
        lambda **kwargs: exporter_kwargs.update(kwargs) or object(),
    )
    monkeypatch.setattr(
        apmplus_exporter_module,
        "PeriodicExportingMetricReader",
        lambda exporter: reader,
    )

    provider = ensure_apmplus_meter_provider(
        endpoint="http://localhost:4319",
        headers={"x-byteapm-appkey": "test"},
        resource_attributes={"service.name": "test-service"},
    )

    assert metrics_api.get_meter_provider() is provider
    assert provider._sdk_config.metric_readers == [reader]
    assert exporter_kwargs == {
        "endpoint": "http://localhost:4319",
        "headers": {"x-byteapm-appkey": "test"},
        "insecure": True,
    }


def test_apmplus_exporter_only_bootstraps_meter_provider(monkeypatch):
    bootstrap_calls = []
    monkeypatch.setattr(
        apmplus_exporter_module,
        "ensure_apmplus_meter_provider",
        lambda **kwargs: bootstrap_calls.append(kwargs),
    )

    APMPlusExporter(
        config=APMPlusExporterConfig(
            endpoint="http://localhost:4319",
            app_key="test-app-key",
            service_name="test-service",
        )
    )

    assert bootstrap_calls == [
        {
            "endpoint": "http://localhost:4319",
            "headers": {"x-byteapm-appkey": "test-app-key"},
            "resource_attributes": {"service.name": "test-service"},
        }
    ]
