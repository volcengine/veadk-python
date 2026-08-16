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
import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from veadk.cli import frontend_sandbox
from veadk.cli.codex_app_server import (
    CodexAppServerError,
    CodexAppServerEvent,
    CodexDirectoryEntry,
    CodexDirectoryListing,
    CodexImportedImage,
    CodexImportedMessage,
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
        self.prompts: list[str] = []
        self.fail = fail
        self.approvals: list[tuple[str, str]] = []
        self.selected_skill_ids: tuple[str, ...] = ()
        self.imported_history: tuple[CodexImportedMessage, ...] = ()

    async def stream_turn(
        self, prompt: str, skill_ids: tuple[str, ...] = ()
    ) -> AsyncIterator[CodexAppServerEvent]:
        self.active = True
        self.workspace_locked = True
        self.turns.append(self.thread_id)
        self.prompts.append(prompt)
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

    async def read_thread(self, thread_id: str) -> CodexThreadSnapshot:
        active_thread_id = self.thread_id
        workspace_locked = self.workspace_locked
        snapshot = self._snapshot(thread_id)
        self.thread_id = active_thread_id
        self.workspace_locked = workspace_locked
        return snapshot

    async def inject_history(self, messages: tuple[CodexImportedMessage, ...]) -> None:
        self.imported_history = messages

    async def fork_thread(self) -> CodexThreadSnapshot:
        return self._snapshot("thread-fork")

    async def archive_thread(self, thread_id: str) -> CodexThreadSnapshot | None:
        if thread_id != self.thread_id:
            return None
        return await self.new_thread()

    async def delete_thread(self, thread_id: str) -> CodexThreadSnapshot | None:
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
        self.agent_kinds: list[str] = []
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

    async def list_snapshots(self, tool_id: str) -> list[SandboxCloudSnapshot]:
        self.tool_ids.append(tool_id)
        self.usernames.append(None)
        return [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.tool_id == tool_id
        ]

    async def get_session(self, tool_id: str, session_id: str) -> SandboxCloudSession:
        self.tool_ids.append(tool_id)
        session = self.sessions.get(session_id)
        if session is None or session.tool_id != tool_id:
            raise SandboxSessionNotFoundError("AgentKit Session 不存在或已过期。")
        return session

    async def create_session(
        self,
        tool_id: str,
        display_name: str = "",
        username: str = "",
        creator_name: str = "",
        agent_kind: str = "",
    ) -> SandboxCloudSession:
        self.created += 1
        self.tool_ids.append(tool_id)
        self.display_names.append(display_name)
        self.creator_names.append(creator_name)
        self.agent_kinds.append(agent_kind)
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
            agent_kind=agent_kind,
        )
        self.sessions[session.instance_id] = session
        return replace(session, expire_at="")

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


