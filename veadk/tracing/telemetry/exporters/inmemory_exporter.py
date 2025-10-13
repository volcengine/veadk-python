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

from opentelemetry.context import (
    _SUPPRESS_INSTRUMENTATION_KEY,
    attach,
    detach,
    set_value,
)
from opentelemetry.sdk.trace import ReadableSpan, export
from typing_extensions import override

from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


# ======== Adapted from Google ADK ========
class _InMemoryExporter(export.SpanExporter):
    def __init__(self) -> None:
        super().__init__()
        self._spans = []
        self.trace_id = ""
        self.session_trace_dict = {}

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> export.SpanExportResult:
        for span in spans:
            if span.context:
                self.trace_id = span.context.trace_id
            else:
                logger.warning(
                    f"Span context is missing, failed to get `trace_id`. span: {span}"
                )

            if span.name == "call_llm":
                attributes = dict(span.attributes or {})
                session_id = attributes.get("gen_ai.session.id", None)
                if session_id:
                    if session_id not in self.session_trace_dict:
                        self.session_trace_dict[session_id] = [self.trace_id]
                    else:
                        self.session_trace_dict[session_id] += [self.trace_id]
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


class _InMemorySpanProcessor(export.SimpleSpanProcessor):
    def __init__(self, exporter: _InMemoryExporter) -> None:
        super().__init__(exporter)

    def on_start(self, span, parent_context) -> None:
        if span.name.startswith("invocation") or span.name.startswith("invoke") :
            span.set_attribute("gen_ai.operation.name", "chain")
            span.set_attribute("gen_ai.span.kind", "workflow")
            span.set_attribute("gen_ai.usage.total_tokens", 0)
            ctx = set_value("invocation_span_instance", span, context=parent_context)
            # suppress instrumentation for llm from apmplus, such as openai
            ctx = set_value("suppress_language_model_instrumentation", True, context=ctx)

            token = attach(ctx)  # mount context on `invocation` root span in Google ADK
            setattr(span, "_invocation_token", token)  # for later detach

        if span.name.startswith("agent_run"):
            span.set_attribute("gen_ai.operation.name", "agent")
            span.set_attribute("gen_ai.span.kind", "agent")

            ctx = set_value("agent_run_span_instance", span, context=parent_context)
            token = attach(ctx)
            setattr(span, "_agent_run_token", token)  # for later detach

    def on_end(self, span: ReadableSpan) -> None:
        if span.context:
            if not span.context.trace_flags.sampled:
                return
            token = attach(set_value(_SUPPRESS_INSTRUMENTATION_KEY, True))
            try:
                self.span_exporter.export((span,))
            # pylint: disable=broad-exception-caught
            except Exception:
                logger.exception("Exception while exporting Span.")
            detach(token)

            token = getattr(span, "_invocation_token", None)
            if token:
                detach(token)

            token = getattr(span, "_agent_run_token", None)
            if token:
                detach(token)


class InMemoryExporter(BaseExporter):
    """InMemory Exporter mainly for store spans in memory for debugging / observability purposes."""

    def __init__(self, name: str = "inmemory_exporter") -> None:
        super().__init__()

        self.name = name

        self._exporter = _InMemoryExporter()
        self.processor = _InMemorySpanProcessor(self._exporter)
