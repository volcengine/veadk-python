# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Read AgentKit Runtime traces from APMPlus for Studio issue reports."""

from __future__ import annotations

import json
import time
from typing import Any, cast

import volcenginesdkcore
from volcenginesdkapmplusserver import (
    APMPLUSSERVERApi,
    FilterForListSpanInput,
    ListSpanRequest,
    TagFilterForListSpanInput,
)

_SESSION_TAGS = (
    "gen_ai.session.id",
    "gen_ai.conversation.id",
    "gcp.vertex.agent.session_id",
    "session.id",
    "session_id",
)
_EVENT_TAGS = (
    "gcp.vertex.agent.event_id",
    "gcp.vertex.agent.associated_event_ids",
    "event.id",
    "gen_ai.event.id",
    "adk.event.id",
    "event_id",
)
_INVOCATION_TAGS = (
    "invocation.id",
    "gen_ai.invocation.id",
    "gcp.vertex.agent.invocation_id",
)
_RUNTIME_TAGS = (
    "cozeloop_agent_runtime_id",
    "agentkit.runtime.id",
    "runtime.id",
)
_QUERY_WINDOW_MS = 2 * 60 * 60 * 1000
_PAGE_SIZE = 200
_MAX_PAGES = 5
_TRACE_CANDIDATE_WINDOW_MS = 2 * 60 * 1000
_TRACE_END_BUFFER_MS = 60 * 1000
_MAX_TRACE_CANDIDATES = 20


def _span_dict(span: object) -> dict[str, Any]:
    to_dict = getattr(span, "to_dict", None)
    value = to_dict() if callable(to_dict) else span
    return value if isinstance(value, dict) else {}


def _span_tags(span: dict[str, Any]) -> dict[str, Any]:
    tags = span.get("tags")
    return tags if isinstance(tags, dict) else {}


def _matches_tag(tags: dict[str, Any], keys: tuple[str, ...], value: str) -> bool:
    for key in keys:
        tag_value = tags.get(key)
        if isinstance(tag_value, (list, tuple, set)):
            if value in {str(item) for item in tag_value}:
                return True
            continue
        if isinstance(tag_value, str) and tag_value.startswith("["):
            try:
                decoded = json.loads(tag_value)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, list) and value in {str(item) for item in decoded}:
                return True
        if str(tag_value or "") == value:
            return True
    return False


