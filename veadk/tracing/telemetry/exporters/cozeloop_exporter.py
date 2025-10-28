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

from veadk.config import settings
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class CozeloopExporterConfig(BaseModel):
    """Configuration model for CozeLoop exporter settings.

    Manages connection parameters and authentication details for
    integrating with CozeLoop observability and evaluation platform.

    Attributes:
        endpoint: OTLP HTTP endpoint URL for CozeLoop data ingestion
        space_id: Workspace identifier for organizing data in CozeLoop
        token: Authentication token for CozeLoop API access
    """

    endpoint: str = Field(
        default_factory=lambda: settings.cozeloop_config.otel_exporter_endpoint,
    )
    space_id: str = Field(
        default_factory=lambda: settings.cozeloop_config.otel_exporter_space_id,
    )
    token: str = Field(
        default_factory=lambda: settings.cozeloop_config.otel_exporter_api_key,
    )


class CozeloopExporter(BaseExporter):
    """OpenTelemetry exporter for CozeLoop evaluation and observability platform.

    CozeloopExporter provides integration with CozeLoop platform for agent
    evaluation, monitoring, and analysis. It uses HTTP-based OTLP export
    to send trace data to CozeLoop's evaluation infrastructure for detailed
    performance analysis and evaluation workflows.

    Integration:
    CozeLoop specializes in AI agent evaluation and provides advanced
    analytics for conversation quality, tool usage effectiveness, and
    overall agent performance metrics. The exporter enables seamless
    integration with CozeLoop's evaluation workflows.

    Examples:
        Basic usage with default settings:
        ```python
        exporter = CozeloopExporter()
        tracer = OpentelemetryTracer(exporters=[exporter])
        ```

    Note:
        - Requires valid CozeLoop workspace ID and authentication token
        - Data is organized by workspace for multi-tenant isolation
        - Suitable for both development and production evaluation workflows
    """

    config: CozeloopExporterConfig = Field(default_factory=CozeloopExporterConfig)

    def model_post_init(self, context: Any) -> None:
        """Initialize CozeLoop exporter components after model construction.

        Sets up HTTP-based OTLP span exporter and batch processor with
        proper authentication headers and workspace identification for
        CozeLoop platform integration.

        Components Initialized:
        - HTTP OTLP span exporter with CozeLoop endpoint
        - Batch span processor for efficient data transmission
        - Authentication headers with workspace ID and bearer token
        - Timeout configuration for reliable network operations
        """
        logger.info(f"CozeloopExporter space ID: {self.config.space_id}")

        headers = {
            "cozeloop-workspace-id": self.config.space_id,
            "authorization": f"Bearer {self.config.token}",
        }
        self.headers |= headers

        self._exporter = OTLPSpanExporter(
            endpoint=self.config.endpoint,
            headers=self.headers,
            timeout=10,
        )

        self.processor = BatchSpanProcessor(self._exporter)

    @override
    def export(self) -> None:
        """Force immediate export of pending telemetry data to CozeLoop.

        Triggers force flush on the HTTP OTLP span exporter to ensure all
        buffered span data is immediately transmitted to CozeLoop for
        real-time evaluation and analysis.

        Operations:
        - Forces flush of span exporter if initialized
        - Logs export status with endpoint and workspace details
        - Handles cases where exporter is not properly initialized
        """
        if self._exporter:
            self._exporter.force_flush()
            logger.info(
                f"CozeloopExporter exports data to {self.config.endpoint}, space id: {self.config.space_id}"
            )
        else:
            logger.warning("CozeloopExporter internal exporter is not initialized.")
