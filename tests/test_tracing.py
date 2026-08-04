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


from types import SimpleNamespace

import pytest
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter as OTelInMemorySpanExporter,
)
from opentelemetry.util._once import Once

from veadk.agent import Agent
from veadk.tracing.telemetry import (
    opentelemetry_tracer as opentelemetry_tracer_module,
)
from veadk.tracing.telemetry import telemetry as telemetry_module
from veadk.tracing.telemetry.exporters import (
    apmplus_exporter as apmplus_exporter_module,
)
from veadk.tracing.telemetry.exporters.apmplus_exporter import (
    APMPlusExporter,
    APMPlusExporterConfig,
)
from veadk.tracing.telemetry.exporters.cozeloop_exporter import (
    CozeloopExporter,
    CozeloopExporterConfig,
)
from veadk.tracing.telemetry.exporters.tls_exporter import (
    TLSExporter,
    TLSExporterConfig,
)
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

APP_NAME = "app"
USER_ID = "testuser"
SESSION_ID = "testsession"


def init_exporters():
    cozeloop_exporter = CozeloopExporter(
        config=CozeloopExporterConfig(
            endpoint="http://localhost:8000",
            token="test_token",
            space_id="test_space_id",
        )
    )

    apmplus_exporter = init_apmplus_exporter()

    tls_exporter = TLSExporter(
        config=TLSExporterConfig(
            endpoint="http://localhost:8000",
            region="test_region",
            topic_id="test_topic_id",
            access_key="test_access_key",
            secret_key="test_secret_key",
        )
    )
    return [cozeloop_exporter, apmplus_exporter, tls_exporter]


def init_apmplus_exporter():
    return APMPlusExporter(
        config=APMPlusExporterConfig(
            endpoint="http://localhost:8000",
            app_key="test_app_key",
            service_name="test_service_name",
        )
    )


def gen_span_processor(endpoint: str):
    otlp_exporter = OTLPSpanExporter(
        endpoint=endpoint,
    )
    span_processor = BatchSpanProcessor(otlp_exporter)
    return span_processor


@pytest.fixture
def fresh_global_tracer_provider(monkeypatch):
    """Give each test an isolated OpenTelemetry global provider."""
    monkeypatch.setattr(trace_api, "_TRACER_PROVIDER", None)
    monkeypatch.setattr(trace_api, "_TRACER_PROVIDER_SET_ONCE", Once())

    yield

    tracer_provider = trace_api.get_tracer_provider()
    if isinstance(tracer_provider, trace_sdk.TracerProvider):
        tracer_provider.shutdown()


@pytest.fixture
def controlled_apmplus_exporter(monkeypatch):
    """Provide an APMPlus exporter without network or global meter side effects."""
    constructed_exporters = []
    monkeypatch.setattr(telemetry_module, "meter_uploader", None)

    class ControlledAPMPlusExporter(APMPlusExporter):
        def __init__(self):
            super().__init__(
                config=APMPlusExporterConfig(
                    endpoint="http://localhost:8000",
                    app_key="test_app_key",
                    service_name="test_service_name",
                )
            )

        def model_post_init(self, context):
            self._exporter = OTelInMemorySpanExporter()
            self.processor = SimpleSpanProcessor(self._exporter)
            self.meter_uploader = object()
            constructed_exporters.append(self)

    monkeypatch.setattr(
        apmplus_exporter_module,
        "APMPlusExporter",
        ControlledAPMPlusExporter,
    )
    monkeypatch.setattr(
        opentelemetry_tracer_module,
        "APMPlusExporter",
        ControlledAPMPlusExporter,
    )
    return ControlledAPMPlusExporter, constructed_exporters


