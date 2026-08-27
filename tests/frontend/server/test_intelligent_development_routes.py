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

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from datetime import datetime, timezone
from dataclasses import dataclass
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from httpx import Response

from frontend.server import intelligent_development_routes as routes
from frontend.server import intelligent_development_source as source_module
from frontend.server.intelligent_development_projects import routes as project_routes
from frontend.server.deployment_source import DeploymentSourceError
from frontend.server.intelligent_development import StudioCredentials
from frontend.server.intelligent_development_projects import (
    IntelligentDevelopmentProject,
    IntelligentDevelopmentProjectStorageUnavailable,
    IntelligentDevelopmentSessionBinding,
    IntelligentDevelopmentVersion,
    IntelligentDevelopmentVersionIntegrityError,
)
from frontend.server.intelligent_development_source import (
    TrustedDevelopmentArtifact,
    TrustedDeploymentSource,
    TrustedSourceFile,
)
from frontend.server.intelligent_development_task import (
    CompletionContract,
    IntentDecision,
    builder_prompt,
    intent_gate_prompt,
    read_only_prompt,
)
from veadk.cli.codex_app_server import (
    CodexAppServerError,
    CodexAppServerEvent,
    CodexPermissionSettings,
    CodexSkill,
    CodexThreadMessage,
    CodexThreadSnapshot,
    CodexThreadSummary,
    CodexTokenUsage,
)
from veadk.cli.frontend_sandbox import (
    SandboxCloudSession,
    SandboxConversationService,
    SandboxSessionNotFoundError,
)


def _gate(
    decision: str = "accept",
    *,
    message: str = "",
    changes: bool = True,
) -> CodexAppServerEvent:
    return CodexAppServerEvent(
        kind="text",
        text=json.dumps(
            {
                "decision": decision,
                "message": message,
                "intentSummary": "构建天气 Agent" if decision == "accept" else "",
                "acceptanceCriteria": ["返回天气和数据时间"]
                if decision == "accept"
                else [],
                "changesDelivery": changes,
            },
            ensure_ascii=False,
        ),
    )


class _FakeCodex:
    def __init__(self, *, cwd: str = "/workspace", locked: bool = False) -> None:
        self.thread_id = "thread-1"
        self.cwd = cwd
        self.model = "gpt-test"
        self.permissions = CodexPermissionSettings()
        self.workspace_locked = locked
        self.active = False
        self.closed = False
        self.skills: tuple[CodexSkill, ...] = (
            CodexSkill(
                id="skill-veadk",
                name="veadk-agent-development",
                description="Build VeADK Agents",
            ),
        )
        self.turns: list[list[CodexAppServerEvent] | BaseException] = []
        self.calls: list[dict[str, object]] = []
        self.threads: list[CodexThreadSummary] = []
        self.thread_messages: tuple[CodexThreadMessage, ...] | None = None

    async def stream_turn(
        self,
        prompt: str,
        skill_ids: tuple[str, ...] = (),
        **options: object,
    ) -> AsyncIterator[CodexAppServerEvent]:
        self.calls.append({"prompt": prompt, "skillIds": skill_ids, **options})
        turn = (
            self.turns.pop(0)
            if self.turns
            else [_gate("reject", message="仅支持 VeADK Agent 开发。")]
        )
        if isinstance(turn, BaseException):
            raise turn
        for event in turn:
            yield event

    async def update_workspace(self, cwd: str) -> str:
        self.cwd = cwd
        return cwd

    async def update_permissions(
        self, settings: CodexPermissionSettings
    ) -> CodexPermissionSettings:
        self.permissions = settings
        return settings

    async def apply_session_permissions(
        self, settings: CodexPermissionSettings
    ) -> None:
        self.permissions = settings

    async def list_models(self) -> tuple[object, ...]:
        return (SimpleNamespace(public_dict=lambda: {"id": "model-1"}),)

    async def list_skills(self, force_reload: bool = False) -> tuple[CodexSkill, ...]:
        del force_reload
        return self.skills

    async def set_model(self, model: str) -> str:
        self.model = model
        return model

    async def interrupt(self) -> None:
        self.active = False

    async def list_threads(
        self,
        *,
        cursor: str = "",
        search_term: str = "",
        archived: bool = False,
    ) -> tuple[tuple[CodexThreadSummary, ...], str]:
        del cursor, search_term, archived
        return tuple(self.threads), ""

    def _snapshot(self, thread_id: str) -> CodexThreadSnapshot:
        return CodexThreadSnapshot(
            thread=next(thread for thread in self.threads if thread.id == thread_id),
            messages=self.thread_messages
            if self.thread_messages is not None
            else (
                CodexThreadMessage(
                    id="message-user",
                    role="user",
                    content="创建销售 Agent",
                    timestamp=1_000,
                ),
                CodexThreadMessage(
                    id="message-assistant",
                    role="assistant",
                    content="已完成",
                    timestamp=2_000,
                ),
            ),
            model=self.model,
            cwd=self.cwd,
            workspace_locked=True,
        )

    async def read_thread(self, thread_id: str) -> CodexThreadSnapshot:
        return self._snapshot(thread_id)

    async def resume_thread(self, thread_id: str) -> CodexThreadSnapshot:
        self.thread_id = thread_id
        return self._snapshot(thread_id)

    async def close(self) -> None:
        self.closed = True


class _FakeGateway:
    def __init__(self, tool_envs: Mapping[str, str] | None = None) -> None:
        self.sessions: dict[str, SandboxCloudSession] = {}
        self.codex = _FakeCodex()
        self.created = 0
        self.envs: list[dict[str, str] | None] = []
        self.tool_envs = (
            dict(tool_envs)
            if tool_envs is not None
            else {
                "CODEX_MODEL": "doubao-seed-1-8-251228",
                "CODEX_API_KEY": "codex-api-key",
                "CODEX_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
            }
        )

    async def get_tool(self, tool_id: str) -> SimpleNamespace:
        del tool_id
        return SimpleNamespace(
            envs=[
                SimpleNamespace(key=key, value=value)
                for key, value in self.tool_envs.items()
            ]
        )

    async def create_session(
        self,
        tool_id: str,
        display_name: str = "",
        username: str = "",
        creator_name: str = "",
        agent_kind: str = "",
        envs: Mapping[str, str] | None = None,
    ) -> SandboxCloudSession:
        self.created += 1
        self.envs.append(dict(envs) if envs is not None else None)
        session = _cloud(
            session_id=f"session-{self.created}",
            owner=username,
            user_session_id=f"workspace-{self.created}",
        )
        session = SandboxCloudSession(
            **{
                **session.__dict__,
                "tool_id": tool_id,
                "display_name": display_name,
                "creator_name": creator_name,
                "agent_kind": agent_kind,
            }
        )
        self.sessions[session.instance_id] = session
        return session

    async def get_session(self, tool_id: str, session_id: str) -> SandboxCloudSession:
        session = self.sessions.get(session_id)
        if session is None or session.tool_id != tool_id:
            raise SandboxSessionNotFoundError("not found")
        return session

    async def list_sessions(
        self, tool_id: str, username: str | None = None
    ) -> list[SandboxCloudSession]:
        return [
            session
            for session in self.sessions.values()
            if session.tool_id == tool_id
            and (username is None or session.created_by == username)
        ]

    async def open_codex(self, session: SandboxCloudSession) -> _FakeCodex:
        del session
        return self.codex

    async def delete_session(self, session: SandboxCloudSession) -> None:
        self.sessions.pop(session.instance_id, None)


