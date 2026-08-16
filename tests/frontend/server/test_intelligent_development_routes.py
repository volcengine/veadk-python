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
from collections.abc import AsyncIterator
from dataclasses import dataclass
import json
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from httpx import Response

from frontend.server import intelligent_development_routes as routes
from frontend.server import intelligent_development_source as source_module
from frontend.server.intelligent_development import StudioCredentials
from frontend.server.intelligent_development_task import CompletionContract
from veadk.cli.codex_app_server import (
    CodexAppServerError,
    CodexAppServerEvent,
    CodexPermissionSettings,
    CodexSkill,
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

    async def close(self) -> None:
        self.closed = True


class _FakeGateway:
    def __init__(self) -> None:
        self.sessions: dict[str, SandboxCloudSession] = {}
        self.codex = _FakeCodex()
        self.created = 0

    async def create_session(
        self,
        tool_id: str,
        display_name: str = "",
        username: str = "",
        creator_name: str = "",
        agent_kind: str = "",
    ) -> SandboxCloudSession:
        self.created += 1
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


def _app(gateway: _FakeGateway, *, configured: bool = True) -> FastAPI:
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
        configured=configured,
    )
    return app


@pytest.fixture(autouse=True)
def _remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "SandboxRemoteTransport", _Remote)


def _connect(client: TestClient) -> None:
    response = client.post(
        "/web/intelligent-development/sessions/dev-session/connect",
        headers={"X-Test-User": "alice"},
    )
    assert response.status_code == 200


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


def test_connect_locks_fixed_workspace_and_enables_autonomous_builder() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    with TestClient(_app(gateway)) as client:
        _connect(client)
    assert gateway.codex.cwd == "/home/gem/workspace/project-1"
    assert gateway.codex.permissions == routes._BUILDER_PERMISSIONS


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
    assert response.json()["validationSummary"] == "未收到完整验证结果"
    source = materialize.await_args.args[1]
    assert source == {
        "kind": "intelligentDevelopment",
        "sessionId": "dev-session",
        "artifactSha256": "a" * 64,
        "validationReportSha256": "b" * 64,
    }
    assert materialize.await_args.kwargs["owner_id"] == "alice"


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
        "verified": verified,
        "validationSummary": "验证完成" if verified else "未收到完整验证结果",
    }


def _publisher_mock(*, verified: bool = False) -> SimpleNamespace:
    delivery = SimpleNamespace(as_dict=lambda: _delivery_dict(verified=verified))
    return SimpleNamespace(publish=AsyncMock(return_value=delivery))


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
            _gate(),
        ],
        [
            CodexAppServerEvent(
                kind="commentary",
                item_id="progress-1",
                text="正在实现并验证天气 Agent。",
            ),
            CodexAppServerEvent(
                kind="tool",
                item_id="build-1",
                status="running",
                name="运行命令",
                arguments={
                    "command": "/task/launcher ak build --config-file agentkit.yaml"
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
    assert "正在理解需求并整理验收标准" in response.text
    assert "正在判断目标是否属于 VeADK Agent 开发" in response.text
    assert "需求已确认，正在准备开发环境" in response.text
    assert "正在实现并验证天气 Agent" in response.text
    assert "正在构建临时验证版本" in response.text
    assert "已完成本地实现" in response.text
    assert "event: usage" in response.text
    assert response.text.count("event: activity") == 2
    assert response.text.count('"kind": "thinking"') == 2
    assert response.text.index("正在理解需求并整理验收标准") < response.text.index(
        "正在判断目标是否属于 VeADK Agent 开发"
    )
    assert response.text.index(
        "正在判断目标是否属于 VeADK Agent 开发"
    ) < response.text.index("需求已确认，正在准备开发环境")
    assert response.text.index("需求已确认，正在准备开发环境") < response.text.index(
        "正在实现并验证天气 Agent"
    )
    assert response.text.index("正在实现并验证天气 Agent") < response.text.index(
        "已完成本地实现"
    )
    assert "shell" not in response.text
    assert "/task/launcher" not in response.text
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
    verified = SimpleNamespace(verified=True)
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
    assert "event: development.source_ready" in response.text
    assert '"verified": false' in response.text
    assert "event: development.succeeded" not in response.text
    assert read_completion.await_count == 1
    assert len(gateway.codex.calls) == 2
    assert publisher.publish.await_args.kwargs["completion"] is None
    assert lease.cleaned is True


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
    gateway.codex.turns = [[_gate()], CodexAppServerError("builder failed")]
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
    assert "开发环境已自动终止" in response.text
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
