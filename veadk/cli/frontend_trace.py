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

"""Stable trace exporter used by the frontend session trace endpoint."""

from __future__ import annotations

import threading

from collections.abc import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

_SESSION_ID_ATTRIBUTES = (
    "gcp.vertex.agent.session_id",
    "gen_ai.conversation.id",
)


class SessionTraceExporter(SpanExporter):
    """Keep finished spans in memory and index their trace IDs by session."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._spans: list[ReadableSpan] = []
        self._trace_ids: dict[str, set[int]] = {}

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self._lock:
            for span in spans:
                if span.name != "call_llm":
                    continue
                context = span.context
                if context is None:
                    continue
                attributes = span.attributes or {}
                session_id = next(
                    (
                        str(attributes[key])
                        for key in _SESSION_ID_ATTRIBUTES
                        if attributes.get(key)
                    ),
                    "",
                )
                if session_id:
                    self._trace_ids.setdefault(session_id, set()).add(context.trace_id)
            self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def get_finished_spans(self, session_id: str) -> list[ReadableSpan]:
        with self._lock:
            trace_ids = self._trace_ids.get(session_id, set())
            return [
                span
                for span in self._spans
                if span.context is not None and span.context.trace_id in trace_ids
            ]
