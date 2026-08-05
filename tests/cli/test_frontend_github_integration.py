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
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veadk.cli.frontend_github_integration import (
    GitHubIntegrationService,
    mount_github_integration_routes,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append((method, url, kwargs))
        if url.endswith("/repos/acme/agent"):
            return _FakeResponse(200, {"default_branch": "main"})
        if "/git/ref/heads/main" in url:
            return _FakeResponse(200, {"object": {"sha": "base-sha"}})
        if method == "POST" and url.endswith("/git/refs"):
            return _FakeResponse(201, {"ref": "refs/heads/feat/agentkit-release"})
        if method == "GET" and "/contents/" in url:
            return _FakeResponse(404, {"message": "Not Found"})
        if method == "PUT" and "/contents/" in url:
            return _FakeResponse(201, {"content": {"sha": "workflow-sha"}})
        if method == "POST" and url.endswith("/pulls"):
            return _FakeResponse(
                201,
                {"number": 42, "html_url": "https://github.com/acme/agent/pull/42"},
            )
        raise AssertionError(f"unexpected GitHub request: {method} {url}")


def _app(session: _FakeSession) -> TestClient:
    app = FastAPI()
    service = GitHubIntegrationService(
        session=session, branch_factory=lambda _operation: "feat/agentkit-release"
    )
    mount_github_integration_routes(app, lambda _request: None, service=service)
    return TestClient(app)


def test_creates_agentkit_workflow_pull_request_without_persisting_token() -> None:
    session = _FakeSession()
    response = _app(session).post(
        "/web/integrations/github/pull-requests",
        json={
            "repository": "https://github.com/acme/agent.git",
            "baseBranch": "main",
            "projectPath": "examples/support_agent",
            "runtimeName": "support-agent",
            "runtimeId": "rt-support-agent",
            "region": "cn-beijing",
            "token": "github-secret-token",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "number": 42,
        "url": "https://github.com/acme/agent/pull/42",
        "branch": "feat/agentkit-release",
    }
    put_call = next(call for call in session.calls if call[0] == "PUT")
    workflow = base64.b64decode(put_call[2]["json"]["content"]).decode()
    parsed_workflow = yaml.safe_load(workflow)
    assert "Publish to AgentKit Runtime" in workflow
    assert "examples/support_agent" in workflow
    assert "support-agent" in workflow
    assert "secrets.VOLCENGINE_ACCESS_KEY" in workflow
    assert (
        parsed_workflow["jobs"]["publish"]["env"]["AGENTKIT_CLOUD_PROVIDER"]
        == "volcengine"
    )
    assert "AgentkitRuntimeClient" in workflow
    assert '"runtime_role_name": runtime_role_name' in workflow
    assert '"image_tag": f"veadk-v{next_version}"' in workflow
    assert (
        parsed_workflow["concurrency"]["group"] == "agentkit-runtime-rt-support-agent"
    )
    assert (
        parsed_workflow["jobs"]["publish"]["defaults"]["run"]["working-directory"]
        == "examples/support_agent"
    )
    assert "github-secret-token" not in workflow
    assert all(
        "github-secret-token" not in str(call[2].get("json")) for call in session.calls
    )
    assert all(
        call[2]["headers"]["Authorization"] == "Bearer github-secret-token"
        for call in session.calls
    )


def test_imports_studio_compatible_basic_template_with_delivery_workflow() -> None:
    session = _FakeSession()
    response = _app(session).post(
        "/web/integrations/github/template-pull-requests",
        json={
            "repository": "acme/agent",
            "baseBranch": "main",
            "projectPath": "examples/basic-agent",
            "runtimeName": "basic-agent",
            "runtimeId": "rt-basic-agent",
            "region": "cn-beijing",
            "token": "github-secret-token",
        },
    )

    assert response.status_code == 200
    contents = {
        call[1].split("/contents/", 1)[1]: base64.b64decode(
            call[2]["json"]["content"]
        ).decode()
        for call in session.calls
        if call[0] == "PUT" and "/contents/" in call[1]
    }
    assert {
        "examples/basic-agent/.dockerignore",
        "examples/basic-agent/.env.example",
        "examples/basic-agent/.gitignore",
        "examples/basic-agent/Dockerfile",
        "examples/basic-agent/README.md",
        "examples/basic-agent/assistant/__init__.py",
        "examples/basic-agent/assistant/agent.py",
        "examples/basic-agent/app.py",
        "examples/basic-agent/requirements.txt",
        ".github/workflows/publish-agentkit-examples-basic-agent.yml",
    } == set(contents)
    app_source = contents["examples/basic-agent/app.py"]
    compile(app_source, "app.py", "exec")
    compile(contents["examples/basic-agent/assistant/agent.py"], "agent.py", "exec")
    assert "create_agentkit_app(" in app_source
    assert "enable_feishu=True" in app_source
    assert "run_agentkit_app(app)" in app_source
    assert "AgentkitAgentServerApp" not in app_source
    assert "root_agent = Agent(" in contents["examples/basic-agent/assistant/agent.py"]
    assert "python app.py" in contents["examples/basic-agent/README.md"]
    assert "lark-channel-sdk" in contents["examples/basic-agent/requirements.txt"]
    workflow = contents[".github/workflows/publish-agentkit-examples-basic-agent.yml"]
    assert '"entry_point": "app.py"' in workflow
    assert "examples/basic-agent" in workflow
    assert "github-secret-token" not in "".join(contents.values())


def test_creates_isolated_codex_sandbox_review_workflow() -> None:
    session = _FakeSession()
    response = _app(session).post(
        "/web/integrations/github/review-pull-requests",
        json={
            "repository": "acme/agent",
            "baseBranch": "main",
            "sandboxToolId": "tool-code-review",
            "modelName": "doubao-seed-code-preview",
            "modelBaseUrl": "https://ark.cn-beijing.volces.com/api/coding/v3",
            "region": "cn-beijing",
            "token": "github-secret-token",
        },
    )

    assert response.status_code == 200
    put_call = next(
        call
        for call in session.calls
        if call[0] == "PUT" and "codex-pr-review.yml" in call[1]
    )
    workflow = base64.b64decode(put_call[2]["json"]["content"]).decode()
    parsed_workflow = yaml.safe_load(workflow)
    assert "pull_request_target" not in workflow
    assert (
        "github.event.pull_request.head.repo.full_name == github.repository" in workflow
    )
    assert "agentkit sandbox exec" in workflow
    assert "--copy . /workspace" in workflow
    assert "codex review --base" in workflow
    assert "agentkit sandbox delete" in workflow
    assert "secrets.CODEX_MODEL_API_KEY" in workflow
    assert parsed_workflow["permissions"]["pull-requests"] == "write"
    assert "github-secret-token" not in workflow


def test_rejects_insecure_review_model_url_before_github_request() -> None:
    session = _FakeSession()
    response = _app(session).post(
        "/web/integrations/github/review-pull-requests",
        json={
            "repository": "acme/agent",
            "sandboxToolId": "tool-code-review",
            "modelName": "review-model",
            "modelBaseUrl": "http://model.example.com/v1",
            "region": "cn-beijing",
            "token": "token",
        },
    )

    assert response.status_code == 400
    assert session.calls == []


def test_rejects_unsafe_repository_and_project_path_before_github_request() -> None:
    session = _FakeSession()
    client = _app(session)

    response = client.post(
        "/web/integrations/github/pull-requests",
        json={
            "repository": "not a repository",
            "projectPath": "../escape",
            "runtimeName": "agent",
            "runtimeId": "rt-agent",
            "region": "cn-beijing",
            "token": "token",
        },
    )

    assert response.status_code == 400
    assert session.calls == []


def test_route_requires_agent_management_permission() -> None:
    app = FastAPI()

    def deny(_request: object) -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Agent management is not allowed")

    mount_github_integration_routes(
        app, deny, service=GitHubIntegrationService(session=_FakeSession())
    )
    response = TestClient(app).post(
        "/web/integrations/github/pull-requests",
        json={
            "repository": "acme/agent",
            "projectPath": ".",
            "runtimeName": "agent",
            "runtimeId": "rt-agent",
            "region": "cn-beijing",
            "token": "token",
        },
    )

    assert response.status_code == 403
