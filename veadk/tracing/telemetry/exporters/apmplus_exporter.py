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

from typing import Any

from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from opentelemetry import metrics
from opentelemetry import metrics as metrics_api
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics._internal import Meter
from opentelemetry.sdk import metrics as metrics_sdk
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field
from typing_extensions import override

from veadk.config import settings
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class MeterUploader:
    def __init__(
        self, name: str, endpoint: str, headers: dict, resource_attributes: dict
    ) -> None:
        # global_metrics_provider -> global_tracer_provider
        # exporter -> exporter
        # metric_reader -> processor
        global_metrics_provider = metrics_api.get_meter_provider()

        # 1. init resource
        if hasattr(global_metrics_provider, "_sdk_config"):
            global_resource = global_metrics_provider._sdk_config.resource  # type: ignore
        else:
            global_resource = Resource.create()

        resource = global_resource.merge(Resource.create(resource_attributes))

        # 2. init exporter and reader
        exporter = OTLPMetricExporter(endpoint=endpoint, headers=headers)
        metric_reader = PeriodicExportingMetricReader(exporter)

        metrics_api.set_meter_provider(
            metrics_sdk.MeterProvider(metric_readers=[metric_reader], resource=resource)
        )

        # 3. init meter
        self.meter: Meter = metrics.get_meter(name=name)

        # create meter attributes
        self.llm_invoke_counter = self.meter.create_counter(
            name="gen_ai.chat.count",
            description="Number of LLM invocations",
            unit="count",
        )
        self.token_usage = self.meter.create_histogram(
            name="gen_ai.client.token.usage",
            description="Token consumption of LLM invocations",
            unit="count",
        )

    def record(self, llm_request: LlmRequest, llm_response: LlmResponse) -> None:
        attributes = {
            "gen_ai_system": "volcengine",
            "gen_ai_response_model": llm_request.model,
            "gen_ai_operation_name": "chat_completions",
            "stream": "false",
            "server_address": "api.volcengine.com",
        }  # required by Volcengine APMPlus

        if llm_response.usage_metadata:
            # llm invocation number += 1
            self.llm_invoke_counter.add(1, attributes)

            # upload token usage
            input_token = llm_response.usage_metadata.prompt_token_count
            output_token = llm_response.usage_metadata.candidates_token_count

            if input_token:
                token_attributes = {**attributes, "gen_ai_token_type": "input"}
                self.token_usage.record(input_token, attributes=token_attributes)
            if output_token:
                token_attributes = {**attributes, "gen_ai_token_type": "output"}
                self.token_usage.record(output_token, attributes=token_attributes)


class APMPlusExporterConfig(BaseModel):
    endpoint: str = Field(
        default_factory=lambda: settings.apmplus_config.otel_exporter_endpoint,
    )
    app_key: str = Field(
        default_factory=lambda: settings.apmplus_config.otel_exporter_api_key,
    )
    service_name: str = Field(
        default_factory=lambda: settings.apmplus_config.otel_exporter_service_name,
        description="Service name shown in APMPlus frontend.",
    )


class APMPlusExporter(BaseExporter):
    config: APMPlusExporterConfig = Field(default_factory=APMPlusExporterConfig)

    def model_post_init(self, context: Any) -> None:
        print(self.config)
        headers = {
            "x-byteapm-appkey": self.config.app_key,
        }
        self.headers |= headers

        resource_attributes = {
            "service.name": self.config.service_name,
        }
        self.resource_attributes |= resource_attributes

        self._exporter = OTLPSpanExporter(
            endpoint=self.config.endpoint, insecure=True, headers=self.headers
        )
        self.processor = BatchSpanProcessor(self._exporter)

        self.meter_uploader = MeterUploader(
            name="apmplus_meter",
            endpoint=self.config.endpoint,
            headers=self.headers,
            resource_attributes=self.resource_attributes,
        )

    @override
    def export(self) -> None:
        if self._exporter:
            self._exporter.force_flush()

            logger.info(
                f"APMPlusExporter exports data to {self.config.endpoint}, service name: {self.config.service_name}"
            )
        else:
            logger.warning("APMPlusExporter internal exporter is not initialized.")
