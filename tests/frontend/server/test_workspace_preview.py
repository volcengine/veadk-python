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

from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.workspace_preview import (
    aio_url,
    mount_workspace_preview_routes,
)
from veadk.cli.frontend_sandbox import SandboxCloudSession


def cloud(owner="alice", session_id="session-1"):
    return SandboxCloudSession(
        tool_id="tool-1",
        instance_id=session_id,
        user_session_id="user-session",
        endpoint="https://sandbox.example/?Authorization=test&faasInstanceName=instance",
        status="Ready",
        created_by=owner,
        agent_kind="workspace-preview",
        expire_at="2099-01-01T00:00:00Z",
    )


def gateway():
    result = AsyncMock()
    result.create_session.return_value = cloud()
    result.get_session.return_value = cloud()
    return result


def test_aio_url_preserves_routing_and_rejects_unsafe_schemes():
    assert (
        aio_url("https://sandbox.example/base?Authorization=test#fragment")
        == "https://sandbox.example/base/?Authorization=test"
    )
    for endpoint in (
        "http://sandbox.example",
        "javascript:alert(1)",
        "https://user@sandbox.example",
    ):
        with pytest.raises(ValueError):
            aio_url(endpoint)


def test_aio_url_adds_workspace_folder_without_reencoding_credentials():
    endpoint = (
        "https://sandbox.example/base?Authorization=a%2Bb%20c&faasInstanceName=instance"
    )
    result = aio_url(endpoint, folder="/home/gem/Projects/测试 agent")
    assert result.startswith(endpoint.replace("/base?", "/base/?") + "&folder=")
    assert parse_qs(urlsplit(result).query)["folder"] == [
        "/home/gem/Projects/测试 agent"
    ]


def test_aio_url_preserves_existing_folder_without_duplicates():
    endpoint = (
        "https://sandbox.example/?folder=%2Fhome%2Fgem%2Fother&Authorization=a%2Bb"
    )
    assert aio_url(endpoint, folder="/home/gem/Projects") == endpoint


@pytest.mark.parametrize(
    "folder", ["Projects", "/home/gem/../etc", "/home/gem/\x00Projects"]
)
def test_aio_url_rejects_invalid_workspace_folder(folder):
    with pytest.raises(ValueError, match="folder"):
        aio_url("https://sandbox.example/", folder=folder)


def test_project_api_requires_name_and_opens_named_directory(monkeypatch):
    from frontend.server.workspace_projects import PersistentWorkspaceProjects

    monkeypatch.setenv("STUDIO_WORKSPACE_TOOL_ID", "tool-1")
    app = FastAPI()
    opened = AsyncMock(return_value=cloud())
    monkeypatch.setattr(PersistentWorkspaceProjects, "open", opened)
    mount_workspace_preview_routes(
        app, gateway(), lambda request: "alice", lambda request: "Alice"
    )
    with TestClient(app) as client:
        assert (
            client.post("/web/workspace-preview/projects", json={}).status_code == 422
        )
        assert (
            client.post(
                "/web/workspace-preview/projects", json={"name": "../bad"}
            ).status_code
            == 422
        )
        response = client.post("/web/workspace-preview/projects/my-agent/open")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    parts = urlsplit(response.json()["url"])
    assert parts.path == "/code-server/"
    assert parse_qs(parts.query)["folder"] == ["/home/gem/Projects/my-agent"]
    opened.assert_awaited_once_with("alice", "Alice", "my-agent")
