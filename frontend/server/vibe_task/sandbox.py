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
from datetime import datetime, timedelta, timezone
import hashlib
import json
import shlex
from typing import Mapping, Protocol

from veadk.cli.agentkit_session_metadata import (
    SESSION_SCHEMA_VERSION_METADATA_KEY,
    SESSION_WORKLOAD_METADATA_KEY,
)
from veadk.cli.frontend_sandbox import (
    AgentkitSandboxGateway,
    SandboxCloudSession,
)

from ..sandbox_remote import SandboxRemoteError, SandboxRemoteTransport
from .artifacts import (
    ARTIFACT_REQUEST_PATH,
    ARTIFACT_WORKER_PATH,
    REMOTE_ARTIFACT_WORKER_SOURCE,
    ArtifactDescriptor,
    ArtifactError,
    ArtifactManifest,
    artifact_descriptor_path,
    download_and_validate_artifact,
    remote_artifact_request,
)
from .control import (
    CredentialsMarkerCommand,
    IntentUpdateCommand,
    REMOTE_SECRETS_ROOT,
    StopCommand,
    TransitionCommand,
    build_control_command,
)
from .models import (
    ArtifactInfo,
    CredentialUpload,
    CreateTaskRequest,
    DEV_SANDBOX_TTL_SECONDS,
    INTENT_SUMMARY_PATH,
    IntentSummary,
    IntentSummaryUpdate,
    StopTaskRequest,
    TaskEvent,
    TaskStage,
    TaskState,
    TaskStatus,
)
from .remote_state import (
    REMOTE_EVENTS_PATH,
    REMOTE_LOCK_PATH,
    REMOTE_REQUEST_PATH,
    REMOTE_STATUS_PATH,
    RemoteTaskRequest,
    build_bootstrap_command,
    project_status,
    replay_event_log,
    task_id_for,
)
from .service import VibeTaskError


VIBE_WORKLOAD = "vibe-task"
VIBE_SCHEMA_VERSION = "1"


class RuntimeManager(Protocol):
    async def interrupt(self, owner_id: str, task_id: str) -> None: ...
    async def close(self, owner_id: str, task_id: str) -> None: ...