def _app(
    gateway: _FakeGateway,
    tool_id: str | None = "tool-studio",
    snapshot_tool_id: str | None = "tool-studio-snapshot",
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


def _agent_app(
    gateway: _FakeGateway,
    *,
    snapshot_tool_ids: dict[str, str] | None = None,
) -> FastAPI:
    if snapshot_tool_ids is None:
        snapshot_tool_ids = {
            "deepseek-harness": "tool-studio-snapshot",
            "openclaw": "tool-openclaw-snapshot",
            "hermes": "tool-hermes-snapshot",
        }
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
            "deepseek-harness": SandboxAgentSessionService(
                gateway,
                kind="deepseek-harness",
                tool_id="tool-studio",
                snapshot_tool_id=snapshot_tool_ids.get("deepseek-harness"),
                surface_path="/deepseek-harness/",
                filter_agent_kind=True,
            ),
            "openclaw": SandboxAgentSessionService(
                gateway,
                kind="openclaw",
                tool_id="tool-openclaw",
                snapshot_tool_id=snapshot_tool_ids.get("openclaw"),
            ),
            "hermes": SandboxAgentSessionService(
                gateway,
                kind="hermes",
                tool_id="tool-hermes",
                snapshot_tool_id=snapshot_tool_ids.get("hermes"),
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
    assert created.json()["persistent"] is True
    assert created.json()["expireAt"] == "2026-07-30T17:00:00Z"
    assert "endpoint" not in created.json()
    assert tool_id in gateway.tool_ids
    assert f"{tool_id}-snapshot" in gateway.tool_ids
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


def test_deepseek_harness_reuses_codex_tools_and_has_its_own_surface() -> None:
    gateway = _FakeGateway()
    headers = {"X-Test-User": "alice"}
    with TestClient(_agent_app(gateway)) as client:
        before = client.get("/web/deepseek-harness/sessions", headers=headers)
        created = client.post(
            "/web/deepseek-harness/sessions",
            headers=headers,
            json={"displayName": "DSH"},
        )
        listed = client.get("/web/deepseek-harness/sessions", headers=headers)
        session_id = created.json()["sessionId"]
        opened = client.post(
            f"/web/deepseek-harness/sessions/{session_id}/open",
            headers=headers,
        )

    assert before.json() == {"sessions": []}
    assert created.status_code == 200
    assert created.json()["toolName"] == "deepseek-harness"
    assert created.json()["persistent"] is True
    assert listed.json()["sessions"] == [created.json()]
    assert opened.json()["webuiUrl"].startswith(
        f"/web/deepseek-harness/sessions/{session_id}/surface/"
    )
    assert opened.json()["webuiUrl"].endswith("/deepseek-harness/")
    assert gateway.agent_kinds == ["deepseek-harness"]
    assert "tool-studio-snapshot" in gateway.tool_ids


@pytest.mark.parametrize("kind", ["openclaw", "hermes"])
def test_managed_agent_routes_select_and_resolve_both_tool_variants(
    kind: str,
) -> None:
    gateway = _FakeGateway()
    headers = {"X-Test-User": "alice"}
    with TestClient(_agent_app(gateway)) as client:
        persistent = client.post(f"/web/{kind}/sessions", headers=headers)
        temporary = client.post(
            f"/web/{kind}/sessions",
            headers=headers,
            json={"persistent": False},
        )
        invalid = client.post(
            f"/web/{kind}/sessions",
            headers=headers,
            json={"persistent": 1},
        )
        listed = client.get(f"/web/{kind}/sessions", headers=headers)
        opened = client.post(
            f"/web/{kind}/sessions/{persistent.json()['sessionId']}/open",
            headers=headers,
        )
        deleted = client.delete(
            f"/web/{kind}/sessions/{temporary.json()['sessionId']}",
            headers=headers,
        )

    assert persistent.status_code == 200
    assert persistent.json()["persistent"] is True
    assert temporary.status_code == 200
    assert temporary.json()["persistent"] is False
    assert invalid.status_code == 422
    assert {item["persistent"] for item in listed.json()["sessions"]} == {
        False,
        True,
    }
    assert opened.json()["persistent"] is True
    assert deleted.json() == {"deleted": True}
    assert gateway.deleted[0].tool_id == f"tool-{kind}"


def test_managed_agent_persistent_create_requires_snapshot_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_CHAT_OPENCLAW_SNAPSHOT", raising=False)
    gateway = _FakeGateway()
    headers = {"X-Test-User": "alice"}
    with TestClient(_agent_app(gateway, snapshot_tool_ids={})) as client:
        missing = client.post("/web/openclaw/sessions", headers=headers)
        temporary = client.post(
            "/web/openclaw/sessions",
            headers=headers,
            json={"persistent": False},
        )

    assert missing.status_code == 503
    assert "快照" in missing.text
    assert temporary.status_code == 200
    assert temporary.json()["persistent"] is False


def test_managed_agent_snapshot_is_listed_resumed_and_deleted() -> None:
    gateway = _FakeGateway()
    gateway.snapshots["snapshot-alice"] = SandboxCloudSnapshot(
        tool_id="tool-openclaw-snapshot",
        snapshot_id="snapshot-alice",
        session_id="expired-alice",
        user_session_id="studio-01234567-89ab-cdef-0123-456789abcdef",
        region="cn-beijing",
        status="Ready",
        reason="Expired",
        created_at="2026-08-06T09:00:00Z",
        display_name="Alice Agent",
        created_by="alice",
    )
    gateway.snapshots["snapshot-bob"] = SandboxCloudSnapshot(
        tool_id="tool-openclaw-snapshot",
        snapshot_id="snapshot-bob",
        session_id="expired-bob",
        user_session_id="studio-fedcba98-7654-3210-fedc-ba9876543210",
        region="cn-beijing",
        status="Ready",
        reason="Expired",
        created_at="2026-08-05T09:00:00Z",
        display_name="Bob Agent",
        created_by="bob",
    )

    with TestClient(_agent_app(gateway)) as client:
        alice_list = client.get(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "alice"},
        )
        admin_list = client.get(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "admin", "X-Test-Role": "admin"},
        )
        denied = client.post(
            "/web/openclaw/snapshots/snapshot-alice/resume",
            headers={"X-Test-User": "bob"},
        )
        resumed = client.post(
            "/web/openclaw/snapshots/snapshot-alice/resume",
            headers={"X-Test-User": "admin", "X-Test-Role": "admin"},
        )
        deleted = client.delete(
            "/web/openclaw/snapshots/snapshot-bob",
            headers={"X-Test-User": "admin", "X-Test-Role": "admin"},
        )

    assert alice_list.status_code == 200
    assert "snapshots" not in alice_list.json()
    assert {item["snapshotId"] for item in admin_list.json()["snapshots"]} == {
        "snapshot-alice",
        "snapshot-bob",
    }
    assert {item["status"] for item in admin_list.json()["snapshots"]} == {"Wakeable"}
    assert denied.status_code == 404
    assert resumed.status_code == 200
    assert resumed.json()["sessionId"] == "resumed-snapshot-alice"
    assert deleted.status_code == 200
    assert [item.snapshot_id for item in gateway.deleted_snapshots] == ["snapshot-bob"]


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
                "persistent": False,
            }
        ]
    }
    assert create.json()["displayName"] == "我的智能体"
    assert create.json()["persistent"] is True
    assert create.json()["expireAt"] == "2026-07-30T17:00:00Z"
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


