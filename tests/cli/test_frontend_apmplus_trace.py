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

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from veadk.cli.frontend_apmplus_trace import (
    load_apmplus_trace,
    normalize_apmplus_trace,
)


class _Span:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def to_dict(self) -> dict[str, Any]:
        return self.value


def test_apmplus_trace_filters_session_runtime_and_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[Any] = []
    rows = [
        _Span(
            {
                "trace_id": "trace-1",
                "span_id": "span-1",
                "tags": {
                    "gen_ai.session.id": "session-1",
                    "cozeloop_agent_runtime_id": "runtime-1",
                    "gen_ai.invocation.id": "invocation-1",
                },
            }
        ),
        _Span(
            {
                "trace_id": "trace-1",
                "span_id": "span-2",
                "tags": {
                    "gen_ai.session.id": "session-1",
                    "cozeloop_agent_runtime_id": "runtime-1",
                },
            }
        ),
        _Span(
            {
                "trace_id": "trace-2",
                "span_id": "span-3",
                "tags": {"gen_ai.session.id": "another-session"},
            }
        ),
    ]

    class _FakeApi:
        def __init__(self, _client: object) -> None:
            pass

        def list_span(self, request: Any) -> SimpleNamespace:
            requests.append(request)
            if request.tag_filters:
                tag_filter = request.tag_filters[0]
                return SimpleNamespace(
                    span_list=[
                        row
                        for row in rows
                        if str(row.value.get("tags", {}).get(tag_filter.key) or "")
                        in tag_filter.values
                    ]
                )
            if request.filters and request.filters[0].key == "trace_id":
                trace_ids = request.filters[0].values
                return SimpleNamespace(
                    span_list=[
                        row for row in rows if row.value.get("trace_id") in trace_ids
                    ]
                )
            return SimpleNamespace(span_list=rows)

    monkeypatch.setattr(
        "veadk.cli.frontend_apmplus_trace.APMPLUSSERVERApi",
        _FakeApi,
    )

    trace = load_apmplus_trace(
        access_key="ak",
        secret_key="sk",
        session_token="token",
        region="cn-beijing",
        project_name="default",
        runtime_id="runtime-1",
        session_id="session-1",
        invocation_id="invocation-1",
        now_ms=1_800_000_000_000,
    )

    assert [span["span_id"] for span in trace] == ["span-1", "span-2"]
    assert requests[0].project_name == "default"
    assert requests[0].order_by == "start_time"
    assert requests[0].tag_filters[0].key == "invocation.id"
    assert requests[1].tag_filters[0].key == "gen_ai.invocation.id"
    assert requests[2].filters[0].key == "trace_id"


def test_apmplus_trace_prefers_event_over_invocation_in_same_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows_by_trace = {
        "trace-invocation": [
            _Span(
                {
                    "trace_id": "trace-invocation",
                    "span_id": "span-invocation",
                    "tags": {
                        "gen_ai.session.id": "session-1",
                        "cozeloop_agent_runtime_id": "runtime-1",
                        "invocation.id": "invocation-1",
                    },
                }
            )
        ],
        "trace-event": [
            _Span(
                {
                    "trace_id": "trace-event",
                    "span_id": "span-event",
                    "tags": {
                        "gen_ai.session.id": "session-1",
                        "cozeloop_agent_runtime_id": "runtime-1",
                        "gcp.vertex.agent.event_id": "event-1",
                    },
                }
            ),
            _Span(
                {
                    "trace_id": "trace-event",
                    "span_id": "span-event-child",
                    "tags": {},
                }
            ),
        ],
    }

    class _FakeApi:
        def __init__(self, _client: object) -> None:
            pass

        def list_span(self, request: Any) -> SimpleNamespace:
            if request.tag_filters:
                return SimpleNamespace(span_list=[])
            filters = request.filters or []
            if filters and filters[0].key == "operation_name":
                return SimpleNamespace(
                    span_list=[
                        _Span(
                            {
                                "trace_id": trace_id,
                                "start_time_millisecond": index,
                            }
                        )
                        for index, trace_id in enumerate(rows_by_trace)
                    ]
                )
            if filters and filters[0].key == "trace_id":
                return SimpleNamespace(span_list=rows_by_trace[filters[0].values[0]])
            return SimpleNamespace(
                span_list=[row for rows in rows_by_trace.values() for row in rows]
            )

    monkeypatch.setattr(
        "veadk.cli.frontend_apmplus_trace.APMPLUSSERVERApi",
        _FakeApi,
    )

    trace = load_apmplus_trace(
        access_key="ak",
        secret_key="sk",
        session_token="token",
        region="cn-beijing",
        project_name="default",
        runtime_id="runtime-1",
        session_id="session-1",
        event_id="event-1",
        invocation_id="invocation-1",
        now_ms=1_800_000_000_000,
    )

    assert [span["span_id"] for span in trace] == [
        "span-event",
        "span-event-child",
    ]


