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

from __future__ import annotations

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
from pydantic import BaseModel, ConfigDict, Field


class BaseExporter(BaseModel):
    """Abstract base class for OpenTelemetry span exporters in VeADK tracing system.

    BaseExporter provides the foundation for implementing custom telemetry data
    exporters that send span data to various observability platforms. It defines
    the common interface and configuration structure that all concrete exporters
    must follow.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    resource_attributes: dict = Field(default_factory=dict)
    headers: dict = Field(default_factory=dict)

    _exporter: SpanExporter | None = None
    _registered_provider: TracerProvider | None = None
    processor: SpanProcessor | None = None

    def register(self, provider: TracerProvider) -> bool:
        """Register this exporter's processor with a tracer provider once.

        Returns:
            Whether the processor was newly registered with ``provider``.
        """
        if self.processor is None or self._registered_provider is provider:
            return False

        if self.resource_attributes:
            provider._resource = provider._resource.merge(
                Resource.create(self.resource_attributes)
            )

        provider.add_span_processor(self.processor)
        self._registered_provider = provider
        return True

    def export(self) -> None:
        """Force export of telemetry data."""
        pass
