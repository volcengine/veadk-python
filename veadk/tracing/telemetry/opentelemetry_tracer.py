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
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry import trace as trace_api
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

from veadk.tracing.base_tracer import BaseTracer
from veadk.tracing.telemetry.exporters.apiserver_exporter import ApiServerExporter
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.tracing.telemetry.exporters.inmemory_exporter import InMemoryExporter
from veadk.tracing.telemetry.metrics.opentelemetry_metrics import MeterUploader
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_VEADK_TRACER_NAME = "veadk_global_tracer"


def update_resource_attributions(provider: TracerProvider, resource_attributes: dict):
    provider._resource = provider._resource.merge(Resource.create(resource_attributes))


class OpentelemetryTracer(BaseModel, BaseTracer):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    exporters: list[BaseExporter] = Field(
        default=[],
        description="The exporters to export spans.",
    )
    name: str = Field(
        DEFAULT_VEADK_TRACER_NAME, description="The identifier of tracer."
    )

    app_name: str = Field(
        "veadk_app",
        description="The identifier of app.",
    )

    def model_post_init(self, context: Any, /) -> None:
        self._processors = []
        self._inmemory_exporter: InMemoryExporter = None
        self._apiserver_exporter: ApiServerExporter = None
        # Inmemory & APIServer are the default exporters
        have_inmemory_exporter = False
        have_apiserver_exporter = False
        for exporter in self.exporters:
            if isinstance(exporter, InMemoryExporter):
                have_inmemory_exporter = True
                self._inmemory_exporter = exporter
            elif isinstance(exporter, ApiServerExporter):
                have_apiserver_exporter = True
                self._apiserver_exporter = exporter

        if not have_inmemory_exporter:
            inmemory_exporter = InMemoryExporter()
            self.exporters.append(inmemory_exporter)
            self._inmemory_exporter = inmemory_exporter
        if not have_apiserver_exporter:
            apiserver_exporter = ApiServerExporter()
            self.exporters.append(apiserver_exporter)
            self._apiserver_exporter = apiserver_exporter

        self._meter_contexts = []
        self._meter_uploaders = []
        for exporter in self.exporters:
            meter_context = exporter.get_meter_context()
            if meter_context is not None:
                self._meter_contexts.append(meter_context)

        for meter_context in self._meter_contexts:
            meter_uploader = MeterUploader(meter_context)
            self._meter_uploaders.append(meter_uploader)

        # init tracer provider
        self._init_tracer_provider()

        # just for debug
        self._trace_file_path = ""

        # patch this before starting instrumentation
        # enable_veadk_tracing(self.dump)

        GoogleADKInstrumentor().instrument()

    def _init_tracer_provider(self):
        # 1. get global trace provider
        global_tracer_provider = trace_api.get_tracer_provider()

        if not isinstance(global_tracer_provider, TracerProvider):
            logger.info(f"Global tracer provider has not been set. Create tracer provider and set it now.")
            # 1.1 init tracer provider
            tracer_provider = trace_sdk.TracerProvider()
            trace_api.set_tracer_provider(tracer_provider)
            global_tracer_provider = trace_api.get_tracer_provider()

        have_apmplus_exporter = False
        # 2. check if apmplus exporter is already exist
        for processor in global_tracer_provider._active_span_processor._span_processors:
            if isinstance(processor, (BatchSpanProcessor, SimpleSpanProcessor)):
                # check exporter endpoint
                if "apmplus" in processor.span_exporter._endpoint:
                    have_apmplus_exporter = True

        # 3. add exporters to global tracer_provider
        # range over a copy of exporters to avoid index issues
        for exporter in self.exporters[:]:
            if have_apmplus_exporter and isinstance(exporter, APMPlusExporter):
                # apmplus exporter has been int in global tracer provider, need to remove from exporters.
                self.exporters.remove(exporter)
                continue
            processor, resource_attributes = exporter.get_processor()
            if resource_attributes is not None:
                update_resource_attributions(global_tracer_provider, resource_attributes)
            global_tracer_provider.add_span_processor(processor)
            logger.debug(f"Add exporter `{exporter.__class__.__name__}` to tracing.")
            self._processors.append(processor)
        logger.debug(f"Init OpentelemetryTracer with {len(self.exporters)} exporters.")


    @override
    def dump(
        self,
        user_id: str,
        session_id: str,
        path: str = "/tmp",
    ) -> str:
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
            json.dump(data, f, indent=4)

        self._trace_file_path = file_path

        for exporter in self.exporters:
            if not isinstance(exporter, InMemoryExporter) and not isinstance(
                exporter, ApiServerExporter
            ):
                exporter.export()
        logger.info(
            f"OpenTelemetryTracer tracing done, trace id: {self._trace_id} (hex)"
        )

        self._spans = spans
        logger.info(f"OpenTelemetryTracer dumps {len(spans)} spans to {file_path}")
        return file_path