def _cloud(
    *,
    session_id: str = "dev-session",
    owner: str = "alice",
    user_session_id: str = "safe-workspace",
    expire_at: str = "2027-08-14T16:00:00Z",
) -> SandboxCloudSession:
    return SandboxCloudSession(
        tool_id="tool-dev",
        instance_id=session_id,
        user_session_id=user_session_id,
        endpoint="https://sandbox.example/dev?Authorization=secret",
        status="Ready",
        expire_at=expire_at,
        created_by=owner,
        agent_kind=routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    )


class _Remote:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    async def exec_text(self, command: str, *, timeout: int = 12) -> str:
        del command, timeout
        return ""


def _app(
    gateway: _FakeGateway,
    *,
    configured: bool = True,
    project_service=None,
) -> FastAPI:
    app = FastAPI()
    service = SandboxConversationService(
        routes.IntelligentDevelopmentGateway(gateway),
        tool_id="tool-dev",
        agent_kind=routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    )

    def owner(request: Request) -> str:
        value = request.headers.get("X-Test-User", "")
        if not value:
            raise HTTPException(status_code=401, detail="identity required")
        return value

    routes.mount_intelligent_development_routes(
        app,
        service,
        owner,
        owner,
        lambda: StudioCredentials("access", "secret", "token"),
        project_service=project_service,
        configured=configured,
    )
    return app


@pytest.fixture(autouse=True)
def _remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.setattr(routes, "SandboxRemoteTransport", _Remote)


def _connect(client: TestClient) -> None:
    response = client.post(
        "/web/intelligent-development/sessions/dev-session/connect",
        headers={"X-Test-User": "alice"},
    )
    assert response.status_code == 200


def test_list_is_empty_when_intelligent_development_is_not_configured() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway, configured=False)) as client:
        response = client.get(
            "/web/intelligent-development/sessions",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.json() == {"sessions": []}


def test_capabilities_requires_sandbox_dev_model_credentials() -> None:
    gateway = _FakeGateway(
        tool_envs={
            "CODEX_MODEL": "doubao-seed-1-8-251228",
            "CODEX_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
        }
    )
    with TestClient(_app(gateway)) as client:
        response = client.get(
            "/web/intelligent-development/capabilities",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "reason": "SANDBOX_DEV 模型配置不可用，请重新部署 Studio。",
        "model": {"configured": False, "id": "doubao-seed-1-8-251228"},
        "projectStorageEnabled": False,
        "projectStorageReason": "管理员未配置项目存储",
    }


def test_create_requires_sandbox_dev_model_credentials() -> None:
    gateway = _FakeGateway(
        tool_envs={
            "CODEX_MODEL": "doubao-seed-1-8-251228",
            "CODEX_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
        }
    )
    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "天气 Agent"},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SANDBOX_NOT_CONFIGURED"
    assert gateway.created == 0


def test_create_is_transient_and_public_contract_includes_expiry() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "天气 Agent"},
        )
    assert response.status_code == 200
    assert response.json()["persistent"] is False
    assert response.json()["toolName"] == "intelligent-development"
    assert response.json()["expireAt"]
    assert gateway.envs == [None]


def test_create_accepts_selected_model_as_session_env() -> None:
    gateway = _FakeGateway()
    model_id = "doubao-seed-2-1-pro-260628"
    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions",
            headers={"X-Test-User": "alice"},
            json={
                "displayName": "天气 Agent",
                "modelId": model_id,
            },
        )

    assert response.status_code == 200
    assert len(gateway.envs) == 1
    envs = gateway.envs[0] or {}
    assert envs["CODEX_MODEL"] == model_id
    assert envs["OPENCODE_MODEL"] == model_id
    assert envs["ANTHROPIC_MODEL"] == model_id
    assert envs["CODEX_BASE_URL"] == "https://ark.cn-beijing.volces.com/api/v3"
    assert model_id in envs["CODEX_CONFIG_TOML"]
    assert f'model = "{model_id}"' in envs["CODEX_CONFIG_TOML"]
    assert f'review_model = "{model_id}"' in envs["CODEX_CONFIG_TOML"]
    assert {
        "ANTHROPIC_AUTH_TOKEN",
        "CODEX_API_KEY",
        "OPENCODE_API_KEY",
    }.isdisjoint(envs)


def test_create_treats_blank_selected_model_as_default() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "天气 Agent", "modelId": "   "},
        )

    assert response.status_code == 200
    assert gateway.envs == [None]


def test_create_rejects_non_text_selected_model() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "天气 Agent", "modelId": 42},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "SANDBOX_INVALID_REQUEST"
    assert gateway.created == 0


def test_create_rejects_invalid_selected_model() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "天气 Agent", "modelId": "bad; export SECRET=value"},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "SANDBOX_INVALID_REQUEST"
    assert gateway.created == 0


def test_create_rejects_unknown_fields() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "天气 Agent", "modelId": "doubao-test", "extra": True},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "SANDBOX_INVALID_REQUEST"
    assert gateway.created == 0


def test_create_binds_selected_project_version() -> None:
    gateway = _FakeGateway()
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    binding = IntelligentDevelopmentSessionBinding(
        ownerId="alice",
        sessionId="session-1",
        projectId="a" * 32,
        projectName="天气 Agent",
        baseVersionId="b" * 32,
        createdAt=now,
        updatedAt=now,
    )
    project_service = SimpleNamespace(create_binding=AsyncMock(return_value=binding))
    with TestClient(_app(gateway, project_service=project_service)) as client:
        response = client.post(
            "/web/intelligent-development/sessions",
            headers={"X-Test-User": "alice"},
            json={
                "displayName": "继续优化天气 Agent",
                "projectId": "a" * 32,
                "baseVersionId": "b" * 32,
            },
        )

    assert response.status_code == 200
    assert response.json()["projectId"] == "a" * 32
    assert response.json()["baseVersionId"] == "b" * 32
    project_service.create_binding.assert_awaited_once_with(
        owner_id="alice",
        session_id="session-1",
        display_name="继续优化天气 Agent",
        project_id="a" * 32,
        base_version_id="b" * 32,
    )


def test_project_list_exposes_storage_failure_as_retryable() -> None:
    gateway = _FakeGateway()
    project_service = SimpleNamespace(
        list_projects=AsyncMock(
            side_effect=IntelligentDevelopmentProjectStorageUnavailable(
                "项目存储暂时不可用，请稍后重试。"
            )
        )
    )
    with TestClient(_app(gateway, project_service=project_service)) as client:
        response = client.get(
            "/web/intelligent-development/projects",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "INTELLIGENT_DEVELOPMENT_STORAGE_UNAVAILABLE",
        "message": "项目存储暂时不可用，请稍后重试。",
        "retryable": True,
    }


