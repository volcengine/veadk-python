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


import pytest
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.sdk.trace.export import BatchSpanProcessor

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

    apmplus_exporter = APMPlusExporter(
        config=APMPlusExporterConfig(
            endpoint="http://localhost:8000",
            app_key="test_app_key",
            service_name="test_service_name",
        )
    )

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


def gen_span_processor(endpoint: str):
    otlp_exporter = OTLPSpanExporter(
        endpoint=endpoint,
    )
    span_processor = BatchSpanProcessor(otlp_exporter)
    return span_processor


@pytest.mark.asyncio
async def test_tracing():
    exporters = init_exporters()
    tracer = OpentelemetryTracer(exporters=exporters)

    assert len(tracer.exporters) == 5  # with extra 2 built-in exporters

    # TODO: Ensure the tracing provider is set correctly after loading SDK
    # TODO: Ensure the tracing provider is set correctly after loading SDK
    # TODO: Ensure the tracing provider is set correctly after loading SDK


@pytest.mark.asyncio
async def test_tracing_with_global_provider():
    exporters = init_exporters()
    # set global tracer provider before init OpentelemetryTracer
    trace_api.set_tracer_provider(trace_sdk.TracerProvider())
    tracer_provider = trace_api.get_tracer_provider()
    tracer_provider.add_span_processor(gen_span_processor("http://localhost:8000"))
    trace_api.set_tracer_provider(tracer_provider)
    #
    tracer = OpentelemetryTracer(exporters=exporters)

    assert len(tracer.exporters) == 5  # with extra 2 built-in exporters


@pytest.mark.asyncio
async def test_tracing_with_apmplus_global_provider():
    exporters = init_exporters()
    # add apmplus exporter to global tracer provider before init OpentelemetryTracer
    trace_api.set_tracer_provider(trace_sdk.TracerProvider())
    tracer_provider = trace_api.get_tracer_provider()
    tracer_provider.add_span_processor(gen_span_processor("http://apmplus-region.com"))

    # init OpentelemetryTracer
    tracer = OpentelemetryTracer(exporters=exporters)

    # apmplus exporter won't init again
    assert len(tracer.exporters) == 4  # with extra 2 built-in exporters
