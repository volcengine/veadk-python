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

from typing import Sequence

from opentelemetry.sdk.trace import ReadableSpan, export
from typing_extensions import override

from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


# ======== Adapted from Google ADK ========
class _InMemoryExporter(export.SpanExporter):
    def __init__(self):
        super().__init__()
        self._spans = []
        self.session_trace_dict = {}
        self.trace_id = ""
        self.prompt_tokens = []
        self.completion_tokens = []

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> export.SpanExportResult:
        for span in spans:
            if span.context:
                trace_id = span.context.trace_id
                self.trace_id = trace_id
            else:
                logger.warning(
                    f"Span context is missing, failed to get `trace_id`. span: {span}"
                )

            if span.name == "call_llm":
                attributes = dict(span.attributes or {})
                prompt_token = attributes.get("gen_ai.usage.prompt_tokens", None)
                completion_token = attributes.get(
                    "gen_ai.usage.completion_tokens", None
                )
                if prompt_token:
                    self.prompt_tokens.append(prompt_token)
                if completion_token:
                    self.completion_tokens.append(completion_token)

            if span.name == "call_llm":
                attributes = dict(span.attributes or {})
                session_id = attributes.get("gcp.vertex.agent.session_id", None)
                if session_id:
                    if session_id not in self.session_trace_dict:
                        self.session_trace_dict[session_id] = [trace_id]
                    else:
                        self.session_trace_dict[session_id] += [trace_id]
        self._spans.extend(spans)
        return export.SpanExportResult.SUCCESS

    @override
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def get_finished_spans(self, session_id: str):
        trace_ids = self.session_trace_dict.get(session_id, None)
        if trace_ids is None or not trace_ids:
            return []
        return [x for x in self._spans if x.context.trace_id in trace_ids]

    def clear(self):
        self._spans.clear()


class InMemoryExporter(BaseExporter):
    """InMemory Exporter mainly for store spans in memory for debugging / observability purposes."""

    def __init__(self, name: str = "inmemory_exporter") -> None:
        super().__init__()

        self.name = name

        self._exporter = _InMemoryExporter()
        self.processor = export.SimpleSpanProcessor(self._exporter)