def test_project_list_returns_owner_scoped_summaries() -> None:
    gateway = _FakeGateway()
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    project = IntelligentDevelopmentProject(
        projectId="a" * 32,
        ownerId="alice",
        origin="migration",
        name="天气 Agent",
        createdAt=now,
        updatedAt=now,
        latestVersionId="b" * 32,
        latestVersionCreatedAt=now,
        latestVersionVerified=True,
        latestAgentName="weather_agent",
        versionCount=1,
    )
    project_service = SimpleNamespace(list_projects=AsyncMock(return_value=[project]))
    with TestClient(_app(gateway, project_service=project_service)) as client:
        response = client.get(
            "/web/intelligent-development/projects?origin=migration",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.json()["projects"][0]["projectId"] == "a" * 32
    assert response.json()["projects"][0]["versionCount"] == 1
    assert response.json()["projects"][0]["origin"] == "migration"
    assert "ownerId" not in response.json()["projects"][0]
    project_service.list_projects.assert_awaited_once_with(
        "alice",
        origin="migration",
    )


def test_project_list_defaults_to_intelligent_development_origin() -> None:
    gateway = _FakeGateway()
    project_service = SimpleNamespace(list_projects=AsyncMock(return_value=[]))
    with TestClient(_app(gateway, project_service=project_service)) as client:
        response = client.get(
            "/web/intelligent-development/projects",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.json() == {"projects": []}
    project_service.list_projects.assert_awaited_once_with(
        "alice",
        origin="intelligent-development",
    )


def test_project_versions_keep_integrity_failures_distinct_from_empty_data() -> None:
    gateway = _FakeGateway()
    project_service = SimpleNamespace(
        list_versions=AsyncMock(
            side_effect=IntelligentDevelopmentVersionIntegrityError(
                "项目版本记录格式无效。"
            )
        )
    )
    with TestClient(_app(gateway, project_service=project_service)) as client:
        response = client.get(
            f"/web/intelligent-development/projects/{'a' * 32}/versions",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "INTELLIGENT_DEVELOPMENT_VERSION_INVALID",
        "message": "项目版本记录格式无效。",
        "retryable": False,
    }


def test_project_source_reads_tos_without_resolving_a_live_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    version = IntelligentDevelopmentVersion(
        projectId="a" * 32,
        versionId="b" * 32,
        parentVersionId="e" * 32,
        sourceSessionId="expired-session",
        createdAt=now,
        intentSummary="构建天气 Agent",
        acceptanceCriteria=["返回天气"],
        artifactSha256="c" * 64,
        validationReportSha256="d" * 64,
        artifactSize=4,
        fileCount=1,
        agentName="weather_agent",
        entryPoint="app.py",
        verified=True,
        validationSummary="验证通过",
        gateSummary=["local-checks"],
        validatedAt=now.isoformat(),
    )
    trusted = TrustedDeploymentSource(
        entry_point="app.py",
        agent_name="weather_agent",
        artifact_sha256="c" * 64,
        validation_report_sha256="d" * 64,
        file_count=1,
        artifact_size=4,
        validated_at=now.isoformat(),
        gate_summary=("local-checks",),
        verified=True,
        validation_summary="验证通过",
        files=(TrustedSourceFile("app.py", "root_agent = object()\n"),),
        project_id="a" * 32,
        version_id="b" * 32,
    )
    materialize = AsyncMock(return_value=trusted)
    monkeypatch.setattr(
        project_routes,
        "materialize_intelligent_development_preview",
        materialize,
    )
    project_service = SimpleNamespace(get_version=AsyncMock(return_value=version))

    with TestClient(_app(gateway, project_service=project_service)) as client:
        response = client.get(
            f"/web/intelligent-development/projects/{'a' * 32}/versions/{'b' * 32}/source",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.json()["sessionId"] == "expired-session"
    assert response.json()["projectId"] == "a" * 32
    assert response.json()["versionId"] == "b" * 32
    assert response.json()["parentVersionId"] == "e" * 32
    assert response.json()["files"] == [
        {"path": "app.py", "content": "root_agent = object()\n"}
    ]
    materialize_call = materialize.await_args
    assert materialize_call is not None
    assert materialize_call.kwargs["service"] is None
    assert materialize_call.kwargs["project_service"] is project_service


def test_project_download_reads_the_exact_tos_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    version = IntelligentDevelopmentVersion(
        projectId="a" * 32,
        versionId="b" * 32,
        sourceSessionId="expired-session",
        createdAt=now,
        intentSummary="构建天气 Agent",
        acceptanceCriteria=["返回天气"],
        artifactSha256="c" * 64,
        validationReportSha256="d" * 64,
        artifactSize=4,
        fileCount=1,
        agentName="weather_agent",
        entryPoint="app.py",
        verified=True,
        validationSummary="验证通过",
        gateSummary=["local-checks"],
        validatedAt=now.isoformat(),
    )
    load = AsyncMock(
        return_value=TrustedDevelopmentArtifact(
            content=b"PK\x03\x04",
            artifact_sha256="c" * 64,
            agent_name="weather_agent",
            file_count=1,
            artifact_size=4,
        )
    )
    monkeypatch.setattr(
        project_routes,
        "load_intelligent_development_artifact",
        load,
    )
    project_service = SimpleNamespace(get_version=AsyncMock(return_value=version))

    with TestClient(_app(gateway, project_service=project_service)) as client:
        response = client.get(
            f"/web/intelligent-development/projects/{'a' * 32}/versions/{'b' * 32}/download",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.content == b"PK\x03\x04"
    assert response.headers["content-type"] == "application/zip"
    assert "weather_agent-source-" in response.headers["content-disposition"]
    load_call = load.await_args
    assert load_call is not None
    assert load_call.kwargs["service"] is None
    assert load_call.kwargs["project_service"] is project_service


def test_connect_locks_fixed_workspace_and_enables_autonomous_builder() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    with TestClient(_app(gateway)) as client:
        _connect(client)
    assert gateway.codex.cwd == "/home/gem/workspace/project-1"
    assert gateway.codex.permissions == routes._BUILDER_PERMISSIONS


def test_connect_restores_the_selected_project_version_before_locking_workspace() -> (
    None
):
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    project_service = SimpleNamespace(
        restore_base_version=AsyncMock(return_value=True),
    )

    with TestClient(_app(gateway, project_service=project_service)) as client:
        _connect(client)

    project_service.restore_base_version.assert_awaited_once_with(
        owner_id="alice",
        session_id="dev-session",
        endpoint="https://sandbox.example/dev?Authorization=secret",
        workspace="/home/gem/workspace/project-1",
    )
    assert gateway.codex.cwd == "/home/gem/workspace/project-1"


def test_connect_restores_the_latest_non_empty_conversation() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    gateway.codex.thread_id = "thread-new"
    gateway.codex.threads = [
        CodexThreadSummary(
            id="thread-new",
            preview="",
            cwd="/home/gem/workspace/project-1",
            updated_at=30,
        ),
        CodexThreadSummary(
            id="thread-restored",
            preview="创建销售 Agent",
            cwd="/home/gem/workspace/project-1",
            updated_at=20,
        ),
    ]
    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.json()["threadId"] == "thread-restored"
    assert response.json()["conversation"]["threadId"] == "thread-restored"
    assert [
        message["content"] for message in response.json()["conversation"]["messages"]
    ] == ["创建销售 Agent", "已完成"]


def test_connect_projects_internal_multi_turn_history_to_user_facing_conversation() -> (
    None
):
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    gateway.codex.threads = [
        CodexThreadSummary(
            id="thread-restored",
            preview="internal intent gate",
            cwd="/home/gem/workspace/project-1",
            updated_at=20,
        )
    ]
    first = IntentDecision(
        "accept",
        "",
        "创建销售 Agent",
        ("生成销售话术",),
        True,
    )
    second = IntentDecision(
        "accept",
        "",
        "为销售 Agent 增加英文输出",
        ("保留中文并支持英文",),
        True,
    )
    decisions = [first, second]
    requests = ["创建销售 Agent", "再支持英文输出"]
    answers = [
        "已创建销售 Agent。\n\n### 已完成\n- 生成销售话术",
        "已完成英文能力优化。\n\n### 已完成\n- 保留中文并支持英文",
    ]
    messages: list[CodexThreadMessage] = []
    timestamp = 1_000
    for index, (request, decision, answer) in enumerate(
        zip(requests, decisions, answers, strict=True),
        start=1,
    ):
        messages.extend(
            (
                CodexThreadMessage(
                    id=f"gate-user-{index}",
                    role="user",
                    content=intent_gate_prompt(request, expire_at="later"),
                    timestamp=timestamp,
                ),
                CodexThreadMessage(
                    id=f"gate-assistant-{index}",
                    role="assistant",
                    content=json.dumps(
                        {
                            "decision": "accept",
                            "message": "",
                            "intentSummary": decision.intent_summary,
                            "acceptanceCriteria": list(decision.acceptance_criteria),
                            "changesDelivery": True,
                        },
                        ensure_ascii=False,
                    ),
                    timestamp=timestamp + 1,
                ),
                CodexThreadMessage(
                    id=f"builder-user-{index}",
                    role="user",
                    content=builder_prompt(
                        request,
                        decision,
                        launcher_path="/secure/launcher",
                        completion_path="/workspace/result.json",
                        expire_at="later",
                        remaining_lifetime_minutes=60,
                        validation_region="cn-beijing",
                        validation_project="default",
                    ),
                    timestamp=timestamp + 2,
                ),
                CodexThreadMessage(
                    id=f"builder-assistant-{index}",
                    role="assistant",
                    content=answer,
                    timestamp=timestamp + 3,
                ),
            )
        )
        timestamp += 10
    gateway.codex.thread_messages = tuple(messages)

    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    restored = response.json()["conversation"]["messages"]
    assert [(message["role"], message["content"]) for message in restored] == [
        ("user", requests[0]),
        ("assistant", answers[0]),
        ("user", requests[1]),
        ("assistant", answers[1]),
    ]
    assert "read-only intent gate" not in json.dumps(restored)
    assert "changesDelivery" not in json.dumps(restored)


def test_connect_projects_clarification_as_one_user_facing_exchange() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    gateway.codex.threads = [
        CodexThreadSummary(
            id="thread-restored",
            preview="internal intent gate",
            cwd="/home/gem/workspace/project-1",
            updated_at=20,
        )
    ]
    request = "帮我优化一下"
    clarification = "你希望优先优化响应速度还是回答准确性？"
    gateway.codex.thread_messages = (
        CodexThreadMessage(
            id="gate-user",
            role="user",
            content=intent_gate_prompt(request, expire_at="later"),
            timestamp=1_000,
        ),
        CodexThreadMessage(
            id="gate-assistant",
            role="assistant",
            content=json.dumps(
                {
                    "decision": "clarify",
                    "message": clarification,
                    "intentSummary": "",
                    "acceptanceCriteria": [],
                    "changesDelivery": False,
                },
                ensure_ascii=False,
            ),
            timestamp=2_000,
        ),
    )

    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    restored = response.json()["conversation"]["messages"]
    assert [(message["role"], message["content"]) for message in restored] == [
        ("user", request),
        ("assistant", clarification),
    ]


def test_connect_projects_read_only_history_to_user_facing_exchange() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    gateway.codex.threads = [
        CodexThreadSummary(
            id="thread-restored",
            preview="internal intent gate",
            cwd="/home/gem/workspace/project-1",
            updated_at=20,
        )
    ]
    request = "这个 Agent 目前支持哪些输入？"
    answer = "目前支持产品名称、目标人群和内容语气。"
    decision = IntentDecision(
        "accept",
        "",
        "说明当前 Agent 支持的输入",
        ("列出已实现的输入字段",),
        False,
    )
    gateway.codex.thread_messages = (
        CodexThreadMessage(
            id="gate-user",
            role="user",
            content=intent_gate_prompt(request, expire_at="later"),
            timestamp=1_000,
        ),
        CodexThreadMessage(
            id="gate-assistant",
            role="assistant",
            content=json.dumps(
                {
                    "decision": "accept",
                    "message": "",
                    "intentSummary": decision.intent_summary,
                    "acceptanceCriteria": list(decision.acceptance_criteria),
                    "changesDelivery": False,
                },
                ensure_ascii=False,
            ),
            timestamp=2_000,
        ),
        CodexThreadMessage(
            id="read-only-user",
            role="user",
            content=read_only_prompt(request, decision, expire_at="later"),
            timestamp=3_000,
        ),
        CodexThreadMessage(
            id="read-only-assistant",
            role="assistant",
            content=answer,
            timestamp=4_000,
        ),
    )

    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    restored = response.json()["conversation"]["messages"]
    assert [(message["role"], message["content"]) for message in restored] == [
        ("user", request),
        ("assistant", answer),
    ]


def test_connect_does_not_switch_threads_while_a_build_is_active() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    gateway.codex.active = True
    gateway.codex.thread_id = "thread-active"
    gateway.codex.cwd = "/home/gem/workspace/project-1"
    gateway.codex.workspace_locked = True
    gateway.codex.permissions = routes._BUILDER_PERMISSIONS
    gateway.codex.threads = [
        CodexThreadSummary(
            id="thread-active",
            preview="正在创建销售 Agent",
            cwd="/home/gem/workspace/project-1",
            updated_at=30,
        )
    ]
    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.json()["threadId"] == "thread-active"
    assert response.json()["busy"] is True
    assert "conversation" not in response.json()


def test_current_release_returns_no_content_or_the_materialized_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    trusted = SimpleNamespace(
        session_id="dev-session",
        artifact_sha256="a" * 64,
        validation_report_sha256="b" * 64,
        agent_name="sales-agent",
        entry_point="agent.py",
        file_count=4,
        artifact_size=2048,
        validated_at="2026-08-17T10:00:00Z",
        gate_summary=("local-checks",),
        deployable=True,
        verified=True,
        validation_summary="云端验证已通过",
        files=(),
    )
    current = AsyncMock(side_effect=[None, trusted])
    monkeypatch.setattr(
        source_module,
        "materialize_current_intelligent_development_preview",
        current,
        raising=False,
    )
    with TestClient(_app(gateway)) as client:
        missing = client.get(
            "/web/intelligent-development/releases/current",
            headers={"X-Test-User": "alice"},
            params={"sessionId": "dev-session"},
        )
        restored = client.get(
            "/web/intelligent-development/releases/current",
            headers={"X-Test-User": "alice"},
            params={"sessionId": "dev-session"},
        )

    assert missing.status_code == 204
    assert restored.status_code == 200
    assert restored.json()["artifactSha256"] == "a" * 64
    assert restored.json()["verified"] is True


def test_release_summary_returns_materialized_text_files_before_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    trusted = SimpleNamespace(
        artifact_sha256="a" * 64,
        validation_report_sha256="b" * 64,
        agent_name="weather",
        entry_point="app.py",
        file_count=3,
        artifact_size=2048,
        validated_at="2026-08-15T00:00:00Z",
        gate_summary=("ak-build", "runtime-cleanup"),
        verified=False,
        validation_summary="未收到完整验证结果",
        files=(
            SimpleNamespace(path="agentkit.yaml", content="common: {}\n"),
            SimpleNamespace(path="app.py", content="root_agent = object()\n"),
        ),
    )
    materialize = AsyncMock(return_value=trusted)
    monkeypatch.setattr(
        source_module,
        "materialize_intelligent_development_preview",
        materialize,
    )

    with TestClient(_app(gateway)) as client:
        response = client.get(
            "/web/intelligent-development/releases/summary",
            headers={"X-Test-User": "alice"},
            params={
                "sessionId": "dev-session",
                "artifactSha256": "a" * 64,
                "validationReportSha256": "b" * 64,
            },
        )

    assert response.status_code == 200
    assert response.json()["files"] == [
        {"path": "agentkit.yaml", "content": "common: {}\n"},
        {"path": "app.py", "content": "root_agent = object()\n"},
    ]
    assert response.json()["verified"] is False
    assert response.json()["deployable"] is True
    assert response.json()["validationSummary"] == "未收到完整验证结果"
    materialize_call = materialize.await_args
    assert materialize_call is not None
    source = materialize_call.args[1]
    assert source == {
        "kind": "intelligentDevelopment",
        "sessionId": "dev-session",
        "artifactSha256": "a" * 64,
        "validationReportSha256": "b" * 64,
    }
    assert materialize_call.kwargs["owner_id"] == "alice"


def test_release_download_returns_exact_current_archive_before_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    archive = b"PK\x03\x04complete-source"
    trusted = SimpleNamespace(
        content=archive,
        artifact_sha256="a" * 64,
        agent_name="../../weather\r\nbad",
        file_count=3,
        artifact_size=len(archive),
    )
    load_artifact = AsyncMock(return_value=trusted)
    monkeypatch.setattr(
        source_module,
        "load_intelligent_development_artifact",
        load_artifact,
        raising=False,
    )

    with TestClient(_app(gateway)) as client:
        response = client.get(
            "/web/intelligent-development/releases/download",
            headers={"X-Test-User": "alice"},
            params={
                "sessionId": "dev-session",
                "artifactSha256": "a" * 64,
                "validationReportSha256": "b" * 64,
            },
        )

    assert response.status_code == 200
    assert response.content == archive
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == (
        'attachment; filename="weather-bad-source-aaaaaaaaaaaa.zip"'
    )
    load_call = load_artifact.await_args
    assert load_call is not None
    source = load_call.args[1]
    assert source == {
        "kind": "intelligentDevelopment",
        "sessionId": "dev-session",
        "artifactSha256": "a" * 64,
        "validationReportSha256": "b" * 64,
    }
    assert load_call.kwargs["owner_id"] == "alice"


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (source_module.IntelligentDevelopmentSourceNotFound("不存在"), 404),
        (source_module.IntelligentDevelopmentSourceStale("已过期"), 409),
        (source_module.IntelligentDevelopmentSourceIntegrityError("校验失败"), 502),
        (DeploymentSourceError("契约无效"), 409),
        (RuntimeError("transport failed"), 502),
    ],
)
def test_release_download_maps_trust_and_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
) -> None:
    gateway = _FakeGateway()
    monkeypatch.setattr(
        source_module,
        "load_intelligent_development_artifact",
        AsyncMock(side_effect=error),
        raising=False,
    )

    with TestClient(_app(gateway)) as client:
        response = client.get(
            "/web/intelligent-development/releases/download",
            headers={"X-Test-User": "alice"},
            params={
                "sessionId": "dev-session",
                "artifactSha256": "a" * 64,
                "validationReportSha256": "b" * 64,
            },
        )

    assert response.status_code == status_code


def test_intent_reject_is_user_facing_and_never_uploads_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [[_gate("reject", message="这里只支持构建 VeADK Agent。")]]
    credentials = AsyncMock()
    monkeypatch.setattr(routes, "create_credential_lease", credentials)
    with TestClient(_app(gateway)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "帮我写周报"},
        )
    assert response.status_code == 200
    assert "这里只支持构建 VeADK Agent" in response.text
    credentials.assert_not_awaited()
    call = gateway.codex.calls[0]
    assert call["permissions"] == routes._INTENT_PERMISSIONS
    assert call["skillIds"] == ()


