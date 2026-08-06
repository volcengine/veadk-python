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

"""Tests for Studio's reusable AgentKit Sandbox Sessions."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from veadk.cli.codex_app_server import (
    CodexAppServerError,
    CodexAppServerEvent,
    CodexDirectoryEntry,
    CodexDirectoryListing,
    CodexModel,
    CodexPermissionSettings,
    CodexSkill,
    CodexThreadMessage,
    CodexThreadSnapshot,
    CodexThreadSummary,
    CodexTokenUsage,
)
from veadk.cli.frontend_sandbox import (
    STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH,
    AgentkitSandboxGateway,
    SandboxAgentSessionService,
    SandboxCloudSession,
    SandboxCloudSnapshot,
    SandboxConfigurationError,
    SandboxConversationService,
    SandboxProvisioningError,
    SandboxSessionNotFoundError,
    _build_studio_user_session_id,
    mount_sandbox_agent_routes,
    mount_sandbox_routes,
)


class _FakeCodex:
    def __init__(self, turns: list[str], *, fail: bool = False) -> None:
        self.thread_id = "thread-1"
        self.cwd = "/workspace"
        self.model = "gpt-test"
        self.permissions = CodexPermissionSettings()
        self.thread_token_total: CodexTokenUsage | None = None
        self.model_context_window: int | None = None
        self.workspace_locked = False
        self.active = False
        self.closed = False
        self.turns = turns
        self.fail = fail
        self.approvals: list[tuple[str, str]] = []
        self.selected_skill_ids: tuple[str, ...] = ()

    async def stream_turn(
        self, prompt: str, skill_ids: tuple[str, ...] = ()
    ) -> AsyncIterator[CodexAppServerEvent]:
        self.active = True
        self.workspace_locked = True
        self.turns.append(self.thread_id)
        self.selected_skill_ids = skill_ids
        try:
            if self.fail:
                raise CodexAppServerError("failed")
            yield CodexAppServerEvent(
                kind="thinking",
                item_id="reasoning-1",
                status="done",
                text="分析请求",
            )
            yield CodexAppServerEvent(
                kind="tool",
                item_id="command-1",
                status="done",
                name="运行命令",
                arguments={"command": "pwd"},
                response={"exitCode": 0, "output": "/home/gem"},
            )
            yield CodexAppServerEvent(
                kind="text",
                text=(
                    "https://sandbox.example/path?Authorization=secret"
                    if prompt == "show private endpoint"
                    else f"reply:{prompt}"
                ),
            )
            if prompt == "tokens":
                usage = CodexTokenUsage(
                    total_tokens=42,
                    input_tokens=30,
                    cached_input_tokens=10,
                    output_tokens=12,
                    reasoning_output_tokens=3,
                )
                self.thread_token_total = CodexTokenUsage(total_tokens=142)
                self.model_context_window = 200_000
                yield CodexAppServerEvent(
                    kind="usage",
                    turn_id="turn-usage",
                    usage=usage,
                    thread_total=self.thread_token_total,
                    model_context_window=self.model_context_window,
                )
        finally:
            self.active = False

    async def list_models(self) -> tuple[CodexModel, ...]:
        return (
            CodexModel(
                id="gpt-test",
                display_name="GPT Test",
                description="Test model",
                is_default=True,
            ),
        )

    async def set_model(self, model: str) -> str:
        self.model = model
        return model

    async def list_skills(self, force_reload: bool = False) -> tuple[CodexSkill, ...]:
        del force_reload
        return (
            CodexSkill(
                id="skill-public-id",
                name="review",
                description="Review code",
            ),
        )

    def _snapshot(self, thread_id: str) -> CodexThreadSnapshot:
        self.thread_id = thread_id
        self.workspace_locked = True
        return CodexThreadSnapshot(
            thread=CodexThreadSummary(
                id=thread_id,
                preview="restored",
                cwd=self.cwd,
                updated_at=20,
            ),
            messages=(
                CodexThreadMessage(
                    id="message-user",
                    role="user",
                    content="restored",
                    timestamp=20_000,
                    skill_names=("review",),
                ),
                CodexThreadMessage(
                    id="message-assistant",
                    role="assistant",
                    content="done",
                    timestamp=20_001,
                ),
            ),
            model=self.model,
            cwd=self.cwd,
            workspace_locked=True,
        )

    async def new_thread(self) -> CodexThreadSnapshot:
        self.workspace_locked = False
        snapshot = self._snapshot("thread-new")
        self.workspace_locked = False
        return CodexThreadSnapshot(
            thread=snapshot.thread,
            messages=(),
            model=self.model,
            cwd=self.cwd,
            workspace_locked=False,
        )

    async def list_threads(
        self,
        *,
        cursor: str = "",
        search_term: str = "",
        archived: bool = False,
    ) -> tuple[tuple[CodexThreadSummary, ...], str]:
        del cursor, search_term, archived
        return (
            (
                CodexThreadSummary(
                    id="thread-old",
                    preview="old work",
                    cwd=self.cwd,
                    updated_at=20,
                ),
            ),
            "",
        )

    async def resume_thread(self, thread_id: str) -> CodexThreadSnapshot:
        return self._snapshot(thread_id)

    async def fork_thread(self) -> CodexThreadSnapshot:
        return self._snapshot("thread-fork")

    async def archive_thread(self, thread_id: str) -> CodexThreadSnapshot | None:
        if thread_id != self.thread_id:
            return None
        return await self.new_thread()

    async def compact_thread(self) -> None:
        return None

    async def update_permissions(
        self, settings: CodexPermissionSettings
    ) -> CodexPermissionSettings:
        self.permissions = settings
        return settings

    async def apply_session_permissions(
        self, settings: CodexPermissionSettings
    ) -> None:
        self.permissions = settings

    async def update_workspace(self, cwd: str) -> str:
        if self.workspace_locked:
            raise CodexAppServerError("workspace locked")
        self.cwd = cwd
        return cwd

    async def list_directories(self, path: str) -> CodexDirectoryListing:
        return CodexDirectoryListing(
            path=path,
            parent="/" if path != "/" else None,
            directories=(
                CodexDirectoryEntry(name="project", path=f"{path.rstrip('/')}/project"),
            ),
        )

    def resolve_approval(self, approval_id: str, decision: str) -> None:
        self.approvals.append((approval_id, decision))

    async def close(self) -> None:
        self.closed = True


class _FakeGateway:
    def __init__(self) -> None:
        self.created = 0
        self.tool_ids: list[str] = []
        self.display_names: list[str] = []
        self.usernames: list[str | None] = []
        self.creator_names: list[str] = []
        self.deleted: list[SandboxCloudSession] = []
        self.deleted_snapshots: list[SandboxCloudSnapshot] = []
        self.thread_ids: list[str] = []
        self.connections: list[_FakeCodex] = []
        self.sessions: dict[str, SandboxCloudSession] = {
            "remote-existing": SandboxCloudSession(
                tool_id="tool-studio",
                instance_id="remote-existing",
                user_session_id="existing-agent",
                endpoint="https://sandbox.example/existing?Authorization=secret",
                region="cn-beijing",
                status="Ready",
                created_at="2026-07-30T08:00:00Z",
                expire_at="2026-07-30T16:00:00Z",
                tool_type="CodeEnv",
                created_by="alice",
            )
        }
        self.snapshots: dict[str, SandboxCloudSnapshot] = {}

    async def list_sessions(
        self, tool_id: str, username: str | None = None
    ) -> list[SandboxCloudSession]:
        self.tool_ids.append(tool_id)
        self.usernames.append(username)
        return [
            session
            for session in self.sessions.values()
            if session.tool_id == tool_id
            and (username is None or session.created_by == username)
        ]

    async def get_session(self, tool_id: str, session_id: str) -> SandboxCloudSession:
        self.tool_ids.append(tool_id)
        session = self.sessions.get(session_id)
        if session is None or session.tool_id != tool_id:
            raise SandboxSessionNotFoundError("AgentKit Session 不存在或已过期。")
        return session

    async def list_snapshots(
        self, tool_id: str, username: str | None = None
    ) -> list[SandboxCloudSnapshot]:
        self.tool_ids.append(tool_id)
        return [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.tool_id == tool_id
            and (username is None or snapshot.created_by == username)
        ]

    async def create_session(
        self,
        tool_id: str,
        display_name: str = "",
        username: str = "",
        creator_name: str = "",
    ) -> SandboxCloudSession:
        self.created += 1
        self.tool_ids.append(tool_id)
        self.display_names.append(display_name)
        self.creator_names.append(creator_name)
        session = SandboxCloudSession(
            tool_id=tool_id,
            instance_id=f"remote-{self.created}",
            user_session_id=f"user-{self.created}",
            endpoint="https://sandbox.example/path?Authorization=secret",
            region="cn-beijing",
            status="Ready",
            created_at="2026-07-30T09:00:00Z",
            expire_at="2026-07-30T17:00:00Z",
            tool_type="CodeEnv",
            display_name=display_name,
            created_by=username,
            creator_name=creator_name,
        )
        self.sessions[session.instance_id] = session
        return session

    async def delete_session(self, session: SandboxCloudSession) -> None:
        self.deleted.append(session)
        self.sessions.pop(session.instance_id, None)

    async def resume_snapshot(
        self, snapshot: SandboxCloudSnapshot
    ) -> SandboxCloudSession:
        session = SandboxCloudSession(
            tool_id=snapshot.tool_id,
            instance_id=f"resumed-{snapshot.snapshot_id}",
            user_session_id=snapshot.user_session_id,
            endpoint="https://sandbox.example/resumed?Authorization=secret",
            region=snapshot.region,
            status="Ready",
            created_at="2026-08-06T10:00:00Z",
            expire_at="2026-08-06T18:00:00Z",
            tool_type="CodeEnv",
            display_name=snapshot.display_name,
            created_by=snapshot.created_by,
        )
        self.sessions[session.instance_id] = session
        return session

    async def delete_snapshot(self, snapshot: SandboxCloudSnapshot) -> None:
        self.deleted_snapshots.append(snapshot)
        self.snapshots.pop(snapshot.snapshot_id, None)

    async def open_codex(self, session: SandboxCloudSession) -> _FakeCodex:
        del session
        connection = _FakeCodex(self.thread_ids)
        self.connections.append(connection)
        return connection

    async def drain(self) -> None:
        return None


@pytest.mark.parametrize(
    "owner_id",
    ["hanzhi", "alice@example.com", "张三", "user_name-with-dashes"],
)
def test_studio_user_session_id_only_uses_agentkit_safe_characters(
    owner_id: str,
) -> None:
    user_session_id = _build_studio_user_session_id(owner_id)

    assert re.fullmatch(r"studio-[A-Za-z0-9_-]+-[0-9a-f]{32}", user_session_id)
    assert len(user_session_id) <= 200


def test_studio_user_session_id_owner_encoding_avoids_escape_collisions() -> None:
    escaped_prefix = _build_studio_user_session_id("/").rsplit("-", 1)[0]
    literal_prefix = _build_studio_user_session_id("_2F").rsplit("-", 1)[0]
    dashed_owner = _build_studio_user_session_id("alice-bob").split("-", 2)[1]

    assert escaped_prefix != literal_prefix
    assert "-" not in dashed_owner
    assert _build_studio_user_session_id("user_name").startswith("studio-user_name-")


def _app(
    gateway: _FakeGateway,
    tool_id: str | None = "tool-studio",
    snapshot_tool_id: str | None = None,
) -> FastAPI:
    app = FastAPI()
    service = SandboxConversationService(
        gateway,
        tool_id=tool_id,
        snapshot_tool_id=snapshot_tool_id,
    )

    def _owner(request: Request) -> str:
        owner = request.headers.get("X-Test-User", "")
        if not owner:
            raise HTTPException(status_code=401, detail="identity required")
        return owner

    def _admin(request: Request) -> bool:
        return request.headers.get("X-Test-Role") == "admin"

    def _creator(request: Request) -> str:
        return request.headers.get("X-Test-Creator") or _owner(request)

    mount_sandbox_routes(
        app,
        service,
        _owner,
        admin_resolver=_admin,
        creator_resolver=_creator,
    )
    return app


def _agent_app(gateway: _FakeGateway, *, dual_tools: bool = False) -> FastAPI:
    app = FastAPI()

    def _owner(request: Request) -> str:
        owner = request.headers.get("X-Test-User", "")
        if not owner:
            raise HTTPException(status_code=401, detail="identity required")
        return owner

    def _admin(request: Request) -> bool:
        return request.headers.get("X-Test-Role") == "admin"

    def _creator(request: Request) -> str:
        return request.headers.get("X-Test-Creator") or _owner(request)

    mount_sandbox_agent_routes(
        app,
        {
            "openclaw": SandboxAgentSessionService(
                gateway,
                kind="openclaw",
                tool_id="tool-openclaw",
                snapshot_tool_id=("tool-openclaw-snapshot" if dual_tools else None),
            ),
            "hermes": SandboxAgentSessionService(
                gateway,
                kind="hermes",
                tool_id="tool-hermes",
                snapshot_tool_id="tool-hermes-snapshot" if dual_tools else None,
            ),
        },
        _owner,
        _admin,
        _creator,
    )
    return app


@pytest.mark.parametrize(
    ("kind", "tool_id"),
    [("openclaw", "tool-openclaw"), ("hermes", "tool-hermes")],
)
def test_managed_agent_routes_create_session_and_return_card_data(
    kind: str,
    tool_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _FakeGateway()

    async def _terminal_url(
        endpoint: str,
        session_id: str,
        *,
        direct: bool = False,
    ) -> tuple[str, str]:
        assert "Authorization=secret" in endpoint
        assert direct is True
        return (
            (
                "https://sandbox.example/terminal"
                "?session_id=shell-1&Authorization=terminal-secret"
            ),
            "shell-1",
        )

    monkeypatch.setattr(
        "veadk.cli.frontend_sandbox.terminal_launch_url",
        _terminal_url,
    )
    with TestClient(_agent_app(gateway)) as client:
        created = client.post(
            f"/web/{kind}/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": f"我的 {kind}"},
        )
        listed = client.get(
            f"/web/{kind}/sessions",
            headers={"X-Test-User": "alice"},
        )
        session_id = created.json()["sessionId"]
        opened = client.post(
            f"/web/{kind}/sessions/{session_id}/open",
            headers={"X-Test-User": "alice"},
        )
        terminal = client.post(
            f"/web/{kind}/sessions/{session_id}/terminal",
            headers={"X-Test-User": "alice"},
        )
        deleted = client.delete(
            f"/web/{kind}/sessions/{session_id}",
            headers={"X-Test-User": "alice"},
        )
        listed_after_delete = client.get(
            f"/web/{kind}/sessions",
            headers={"X-Test-User": "alice"},
        )

    assert created.status_code == 200
    assert created.json()["toolName"] == kind
    assert created.json()["displayName"] == f"我的 {kind}"
    assert "endpoint" not in created.json()
    assert gateway.tool_ids == [tool_id] * 7
    assert listed.status_code == 200
    assert [item["sessionId"] for item in listed.json()["sessions"]] == [
        created.json()["sessionId"]
    ]
    assert opened.status_code == 200
    assert opened.json()["webuiUrl"].startswith(
        f"/web/{kind}/sessions/{session_id}/surface/"
    )
    assert "Authorization" not in opened.text
    assert "secret" not in opened.text
    assert terminal.status_code == 200
    assert terminal.json()["shellSessionId"] == "shell-1"
    assert terminal.json()["url"].startswith("https://sandbox.example/terminal?")
    assert "Authorization=terminal-secret" in terminal.json()["url"]
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert listed_after_delete.json() == {"sessions": []}
    assert [session.instance_id for session in gateway.deleted] == [session_id]


@pytest.mark.parametrize(
    ("kind", "temporary_tool_id", "snapshot_tool_id"),
    [
        ("sandbox", "tool-studio", "tool-studio-snapshot"),
        ("openclaw", "tool-openclaw", "tool-openclaw-snapshot"),
        ("hermes", "tool-hermes", "tool-hermes-snapshot"),
    ],
)
def test_sandbox_create_routes_select_tool_by_retention_mode(
    kind: str,
    temporary_tool_id: str,
    snapshot_tool_id: str,
) -> None:
    gateway = _FakeGateway()
    gateway.snapshots["snapshot-temporary-tool"] = SandboxCloudSnapshot(
        tool_id=temporary_tool_id,
        snapshot_id="snapshot-temporary-tool",
        session_id="expired-temporary",
        user_session_id="studio-alice-temporary",
        created_by="alice",
    )
    gateway.snapshots["snapshot-recoverable-tool"] = SandboxCloudSnapshot(
        tool_id=snapshot_tool_id,
        snapshot_id="snapshot-recoverable-tool",
        session_id="expired-recoverable",
        user_session_id="studio-alice-recoverable",
        created_by="alice",
    )
    app = (
        _app(gateway, temporary_tool_id, snapshot_tool_id)
        if kind == "sandbox"
        else _agent_app(gateway, dual_tools=True)
    )
    root = "/web/sandbox" if kind == "sandbox" else f"/web/{kind}"
    headers = {"X-Test-User": "alice"}

    with TestClient(app) as client:
        capabilities = client.get(f"{root}/capabilities", headers=headers)
        temporary = client.post(
            f"{root}/sessions",
            headers=headers,
            json={"displayName": "临时", "retentionMode": "temporary"},
        )
        recoverable = client.post(
            f"{root}/sessions",
            headers=headers,
            json={"displayName": "可恢复", "retentionMode": "recoverable"},
        )
        invalid = client.post(
            f"{root}/sessions",
            headers=headers,
            json={"displayName": "无效", "retentionMode": "forever"},
        )
        created_tool_ids = gateway.tool_ids[-2:]
        listed = client.get(f"{root}/sessions", headers=headers)

    assert capabilities.status_code == 200
    assert capabilities.json()["retentionModes"] == {
        "temporary": {"enabled": True, "reason": ""},
        "recoverable": {"enabled": True, "reason": ""},
    }
    assert temporary.status_code == 200
    assert recoverable.status_code == 200
    assert invalid.status_code == 422
    assert created_tool_ids == [temporary_tool_id, snapshot_tool_id]
    assert {item["displayName"] for item in listed.json()["sessions"]} >= {
        "临时",
        "可恢复",
    }
    assert [item["snapshotId"] for item in listed.json()["snapshots"]] == [
        "snapshot-recoverable-tool"
    ]


@pytest.mark.parametrize(
    ("kind", "tool_id"),
    [("sandbox", "tool-studio"), ("openclaw", "tool-openclaw")],
)
def test_sandbox_snapshot_is_wakeable_and_resumes_to_a_ready_session(
    kind: str,
    tool_id: str,
) -> None:
    gateway = _FakeGateway()
    gateway.snapshots["snapshot-1"] = SandboxCloudSnapshot(
        tool_id=tool_id,
        snapshot_id="snapshot-1",
        session_id="expired-1",
        user_session_id="studio2-owner-random-name",
        region="cn-beijing",
        status="Ready",
        reason="Expired",
        created_at="2026-08-06T09:00:00Z",
        display_name="可恢复智能体",
        created_by="alice",
    )
    gateway.snapshots["snapshot-older"] = SandboxCloudSnapshot(
        tool_id=tool_id,
        snapshot_id="snapshot-older",
        session_id="expired-older",
        user_session_id="studio2-owner-random-name",
        region="cn-beijing",
        status="Ready",
        reason="Expired",
        created_at="2026-08-05T09:00:00Z",
        display_name="更早的快照",
        created_by="alice",
    )
    app = _app(gateway) if kind == "sandbox" else _agent_app(gateway)
    root = f"/web/{kind}"
    headers = {"X-Test-User": "alice"}
    with TestClient(app) as client:
        listed = client.get(f"{root}/sessions", headers=headers)
        # A Session can become active after the list response but before the
        # user clicks wake. Authorization must use the owned raw snapshot list,
        # not the presentation list that now hides this snapshot.
        gateway.sessions["already-running"] = SandboxCloudSession(
            tool_id=tool_id,
            instance_id="already-running",
            user_session_id="studio2-owner-random-name",
            endpoint="https://sandbox.example/already-running",
            status="Ready",
            display_name="可恢复智能体",
            created_by="alice",
        )
        resumed = client.post(
            f"{root}/snapshots/snapshot-1/resume",
            headers=headers,
        )
        listed_after_resume = client.get(f"{root}/sessions", headers=headers)

    assert listed.status_code == 200
    assert listed.json()["snapshots"] == [
        {
            "snapshotId": "snapshot-1",
            "sessionId": "expired-1",
            "userSessionId": "studio2-owner-random-name",
            "status": "Wakeable",
            "snapshotStatus": "Ready",
            "reason": "Expired",
            "createdAt": "2026-08-06T09:00:00Z",
            "createdBy": "alice",
            "displayName": "可恢复智能体",
            "toolName": "veadk-studio-codex" if kind == "sandbox" else kind,
        },
        {
            "snapshotId": "snapshot-older",
            "sessionId": "expired-older",
            "userSessionId": "studio2-owner-random-name",
            "status": "Wakeable",
            "snapshotStatus": "Ready",
            "reason": "Expired",
            "createdAt": "2026-08-05T09:00:00Z",
            "createdBy": "alice",
            "displayName": "更早的快照",
            "toolName": "veadk-studio-codex" if kind == "sandbox" else kind,
        },
    ]
    assert resumed.status_code == 200
    assert resumed.json()["sessionId"] == "resumed-snapshot-1"
    assert resumed.json()["status"] == "Ready"
    assert "snapshots" not in listed_after_resume.json()


def test_sandbox_snapshot_routes_enforce_owner_and_support_delete() -> None:
    gateway = _FakeGateway()
    gateway.snapshots["snapshot-alice"] = SandboxCloudSnapshot(
        tool_id="tool-openclaw",
        snapshot_id="snapshot-alice",
        session_id="expired-alice",
        user_session_id="studio2-owner-random-name",
        status="Ready",
        display_name="Alice Agent",
        created_by="alice",
    )
    with TestClient(_agent_app(gateway)) as client:
        denied = client.post(
            "/web/openclaw/snapshots/snapshot-alice/resume",
            headers={"X-Test-User": "bob"},
        )
        deleted = client.delete(
            "/web/openclaw/snapshots/snapshot-alice",
            headers={"X-Test-User": "alice"},
        )

    assert denied.status_code == 404
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert [item.snapshot_id for item in gateway.deleted_snapshots] == [
        "snapshot-alice"
    ]


def test_managed_agent_routes_enforce_username_scope() -> None:
    gateway = _FakeGateway()
    with TestClient(_agent_app(gateway)) as client:
        alice = client.post(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "alice"},
        ).json()
        bob = client.post(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "bob"},
        ).json()
        alice_list = client.get(
            "/web/openclaw/sessions", headers={"X-Test-User": "alice"}
        )
        admin_list = client.get(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "admin", "X-Test-Role": "admin"},
        )
        denied = client.delete(
            f"/web/openclaw/sessions/{alice['sessionId']}",
            headers={"X-Test-User": "bob"},
        )

    assert [item["sessionId"] for item in alice_list.json()["sessions"]] == [
        alice["sessionId"]
    ]
    assert {item["sessionId"] for item in admin_list.json()["sessions"]} == {
        alice["sessionId"],
        bob["sessionId"],
    }
    assert all(item["createdBy"] for item in admin_list.json()["sessions"])
    assert denied.status_code == 404


def test_managed_agent_routes_display_creator_separately_from_owner_id() -> None:
    gateway = _FakeGateway()
    owner_id = "255d476b-099c-4719-b0f5-22f0d57efe56"
    headers = {
        "X-Test-User": owner_id,
        "X-Test-Creator": "alice@example.com",
    }
    with TestClient(_agent_app(gateway)) as client:
        created = client.post("/web/openclaw/sessions", headers=headers)
        owner_list = client.get("/web/openclaw/sessions", headers=headers)
        other_list = client.get(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "another-user-id"},
        )

    assert created.json()["createdBy"] == "alice@example.com"
    assert owner_list.json()["sessions"][0]["createdBy"] == "alice@example.com"
    assert other_list.json() == {"sessions": []}
    session = gateway.sessions[created.json()["sessionId"]]
    assert session.created_by == owner_id
    assert session.creator_name == "alice@example.com"


def test_sandbox_routes_list_create_connect_and_disconnect() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        listed = client.get("/web/sandbox/sessions", headers={"X-Test-User": "alice"})
        create = client.post(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "  我的智能体  "},
        )

        assert create.status_code == 200
        assert create.json()["status"] == "Ready"
        assert "endpoint" not in create.json()
        assert "secret" not in create.text
        session_id = create.json()["sessionId"]
        not_connected = client.post(
            f"/web/sandbox/sessions/{session_id}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "not connected yet"},
        )
        connected = client.post(
            "/web/sandbox/sessions/remote-existing/connect",
            headers={"X-Test-User": "alice"},
        )

        first = client.post(
            "/web/sandbox/sessions/remote-existing/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "hello"},
        )
        second = client.post(
            "/web/sandbox/sessions/remote-existing/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "again"},
        )
        disconnected = client.post(
            "/web/sandbox/sessions/remote-existing/disconnect",
            headers={"X-Test-User": "alice"},
        )

    assert listed.status_code == 200
    assert listed.json() == {
        "sessions": [
            {
                "sessionId": "remote-existing",
                "userSessionId": "existing-agent",
                "status": "Ready",
                "createdAt": "2026-07-30T08:00:00Z",
                "expireAt": "2026-07-30T16:00:00Z",
                "toolType": "CodeEnv",
                "createdBy": "alice",
                "displayName": "",
            }
        ]
    }
    assert create.json()["displayName"] == "我的智能体"
    assert gateway.display_names == ["我的智能体"]
    assert connected.status_code == 200
    assert connected.json()["sessionId"] == "remote-existing"
    assert "endpoint" not in connected.json()
    assert "secret" not in connected.text
    assert not_connected.status_code == 404
    assert first.status_code == 200
    assert "event: activity" in first.text
    assert '"kind": "thinking"' in first.text
    assert '"kind": "tool"' in first.text
    assert "event: delta" in first.text
    assert 'data: {"text": "reply:hello"}' in first.text
    assert "event: done" in first.text
    assert second.status_code == 200
    assert gateway.thread_ids == ["thread-1", "thread-1"]
    assert disconnected.json() == {"disconnected": True}
    assert gateway.deleted == []
    assert session_id == "remote-1"


def test_sandbox_list_scope_follows_user_role() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        alice = client.post(
            "/web/sandbox/sessions", headers={"X-Test-User": "alice"}
        ).json()
        bob = client.post(
            "/web/sandbox/sessions", headers={"X-Test-User": "bob"}
        ).json()
        alice_list = client.get(
            "/web/sandbox/sessions", headers={"X-Test-User": "alice"}
        )
        developer_list = client.get(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "bob", "X-Test-Role": "developer"},
        )
        admin_list = client.get(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "admin", "X-Test-Role": "admin"},
        )

    assert [item["sessionId"] for item in alice_list.json()["sessions"]] == [
        alice["sessionId"],
        "remote-existing",
    ]
    assert [item["sessionId"] for item in developer_list.json()["sessions"]] == [
        bob["sessionId"]
    ]
    assert {item["sessionId"] for item in admin_list.json()["sessions"]} == {
        "remote-existing",
        alice["sessionId"],
        bob["sessionId"],
    }
    assert {item["createdBy"] for item in admin_list.json()["sessions"]} == {
        "alice",
        "bob",
    }
    assert gateway.usernames[-3:] == ["alice", "bob", None]


def test_sandbox_admin_can_delete_another_users_session() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        created = client.post(
            "/web/sandbox/sessions", headers={"X-Test-User": "alice"}
        ).json()
        deleted = client.delete(
            f"/web/sandbox/sessions/{created['sessionId']}",
            headers={"X-Test-User": "admin", "X-Test-Role": "admin"},
        )

    assert deleted.status_code == 200
    assert [session.instance_id for session in gateway.deleted] == [
        created["sessionId"]
    ]


def test_sandbox_delete_disconnects_and_removes_cloud_session() -> None:
    gateway = _FakeGateway()
    headers = {"X-Test-User": "alice"}
    root = "/web/sandbox/sessions/remote-existing"
    with TestClient(_app(gateway)) as client:
        assert client.post(f"{root}/connect", headers=headers).status_code == 200
        deleted = client.delete(root, headers=headers)
        listed = client.get("/web/sandbox/sessions", headers=headers)

    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert listed.json() == {"sessions": []}
    assert gateway.connections[0].closed is True
    assert [session.instance_id for session in gateway.deleted] == ["remote-existing"]


def test_sandbox_codex_commands_skills_threads_and_token_usage() -> None:
    gateway = _FakeGateway()
    headers = {"X-Test-User": "alice"}
    root = "/web/sandbox/sessions/remote-existing"
    with TestClient(_app(gateway)) as client:
        assert client.post(f"{root}/connect", headers=headers).status_code == 200

        models = client.get(f"{root}/models", headers=headers)
        skills = client.get(f"{root}/skills", headers=headers)
        selected = client.post(
            f"{root}/messages",
            headers=headers,
            json={
                "message": "$review inspect",
                "skillIds": ["skill-public-id"],
            },
        )
        assert gateway.connections[0].selected_skill_ids == ("skill-public-id",)
        token_reply = client.post(
            f"{root}/messages",
            headers=headers,
            json={"message": "tokens"},
        )
        model = client.put(
            f"{root}/model",
            headers=headers,
            json={"model": "gpt-next"},
        )
        threads = client.get(f"{root}/threads", headers=headers)
        resumed = client.post(
            f"{root}/threads/resume",
            headers=headers,
            json={"threadId": "thread-old"},
        )
        forked = client.post(f"{root}/threads/fork", headers=headers)
        compacted = client.post(f"{root}/threads/compact", headers=headers)
        archived = client.post(
            f"{root}/threads/archive",
            headers=headers,
            json={"threadId": "thread-fork"},
        )
        status = client.get(f"{root}/status", headers=headers)

    assert models.json()["models"][0]["id"] == "gpt-test"
    assert skills.json()["skills"] == [
        {
            "id": "skill-public-id",
            "name": "review",
            "description": "Review code",
        }
    ]
    assert "path" not in skills.text.lower()
    assert selected.status_code == 200
    assert "event: usage" in token_reply.text
    assert '"totalTokens": 42' in token_reply.text
    assert '"modelContextWindow": 200000' in token_reply.text
    assert model.json() == {"model": "gpt-next"}
    assert threads.json()["threads"][0]["id"] == "thread-old"
    assert resumed.json()["messages"][0]["skillNames"] == ["review"]
    assert forked.json()["threadId"] == "thread-fork"
    assert compacted.json() == {"started": True}
    assert archived.json()["archived"] is True
    assert archived.json()["threadId"] == "thread-new"
    assert status.json()["model"] == "gpt-next"
    assert status.json()["threadId"] == "thread-new"


def test_sandbox_settings_tools_and_first_turn_workspace_lock() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        connected = client.post(
            "/web/sandbox/sessions/remote-existing/connect",
            headers={"X-Test-User": "alice"},
        )
        settings = client.get(
            "/web/sandbox/sessions/remote-existing/settings",
            headers={"X-Test-User": "alice"},
        )
        permissions = client.put(
            "/web/sandbox/sessions/remote-existing/permissions",
            headers={"X-Test-User": "alice"},
            json={
                "approvalPolicy": "never",
                "approvalsReviewer": "auto_review",
                "sandboxMode": "read-only",
                "networkAccess": True,
            },
        )
        workspace = client.put(
            "/web/sandbox/sessions/remote-existing/workspace",
            headers={"X-Test-User": "alice"},
            json={"cwd": "/workspace/project"},
        )
        directories = client.get(
            "/web/sandbox/sessions/remote-existing/directories",
            headers={"X-Test-User": "alice"},
            params={"path": "/workspace"},
        )
        browser = client.post(
            "/web/sandbox/sessions/remote-existing/browser",
            headers={"X-Test-User": "alice"},
        )
        client.post(
            "/web/sandbox/sessions/remote-existing/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "start"},
        )
        locked = client.put(
            "/web/sandbox/sessions/remote-existing/workspace",
            headers={"X-Test-User": "alice"},
            json={"cwd": "/other"},
        )

    assert connected.status_code == 200
    assert connected.json()["cwd"] == "/workspace"
    assert settings.json()["permissions"]["approvalPolicy"] == "on-request"
    assert permissions.json()["permissions"] == {
        "approvalPolicy": "never",
        "approvalsReviewer": "auto_review",
        "sandboxMode": "read-only",
        "networkAccess": True,
    }
    assert workspace.json() == {
        "cwd": "/workspace/project",
        "workspaceLocked": False,
    }
    assert directories.json()["directories"] == [
        {"name": "project", "path": "/workspace/project"}
    ]
    assert browser.status_code == 200
    assert browser.json()["url"].startswith(
        "https://sandbox.example/existing/browser-ui?"
    )
    assert "Authorization=secret" in browser.json()["url"]
    assert "veadk_sandbox_" in browser.headers["set-cookie"]
    assert locked.status_code == 409


def test_sandbox_stream_redacts_private_endpoint_queries() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        client.post(
            "/web/sandbox/sessions/remote-existing/connect",
            headers={"X-Test-User": "alice"},
        )
        response = client.post(
            "/web/sandbox/sessions/remote-existing/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "show private endpoint"},
        )

    assert response.status_code == 200
    assert "Authorization" not in response.text
    assert "secret" not in response.text
    assert "[sandbox endpoint]" in response.text


@pytest.mark.asyncio
async def test_permissions_propagate_to_every_thread_in_the_cloud_session() -> None:
    gateway = _FakeGateway()
    service = SandboxConversationService(gateway, tool_id="tool-studio")
    alice = await service.connect("remote-existing", "alice")
    bob = await service.connect("remote-existing", "bob", is_admin=True)
    settings = CodexPermissionSettings(
        approval_policy="never",
        approvals_reviewer="auto_review",
        sandbox_mode="danger-full-access",
        network_access=True,
    )

    applied = await service.update_permissions("remote-existing", "alice", settings)

    assert alice.codex.permissions == applied
    assert bob.codex.permissions == applied


def test_sandbox_create_rejects_invalid_display_names() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        too_long = client.post(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "名" * (STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH + 1)},
        )
        wrong_type = client.post(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": 42},
        )

    assert too_long.status_code == 422
    assert "40" in too_long.text
    assert wrong_type.status_code == 422
    assert gateway.display_names == []


def test_sandbox_capabilities_report_configured_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_CHAT_CODEX", "configured-tool")
    with TestClient(_app(_FakeGateway(), tool_id=None)) as client:
        response = client.get(
            "/web/sandbox/capabilities", headers={"X-Test-User": "alice"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "reason": "",
        "defaultRetentionMode": "recoverable",
        "retentionModes": {
            "temporary": {
                "enabled": False,
                "reason": "管理员未配置临时会话 Tool",
            },
            "recoverable": {"enabled": True, "reason": ""},
        },
    }


def test_sandbox_capabilities_report_admin_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_CHAT_CODEX", raising=False)
    with TestClient(_app(_FakeGateway(), tool_id=None)) as client:
        response = client.get(
            "/web/sandbox/capabilities", headers={"X-Test-User": "alice"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "reason": "管理员未配置",
        "defaultRetentionMode": "temporary",
        "retentionModes": {
            "temporary": {
                "enabled": False,
                "reason": "管理员未配置临时会话 Tool",
            },
            "recoverable": {
                "enabled": False,
                "reason": "管理员未配置可恢复会话 Tool",
            },
        },
    }


@pytest.mark.asyncio
async def test_sandbox_start_requires_preconfigured_chat_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_CHAT_CODEX", raising=False)
    gateway = _FakeGateway()
    service = SandboxConversationService(gateway)

    with pytest.raises(SandboxConfigurationError, match="管理员未配置"):
        await service.create("alice")

    assert gateway.created == 0


def test_sandbox_route_hides_sessions_owned_by_another_user() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        created = client.post("/web/sandbox/sessions", headers={"X-Test-User": "alice"})
        session_id = created.json()["sessionId"]
        connected = client.post(
            f"/web/sandbox/sessions/{session_id}/connect",
            headers={"X-Test-User": "alice"},
        )
        response = client.delete(
            f"/web/sandbox/sessions/{session_id}",
            headers={"X-Test-User": "bob"},
        )

    assert connected.status_code == 200
    assert response.status_code == 404
    assert gateway.deleted == []


def test_sandbox_route_rejects_empty_message() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        created = client.post("/web/sandbox/sessions", headers={"X-Test-User": "alice"})
        response = client.post(
            f"/web/sandbox/sessions/{created.json()['sessionId']}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "  "},
        )

    assert response.status_code == 422


def test_sandbox_route_requires_an_identity() -> None:
    with TestClient(_app(_FakeGateway())) as client:
        response = client.post("/web/sandbox/sessions")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_service_owner_check_does_not_reveal_session() -> None:
    service = SandboxConversationService(_FakeGateway(), tool_id="tool-studio")
    cloud = await service.create("alice")
    session = await service.connect(cloud.instance_id, "alice")

    with pytest.raises(SandboxSessionNotFoundError):
        await service.close(session.session_id, "bob")


@pytest.mark.asyncio
async def test_service_allows_multiple_sessions_for_the_same_owner() -> None:
    gateway = _FakeGateway()
    service = SandboxConversationService(gateway, tool_id="tool-studio")

    first, second = await asyncio.gather(
        service.create("alice"),
        service.create("alice"),
    )

    assert first.instance_id != second.instance_id
    assert gateway.created == 2


@pytest.mark.asyncio
async def test_gateway_accepts_a_lazy_client_factory() -> None:
    class _Client:
        def list_tools(self, request: object) -> str:
            del request
            return "ok"

    calls = 0

    def _factory() -> _Client:
        nonlocal calls
        calls += 1
        return _Client()

    gateway = AgentkitSandboxGateway(_factory)

    assert await gateway._call("list_tools", object()) == "ok"
    assert calls == 1


@pytest.mark.asyncio
async def test_gateway_accepts_an_already_expired_session_as_deleted() -> None:
    class _Client:
        def delete_session(self, request: object) -> None:
            del request
            raise RuntimeError("InvalidResource.NotFound")

    gateway = AgentkitSandboxGateway(_Client())
    await gateway.delete_session(
        SandboxCloudSession(
            tool_id="tool-1",
            instance_id="expired-session",
            user_session_id="user-1",
            endpoint="https://sandbox.example",
        )
    )


@pytest.mark.asyncio
async def test_gateway_lists_all_sessions_from_the_configured_tool_region() -> None:
    calls: list[tuple[str, str | None]] = []

    class _Client:
        def __init__(self, region: str) -> None:
            self.region = region

        def list_sessions(self, request: object) -> SimpleNamespace:
            next_token = request.next_token
            calls.append((self.region, next_token))
            if self.region == "cn-beijing":
                raise RuntimeError("InvalidResource.NotFound")
            if next_token is None:
                return SimpleNamespace(
                    session_infos=[
                        SimpleNamespace(
                            session_id="remote-old",
                            user_session_id="old-agent",
                            endpoint="https://sandbox.example/old?Authorization=secret",
                            status="Ready",
                            created_at="2026-07-29T08:00:00Z",
                            expire_at="2026-07-30T08:00:00Z",
                            tool_type="CodeEnv",
                        )
                    ],
                    next_token="page-2",
                )
            return SimpleNamespace(
                session_infos=[
                    SimpleNamespace(
                        session_id="remote-new",
                        user_session_id="new-agent",
                        endpoint="https://sandbox.example/new?Authorization=secret",
                        status="Ready",
                        created_at="2026-07-30T08:00:00Z",
                        expire_at="2026-07-31T08:00:00Z",
                        tool_type="CodeEnv",
                    )
                ],
                next_token=None,
            )

    gateway = AgentkitSandboxGateway(
        _Client,
        region_candidates=("cn-beijing", "cn-shanghai"),
    )

    sessions = await gateway.list_sessions("tool-1")

    assert [session.instance_id for session in sessions] == [
        "remote-new",
        "remote-old",
    ]
    assert all(session.region == "cn-shanghai" for session in sessions)
    assert calls == [
        ("cn-beijing", None),
        ("cn-shanghai", None),
        ("cn-shanghai", "page-2"),
    ]


@pytest.mark.asyncio
async def test_gateway_uses_the_installed_agentkit_list_sessions_contract() -> None:
    from agentkit.sdk.tools import types as tools_types

    requests: list[dict[str, object]] = []

    class _Client:
        def list_sessions(
            self, request: tools_types.ListSessionsRequest
        ) -> tools_types.ListSessionsResponse:
            requests.append(request.model_dump(by_alias=True, exclude_none=True))
            return tools_types.ListSessionsResponse(
                SessionInfos=[
                    tools_types.SessionInfosForListSessions(
                        SessionId="remote-sdk",
                        UserSessionId="sdk-agent",
                        Status="Ready",
                        Endpoint=("https://sandbox.example/path?Authorization=secret"),
                        CreatedAt="2026-07-30T08:00:00Z",
                        ExpireAt="2026-07-30T16:00:00Z",
                        ToolType="CodeEnv",
                    )
                ]
            )

    sessions = await AgentkitSandboxGateway(_Client()).list_sessions("tool-sdk")

    assert requests == [{"MaxResults": 100, "ToolId": "tool-sdk"}]
    assert len(sessions) == 1
    assert sessions[0].instance_id == "remote-sdk"
    assert sessions[0].user_session_id == "sdk-agent"
    assert sessions[0].status == "Ready"
    assert sessions[0].created_at == "2026-07-30T08:00:00Z"
    assert sessions[0].expire_at == "2026-07-30T16:00:00Z"
    assert sessions[0].tool_type == "CodeEnv"


@pytest.mark.asyncio
async def test_gateway_filters_sessions_by_username_metadata() -> None:
    requests: list[dict[str, object]] = []

    class _Client:
        def list_sessions(self, request: object) -> SimpleNamespace:
            requests.append(request.model_dump(by_alias=True, exclude_none=True))
            return SimpleNamespace(
                session_infos=[
                    SimpleNamespace(
                        session_id="remote-alice",
                        user_session_id="alice-agent",
                        endpoint="https://sandbox.example/path?Authorization=secret",
                        status="Ready",
                        metadata=[
                            {"Key": "Username", "Type": "String", "Value": "alice"},
                            {
                                "Key": "veadk_creator_name",
                                "Type": "String",
                                "Value": "alice@example.com",
                            },
                        ],
                    )
                ],
                next_token=None,
            )

    sessions = await AgentkitSandboxGateway(_Client()).list_sessions(
        "tool-sdk", "alice"
    )

    assert requests == [
        {
            "MaxResults": 100,
            "ToolId": "tool-sdk",
            "Metadata": [{"Key": "Username", "Value": "alice"}],
        }
    ]
    assert [session.created_by for session in sessions] == ["alice"]
    assert [session.creator_name for session in sessions] == ["alice@example.com"]


@pytest.mark.asyncio
async def test_gateway_creates_session_with_username_metadata() -> None:
    requests: list[dict[str, object]] = []

    class _Client:
        def create_session(self, request: object) -> SimpleNamespace:
            requests.append(request.model_dump(by_alias=True, exclude_none=True))
            return SimpleNamespace(
                session_id="remote-alice",
                user_session_id="alice-agent",
                endpoint="https://sandbox.example",
            )

    session = await AgentkitSandboxGateway(_Client()).create_session(
        "tool-sdk",
        "Alice Agent",
        "alice",
        "alice@example.com",
    )

    assert requests[0]["Metadata"] == [
        {"Key": "veadk_display_name", "Type": "String", "Value": "Alice Agent"},
        {"Key": "Username", "Type": "String", "Value": "alice"},
        {
            "Key": "veadk_creator_name",
            "Type": "String",
            "Value": "alice@example.com",
        },
    ]
    assert session.created_by == "alice"
    assert session.creator_name == "alice@example.com"


@pytest.mark.asyncio
async def test_gateway_lists_only_owned_studio_snapshots_and_restores_one() -> None:
    from agentkit.sdk.tools import types as tools_types

    requests: list[tuple[str, dict[str, object]]] = []
    created_user_session_id = ""
    resumed_once = False

    class _Client:
        def create_session(self, request: object) -> SimpleNamespace:
            nonlocal created_user_session_id
            created_user_session_id = request.user_session_id
            return SimpleNamespace(
                session_id="expired-alice",
                user_session_id=created_user_session_id,
                endpoint="https://sandbox.example",
            )

        def list_session_snapshots(
            self, request: tools_types.ListSessionSnapshotsRequest
        ) -> tools_types.ListSessionSnapshotsResponse:
            requests.append(
                (
                    "list",
                    request.model_dump(by_alias=True, exclude_none=True),
                )
            )
            if request.next_token is None:
                return tools_types.ListSessionSnapshotsResponse(
                    NextToken="snapshot-page-2",
                    Snapshots=[
                        tools_types.SnapshotsForListSessionSnapshots(
                            SnapshotId="snapshot-alice",
                            SessionId="expired-alice",
                            UserSessionId=created_user_session_id,
                            Status="Ready",
                            Reason="Expired",
                            CreatedAt="2026-08-06T09:00:00Z",
                        ),
                        tools_types.SnapshotsForListSessionSnapshots(
                            SnapshotId="snapshot-bob",
                            SessionId="expired-bob",
                            UserSessionId=(
                                "studio-bob-0123456789abcdef0123456789abcdef"
                            ),
                            Status="Ready",
                        ),
                        tools_types.SnapshotsForListSessionSnapshots(
                            SnapshotId="snapshot-custom-suffix",
                            SessionId="expired-custom-suffix",
                            UserSessionId=(
                                "studio-alice-84a286wese63c484a299ac9b461cf94asd2"
                            ),
                            Status="Ready",
                        ),
                    ],
                )
            return tools_types.ListSessionSnapshotsResponse(
                Snapshots=[
                    tools_types.SnapshotsForListSessionSnapshots(
                        SnapshotId="snapshot-legacy-owned",
                        SessionId="expired-legacy-owned",
                        UserSessionId="studio2-2bd806c97f0e00af-random-QWxpY2UgT2xk",
                        Status="Ready",
                    ),
                    tools_types.SnapshotsForListSessionSnapshots(
                        SnapshotId="snapshot-legacy",
                        SessionId="expired-legacy",
                        UserSessionId="studio-random-legacy",
                        Status="Ready",
                    ),
                    tools_types.SnapshotsForListSessionSnapshots(
                        SnapshotId="snapshot-without-user-session-id",
                        SessionId="expired-without-user-session-id",
                        Status="Ready",
                    ),
                ]
            )

        def list_sessions(self, request: object) -> SimpleNamespace:
            requests.append(
                (
                    "sessions",
                    request.model_dump(by_alias=True, exclude_none=True),
                )
            )
            session_infos = []
            if resumed_once:
                session_infos.append(
                    SimpleNamespace(
                        session_id="resumed-alice",
                        user_session_id=created_user_session_id,
                        endpoint="https://sandbox.example/resumed",
                        status="Ready",
                        tool_type="CodeEnv",
                    )
                )
            return SimpleNamespace(session_infos=session_infos, next_token=None)

        def resume_session_from_snapshot(self, request: object) -> SimpleNamespace:
            nonlocal resumed_once
            requests.append(
                (
                    "resume",
                    request.model_dump(by_alias=True, exclude_none=True),
                )
            )
            resumed_once = True
            return SimpleNamespace(session_id="resumed-alice")

        def get_session(self, request: object) -> SimpleNamespace:
            return SimpleNamespace(
                session_id="resumed-alice",
                user_session_id=created_user_session_id,
                endpoint="https://sandbox.example/resumed",
                status="Ready",
                tool_type="CodeEnv",
            )

    gateway = AgentkitSandboxGateway(_Client())
    await gateway.create_session("tool-sdk", "Alice 智能体", "alice")
    snapshots = await gateway.list_snapshots("tool-sdk", "alice")
    admin_snapshots = await gateway.list_snapshots("tool-sdk")
    resumed = await gateway.resume_snapshot(snapshots[0])
    reused = await gateway.resume_snapshot(snapshots[0])

    assert re.fullmatch(
        r"studio-alice-[0-9a-f]{32}",
        created_user_session_id,
    )
    assert len(created_user_session_id) <= 200
    assert [snapshot.snapshot_id for snapshot in snapshots] == [
        "snapshot-alice",
        "snapshot-custom-suffix",
        "snapshot-legacy-owned",
    ]
    assert snapshots[0].display_name == created_user_session_id
    assert snapshots[1].display_name.startswith("studio-alice-")
    assert snapshots[2].display_name == "Alice Old"
    assert {snapshot.snapshot_id for snapshot in admin_snapshots} == {
        "snapshot-alice",
        "snapshot-bob",
        "snapshot-custom-suffix",
        "snapshot-legacy-owned",
        "snapshot-legacy",
        "snapshot-without-user-session-id",
    }
    assert (
        next(
            snapshot
            for snapshot in admin_snapshots
            if snapshot.snapshot_id == "snapshot-without-user-session-id"
        ).display_name
        == "snapshot-without-user-session-id"
    )
    assert resumed.instance_id == "resumed-alice"
    assert reused.instance_id == "resumed-alice"
    assert [action for action, _ in requests].count("resume") == 1
    resume_request = next(body for action, body in requests if action == "resume")
    assert resume_request == {
        "CreateNewInstance": False,
        "SnapshotId": "snapshot-alice",
        "ToolId": "tool-sdk",
        "Ttl": 28800,
    }


@pytest.mark.asyncio
async def test_gateway_gets_an_existing_session_without_exposing_its_region() -> None:
    calls: list[str] = []

    class _Client:
        def __init__(self, region: str) -> None:
            self.region = region

        def get_session(self, request: object) -> SimpleNamespace:
            del request
            calls.append(self.region)
            if self.region == "cn-beijing":
                raise RuntimeError("InvalidResource.NotFound")
            return SimpleNamespace(
                session_id="remote-1",
                user_session_id="agent-1",
                endpoint="https://sandbox.example/path?Authorization=secret",
                status="Ready",
                created_at="2026-07-30T08:00:00Z",
                expire_at="2026-07-31T08:00:00Z",
                tool_type="CodeEnv",
            )

    gateway = AgentkitSandboxGateway(
        _Client,
        region_candidates=("cn-beijing", "cn-shanghai"),
    )

    session = await gateway.get_session("tool-1", "remote-1")

    assert session.instance_id == "remote-1"
    assert session.region == "cn-shanghai"
    assert calls == ["cn-beijing", "cn-shanghai"]


@pytest.mark.asyncio
async def test_gateway_retries_session_creation_in_shanghai_and_deletes_there() -> None:
    created_regions: list[str] = []
    deleted_regions: list[str] = []

    class _Client:
        def __init__(self, region: str) -> None:
            self.region = region

        def create_session(self, request: object) -> SimpleNamespace:
            del request
            created_regions.append(self.region)
            if self.region == "cn-beijing":
                raise RuntimeError("InvalidResource.NotFound")
            return SimpleNamespace(
                session_id="remote-1",
                user_session_id="user-1",
                endpoint="https://sandbox.example",
            )

        def delete_session(self, request: object) -> None:
            del request
            deleted_regions.append(self.region)

    gateway = AgentkitSandboxGateway(
        _Client,
        region_candidates=("cn-beijing", "cn-shanghai"),
    )

    session = await gateway.create_session("tool-1")
    await gateway.delete_session(session)

    assert created_regions == ["cn-beijing", "cn-shanghai"]
    assert session.region == "cn-shanghai"
    assert deleted_regions == ["cn-shanghai"]


@pytest.mark.asyncio
async def test_gateway_accepts_create_response_while_session_is_starting() -> None:
    class _Client:
        def create_session(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                session_id="remote-creating",
                user_session_id="user-creating",
                endpoint=None,
            )

    session = await AgentkitSandboxGateway(_Client()).create_session("tool-1")

    assert session.instance_id == "remote-creating"
    assert session.status == "Creating"
    assert session.endpoint == ""


@pytest.mark.asyncio
async def test_gateway_does_not_retry_non_not_found_creation_errors() -> None:
    regions: list[str] = []

    class _Client:
        def __init__(self, region: str) -> None:
            self.region = region

        def create_session(self, request: object) -> None:
            del request
            regions.append(self.region)
            raise RuntimeError("AccessDenied")

    gateway = AgentkitSandboxGateway(
        _Client,
        region_candidates=("cn-beijing", "cn-shanghai"),
    )

    with pytest.raises(SandboxProvisioningError, match="AccessDenied"):
        await gateway.create_session("tool-1")

    assert regions == ["cn-beijing"]


@pytest.mark.asyncio
async def test_disconnect_never_deletes_the_cloud_session() -> None:
    class _FailDeleteGateway(_FakeGateway):
        async def delete_session(self, session: SandboxCloudSession) -> None:
            del session
            raise SandboxProvisioningError("delete failed")

    service = SandboxConversationService(_FailDeleteGateway(), tool_id="tool-studio")
    cloud = await service.create("alice")
    session = await service.connect(cloud.instance_id, "alice")

    await service.close(session.session_id, "alice")

    with pytest.raises(SandboxSessionNotFoundError):
        service.require_owned(session.session_id, "alice")


@pytest.mark.asyncio
async def test_expiry_and_close_all_only_drop_local_connections() -> None:
    gateway = _FakeGateway()
    service = SandboxConversationService(gateway, tool_id="tool-studio")
    expired = await service.connect("remote-existing", "alice")
    expired.expires_at = time.monotonic() - 1

    await service.cleanup_expired()
    active = await service.connect("remote-existing", "bob", is_admin=True)
    await service.close_all()

    with pytest.raises(SandboxSessionNotFoundError):
        service.require_owned(expired.session_id, "alice")
    with pytest.raises(SandboxSessionNotFoundError):
        service.require_owned(active.session_id, "bob")
    assert gateway.deleted == []


def test_sse_error_has_an_explicit_done_frame() -> None:
    class _FailStreamGateway(_FakeGateway):
        async def open_codex(self, session: SandboxCloudSession) -> _FakeCodex:
            del session
            connection = _FakeCodex(self.thread_ids, fail=True)
            self.connections.append(connection)
            return connection

    with TestClient(_app(_FailStreamGateway())) as client:
        created = client.post("/web/sandbox/sessions", headers={"X-Test-User": "alice"})
        client.post(
            f"/web/sandbox/sessions/{created.json()['sessionId']}/connect",
            headers={"X-Test-User": "alice"},
        )
        response = client.post(
            f"/web/sandbox/sessions/{created.json()['sessionId']}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "hello"},
        )

    assert "event: error" in response.text
    assert 'event: done\ndata: {"reason": "failed"}' in response.text


@pytest.mark.asyncio
async def test_cancelled_create_is_deleted_after_sdk_call_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[str] = []
    created: list[object] = []

    class _Client:
        def create_session(self, request: object) -> SimpleNamespace:
            created.append(request)
            time.sleep(0.05)
            return SimpleNamespace(
                session_id="remote-1",
                user_session_id="user-1",
                endpoint="https://sandbox.example?Authorization=secret",
            )

        def delete_session(self, request: object) -> None:
            deleted.append(str(request.session_id))

    gateway = AgentkitSandboxGateway(_Client())
    task = asyncio.create_task(gateway.create_session("tool-1"))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    await gateway.drain()

    assert deleted == ["remote-1"]
    assert len(created) == 1
    assert created[0].tool_id == "tool-1"
    assert created[0].envs is None
