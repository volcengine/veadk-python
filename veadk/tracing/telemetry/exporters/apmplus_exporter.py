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

from collections.abc import Sequence
from typing import Any

from opentelemetry import metrics as metrics_api
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics._internal import _ProxyMeterProvider
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk import metrics as metrics_sdk
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field
from requests.structures import CaseInsensitiveDict
from typing_extensions import override

from veadk.config import settings
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _grpc_header_options(headers: dict) -> dict[str, Any]:
    metadata = {key.lower(): value for key, value in headers.items()}
    user_agent = metadata.pop("user-agent", None)
    options: dict[str, Any] = {"headers": metadata}
    if user_agent:
        # gRPC constructs the wire User-Agent from channel options.
        options["channel_options"] = (("grpc.secondary_user_agent", user_agent),)
    return options


class _APMPlusSpanExporter(OTLPSpanExporter):
    """Include VeADK attribution in the span payload indexed by APMPlus."""

    def __init__(self, endpoint: str, headers: dict):
        super().__init__(
            endpoint=endpoint, insecure=True, **_grpc_header_options(headers)
        )
        effective_headers = CaseInsensitiveDict(headers)
        # Only these five public fields may become searchable span tags.
        self._header_tags = {
            key: effective_headers[key]
            for key in (
                "veadk-source",
                "veadk-version",
                "User-Agent",
                "X-Client-Request-Id",
                "x-is-encrypted",
            )
        }

    @override
    def _translate_data(
        self, data: Sequence[ReadableSpan]
    ) -> ExportTraceServiceRequest:
        request = super()._translate_data(data)
        for resource in request.resource_spans:
            for scope in resource.scope_spans:
                for span in scope.spans:
                    existing = {
                        attr.key: attr
                        for attr in span.attributes
                        if attr.key in self._header_tags
                    }
                    for key, value in self._header_tags.items():
                        attr = existing.get(key)
                        if attr is None:
                            attr = span.attributes.add(key=key)
                        attr.value.string_value = value
        return request


def ensure_apmplus_meter_provider(
    endpoint: str,
    headers: dict,
    resource_attributes: dict,
) -> metrics_api.MeterProvider:
    """Install an APMPlus-backed global MeterProvider only when none exists."""
    global_provider = metrics_api.get_meter_provider()
    if not isinstance(global_provider, _ProxyMeterProvider):
        return global_provider

    exporter = OTLPMetricExporter(
        endpoint=endpoint,
        insecure=True,
        **_grpc_header_options(headers),
    )
    metric_reader = PeriodicExportingMetricReader(exporter)
    provider = metrics_sdk.MeterProvider(
        metric_readers=[metric_reader],
        resource=Resource.create(resource_attributes),
    )
    metrics_api.set_meter_provider(provider)
    resolved_provider = metrics_api.get_meter_provider()

    if resolved_provider is not provider:
        # Another component won the set-once race. Keep its provider and close
        # the unused APMPlus pipeline created by this call.
        provider.shutdown()

    return resolved_provider


class APMPlusExporterConfig(BaseModel):
    """Configuration model for APMPlus exporter settings.

    Manages connection parameters and authentication details for
    integrating with Volcengine's APMPlus observability platform.

    Attributes:
        endpoint: OTLP endpoint URL for APMPlus data ingestion
        app_key: Authentication key for APMPlus API access
        service_name: Service identifier displayed in APMPlus interface
    """

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
    """OpenTelemetry exporter for Volcengine APMPlus observability platform.

    APMPlusExporter provides comprehensive integration with Volcengine's APMPlus
    platform, enabling advanced observability for VeADK agents. It combines
    distributed tracing with detailed metrics collection for complete visibility
    into agent performance, costs, and reliability.

    Key Capabilities:
    - OTLP-based span export to APMPlus with authentication
    - Comprehensive metrics collection for LLM and tool operations
    - Automatic resource attribution with service identification
    - Cost tracking through detailed token usage metrics
    - Performance monitoring with latency histograms
    - Error tracking and exception monitoring

    Configuration:
    The exporter uses VeADK settings for automatic configuration but
    can be customized with explicit parameters. Authentication is
    handled through APMPlus app keys in request headers.

    Examples:
        Basic usage with default settings:
        ```python
        exporter = APMPlusExporter()
        tracer = OpentelemetryTracer(exporters=[exporter])
        ```

    Note:
        - Requires valid APMPlus app key for authentication
        - Endpoint should point to APMPlus OTLP ingestion service
        - Service name appears in APMPlus dashboards for identification
        - Metrics and spans are automatically correlated by trace context
        - Supports both development and production environments
    """

    config: APMPlusExporterConfig = Field(default_factory=APMPlusExporterConfig)

    def model_post_init(self, context: Any) -> None:
        """Initialize APMPlus exporter components after model construction.

        Sets up the OTLP span exporter and ensures a usable global
        MeterProvider without replacing one configured by the application.

        Components Initialized:
        - OTLP span exporter with APMPlus endpoint and authentication
        - Batch span processor for efficient data transmission
        - APMPlus metric pipeline only when no global MeterProvider exists
        - Resource attributes for service identification
        """
        logger.info(f"APMPlusExporter sevice name: {self.config.service_name}")

        headers = {
            "x-byteapm-appkey": self.config.app_key,
        }
        self._set_request_headers(headers)

        resource_attributes = {
            "service.name": self.config.service_name,
        }
        self.resource_attributes |= resource_attributes

        self._exporter = _APMPlusSpanExporter(self.config.endpoint, self.headers)
        self.processor = BatchSpanProcessor(self._exporter)

        ensure_apmplus_meter_provider(
            endpoint=self.config.endpoint,
            headers=self.headers,
            resource_attributes=self.resource_attributes,
        )

    @override
    def export(self) -> None:
        """Force immediate export of pending telemetry data to APMPlus.

        Triggers force flush on the OTLP span exporter to ensure all
        buffered span data is immediately transmitted to APMPlus for
        real-time observability and debugging.

        Operations:
        - Forces flush of span exporter if initialized
        - Logs export status and configuration details
        - Handles cases where exporter is not properly initialized
        """
        if self._exporter:
            self._exporter.force_flush()

            from veadk.tracing.telemetry.portal_metrics import (
                portal_metric_recorder,
            )

            portal_metric_recorder.force_flush()

            logger.info(
                f"APMPlusExporter exports data to {self.config.endpoint}, service name: {self.config.service_name}"
            )
        else:
            logger.warning("APMPlusExporter internal exporter is not initialized.")
