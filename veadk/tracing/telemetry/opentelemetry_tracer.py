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

import json
import time
from typing import Any

from opentelemetry import trace as trace_api
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import override

from veadk.tracing.base_tracer import BaseTracer
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.tracing.telemetry.exporters.inmemory_exporter import InMemoryExporter
from veadk.utils.logger import get_logger
from veadk.utils.patches import patch_google_adk_telemetry
from veadk.utils.misc import get_temp_dir

logger = get_logger(__name__)


def _update_resource_attributions(
    provider: TracerProvider, resource_attributes: dict
) -> None:
    provider._resource = provider._resource.merge(Resource.create(resource_attributes))


class OpentelemetryTracer(BaseModel, BaseTracer):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(
        default="veadk_opentelemetry_tracer", description="The identifier of tracer."
    )

    exporters: list[BaseExporter] = Field(
        default_factory=list,
        description="The exporters to export spans.",
    )

    # Forbid InMemoryExporter in exporters list
    # cause we need to set custom in-memory span processor by VeADK
    @field_validator("exporters")
    @classmethod
    def forbid_inmemory_exporter(cls, v: list[BaseExporter]) -> list[BaseExporter]:
        for e in v:
            if isinstance(e, InMemoryExporter):
                raise ValueError("InMemoryExporter is not allowed in exporters list")
        return v

    def model_post_init(self, context: Any) -> None:
        # Replace Google ADK tracing funcs
        # `trace_call_llm` and `trace_tool_call`
        patch_google_adk_telemetry()

        # We save internal processors for tracing data dump
        self._processors = []

        # Initialize global tracer provider to avoid VeFaaS global tracer
        # provider conflicts
        self._init_global_tracer_provider()

    def _init_global_tracer_provider(self) -> None:
        # set provider anyway, then get global provider
        trace_api.set_tracer_provider(trace_sdk.TracerProvider())
        global_tracer_provider: TracerProvider = trace_api.get_tracer_provider()  # type: ignore

        span_processors = global_tracer_provider._active_span_processor._span_processors
        have_apmplus_exporter = any(
            isinstance(p, (BatchSpanProcessor, SimpleSpanProcessor))
            and hasattr(p.span_exporter, "_endpoint")
            and "apmplus" in p.span_exporter._endpoint
            for p in span_processors
        )

        if have_apmplus_exporter:
            self.exporters = [
                e for e in self.exporters if not isinstance(e, APMPlusExporter)
            ]

        for exporter in self.exporters:
            processor = exporter.processor
            resource_attributes = exporter.resource_attributes

            if resource_attributes:
                _update_resource_attributions(
                    global_tracer_provider, resource_attributes
                )

            if processor:
                global_tracer_provider.add_span_processor(processor)
                self._processors.append(processor)

                logger.debug(
                    f"Add span processor for exporter `{exporter.__class__.__name__}` to OpentelemetryTracer."
                )
            else:
                logger.error(
                    f"Add span processor for exporter `{exporter.__class__.__name__}` to OpentelemetryTracer failed."
                )

        self._inmemory_exporter = InMemoryExporter()
        if self._inmemory_exporter.processor:
            # make sure the in memory exporter processor is added at index 0
            # because we use this to record all spans
            global_tracer_provider._active_span_processor._span_processors = (
                self._inmemory_exporter.processor,
            ) + global_tracer_provider._active_span_processor._span_processors

            self._processors.append(self._inmemory_exporter.processor)
        else:
            logger.warning(
                "InMemoryExporter processor is not initialized, cannot add to OpentelemetryTracer."
            )

        logger.info(f"Init OpentelemetryTracer with {len(self._processors)} exporters.")

    @property
    def trace_file_path(self) -> str:
        return self._trace_file_path

    @property
    def trace_id(self) -> str:
        try:
            trace_id = hex(int(self._inmemory_exporter._exporter.trace_id))[2:]  # type: ignore
            return trace_id
        except Exception as e:
            logger.error(f"Failed to get trace_id from InMemoryExporter: {e}")
            return self._trace_id

    def force_export(self) -> None:
        """Force to export spans in all processors."""
        for processor in self._processors:
            time.sleep(0.05)
            processor.force_flush()

    @override
    def dump(
        self,
        user_id: str = "unknown_user_id",
        session_id: str = "unknown_session_id",
        path: str = get_temp_dir(),
    ) -> str:
        def _build_trace_file_path(path: str, user_id: str, session_id: str) -> str:
            return f"{path}/{self.name}_{user_id}_{session_id}_{self.trace_id}.json"

        if not self._inmemory_exporter:
            logger.warning(
                "InMemoryExporter is not initialized. Please check your tracer exporters."
            )
            return ""
        self.force_export()

        spans = self._inmemory_exporter._exporter.get_finished_spans(  # type: ignore
            session_id=session_id
        )
        data = (
            [
                {
                    "name": s.name,
                    "span_id": s.context.span_id,
                    "trace_id": s.context.trace_id,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "attributes": dict(s.attributes),
                    "parent_span_id": s.parent.span_id if s.parent else None,
                }
                for s in spans
            ]
            if spans
            else []
        )

        self._trace_file_path = _build_trace_file_path(path, user_id, session_id)
        with open(self._trace_file_path, "w") as f:
            json.dump(
                data, f, indent=4, ensure_ascii=False
            )  # ensure_ascii=False to support Chinese characters

        logger.info(
            f"OpenTelemetryTracer dumps {len(spans)} spans to {self._trace_file_path}. Trace id: {self.trace_id} (hex)"
        )

        return self._trace_file_path