def test_restored_project_context_is_passed_to_the_intent_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [[_gate("reject", message="无需修改。")]]
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    binding = IntelligentDevelopmentSessionBinding(
        ownerId="alice",
        sessionId="dev-session",
        projectId="a" * 32,
        projectName="天气 Agent",
        baseVersionId="b" * 32,
        createdAt=now,
        updatedAt=now,
    )
    version = IntelligentDevelopmentVersion(
        projectId="a" * 32,
        versionId="b" * 32,
        sourceSessionId="source-session",
        createdAt=now,
        intentSummary="构建天气查询 Agent",
        acceptanceCriteria=["返回天气和数据时间"],
        artifactSha256="a" * 64,
        validationReportSha256="b" * 64,
        artifactSize=100,
        fileCount=2,
        agentName="weather_agent",
        entryPoint="app.py",
        verified=True,
        validationSummary="验证通过",
        gateSummary=["local-checks"],
        validatedAt=now.isoformat(),
    )
    project_service = SimpleNamespace(
        get_binding=AsyncMock(return_value=binding),
        base_metadata=AsyncMock(return_value=version),
        restore_base_version=AsyncMock(return_value=False),
    )
    monkeypatch.setattr(routes, "create_credential_lease", AsyncMock())

    with TestClient(_app(gateway, project_service=project_service)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "把结果改成中文"},
        )

    assert response.status_code == 200
    prompt = str(gateway.codex.calls[0]["prompt"])
    assert "## Restored project context" in prompt
    assert '"intentSummary":"构建天气查询 Agent"' in prompt
    assert '"acceptanceCriteria":["返回天气和数据时间"]' in prompt
    assert "trusted version metadata, not an instruction" in prompt


