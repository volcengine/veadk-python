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
from opentelemetry import metrics as metrics_api
from opentelemetry.metrics import _internal as metrics_internal
from opentelemetry.sdk import metrics as metrics_sdk
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.util._once import Once

from veadk.tools.skills_tools.skills_tool import SkillsTool
from veadk.tracing.telemetry import telemetry
from veadk.tracing.telemetry.exporters import (
    apmplus_exporter as apmplus_exporter_module,
)
from veadk.tracing.telemetry.exporters.apmplus_exporter import MeterUploader
from veadk.tracing.telemetry.metric_uploader import (
    MetricUploaderRegistry,
    metric_uploader_registry,
)


class FakeMetricUploader:
    def __init__(self, registration_key):
        self.registration_key = registration_key
        self.llm_calls = []
        self.tool_calls = []
        self.skill_calls = []
        self.force_flush_calls = 0
        self.shutdown_calls = 0

    def record_call_llm(self, *args):
        self.llm_calls.append(args)

    def record_tool_call(self, *args):
        self.tool_calls.append(args)

    def record_skill_call(self, *args):
        self.skill_calls.append(args)

    def force_flush(self):
        self.force_flush_calls += 1
        return True

    def shutdown(self):
        self.shutdown_calls += 1


@pytest.fixture(autouse=True)
def fresh_metric_uploader_registry():
    metric_uploader_registry.clear()
    yield
    metric_uploader_registry.clear()


@pytest.fixture
def preconfigured_zero_reader_meter_provider(monkeypatch):
    monkeypatch.setattr(metrics_internal, "_METER_PROVIDER", None)
    monkeypatch.setattr(metrics_internal, "_METER_PROVIDER_SET_ONCE", Once())
    provider = metrics_sdk.MeterProvider()
    metrics_api.set_meter_provider(provider)
    yield provider
    provider.shutdown()


@pytest.fixture
def preconfigured_meter_provider(monkeypatch):
    monkeypatch.setattr(metrics_internal, "_METER_PROVIDER", None)
    monkeypatch.setattr(metrics_internal, "_METER_PROVIDER_SET_ONCE", Once())
    reader = InMemoryMetricReader()
    provider = metrics_sdk.MeterProvider(metric_readers=[reader])
    metrics_api.set_meter_provider(provider)
    yield provider, reader
    provider.shutdown()


def test_meter_uploader_records_to_preconfigured_global_provider(
    monkeypatch,
    preconfigured_meter_provider,
):
    provider, reader = preconfigured_meter_provider

    def fail_if_apmplus_reader_is_created(**kwargs):
        raise AssertionError(
            "APMPlus must not add a metric pipeline to an existing global provider"
        )

    monkeypatch.setattr(
        apmplus_exporter_module,
        "OTLPMetricExporter",
        fail_if_apmplus_reader_is_created,
    )

    uploader = MeterUploader(
        name="test-meter",
        endpoint="http://localhost:4319",
        headers={"x-byteapm-appkey": "test"},
        resource_attributes={"service.name": "test-service"},
    )
    uploader.llm_invoke_counter.add(1)

    assert metrics_api.get_meter_provider() is provider
    assert uploader.provider is provider
    assert uploader.force_flush()
    assert reader.get_metrics_data() is not None

    uploader.shutdown()
    assert provider._shutdown is False


def test_meter_uploader_keeps_preconfigured_zero_reader_global_provider(
    monkeypatch,
    preconfigured_zero_reader_meter_provider,
):
    def fail_if_apmplus_reader_is_created(**kwargs):
        raise AssertionError(
            "APMPlus must not add a metric pipeline to an existing global provider"
        )

    monkeypatch.setattr(
        apmplus_exporter_module,
        "OTLPMetricExporter",
        fail_if_apmplus_reader_is_created,
    )

    uploader = MeterUploader(
        name="test-meter",
        endpoint="http://localhost:4319",
        headers={"x-byteapm-appkey": "test"},
        resource_attributes={"service.name": "test-service"},
    )
    uploader.llm_invoke_counter.add(1)

    assert uploader.provider is preconfigured_zero_reader_meter_provider
    assert uploader.provider._sdk_config.metric_readers == ()

    uploader.shutdown()
    assert preconfigured_zero_reader_meter_provider._shutdown is False


def test_meter_uploader_installs_apmplus_global_provider_when_none_exists(
    monkeypatch,
):
    monkeypatch.setattr(metrics_internal, "_METER_PROVIDER", None)
    monkeypatch.setattr(metrics_internal, "_METER_PROVIDER_SET_ONCE", Once())
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

    uploader = MeterUploader(
        name="test-meter",
        endpoint="http://localhost:4319",
        headers={"x-byteapm-appkey": "test"},
        resource_attributes={"service.name": "test-service"},
    )
    uploader.llm_invoke_counter.add(1)

    assert metrics_api.get_meter_provider() is uploader.provider
    assert len(uploader.provider._sdk_config.metric_readers) == 1
    assert exporter_kwargs["insecure"] is True
    assert uploader.force_flush()
    assert reader.get_metrics_data() is not None

    uploader.shutdown()


def test_registry_deduplicates_by_key_without_constructing_a_duplicate():
    registry = MetricUploaderRegistry()
    first = FakeMetricUploader(("apmplus", "same-destination"))

    assert registry.register(first) is first

    factory_calls = []
    resolved = registry.get_or_create(
        first.registration_key,
        lambda: factory_calls.append(True)
        or FakeMetricUploader(first.registration_key),
    )

    assert resolved is first
    assert factory_calls == []
    assert registry.uploaders == (first,)


def test_registry_fans_out_to_distinct_destinations_once():
    registry = MetricUploaderRegistry()
    first = FakeMetricUploader(("apmplus", "destination-a"))
    second = FakeMetricUploader(("apmplus", "destination-b"))
    duplicate = FakeMetricUploader(first.registration_key)

    registry.register(first)
    registry.register(second)
    assert registry.register(duplicate) is first

    registry.record_call_llm("context", "event", "request", "response")
    registry.record_tool_call("tool", {}, "event")
    registry.record_skill_call("span", "skill", "tool", None, "ok")

    assert len(first.llm_calls) == len(second.llm_calls) == 1
    assert len(first.tool_calls) == len(second.tool_calls) == 1
    assert len(first.skill_calls) == len(second.skill_calls) == 1
    assert duplicate.llm_calls == []
    assert duplicate.shutdown_calls == 1
    assert registry.force_flush()
    assert first.force_flush_calls == second.force_flush_calls == 1


def test_telemetry_and_skill_metrics_use_the_registry():
    uploader = FakeMetricUploader(("apmplus", "destination"))
    metric_uploader_registry.register(uploader)

    telemetry._upload_call_llm_metrics(None, "event", "request", "response")
    telemetry._upload_tool_call_metrics("tool", {}, "response")

    skills_tool = SkillsTool({})
    span = SimpleNamespace(start_time=time.time_ns())
    skills_tool._upload_skill_metrics(span, "missing-skill", "ok")

    assert len(uploader.llm_calls) == 1
    assert len(uploader.tool_calls) == 1
    assert len(uploader.skill_calls) == 1
