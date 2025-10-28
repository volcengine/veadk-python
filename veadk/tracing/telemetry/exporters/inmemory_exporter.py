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
    """Internal span exporter that stores spans in memory for local analysis and debugging.

    This exporter collects and stores OpenTelemetry spans in memory rather than
    sending them to external services. It's particularly useful for development,
    testing, and local trace analysis scenarios where immediate access to span
    data is needed.

    Key Features:
    - In-memory span storage with session-based organization
    - Trace ID tracking for span correlation
    - Session-to-trace mapping for efficient filtering
    - Support for span retrieval by session ID

    Attributes:
        _spans: List of all collected ReadableSpan objects
        trace_id: Current trace identifier from the most recent span
        session_trace_dict: Mapping of session IDs to their associated trace IDs
    """

    def __init__(self) -> None:
        """Initialize the in-memory exporter with empty storage containers."""
        super().__init__()
        self._spans = []
        self.trace_id = ""
        self.session_trace_dict = {}

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> export.SpanExportResult:
        """Export spans to in-memory storage with session tracking.

        Processes and stores spans while maintaining session-to-trace mapping
        for efficient retrieval. Extracts session information from LLM call spans
        to enable session-based filtering.

        Args:
            spans: Sequence of ReadableSpan objects to store

        Returns:
            SpanExportResult.SUCCESS: Always returns success for in-memory storage
        """
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
        """Force flush operation for in-memory exporter.

        Since spans are immediately stored in memory, this operation
        always succeeds without performing any actual flushing.

        Returns:
            bool: Always True indicating successful flush
        """
        return True

    def get_finished_spans(self, session_id: str):
        """Retrieve all spans associated with a specific session ID.

        Filters stored spans to return only those belonging to the specified
        session, enabling session-scoped trace analysis and debugging.

        Args:
            session_id: Session identifier to filter spans by

        Returns:
            list[ReadableSpan]: List of spans associated with the session,
                empty list if session not found or no spans available
        """
        trace_ids = self.session_trace_dict.get(session_id, None)
        if trace_ids is None or not trace_ids:
            return []
        return [x for x in self._spans if x.context.trace_id in trace_ids]

    def clear(self):
        """Clear all stored spans and session mappings.

        Removes all collected span data from memory, useful for cleanup
        between test runs or to free memory in long-running processes.
        """
        self._spans.clear()


class _InMemorySpanProcessor(export.SimpleSpanProcessor):
    """Custom span processor for in-memory export with enhanced span annotation.

    Extends SimpleSpanProcessor to add VeADK-specific span attributes and
    context management. Handles span lifecycle events to set appropriate
    attributes and manage OpenTelemetry context for nested span hierarchies.
    """

    def __init__(self, exporter: _InMemoryExporter) -> None:
        """Initialize the span processor with the given in-memory exporter.

        Args:
            exporter: _InMemoryExporter instance for storing processed spans
        """
        super().__init__(exporter)

    def on_start(self, span, parent_context) -> None:
        """Handle span start events with type-specific attribute setting.

        Automatically detects span types based on name patterns and applies
        appropriate attributes. Sets up OpenTelemetry context for hierarchical
        span management and instrumentation suppression.

        Args:
            span: The span being started
            parent_context: Parent OpenTelemetry context
        """
        if span.name.startswith("invocation"):
            span.set_attribute("gen_ai.operation.name", "chain")
            span.set_attribute("gen_ai.span.kind", "workflow")
            span.set_attribute("gen_ai.usage.total_tokens", 0)
            ctx = set_value("invocation_span_instance", span, context=parent_context)
            # suppress instrumentation for llm to avoid auto instrument from apmplus, such as openai
            ctx = set_value(
                "suppress_language_model_instrumentation", True, context=ctx
            )

            token = attach(ctx)  # mount context on `invocation` root span in Google ADK
            setattr(span, "_invocation_token", token)  # for later detach

        if span.name.startswith("agent_run") or span.name.startswith("invoke_agent"):
            span.set_attribute("gen_ai.operation.name", "agent")
            span.set_attribute("gen_ai.span.kind", "agent")

            ctx = set_value("agent_run_span_instance", span, context=parent_context)
            token = attach(ctx)
            setattr(span, "_agent_run_token", token)  # for later detach

    def on_end(self, span: ReadableSpan) -> None:
        """Handle span end events with proper context cleanup.

        Exports the finished span to the in-memory storage while managing
        OpenTelemetry context and cleaning up attached tokens to prevent
        memory leaks.

        Args:
            span: The span that has finished execution
        """
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
    """In-memory span exporter for local debugging and observability analysis.

    InMemoryExporter provides a complete in-memory tracing solution that stores
    spans locally for immediate analysis, debugging, and testing. It's ideal for
    development environments where external observability platforms are not
    available or not desired.

    Use Cases:
    - Development and debugging of agent workflows
    - Unit and integration testing with trace verification
    - Local trace analysis and performance profiling
    - Offline environments without external connectivity
    - Trace data export for post-processing and analysis

    Integration:
    The exporter is automatically added to OpentelemetryTracer instances
    and cannot be manually configured to avoid conflicts. It provides the
    foundation for local trace file generation and analysis.

    Note:
        - Cannot be added to exporter lists (validation prevents this)
        - Automatically managed by OpentelemetryTracer
        - Memory usage grows with span count - consider periodic clearing
        - Session tracking requires properly configured session IDs
    """

    def __init__(self, name: str = "inmemory_exporter") -> None:
        """Initialize the in-memory exporter with internal components.

        Args:
            name: Identifier for this exporter instance.
        """
        super().__init__()

        self.name = name

        self._exporter = _InMemoryExporter()
        self.processor = _InMemorySpanProcessor(self._exporter)
