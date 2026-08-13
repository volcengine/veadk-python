from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from frontend.server.vibe_task.models import CreateTaskRequest
from frontend.server.vibe_task.sandbox import VibeSandboxStore
from veadk.cli.frontend_sandbox import SandboxCloudSession


class FakeGateway:
    def __init__(self) -> None:
        self.sessions: list[SandboxCloudSession] = []
        self.creates: list[dict[str, object]] = []

    async def list_sessions(self, tool_id, username=None):
        del tool_id, username
        return self.sessions

    async def create_session(self, tool_id, display_name, username, creator_name, **kwargs):
        self.creates.append(
            {
                "tool_id": tool_id,
                "display_name": display_name,
                "username": username,
                "creator_name": creator_name,
                **kwargs,
            }
        )
        session = SandboxCloudSession(
            tool_id=tool_id,
            instance_id="session-1",
            user_session_id=kwargs["user_session_id"],
            endpoint="https://sandbox.example",
            status="Ready",
            created_at="2026-08-13T00:00:00+00:00",
            expire_at="2026-08-13T08:00:00+00:00",
            created_by=username,
            workload="vibe-task",
            schema_version="1",
        )
        self.sessions.append(session)
        return session


@pytest.mark.asyncio
async def test_create_is_idempotent_and_bootstraps_remote_status(monkeypatch) -> None:
    gateway = FakeGateway()
    store = VibeSandboxStore(gateway, "dev-tool")
    status_payload = None

    async def remote_exec(endpoint, command, *, timeout):
        nonlocal status_payload
        del endpoint, timeout
        if "request.json" in command:
            status_payload = command
            return ""
        assert status_payload is not None
        task_id = store._task_id if hasattr(store, "_task_id") else gateway.sessions[0].user_session_id
        return (
            '{"task_id":"%s","display_name":"Vibe Task","goal":"Build",'
            '"state":"provisioning","stage":"provisioning",'
            '"created_at":"2026-08-13T00:00:00+00:00",'
            '"expires_at":"2026-08-13T08:00:00+00:00",'
            '"sandbox_session_id":"session-1"}' % task_id
        )

    monkeypatch.setattr(store, "_exec", remote_exec)
    body = CreateTaskRequest(requestId=UUID(int=1), goal="Build")
    first = await store.create("owner", body)
    second = await store.create("owner", body)
    assert first.task_id == second.task_id
    assert len(gateway.creates) == 1
    assert gateway.creates[0]["ttl_seconds"] == 28_800
    assert gateway.creates[0]["user_session_id"] == first.task_id


@pytest.mark.asyncio
async def test_list_filters_foreign_and_non_vibe_sessions(monkeypatch) -> None:
    gateway = FakeGateway()
    store = VibeSandboxStore(gateway, "dev-tool")
    good = SandboxCloudSession(
        tool_id="dev-tool",
        instance_id="good",
        user_session_id="vt-4c1029697ee3-000000000000000000000000",
        endpoint="https://good",
        created_by="owner",
        workload="vibe-task",
        schema_version="1",
    )
    gateway.sessions = [
        good,
        good.__class__(**{**good.__dict__, "instance_id": "foreign", "created_by": "other"}),
        good.__class__(**{**good.__dict__, "instance_id": "chat", "workload": "sandbox-chat"}),
    ]

    async def read_status(session):
        return SimpleNamespace(created_at=session.instance_id)

    monkeypatch.setattr(store, "_read_status", read_status)
    tasks = await store.list("owner")
    assert [item.created_at for item in tasks] == ["good"]


def test_capability_is_truthful_without_tool() -> None:
    store = VibeSandboxStore(FakeGateway(), "")
    assert store.capabilities()["enabled"] is False
    assert store.capabilities()["stateSource"] == "dev-sandbox"
