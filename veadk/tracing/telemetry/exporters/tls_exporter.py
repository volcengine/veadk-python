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
    config: TLSExporterConfig = Field(default_factory=TLSExporterConfig)

    def model_post_init(self, context: Any) -> None:
        logger.info(f"TLSExporter topic ID: {self.config.topic_id}")

        headers = {
            "x-tls-otel-tracetopic": self.config.topic_id,
            "x-tls-otel-ak": self.config.access_key,
            "x-tls-otel-sk": self.config.secret_key,
            "x-tls-otel-region": self.config.region,
            "TraceTag": "veadk",
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
        if self._exporter:
            self._exporter.force_flush()
            logger.info(
                f"TLSExporter exports data to {self.config.endpoint}, topic id: {self.config.topic_id}"
            )
        else:
            logger.warning("TLSExporter internal exporter is not initialized.")
