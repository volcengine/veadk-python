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
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
from typing import Protocol

from .models import (
    CredentialUpload,
    CreateTaskRequest,
    DEV_SANDBOX_TTL_SECONDS,
    INTENT_SUMMARY_PATH,
    IntentSummary,
    IntentSummaryUpdate,
    TaskEvent,
    TaskStage,
    TaskState,
    TaskStatus,
)


_TASK_ID_RE = re.compile(r"^vt-[0-9a-f]{12}-[0-9a-f]{24}$")


class VibeTaskError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class TaskRepository(Protocol):
    async def create(self, owner_id: str, status: TaskStatus) -> None: ...
    async def list(self, owner_id: str) -> list[TaskStatus]: ...
    async def get(self, owner_id: str, task_id: str) -> TaskStatus | None: ...
    async def save(self, owner_id: str, status: TaskStatus) -> None: ...
    async def delete(self, owner_id: str, task_id: str) -> bool: ...
    async def get_intent(self, owner_id: str, task_id: str) -> IntentSummary: ...
    async def save_intent(
        self, owner_id: str, task_id: str, summary: IntentSummary
    ) -> None: ...
    async def append_event(
        self, owner_id: str, task_id: str, event: TaskEvent
    ) -> None: ...
    async def events_after(
        self, owner_id: str, task_id: str, sequence: int
    ) -> list[TaskEvent]: ...
    async def store_credentials(
        self, owner_id: str, task_id: str, credentials: CredentialUpload
    ) -> None: ...
    async def delete_credentials(self, owner_id: str, task_id: str) -> None: ...


class InMemoryTaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[tuple[str, str], TaskStatus] = {}
        self._intents: dict[tuple[str, str], IntentSummary] = {}
        self._events: dict[tuple[str, str], list[TaskEvent]] = {}
        self._credentials: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    async def create(self, owner_id: str, status: TaskStatus) -> None:
        async with self._lock:
            key = (owner_id, status.task_id)
            if key in self._tasks:
                raise VibeTaskError("VIBE_TASK_EXISTS", "Task already exists", status_code=409)
            self._tasks[key] = status.model_copy(deep=True)
            self._intents[key] = IntentSummary(goal=status.goal).next_revision()
            self._events[key] = []

    async def list(self, owner_id: str) -> list[TaskStatus]:
        async with self._lock:
            return [v.model_copy(deep=True) for (owner, _), v in self._tasks.items() if owner == owner_id]

    async def get(self, owner_id: str, task_id: str) -> TaskStatus | None:
        async with self._lock:
            value = self._tasks.get((owner_id, task_id))
            return value.model_copy(deep=True) if value else None

    async def save(self, owner_id: str, status: TaskStatus) -> None:
        async with self._lock:
            self._tasks[(owner_id, status.task_id)] = status.model_copy(deep=True)

    async def delete(self, owner_id: str, task_id: str) -> bool:
        async with self._lock:
            key = (owner_id, task_id)
            existed = self._tasks.pop(key, None) is not None
            self._intents.pop(key, None)
            self._events.pop(key, None)
            self._credentials.discard(key)
            return existed

    async def get_intent(self, owner_id: str, task_id: str) -> IntentSummary:
        async with self._lock:
            value = self._intents.get((owner_id, task_id))
            if value is None:
                raise VibeTaskError("VIBE_TASK_NOT_FOUND", "Task not found", status_code=404)
            return value.model_copy(deep=True)

    async def save_intent(self, owner_id: str, task_id: str, summary: IntentSummary) -> None:
        async with self._lock:
            self._intents[(owner_id, task_id)] = summary.model_copy(deep=True)

    async def append_event(self, owner_id: str, task_id: str, event: TaskEvent) -> None:
        async with self._lock:
            self._events.setdefault((owner_id, task_id), []).append(event.model_copy(deep=True))

    async def events_after(self, owner_id: str, task_id: str, sequence: int) -> list[TaskEvent]:
        async with self._lock:
            return [e.model_copy(deep=True) for e in self._events.get((owner_id, task_id), []) if e.sequence > sequence]

    async def store_credentials(self, owner_id: str, task_id: str, credentials: CredentialUpload) -> None:
        del credentials
        async with self._lock:
            self._credentials.add((owner_id, task_id))

    async def delete_credentials(self, owner_id: str, task_id: str) -> None:
        async with self._lock:
            self._credentials.discard((owner_id, task_id))


