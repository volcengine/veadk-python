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

import typing

from opentelemetry.sdk.trace import ReadableSpan, export
from pydantic import BaseModel
from typing_extensions import override

from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter


# ======== Adapted from Google ADK ========
class _ApiServerSpanExporter(export.SpanExporter):
    def __init__(self, trace_dict):
        self.trace_dict = trace_dict
        self.trace_id = ""

    def export(self, spans: typing.Sequence[ReadableSpan]) -> export.SpanExportResult:
        for span in spans:
            if (
                span.name == "call_llm"
                or span.name == "send_data"
                or span.name.startswith("execute_tool")
            ):
                attributes = dict(span.attributes)
                attributes["trace_id"] = span.get_span_context().trace_id
                attributes["span_id"] = span.get_span_context().span_id
                if attributes.get("gcp.vertex.agent.event_id", None):
                    self.trace_dict[attributes["gcp.vertex.agent.event_id"]] = (
                        attributes
                    )
        return export.SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class ApiServerExporter(BaseModel, BaseExporter):
    name: str = "apiserver_exporter"
    trace_dict: dict = {}

    def model_post_init(self, context) -> None:
        self._exporter = _ApiServerSpanExporter(self.trace_dict)

    @override
    def get_processor(self):
        processor = export.SimpleSpanProcessor(self._exporter)
        return processor, None