@pytest.mark.asyncio
async def test_sandbox_client_disconnect_interrupts_only_the_active_turn() -> None:
    class _CancellableCodex(_FakeCodex):
        def __init__(self, turns: list[str]) -> None:
            super().__init__(turns)
            self.partial_sent = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def stream_turn(
            self, prompt: str, skill_ids: tuple[str, ...] = ()
        ) -> AsyncIterator[CodexAppServerEvent]:
            if prompt != "first":
                yield CodexAppServerEvent(kind="text", text=f"reply:{prompt}")
                return
            self.active = True
            self.workspace_locked = True
            try:
                yield CodexAppServerEvent(kind="text", text="partial")
                self.partial_sent.set()
                await asyncio.Event().wait()
            finally:
                self.active = False
                self.cancelled.set()

    class _CancellableGateway(_FakeGateway):
        async def open_codex(self, session: SandboxCloudSession) -> _FakeCodex:
            del session
            connection = _CancellableCodex(self.thread_ids)
            self.connections.append(connection)
            return connection

    gateway = _CancellableGateway()
    service = SandboxConversationService(gateway, tool_id="tool-studio")
    app = FastAPI()
    mount_sandbox_routes(app, service, lambda _request: "alice")
    await service.connect("remote-existing", "alice")
    connection = gateway.connections[0]
    request_sent = False
    response_messages: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {
                "type": "http.request",
                "body": json.dumps({"message": "first"}).encode(),
                "more_body": False,
            }
        await connection.partial_sent.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        response_messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/web/sandbox/sessions/remote-existing/messages",
            "raw_path": b"/web/sandbox/sessions/remote-existing/messages",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "root_path": "",
        },
        receive,
        send,
    )

    await asyncio.wait_for(connection.cancelled.wait(), timeout=1)
    assert any(b"partial" in message.get("body", b"") for message in response_messages)
    assert connection.active is False
    assert connection.closed is False
    follow_up = [
        event
        async for event in service.stream_message("remote-existing", "alice", "again")
    ]
    assert [event.text for event in follow_up] == ["reply:again"]


def test_sandbox_routes_select_and_resolve_both_tool_variants() -> None:
    gateway = _FakeGateway()
    headers = {"X-Test-User": "alice"}
    with TestClient(_app(gateway)) as client:
        persistent = client.post(
            "/web/sandbox/sessions",
            headers=headers,
            json={"displayName": "Persistent"},
        )
        temporary = client.post(
            "/web/sandbox/sessions",
            headers=headers,
            json={"displayName": "Temporary", "persistent": False},
        )
        invalid = client.post(
            "/web/sandbox/sessions",
            headers=headers,
            json={"persistent": "yes"},
        )
        listed = client.get("/web/sandbox/sessions", headers=headers)
        opened_persistent = client.post(
            f"/web/sandbox/sessions/{persistent.json()['sessionId']}/connect",
            headers=headers,
        )
        deleted_temporary = client.delete(
            f"/web/sandbox/sessions/{temporary.json()['sessionId']}",
            headers=headers,
        )

    assert persistent.status_code == 200
    assert persistent.json()["persistent"] is True
    assert gateway.sessions[persistent.json()["sessionId"]].tool_id == (
        "tool-studio-snapshot"
    )
    assert temporary.status_code == 200
    assert temporary.json()["persistent"] is False
    assert gateway.deleted[0].tool_id == "tool-studio"
    assert invalid.status_code == 422
    assert {item["persistent"] for item in listed.json()["sessions"]} == {False, True}
    assert opened_persistent.json()["persistent"] is True
    assert deleted_temporary.json() == {"deleted": True}


def test_sandbox_endpoint_export_requires_connected_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDIO_EXPOSE_SANDBOX_ENDPOINT", raising=False)
    gateway = _FakeGateway()
    headers = {"X-Test-User": "alice"}
    with TestClient(_app(gateway)) as client:
        listed = client.get("/web/sandbox/sessions", headers=headers)
        connected = client.post(
            "/web/sandbox/sessions/remote-existing/connect",
            headers=headers,
        )
        exported = client.get(
            "/web/sandbox/sessions/remote-existing/endpoint",
            headers=headers,
        )

    assert connected.status_code == 200
    assert "Authorization=secret" not in listed.text
    assert "Authorization=secret" not in connected.text
    assert exported.status_code == 200
    assert exported.json() == {
        "endpoint": "https://sandbox.example/existing?Authorization=secret",
        "sessionId": "remote-existing",
        "expireAt": "2026-07-30T16:00:00Z",
    }


def test_sandbox_endpoint_export_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUDIO_EXPOSE_SANDBOX_ENDPOINT", "0")
    gateway = _FakeGateway()
    headers = {"X-Test-User": "alice"}
    with TestClient(_app(gateway)) as client:
        capabilities = client.get("/web/sandbox/capabilities", headers=headers)
        client.post("/web/sandbox/sessions/remote-existing/connect", headers=headers)
        exported = client.get(
            "/web/sandbox/sessions/remote-existing/endpoint",
            headers=headers,
        )

    assert capabilities.json()["endpointExportEnabled"] is False
    assert exported.status_code == 403


