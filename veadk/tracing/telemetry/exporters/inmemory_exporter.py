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

import sys
from collections import deque
from collections.abc import Mapping
from threading import Lock
from typing import Sequence

from opentelemetry.context import (
    _SUPPRESS_INSTRUMENTATION_KEY,
    attach,
    detach,
    set_value,
)
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider, export
from typing_extensions import override

from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)
_registration_lock = Lock()


def _value_size(value) -> int:
    """Estimate OTel attribute data without copying or serializing large strings"""
    size = sys.getsizeof(value)
    if isinstance(value, Mapping):
        size += sum(_value_size(k) + _value_size(v) for k, v in value.items())
    elif isinstance(value, (tuple, list)):
        size += sum(_value_size(item) for item in value)
    return size


def _span_size(span: ReadableSpan) -> int:
    """Estimate retained span data; this is a cache budget, not an RSS measurement"""
    # Include fixed span/container bookkeeping and all variable-size OTel fields
    size = 1024 + _value_size(span.name) + _value_size(span.attributes)
    for context in (span.context, span.parent):
        if context:
            size += _value_size(dict(context.trace_state.items()))
    if span.status:
        size += _value_size(span.status.description)
    if span.resource:
        size += _value_size(span.resource.attributes)
        size += _value_size(span.resource.schema_url)
    scope = span.instrumentation_scope
    if scope:
        size += _value_size((scope.name, scope.version, scope.schema_url))
        size += _value_size(scope.attributes)
    for event in span.events or ():
        size += 128 + _value_size(event.name) + _value_size(event.attributes)
    for link in span.links or ():
        size += 128 + _value_size(link.attributes)
        size += _value_size(dict(link.context.trace_state.items()))
    return size


# ======== Adapted from Google ADK ========
class _InMemoryExporter(export.SpanExporter):
    """Bounded local span history, independent of cloud exporter delivery"""

    def __init__(
        self, max_spans: int = 1024, max_bytes: int = 16 * 1024 * 1024
    ) -> None:
        super().__init__()
        if max_spans < 0 or max_bytes < 0:
            raise ValueError("In-memory tracing limits must be nonnegative")
        self._max_spans = max_spans
        self._max_bytes = max_bytes
        self._spans: deque[ReadableSpan] = deque()
        self._span_sizes: deque[int] = deque()
        self._retained_bytes = 0
        self._lock = Lock()
        self._shutdown = False
        self.trace_id = ""

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> export.SpanExportResult:
        """Retain recent spans within both limits without changing their contents"""
        with self._lock:
            if self._shutdown:
                return export.SpanExportResult.SUCCESS
            for span in spans:
                if span.context:
                    self.trace_id = span.context.trace_id
                if not self._max_spans or not self._max_bytes:
                    continue
                size = _span_size(span)
                if size > self._max_bytes:
                    continue
                while self._spans and (
                    len(self._spans) >= self._max_spans
                    or self._retained_bytes + size > self._max_bytes
                ):
                    self._spans.popleft()
                    self._retained_bytes -= self._span_sizes.popleft()
                self._spans.append(span)
                self._span_sizes.append(size)
                self._retained_bytes += size
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

    def _session_traces(self) -> dict[str, dict[int, None]]:
        """Build an index only from retained anchors while holding the cache lock"""
        sessions: dict[str, dict[int, None]] = {}
        for span in self._spans:
            if span.name == "call_llm" and span.context:
                session_id = (span.attributes or {}).get("gen_ai.session.id")
                if isinstance(session_id, str) and session_id:
                    sessions.setdefault(session_id, {})[span.context.trace_id] = None
        return sessions

    @property
    def session_trace_dict(self) -> dict[str, list[int]]:
        """Return a snapshot with no independently retained session metadata"""
        with self._lock:
            return {key: list(traces) for key, traces in self._session_traces().items()}

    def get_finished_spans(self, session_id: str) -> list[ReadableSpan]:
        """Return retained session spans; evicted history is unavailable locally"""
        with self._lock:
            trace_ids = self._session_traces().get(session_id, {})
            return [
                span
                for span in self._spans
                if span.context and span.context.trace_id in trace_ids
            ]

    def clear(self):
        """Reset local history, accounting, session mappings, and the trace ID"""
        with self._lock:
            self._clear()

    def _clear(self) -> None:
        self._spans.clear()
        self._span_sizes.clear()
        self._retained_bytes = 0
        self.trace_id = ""

    @override
    def shutdown(self) -> None:
        """Release history and stop retaining spans after provider shutdown"""
        with self._lock:
            self._shutdown = True
            self._clear()


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
            # ADK telemetry schema v2 may omit the legacy ``invocation`` span.
            # Carry the suppression flag on the agent span as well so native
            # inference spans and metrics remain deduplicated across versions.
            ctx = set_value(
                "suppress_language_model_instrumentation", True, context=ctx
            )
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
        - Recent history is bounded by configured span and estimated byte limits
        - Disabling retention preserves annotation and cloud export behavior
        - Session tracking requires properly configured session IDs
    """

    def __init__(self, name: str = "inmemory_exporter") -> None:
        """Initialize the in-memory exporter with internal components.

        Args:
            name: Identifier for this exporter instance.
        """
        super().__init__()

        self.name = name

        from veadk.config import settings

        config = settings.opentelemetry_config
        self._exporter = _InMemoryExporter(
            max_spans=config.inmemory_max_spans if config.inmemory_enabled else 0,
            max_bytes=config.inmemory_max_bytes,
        )
        self.processor = _InMemorySpanProcessor(self._exporter)

    @classmethod
    def for_provider(cls, provider: TracerProvider) -> "InMemoryExporter":
        """Reuse one annotation processor and bounded cache for each provider"""
        with _registration_lock:
            existing = getattr(provider, "_veadk_inmemory_exporter", None)
            if existing is not None:
                return existing
            exporter = cls()
            # Preserve first-processor annotation order without racing registration
            processors = provider._active_span_processor
            with processors._lock:
                processors._span_processors = (
                    exporter.processor,
                ) + processors._span_processors
            provider._veadk_inmemory_exporter = exporter
            return exporter
