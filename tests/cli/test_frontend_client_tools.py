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

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from veadk.cli import frontend_client_tools


def _app() -> tuple[FastAPI, list[str], list[int]]:
    app = FastAPI()
    authorized: list[str] = []
    credential_calls: list[int] = []

    def authorize(request: Request) -> None:
        authorized.append(request.url.path)

    def credentials() -> tuple[str, str, str | None]:
        credential_calls.append(1)
        return ("ak", "sk", "token")

    frontend_client_tools.mount_frontend_client_tool_routes(
        app,
        authorize=authorize,
        credentials=credentials,
    )
    return app, authorized, credential_calls


def test_capabilities_lists_frontend_owned_tools_without_loading_credentials() -> None:
    app, authorized, credential_calls = _app()

    response = TestClient(app).get("/web/client-tools/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "protocols": {"client_tools": {"version": 1}},
        "tools": [
            "ppt_generate",
            "image_generate",
            "image_edit",
            "video_generate",
            "video_task_query",
        ],
    }
    assert authorized == ["/web/client-tools/capabilities"]
    assert credential_calls == []


@pytest.mark.asyncio
async def test_execute_ppt_returns_base64_download_without_cloud_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def create_pptx(
        spec: dict[str, object],
        output: Path,
        preview: Path,
    ) -> None:
        assert spec["title"] == "Demo"
        output.write_bytes(b"pptx")
        preview.write_bytes(b"preview")

    from veadk.tools.builtin_tools import ppt_generate

    monkeypatch.setattr(ppt_generate, "_create_pptx", create_pptx)
    app, authorized, credential_calls = _app()
    response = TestClient(app).post(
        "/web/client-tools/execute",
        json={
            "name": "ppt_generate",
            "arguments": {
                "title": "Demo",
                "deck_markdown": "## Result\nSummary\n- Works",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["slide_count"] == 2
    assert base64.b64decode(payload["downloads"][0]["data"]) == b"pptx"
    assert authorized == ["/web/client-tools/execute"]
    assert credential_calls == []


@pytest.mark.parametrize(
    ("name", "arguments", "expected_method", "expected_path"),
    [
        (
            "image_generate",
            {"tasks": [{"task_type": "text_to_single", "prompt": "cat"}]},
            "POST",
            "/images/generations",
        ),
        (
            "image_edit",
            {
                "params": [
                    {
                        "origin_image": "data:image/png;base64,eA==",
                        "prompt": "blue",
                    }
                ]
            },
            "POST",
            "/images/generations",
        ),
        (
            "video_generate",
            {"params": [{"video_name": "demo", "prompt": "waves"}]},
            "POST",
            "/contents/generations/tasks",
        ),
        (
            "video_task_query",
            {"task_id": "task-1"},
            "GET",
            "/contents/generations/tasks/task-1",
        ),
    ],
)
def test_execute_media_dispatches_with_injected_credentials(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    arguments: dict[str, Any],
    expected_method: str,
    expected_path: str,
) -> None:
    calls: list[dict[str, Any]] = []

    async def request_json(
        method: str,
        url: str,
        *,
        credentials: tuple[str, str, str | None],
        body: dict[str, Any] | None = None,
        timeout: float = 600,
    ) -> dict[str, Any]:
        calls.append(
            {
                "method": method,
                "url": url,
                "credentials": credentials,
                "body": body,
                "timeout": timeout,
            }
        )
        return {"id": "task-1", "status": "running"}

    monkeypatch.setattr(frontend_client_tools, "_request_json", request_json)
    app, _, credential_calls = _app()
    response = TestClient(app).post(
        "/web/client-tools/execute",
        json={"name": name, "arguments": arguments},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["method"] == expected_method
    assert calls[0]["url"].endswith(expected_path)
    assert calls[0]["credentials"] == ("ak", "sk", "token")
    assert credential_calls == [1]


def test_execute_rejects_unknown_tool() -> None:
    app, _, credential_calls = _app()

    response = TestClient(app).post(
        "/web/client-tools/execute",
        json={"name": "unknown", "arguments": {}},
    )

    assert response.status_code == 404
    assert credential_calls == []