def test_sandbox_persistent_create_requires_snapshot_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_CHAT_CODEX_SNAPSHOT", raising=False)
    gateway = _FakeGateway()
    with TestClient(_app(gateway, snapshot_tool_id=None)) as client:
        missing = client.post(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
        )
        temporary = client.post(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
            json={"persistent": False},
        )

    assert missing.status_code == 503
    assert "快照" in missing.text
    assert temporary.status_code == 200
    assert temporary.json()["persistent"] is False


def test_codex_project_handoff_pairing_creates_temporary_session_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frontend_sandbox._CODEX_PROJECT_HANDOFF_PAIRINGS.clear()
    gateway = _FakeGateway()

    with TestClient(_app(gateway)) as client:
        pairing = client.post(
            "/web/sandbox/codex-project-handoff/pairings",
            headers={
                "X-Test-User": "alice",
                "X-Test-Creator": "alice@example.com",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "studio.example.com",
            },
            json={"ttlSeconds": 120},
        )
        code = pairing.json()["pairingCode"]
        issued_status = client.get(
            f"/web/sandbox/codex-project-handoff/pairings/{code}",
            headers={"X-Test-User": "alice"},
        )
        foreign_status = client.get(
            f"/web/sandbox/codex-project-handoff/pairings/{code}",
            headers={"X-Test-User": "bob"},
        )
        created = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": code,
                "projectName": "My Repo",
                "agentName": "完善端云接力",
                "handoffId": "handoff-request-0001",
            },
        )
        created_status = client.get(
            f"/web/sandbox/codex-project-handoff/pairings/{code}",
            headers={"X-Test-User": "alice"},
        )
        reused = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": code,
                "projectName": "My Repo",
                "agentName": "完善端云接力",
                "handoffId": "handoff-request-0001",
            },
        )
        reused_with_different_payload = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": code,
                "projectName": "My Repo",
                "agentName": "另一个任务",
                "handoffId": "handoff-request-0001",
            },
        )
        conflicting = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": code,
                "projectName": "My Repo",
                "agentName": "另一个任务",
                "handoffId": "handoff-request-0002",
            },
        )
        continued = client.post(
            f"/web/sandbox/codex-project-handoff/sessions/{created.json()['sessionId']}/messages",
            json={
                "pairingCode": code,
                "history": [
                    {"role": "user", "content": "修复登录超时"},
                    {"role": "assistant", "content": "我已经定位到重试逻辑。"},
                ],
                "message": "继续",
            },
        )
        continued_twice = client.post(
            f"/web/sandbox/codex-project-handoff/sessions/{created.json()['sessionId']}/messages",
            json={
                "pairingCode": code,
                "message": "continue again",
            },
        )
        completed_status = client.get(
            f"/web/sandbox/codex-project-handoff/pairings/{code}",
            headers={"X-Test-User": "alice"},
        )
        listed = client.get(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
        )

    assert pairing.status_code == 200
    assert pairing.headers["cache-control"] == "no-store"
    assert pairing.json()["studioUrl"] == "https://studio.example.com"
    assert pairing.json()["expireAt"].endswith("Z")
    assert re.fullmatch(r"[2-9A-HJ-KM-NP-Z]{4}-[2-9A-HJ-KM-NP-Z]{4}", code)
    assert issued_status.status_code == 200
    assert issued_status.headers["cache-control"] == "no-store"
    assert issued_status.json()["state"] == "issued"
    assert foreign_status.status_code == 404
    assert created.status_code == 200
    assert created.headers["cache-control"] == "no-store"
    assert created.json()["sessionId"] == "remote-1"
    assert created.json()["displayName"] == "完善端云接力"
    assert created.json()["remoteRepoDir"] == "/home/gem/My-Repo"
    assert created.json()["endpoint"].endswith("Authorization=secret")
    assert created_status.status_code == 200
    assert created_status.json()["state"] == "session-created"
    assert created_status.json()["projectName"] == "My Repo"
    assert created_status.json()["agentName"] == "完善端云接力"
    assert created_status.json()["sessionId"] == "remote-1"
    assert reused.status_code == 200
    assert reused.json() == created.json()
    assert reused_with_different_payload.status_code == 200
    assert reused_with_different_payload.json() == created.json()
    assert conflicting.status_code == 403
    assert continued.status_code == 200
    assert '"stage": "connecting-session"' in continued.text
    assert '"stage": "importing-history"' in continued.text
    assert '"stage": "task-started"' in continued.text
    assert 'data: {"reason": "completed"}' in continued.text
    assert "reply:继续" not in continued.text
    assert continued_twice.status_code == 403
    assert completed_status.status_code == 200
    assert completed_status.json()["state"] == "completed"
    assert completed_status.json()["sessionId"] == "remote-1"
    assert gateway.sessions["remote-1"].tool_id == "tool-studio"
    assert gateway.sessions["remote-1"].created_by == "alice"
    assert gateway.sessions["remote-1"].creator_name == "alice@example.com"
    assert gateway.created == 1
    assert gateway.display_names == ["完善端云接力"]
    assert gateway.connections[0].cwd == "/home/gem/My-Repo"
    assert gateway.connections[0].imported_history == (
        CodexImportedMessage(role="user", content="修复登录超时"),
        CodexImportedMessage(role="assistant", content="我已经定位到重试逻辑。"),
    )
    assert gateway.connections[0].prompts == ["继续"]
    assert gateway.connections[0].permissions == CodexPermissionSettings(
        approval_policy="never",
        approvals_reviewer="auto_review",
        sandbox_mode="danger-full-access",
        network_access=True,
    )
    assert "Authorization=secret" not in listed.text