def normalize_apmplus_trace(
    spans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert APMPlus spans to the trace shape consumed by Studio."""
    normalized: list[dict[str, Any]] = []
    attribute_fields = (
        ("status", "status"),
        ("service_name", "service.name"),
        ("service_type", "service.type"),
        ("span_type", "span.type"),
        ("gen_ai_input", "gen_ai.input"),
        ("gen_ai_output", "gen_ai.output"),
    )
    for span in spans:
        start_time = int(span.get("start_time_microsecond") or 0) * 1_000
        duration = max(int(span.get("duration_microseconds") or 0), 0) * 1_000
        attributes = dict(_span_tags(span))
        for source, target in attribute_fields:
            value = span.get(source)
            if value not in (None, ""):
                attributes[target] = value
        parent_span_id = str(span.get("parent_span_id") or "") or None
        normalized.append(
            {
                "name": str(
                    span.get("operation_name") or span.get("api_name") or "未命名调用"
                ),
                "span_id": str(span.get("span_id") or ""),
                "trace_id": str(span.get("trace_id") or ""),
                "start_time": start_time,
                "end_time": start_time + duration,
                "parent_span_id": parent_span_id,
                "attributes": attributes,
            }
        )
    return normalized


def load_apmplus_trace(
    *,
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str,
    project_name: str,
    runtime_id: str,
    session_id: str,
    event_id: str = "",
    invocation_id: str = "",
    now_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Return recent APMPlus spans associated with one Studio session."""
    if not session_id:
        return []

    configuration = volcenginesdkcore.Configuration()
    configuration.ak = access_key
    configuration.sk = secret_key
    configuration.session_token = session_token
    configuration.region = region
    api = APMPLUSSERVERApi(volcenginesdkcore.ApiClient(configuration))

    end_time = now_ms if now_ms is not None else int(time.time() * 1000)
    query_end_time = end_time + (_TRACE_END_BUFFER_MS if now_ms is not None else 0)

    def session_runtime_spans(rows: list[object]) -> list[dict[str, Any]]:
        spans = [_span_dict(row) for row in rows]
        session_trace_ids = {
            str(span.get("trace_id") or "")
            for span in spans
            if span.get("trace_id")
            and _matches_tag(_span_tags(span), _SESSION_TAGS, session_id)
        }
        eligible_trace_ids: set[str] = set()
        for trace_id in session_trace_ids:
            runtime_values = {
                str(tags.get(key) or "")
                for span in spans
                if str(span.get("trace_id") or "") == trace_id
                for tags in [_span_tags(span)]
                for key in _RUNTIME_TAGS
                if tags.get(key)
            }
            if not runtime_values or runtime_id in runtime_values:
                eligible_trace_ids.add(trace_id)
        return [
            span
            for span in spans
            if str(span.get("trace_id") or "") in eligible_trace_ids
        ]

    def trace_for_tag(
        spans: list[dict[str, Any]],
        keys: tuple[str, ...],
        value: str,
    ) -> list[dict[str, Any]]:
        if not value:
            return []
        trace_ids = {
            str(span.get("trace_id") or "")
            for span in spans
            if _matches_tag(_span_tags(span), keys, value) and span.get("trace_id")
        }
        if not trace_ids:
            return []
        return [span for span in spans if str(span.get("trace_id") or "") in trace_ids]

    def fetch_trace(trace_id: str) -> list[dict[str, Any]]:
        response = cast(
            Any,
            api.list_span(
                ListSpanRequest(
                    project_name=project_name or "default",
                    start_time=end_time - _QUERY_WINDOW_MS,
                    end_time=query_end_time,
                    limit=_PAGE_SIZE,
                    offset=0,
                    min_call_cost_millisecond=0,
                    max_call_cost_millisecond=86_400_000,
                    order="desc",
                    order_by="start_time",
                    filters=[
                        FilterForListSpanInput(
                            key="trace_id",
                            op="in",
                            values=[trace_id],
                        )
                    ],
                )
            ),
        )
        return session_runtime_spans(list(response.span_list or []))

    def trace_from_tag_filter(
        keys: tuple[str, ...],
        value: str,
    ) -> list[dict[str, Any]]:
        if not value:
            return []
        for key in keys:
            try:
                response = cast(
                    Any,
                    api.list_span(
                        ListSpanRequest(
                            project_name=project_name or "default",
                            start_time=end_time - _QUERY_WINDOW_MS,
                            end_time=query_end_time,
                            limit=_PAGE_SIZE,
                            offset=0,
                            min_call_cost_millisecond=0,
                            max_call_cost_millisecond=86_400_000,
                            order="desc",
                            order_by="start_time",
                            tag_filters=[
                                TagFilterForListSpanInput(key=key, values=[value])
                            ],
                        )
                    ),
                )
            except Exception:  # noqa: BLE001, S112 - compatibility scan follows
                continue
            trace_ids = list(
                dict.fromkeys(
                    str(_span_dict(row).get("trace_id") or "")
                    for row in response.span_list or []
                    if _span_dict(row).get("trace_id")
                )
            )
            for trace_id in trace_ids:
                spans = fetch_trace(trace_id)
                matched_trace = trace_for_tag(spans, keys, value)
                if matched_trace:
                    return matched_trace
        return []

    direct_event_trace = trace_from_tag_filter(_EVENT_TAGS, event_id)
    if direct_event_trace:
        return direct_event_trace
    direct_invocation_trace = trace_from_tag_filter(
        _INVOCATION_TAGS,
        invocation_id,
    )
    if direct_invocation_trace and not event_id:
        return direct_invocation_trace

    candidate_invocation_trace: list[dict[str, Any]] = []

    if now_ms is not None:
        candidates = cast(
            Any,
            api.list_span(
                ListSpanRequest(
                    project_name=project_name or "default",
                    start_time=end_time - _TRACE_CANDIDATE_WINDOW_MS,
                    end_time=query_end_time,
                    limit=_PAGE_SIZE,
                    offset=0,
                    min_call_cost_millisecond=0,
                    max_call_cost_millisecond=86_400_000,
                    order="desc",
                    order_by="start_time",
                    filters=[
                        FilterForListSpanInput(
                            key="operation_name",
                            op="in",
                            values=["POST /run_sse", "POST /harness/run_sse"],
                        )
                    ],
                )
            ),
        )
        candidate_spans = [_span_dict(row) for row in candidates.span_list or []]
        candidate_spans.sort(
            key=lambda span: abs(
                int(span.get("start_time_millisecond") or end_time) - end_time
            )
        )
        trace_ids = list(
            dict.fromkeys(
                str(span.get("trace_id") or "")
                for span in candidate_spans
                if span.get("trace_id")
            )
        )[:_MAX_TRACE_CANDIDATES]
        for trace_id in trace_ids:
            scoped_spans = fetch_trace(trace_id)
            if not scoped_spans:
                continue
            event_trace = trace_for_tag(scoped_spans, _EVENT_TAGS, event_id)
            if event_trace:
                return event_trace
            invocation_trace = trace_for_tag(
                scoped_spans,
                _INVOCATION_TAGS,
                invocation_id,
            )
            if invocation_trace and not event_id:
                return invocation_trace
            if invocation_trace and not candidate_invocation_trace:
                candidate_invocation_trace = invocation_trace
            if not event_id and not invocation_id:
                return scoped_spans
        # Runtime versions do not all use the same HTTP operation name for the
        # invocation root span. Fall back to the bounded recent-span scan when
        # the fast candidate lookup cannot identify this session.

    recent_rows: list[object] = []
    for page in range(_MAX_PAGES):
        response = cast(
            Any,
            api.list_span(
                ListSpanRequest(
                    project_name=project_name or "default",
                    start_time=end_time - _QUERY_WINDOW_MS,
                    end_time=query_end_time,
                    limit=_PAGE_SIZE,
                    offset=page * _PAGE_SIZE,
                    min_call_cost_millisecond=0,
                    max_call_cost_millisecond=86_400_000,
                    order="desc",
                    order_by="start_time",
                )
            ),
        )
        rows = list(response.span_list or [])
        recent_rows.extend(rows)
        if len(rows) < _PAGE_SIZE:
            break
    session_spans = session_runtime_spans(recent_rows)
    event_trace = trace_for_tag(session_spans, _EVENT_TAGS, event_id)
    if event_trace:
        return event_trace
    if direct_invocation_trace:
        return direct_invocation_trace
    if candidate_invocation_trace:
        return candidate_invocation_trace
    invocation_trace = trace_for_tag(session_spans, _INVOCATION_TAGS, invocation_id)
    if invocation_trace:
        return invocation_trace
    if event_id or invocation_id:
        return []
    return session_spans