@pytest.mark.parametrize(
    "enable_apmplus",
    [False, True],
    ids=["env-disabled", "env-enabled"],
)
@pytest.mark.parametrize(
    "provider_preconfigured",
    [False, True],
    ids=["provider-proxy", "provider-preconfigured"],
)
@pytest.mark.parametrize(
    "manual_exporter",
    [False, True],
    ids=["no-manual-exporter", "manual-exporter"],
)
def test_apmplus_enable_provider_and_manual_exporter_matrix(
    fresh_global_tracer_provider,
    controlled_apmplus_exporter,
    monkeypatch,
    enable_apmplus,
    provider_preconfigured,
    manual_exporter,
):
    """Validate env, global provider, and explicit exporter independently."""
    controlled_exporter_class, constructed_exporters = controlled_apmplus_exporter
    monkeypatch.setenv("ENABLE_APMPLUS", str(enable_apmplus).lower())
    monkeypatch.setenv("ENABLE_COZELOOP", "false")
    monkeypatch.setenv("ENABLE_TLS", "false")

    initial_provider = trace_api.get_tracer_provider()
    if provider_preconfigured:
        initial_provider = trace_sdk.TracerProvider()
        trace_api.set_tracer_provider(initial_provider)

    tracers = []
    if manual_exporter:
        tracers.append(OpentelemetryTracer(exporters=[controlled_exporter_class()]))

    agent = SimpleNamespace(tracers=tracers)
    Agent._prepare_tracers(agent)

    should_create_tracer = manual_exporter or enable_apmplus
    assert len(agent.tracers) == int(should_create_tracer)

    final_provider = trace_api.get_tracer_provider()
    if not should_create_tracer:
        assert final_provider is initial_provider
        assert constructed_exporters == []
        assert telemetry_module.meter_uploader is None
        return

    tracer = agent.tracers[0]
    assert isinstance(final_provider, trace_sdk.TracerProvider)
    if provider_preconfigured:
        assert final_provider is initial_provider
    else:
        assert final_provider is not initial_provider

    should_register_apmplus = not provider_preconfigured and (
        manual_exporter or enable_apmplus
    )
    should_construct_apmplus = manual_exporter or enable_apmplus
    assert len(constructed_exporters) == int(should_construct_apmplus)
    assert sum(
        isinstance(exporter, controlled_exporter_class) for exporter in tracer.exporters
    ) == int(should_construct_apmplus)

    span_processors = final_provider._active_span_processor._span_processors
    registered_apmplus_processors = sum(
        any(processor is exporter.processor for processor in span_processors)
        for exporter in constructed_exporters
    )
    assert registered_apmplus_processors == int(should_register_apmplus)
    assert len(span_processors) == 1 + int(should_register_apmplus)
    assert tracer.apmplus_managed_externally is provider_preconfigured
    expected_meter_uploader = (
        constructed_exporters[0].meter_uploader if should_construct_apmplus else None
    )
    assert telemetry_module.meter_uploader is expected_meter_uploader


def test_add_exporter_registers_after_tracer_initialization(
    fresh_global_tracer_provider,
):
    tracer = OpentelemetryTracer()
    exporter = init_exporters()[1]

    tracer.add_exporter(exporter)

    tracer_provider = trace_api.get_tracer_provider()
    span_processors = tracer_provider._active_span_processor._span_processors
    assert exporter in tracer.exporters
    assert exporter.processor in span_processors
    assert exporter.processor in tracer._processors


def test_add_exporter_is_idempotent(fresh_global_tracer_provider):
    tracer = OpentelemetryTracer()
    exporter = init_exporters()[1]

    tracer.add_exporter(exporter)
    tracer.add_exporter(exporter)

    tracer_provider = trace_api.get_tracer_provider()
    span_processors = tracer_provider._active_span_processor._span_processors
    assert sum(processor is exporter.processor for processor in span_processors) == 1
    assert sum(processor is exporter.processor for processor in tracer._processors) == 1


def test_tracing_registers_apmplus_without_global_provider(
    fresh_global_tracer_provider,
):
    apmplus_exporter = init_apmplus_exporter()

    tracer = OpentelemetryTracer(exporters=[apmplus_exporter])
    tracer_provider = trace_api.get_tracer_provider()
    span_processors = tracer_provider._active_span_processor._span_processors

    assert apmplus_exporter in tracer.exporters
    assert apmplus_exporter.processor in span_processors


