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
    assert requests[0].filters[0].key == "operation_name"
    assert requests[0].filters[0].op == "in"
    assert requests[1].filters[0].key == "trace_id"


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