def test_codex_project_handoff_continuation_failure_reaches_edge_and_pairing() -> None:
    class _FailStreamGateway(_FakeGateway):
        async def open_codex(self, session: SandboxCloudSession) -> _FakeCodex:
            del session
            connection = _FakeCodex(self.thread_ids, fail=True)
            self.connections.append(connection)
            return connection

    frontend_sandbox._CODEX_PROJECT_HANDOFF_PAIRINGS.clear()
    with TestClient(_app(_FailStreamGateway())) as client:
        pairing = client.post(
            "/web/sandbox/codex-project-handoff/pairings",
            headers={"X-Test-User": "alice"},
        )
        code = pairing.json()["pairingCode"]
        created = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": code,
                "projectName": "Repo",
                "agentName": "继续失败任务",
                "handoffId": "handoff-request-failed-turn",
            },
        )
        continued = client.post(
            f"/web/sandbox/codex-project-handoff/sessions/{created.json()['sessionId']}/messages",
            json={"pairingCode": code, "message": "继续"},
        )
        status = client.get(
            f"/web/sandbox/codex-project-handoff/pairings/{code}",
            headers={"X-Test-User": "alice"},
        )

    assert continued.status_code == 200
    assert "event: error" in continued.text
    assert 'data: {"reason": "failed"}' in continued.text
    assert "failed" in continued.text
    assert status.json()["state"] == "failed"
    assert status.json()["failedStage"] == "continuing-task"
    assert status.json()["error"].startswith("failed")


def test_codex_project_handoff_first_event_timeout_interrupts_and_fails_pairing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StalledCodex(_FakeCodex):
        def __init__(self, turns: list[str]) -> None:
            super().__init__(turns)
            self.cancelled = False

        async def stream_turn(
            self, prompt: str, skill_ids: tuple[str, ...] = ()
        ) -> AsyncIterator[CodexAppServerEvent]:
            del prompt, skill_ids
            self.active = True
            self.workspace_locked = True
            try:
                await asyncio.Event().wait()
                if False:
                    yield CodexAppServerEvent()
            except asyncio.CancelledError as error:
                self.cancelled = True
                raise CodexAppServerError("cancelled while waiting") from error
            finally:
                self.active = False

    class _StalledGateway(_FakeGateway):
        async def open_codex(self, session: SandboxCloudSession) -> _FakeCodex:
            del session
            connection = _StalledCodex(self.thread_ids)
            self.connections.append(connection)
            return connection

    monkeypatch.setattr(
        frontend_sandbox,
        "_CODEX_PROJECT_HANDOFF_FIRST_EVENT_TIMEOUT_SECONDS",
        0.01,
    )
    frontend_sandbox._CODEX_PROJECT_HANDOFF_PAIRINGS.clear()
    gateway = _StalledGateway()
    with TestClient(_app(gateway)) as client:
        pairing = client.post(
            "/web/sandbox/codex-project-handoff/pairings",
            headers={"X-Test-User": "alice"},
        )
        code = pairing.json()["pairingCode"]
        created = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": code,
                "projectName": "Repo",
                "agentName": "连接超时任务",
                "handoffId": "handoff-request-stalled-turn",
            },
        )
        continued = client.post(
            f"/web/sandbox/codex-project-handoff/sessions/{created.json()['sessionId']}/messages",
            json={"pairingCode": code, "message": "继续"},
        )
        status = client.get(
            f"/web/sandbox/codex-project-handoff/pairings/{code}",
            headers={"X-Test-User": "alice"},
        )

    assert continued.status_code == 200
    assert "event: error" in continued.text
    assert 'data: {"reason": "failed"}' in continued.text
    assert "云端模型连接异常" in continued.text
    assert status.json()["state"] == "failed"
    assert status.json()["failedStage"] == "continuing-task"
    assert "云端模型连接异常" in status.json()["error"]
    assert gateway.connections[0].cancelled is True
    assert gateway.connections[0].active is False