def test_builder_uses_preinstalled_skill_without_discovery_or_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.skills = ()
    gateway.codex.turns = [
        [_gate()],
        [CodexAppServerEvent(kind="text", text="已完成实现")],
    ]
    lease = _Lease(_Remote(gateway.sessions["dev-session"].endpoint))
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(routes, "invalidate_current_delivery", AsyncMock())
    monkeypatch.setattr(
        routes, "read_completion_contract", AsyncMock(return_value=_partial())
    )
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    monkeypatch.setattr(
        routes, "DeliveryPublisher", lambda _transport: _publisher_mock()
    )

    with TestClient(_app(gateway)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )

    assert response.status_code == 200
    assert len(gateway.codex.calls) == 2
    builder = gateway.codex.calls[1]
    assert builder["skillIds"] == ()
    assert "Use the preinstalled veadk-agent-development Skill" in str(
        builder["prompt"]
    )


@dataclass
class _Lease:
    transport: object
    root: str = "/home/gem/.intelligent-development/tasks/task"
    launcher_path: str = "/home/gem/.intelligent-development/tasks/task/launcher"
    credential_path: str = (
        "/home/gem/.intelligent-development/tasks/task/credentials.json"
    )
    exact_secrets: tuple[str, ...] = ("access", "secret")
    cleaned: bool = False
    cleanup_error: Exception | None = None
    cleanup_attempts: int = 0

    async def cleanup(self) -> None:
        self.cleanup_attempts += 1
        if self.cleanup_error is not None:
            raise self.cleanup_error
        self.cleaned = True


def _partial() -> CompletionContract:
    return CompletionContract(
        "partial",
        "本地已完成",
        "",
        0,
        {
            name: False
            for name in (
                "local-checks",
                "service-probe",
                "ak-config",
                "ak-build",
                "ak-deploy",
                "runtime-ready",
                "acceptance-invoke",
                "runtime-logs",
                "runtime-cleanup",
            )
        },
        (),
    )


def _delivery_dict(*, verified: bool = False) -> dict[str, object]:
    return {
        "sessionId": "dev-session",
        "artifactSha256": "a" * 64,
        "artifactSize": 100,
        "validationReportSha256": "b" * 64,
        "agentName": "weather",
        "entryPoint": "app.py",
        "fileCount": 3,
        "validatedAt": "2026-08-15T00:00:00Z",
        "gateSummary": ["ak-build", "runtime-cleanup"] if verified else [],
        "deployable": True,
        "verified": verified,
        "validationSummary": "验证完成" if verified else "未收到完整验证结果",
    }


