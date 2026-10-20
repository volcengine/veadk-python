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

"""In-memory repository for local invocation and deterministic service tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime

from .models import CronJob, DuePointer, JobLock, LockAttempt, ScheduledRun


class InMemorySchedulerRepository:
    """Process-local implementation of the same repository contract as TOS."""

    def __init__(self) -> None:
        self.jobs: dict[tuple[str, str], CronJob] = {}
        self.due: dict[tuple[str, str, datetime], DuePointer] = {}
        self.ready: dict[str, DuePointer] = {}
        self.runs: dict[tuple[str, str, str], ScheduledRun] = {}
        self.locks: dict[tuple[str, str], JobLock] = {}
        self._mutex = asyncio.Lock()

    async def put_job(self, job: CronJob) -> None:
        async with self._mutex:
            self.jobs[(job.user_id, job.job_id)] = job

    async def list_due(self, minute: datetime) -> list[DuePointer]:
        async with self._mutex:
            return sorted(
                (
                    pointer
                    for pointer in self.due.values()
                    if pointer.scheduled_at == minute
                ),
                key=lambda pointer: (pointer.user_id, pointer.job_id),
            )

    async def put_ready(self, pointer: DuePointer) -> bool:
        run_id = self._run_id(pointer)
        async with self._mutex:
            existing = self.ready.get(run_id)
            if existing is not None and existing != pointer:
                raise ValueError("Ready pointer already exists with different data")
            self.ready[run_id] = pointer
            return existing is None

    async def list_ready(self, limit: int) -> list[DuePointer]:
        if limit < 1:
            raise ValueError("Ready pointer limit must be positive")
        async with self._mutex:
            return sorted(
                self.ready.values(),
                key=lambda pointer: (
                    pointer.scheduled_at,
                    pointer.user_id,
                    pointer.job_id,
                ),
            )[:limit]

    async def delete_ready(self, pointer: DuePointer) -> None:
        async with self._mutex:
            self.ready.pop(self._run_id(pointer), None)

    async def get_job(self, user_id: str, job_id: str) -> CronJob | None:
        async with self._mutex:
            return self.jobs.get((user_id, job_id))

    async def put_due(self, pointer: DuePointer) -> bool:
        key = (pointer.user_id, pointer.job_id, pointer.scheduled_at)
        async with self._mutex:
            existing = self.due.get(key)
            if existing is not None and existing != pointer:
                raise ValueError("Due pointer already exists with different data")
            self.due[key] = pointer
            return existing is None

    async def acquire_lock(
        self,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
        replica_id: str,
        now: datetime,
        expires_at: datetime,
    ) -> LockAttempt:
        key = (user_id, job_id)
        requested = JobLock(
            run_id=run_id,
            replica_id=replica_id,
            state="held",
            acquired_at=now,
            expires_at=expires_at,
        )
        async with self._mutex:
            existing = self.locks.get(key)
            if existing and existing.state == "held" and existing.expires_at > now:
                return LockAttempt(acquired=False, active_run_id=existing.run_id)
            self.locks[key] = requested
            abandoned = (
                existing.run_id
                if existing is not None and existing.state == "held"
                else ""
            )
            return LockAttempt(acquired=True, abandoned_run_id=abandoned)

    async def release_lock(
        self,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
        released_at: datetime,
    ) -> None:
        key = (user_id, job_id)
        async with self._mutex:
            existing = self.locks.get(key)
            if existing and existing.run_id == run_id and existing.state == "held":
                self.locks[key] = replace(
                    existing,
                    state="released",
                    released_at=released_at,
                )

    async def create_run(self, run: ScheduledRun) -> bool:
        key = (run.user_id, run.job_id, run.run_id)
        async with self._mutex:
            existing = self.runs.get(key)
            if existing is not None:
                return False
            self.runs[key] = run
            return True

    async def update_run(self, run: ScheduledRun) -> ScheduledRun:
        key = (run.user_id, run.job_id, run.run_id)
        async with self._mutex:
            existing = self.runs[key]
            if existing.state in {"succeeded", "failed", "cancelled", "skipped"}:
                return existing
            merged = replace(
                run,
                cancel_requested=run.cancel_requested or existing.cancel_requested,
                acknowledged=run.acknowledged or existing.acknowledged,
                session_id=(
                    existing.session_id
                    if existing.acknowledged and existing.session_id
                    else run.session_id
                ),
                started_at=run.started_at or existing.started_at,
            )
            self.runs[key] = merged
            return merged

    async def get_run(
        self, *, user_id: str, job_id: str, run_id: str
    ) -> ScheduledRun | None:
        async with self._mutex:
            return self.runs.get((user_id, job_id, run_id))

    async def request_cancel(
        self,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
        requested_at: datetime,
    ) -> ScheduledRun | None:
        key = (user_id, job_id, run_id)
        async with self._mutex:
            existing = self.runs.get(key)
            if existing is None:
                return None
            updated = replace(
                existing,
                cancel_requested=True,
                updated_at=requested_at,
            )
            self.runs[key] = updated
            return updated

    @staticmethod
    def _run_id(pointer: DuePointer) -> str:
        from .models import deterministic_run_id

        return deterministic_run_id(pointer)