def test_codex_project_handoff_upload_failure_is_visible_and_session_is_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frontend_sandbox._CODEX_PROJECT_HANDOFF_PAIRINGS.clear()
    gateway = _FakeGateway()

    with TestClient(_app(gateway)) as client:
        pairing = client.post(
            "/web/sandbox/codex-project-handoff/pairings",
            headers={"X-Test-User": "alice"},
        )
        code = pairing.json()["pairingCode"]
        payload = {
            "pairingCode": code,
            "projectName": "Large Repo",
            "agentName": "修复大包上传",
            "handoffId": "handoff-request-retry-0001",
        }
        created = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json=payload,
        )
        session_id = created.json()["sessionId"]
        failed = client.post(
            f"/web/sandbox/codex-project-handoff/sessions/{session_id}/status",
            json={
                "pairingCode": code,
                "handoffId": payload["handoffId"],
                "failedStage": "uploading-project",
                "error": "Sandbox upload could not connect to the service",
            },
        )
        failed_status = client.get(
            f"/web/sandbox/codex-project-handoff/pairings/{code}",
            headers={"X-Test-User": "alice"},
        )
        retried = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={**payload, "agentName": "继续大包上传"},
        )
        retried_status = client.get(
            f"/web/sandbox/codex-project-handoff/pairings/{code}",
            headers={"X-Test-User": "alice"},
        )

    assert failed.status_code == 200
    assert failed.headers["cache-control"] == "no-store"
    assert failed_status.json()["state"] == "failed"
    assert failed_status.json()["failedStage"] == "uploading-project"
    assert failed_status.json()["error"] == (
        "Sandbox upload could not connect to the service"
    )
    assert retried.status_code == 200
    assert retried.json() == created.json()
    assert retried_status.json()["state"] == "session-created"
    assert retried_status.json()["agentName"] == "修复大包上传"
    assert "failedStage" not in retried_status.json()
    assert gateway.created == 1


def test_codex_project_handoff_failure_status_rejects_mismatched_request() -> None:
    frontend_sandbox._CODEX_PROJECT_HANDOFF_PAIRINGS.clear()
    gateway = _FakeGateway()

    with TestClient(_app(gateway)) as client:
        pairing = client.post(
            "/web/sandbox/codex-project-handoff/pairings",
            headers={"X-Test-User": "alice"},
        )
        code = pairing.json()["pairingCode"]
        handoff_id = "handoff-request-status-0001"
        created = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": code,
                "projectName": "Repo",
                "agentName": "迁移项目",
                "handoffId": handoff_id,
            },
        )
        session_id = created.json()["sessionId"]
        wrong_handoff = client.post(
            f"/web/sandbox/codex-project-handoff/sessions/{session_id}/status",
            json={
                "pairingCode": code,
                "handoffId": "handoff-request-status-wrong",
                "failedStage": "restoring-project",
                "error": "restore failed",
            },
        )
        wrong_session = client.post(
            "/web/sandbox/codex-project-handoff/sessions/remote-wrong/status",
            json={
                "pairingCode": code,
                "handoffId": handoff_id,
                "failedStage": "restoring-project",
                "error": "restore failed",
            },
        )
        wrong_stage = client.post(
            f"/web/sandbox/codex-project-handoff/sessions/{session_id}/status",
            json={
                "pairingCode": code,
                "handoffId": handoff_id,
                "failedStage": "continuing-task",
                "error": "continue failed",
            },
        )

    assert wrong_handoff.status_code == 403
    assert wrong_session.status_code == 403
    assert wrong_stage.status_code == 422


def test_codex_project_handoff_session_accepts_custom_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frontend_sandbox._CODEX_PROJECT_HANDOFF_PAIRINGS.clear()
    gateway = _FakeGateway()

    with TestClient(_app(gateway)) as client:
        pairing = client.post(
            "/web/sandbox/codex-project-handoff/pairings",
            headers={"X-Test-User": "alice"},
        )
        created = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": pairing.json()["pairingCode"],
                "projectName": "codex-demo/project",
                "agentName": "迁移演示项目",
                "handoffId": "handoff-request-0003",
                "remoteHome": "/workspace/.",
            },
        )

    assert created.status_code == 200
    assert created.json()["displayName"] == "迁移演示项目"
    assert created.json()["remoteRepoDir"] == "/workspace/codex-demo-project"
    assert gateway.sessions[created.json()["sessionId"]].tool_id == "tool-studio"
    assert gateway.display_names == ["迁移演示项目"]


def test_codex_project_handoff_history_accepts_only_visible_messages() -> None:
    assert frontend_sandbox._codex_project_handoff_history(
        [
            {"role": "user", "content": " 继续修复问题 "},
            {"role": "assistant", "content": "已完成定位。"},
        ]
    ) == (
        CodexImportedMessage(role="user", content="继续修复问题"),
        CodexImportedMessage(role="assistant", content="已完成定位。"),
    )
    with pytest.raises(
        frontend_sandbox.SandboxValidationError,
        match="只支持用户和助手消息",
    ):
        frontend_sandbox._codex_project_handoff_history(
            [{"role": "developer", "content": "hidden instructions"}]
        )


def test_codex_project_handoff_history_accepts_bounded_images() -> None:
    assert frontend_sandbox._codex_project_handoff_history(
        [
            {
                "role": "user",
                "content": "请看图片",
                "images": [
                    {
                        "mimeType": "image/png",
                        "data": "iVBORw0KGgppbWFnZQ==",
                        "name": "handoff.png",
                        "alt": "端云接力界面",
                    }
                ],
            }
        ]
    ) == (
        CodexImportedMessage(
            role="user",
            content="请看图片",
            images=(
                CodexImportedImage(
                    mime_type="image/png",
                    data="iVBORw0KGgppbWFnZQ==",
                    name="handoff.png",
                    alt="端云接力界面",
                ),
            ),
        ),
    )