class VibeSandboxStore:
    """Sandbox-backed boundary for discovering and reading Vibe tasks."""

    def __init__(
        self,
        gateway: AgentkitSandboxGateway,
        tool_id: str,
        *,
        runtime_manager: RuntimeManager | None = None,
    ) -> None:
        self.gateway = gateway
        self.tool_id = tool_id.strip()
        self.runtime_manager = runtime_manager

    def capabilities(self) -> dict[str, object]:
        return {
            "enabled": bool(self.tool_id),
            "reason": "" if self.tool_id else "管理员未配置 Dev Sandbox",
            "sandboxTtlSeconds": DEV_SANDBOX_TTL_SECONDS,
            "maxCloudAttempts": 3,
            "intentSummaryPath": INTENT_SUMMARY_PATH,
            "evaluationEnabled": False,
            "stateSource": "dev-sandbox",
        }

    @staticmethod
    def _is_vibe_session(session: SandboxCloudSession, owner_id: str) -> bool:
        return (
            session.created_by == owner_id
            and session.user_session_id.startswith("vt-")
            and session.workload == VIBE_WORKLOAD
            and session.schema_version == VIBE_SCHEMA_VERSION
        )

    async def _sessions(self, owner_id: str) -> list[SandboxCloudSession]:
        if not self.tool_id:
            raise VibeTaskError(
                "VIBE_DEV_SANDBOX_UNAVAILABLE",
                "管理员未配置 Dev Sandbox",
                status_code=503,
            )
        sessions = await self.gateway.list_sessions(self.tool_id, username=owner_id)
        return [item for item in sessions if self._is_vibe_session(item, owner_id)]

    async def find(self, owner_id: str, task_id: str) -> SandboxCloudSession:
        parts = task_id.split("-")
        expected_owner_hash = parts[1] if len(parts) == 3 else ""
        if expected_owner_hash != hashlib.sha256(owner_id.encode()).hexdigest()[:12]:
            raise VibeTaskError("VIBE_TASK_NOT_FOUND", "Task not found", status_code=404)
        matches = [
            item
            for item in await self._sessions(owner_id)
            if item.user_session_id == task_id
        ]
        if not matches:
            raise VibeTaskError("VIBE_TASK_NOT_FOUND", "Task not found", status_code=404)
        return max(matches, key=lambda item: (item.created_at, item.instance_id))

    async def create(
        self, owner_id: str, body: CreateTaskRequest, *, creator_name: str = ""
    ) -> TaskStatus:
        task_id = task_id_for(owner_id, body.request_id)
        try:
            session = await self.find(owner_id, task_id)
        except VibeTaskError as error:
            if error.code != "VIBE_TASK_NOT_FOUND":
                raise
            session = await self.gateway.create_session(
                self.tool_id,
                body.display_name or "Vibe Task",
                owner_id,
                creator_name,
                user_session_id=task_id,
                ttl_seconds=DEV_SANDBOX_TTL_SECONDS,
                metadata={
                    SESSION_WORKLOAD_METADATA_KEY: VIBE_WORKLOAD,
                    SESSION_SCHEMA_VERSION_METADATA_KEY: VIBE_SCHEMA_VERSION,
                },
            )
        if not session.endpoint:
            raise VibeTaskError(
                "VIBE_TASK_INITIALIZING",
                "Dev Sandbox 正在初始化",
                status_code=409,
            )
        now = datetime.now(timezone.utc)
        expires_at = session.expire_at or (
            now + timedelta(seconds=DEV_SANDBOX_TTL_SECONDS)
        ).isoformat()
        status = TaskStatus(
            task_id=task_id,
            display_name=body.display_name or "Vibe Task",
            goal=body.goal,
            state=TaskState.PROVISIONING,
            stage=TaskStage.PROVISIONING,
            created_at=session.created_at or now.isoformat(),
            expires_at=expires_at,
            sandbox_session_id=session.instance_id,
        )
        request = RemoteTaskRequest(
            task_id=task_id,
            request_id=body.request_id,
            goal=body.goal,
            display_name=status.display_name,
        )
        await SandboxRemoteTransport(session.endpoint).exec_text(
            build_bootstrap_command(request.model_dump(by_alias=True), status),
            timeout=30,
        )
        return await self.get(owner_id, task_id)

    async def list(self, owner_id: str) -> list[TaskStatus]:
        async def hydrate(session: SandboxCloudSession) -> TaskStatus | None:
            try:
                status, _, _ = await self._snapshot(session)
                return status
            except (VibeTaskError, ValueError, SandboxRemoteError):
                return None

        results = await asyncio.gather(*(hydrate(item) for item in await self._sessions(owner_id)))
        return sorted(
            (item for item in results if item is not None),
            key=lambda item: item.created_at,
            reverse=True,
        )

    async def get(self, owner_id: str, task_id: str) -> TaskStatus:
        status, _, _ = await self._snapshot(await self.find(owner_id, task_id))
        return status

    async def get_intent(self, owner_id: str, task_id: str) -> IntentSummary:
        _, intent, _ = await self._snapshot(await self.find(owner_id, task_id))
        return intent

    async def events_after(
        self, owner_id: str, task_id: str, sequence: int
    ) -> list[TaskEvent]:
        if sequence < 0:
            raise ValueError("sequence must not be negative")
        _, _, events = await self._snapshot(await self.find(owner_id, task_id))
        return [event for event in events if event.sequence > sequence]

    async def _execute_control(
        self,
        session: SandboxCloudSession,
        command: IntentUpdateCommand | CredentialsMarkerCommand | StopCommand,
        *,
        prefix: str = "",
    ) -> tuple[TaskStatus, IntentSummary, list[TaskEvent]]:
        if not session.endpoint:
            raise VibeTaskError(
                "VIBE_TASK_INITIALIZING",
                "Dev Sandbox 正在初始化",
                status_code=409,
            )
        error: SandboxRemoteError | None = None
        try:
            await SandboxRemoteTransport(session.endpoint).exec_text(
                prefix + build_control_command(command), timeout=30
            )
        except SandboxRemoteError as caught:
            error = caught
            if not caught.retryable:
                raise VibeTaskError(
                    "VIBE_CONTROL_COMMAND_FAILED",
                    "Dev Sandbox control command failed",
                    status_code=502,
                ) from caught
        snapshot = await self._snapshot(session)
        if any(
            event.payload.get("commandId") == command.command_id
            for event in snapshot[2]
        ):
            return snapshot
        if isinstance(command, IntentUpdateCommand) and (
            snapshot[0].intent_revision != command.expected_revision
        ):
            raise VibeTaskError(
                "VIBE_INTENT_REVISION_CONFLICT",
                "Intent Summary is stale",
                status_code=409,
            ) from error
        if snapshot[0].terminal:
            raise VibeTaskError(
                "VIBE_TASK_TERMINAL", "Task is terminal", status_code=409
            ) from error
        raise VibeTaskError(
            "VIBE_CONTROL_COMMAND_FAILED",
            "Dev Sandbox control command failed",
            status_code=502,
        ) from error

    async def transition(
        self,
        owner_id: str,
        task_id: str,
        event_type: str,
        stage: TaskStage,
        *,
        payload: dict[str, object] | None = None,
        projection: dict[str, object] | None = None,
    ) -> TaskStatus:
        session = await self.find(owner_id, task_id)
        from uuid import uuid4

        command = TransitionCommand(
            commandId=uuid4().hex,
            taskId=task_id,
            commandType="task.transition",
            timestamp=datetime.now(timezone.utc).isoformat(),
            eventType=event_type,
            stage=stage.value,
            payload=payload or {},
            projection=projection or {},
        )
        status, _, _ = await self._execute_control(session, command)
        return status

    async def configure_credentials(
        self, owner_id: str, task_id: str, body: CredentialUpload
    ) -> TaskStatus:
        session = await self.find(owner_id, task_id)
        command_id = body.command_id.hex
        secret_path = f"{REMOTE_SECRETS_ROOT}/{command_id}.json"
        secret = json.dumps(
            {
                "accessKeyId": body.access_key_id.get_secret_value(),
                "secretAccessKey": body.secret_access_key.get_secret_value(),
                "sessionToken": (
                    body.session_token.get_secret_value() if body.session_token else None
                ),
            },
            separators=(",", ":"),
        ).encode()
        transport = SandboxRemoteTransport(session.endpoint)
        await transport.upload(secret_path, secret, media_type="application/json")
        command = CredentialsMarkerCommand(
            commandId=command_id,
            taskId=task_id,
            commandType="credentials.marker",
            timestamp=datetime.now(timezone.utc).isoformat(),
            secretRelativePath=f"secrets/{command_id}.json",
        )
        status, _, _ = await self._execute_control(
            session,
            command,
            prefix=f"chmod 600 -- {secret_path} && ",
        )
        return status

    async def update_intent(
        self, owner_id: str, task_id: str, body: IntentSummaryUpdate
    ) -> IntentSummary:
        session = await self.find(owner_id, task_id)
        summary = body.summary.model_copy(
            update={"revision": body.expected_revision}
        ).next_revision()
        command = IntentUpdateCommand(
            commandId=body.command_id.hex,
            taskId=task_id,
            commandType="intent.update",
            timestamp=datetime.now(timezone.utc).isoformat(),
            expectedRevision=body.expected_revision,
            summary=summary,
        )
        _, intent, _ = await self._execute_control(session, command)
        return intent

    async def _close_runtime(self, owner_id: str, task_id: str) -> None:
        if self.runtime_manager is None:
            return
        try:
            await self.runtime_manager.interrupt(owner_id, task_id)
            await self.runtime_manager.close(owner_id, task_id)
        except Exception as error:
            if getattr(error, "code", "") != "VIBE_RUNTIME_NOT_CONNECTED":
                raise

    async def stop(
        self, owner_id: str, task_id: str, body: StopTaskRequest
    ) -> TaskStatus:
        session = await self.find(owner_id, task_id)
        await self._close_runtime(owner_id, task_id)
        status, _, _ = await self._snapshot(session)
        if status.terminal:
            return status
        command = StopCommand(
            commandId=body.command_id.hex,
            taskId=task_id,
            commandType="task.stop",
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=body.reason,
        )
        status, _, _ = await self._execute_control(session, command)
        return status

    async def package_artifact(
        self,
        owner_id: str,
        task_id: str,
        evidence_hashes: Mapping[str, str],
    ) -> ArtifactInfo:
        session = await self.find(owner_id, task_id)
        status, intent, _ = await self._snapshot(session)
        if status.terminal:
            raise VibeTaskError("VIBE_TASK_TERMINAL", "Task is terminal", status_code=409)
        expected = {"runtime", "status", "invoke", "log"}
        if set(evidence_hashes) != expected:
            raise VibeTaskError(
                "VIBE_ARTIFACT_EVIDENCE_INVALID",
                "Artifact evidence hashes are invalid",
                status_code=400,
            )
        try:
            manifest = ArtifactManifest(
                revision=1,
                intent_revision=intent.revision,
                runtime_sha256=evidence_hashes["runtime"],
                status_sha256=evidence_hashes["status"],
                invoke_sha256=evidence_hashes["invoke"],
                log_sha256=evidence_hashes["log"],
            )
            request = remote_artifact_request(task_id, manifest)
        except (ArtifactError, KeyError, TypeError) as error:
            raise VibeTaskError(
                "VIBE_ARTIFACT_EVIDENCE_INVALID",
                "Artifact evidence hashes are invalid",
                status_code=400,
            ) from error
        transport = SandboxRemoteTransport(session.endpoint)
        await transport.upload(
            ARTIFACT_WORKER_PATH,
            REMOTE_ARTIFACT_WORKER_SOURCE.encode(),
            media_type="text/x-python",
        )
        await transport.upload(
            ARTIFACT_REQUEST_PATH, request, media_type="application/json"
        )
        try:
            value = await transport.exec_json(
                f"python3 {ARTIFACT_WORKER_PATH} {ARTIFACT_REQUEST_PATH}", timeout=120
            )
            descriptor = ArtifactDescriptor.from_mapping(value)
        except (ArtifactError, SandboxRemoteError, ValueError, TypeError) as error:
            raise VibeTaskError(
                "VIBE_ARTIFACT_PACKAGE_FAILED",
                "Artifact packaging failed",
                status_code=502,
            ) from error
        return ArtifactInfo(
            revision=descriptor.revision,
            sha256=descriptor.sha256,
            size=descriptor.size,
            filename="artifact.zip",
        )

    async def download_artifact(
        self,
        owner_id: str,
        task_id: str,
        *,
        expected_revision: int,
        expected_sha256: str,
    ) -> bytes:
        session = await self.find(owner_id, task_id)
        status, _, _ = await self._snapshot(session)
        artifact = status.artifact
        if (
            artifact is None
            or artifact.revision != expected_revision
            or artifact.sha256 != expected_sha256
        ):
            raise VibeTaskError(
                "VIBE_ARTIFACT_VERSION_CONFLICT",
                "Artifact revision or digest is stale",
                status_code=409,
            )
        transport = SandboxRemoteTransport(session.endpoint)
        try:
            descriptor_value = json.loads(
                (
                    await transport.download(
                        artifact_descriptor_path(expected_revision), max_bytes=1024
                    )
                ).decode("utf-8")
            )
            if not isinstance(descriptor_value, dict):
                raise ArtifactError("Artifact descriptor is invalid")
            descriptor = ArtifactDescriptor.from_mapping(descriptor_value)
            if (
                descriptor.revision != artifact.revision
                or descriptor.sha256 != artifact.sha256
                or descriptor.size != artifact.size
            ):
                raise ArtifactError("Artifact descriptor does not match projection")
            return await download_and_validate_artifact(transport, descriptor)
        except (ArtifactError, SandboxRemoteError, UnicodeDecodeError, ValueError) as error:
            raise VibeTaskError(
                "VIBE_ARTIFACT_INVALID",
                "Artifact failed integrity validation",
                status_code=502,
            ) from error

    async def delete(self, owner_id: str, task_id: str) -> bool:
        session = await self.find(owner_id, task_id)
        await self.stop(owner_id, task_id, StopTaskRequest())
        await SandboxRemoteTransport(session.endpoint).exec_text(
            f"rm -rf -- {REMOTE_SECRETS_ROOT}", timeout=15
        )
        await self.gateway.delete_session(session)
        return True

    async def _snapshot(
        self, session: SandboxCloudSession
    ) -> tuple[TaskStatus, IntentSummary, list[TaskEvent]]:
        if not session.endpoint:
            raise VibeTaskError(
                "VIBE_TASK_INITIALIZING",
                "Dev Sandbox 正在初始化",
                status_code=409,
            )
        source = f"""import fcntl
import json
from pathlib import Path
def read(path, required=True):
    try:
        return Path(path).read_text(encoding=\"utf-8\")
    except FileNotFoundError:
        if required:
            raise
        return None
with open({REMOTE_LOCK_PATH!r}, \"a+\") as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
    snapshot = {{
        \"request\": read({REMOTE_REQUEST_PATH!r}),
        \"status\": read({REMOTE_STATUS_PATH!r}),
        \"intent\": read({INTENT_SUMMARY_PATH!r}, required=False),
        \"events\": read({REMOTE_EVENTS_PATH!r}),
    }}
print(json.dumps(snapshot, separators=(\",\", \":\")))
"""
        try:
            snapshot = await SandboxRemoteTransport(session.endpoint).exec_json(
                f"python3 -c {shlex.quote(source)}", timeout=15
            )
            request_value = snapshot.get("request")
            status_value = snapshot.get("status")
            intent_value = snapshot.get("intent")
            events_value = snapshot.get("events")
            if not all(isinstance(value, str) for value in (request_value, status_value, events_value)):
                raise ValueError("snapshot is missing required state")
            request = RemoteTaskRequest.model_validate_json(request_value)
            status = TaskStatus.model_validate_json(status_value)
            replay = replay_event_log(events_value, expected_task_id=session.user_session_id)
            if request.task_id != session.user_session_id or status.task_id != session.user_session_id:
                raise ValueError("snapshot task identity does not match session")
            initial = TaskStatus(
                task_id=request.task_id,
                display_name=request.display_name or "Vibe Task",
                goal=request.goal,
                state=TaskState.PROVISIONING,
                stage=TaskStage.PROVISIONING,
                created_at=status.created_at,
                expires_at=status.expires_at,
                sandbox_session_id=session.instance_id,
            )
            projected = project_status(initial, replay.events)
            comparable_fields = (
                "state",
                "stage",
                "attempt",
                "last_sequence",
                "credentials_configured",
                "intent_revision",
                "validation_runtime_id",
                "validation_runtime_status",
                "artifact",
                "warnings",
                "error",
            )
            if any(
                getattr(status, field) != getattr(projected, field)
                for field in comparable_fields
            ):
                raise ValueError("status projection does not match event log")
            if intent_value is None:
                intent = IntentSummary(
                    revision=status.intent_revision,
                    goal=request.goal,
                )
            elif isinstance(intent_value, str):
                intent = IntentSummary.model_validate_json(intent_value)
            else:
                raise ValueError("snapshot intent is invalid")
            if intent.revision != status.intent_revision:
                raise ValueError("intent revision does not match status")
        except VibeTaskError:
            raise
        except (ValueError, TypeError, SandboxRemoteError) as error:
            raise VibeTaskError(
                "VIBE_TASK_STATE_INVALID",
                "Dev Sandbox 中的 Vibe Task 状态无效",
                status_code=502,
            ) from error
        return (
            projected.model_copy(update={"sandbox_session_id": session.instance_id}),
            intent,
            [record.event for record in replay.events],
        )
