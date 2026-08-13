from __future__ import annotations

from uuid import UUID

import pytest

from frontend.server.vibe_task.models import (
    CreateTaskRequest,
    IntentSummary,
    TaskStage,
    TaskState,
    TaskStatus,
)
from frontend.server.vibe_task.remote_state import (
    EVENT_CHAIN_GENESIS,
    RemoteStatusProjection,
    RemoteTaskRequest,
    make_event_record,
    task_id_for,
)
from frontend.server.vibe_task.sandbox import VibeSandboxStore
from frontend.server.vibe_task.service import VibeTaskError
from veadk.cli.frontend_sandbox import SandboxCloudSession


class FakeGateway:
    def __init__(self) -> None:
        self.sessions: list[SandboxCloudSession] = []
        self.creates: list[dict[str, object]] = []
        self.deleted: list[SandboxCloudSession] = []

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
        session = _session(kwargs["user_session_id"], created_by=username)
        self.sessions.append(session)
        return session

    async def delete_session(self, session):
        self.deleted.append(session)
        self.sessions.remove(session)


class FakeTransport:
    snapshots: dict[str, dict[str, object]] = {}
    exec_json_calls: list[tuple[str, str, int]] = []
    exec_text_calls: list[tuple[str, str, int]] = []

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    async def exec_json(self, command: str, *, timeout: int = 12):
        self.exec_json_calls.append((self.endpoint, command, timeout))
        return self.snapshots[self.endpoint]

    async def exec_text(self, command: str, *, timeout: int = 12):
        self.exec_text_calls.append((self.endpoint, command, timeout))
        return ""


@pytest.fixture(autouse=True)
def fake_transport(monkeypatch):
    FakeTransport.snapshots = {}
    FakeTransport.exec_json_calls = []
    FakeTransport.exec_text_calls = []
    monkeypatch.setattr(
        "frontend.server.vibe_task.sandbox.SandboxRemoteTransport", FakeTransport
    )


def _session(
    task_id: str,
    *,
    instance_id: str = "session-1",
    endpoint: str = "https://sandbox.example",
    created_by: str = "owner",
) -> SandboxCloudSession:
    return SandboxCloudSession(
        tool_id="dev-tool",
        instance_id=instance_id,
        user_session_id=task_id,
        endpoint=endpoint,
        status="Ready",
        created_at="2026-08-13T00:00:00+00:00",
        expire_at="2026-08-13T08:00:00+00:00",
        created_by=created_by,
        workload="vibe-task",
        schema_version="1",
    )


def _snapshot(task_id: str, *, corrupt_events: bool = False) -> dict[str, object]:
    request = RemoteTaskRequest(
        taskId=task_id,
        requestId=UUID(int=1),
        goal="Build",
        displayName="Vibe Task",
    )
    event = make_event_record(
        task_id=task_id,
        sequence=1,
        previous_hash=EVENT_CHAIN_GENESIS,
        event_type="task.created",
        stage=TaskStage.PROVISIONING,
        timestamp="2026-08-13T00:00:00+00:00",
        payload={},
        projection=RemoteStatusProjection(
            state=TaskState.PROVISIONING,
            stage=TaskStage.PROVISIONING,
            intentRevision=1,
        ),
    )
    status = TaskStatus(
        taskId=task_id,
        displayName="Vibe Task",
        goal="Build",
        state=TaskState.PROVISIONING,
        stage=TaskStage.PROVISIONING,
        createdAt="2026-08-13T00:00:00+00:00",
        expiresAt="2026-08-13T08:00:00+00:00",
        lastSequence=1,
        intentRevision=1,
    )
    events = event.model_dump_json(by_alias=True) + "\n"
    if corrupt_events:
        events = events.replace('"eventType":"task.created"', '"eventType":"tampered"')
    return {
        "request": request.model_dump_json(by_alias=True),
        "status": status.model_dump_json(by_alias=True),
        "intent": IntentSummary(revision=1, goal="Build").model_dump_json(by_alias=True),
        "events": events,
    }