def test_tracing_skips_apmplus_for_preconfigured_provider(
    fresh_global_tracer_provider,
):
    tracer_provider = trace_sdk.TracerProvider()
    trace_api.set_tracer_provider(tracer_provider)
    apmplus_exporter = init_apmplus_exporter()

    tracer = OpentelemetryTracer(exporters=[apmplus_exporter])
    global_tracer_provider = trace_api.get_tracer_provider()
    span_processors = global_tracer_provider._active_span_processor._span_processors

    assert global_tracer_provider is tracer_provider
    assert apmplus_exporter in tracer.exporters
    assert apmplus_exporter.processor not in span_processors
    assert len(span_processors) == 1  # VeADK in-memory processor only
    assert telemetry_module.meter_uploader is apmplus_exporter.meter_uploader


def test_add_exporter_skips_apmplus_for_preconfigured_provider(
    fresh_global_tracer_provider,
):
    tracer_provider = trace_sdk.TracerProvider()
    trace_api.set_tracer_provider(tracer_provider)
    tracer = OpentelemetryTracer()
    apmplus_exporter = init_apmplus_exporter()

    tracer.add_exporter(apmplus_exporter)

    span_processors = tracer_provider._active_span_processor._span_processors
    assert apmplus_exporter in tracer.exporters
    assert apmplus_exporter.processor not in span_processors
    assert len(span_processors) == 1  # VeADK in-memory processor only
    assert telemetry_module.meter_uploader is apmplus_exporter.meter_uploader


def test_agent_env_keeps_metrics_only_apmplus_for_preconfigured_provider(
    fresh_global_tracer_provider,
    controlled_apmplus_exporter,
    monkeypatch,
):
    controlled_exporter_class, constructed_exporters = controlled_apmplus_exporter
    tracer_provider = trace_sdk.TracerProvider()
    trace_api.set_tracer_provider(tracer_provider)
    tracer = OpentelemetryTracer()
    monkeypatch.setenv("ENABLE_APMPLUS", "true")
    monkeypatch.setenv("ENABLE_COZELOOP", "false")
    monkeypatch.setenv("ENABLE_TLS", "false")

    Agent._prepare_tracers(SimpleNamespace(tracers=[tracer]))

    span_processors = tracer_provider._active_span_processor._span_processors
    assert len(constructed_exporters) == 1
    exporter = constructed_exporters[0]
    assert isinstance(exporter, controlled_exporter_class)
    assert exporter in tracer.exporters
    assert exporter.processor not in span_processors
    assert telemetry_module.meter_uploader is exporter.meter_uploader
    assert len(span_processors) == 1  # VeADK in-memory processor only


@pytest.mark.asyncio
async def test_tracing(fresh_global_tracer_provider):
    exporters = init_exporters()
    tracer = OpentelemetryTracer(exporters=exporters)

    assert len(tracer.exporters) == 4  # with extra 1 built-in exporters

    # TODO: Ensure the tracing provider is set correctly after loading SDK


@pytest.mark.asyncio
async def test_tracing_with_global_provider(fresh_global_tracer_provider):
    exporters = init_exporters()
    # set global tracer provider before init OpentelemetryTracer
    trace_api.set_tracer_provider(trace_sdk.TracerProvider())
    tracer_provider = trace_api.get_tracer_provider()
    tracer_provider.add_span_processor(gen_span_processor("http://localhost:8000"))
    trace_api.set_tracer_provider(tracer_provider)
    tracer = OpentelemetryTracer(exporters=exporters)

    # APMPlus is retained for metrics but its span processor is not registered.
    assert len(tracer.exporters) == 4


@pytest.mark.asyncio
async def test_tracing_with_apmplus_global_provider(fresh_global_tracer_provider):
    exporters = init_exporters()
    # add apmplus exporter to global tracer provider before init OpentelemetryTracer
    trace_api.set_tracer_provider(trace_sdk.TracerProvider())
    tracer_provider = trace_api.get_tracer_provider()
    tracer_provider.add_span_processor(gen_span_processor("http://apmplus-region.com"))

    # init OpentelemetryTracer
    tracer = OpentelemetryTracer(exporters=exporters)

    # APMPlus is retained for metrics but its span processor is not registered.
    assert len(tracer.exporters) == 4  # with extra 1 built-in exporters
