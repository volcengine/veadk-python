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

"""Provider-neutral dependency contracts for the scheduler core."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .models import (
    CronJob,
    DuePointer,
    ExecutionRequest,
    ExecutionResult,
    LockAttempt,
    ProviderName,
    ScheduledRun,
)


class CancellationControl(Protocol):
    async def is_cancel_requested(self) -> bool:
        """Return the durable cancellation flag for the current run."""
        ...

    async def mark_acknowledged(self, session_id: str) -> None:
        """Persist that Runtime accepted the request before reading its result."""
        ...


class RuntimeProvider(Protocol):
    """Cloud adapter that invokes Runtime using its own service identity."""

    provider: ProviderName

    async def execute(
        self, request: ExecutionRequest, control: CancellationControl
    ) -> ExecutionResult: ...


class RuntimeExecutor(Protocol):
    async def execute(
        self, request: ExecutionRequest, control: CancellationControl
    ) -> ExecutionResult: ...


class SchedulerRepository(Protocol):
    async def list_due(self, minute: datetime) -> list[DuePointer]: ...

    async def put_ready(self, pointer: DuePointer) -> bool: ...

    async def list_ready(self, limit: int) -> list[DuePointer]: ...

    async def delete_ready(self, pointer: DuePointer) -> None: ...

    async def get_job(self, user_id: str, job_id: str) -> CronJob | None: ...

    async def put_due(self, pointer: DuePointer) -> bool: ...

    async def acquire_lock(
        self,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
        replica_id: str,
        now: datetime,
        expires_at: datetime,
    ) -> LockAttempt: ...

    async def release_lock(
        self,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
        released_at: datetime,
    ) -> None: ...

    async def create_run(self, run: ScheduledRun) -> bool: ...

    async def update_run(self, run: ScheduledRun) -> ScheduledRun: ...

    async def get_run(
        self, *, user_id: str, job_id: str, run_id: str
    ) -> ScheduledRun | None: ...

    async def request_cancel(
        self,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
        requested_at: datetime,
    ) -> ScheduledRun | None: ...
