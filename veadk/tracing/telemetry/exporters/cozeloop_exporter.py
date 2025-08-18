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


class CozeloopExporterConfig(BaseModel):
    endpoint: str = Field(
        default_factory=lambda: getenv(
            "OBSERVABILITY_OPENTELEMETRY_COZELOOP_ENDPOINT",
            "https://api.coze.cn/v1/loop/opentelemetry/v1/traces",
        ),
    )
    space_id: str = Field(
        default_factory=lambda: getenv(
            "OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME"
        ),
    )
    token: str = Field(
        default_factory=lambda: getenv("OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY"),
    )


class CozeloopExporter(BaseModel, BaseExporter):
    config: CozeloopExporterConfig = Field(default_factory=CozeloopExporterConfig)

    @override
    def get_processor(self):
        headers = {
            "cozeloop-workspace-id": self.config.space_id,
            "authorization": f"Bearer {self.config.token}",
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
            f"CozeloopExporter exports data to {self.config.endpoint}, space id: {self.config.space_id}"
        )