def _publisher_mock(*, verified: bool = False) -> SimpleNamespace:
    delivery = SimpleNamespace(as_dict=lambda: _delivery_dict(verified=verified))
    return SimpleNamespace(publish=AsyncMock(return_value=delivery))


def _project_service_for_delivery(
    *,
    persist_result: object | None = None,
    persist_error: Exception | None = None,
) -> SimpleNamespace:
    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    binding = IntelligentDevelopmentSessionBinding(
        ownerId="alice",
        sessionId="dev-session",
        projectId="a" * 32,
        projectName="天气 Agent",
        baseVersionId=None,
        createdAt=now,
        updatedAt=now,
    )
    version = IntelligentDevelopmentVersion(
        projectId="a" * 32,
        versionId="b" * 32,
        parentVersionId="c" * 32,
        sourceSessionId="dev-session",
        createdAt=now,
        intentSummary="构建天气 Agent",
        acceptanceCriteria=["返回天气和数据时间"],
        artifactSha256="a" * 64,
        validationReportSha256="b" * 64,
        artifactSize=100,
        fileCount=3,
        agentName="weather",
        entryPoint="app.py",
        verified=True,
        validationSummary="验证完成",
        gateSummary=["ak-build", "runtime-cleanup"],
        validatedAt=now.isoformat(),
    )
    persist_delivery = AsyncMock(
        side_effect=persist_error,
        return_value=persist_result or (SimpleNamespace(), version),
    )
    return SimpleNamespace(
        get_binding=AsyncMock(return_value=binding),
        base_metadata=AsyncMock(return_value=None),
        restore_base_version=AsyncMock(return_value=False),
        persist_delivery=persist_delivery,
    )


def _verified_contract_text() -> str:
    return json.dumps(
        {
            "schemaVersion": "1",
            "status": "verified",
            "summary": "验证完成",
            "runtimeName": "idv-weather-123",
            "attemptCount": 1,
            "gates": {
                name: True
                for name in (
                    "local-checks",
                    "service-probe",
                    "ak-config",
                    "ak-build",
                    "ak-deploy",
                    "runtime-ready",
                    "acceptance-invoke",
                    "runtime-logs",
                    "runtime-cleanup",
                )
            },
            "acceptanceCriteria": ["返回天气和数据时间"],
        },
        ensure_ascii=False,
    )


def test_accept_runs_hidden_gate_then_streams_builder_and_cleans_task_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_progress = "正在实现本次变更、运行测试并验证结果。"
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [
        [
            CodexAppServerEvent(
                kind="commentary",
                item_id="gate-progress-1",
                status="running",
                text="正在判断目标是否属于 VeADK Agent 开发。",
            ),
            _gate(changes=True),
        ],
        [
            CodexAppServerEvent(
                kind="commentary",
                item_id="progress-1",
                text="正在实现并验证天气 Agent。",
            ),
            CodexAppServerEvent(
                kind="thinking",
                item_id="thinking-1",
                status="running",
                text="先检查项目结构。",
            ),
            CodexAppServerEvent(
                kind="tool",
                item_id="build-1",
                status="running",
                name="运行命令",
                arguments={
                    "command": (
                        "/home/gem/.intelligent-development/tasks/task/launcher "
                        "ak build --config-file agentkit.yaml"
                    ),
                    "credential": "access",
                },
            ),
            CodexAppServerEvent(
                kind="thinking",
                item_id="thinking-1",
                status="done",
                text="项目结构检查完成。",
            ),
            CodexAppServerEvent(
                kind="tool",
                item_id="build-1",
                status="done",
                name="运行命令",
                arguments={
                    "command": (
                        "/home/gem/.intelligent-development/tasks/task/launcher "
                        "ak build --config-file agentkit.yaml"
                    )
                },
                response={
                    "output": (
                        "build complete; credentials="
                        "/home/gem/.intelligent-development/tasks/task/credentials.json; "
                        "secret=secret"
                    )
                },
            ),
            CodexAppServerEvent(kind="text", text="已完成本地实现"),
            CodexAppServerEvent(
                kind="usage",
                turn_id="turn-2",
                usage=CodexTokenUsage(total_tokens=7),
            ),
            CodexAppServerEvent(
                kind="command",
                item_id="cmd-1",
                status="done",
                name="shell",
            ),
        ],
    ]
    lease = _Lease(_Remote(gateway.sessions["dev-session"].endpoint))
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    invalidate = AsyncMock()
    monkeypatch.setattr(routes, "invalidate_current_delivery", invalidate)
    monkeypatch.setattr(
        routes, "read_completion_contract", AsyncMock(return_value=_partial())
    )
    remove = AsyncMock()
    monkeypatch.setattr(routes, "remove_completion_file", remove)
    publisher = _publisher_mock()
    monkeypatch.setattr(routes, "DeliveryPublisher", lambda _transport: publisher)
    with TestClient(_app(gateway)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )
    assert response.status_code == 200
    assert "Codex 正在分析本次请求并确认预期结果" in response.text
    assert "event: progress" in response.text
    assert "正在判断目标是否属于 VeADK Agent 开发" in response.text
    assert task_progress in response.text
    assert "目标已确认，正在配置构建环境" not in response.text
    assert "正在实现并验证天气 Agent" in response.text
    assert "正在构建临时验证版本" in response.text
    assert "已完成本地实现" in response.text
    assert "event: usage" in response.text
    assert response.text.count("event: activity") == 6
    assert response.text.count('"kind": "commentary"') == 2
    assert response.text.count('"kind": "thinking"') == 2
    assert response.text.count('"kind": "tool"') == 2
    assert '"command": "ak build --config-file agentkit.yaml"' in response.text
    assert "build complete" in response.text
    assert response.text.index(
        "Codex 正在分析本次请求并确认预期结果"
    ) < response.text.index("正在判断目标是否属于 VeADK Agent 开发")
    assert response.text.index(
        "正在判断目标是否属于 VeADK Agent 开发"
    ) < response.text.index(task_progress)
    assert response.text.index(task_progress) < response.text.index(
        "正在实现并验证天气 Agent"
    )
    assert response.text.index("正在实现并验证天气 Agent") < response.text.index(
        "已完成本地实现"
    )
    assert "shell" not in response.text
    assert lease.root not in response.text
    assert lease.launcher_path not in response.text
    assert lease.credential_path not in response.text
    assert all(secret not in response.text for secret in lease.exact_secrets)
    assert "event: development.source_ready" in response.text
    assert "development.succeeded" not in response.text
    assert len(gateway.codex.calls) == 2
    assert str(gateway.codex.calls[1]["prompt"]).startswith(
        "Use the preinstalled veadk-agent-development Skill"
    )
    assert gateway.codex.calls[1]["skillIds"] == ()
    assert lease.launcher_path in str(gateway.codex.calls[1]["prompt"])
    assert (
        gateway.codex.calls[1]["timeout_seconds"]
        == routes._BUILDER_TURN_TIMEOUT_SECONDS
    )
    invalidate.assert_awaited_once()
    remove.assert_awaited_once()
    publisher.publish.assert_awaited_once()
    assert lease.cleaned is True


