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

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veadk.cli.cli import veadk
from veadk.cli.cli_frontend import _run_frontend_server


PROJECT = {
    "name": "demo_agent",
    "files": [
        {"path": "app.py", "content": "app = object()\n"},
        {"path": "requirements.txt", "content": "veadk-python\n"},
    ],
}


def test_parse_github_repo_url_accepts_common_forms() -> None:
    from veadk.cli.github_cicd import parse_github_repo_url

    assert parse_github_repo_url("https://github.com/acme/demo") == ("acme", "demo")
    assert parse_github_repo_url("https://github.com/acme/demo.git") == (
        "acme",
        "demo",
    )
    assert parse_github_repo_url("git@github.com:acme/demo.git") == (
        "acme",
        "demo",
    )


def test_create_github_cicd_pipeline_commits_pr_and_creates_runtime(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import create_github_cicd_pipeline

    github = FakeGitHubClient()
    deploy_calls: list[dict[str, Any]] = []

    def deployer(**kwargs: Any) -> dict[str, Any]:
        deploy_calls.append(kwargs)
        return {
            "runtimeId": "rt-first",
            "agentName": kwargs["project"]["name"],
            "region": kwargs["region"],
            "version": 1,
        }

    result = create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=github,
        deployer=deployer,
        state_path=tmp_path / "state.json",
    )

    assert result["pipelineId"] == "github-acme-demo-studio-demo-agent"
    assert result["github"]["branch"] == "studio/demo-agent"
    assert result["github"]["commitSha"] == "commit-1"
    assert result["github"]["pullRequestUrl"] == "https://github.com/acme/demo/pull/1"
    assert result["deployment"]["runtimeId"] == "rt-first"
    assert result["status"] == "succeeded"
    assert result["phase"] == "ready"
    assert isinstance(result["updatedAt"], str)
    assert deploy_calls == [
        {
            "project": PROJECT,
            "region": "cn-beijing",
            "runtime_id": "",
            "description": "GitHub CI/CD deployment from acme/demo@studio/demo-agent",
        }
    ]
    assert github.created_branch == ("main-sha", "studio/demo-agent")
    assert github.committed_files == PROJECT["files"]
    assert github.pull_request == ("studio/demo-agent", "main")

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["github-acme-demo-studio-demo-agent"]["status"] == "succeeded"
    assert state["github-acme-demo-studio-demo-agent"]["phase"] == "ready"
    assert state["github-acme-demo-studio-demo-agent"]["runtimeId"] == "rt-first"


def test_create_github_cicd_pipeline_reports_progress(tmp_path: Path) -> None:
    from veadk.cli.github_cicd import create_github_cicd_pipeline

    events: list[str] = []

    def deployer(**kwargs: Any) -> dict[str, Any]:
        return {
            "runtimeId": kwargs["runtime_id"] or "rt-created",
            "agentName": kwargs["project"]["name"],
            "region": kwargs["region"],
            "version": 1,
        }

    create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=FakeGitHubClient(),
        deployer=deployer,
        state_path=tmp_path / "state.json",
        progress=events.append,
    )

    assert events == [
        "Validating AgentProject...",
        "Connecting GitHub repo acme/demo...",
        "Reading base branch main...",
        "Ensuring Studio branch studio/demo-agent...",
        "Committing 2 file(s) to studio/demo-agent...",
        "Ensuring pull request studio/demo-agent -> main...",
        "Deploying AgentKit Runtime...",
        "Saving GitHub CI/CD pipeline state...",
        "GitHub CI/CD pipeline ready.",
    ]


def test_default_deployer_uses_shared_studio_agentkit_deploy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.cli import github_cicd

    captured: dict[str, Any] = {}

    def deploy_agentkit_project(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"runtimeId": "rt-shared"}

    monkeypatch.setattr(
        "veadk.cli.studio_agentkit_deploy.deploy_agentkit_project",
        deploy_agentkit_project,
    )

    result = github_cicd._default_deployer(
        project=PROJECT,
        region="cn-beijing",
        runtime_id="",
        description="demo",
    )

    assert result == {"runtimeId": "rt-shared"}
    assert captured["project"] == PROJECT


