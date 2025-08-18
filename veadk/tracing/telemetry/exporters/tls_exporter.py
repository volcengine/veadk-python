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

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field
from typing_extensions import override

from veadk.config import getenv
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class TLSExporterConfig(BaseModel):
    endpoint: str = Field(
        default_factory=lambda: getenv(
            "OBSERVABILITY_OPENTELEMETRY_TLS_ENDPOINT",
            "https://tls-cn-beijing.volces.com:4318/v1/traces",
        ),
    )
    region: str = Field(
        default_factory=lambda: getenv(
            "OBSERVABILITY_OPENTELEMETRY_TLS_REGION",
            "cn-beijing",
        ),
    )
    topic_id: str = Field(
        default_factory=lambda: getenv("OBSERVABILITY_OPENTELEMETRY_TLS_SERVICE_NAME"),
    )
    access_key: str = Field(default_factory=lambda: getenv("VOLCENGINE_ACCESS_KEY"))
    secret_key: str = Field(default_factory=lambda: getenv("VOLCENGINE_SECRET_KEY"))


class TLSExporter(BaseModel, BaseExporter):
    config: TLSExporterConfig = Field(default_factory=TLSExporterConfig)

    @override
    def get_processor(self):
        headers = {
            "x-tls-otel-tracetopic": self.config.topic_id,
            "x-tls-otel-ak": self.config.access_key,
            "x-tls-otel-sk": self.config.secret_key,
            "x-tls-otel-region": self.config.region,
        }
        exporter = OTLPSpanExporter(
            endpoint=self.config.endpoint,
            headers=headers,
            timeout=10,
        )
        self._real_exporter = exporter
        processor = BatchSpanProcessor(exporter)
        return processor, None

    def export(self):
        self._real_exporter.force_flush()
        logger.info(
            f"TLSExporter exports data to {self.config.endpoint}, topic id: {self.config.topic_id}"
        )