def test_apmplus_trace_falls_back_from_event_to_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _Span(
            {
                "trace_id": "trace-1",
                "span_id": "span-1",
                "tags": {
                    "gen_ai.session.id": "session-1",
                    "invocation.id": "invocation-1",
                },
            }
        ),
        _Span(
            {
                "trace_id": "trace-2",
                "span_id": "span-2",
                "tags": {"gen_ai.session.id": "session-1"},
            }
        ),
    ]

    class _FakeApi:
        def __init__(self, _client: object) -> None:
            pass

        def list_span(self, request: Any) -> SimpleNamespace:
            if request.tag_filters:
                return SimpleNamespace(span_list=[])
            return SimpleNamespace(span_list=rows)

    monkeypatch.setattr(
        "veadk.cli.frontend_apmplus_trace.APMPLUSSERVERApi",
        _FakeApi,
    )

    trace = load_apmplus_trace(
        access_key="ak",
        secret_key="sk",
        session_token="token",
        region="cn-beijing",
        project_name="default",
        runtime_id="runtime-1",
        session_id="session-1",
        event_id="missing-event",
        invocation_id="invocation-1",
        now_ms=1_800_000_000_000,
    )

    assert [span["span_id"] for span in trace] == ["span-1"]

    missing = load_apmplus_trace(
        access_key="ak",
        secret_key="sk",
        session_token="token",
        region="cn-beijing",
        project_name="default",
        runtime_id="runtime-1",
        session_id="session-1",
        event_id="missing-event",
        invocation_id="missing-invocation",
        now_ms=1_800_000_000_000,
    )

    assert missing == []


def test_apmplus_trace_matches_associated_event_ids_json_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _Span(
            {
                "trace_id": "trace-1",
                "span_id": "span-1",
                "tags": {
                    "gen_ai.session.id": "session-1",
                    "gcp.vertex.agent.associated_event_ids": (
                        '["earlier-event", "event-1"]'
                    ),
                },
            }
        ),
        _Span(
            {
                "trace_id": "trace-1",
                "span_id": "span-child-without-tags",
                "tags": {},
            }
        ),
    ]

    class _FakeApi:
        def __init__(self, _client: object) -> None:
            pass

        def list_span(self, request: Any) -> SimpleNamespace:
            if request.tag_filters:
                return SimpleNamespace(span_list=[])
            return SimpleNamespace(span_list=rows)

    monkeypatch.setattr(
        "veadk.cli.frontend_apmplus_trace.APMPLUSSERVERApi",
        _FakeApi,
    )

    trace = load_apmplus_trace(
        access_key="ak",
        secret_key="sk",
        session_token="token",
        region="cn-beijing",
        project_name="default",
        runtime_id="runtime-1",
        session_id="session-1",
        event_id="event-1",
    )

    assert [span["span_id"] for span in trace] == [
        "span-1",
        "span-child-without-tags",
    ]


def test_normalize_apmplus_trace_converts_span_shape_for_frontend() -> None:
    spans = normalize_apmplus_trace(
        [
            {
                "operation_name": "invoke_agent demo",
                "span_id": "span-1",
                "trace_id": "trace-1",
                "parent_span_id": "parent-1",
                "start_time_microsecond": 1_000,
                "duration_microseconds": 250,
                "status": "OK",
                "service_name": "demo-service",
                "gen_ai_input": "hello",
                "tags": {"gen_ai.session.id": "session-1"},
            }
        ]
    )

    assert spans == [
        {
            "name": "invoke_agent demo",
            "span_id": "span-1",
            "trace_id": "trace-1",
            "start_time": 1_000_000,
            "end_time": 1_250_000,
            "parent_span_id": "parent-1",
            "attributes": {
                "gen_ai.session.id": "session-1",
                "status": "OK",
                "service.name": "demo-service",
                "gen_ai.input": "hello",
            },
        }
    ]


def test_apmplus_trace_falls_back_when_runtime_root_operation_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[Any] = []

    class _FakeApi:
        def __init__(self, _client: object) -> None:
            pass

        def list_span(self, request: Any) -> SimpleNamespace:
            requests.append(request)
            if request.filters:
                return SimpleNamespace(span_list=[])
            return SimpleNamespace(
                span_list=[
                    _Span(
                        {
                            "trace_id": "trace-1",
                            "span_id": "span-1",
                            "tags": {"session.id": "session-1"},
                        }
                    )
                ]
            )

    monkeypatch.setattr(
        "veadk.cli.frontend_apmplus_trace.APMPLUSSERVERApi",
        _FakeApi,
    )

    trace = load_apmplus_trace(
        access_key="ak",
        secret_key="sk",
        session_token="token",
        region="cn-beijing",
        project_name="default",
        runtime_id="runtime-1",
        session_id="session-1",
        now_ms=1_800_000_000_000,
    )

    assert [span["span_id"] for span in trace] == ["span-1"]
    assert requests[0].filters[0].key == "operation_name"
    assert requests[0].filters[0].values == [
        "POST /run_sse",
        "POST /harness/run_sse",
    ]
    assert requests[1].filters is None