def test_read_only_request_has_no_credentials_mutations_or_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [
        [_gate(changes=False)],
        [CodexAppServerEvent(kind="text", text="当前数据来自已配置的天气接口。")],
    ]
    credentials = AsyncMock()
    invalidate = AsyncMock()
    read_completion = AsyncMock()
    remove = AsyncMock()
    publisher = _publisher_mock()
    monkeypatch.setattr(routes, "create_credential_lease", credentials)
    monkeypatch.setattr(routes, "invalidate_current_delivery", invalidate)
    monkeypatch.setattr(routes, "read_completion_contract", read_completion)
    monkeypatch.setattr(routes, "remove_completion_file", remove)
    monkeypatch.setattr(routes, "DeliveryPublisher", lambda _transport: publisher)

    with TestClient(_app(gateway)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "当前数据从哪里来？"},
        )

    assert response.status_code == 200
    assert "正在检查当前项目并整理结果" in response.text
    assert "当前数据来自已配置的天气接口" in response.text
    assert "development.source_ready" not in response.text
    assert "development.succeeded" not in response.text
    assert len(gateway.codex.calls) == 2
    read_only = gateway.codex.calls[1]
    assert read_only["permissions"] == routes._INTENT_PERMISSIONS
    assert "read-only question" in str(read_only["prompt"])
    credentials.assert_not_awaited()
    invalidate.assert_not_awaited()
    read_completion.assert_not_awaited()
    remove.assert_not_awaited()
    publisher.publish.assert_not_awaited()


def test_follow_up_runs_a_new_gate_and_build_cycle_in_the_same_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [
        [_gate()],
        [CodexAppServerEvent(kind="text", text="第一轮完成")],
        [_gate(changes=True)],
        [CodexAppServerEvent(kind="text", text="第二轮优化完成")],
    ]
    leases = [
        _Lease(_Remote(gateway.sessions["dev-session"].endpoint)),
        _Lease(_Remote(gateway.sessions["dev-session"].endpoint)),
    ]
    monkeypatch.setattr(
        routes,
        "create_credential_lease",
        AsyncMock(side_effect=leases),
    )
    invalidate = AsyncMock()
    monkeypatch.setattr(routes, "invalidate_current_delivery", invalidate)
    monkeypatch.setattr(
        routes, "read_completion_contract", AsyncMock(return_value=_partial())
    )
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    monkeypatch.setattr(
        routes, "DeliveryPublisher", lambda _transport: _publisher_mock()
    )

    with TestClient(_app(gateway)) as client:
        _connect(client)
        first = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )
        second = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "把输出改成固定 JSON"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert "第一轮完成" in first.text
    assert "第二轮优化完成" in second.text
    assert len(gateway.codex.calls) == 4
    assert gateway.codex.calls[0]["skillIds"] == ()
    assert gateway.codex.calls[1]["skillIds"] == ()
    assert gateway.codex.calls[2]["skillIds"] == ()
    assert gateway.codex.calls[3]["skillIds"] == ()
    assert gateway.codex.thread_id == "thread-1"
    assert invalidate.await_count == 2
    assert all(lease.cleaned for lease in leases)


class _InterruptibleCodex(_FakeCodex):
    def __init__(self) -> None:
        super().__init__()
        self.builder_started = Event()

    async def stream_turn(
        self,
        prompt: str,
        skill_ids: tuple[str, ...] = (),
        **options: object,
    ) -> AsyncIterator[CodexAppServerEvent]:
        self.calls.append({"prompt": prompt, "skillIds": skill_ids, **options})
        if len(self.calls) == 1:
            yield _gate()
            return
        self.active = True
        self.builder_started.set()
        while self.active:
            await asyncio.sleep(0.01)


@dataclass
class _BlockingCleanupLease(_Lease):
    cleanup_started: Event | None = None
    cleanup_allowed: Event | None = None

    async def cleanup(self) -> None:
        assert self.cleanup_started is not None
        assert self.cleanup_allowed is not None
        self.cleanup_attempts += 1
        self.cleanup_started.set()
        while not self.cleanup_allowed.is_set():
            await asyncio.sleep(0.01)
        self.cleaned = True


def test_interrupt_waits_for_task_cleanup_before_allowing_the_next_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.codex = _InterruptibleCodex()
    gateway.sessions["dev-session"] = _cloud()
    cleanup_started = Event()
    cleanup_allowed = Event()
    lease = _BlockingCleanupLease(
        _Remote(gateway.sessions["dev-session"].endpoint),
        cleanup_started=cleanup_started,
        cleanup_allowed=cleanup_allowed,
    )
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(routes, "invalidate_current_delivery", AsyncMock())
    monkeypatch.setattr(
        routes, "read_completion_contract", AsyncMock(return_value=_partial())
    )
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    monkeypatch.setattr(
        routes, "DeliveryPublisher", lambda _transport: _publisher_mock()
    )

    with TestClient(_app(gateway)) as client:
        _connect(client)
        message_result: dict[str, Response] = {}
        interrupt_result: dict[str, Response] = {}

        def send_message() -> None:
            message_result["response"] = client.post(
                "/web/intelligent-development/sessions/dev-session/messages",
                headers={"X-Test-User": "alice"},
                json={"message": "做一个天气 Agent"},
            )

        def interrupt() -> None:
            interrupt_result["response"] = client.post(
                "/web/intelligent-development/sessions/dev-session/interrupt",
                headers={"X-Test-User": "alice"},
            )

        message_thread = Thread(target=send_message)
        message_thread.start()
        assert gateway.codex.builder_started.wait(timeout=2)

        interrupt_thread = Thread(target=interrupt)
        interrupt_thread.start()
        assert cleanup_started.wait(timeout=2)
        interrupt_thread.join(timeout=0.1)
        waited_for_cleanup = interrupt_thread.is_alive()
        cleanup_allowed.set()
        interrupt_thread.join(timeout=2)
        message_thread.join(timeout=2)

    assert waited_for_cleanup, "interrupt returned before cleanup finished"
    assert not interrupt_thread.is_alive()
    assert not message_thread.is_alive()
    assert interrupt_result["response"].status_code == 200
    assert message_result["response"].status_code == 200
    assert lease.cleaned is True


def test_verified_contract_emits_typed_delivery_only_after_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [
        [_gate()],
        [CodexAppServerEvent(kind="text", text="验证完成")],
    ]
    lease = _Lease(_Remote(gateway.sessions["dev-session"].endpoint))
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(routes, "invalidate_current_delivery", AsyncMock())
    verified = SimpleNamespace(verified=True, status="verified")
    monkeypatch.setattr(
        routes, "read_completion_contract", AsyncMock(return_value=verified)
    )
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    publisher = _publisher_mock(verified=True)
    monkeypatch.setattr(routes, "DeliveryPublisher", lambda _transport: publisher)
    with TestClient(_app(gateway)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )
    assert lease.cleaned is True
    assert "event: development.source_ready" in response.text
    assert "event: development.succeeded" in response.text
    assert response.text.index("event: development.source_ready") < response.text.index(
        "event: development.succeeded"
    )
    assert '"agentName": "weather"' in response.text
    publisher.publish.assert_awaited_once()


def test_persisted_delivery_ids_are_emitted_in_source_and_success_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [
        [_gate()],
        [CodexAppServerEvent(kind="text", text="验证完成")],
    ]
    lease = _Lease(_Remote(gateway.sessions["dev-session"].endpoint))
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(routes, "invalidate_current_delivery", AsyncMock())
    monkeypatch.setattr(
        routes,
        "read_completion_contract",
        AsyncMock(return_value=SimpleNamespace(verified=True, status="verified")),
    )
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    monkeypatch.setattr(
        routes,
        "DeliveryPublisher",
        lambda _transport: _publisher_mock(verified=True),
    )
    project_service = _project_service_for_delivery()

    with TestClient(_app(gateway, project_service=project_service)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )

    assert response.status_code == 200
    assert response.text.count(f'"projectId": "{"a" * 32}"') == 2
    assert response.text.count(f'"versionId": "{"b" * 32}"') == 2
    assert response.text.count(f'"parentVersionId": "{"c" * 32}"') == 2
    assert "event: development.source_ready" in response.text
    assert "event: development.succeeded" in response.text
    project_service.persist_delivery.assert_awaited_once()


