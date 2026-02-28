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

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
from pydantic import BaseModel, ConfigDict, Field

def _update_resource_attributions(
    provider: TracerProvider, resource_attributes: dict
) -> None:
    """Update the resource attributes of a TracerProvider instance.

    This function merges new resource attributes with the existing ones in the
    provider, allowing dynamic configuration of telemetry metadata.

    Args:
        provider: The TracerProvider instance to update
        resource_attributes: Dictionary of attributes to merge with existing resources
    """
    provider._resource = provider._resource.merge(Resource.create(resource_attributes))


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
    processor: SpanProcessor | None = None
    _registered: bool = False

    def register(self) -> None:
        """Register the exporter with the global tracer provider.

        This method will automatically get the global tracer provider
        and register the exporter's span processor with it.
        The registration Dprocess will only be executed once.
        """
        if self._registered:
            return

        tracer_provider = trace.get_tracer_provider()
        # Update resource attributes if any
        if self.resource_attributes:
            _update_resource_attributions(tracer_provider, self.resource_attributes)
        
        # Add processor to tracer provider if exists
        if self.processor:
            tracer_provider.add_span_processor(self.processor)
            
        self._registered = True

    def export(self) -> None:
        """Force export of telemetry data."""
        pass
