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

from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
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

logger = get_logger(__name__)

DEFAULT_VEADK_TRACER_NAME = "veadk_global_tracer"


def update_resource_attributions(provider: TracerProvider, resource_attributes: dict):
    provider._resource = provider._resource.merge(Resource.create(resource_attributes))


class OpentelemetryTracer(BaseModel, BaseTracer):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(
        default=DEFAULT_VEADK_TRACER_NAME, description="The identifier of tracer."
    )

    app_name: str = Field(
        default="veadk_app",
        description="The identifier of app.",
    )

    exporters: list[BaseExporter] = Field(
        default_factory=list,
        description="The exporters to export spans.",
    )

    @field_validator("exporters")
    @classmethod
    def forbid_inmemory_exporter(cls, v: list[BaseExporter]) -> list[BaseExporter]:
        for e in v:
            if isinstance(e, InMemoryExporter):
                raise ValueError("InMemoryExporter is not allowed in exporters list")
        return v

    def model_post_init(self, context: Any) -> None:
        patch_google_adk_telemetry()

        self._processors = []
        self._inmemory_exporter = InMemoryExporter()
        self.exporters.append(self._inmemory_exporter)

        # VeADK operates on global OpenTelemetry provider, return nothing
        self._init_global_tracer_provider()

        GoogleADKInstrumentor().instrument()

    def _init_global_tracer_provider(self) -> None:
        # set provider anyway, then get global provider
        tracer_provider = trace_sdk.TracerProvider()
        trace_api.set_tracer_provider(tracer_provider)
        global_tracer_provider: TracerProvider = trace_api.get_tracer_provider()  # type: ignore

        span_processors = global_tracer_provider._active_span_processor._span_processors
        have_apmplus_exporter = any(
            isinstance(p, (BatchSpanProcessor, SimpleSpanProcessor))
            and isinstance(p.span_exporter, OTLPSpanExporter)
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
                update_resource_attributions(
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

        logger.debug(
            f"Init OpentelemetryTracer with {len(self._processors)} exporters."
        )

    @property
    def trace_file_path(self) -> str:
        return self._trace_file_path

    @property
    def trace_id(self) -> str:
        try:
            trace_id = hex(int(self._inmemory_exporter._exporter.trace_id))[2:]
            return trace_id
        except Exception as e:
            logger.error(f"Failed to get trace_id from InMemoryExporter: {e}")
            return self._trace_id

    @override
    def dump(
        self,
        user_id: str,
        session_id: str,
        path: str = "/tmp",
    ) -> str:
        if not self._inmemory_exporter:
            logger.warning(
                "InMemoryExporter is not initialized. Please check your tracer exporters."
            )
            return ""

        prompt_tokens = self._inmemory_exporter._real_exporter.prompt_tokens
        completion_tokens = self._inmemory_exporter._real_exporter.completion_tokens

        # upload
        for meter_uploader in self._meter_uploaders:
            meter_uploader.record(
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
            )
        # clear tokens after dump
        self._inmemory_exporter._real_exporter.completion_tokens = []
        self._inmemory_exporter._real_exporter.prompt_tokens = []

        for processor in self._processors:
            time.sleep(0.05)  # give some time for the exporter to upload spans
            processor.force_flush()

        spans = self._inmemory_exporter._real_exporter.get_finished_spans(
            session_id=session_id
        )
        if not spans:
            data = []
        else:
            data = [
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

        trace_id = hex(int(self._inmemory_exporter._real_exporter.trace_id))[2:]
        self._trace_id = trace_id
        file_path = f"{path}/{self.name}_{user_id}_{session_id}_{trace_id}.json"
        with open(file_path, "w") as f:
            json.dump(
                data, f, indent=4, ensure_ascii=False
            )  # ensure_ascii=False to support Chinese characters

        self._trace_file_path = file_path

        for exporter in self.exporters:
            if not isinstance(exporter, InMemoryExporter):
                exporter.export()
        logger.info(
            f"OpenTelemetryTracer tracing done, trace id: {self._trace_id} (hex)"
        )

        self._spans = spans
        logger.info(f"OpenTelemetryTracer dumps {len(spans)} spans to {file_path}")
        return file_path
