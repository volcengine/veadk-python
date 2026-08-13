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
import shlex
from typing import Any

import requests
from agentkit.toolkit.cli.sandbox.sandbox_client import build_exec_url

from veadk.cli.agentkit_session_metadata import (
    SESSION_SCHEMA_VERSION_METADATA_KEY,
    SESSION_WORKLOAD_METADATA_KEY,
)
from veadk.cli.frontend_sandbox import (
    AgentkitSandboxGateway,
    SandboxCloudSession,
)

from .models import (
    CreateTaskRequest,
    DEV_SANDBOX_TTL_SECONDS,
    TaskStage,
    TaskState,
    TaskStatus,
)
from .remote_state import (
    REMOTE_STATUS_PATH,
    RemoteTaskRequest,
    build_bootstrap_command,
    task_id_for,
)
from .service import VibeTaskError


VIBE_WORKLOAD = "vibe-task"
VIBE_SCHEMA_VERSION = "1"


class VibeSandboxStore:
    """Discover Vibe tasks from AgentKit and read state from their Sandbox."""

    def __init__(self, gateway: AgentkitSandboxGateway, tool_id: str) -> None:
        self.gateway = gateway
        self.tool_id = tool_id.strip()

    def capabilities(self) -> dict[str, object]:
        return {
            "enabled": bool(self.tool_id),
            "reason": "" if self.tool_id else "管理员未配置 Dev Sandbox",
            "sandboxTtlSeconds": DEV_SANDBOX_TTL_SECONDS,
            "maxCloudAttempts": 3,
            "intentSummaryPath": "/home/gem/.vibe/task/intent-summary.json",
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
        from hashlib import sha256

        if expected_owner_hash != sha256(owner_id.encode()).hexdigest()[:12]:
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
        await self._exec(
            session.endpoint,
            build_bootstrap_command(request.model_dump(by_alias=True), status),
            timeout=30,
        )
        return await self.get(owner_id, task_id)

    async def list(self, owner_id: str) -> list[TaskStatus]:
        async def hydrate(session: SandboxCloudSession) -> TaskStatus | None:
            try:
                return await self._read_status(session)
            except (VibeTaskError, ValueError, requests.RequestException):
                return None

        results = await asyncio.gather(*(hydrate(item) for item in await self._sessions(owner_id)))
        return sorted(
            (item for item in results if item is not None),
            key=lambda item: item.created_at,
            reverse=True,
        )

    async def get(self, owner_id: str, task_id: str) -> TaskStatus:
        return await self._read_status(await self.find(owner_id, task_id))

    async def _read_status(self, session: SandboxCloudSession) -> TaskStatus:
        source = (
            "import pathlib;"
            f"print(pathlib.Path({REMOTE_STATUS_PATH!r}).read_text(encoding='utf-8'))"
        )
        output = await self._exec(
            session.endpoint,
            f"python3 -c {shlex.quote(source)}",
            timeout=15,
        )
        try:
            status = TaskStatus.model_validate_json(output)
        except ValueError as error:
            raise VibeTaskError(
                "VIBE_TASK_STATE_INVALID",
                "Dev Sandbox 中的 Vibe Task 状态无效",
                status_code=502,
            ) from error
        if status.task_id != session.user_session_id:
            raise VibeTaskError(
                "VIBE_TASK_STATE_INVALID",
                "Dev Sandbox 中的 Vibe Task 身份不匹配",
                status_code=502,
            )
        return status.model_copy(
            update={"sandbox_session_id": session.instance_id}
        )

    @staticmethod
    async def _exec(endpoint: str, command: str, *, timeout: int) -> str:
        def invoke() -> str:
            response = requests.post(
                build_exec_url(endpoint),
                json={"id": "", "exec_dir": "/home/gem", "command": command},
                timeout=(5, timeout),
            )
            response.raise_for_status()
            payload: Any = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            output = data.get("output") if isinstance(data, dict) else None
            if not isinstance(output, str):
                raise ValueError("Dev Sandbox command returned no output")
            return output

        return await asyncio.to_thread(invoke)