def test_public_thread_snapshot_preserves_validated_imported_image_data() -> None:
    image = CodexImportedImage(
        mime_type="image/png",
        data="iVBORw0KGgppbWFnZQ==",
        name="handoff.png",
        alt="端云接力界面",
    )
    snapshot = CodexThreadSnapshot(
        thread=CodexThreadSummary(id="thread-1"),
        messages=(
            CodexThreadMessage(
                id="message-1",
                role="user",
                content="请看图片",
                timestamp=1,
                images=(image,),
            ),
        ),
    )
    service = SandboxConversationService(_FakeGateway(), tool_id="tool-studio")
    session = SimpleNamespace(
        codex=SimpleNamespace(permissions=CodexPermissionSettings())
    )

    value = service._public_snapshot(session, snapshot)

    assert value["messages"][0]["images"] == [
        {
            "mimeType": "image/png",
            "data": "iVBORw0KGgppbWFnZQ==",
            "name": "handoff.png",
            "alt": "端云接力界面",
        }
    ]


def test_codex_project_handoff_rejects_invalid_and_expired_pairing_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frontend_sandbox._CODEX_PROJECT_HANDOFF_PAIRINGS.clear()
    gateway = _FakeGateway()

    with TestClient(_app(gateway)) as client:
        pairing = client.post(
            "/web/sandbox/codex-project-handoff/pairings",
            headers={"X-Test-User": "alice"},
            json={"ttlSeconds": 60},
        )
        code = pairing.json()["pairingCode"]
        tampered = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": f"{code}x",
                "projectName": "repo",
                "agentName": "迁移项目",
                "handoffId": "handoff-request-0004",
            },
        )
        invalid_request = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": code,
                "projectName": "repo",
                "agentName": "迁移项目",
                "handoffId": "handoff-request-0004",
                "persistent": True,
            },
        )
        invalid_name = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": code,
                "projectName": "repo",
                "agentName": "这是一个超过十二个字符的云端任务名称",
                "handoffId": "handoff-request-0004",
            },
        )
        expired_at = int(frontend_sandbox.time.time()) + 61
        monkeypatch.setattr(frontend_sandbox.time, "time", lambda: expired_at)
        expired = client.post(
            "/web/sandbox/codex-project-handoff/sessions",
            json={
                "pairingCode": code,
                "projectName": "repo",
                "agentName": "迁移项目",
                "handoffId": "handoff-request-0004",
            },
        )

    assert tampered.status_code == 403
    assert invalid_request.status_code == 422
    assert invalid_name.status_code == 422
    assert expired.status_code == 403
    assert gateway.created == 0