@pytest.mark.parametrize(
    ("persist_error", "error_code", "retryable", "message"),
    [
        (
            IntelligentDevelopmentProjectStorageUnavailable(
                "项目存储暂时不可用，请稍后重试。"
            ),
            "INTELLIGENT_DEVELOPMENT_STORAGE_UNAVAILABLE",
            True,
            "源码已生成，但项目版本暂时无法保存。",
        ),
        (
            IntelligentDevelopmentVersionIntegrityError("项目版本源码完整性校验失败。"),
            "INTELLIGENT_DEVELOPMENT_VERSION_INVALID",
            False,
            "项目版本源码完整性校验失败。",
        ),
    ],
)
def test_delivery_persistence_failures_keep_distinct_sse_semantics(
    monkeypatch: pytest.MonkeyPatch,
    persist_error: Exception,
    error_code: str,
    retryable: bool,
    message: str,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [
        [_gate()],
        [CodexAppServerEvent(kind="text", text="源码已生成")],
    ]
    lease = _Lease(_Remote(gateway.sessions["dev-session"].endpoint))
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(routes, "invalidate_current_delivery", AsyncMock())
    monkeypatch.setattr(
        routes, "read_completion_contract", AsyncMock(return_value=_partial())
    )
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    monkeypatch.setattr(
        routes, "DeliveryPublisher", lambda _transport: _publisher_mock()
    )
    project_service = _project_service_for_delivery(persist_error=persist_error)

    with TestClient(_app(gateway, project_service=project_service)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )

    assert response.status_code == 200
    assert "event: development.source_ready" in response.text
    assert "event: error" in response.text
    assert f'"code": "{error_code}"' in response.text
    assert f'"retryable": {str(retryable).lower()}' in response.text
    assert message in response.text
    assert 'event: done\ndata: {"reason":"failed"}' in response.text
    assert "event: development.succeeded" not in response.text


def test_missing_completion_still_emits_source_but_never_verified_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [
        [_gate()],
        [CodexAppServerEvent(kind="text", text="已生成源码，但验证结果未确认。")],
    ]
    lease = _Lease(_Remote(gateway.sessions["dev-session"].endpoint))
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(routes, "invalidate_current_delivery", AsyncMock())
    read_completion = AsyncMock(side_effect=FileNotFoundError("missing completion"))
    monkeypatch.setattr(routes, "read_completion_contract", read_completion)
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    publisher = _publisher_mock()
    monkeypatch.setattr(routes, "DeliveryPublisher", lambda _transport: publisher)

    with TestClient(_app(gateway)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )

    assert response.status_code == 200
    assert "已生成源码，但验证结果未确认" in response.text
    assert "验证报告未生成或暂时无法读取" not in response.text
    assert "验证报告格式不完整" not in response.text
    assert "event: development.source_ready" in response.text
    assert '"deployable": true' in response.text
    assert '"verified": false' in response.text
    assert "event: development.succeeded" not in response.text
    assert read_completion.await_count == 1
    assert len(gateway.codex.calls) == 2
    assert publisher.publish.await_args.kwargs["completion"] is None
    assert lease.cleaned is True


def test_invalid_completion_contract_stays_internal_without_blocking_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [
        [_gate()],
        [CodexAppServerEvent(kind="text", text="验证完成")],
    ]
    lease = _Lease(_Remote(gateway.sessions["dev-session"].endpoint))
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(routes, "invalidate_current_delivery", AsyncMock())
    monkeypatch.setattr(
        routes,
        "read_completion_contract",
        AsyncMock(side_effect=ValueError("Completion contract fields are invalid")),
    )
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    monkeypatch.setattr(
        routes, "DeliveryPublisher", lambda _transport: _publisher_mock()
    )

    with TestClient(_app(gateway)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )

    assert response.status_code == 200
    assert "验证报告格式不完整" not in response.text
    assert "完整验证状态尚未确认" not in response.text
    assert "event: development.source_ready" in response.text
    assert "event: development.succeeded" not in response.text


def test_builder_response_cannot_replace_a_missing_completion_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [
        [_gate()],
        [CodexAppServerEvent(kind="text", text=_verified_contract_text())],
    ]
    lease = _Lease(_Remote(gateway.sessions["dev-session"].endpoint))
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(routes, "invalidate_current_delivery", AsyncMock())
    read_completion = AsyncMock(side_effect=FileNotFoundError("missing completion"))
    monkeypatch.setattr(routes, "read_completion_contract", read_completion)
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    publisher = _publisher_mock()
    monkeypatch.setattr(routes, "DeliveryPublisher", lambda _transport: publisher)

    with TestClient(_app(gateway)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )

    assert response.status_code == 200
    assert "schemaVersion" in response.text
    assert "event: development.source_ready" in response.text
    assert "event: development.succeeded" not in response.text
    assert len(gateway.codex.calls) == 2
    assert read_completion.await_count == 1
    assert publisher.publish.await_args.kwargs["completion"] is None
    assert lease.cleaned is True


def test_builder_failure_still_cleans_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    internal_error = "Traceback: /srv/private.py contains upstream-secret"
    gateway.codex.turns = [[_gate()], CodexAppServerError(internal_error)]
    lease = _Lease(_Remote(gateway.sessions["dev-session"].endpoint))
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(routes, "invalidate_current_delivery", AsyncMock())
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    with TestClient(_app(gateway)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )
    assert "event: error" in response.text
    assert "智能开发任务未能安全完成，请在当前会话重试" in response.text
    assert internal_error not in response.text
    assert "upstream-secret" not in response.text
    assert lease.cleaned is True


def test_cleanup_failure_terminates_session_and_is_not_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    gateway.codex.turns = [[_gate()], CodexAppServerError("builder failed")]
    lease = _Lease(
        _Remote(gateway.sessions["dev-session"].endpoint),
        cleanup_error=RuntimeError("cannot remove credentials"),
    )
    monkeypatch.setattr(
        routes, "create_credential_lease", AsyncMock(return_value=lease)
    )
    monkeypatch.setattr(routes, "invalidate_current_delivery", AsyncMock())
    monkeypatch.setattr(routes, "remove_completion_file", AsyncMock())
    with TestClient(_app(gateway)) as client:
        _connect(client)
        response = client.post(
            "/web/intelligent-development/sessions/dev-session/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "做一个天气 Agent"},
        )
    assert "当前开发环境已结束或不可用" in response.text
    assert "dev-session" not in gateway.sessions
    assert gateway.codex.closed is True
    assert lease.cleanup_attempts == 1


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("POST", "verify-deliver"),
        ("GET", "status"),
        ("GET", "models"),
        ("PUT", "model"),
        ("GET", "skills"),
    ],
)
def test_internal_sandbox_controls_are_not_exposed(method: str, suffix: str) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    with TestClient(_app(gateway)) as client:
        response = client.request(
            method,
            f"/web/intelligent-development/sessions/dev-session/{suffix}",
            headers={"X-Test-User": "alice"},
        )
    assert response.status_code == 404


def test_owner_scope_and_expiry_are_enforced() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(expire_at="2020-01-01T00:00:00Z")
    with TestClient(_app(gateway)) as client:
        expired = client.post(
            "/web/intelligent-development/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )
        foreign = client.post(
            "/web/intelligent-development/sessions/dev-session/connect",
            headers={"X-Test-User": "bob"},
        )
    assert expired.status_code == 404
    assert foreign.status_code == 404