class VibeTaskService:
    def __init__(
        self,
        repository: TaskRepository | None = None,
    ) -> None:
        self.repository = repository or InMemoryTaskRepository()
        self._conditions: dict[tuple[str, str], asyncio.Condition] = {}

    @staticmethod
    def _task_id(owner_id: str) -> str:
        owner_hash = hashlib.sha256(owner_id.encode()).hexdigest()[:12]
        return f"vt-{owner_hash}-{secrets.token_hex(12)}"

    @staticmethod
    def validate_task_owner(task_id: str, owner_id: str) -> None:
        owner_hash = hashlib.sha256(owner_id.encode()).hexdigest()[:12]
        if not _TASK_ID_RE.fullmatch(task_id) or task_id.split("-")[1] != owner_hash:
            raise VibeTaskError("VIBE_TASK_NOT_FOUND", "Task not found", status_code=404)

    async def create(self, owner_id: str, body: CreateTaskRequest) -> TaskStatus:
        now = datetime.now(timezone.utc)
        status = TaskStatus(
            task_id=self._task_id(owner_id),
            display_name=body.display_name or "Vibe Task",
            goal=body.goal,
            state=TaskState.READY,
            stage=TaskStage.UNDERSTANDING,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=DEV_SANDBOX_TTL_SECONDS)).isoformat(),
        )
        await self.repository.create(owner_id, status)
        self._conditions[(owner_id, status.task_id)] = asyncio.Condition()
        await self.emit(owner_id, status.task_id, "task.created", TaskStage.PROVISIONING, {"intentSummaryPath": INTENT_SUMMARY_PATH})
        return await self.require(owner_id, status.task_id)

    async def require(self, owner_id: str, task_id: str) -> TaskStatus:
        self.validate_task_owner(task_id, owner_id)
        status = await self.repository.get(owner_id, task_id)
        if status is None:
            raise VibeTaskError("VIBE_TASK_NOT_FOUND", "Task not found", status_code=404)
        return status

    async def list(self, owner_id: str) -> list[TaskStatus]:
        return sorted(await self.repository.list(owner_id), key=lambda item: item.created_at, reverse=True)

    async def configure_credentials(self, owner_id: str, task_id: str, body: CredentialUpload) -> TaskStatus:
        status = await self.require(owner_id, task_id)
        if status.terminal:
            raise VibeTaskError("VIBE_TASK_TERMINAL", "Task is terminal", status_code=409)
        await self.repository.store_credentials(owner_id, task_id, body)
        status = status.model_copy(update={"credentials_configured": True})
        await self.repository.save(owner_id, status)
        await self.emit(owner_id, task_id, "credentials.configured", status.stage, {})
        return status

    async def get_intent(self, owner_id: str, task_id: str) -> IntentSummary:
        await self.require(owner_id, task_id)
        return await self.repository.get_intent(owner_id, task_id)

    async def update_intent(self, owner_id: str, task_id: str, body: IntentSummaryUpdate) -> IntentSummary:
        status = await self.require(owner_id, task_id)
        if status.terminal:
            raise VibeTaskError("VIBE_TASK_TERMINAL", "Task is terminal", status_code=409)
        current = await self.repository.get_intent(owner_id, task_id)
        if body.expected_revision != current.revision:
            raise VibeTaskError("VIBE_INTENT_REVISION_CONFLICT", "Intent Summary is stale", status_code=409)
        updated = body.summary.model_copy(update={"revision": current.revision}).next_revision()
        await self.repository.save_intent(owner_id, task_id, updated)
        await self.repository.save(owner_id, status.model_copy(update={"intent_revision": updated.revision}))
        await self.emit(owner_id, task_id, "vibe.intent.updated", status.stage, {"revision": updated.revision})
        return updated

    async def emit(self, owner_id: str, task_id: str, event_type: str, stage: TaskStage, payload: dict[str, object]) -> TaskEvent:
        status = await self.require(owner_id, task_id)
        sequence = status.last_sequence + 1
        event = TaskEvent(
            sequence=sequence,
            event_type=event_type,
            stage=stage,
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload=payload,
        )
        await self.repository.append_event(owner_id, task_id, event)
        await self.repository.save(owner_id, status.model_copy(update={"last_sequence": sequence, "stage": stage}))
        condition = self._conditions.setdefault((owner_id, task_id), asyncio.Condition())
        async with condition:
            condition.notify_all()
        return event

    async def events(self, owner_id: str, task_id: str, after: int = 0) -> AsyncIterator[TaskEvent]:
        status = await self.require(owner_id, task_id)
        sequence = after
        while True:
            pending = await self.repository.events_after(owner_id, task_id, sequence)
            for event in pending:
                sequence = event.sequence
                yield event
            status = await self.require(owner_id, task_id)
            if status.terminal and sequence >= status.last_sequence:
                return
            condition = self._conditions.setdefault((owner_id, task_id), asyncio.Condition())
            try:
                async with condition:
                    await asyncio.wait_for(condition.wait(), timeout=15)
            except TimeoutError:
                yield TaskEvent(
                    sequence=sequence + 1,
                    event_type="heartbeat",
                    stage=status.stage,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    payload={},
                )
                sequence += 1

    async def stop(self, owner_id: str, task_id: str) -> TaskStatus:
        status = await self.require(owner_id, task_id)
        if status.terminal:
            return status
        await self.repository.delete_credentials(owner_id, task_id)
        status = status.model_copy(update={"state": TaskState.CANCELLED, "stage": TaskStage.DONE, "credentials_configured": False})
        await self.repository.save(owner_id, status)
        await self.emit(owner_id, task_id, "task.cancelled", TaskStage.DONE, {})
        return await self.require(owner_id, task_id)

    async def delete(self, owner_id: str, task_id: str) -> bool:
        self.validate_task_owner(task_id, owner_id)
        deleted = await self.repository.delete(owner_id, task_id)
        self._conditions.pop((owner_id, task_id), None)
        return deleted
