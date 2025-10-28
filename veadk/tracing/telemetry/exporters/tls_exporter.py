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

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field
from typing_extensions import override

from veadk.config import getenv, settings
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class TLSExporterConfig(BaseModel):
    """Configuration model for Volcengine TLS exporter settings.

    Manages connection parameters and authentication details for
    integrating with Volcengine's TLS logging and observability platform.

    Attributes:
        endpoint: OTLP HTTP endpoint URL for TLS data ingestion
        region: Volcengine region where the TLS service is deployed
        topic_id: TLS topic identifier for organizing log data
        access_key: Volcengine access key for API authentication
        secret_key: Volcengine secret key for API authentication
    """

    endpoint: str = Field(
        default_factory=lambda: settings.tls_config.otel_exporter_endpoint,
    )
    region: str = Field(
        default_factory=lambda: settings.tls_config.otel_exporter_region,
    )
    topic_id: str = Field(
        default_factory=lambda: settings.tls_config.otel_exporter_topic_id,
    )
    access_key: str = Field(default_factory=lambda: getenv("VOLCENGINE_ACCESS_KEY"))
    secret_key: str = Field(default_factory=lambda: getenv("VOLCENGINE_SECRET_KEY"))


class TLSExporter(BaseExporter):
    """OpenTelemetry exporter for Volcengine TLS platform.

    TLSExporter provides integration with Volcengine's TLS platform for
    centralized logging and trace data management. It uses HTTP-based OTLP
    export to send trace data to TLS topics for storage, analysis, and
    long-term retention.

    Use Cases:
    - Centralized trace data storage and archival
    - Long-term performance trend analysis
    - Compliance and audit trail requirements
    - Cross-service trace correlation and analysis
    - Integration with existing TLS logging infrastructure

    Examples:
        Basic usage with default settings:
        ```python
        exporter = TLSExporter()
        tracer = OpentelemetryTracer(exporters=[exporter])
        ```

    Note:
        - Requires valid Volcengine credentials and TLS topic ID
        - Data is organized by topics for efficient management
        - Supports regional deployments for data locality compliance
        - Integrates with TLS alerting and analysis features
        - Suitable for production environments requiring data retention
    """

    config: TLSExporterConfig = Field(default_factory=TLSExporterConfig)

    def model_post_init(self, context: Any) -> None:
        """Initialize TLS exporter components after model construction.

        Sets up HTTP-based OTLP span exporter and batch processor with
        Volcengine authentication headers and TLS topic configuration for
        centralized trace data management.

        Components Initialized:
        - HTTP OTLP span exporter with TLS endpoint
        - Batch span processor for efficient data transmission
        - Authentication headers with Volcengine credentials
        - Topic and region configuration for data routing
        - Timeout configuration for reliable network operations
        """
        logger.info(f"TLSExporter topic ID: {self.config.topic_id}")

        headers = {
            "x-tls-otel-tracetopic": self.config.topic_id,
            "x-tls-otel-ak": self.config.access_key,
            "x-tls-otel-sk": self.config.secret_key,
            "x-tls-otel-region": self.config.region,
        }
        self.headers |= headers

        self._exporter = OTLPSpanExporter(
            endpoint=self.config.endpoint,
            headers=headers,
            timeout=10,
        )

        self.processor = BatchSpanProcessor(self._exporter)

    @override
    def export(self) -> None:
        """Force immediate export of pending telemetry data to TLS.

        Triggers force flush on the HTTP OTLP span exporter to ensure all
        buffered span data is immediately transmitted to TLS for centralized
        logging and analysis.

        Operations:
        - Forces flush of span exporter if initialized
        - Logs export status with endpoint and topic details
        - Handles cases where exporter is not properly initialized
        """
        if self._exporter:
            self._exporter.force_flush()
            logger.info(
                f"TLSExporter exports data to {self.config.endpoint}, topic id: {self.config.topic_id}"
            )
        else:
            logger.warning("TLSExporter internal exporter is not initialized.")
