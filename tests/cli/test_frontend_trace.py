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
"""Tests for the frontend session trace endpoint."""

from types import SimpleNamespace
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult

from veadk.cli.cli_frontend import _mount_session_trace_route
from veadk.cli.frontend_trace import SessionTraceExporter


class _MemoryExporter:
    """Small exporter stub that returns spans for one session."""

    def get_finished_spans(self, session_id: str) -> list[SimpleNamespace]:
        if session_id != "session-1":
            return []
        return [
            SimpleNamespace(
                name="call_llm",
                context=SimpleNamespace(span_id=11, trace_id=22),
                start_time=100,
                end_time=200,
                attributes={"gen_ai.conversation.id": session_id},
                parent=SimpleNamespace(span_id=10),
            )
        ]


def test_session_trace_route_returns_json_spans() -> None:
    app = FastAPI()
    _mount_session_trace_route(app, _MemoryExporter())

    response = TestClient(app).get("/dev/apps/demo/debug/trace/session/session-1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == [
        {
            "name": "call_llm",
            "span_id": 11,
            "trace_id": 22,
            "start_time": 100,
            "end_time": 200,
            "attributes": {"gen_ai.conversation.id": "session-1"},
            "parent_span_id": 10,
        }
    ]


def test_session_trace_route_returns_empty_json_array() -> None:
    app = FastAPI()
    _mount_session_trace_route(app, _MemoryExporter())

    response = TestClient(app).get("/dev/apps/demo/debug/trace/session/unknown")

    assert response.status_code == 200
    assert response.json() == []


def test_session_trace_exporter_groups_spans_without_google_adk_internals() -> None:
    exporter = SessionTraceExporter()
    matching = SimpleNamespace(
        name="call_llm",
        context=SimpleNamespace(trace_id=22),
        attributes={"gcp.vertex.agent.session_id": "session-1"},
    )
    child = SimpleNamespace(
        name="execute_tool",
        context=SimpleNamespace(trace_id=22),
        attributes={},
    )
    unrelated = SimpleNamespace(
        name="call_llm",
        context=SimpleNamespace(trace_id=33),
        attributes={"gcp.vertex.agent.session_id": "session-2"},
    )

    result = exporter.export(cast(list[ReadableSpan], [matching, child, unrelated]))

    assert result == SpanExportResult.SUCCESS
    assert exporter.get_finished_spans("session-1") == [matching, child]
    assert exporter.get_finished_spans("unknown") == []