def test_sandbox_snapshot_is_wakeable_for_admin_only() -> None:
    gateway = _FakeGateway()
    gateway.snapshots["snapshot-alice"] = SandboxCloudSnapshot(
        tool_id="tool-studio-snapshot",
        snapshot_id="snapshot-alice",
        session_id="expired-alice",
        user_session_id="studio-01234567-89ab-cdef-0123-456789abcdef",
        region="cn-beijing",
        status="Ready",
        reason="Expired",
        created_at="2026-08-06T09:00:00Z",
        display_name="Alice Codex",
        created_by="alice",
    )
    gateway.snapshots["snapshot-bob"] = SandboxCloudSnapshot(
        tool_id="tool-studio-snapshot",
        snapshot_id="snapshot-bob",
        session_id="expired-bob",
        user_session_id="studio-fedcba98-7654-3210-fedc-ba9876543210",
        region="cn-beijing",
        status="Ready",
        reason="Expired",
        created_at="2026-08-05T09:00:00Z",
        display_name="Bob Codex",
        created_by="bob",
    )
    gateway.snapshots["snapshot-failed"] = SandboxCloudSnapshot(
        tool_id="tool-studio-snapshot",
        snapshot_id="snapshot-failed",
        session_id="failed-session",
        user_session_id="studio-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        region="cn-beijing",
        status="Failed",
        reason="Create failed",
        created_at="2026-08-06T10:00:00Z",
        display_name="Failed Codex",
        created_by="bob",
    )

    with TestClient(_app(gateway)) as client:
        alice_list = client.get(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
        )
        admin_list = client.get(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "admin", "X-Test-Role": "admin"},
        )
        resumed = client.post(
            "/web/sandbox/snapshots/snapshot-alice/resume",
            headers={"X-Test-User": "alice"},
        )
        admin_resumed = client.post(
            "/web/sandbox/snapshots/snapshot-alice/resume",
            headers={"X-Test-User": "admin", "X-Test-Role": "admin"},
        )
        deleted = client.delete(
            "/web/sandbox/snapshots/snapshot-bob",
            headers={"X-Test-User": "admin", "X-Test-Role": "admin"},
        )

    assert "snapshots" not in alice_list.json()
    assert {item["snapshotId"] for item in admin_list.json()["snapshots"]} == {
        "snapshot-alice",
        "snapshot-bob",
    }
    assert resumed.status_code == 404
    assert admin_resumed.json()["sessionId"] == "resumed-snapshot-alice"
    assert admin_resumed.json()["persistent"] is True
    assert deleted.json() == {"deleted": True}


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
    assert gateway.usernames[-7:] == [
        "alice",
        "alice",
        "bob",
        "bob",
        None,
        None,
        None,
    ]


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
        history = client.get(f"{root}/threads/thread-old", headers=headers)
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
        deleted_thread = client.post(
            f"{root}/threads/delete",
            headers=headers,
            json={"threadId": "thread-old"},
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
    assert history.json()["threadId"] == "thread-old"
    assert history.json()["messages"][0]["content"] == "restored"
    assert resumed.json()["messages"][0]["skillNames"] == ["review"]
    assert forked.json()["threadId"] == "thread-fork"
    assert compacted.json() == {"started": True}
    assert archived.json()["archived"] is True
    assert archived.json()["threadId"] == "thread-new"
    assert deleted_thread.json() == {"deleted": True}
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
    monkeypatch.delenv("SANDBOX_CHAT_CODEX_SNAPSHOT", raising=False)
    with TestClient(
        _app(_FakeGateway(), tool_id=None, snapshot_tool_id=None)
    ) as client:
        response = client.get(
            "/web/sandbox/capabilities", headers={"X-Test-User": "alice"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "reason": "",
        "persistentEnabled": False,
        "persistentReason": "管理员未配置快照版 Tool",
        "endpointExportEnabled": True,
    }


def test_sandbox_snapshot_tool_can_be_configured_by_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_CHAT_CODEX", "configured-tool")
    monkeypatch.setenv("SANDBOX_CHAT_CODEX_SNAPSHOT", "configured-snapshot-tool")
    gateway = _FakeGateway()
    with TestClient(_app(gateway, tool_id=None, snapshot_tool_id=None)) as client:
        created = client.post(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
        )

    assert created.status_code == 200
    assert created.json()["persistent"] is True
    assert gateway.sessions[created.json()["sessionId"]].tool_id == (
        "configured-snapshot-tool"
    )


def test_sandbox_capabilities_report_admin_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_CHAT_CODEX", raising=False)
    monkeypatch.delenv("SANDBOX_CHAT_CODEX_SNAPSHOT", raising=False)
    with TestClient(
        _app(_FakeGateway(), tool_id=None, snapshot_tool_id=None)
    ) as client:
        response = client.get(
            "/web/sandbox/capabilities", headers={"X-Test-User": "alice"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "reason": "管理员未配置",
        "persistentEnabled": False,
        "persistentReason": "管理员未配置快照版 Tool",
        "endpointExportEnabled": True,
    }


@pytest.mark.asyncio
async def test_sandbox_start_requires_preconfigured_chat_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_CHAT_CODEX", raising=False)
    monkeypatch.delenv("SANDBOX_CHAT_CODEX_SNAPSHOT", raising=False)
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
    service = SandboxConversationService(
        _FakeGateway(),
        tool_id="tool-studio",
        snapshot_tool_id="tool-studio-snapshot",
    )
    cloud = await service.create("alice")
    session = await service.connect(cloud.instance_id, "alice")

    with pytest.raises(SandboxSessionNotFoundError):
        await service.close(session.session_id, "bob")


@pytest.mark.asyncio
async def test_service_allows_multiple_sessions_for_the_same_owner() -> None:
    gateway = _FakeGateway()
    service = SandboxConversationService(
        gateway,
        tool_id="tool-studio",
        snapshot_tool_id="tool-studio-snapshot",
    )

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
        "deepseek-harness",
    )

    assert requests[0]["Metadata"] == [
        {"Key": "veadk_display_name", "Type": "String", "Value": "Alice Agent"},
        {"Key": "Username", "Type": "String", "Value": "alice"},
        {
            "Key": "veadk_creator_name",
            "Type": "String",
            "Value": "alice@example.com",
        },
        {
            "Key": "veadk_agent_kind",
            "Type": "String",
            "Value": "deepseek-harness",
        },
    ]
    assert session.created_by == "alice"
    assert session.creator_name == "alice@example.com"
    assert session.agent_kind == "deepseek-harness"


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

    service = SandboxConversationService(
        _FailDeleteGateway(),
        tool_id="tool-studio",
        snapshot_tool_id="tool-studio-snapshot",
    )
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


def test_sse_error_includes_redacted_exception_chain() -> None:
    class _CauseFailCodex(_FakeCodex):
        async def stream_turn(
            self, prompt: str, skill_ids: tuple[str, ...] = ()
        ) -> AsyncIterator[CodexAppServerEvent]:
            del prompt, skill_ids
            if False:
                yield CodexAppServerEvent()
            try:
                raise ConnectionError(
                    "socket write failed: Authorization=transport-secret"
                )
            except ConnectionError as error:
                raise CodexAppServerError(
                    "向 Codex app-server 发送请求失败。"
                ) from error

    class _CauseFailGateway(_FakeGateway):
        async def open_codex(self, session: SandboxCloudSession) -> _FakeCodex:
            del session
            connection = _CauseFailCodex(self.thread_ids)
            self.connections.append(connection)
            return connection

    with TestClient(_app(_CauseFailGateway())) as client:
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

    assert "向 Codex app-server 发送请求失败。" in response.text
    assert "Caused by ConnectionError: socket write failed" in response.text
    assert "transport-secret" not in response.text
    assert "Authorization=***" in response.text


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
