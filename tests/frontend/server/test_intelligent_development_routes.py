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

"""Focused route-contract tests for foreground intelligent development."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from frontend.server.intelligent_development import (
    DevelopmentEvent,
    DevelopmentStage,
)
from frontend.server import intelligent_development_routes as routes
from frontend.server import intelligent_development_source as source_module
from frontend.server.deployment_source import DeploymentSourceError
from veadk.cli.agentkit_session_metadata import SESSION_AGENT_KIND_METADATA_KEY
from veadk.cli.codex_app_server import (
    CodexAppServerError,
    CodexAppServerEvent,
    CodexApproval,
    CodexPermissionSettings,
    CodexTokenUsage,
)
from veadk.cli.frontend_sandbox import (
    SandboxCapacityError,
    SandboxCloudSession,
    SandboxConfigurationError,
    SandboxConversationService,
    SandboxError,
    SandboxInvocationError,
    SandboxProvisioningError,
    SandboxSessionNotFoundError,
    SandboxSessionUnavailableError,
    SandboxValidationError,
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
        self.prompts: list[tuple[str, tuple[str, ...]]] = []
        self.list_skills_calls = 0
        self.events: list[CodexAppServerEvent] | None = None
        self.stream_error: CodexAppServerError | None = None

    async def stream_turn(
        self,
        prompt: str,
        skill_ids: tuple[str, ...] = (),
    ) -> AsyncIterator[CodexAppServerEvent]:
        self.prompts.append((prompt, skill_ids))
        if self.stream_error is not None:
            raise self.stream_error
        if self.events is not None:
            for event in self.events:
                yield event
            return
        yield CodexAppServerEvent(kind="text", text=f"reply:{prompt}")

    async def list_models(self) -> tuple[object, ...]:
        return (
            SimpleNamespace(
                public_dict=lambda: {
                    "id": "model-1",
                    "displayName": "Model One",
                    "description": "",
                    "isDefault": True,
                }
            ),
        )

    async def set_model(self, model: str) -> str:
        self.model = model
        return model

    async def list_skills(self, force_reload: bool = False) -> tuple[object, ...]:
        del force_reload
        self.list_skills_calls += 1
        raise AssertionError("intelligent development must not list skills")

    async def update_workspace(self, cwd: str) -> str:
        if self.workspace_locked:
            raise AssertionError("locked workspace must not be changed")
        self.cwd = cwd
        return cwd

    async def interrupt(self) -> None:
        self.active = False

    async def close(self) -> None:
        self.closed = True


class _FakeGateway:
    def __init__(self) -> None:
        self.sessions: dict[str, SandboxCloudSession] = {}
        self.created_metadata: list[dict[str, str]] = []
        self.created = 0
        self.opened: list[_FakeCodex] = []
        self.deleted: list[str] = []
        self.drained = False
        self.codex_factory: Callable[[], _FakeCodex] = _FakeCodex

    async def create_session(
        self,
        tool_id: str,
        display_name: str = "",
        username: str = "",
        creator_name: str = "",
        agent_kind: str = "",
    ) -> SandboxCloudSession:
        self.created += 1
        recorded = {SESSION_AGENT_KIND_METADATA_KEY: agent_kind}
        self.created_metadata.append(recorded)
        session = SandboxCloudSession(
            tool_id=tool_id,
            instance_id=f"session-{self.created}",
            user_session_id=f"workspace-{self.created}",
            endpoint="https://sandbox.example/dev?Authorization=secret",
            status="Ready",
            created_at="2026-08-14T08:00:00Z",
            expire_at="2026-08-14T16:00:00Z",
            tool_type="CodeEnv",
            display_name=display_name,
            created_by=username,
            creator_name=creator_name,
            agent_kind=recorded.get(SESSION_AGENT_KIND_METADATA_KEY, ""),
        )
        self.sessions[session.instance_id] = session
        return session

    async def get_session(self, tool_id: str, session_id: str) -> SandboxCloudSession:
        session = self.sessions.get(session_id)
        if session is None or session.tool_id != tool_id:
            raise SandboxSessionNotFoundError("not found")
        return session

    async def list_sessions(
        self,
        tool_id: str,
        username: str | None = None,
    ) -> list[SandboxCloudSession]:
        return [
            session
            for session in self.sessions.values()
            if session.tool_id == tool_id
            and (username is None or session.created_by == username)
        ]

    async def open_codex(self, session: SandboxCloudSession) -> _FakeCodex:
        del session
        codex = self.codex_factory()
        self.opened.append(codex)
        return codex

    async def delete_session(self, session: SandboxCloudSession) -> None:
        self.deleted.append(session.instance_id)
        self.sessions.pop(session.instance_id, None)

    async def drain(self) -> None:
        self.drained = True


def _cloud(
    *,
    session_id: str = "dev-session",
    owner: str = "alice",
    user_session_id: str = "safe-workspace",
    agent_kind: str = routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    status: str = "Ready",
    endpoint: str = "https://sandbox.example/dev?Authorization=secret",
    expire_at: str = "2027-08-14T16:00:00Z",
) -> SandboxCloudSession:
    return SandboxCloudSession(
        tool_id="tool-dev",
        instance_id=session_id,
        user_session_id=user_session_id,
        endpoint=endpoint,
        status=status,
        created_at="2026-08-14T08:00:00Z",
        expire_at=expire_at,
        tool_type="CodeEnv",
        created_by=owner,
        agent_kind=agent_kind,
    )


def _app(
    gateway: _FakeGateway,
    *,
    verifier_factory: routes.VerifierFactory | None = None,
    tool_id: str | None = "tool-dev",
) -> FastAPI:
    app = FastAPI()
    service = SandboxConversationService(
        routes.IntelligentDevelopmentGateway(gateway),
        tool_id=tool_id,
        agent_kind=routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    )
    app.state.test_service = service

    def owner(request: Request) -> str:
        value = request.headers.get("X-Test-User", "")
        if not value:
            raise HTTPException(status_code=401, detail="identity required")
        return value

    def creator(request: Request) -> str:
        return request.headers.get("X-Test-Creator") or owner(request)

    routes.mount_intelligent_development_routes(
        app,
        service,
        owner,
        creator,
        verifier_factory,
        configured=tool_id is not None,
    )
    return app


class _RemoteRecorder:
    calls: list[tuple[str, int]] = []
    error: SandboxError | None = None

    def __init__(self, endpoint: str) -> None:
        assert endpoint.startswith("https://sandbox.example/")

    async def exec_text(self, command: str, *, timeout: int = 12) -> str:
        self.calls.append((command, timeout))
        if self.error is not None:
            raise self.error
        return ""


@pytest.fixture(autouse=True)
def _record_workspace_preparation(monkeypatch: pytest.MonkeyPatch) -> None:
    _RemoteRecorder.calls = []
    _RemoteRecorder.error = None
    monkeypatch.setattr(routes, "SandboxRemoteTransport", _RemoteRecorder)


@pytest.mark.asyncio
async def test_gateway_forces_development_metadata_and_does_not_drain_shared_gateway() -> (
    None
):
    gateway = _FakeGateway()
    adapter = routes.IntelligentDevelopmentGateway(gateway)

    session = await adapter.create_session(
        "tool-dev",
        "Dev",
        "alice",
        agent_kind=routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    )
    await adapter.drain()

    assert gateway.created_metadata == [
        {SESSION_AGENT_KIND_METADATA_KEY: routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND}
    ]
    assert session.agent_kind == routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND
    assert gateway.drained is False


@pytest.mark.parametrize(
    ("tool_id", "expected"),
    [
        ("tool-dev", {"enabled": True, "reason": ""}),
        (None, {"enabled": False, "reason": "管理员未配置 SANDBOX_DEV"}),
    ],
)
def test_capabilities_expose_only_fixed_development_availability(
    tool_id: str | None,
    expected: dict[str, object],
) -> None:
    with TestClient(_app(_FakeGateway(), tool_id=tool_id)) as client:
        response = client.get(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/capabilities",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.json() == expected
    assert "persistent" not in response.text.lower()


def test_create_uses_transient_session_and_returns_fixed_public_contract() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions",
            headers={
                "X-Test-User": "alice-id",
                "X-Test-Creator": "alice@example.com",
            },
            json={"displayName": "  My Agent  "},
        )

    assert response.status_code == 200
    assert response.json() == {
        "sessionId": "session-1",
        "userSessionId": "workspace-1",
        "status": "Ready",
        "createdAt": "2026-08-14T08:00:00Z",
        "expireAt": "2026-08-14T16:00:00Z",
        "toolType": "CodeEnv",
        "createdBy": "alice@example.com",
        "displayName": "My Agent",
        "persistent": False,
        "toolName": routes.INTELLIGENT_DEVELOPMENT_TOOL_NAME,
    }
    assert gateway.sessions["session-1"].created_by == "alice-id"
    assert gateway.created_metadata == [
        {SESSION_AGENT_KIND_METADATA_KEY: routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND}
    ]
    assert "endpoint" not in response.text.lower()
    assert "secret" not in response.text.lower()


@pytest.mark.parametrize(
    "body",
    [
        {"displayName": "Dev", "extra": True},
        {"persistent": False},
        {"skillIds": ["review"]},
    ],
)
def test_create_rejects_every_non_display_name_field(body: dict[str, object]) -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions",
            headers={"X-Test-User": "alice"},
            json=body,
        )

    assert response.status_code == 422
    assert gateway.created == 0


def test_message_surface_is_text_only_and_never_lists_or_selects_skills() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    with TestClient(_app(gateway)) as client:
        connected = client.post(f"{root}/connect", headers={"X-Test-User": "alice"})
        skills = client.get(f"{root}/skills", headers={"X-Test-User": "alice"})
        selected = client.post(
            f"{root}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "review it", "skillIds": ["review"]},
        )
        response = client.post(
            f"{root}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "  build it  "},
        )

    assert connected.status_code == 200
    assert skills.status_code == 404
    assert selected.status_code == 422
    assert response.status_code == 200
    assert 'event: delta\ndata: {"text": "reply:build it"}' in response.text
    assert "event: done" in response.text
    assert gateway.opened[0].prompts == [("build it", ())]
    assert gateway.opened[0].list_skills_calls == 0


def test_list_and_delete_hide_same_owner_foreign_agent_kinds() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(session_id="dev-session")
    gateway.sessions["foreign-session"] = _cloud(
        session_id="foreign-session",
        agent_kind="other",
    )
    root = routes.INTELLIGENT_DEVELOPMENT_PREFIX
    with TestClient(_app(gateway)) as client:
        listed = client.get(f"{root}/sessions", headers={"X-Test-User": "alice"})
        rejected = client.delete(
            f"{root}/sessions/foreign-session",
            headers={"X-Test-User": "alice"},
        )
        deleted = client.delete(
            f"{root}/sessions/dev-session",
            headers={"X-Test-User": "alice"},
        )

    assert listed.status_code == 200
    assert [item["sessionId"] for item in listed.json()["sessions"]] == ["dev-session"]
    assert listed.json()["sessions"][0]["toolName"] == (
        routes.INTELLIGENT_DEVELOPMENT_TOOL_NAME
    )
    assert rejected.status_code == 404
    assert "foreign-session" in gateway.sessions
    assert deleted.json() == {"deleted": True}
    assert gateway.deleted == ["dev-session"]


def test_admin_header_cannot_bypass_owner_scope_on_custom_or_delegated_routes() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(owner="alice")
    headers = {"X-Test-User": "bob", "X-Test-Role": "admin"}
    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    with TestClient(_app(gateway)) as client:
        connected = client.post(f"{root}/connect", headers=headers)
        deleted = client.delete(root, headers=headers)

    assert connected.status_code == 404
    assert deleted.status_code == 404
    assert "dev-session" in gateway.sessions
    assert gateway.deleted == []
    assert gateway.opened == []


@pytest.mark.parametrize("agent_kind", ["other", "codex", ""])
def test_connect_rejects_foreign_agent_kind_before_opening_codex(
    agent_kind: str,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(
        agent_kind=agent_kind,
    )
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 404
    assert gateway.opened == []
    assert _RemoteRecorder.calls == []


@pytest.mark.parametrize("identity", ["../escape", "/absolute", "bad/name", "x" * 129])
def test_connect_rejects_unsafe_workspace_identity(identity: str) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id=identity)
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 409
    assert _RemoteRecorder.calls == []


def test_connect_prepares_and_locks_the_fixed_workspace() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.json()["cwd"] == "/home/gem/workspace/project-1"
    assert response.json()["workspaceLocked"] is False
    assert response.json()["persistent"] is False
    assert response.json()["toolName"] == routes.INTELLIGENT_DEVELOPMENT_TOOL_NAME
    assert len(_RemoteRecorder.calls) == 1
    command, timeout = _RemoteRecorder.calls[0]
    assert "/home/gem/workspace/project-1" in command
    assert "follow_symlinks=False" in command
    assert timeout == 12


def test_connect_rejects_a_locked_codex_in_another_workspace() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    gateway.codex_factory = lambda: _FakeCodex(cwd="/tmp/other", locked=True)
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 409
    assert _RemoteRecorder.calls == []


class _RecordingVerifier:
    def __init__(
        self,
        sink: Callable[[DevelopmentEvent], Any],
        *,
        blocking: bool = False,
        error: Exception | None = None,
    ) -> None:
        self.sink = sink
        self.blocking = blocking
        self.error = error
        self.calls: list[tuple[str, object]] = []
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def run(self, *, owner_id: str, session: object) -> None:
        self.calls.append((owner_id, session))
        event = DevelopmentEvent(
            1,
            "verification.stage.started",
            DevelopmentStage.LOCAL_COMPILE,
            "2026-08-14T08:00:00+00:00",
            {"name": "compile"},
        )
        await self.sink(event)
        self.started.set()
        if self.error is not None:
            raise self.error
        if self.blocking:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise


@pytest.mark.parametrize("agent_kind", ["other", "codex"])
def test_verify_deliver_rejects_foreign_agent_kind_before_opening_codex(
    agent_kind: str,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(
        agent_kind=agent_kind,
    )

    def verifier_factory(sink: Callable[[DevelopmentEvent], Any]) -> _RecordingVerifier:
        return _RecordingVerifier(sink)

    with TestClient(_app(gateway, verifier_factory=verifier_factory)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/verify-deliver",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 404
    assert gateway.opened == []


def test_verify_deliver_requires_configured_verifier() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/verify-deliver",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 503
    assert gateway.opened == []


def test_verify_deliver_rejects_foreign_owner_and_busy_codex() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(owner="alice", user_session_id="project-1")
    verifier_instances: list[_RecordingVerifier] = []

    def verifier_factory(sink: Callable[[DevelopmentEvent], Any]) -> _RecordingVerifier:
        verifier = _RecordingVerifier(sink)
        verifier_instances.append(verifier)
        return verifier

    app = _app(gateway, verifier_factory=verifier_factory)
    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    with TestClient(app) as client:
        foreign = client.post(
            f"{root}/verify-deliver",
            headers={"X-Test-User": "bob", "X-Test-Role": "admin"},
        )
        connected = client.post(f"{root}/connect", headers={"X-Test-User": "alice"})
        gateway.opened[0].active = True
        busy = client.post(
            f"{root}/verify-deliver",
            headers={"X-Test-User": "alice"},
        )

    assert foreign.status_code == 404
    assert connected.status_code == 200
    assert busy.status_code == 409
    assert verifier_instances == []


def test_verify_deliver_rejects_an_unlocked_wrong_workspace() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")

    def verifier_factory(sink: Callable[[DevelopmentEvent], Any]) -> _RecordingVerifier:
        return _RecordingVerifier(sink)

    with TestClient(_app(gateway, verifier_factory=verifier_factory)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/"
            "dev-session/verify-deliver",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == (
        "开发工作空间不符合验证要求。"
    )


def test_verify_deliver_streams_events_for_the_owned_fixed_workspace() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    verifier_instances: list[_RecordingVerifier] = []

    def verifier_factory(sink: Callable[[DevelopmentEvent], Any]) -> _RecordingVerifier:
        verifier = _RecordingVerifier(sink)
        verifier_instances.append(verifier)
        return verifier

    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    with TestClient(_app(gateway, verifier_factory=verifier_factory)) as client:
        assert (
            client.post(f"{root}/connect", headers={"X-Test-User": "alice"}).status_code
            == 200
        )
        response = client.post(
            f"{root}/verify-deliver",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert "id: 1" in response.text
    assert "event: verification.stage.started" in response.text
    assert '"stage":"local_compile"' in response.text
    verifier = verifier_instances[0]
    owner, session = verifier.calls[0]
    assert owner == "alice"
    assert session.owner_id == "alice"
    assert session.session_id == "dev-session"
    assert session.endpoint.startswith("https://sandbox.example/")
    assert session.project_root == "/home/gem/workspace/project-1"


def test_verify_deliver_streams_a_safe_error_when_the_verifier_fails() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")

    def verifier_factory(sink: Callable[[DevelopmentEvent], Any]) -> _RecordingVerifier:
        return _RecordingVerifier(sink, error=RuntimeError("secret verifier failure"))

    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    with TestClient(_app(gateway, verifier_factory=verifier_factory)) as client:
        assert client.post(f"{root}/connect", headers={"X-Test-User": "alice"}).is_success
        response = client.post(
            f"{root}/verify-deliver",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert "event: verification.stage.started" in response.text
    assert "event: error" in response.text
    assert "INTELLIGENT_DEVELOPMENT_FAILED" in response.text
    assert "secret verifier failure" not in response.text


@pytest.mark.asyncio
async def test_verify_stream_cancels_a_pending_verifier_after_stream_failure() -> None:
    class _PendingTask:
        def __init__(self, task: asyncio.Task[None]) -> None:
            self.task = task
            self.cancelled = False

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            self.cancelled = True

        def __await__(self) -> Any:
            return self.task.__await__()

    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")

    def verifier_factory(sink: Callable[[DevelopmentEvent], Any]) -> _RecordingVerifier:
        return _RecordingVerifier(sink, error=RuntimeError("verifier failed"))

    app = _app(gateway, verifier_factory=verifier_factory)
    pending: _PendingTask | None = None
    real_create_task = asyncio.create_task

    def create_task(coro: Any) -> _PendingTask:
        nonlocal pending
        pending = _PendingTask(real_create_task(coro))
        return pending

    verify_route = next(
        route
        for route in app.routes
        if getattr(route, "path", "").endswith("/verify-deliver")
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": verify_route.path,
            "headers": [(b"x-test-user", b"alice")],
        }
    )
    with TestClient(app) as client:
        root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
        assert client.post(f"{root}/connect", headers={"X-Test-User": "alice"}).is_success
        response = await verify_route.endpoint("dev-session", request)
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(routes.asyncio, "create_task", create_task)
            chunks = [chunk async for chunk in response.body_iterator]

    assert pending is not None
    assert pending.cancelled is True
    assert "event: error" in "".join(chunks)


def test_verify_deliver_releases_lock_when_the_factory_raises() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    attempts = 0

    def verifier_factory(sink: Callable[[DevelopmentEvent], Any]) -> _RecordingVerifier:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("factory failed")
        return _RecordingVerifier(sink)

    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    app = _app(gateway, verifier_factory=verifier_factory)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post(f"{root}/connect", headers={"X-Test-User": "alice"}).is_success
        failed = client.post(
            f"{root}/verify-deliver",
            headers={"X-Test-User": "alice"},
        )
        replacement = client.post(
            f"{root}/verify-deliver",
            headers={"X-Test-User": "alice"},
        )

    assert failed.status_code == 500
    assert replacement.status_code == 200
    assert "event: verification.stage.started" in replacement.text
    assert attempts == 2


@pytest.mark.asyncio
async def test_verify_deliver_rejects_a_concurrent_run_and_releases_its_guard() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    service = SandboxConversationService(
        routes.IntelligentDevelopmentGateway(gateway),
        tool_id="tool-dev",
        agent_kind=routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    )
    conversation = await service.connect("dev-session", "alice")
    await conversation.codex.update_workspace("/home/gem/workspace/project-1")
    verifier_instances: list[_RecordingVerifier] = []

    def verifier_factory(sink: Callable[[DevelopmentEvent], Any]) -> _RecordingVerifier:
        verifier = _RecordingVerifier(sink, blocking=True)
        verifier_instances.append(verifier)
        return verifier

    app = FastAPI()
    routes.mount_intelligent_development_routes(
        app,
        service,
        lambda _request: "alice",
        lambda _request: "alice",
        verifier_factory,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = asyncio.create_task(
            client.post(
                f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/"
                "dev-session/verify-deliver"
            )
        )
        while not verifier_instances:
            await asyncio.sleep(0)
        await verifier_instances[0].started.wait()
        duplicate = await client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/"
            "dev-session/verify-deliver"
        )
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        await asyncio.wait_for(verifier_instances[0].cancelled.wait(), timeout=1)

        replacement = asyncio.create_task(
            client.post(
                f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/"
                "dev-session/verify-deliver"
            )
        )
        while len(verifier_instances) < 2:
            await asyncio.sleep(0)
        await verifier_instances[1].started.wait()
        replacement.cancel()
        with pytest.raises(asyncio.CancelledError):
            await replacement
        await asyncio.wait_for(verifier_instances[1].cancelled.wait(), timeout=1)

    assert duplicate.status_code == 409
    assert len(verifier_instances) == 2
    await service.close_all()


@pytest.mark.asyncio
async def test_verify_deliver_cancels_verifier_when_client_disconnects() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    service = SandboxConversationService(
        routes.IntelligentDevelopmentGateway(gateway),
        tool_id="tool-dev",
        agent_kind=routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    )
    conversation = await service.connect("dev-session", "alice")
    await conversation.codex.update_workspace("/home/gem/workspace/project-1")
    verifier_instances: list[_RecordingVerifier] = []

    def verifier_factory(sink: Callable[[DevelopmentEvent], Any]) -> _RecordingVerifier:
        verifier = _RecordingVerifier(sink, blocking=True)
        verifier_instances.append(verifier)
        return verifier

    app = FastAPI()
    routes.mount_intelligent_development_routes(
        app,
        service,
        lambda _request: "alice",
        lambda _request: "alice",
        verifier_factory,
    )
    request_sent = False
    disconnected = False
    response_messages: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        nonlocal request_sent, disconnected
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        while not verifier_instances:
            await asyncio.sleep(0)
        await verifier_instances[0].started.wait()
        if not disconnected:
            disconnected = True
            return {"type": "http.disconnect"}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: dict[str, object]) -> None:
        response_messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": (
                f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/"
                "dev-session/verify-deliver"
            ),
            "raw_path": (
                f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/"
                "dev-session/verify-deliver"
            ).encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "root_path": "",
        },
        receive,
        send,
    )

    verifier = verifier_instances[0]
    await asyncio.wait_for(verifier.cancelled.wait(), timeout=1)
    assert verifier.calls
    assert any(
        message.get("type") == "http.response.start" for message in response_messages
    )
    await service.close_all()


def test_gateway_delegates_unmodified_attributes() -> None:
    gateway = _FakeGateway()

    assert routes.IntelligentDevelopmentGateway(gateway).sessions is gateway.sessions


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (SandboxError("generic"), 500),
        (SandboxConfigurationError("configuration"), 503),
        (SandboxValidationError("validation"), 422),
        (SandboxSessionNotFoundError("missing"), 404),
        (SandboxSessionUnavailableError("unavailable"), 409),
        (SandboxCapacityError("capacity"), 409),
        (SandboxProvisioningError("provisioning"), 502),
    ],
)
def test_http_error_maps_each_sandbox_error_contract(
    error: SandboxError,
    status: int,
) -> None:
    response = routes._http_error(error)

    assert response.status_code == status
    assert response.detail == {
        "code": error.code,
        "message": str(error),
        "retryable": error.retryable,
    }


@pytest.mark.parametrize(
    ("body", "expected_message"),
    [
        (b"{" + b" " * (64 * 1024), "请求内容过大。"),
        (b"{broken", "请求不是有效 JSON。"),
        (b"\xff", "请求不是有效 JSON。"),
        (b"[]", "请求必须是 JSON 对象。"),
    ],
    ids=["oversized", "invalid-json", "invalid-utf8", "non-object"],
)
def test_create_rejects_size_invalid_json_and_non_object_bodies(
    body: bytes,
    expected_message: str,
) -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions",
            headers={"X-Test-User": "alice", "Content-Type": "application/json"},
            content=body,
        )

    assert response.status_code == 422
    assert response.json()["detail"]["message"] == expected_message
    assert gateway.created == 0


def test_create_accepts_an_empty_body_as_an_empty_object() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions",
            headers={"X-Test-User": "alice"},
            content=b"",
        )

    assert response.status_code == 200
    assert response.json()["displayName"] == ""


def test_list_translates_service_errors() -> None:
    app = _app(_FakeGateway())
    app.state.test_service.list_sessions = AsyncMock(
        side_effect=SandboxProvisioningError("list failed")
    )
    with TestClient(app) as client:
        response = client.get(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "SANDBOX_PROVISIONING_FAILED"


def test_unconfigured_create_fails_before_body_or_remote_processing() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway, tool_id=None)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions",
            headers={"X-Test-User": "alice"},
            content=b"not-json",
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "管理员未配置 SANDBOX_DEV"
    assert gateway.created == 0


@pytest.mark.parametrize(
    ("status", "endpoint"),
    [("Creating", "https://sandbox.example/dev"), ("Ready", "")],
)
def test_connect_rejects_remote_sessions_that_are_not_ready(
    status: str,
    endpoint: str,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(status=status, endpoint=endpoint)
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 409
    assert gateway.opened == []


@pytest.mark.parametrize(
    ("expire_at", "status", "message"),
    [
        ("not-a-date", 409, "智能开发 Session 过期时间无效。"),
        ("2026-08-14T16:00:00", 404, "智能开发 Session 已过期。"),
        ("2026-08-14T16:00:00Z", 404, "智能开发 Session 已过期。"),
    ],
)
def test_connect_rejects_invalid_or_expired_remote_sessions(
    expire_at: str,
    status: int,
    message: str,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(expire_at=expire_at)
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == status
    assert response.json()["detail"]["message"] == message
    assert gateway.opened == []


def test_connect_accepts_a_missing_expiration_timestamp() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(expire_at="")
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200


def test_connect_translates_workspace_remote_errors() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    _RemoteRecorder.error = SandboxInvocationError("remote failed")
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 500
    assert response.json()["detail"]["message"] == "remote failed"
    assert len(_RemoteRecorder.calls) == 1


def test_connect_accepts_a_locked_codex_in_the_fixed_workspace() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(user_session_id="project-1")
    gateway.codex_factory = lambda: _FakeCodex(
        cwd="/home/gem/workspace/project-1",
        locked=True,
    )
    with TestClient(_app(gateway)) as client:
        response = client.post(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session/connect",
            headers={"X-Test-User": "alice"},
        )

    assert response.status_code == 200
    assert response.json()["workspaceLocked"] is True
    assert _RemoteRecorder.calls == []


@pytest.mark.asyncio
async def test_surface_adapter_rejects_skills_and_malformed_session_paths() -> None:
    adapter = routes._SandboxSurfaceAdapter(
        FastAPI(),
        SimpleNamespace(),
        lambda _request: "alice",
    )

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: dict[str, object]) -> None:
        raise AssertionError("rejected requests must not reach the delegated app")

    for path in (
        "/sessions/dev-session/skills",
        "/not-sessions/dev-session/settings",
        "/sessions",
    ):
        with pytest.raises(HTTPException) as captured:
            await adapter({"type": "http", "path": path}, receive, send)
        assert captured.value.status_code == 404


@pytest.mark.asyncio
async def test_surface_adapter_rejects_allowed_suffix_without_session_segment() -> None:
    adapter = routes._SandboxSurfaceAdapter(
        FastAPI(),
        SimpleNamespace(),
        lambda _request: "alice",
    )

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: dict[str, object]) -> None:
        raise AssertionError("malformed requests must not reach the delegated app")

    with pytest.raises(HTTPException) as captured:
        await adapter(
            {"type": "http", "path": "/disconnect", "headers": []},
            receive,
            send,
        )

    assert captured.value.status_code == 404


@pytest.mark.asyncio
async def test_surface_adapter_enforces_owner_and_rewrites_delegated_paths() -> None:
    cloud = _cloud(user_session_id="project-1")
    service = SimpleNamespace(_cloud_session=AsyncMock(return_value=cloud))
    calls: list[dict[str, object]] = []

    async def delegated(
        scope: dict[str, object],
        _receive: Callable[[], Any],
        _send: Callable[[dict[str, Any]], Any],
    ) -> None:
        calls.append(scope)

    adapter = routes._SandboxSurfaceAdapter(
        delegated,
        service,
        lambda _request: "alice",
    )

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: dict[str, object]) -> None:
        return None

    await adapter(
        {
            "type": "http",
            "path": "/sessions/dev-session/disconnect",
            "raw_path": b"/sessions/dev-session/disconnect",
            "headers": [],
        },
        receive,
        send,
    )
    await adapter(
        {
            "type": "http",
            "path": "/sessions/dev-session/approvals/approval-1",
            "raw_path": "not-bytes",
            "headers": [],
        },
        receive,
        send,
    )

    assert calls[0]["path"] == "/web/sandbox/sessions/dev-session/disconnect"
    assert calls[0]["raw_path"] == b"/web/sandbox/sessions/dev-session/disconnect"
    assert calls[1]["path"] == "/web/sandbox/sessions/dev-session/approvals/approval-1"
    assert calls[1]["raw_path"] == "not-bytes"

    service._cloud_session.side_effect = SandboxSessionNotFoundError("hidden")
    with pytest.raises(HTTPException) as captured:
        await adapter(
            {
                "type": "http",
                "path": "/sessions/dev-session/disconnect",
                "headers": [],
            },
            receive,
            send,
        )
    assert captured.value.status_code == 404
    assert calls == [
        {
            "type": "http",
            "path": "/web/sandbox/sessions/dev-session/disconnect",
            "raw_path": b"/web/sandbox/sessions/dev-session/disconnect",
            "headers": [],
        },
        {
            "type": "http",
            "path": "/web/sandbox/sessions/dev-session/approvals/approval-1",
            "raw_path": "not-bytes",
            "headers": [],
        },
    ]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"{}", "智能开发会话只接受文本消息。"),
        (b'{"message":"   "}', "message must not be empty"),
        (b'{"message":"' + b"x" * 100_001 + b'"}', "message is too large"),
        (b"x" * (128 * 1024 + 1), "请求内容过大。"),
    ],
    ids=["wrong-shape", "blank", "message-limit", "body-limit"],
)
def test_message_rejects_shape_content_and_size_boundaries(
    body: bytes,
    message: str,
) -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    with TestClient(_app(gateway)) as client:
        assert client.post(f"{root}/connect", headers={"X-Test-User": "alice"}).is_success
        response = client.post(
            f"{root}/messages",
            headers={"X-Test-User": "alice", "Content-Type": "application/json"},
            content=body,
        )

    assert response.status_code == 422
    assert response.json()["detail"]["message"] == message
    assert gateway.opened[0].prompts == []


def test_message_stream_serializes_every_event_type_and_optional_usage_field() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    events = [
        CodexAppServerEvent(kind="text", text="hello"),
        CodexAppServerEvent(
            kind="approval",
            approval=CodexApproval(
                id="approval-1",
                kind="command",
                method="exec",
                reason="confirm",
            )
        ),
        CodexAppServerEvent(
            kind="approval_resolved",
            approval_resolved_id="approval-1",
        ),
        CodexAppServerEvent(
            kind="usage",
            turn_id="turn-1",
            usage=CodexTokenUsage(total_tokens=3),
            thread_total=CodexTokenUsage(total_tokens=5),
            model_context_window=100,
        ),
        CodexAppServerEvent(
            kind="usage",
            turn_id="turn-2",
            usage=CodexTokenUsage(total_tokens=7),
        ),
        CodexAppServerEvent(
            kind="command",
            item_id="item-1",
            status="running",
            name="shell",
            arguments={"cmd": "pwd"},
            response={"ok": True},
        ),
    ]
    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    with TestClient(_app(gateway)) as client:
        assert client.post(f"{root}/connect", headers={"X-Test-User": "alice"}).is_success
        gateway.opened[0].events = events
        response = client.post(
            f"{root}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "go"},
        )

    assert response.status_code == 200
    assert "event: delta" in response.text
    assert '"text": "hello"' in response.text
    assert "event: approval" in response.text
    assert '"id": "approval-1"' in response.text
    assert "event: approval_resolved" in response.text
    assert '"approvalId": "approval-1"' in response.text
    assert response.text.count("event: usage") == 2
    assert '"threadTotal": {"totalTokens": 5' in response.text
    assert '"modelContextWindow": 100' in response.text
    turn_two = response.text.split('"turnId": "turn-2"', 1)[1].split("\n\n", 1)[0]
    assert "threadTotal" not in turn_two
    assert "modelContextWindow" not in turn_two
    assert "event: activity" in response.text
    assert '"text": null' in response.text
    assert '"name": "shell"' in response.text
    assert response.text.endswith("event: done\ndata: {}\n\n")


@pytest.mark.asyncio
async def test_cleanup_loop_runs_and_shutdown_covers_both_lifecycle_branches() -> None:
    cleanup_ran = asyncio.Event()
    continue_cleanup = asyncio.Event()

    async def stale_cleanup_run() -> None:
        cleanup_ran.set()
        await continue_cleanup.wait()

    stale_cleanup = AsyncMock(side_effect=stale_cleanup_run)
    gateway = _FakeGateway()
    app = FastAPI()
    service = SandboxConversationService(
        routes.IntelligentDevelopmentGateway(gateway),
        tool_id="tool-dev",
        agent_kind=routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    )
    app.state.test_service = service
    routes.mount_intelligent_development_routes(
        app,
        service,
        lambda _request: "alice",
        lambda _request: "alice",
        cleanup_stale_runtimes=stale_cleanup,
    )
    service.close_all = AsyncMock()

    async def cleanup_expired() -> None:
        return None

    service.cleanup_expired = cleanup_expired

    async def sleep(_seconds: int) -> None:
        return None

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(routes.asyncio, "sleep", sleep)
        await app.router.on_startup[0]()
        await asyncio.wait_for(cleanup_ran.wait(), timeout=1)
        await app.router.on_shutdown[0]()

    service.close_all.assert_awaited_once()
    assert stale_cleanup.await_count >= 1

    async def sync_cleanup() -> None:
        return None

    sync_app = FastAPI()
    sync_service = SandboxConversationService(
        routes.IntelligentDevelopmentGateway(_FakeGateway()),
        tool_id="tool-dev",
        agent_kind=routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    )
    sync_service.cleanup_expired = AsyncMock()
    sync_service.close_all = AsyncMock()
    routes.mount_intelligent_development_routes(
        sync_app,
        sync_service,
        lambda _request: "alice",
        lambda _request: "alice",
        cleanup_stale_runtimes=lambda: None,
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        calls = 0

        async def one_cycle(_seconds: int) -> None:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise asyncio.CancelledError

        monkeypatch.setattr(routes.asyncio, "sleep", one_cycle)
        await sync_app.router.on_startup[0]()
        await asyncio.sleep(0)
        await sync_app.router.on_shutdown[0]()

    failing_app = FastAPI()
    failing_service = SandboxConversationService(
        routes.IntelligentDevelopmentGateway(_FakeGateway()),
        tool_id="tool-dev",
        agent_kind=routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    )
    failing_service.cleanup_expired = AsyncMock()
    failing_service.close_all = AsyncMock()
    attempts = 0
    failing_cleanup_ran = asyncio.Event()

    async def failing_cleanup() -> None:
        nonlocal attempts
        attempts += 1
        failing_cleanup_ran.set()
        raise RuntimeError("retry")

    routes.mount_intelligent_development_routes(
        failing_app,
        failing_service,
        lambda _request: "alice",
        lambda _request: "alice",
        cleanup_stale_runtimes=failing_cleanup,
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        sleeps = 0

        async def retry_cycle(_seconds: int) -> None:
            nonlocal sleeps
            sleeps += 1
            if sleeps > 2:
                raise asyncio.CancelledError

        monkeypatch.setattr(routes.asyncio, "sleep", retry_cycle)
        await failing_app.router.on_startup[0]()
        await asyncio.wait_for(failing_cleanup_ran.wait(), timeout=1)
        await failing_app.router.on_shutdown[0]()
    assert attempts >= 1

    no_callback_app = FastAPI()
    no_callback_service = SandboxConversationService(
        routes.IntelligentDevelopmentGateway(_FakeGateway()),
        tool_id="tool-dev",
        agent_kind=routes.INTELLIGENT_DEVELOPMENT_AGENT_KIND,
    )
    no_callback_ran = asyncio.Event()

    async def no_callback_cleanup() -> None:
        no_callback_ran.set()
        await asyncio.Event().wait()

    no_callback_service.cleanup_expired = no_callback_cleanup
    no_callback_service.close_all = AsyncMock()
    routes.mount_intelligent_development_routes(
        no_callback_app,
        no_callback_service,
        lambda _request: "alice",
        lambda _request: "alice",
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(routes.asyncio, "sleep", AsyncMock(return_value=None))
        await no_callback_app.router.on_startup[0]()
        await asyncio.wait_for(no_callback_ran.wait(), timeout=1)
        await no_callback_app.router.on_shutdown[0]()

    no_start = _app(_FakeGateway())
    no_start.state.test_service.close_all = AsyncMock()
    await no_start.router.on_shutdown[0]()
    no_start.state.test_service.close_all.assert_awaited_once()


def test_message_stream_translates_sandbox_errors_after_sse_starts() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud()
    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    with TestClient(_app(gateway)) as client:
        assert client.post(f"{root}/connect", headers={"X-Test-User": "alice"}).is_success
        gateway.opened[0].stream_error = CodexAppServerError("turn failed")
        response = client.post(
            f"{root}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "go"},
        )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "SANDBOX_INVOCATION_FAILED" in response.text
    assert "turn failed" in response.text
    assert response.text.endswith('event: done\ndata: {"reason":"failed"}\n\n')


def test_release_summary_returns_only_trusted_server_metadata_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()
    captured: dict[str, object] = {}
    destination = Path("/tmp/intelligent-summary-test")

    async def materialize(
        requested_destination: Path,
        source: dict[str, object],
        *,
        owner_id: str,
        service: SandboxConversationService,
    ) -> SimpleNamespace:
        captured.update(
            destination=requested_destination,
            source=source,
            owner_id=owner_id,
            service=service,
        )
        return SimpleNamespace(
            artifact_sha256="a" * 64,
            validation_report_sha256="b" * 64,
            agent_name="trusted-agent",
            entry_point="app.py",
            file_count=3,
            artifact_size=123,
            validated_at="2026-08-15T00:00:00+00:00",
            gate_summary=("compile", "service-contract"),
        )

    removed: list[tuple[Path, bool]] = []
    monkeypatch.setattr("tempfile.mkdtemp", lambda **_kwargs: str(destination))
    monkeypatch.setattr(source_module, "materialize_intelligent_development_source", materialize)
    monkeypatch.setattr("shutil.rmtree", lambda path, ignore_errors: removed.append((path, ignore_errors)))

    app = _app(gateway)
    with TestClient(app) as client:
        response = client.get(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/releases/summary",
            headers={"X-Test-User": "alice"},
            params={
                "sessionId": "dev-session",
                "artifactSha256": "request-artifact",
                "validationReportSha256": "request-report",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "sessionId": "dev-session",
        "artifactSha256": "a" * 64,
        "validationReportSha256": "b" * 64,
        "agentName": "trusted-agent",
        "entryPoint": "app.py",
        "fileCount": 3,
        "artifactSize": 123,
        "validatedAt": "2026-08-15T00:00:00+00:00",
        "gateSummary": ["compile", "service-contract"],
    }
    assert captured == {
        "destination": destination,
        "source": {
            "kind": "intelligentDevelopment",
            "sessionId": "dev-session",
            "artifactSha256": "request-artifact",
            "validationReportSha256": "request-report",
        },
        "owner_id": "alice",
        "service": app.state.test_service,
    }
    assert removed == [(destination, True)]


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (DeploymentSourceError("untrusted release"), 409, "untrusted release"),
        (SandboxSessionNotFoundError("hidden"), 404, "hidden"),
        (SandboxSessionUnavailableError("not ready"), 409, "not ready"),
        (RuntimeError("secret"), 502, "无法校验已验证交付物。"),
    ],
    ids=("deployment-source", "not-found", "unavailable", "unexpected"),
)
def test_release_summary_translates_failures_and_always_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: int,
    detail: str,
) -> None:
    destination = Path("/tmp/intelligent-summary-test")

    async def materialize(*_args: object, **_kwargs: object) -> None:
        raise error

    removed: list[tuple[Path, bool]] = []
    monkeypatch.setattr("tempfile.mkdtemp", lambda **_kwargs: str(destination))
    monkeypatch.setattr(source_module, "materialize_intelligent_development_source", materialize)
    monkeypatch.setattr("shutil.rmtree", lambda path, ignore_errors: removed.append((path, ignore_errors)))

    with TestClient(_app(_FakeGateway())) as client:
        response = client.get(
            f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/releases/summary",
            headers={"X-Test-User": "alice"},
            params={
                "sessionId": "dev-session",
                "artifactSha256": "a" * 64,
                "validationReportSha256": "b" * 64,
            },
        )

    assert response.status_code == status
    if isinstance(response.json()["detail"], dict):
        assert response.json()["detail"]["message"] == detail
    else:
        assert response.json()["detail"] == detail
    assert removed == [(destination, True)]


def test_status_and_model_routes_are_owner_scoped() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(owner="alice")
    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    with TestClient(_app(gateway)) as client:
        assert client.post(f"{root}/connect", headers={"X-Test-User": "alice"}).is_success
        status = client.get(f"{root}/status", headers={"X-Test-User": "alice"})
        models = client.get(f"{root}/models", headers={"X-Test-User": "alice"})
        changed = client.put(
            f"{root}/model",
            headers={"X-Test-User": "alice"},
            json={"model": "model-1"},
        )
        invalid = client.put(
            f"{root}/model",
            headers={"X-Test-User": "alice"},
            json={"model": 1},
        )
        foreign = client.get(f"{root}/status", headers={"X-Test-User": "bob"})
        foreign_models = client.get(f"{root}/models", headers={"X-Test-User": "bob"})
    assert status.status_code == 200
    assert models.json()["models"][0]["id"] == "model-1"
    assert changed.json() == {"model": "model-1"}
    assert invalid.status_code == 422
    assert foreign.status_code == 404
    assert foreign_models.status_code == 404


def test_interrupt_is_owner_scoped_and_translates_resolution_errors() -> None:
    gateway = _FakeGateway()
    gateway.sessions["dev-session"] = _cloud(owner="alice")
    root = f"{routes.INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/dev-session"
    with TestClient(_app(gateway)) as client:
        assert client.post(f"{root}/connect", headers={"X-Test-User": "alice"}).is_success
        gateway.opened[0].active = True
        interrupted = client.post(f"{root}/interrupt", headers={"X-Test-User": "alice"})
        foreign = client.post(f"{root}/interrupt", headers={"X-Test-User": "bob"})

    assert interrupted.status_code == 200
    assert interrupted.json() == {"interrupted": True}
    assert gateway.opened[0].active is False
    assert foreign.status_code == 404
