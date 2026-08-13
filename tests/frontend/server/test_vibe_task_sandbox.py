from __future__ import annotations

import hashlib
import io
import json
from uuid import UUID
import zipfile

import pytest

from frontend.server.sandbox_remote import SandboxRemoteError
from frontend.server.vibe_task.models import (
    ArtifactInfo,
    CredentialUpload,
    CreateTaskRequest,
    IntentSummary,
    IntentSummaryUpdate,
    StopTaskRequest,
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
    upload_calls: list[tuple[str, str, bytes]] = []
    exec_error: Exception | None = None
    downloads: dict[str, bytes] = {}

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    async def exec_json(self, command: str, *, timeout: int = 12):
        self.exec_json_calls.append((self.endpoint, command, timeout))
        snapshot = self.snapshots[self.endpoint]
        if isinstance(snapshot, list):
            return snapshot.pop(0)
        return snapshot

    async def exec_text(self, command: str, *, timeout: int = 12):
        self.exec_text_calls.append((self.endpoint, command, timeout))
        if self.exec_error is not None:
            raise self.exec_error
        return ""

    async def upload(self, path: str, content: bytes, **kwargs):
        del kwargs
        self.upload_calls.append((self.endpoint, path, content))

    async def download(self, path: str, *, max_bytes: int):
        content = self.downloads[path]
        if len(content) > max_bytes:
            raise SandboxRemoteError("too large")
        return content


@pytest.fixture(autouse=True)
def fake_transport(monkeypatch):
    FakeTransport.snapshots = {}
    FakeTransport.exec_json_calls = []
    FakeTransport.exec_text_calls = []
    FakeTransport.upload_calls = []
    FakeTransport.exec_error = None
    FakeTransport.downloads = {}
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


def _snapshot(
    task_id: str,
    *,
    corrupt_events: bool = False,
    command_id: str = "",
    event_type: str = "task.created",
    state: TaskState = TaskState.PROVISIONING,
    intent_revision: int = 1,
    credentials_configured: bool = False,
    artifact: ArtifactInfo | None = None,
) -> dict[str, object]:
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
        event_type=event_type,
        stage=TaskStage.DONE if state is TaskState.CANCELLED else TaskStage.PROVISIONING,
        timestamp="2026-08-13T00:00:00+00:00",
        payload={"commandId": command_id} if command_id else {},
        projection=RemoteStatusProjection(
            state=state,
            stage=TaskStage.DONE if state is TaskState.CANCELLED else TaskStage.PROVISIONING,
            intentRevision=intent_revision,
            credentialsConfigured=credentials_configured,
            artifact=artifact,
        ),
    )
    status = TaskStatus(
        taskId=task_id,
        displayName="Vibe Task",
        goal="Build",
        state=state,
        stage=TaskStage.DONE if state is TaskState.CANCELLED else TaskStage.PROVISIONING,
        createdAt="2026-08-13T00:00:00+00:00",
        expiresAt="2026-08-13T08:00:00+00:00",
        lastSequence=1,
        intentRevision=intent_revision,
        credentialsConfigured=credentials_configured,
        artifact=artifact,
    )
    events = event.model_dump_json(by_alias=True) + "\n"
    if corrupt_events:
        events = events.replace('"eventType":"task.created"', '"eventType":"tampered"')
    return {
        "request": request.model_dump_json(by_alias=True),
        "status": status.model_dump_json(by_alias=True),
        "intent": IntentSummary(revision=intent_revision, goal="Build").model_dump_json(by_alias=True),
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
async def test_credentials_upload_secret_out_of_band_and_reconcile_unknown_outcome() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    command_id = UUID(int=9)
    gateway = FakeGateway()
    gateway.sessions = [_session(task_id)]
    FakeTransport.snapshots["https://sandbox.example"] = _snapshot(
        task_id,
        command_id=command_id.hex,
        event_type="credentials.configured",
        credentials_configured=True,
    )
    FakeTransport.exec_error = SandboxRemoteError("unknown", retryable=True)
    store = VibeSandboxStore(gateway, "dev-tool")

    status = await store.configure_credentials(
        "owner",
        task_id,
        CredentialUpload(
            commandId=command_id,
            accessKeyId="access-secret",
            secretAccessKey="secret-secret",
        ),
    )

    assert status.credentials_configured is True
    assert len(FakeTransport.exec_text_calls) == 1
    command = FakeTransport.exec_text_calls[0][1]
    assert "access-secret" not in command and "secret-secret" not in command
    assert f"chmod 600 -- /home/gem/.vibe/task/secrets/{command_id.hex}.json" in command
    assert FakeTransport.upload_calls[0][1].endswith(f"/{command_id.hex}.json")
    assert b"access-secret" in FakeTransport.upload_calls[0][2]


@pytest.mark.asyncio
async def test_update_intent_uses_cas_command_and_reconciles_snapshot() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    command_id = UUID(int=10)
    gateway = FakeGateway()
    gateway.sessions = [_session(task_id)]
    FakeTransport.snapshots["https://sandbox.example"] = _snapshot(
        task_id,
        command_id=command_id.hex,
        event_type="vibe.intent.updated",
        intent_revision=2,
    )
    store = VibeSandboxStore(gateway, "dev-tool")

    intent = await store.update_intent(
        "owner",
        task_id,
        IntentSummaryUpdate(
            commandId=command_id,
            expectedRevision=1,
            summary=IntentSummary(goal="Build"),
        ),
    )

    assert intent.revision == 2
    assert len(FakeTransport.exec_text_calls) == 1
    assert '"expectedRevision":1' in FakeTransport.exec_text_calls[0][1]


@pytest.mark.asyncio
async def test_stop_closes_runtime_before_remote_command() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    command_id = UUID(int=11)
    calls = []

    class Runtime:
        async def interrupt(self, owner, task):
            calls.append(("interrupt", owner, task))

        async def close(self, owner, task):
            calls.append(("close", owner, task))

    gateway = FakeGateway()
    gateway.sessions = [_session(task_id)]
    FakeTransport.snapshots["https://sandbox.example"] = _snapshot(
        task_id,
        command_id=command_id.hex,
        event_type="task.cancelled",
        state=TaskState.CANCELLED,
    )
    store = VibeSandboxStore(gateway, "dev-tool", runtime_manager=Runtime())

    status = await store.stop(
        "owner", task_id, StopTaskRequest(commandId=command_id)
    )

    assert status.state is TaskState.CANCELLED
    assert calls == [("interrupt", "owner", task_id), ("close", "owner", task_id)]
    assert FakeTransport.exec_text_calls == []


@pytest.mark.asyncio
async def test_stop_executes_once_after_runtime_cleanup() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    command_id = UUID(int=12)
    gateway = FakeGateway()
    gateway.sessions = [_session(task_id)]
    FakeTransport.snapshots["https://sandbox.example"] = [
        _snapshot(task_id),
        _snapshot(
            task_id,
            command_id=command_id.hex,
            event_type="task.cancelled",
            state=TaskState.CANCELLED,
        ),
    ]
    store = VibeSandboxStore(gateway, "dev-tool")

    status = await store.stop(
        "owner", task_id, StopTaskRequest(commandId=command_id, reason="user")
    )

    assert status.state is TaskState.CANCELLED
    assert len(FakeTransport.exec_text_calls) == 1
    assert '"commandType":"task.stop"' in FakeTransport.exec_text_calls[0][1]


@pytest.mark.asyncio
async def test_package_artifact_uploads_fixed_worker_and_returns_info() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    gateway = FakeGateway()
    gateway.sessions = [_session(task_id)]
    FakeTransport.snapshots["https://sandbox.example"] = _snapshot(task_id)
    FakeTransport.snapshots["https://sandbox.example"] = [
        _snapshot(task_id),
        {"revision": 1, "path": "/home/gem/.vibe/task/artifacts/1/artifact.zip", "sha256": "a" * 64, "size": 123},
    ]

    info = await VibeSandboxStore(gateway, "dev-tool").package_artifact(
        "owner", task_id, {name: value * 64 for name, value in zip(("runtime", "status", "invoke", "log"), "1234")}
    )

    assert info == ArtifactInfo(revision=1, sha256="a" * 64, size=123, filename="artifact.zip")
    assert [call[1] for call in FakeTransport.upload_calls] == [
        "/home/gem/.vibe/task/artifact-worker.py",
        "/home/gem/.vibe/task/artifact-request.json",
    ]
    request = json.loads(FakeTransport.upload_calls[1][2])
    assert request["taskId"] == task_id
    assert request["manifest"]["hashes"]["invoke"] == "3" * 64
    assert "frontend.server" not in FakeTransport.upload_calls[0][2].decode()


@pytest.mark.asyncio
async def test_download_artifact_validates_projected_descriptor_and_zip() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("artifact-manifest.json", "{}")
    content = buffer.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    artifact = ArtifactInfo(revision=1, sha256=digest, size=len(content), filename="artifact.zip")
    gateway = FakeGateway()
    gateway.sessions = [_session(task_id)]
    FakeTransport.snapshots["https://sandbox.example"] = _snapshot(task_id, artifact=artifact)
    FakeTransport.downloads = {
        "/home/gem/.vibe/task/artifacts/1/descriptor.json": json.dumps(
            {"revision": 1, "path": "/home/gem/.vibe/task/artifacts/1/artifact.zip", "sha256": digest, "size": len(content)}
        ).encode(),
        "/home/gem/.vibe/task/artifacts/1/artifact.zip": content,
    }
    store = VibeSandboxStore(gateway, "dev-tool")

    assert await store.download_artifact(
        "owner", task_id, expected_revision=1, expected_sha256=digest
    ) == content
    with pytest.raises(VibeTaskError) as caught:
        await store.download_artifact(
            "owner", task_id, expected_revision=1, expected_sha256="0" * 64
        )
    assert caught.value.code == "VIBE_ARTIFACT_VERSION_CONFLICT"


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
    FakeTransport.snapshots["https://sandbox.example"] = _snapshot(
        task_id, state=TaskState.CANCELLED, event_type="task.cancelled"
    )

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
