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
    "manual_exporter",
    [False, True],
    ids=["no-manual-exporter", "manual-exporter"],
)
def test_apmplus_preconfigured_provider_matrix(
    fresh_global_tracer_provider,
    controlled_apmplus_exporter,
    monkeypatch,
    enable_apmplus,
    manual_exporter,
):
    """A preconfigured provider owns traces; env exporter retains metrics."""
    controlled_exporter_class, constructed_exporters = controlled_apmplus_exporter
    monkeypatch.setenv("ENABLE_APMPLUS", str(enable_apmplus).lower())
    monkeypatch.setenv("ENABLE_COZELOOP", "false")
    monkeypatch.setenv("ENABLE_TLS", "false")

    tracer_provider = trace_sdk.TracerProvider()
    trace_api.set_tracer_provider(tracer_provider)

    tracers = []
    if manual_exporter:
        tracers.append(OpentelemetryTracer(exporters=[controlled_exporter_class()]))

    agent = SimpleNamespace(tracers=tracers)
    Agent._prepare_tracers(agent)

    should_create_tracer = manual_exporter or enable_apmplus
    assert len(agent.tracers) == int(should_create_tracer)
    assert trace_api.get_tracer_provider() is tracer_provider
    assert len(constructed_exporters) == int(manual_exporter) + int(enable_apmplus)

    span_processors = tracer_provider._active_span_processor._span_processors
    if not should_create_tracer:
        assert span_processors == ()
        return

    tracer = agent.tracers[0]
    assert sum(
        isinstance(exporter, controlled_exporter_class) for exporter in tracer.exporters
    ) == int(enable_apmplus)
    assert all(
        exporter.processor not in span_processors for exporter in constructed_exporters
    )
    assert len(span_processors) == 1  # VeADK in-memory processor only
    assert tracer.apmplus_managed_externally is True
    expected_meter_uploader = (
        constructed_exporters[-1].meter_uploader if enable_apmplus else None
    )
    assert telemetry_module.meter_uploader is expected_meter_uploader


def test_tracing_registers_apmplus_without_global_provider(
    fresh_global_tracer_provider,
):
    apmplus_exporter = init_apmplus_exporter()

    tracer = OpentelemetryTracer(exporters=[apmplus_exporter])
    tracer_provider = trace_api.get_tracer_provider()
    span_processors = tracer_provider._active_span_processor._span_processors

    assert apmplus_exporter in tracer.exporters
    assert apmplus_exporter.processor in span_processors


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
    #
    tracer = OpentelemetryTracer(exporters=exporters)

    assert len(tracer.exporters) == 3  # APMPlus is managed by the existing provider


@pytest.mark.asyncio
async def test_tracing_with_apmplus_global_provider(fresh_global_tracer_provider):
    exporters = init_exporters()
    # add apmplus exporter to global tracer provider before init OpentelemetryTracer
    trace_api.set_tracer_provider(trace_sdk.TracerProvider())
    tracer_provider = trace_api.get_tracer_provider()
    tracer_provider.add_span_processor(gen_span_processor("http://apmplus-region.com"))

    # init OpentelemetryTracer
    tracer = OpentelemetryTracer(exporters=exporters)

    # apmplus exporter won't init again, so there are cozeloop, tls, in_memory exporter
    assert len(tracer.exporters) == 3  # with extra 1 built-in exporters