def test_create_github_cicd_pipeline_reuses_runtime_on_next_run(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import create_github_cicd_pipeline

    state_path = tmp_path / "state.json"
    first_github = FakeGitHubClient(commit_sha="commit-1")
    second_github = FakeGitHubClient(commit_sha="commit-2")
    runtime_ids: list[str] = []

    def deployer(**kwargs: Any) -> dict[str, Any]:
        runtime_ids.append(kwargs["runtime_id"])
        return {
            "runtimeId": kwargs["runtime_id"] or "rt-created",
            "agentName": kwargs["project"]["name"],
            "region": kwargs["region"],
            "version": 1 if not kwargs["runtime_id"] else 2,
        }

    create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=first_github,
        deployer=deployer,
        state_path=state_path,
    )
    result = create_github_cicd_pipeline(
        project=PROJECT,
        github_url="https://github.com/acme/demo",
        github_token="ghp_secret",
        base_branch="main",
        region="cn-beijing",
        github_client=second_github,
        deployer=deployer,
        state_path=state_path,
    )

    assert runtime_ids == ["", "rt-created"]
    assert result["github"]["commitSha"] == "commit-2"
    assert result["deployment"]["runtimeId"] == "rt-created"
    assert result["deployment"]["version"] == 2


def test_create_github_cicd_pipeline_persists_failed_deploy_state(
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import GitHubCicdError, create_github_cicd_pipeline

    def deployer(**_kwargs: Any) -> dict[str, Any]:
        raise GitHubCicdError(
            "Runtime status is Error. Initialization failed",
            phase="deploy",
            runtime_id="rt-failed",
            log_path="/tmp/runtime.log",
        )

    with pytest.raises(GitHubCicdError) as exc:
        create_github_cicd_pipeline(
            project=PROJECT,
            github_url="https://github.com/acme/demo",
            github_token="ghp_secret",
            base_branch="main",
            region="cn-beijing",
            github_client=FakeGitHubClient(),
            deployer=deployer,
            state_path=tmp_path / "state.json",
        )

    assert exc.value.phase == "deploy"
    assert exc.value.runtime_id == "rt-failed"
    assert exc.value.to_response() == {
        "status": "failed",
        "phase": "deploy",
        "message": "Runtime status is Error. Initialization failed",
        "runtimeId": "rt-failed",
        "logPath": "/tmp/runtime.log",
    }
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    failed = state["github-acme-demo-studio-demo-agent"]
    assert failed["status"] == "failed"
    assert failed["phase"] == "deploy"
    assert failed["runtimeId"] == "rt-failed"
    assert failed["latestCommitSha"] == "commit-1"
    assert failed["pullRequestUrl"] == "https://github.com/acme/demo/pull/1"
    assert failed["lastError"]["message"] == (
        "Runtime status is Error. Initialization failed"
    )


def test_github_cicd_pipeline_cli_reads_project_json_and_runs_github_cicd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_create_github_cicd_pipeline(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        kwargs["progress"]("Testing progress output...")
        return {
            "pipelineId": "github-acme-demo-studio-demo-agent",
            "status": "succeeded",
            "phase": "ready",
            "github": {"pullRequestUrl": "https://github.com/acme/demo/pull/1"},
            "deployment": {"runtimeId": "rt-1"},
        }

    monkeypatch.setattr(
        "veadk.cli.cli_github_cicd_pipeline.create_github_cicd_pipeline",
        fake_create_github_cicd_pipeline,
    )
    project_json = tmp_path / "agent-project.json"
    project_json.write_text(json.dumps(PROJECT), encoding="utf-8")

    result = CliRunner().invoke(
        veadk,
        [
            "github-cicd-pipeline",
            "--github-url",
            "https://github.com/acme/demo",
            "--github-token",
            "ghp_secret",
            "--github-branch",
            "main",
            "--project-json",
            str(project_json),
            "--region",
            "cn-beijing",
        ],
    )

    assert result.exit_code == 0
    assert captured["project"] == PROJECT
    assert captured["github_url"] == "https://github.com/acme/demo"
    assert captured["github_token"] == "ghp_secret"
    assert captured["base_branch"] == "main"
    assert captured["region"] == "cn-beijing"
    assert callable(captured["progress"])
    assert "[github-cicd] Testing progress output..." in result.output
    assert "ghp_secret" not in result.output
    assert "github-acme-demo-studio-demo-agent" in result.output
    assert '"status": "succeeded"' in result.output


def test_studio_endpoint_creates_github_cicd_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")
    captured: dict[str, Any] = {}

    def fake_create_github_cicd_pipeline(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "pipelineId": "github-acme-demo-studio-demo-agent",
            "status": "succeeded",
            "phase": "ready",
            "github": {"branch": "studio/demo-agent"},
            "deployment": {"runtimeId": "rt-1"},
        }

    monkeypatch.setattr(
        "veadk.cli.github_cicd.create_github_cicd_pipeline",
        fake_create_github_cicd_pipeline,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/github-cicd/pipelines",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "project": PROJECT,
                "githubUrl": "https://github.com/acme/demo",
                "githubToken": "ghp_secret",
                "baseBranch": "main",
                "region": "cn-beijing",
            },
        )

    assert response.status_code == 200
    assert response.json()["pipelineId"] == "github-acme-demo-studio-demo-agent"
    assert response.json()["status"] == "succeeded"
    assert captured["project"] == PROJECT
    assert captured["github_url"] == "https://github.com/acme/demo"
    assert captured["github_token"] == "ghp_secret"
    assert captured["base_branch"] == "main"
    assert captured["region"] == "cn-beijing"


def test_studio_endpoint_returns_structured_github_cicd_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from veadk.cli.github_cicd import GitHubCicdError

    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    def fake_create_github_cicd_pipeline(**_kwargs: Any) -> dict[str, Any]:
        raise GitHubCicdError(
            "GitHub token cannot create branches",
            phase="github",
        )

    monkeypatch.setattr(
        "veadk.cli.github_cicd.create_github_cicd_pipeline",
        fake_create_github_cicd_pipeline,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/github-cicd/pipelines",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "project": PROJECT,
                "githubUrl": "https://github.com/acme/demo",
                "githubToken": "ghp_secret",
                "baseBranch": "main",
                "region": "cn-beijing",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "status": "failed",
        "phase": "github",
        "message": "GitHub token cannot create branches",
    }


class FakeGitHubClient:
    def __init__(self, commit_sha: str = "commit-1") -> None:
        self.commit_sha = commit_sha
        self.created_branch: tuple[str, str] | None = None
        self.committed_files: list[dict[str, str]] = []
        self.pull_request: tuple[str, str] | None = None

    def ensure_repository_access(self, owner: str, repo: str) -> None:
        assert (owner, repo) == ("acme", "demo")

    def get_branch_head(self, owner: str, repo: str, branch: str) -> str:
        assert (owner, repo, branch) == ("acme", "demo", "main")
        return "main-sha"

    def ensure_branch(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        source_sha: str,
    ) -> None:
        assert (owner, repo) == ("acme", "demo")
        self.created_branch = (source_sha, branch)

    def commit_files(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        files: list[dict[str, str]],
        message: str,
    ) -> str:
        assert (owner, repo, branch) == ("acme", "demo", "studio/demo-agent")
        assert "Studio" in message
        self.committed_files = files
        return self.commit_sha

    def ensure_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> SimpleNamespace:
        assert (owner, repo) == ("acme", "demo")
        assert title
        assert body
        self.pull_request = (head_branch, base_branch)
        return SimpleNamespace(number=1, url="https://github.com/acme/demo/pull/1")


def _create_studio_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    developers: str,
) -> FastAPI:
    captured: dict[str, Any] = {}
    monkeypatch.setattr("dotenv.find_dotenv", lambda *args, **kwargs: "")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test-sk")
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: captured.setdefault("app", app),
    )
    _run_frontend_server(
        agents_dir=str(tmp_path),
        frontend_dir=None,
        site_logo=None,
        site_title=None,
        host="127.0.0.1",
        port=8765,
        dev=True,
        vite=True,
        oauth2_user_pool=None,
        oauth2_user_pool_client=None,
        oauth2_user_pool_uid=None,
        oauth2_user_pool_client_uid=None,
        oauth2_redirect_uri=None,
        oauth2_provider=None,
        oauth2_provider_label=None,
        auth_mode="frontend",
        generated_agent_test_run_ttl=60,
        studio_admins=None,
        studio_developers=developers,
        open_browser=False,
        studio=True,
    )
    return captured["app"]