@pytest.mark.asyncio
async def test_create_is_idempotent_and_each_bootstrap_is_single_attempt() -> None:
    gateway = FakeGateway()
    store = VibeSandboxStore(gateway, "dev-tool")
    body = CreateTaskRequest(requestId=UUID(int=1), goal="Build")
    task_id = task_id_for("owner", body.request_id)
    FakeTransport.snapshots["https://sandbox.example"] = _snapshot(task_id)

    first = await store.create("owner", body)
    second = await store.create("owner", body)

    assert first.task_id == second.task_id == task_id
    assert len(gateway.creates) == 1
    assert gateway.creates[0]["ttl_seconds"] == 28_800
    assert len(FakeTransport.exec_text_calls) == 2
    assert all(call[2] == 30 for call in FakeTransport.exec_text_calls)
    assert len(FakeTransport.exec_json_calls) == 2
    assert all("request.json" in call[1] and "events.jsonl" in call[1] for call in FakeTransport.exec_json_calls)


@pytest.mark.asyncio
async def test_snapshot_reconstructs_reads_after_store_restart() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    gateway = FakeGateway()
    gateway.sessions = [_session(task_id)]
    FakeTransport.snapshots["https://sandbox.example"] = _snapshot(task_id)

    first_store = VibeSandboxStore(gateway, "dev-tool")
    assert (await first_store.get("owner", task_id)).last_sequence == 1

    restarted_store = VibeSandboxStore(gateway, "dev-tool")
    intent = await restarted_store.get_intent("owner", task_id)
    events = await restarted_store.events_after("owner", task_id, 0)

    assert intent == IntentSummary(revision=1, goal="Build")
    assert [(event.sequence, event.event_type) for event in events] == [(1, "task.created")]
    assert len(FakeTransport.exec_json_calls) == 3


@pytest.mark.asyncio
async def test_corrupt_event_log_fails_closed_for_all_reads() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    gateway = FakeGateway()
    gateway.sessions = [_session(task_id)]
    FakeTransport.snapshots["https://sandbox.example"] = _snapshot(
        task_id, corrupt_events=True
    )
    store = VibeSandboxStore(gateway, "dev-tool")

    for read in (
        lambda: store.get("owner", task_id),
        lambda: store.get_intent("owner", task_id),
        lambda: store.events_after("owner", task_id, 0),
    ):
        with pytest.raises(VibeTaskError) as caught:
            await read()
        assert caught.value.code == "VIBE_TASK_STATE_INVALID"
        assert caught.value.status_code == 502


@pytest.mark.asyncio
async def test_delete_resolves_owner_and_workload_identity_before_gateway() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    session = _session(task_id)
    gateway = FakeGateway()
    gateway.sessions = [
        session,
        _session(task_id, instance_id="foreign", created_by="other"),
        _session(task_id, instance_id="chat").__class__(
            **{**session.__dict__, "instance_id": "chat", "workload": "sandbox-chat"}
        ),
    ]
    store = VibeSandboxStore(gateway, "dev-tool")

    assert await store.delete("owner", task_id) is True
    assert gateway.deleted == [session]

    with pytest.raises(VibeTaskError) as caught:
        await store.delete("other", task_id)
    assert caught.value.code == "VIBE_TASK_NOT_FOUND"
    assert gateway.deleted == [session]


@pytest.mark.asyncio
async def test_list_filters_foreign_and_non_vibe_sessions() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    gateway = FakeGateway()
    good = _session(task_id, instance_id="good", endpoint="https://good")
    gateway.sessions = [
        good,
        _session(task_id, instance_id="foreign", endpoint="https://foreign", created_by="other"),
        good.__class__(**{**good.__dict__, "instance_id": "chat", "workload": "sandbox-chat"}),
    ]
    FakeTransport.snapshots["https://good"] = _snapshot(task_id)

    tasks = await VibeSandboxStore(gateway, "dev-tool").list("owner")

    assert [item.sandbox_session_id for item in tasks] == ["good"]
    assert [call[0] for call in FakeTransport.exec_json_calls] == ["https://good"]


def test_capability_is_truthful_without_tool() -> None:
    store = VibeSandboxStore(FakeGateway(), "")
    assert store.capabilities()["enabled"] is False
    assert store.capabilities()["stateSource"] == "dev-sandbox"
