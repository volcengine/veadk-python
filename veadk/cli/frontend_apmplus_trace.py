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

import time
from typing import Any, cast

import volcenginesdkcore
from volcenginesdkapmplusserver import (
    APMPLUSSERVERApi,
    FilterForListSpanInput,
    ListSpanRequest,
)

_SESSION_TAGS = (
    "gen_ai.session.id",
    "gen_ai.conversation.id",
    "gcp.vertex.agent.session_id",
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
    return any(str(tags.get(key) or "") == value for key in keys)


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

    def matching_spans(rows: list[object]) -> list[dict[str, Any]]:
        session_spans: list[dict[str, Any]] = []
        invocation_trace_ids: set[str] = set()
        for row in rows:
            span = _span_dict(row)
            tags = _span_tags(span)
            if not _matches_tag(tags, _SESSION_TAGS, session_id):
                continue
            runtime_tags = [str(tags.get(key) or "") for key in _RUNTIME_TAGS]
            runtime_tags = [value for value in runtime_tags if value]
            if runtime_tags and runtime_id not in runtime_tags:
                continue
            session_spans.append(span)
            if invocation_id and _matches_tag(
                tags,
                _INVOCATION_TAGS,
                invocation_id,
            ):
                invocation_trace_ids.add(str(span.get("trace_id") or ""))
        if invocation_trace_ids:
            return [
                span
                for span in session_spans
                if str(span.get("trace_id") or "") in invocation_trace_ids
            ]
        return session_spans

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
                            values=["POST /run_sse"],
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
            session_spans = matching_spans(list(response.span_list or []))
            if session_spans:
                return session_spans
        return []

    session_spans: list[dict[str, Any]] = []
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
        session_spans.extend(matching_spans(rows))
        if len(rows) < _PAGE_SIZE:
            break
    return session_spans
