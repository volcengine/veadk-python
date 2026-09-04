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
"""Tests for frontend dev web endpoints."""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
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


def _write_agent_app(tmp_path: Path, app_name: str, source: str) -> None:
    app_dir = tmp_path / app_name
    app_dir.mkdir()
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "agent.py").write_text(source, encoding="utf-8")


_MISSING = object()


@contextmanager
def _build_adk_web_client(tmp_path: Path) -> Iterator[TestClient]:
    from google.adk.cli.fast_api import get_fast_api_app

    from veadk.utils.patches import patch_adk_build_graph_serialization

    original_sys_path = list(sys.path)
    app_names = [path.name for path in tmp_path.iterdir() if path.is_dir()]
    module_names = {name for name in app_names}
    module_names.update(f"{name}.agent" for name in app_names)
    original_modules = {name: sys.modules.get(name, _MISSING) for name in module_names}
    patch_adk_build_graph_serialization()
    try:
        app = get_fast_api_app(agents_dir=str(tmp_path), web=True)
        with TestClient(app) as client:
            yield client
    finally:
        sys.path[:] = original_sys_path
        for name, module in original_modules.items():
            if module is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        importlib.invalidate_caches()


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


def test_session_trace_exporter_indexes_failed_trace_before_first_llm_token() -> None:
    exporter = SessionTraceExporter()
    failed_llm = SimpleNamespace(
        name="call_llm",
        context=SimpleNamespace(trace_id=44),
        attributes={},
    )
    failed_inference = SimpleNamespace(
        name="generate_content test-model",
        context=SimpleNamespace(trace_id=44),
        attributes={"gen_ai.conversation.id": "session-failed"},
    )
    failed_agent = SimpleNamespace(
        name="invoke_agent demo",
        context=SimpleNamespace(trace_id=44),
        attributes={"gen_ai.conversation.id": "session-failed"},
    )

    exporter.export(
        cast(
            list[ReadableSpan],
            [failed_llm, failed_inference, failed_agent],
        )
    )

    assert exporter.get_finished_spans("session-failed") == [
        failed_llm,
        failed_inference,
        failed_agent,
    ]


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_build_graph_serializes_veadk_agent_model(tmp_path: Path) -> None:
    _write_agent_app(
        tmp_path,
        "demo_agent",
        """
from veadk import Agent


def hello() -> str:
    return "ok"


root_agent = Agent(
    name="demo_agent",
    model_name="test_model",
    model_provider="test_provider",
    model_api_key="test_key",
    model_api_base="test_base",
    tools=[hello],
)
""",
    )

    with _build_adk_web_client(tmp_path) as client:
        response = client.get("/dev/apps/demo_agent/build_graph")

    assert response.status_code == 200
    payload = response.json()
    encoded = json.dumps(payload)
    assert payload["root_agent"]["model"] == "test_provider/test_model"
    assert payload["root_agent"]["tools"] == [{"name": "hello", "type": "tool"}]
    assert "llm_client" not in encoded
    assert "LiteLLMClient" not in encoded


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_build_graph_serializes_nested_veadk_agent_models(tmp_path: Path) -> None:
    _write_agent_app(
        tmp_path,
        "nested_agent",
        """
from veadk import Agent


child_agent = Agent(
    name="child_agent",
    model_name="child_model",
    model_provider="child_provider",
    model_api_key="test_key",
    model_api_base="test_base",
)

root_agent = Agent(
    name="root_agent",
    model_name="root_model",
    model_provider="root_provider",
    model_api_key="test_key",
    model_api_base="test_base",
    sub_agents=[child_agent],
)
""",
    )

    with _build_adk_web_client(tmp_path) as client:
        response = client.get("/dev/apps/nested_agent/build_graph")

    assert response.status_code == 200
    payload = response.json()
    encoded = json.dumps(payload)
    assert payload["root_agent"]["model"] == "root_provider/root_model"
    assert payload["root_agent"]["sub_agents"][0]["model"] == (
        "child_provider/child_model"
    )
    assert "llm_client" not in encoded
    assert "LiteLLMClient" not in encoded
