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


@pytest.mark.asyncio
async def test_tracing():
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

    exporters = [cozeloop_exporter, apmplus_exporter, tls_exporter]
    tracer = OpentelemetryTracer(exporters=exporters)

    assert len(tracer.exporters) == 5  # with extra 2 built-in exporters

    # TODO: Ensure the tracing provider is set correctly after loading SDK
    # TODO: Ensure the tracing provider is set correctly after loading SDK
    # TODO: Ensure the tracing provider is set correctly after loading SDK
