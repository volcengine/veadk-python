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

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field
from typing_extensions import override

from veadk.config import getenv
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.tracing.telemetry.metrics.opentelemetry_metrics import MeterContext
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class APMPlusExporterConfig(BaseModel):
    endpoint: str = Field(
        default_factory=lambda: getenv(
            "OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT",
            "http://apmplus-cn-beijing.volces.com:4317",
        ),
    )
    app_key: str = Field(
        default_factory=lambda: getenv("OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY"),
    )
    service_name: str = Field(
        default_factory=lambda: getenv(
            "OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME",
            "veadk_tracing_service",
        ),
        description="Service name shown in APMPlus frontend.",
    )


class APMPlusExporter(BaseModel, BaseExporter):
    config: APMPlusExporterConfig = Field(default_factory=APMPlusExporterConfig)

    @override
    def get_processor(self):
        resource_attributes = {
            "service.name": self.config.service_name,
        }

        headers = {
            "x-byteapm-appkey": self.config.app_key,
        }
        exporter = OTLPSpanExporter(
            endpoint=self.config.endpoint, insecure=True, headers=headers
        )
        self._real_exporter = exporter
        processor = BatchSpanProcessor(exporter)
        return processor, resource_attributes

    def export(self):
        self._real_exporter.force_flush()
        logger.info(
            f"APMPlusExporter exports data to {self.config.endpoint}, service name: {self.config.service_name}"
        )

    @override
    def get_meter_context(self) -> MeterContext:
        resource_attributes = {
            "service.name": self.config.service_name,
        }
        endpoint = self.config.endpoint
        headers = {
            "x-byteapm-appkey": self.config.app_key,
        }

        resource = Resource.create(resource_attributes)
        exporter = OTLPMetricExporter(endpoint=endpoint, headers=headers)
        metric_reader = PeriodicExportingMetricReader(exporter)
        provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
        metrics.set_meter_provider(provider)
        meter = metrics.get_meter("my.meter.name")
        meter_context = MeterContext(
            meter=meter,
            provider=provider,
            reader=metric_reader,
        )
        return meter_context
