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

"""One-shot dispatcher invoked once per minute by the cloud trigger."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Literal

from .diagnostics import sanitize_diagnostic
from .models import (
    CronJob,
    DispatchSummary,
    DuePointer,
    ExecutionRequest,
    RuntimeInvocationError,
    ScheduledRun,
    deterministic_run_id,
)
from .ports import CancellationControl, RuntimeExecutor, SchedulerRepository
from .schedule import next_scheduled_time

_Outcome = Literal["started", "stale", "skipped", "failed"]


class _RunControl(CancellationControl):
    def __init__(
        self,
        repository: SchedulerRepository,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
    ) -> None:
        self._repository = repository
        self._user_id = user_id
        self._job_id = job_id
        self._run_id = run_id

    async def is_cancel_requested(self) -> bool:
        run = await self._repository.get_run(
            user_id=self._user_id,
            job_id=self._job_id,
            run_id=self._run_id,
        )
        return bool(run and run.cancel_requested)


class Dispatcher:
    """Dispatch a single UTC minute without retaining in-memory schedule state."""

    def __init__(
        self,
        repository: SchedulerRepository,
        executor: RuntimeExecutor,
        *,
        replica_id: str,
        pre_ack_attempts: int = 2,
    ) -> None:
        if not replica_id.strip():
            raise ValueError("replica_id must not be empty")
        if pre_ack_attempts < 1:
            raise ValueError("pre_ack_attempts must be positive")
        self._repository = repository
        self._executor = executor
        self._replica_id = replica_id
        self._pre_ack_attempts = pre_ack_attempts

    async def dispatch_minute(self, now: datetime) -> DispatchSummary:
        """List and process only the due bucket for ``now``; missed buckets stay missed."""
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("dispatch time must include a timezone")
        minute = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
        pointers = await self._repository.list_due(minute)
        outcomes = await asyncio.gather(
            *(self._dispatch(pointer, minute) for pointer in pointers)
        )
        return DispatchSummary(
            scanned=len(pointers),
            started=outcomes.count("started"),
            stale=outcomes.count("stale"),
            skipped=outcomes.count("skipped"),
            failed=outcomes.count("failed"),
        )

    async def _dispatch(self, pointer: DuePointer, now: datetime) -> _Outcome:
        if pointer.scheduled_at != now:
            return "stale"
        job = await self._repository.get_job(pointer.user_id, pointer.job_id)
        if not self._is_current(pointer, job):
            return "stale"
        assert job is not None

        run_id = deterministic_run_id(pointer)
        lock = await self._repository.acquire_lock(
            user_id=job.user_id,
            job_id=job.job_id,
            run_id=run_id,
            replica_id=self._replica_id,
            now=now,
            expires_at=now + timedelta(seconds=job.max_runtime_seconds),
        )
        if not lock.acquired:
            if lock.active_run_id != run_id:
                await self._record_skipped(pointer, now, run_id)
                await self._write_next_due(job, pointer)
            return "skipped"

        if lock.abandoned_run_id:
            await self._mark_abandoned(job, lock.abandoned_run_id, now)

        run = ScheduledRun(
            user_id=job.user_id,
            job_id=job.job_id,
            run_id=run_id,
            revision=job.revision,
            scheduled_at=pointer.scheduled_at,
            session_id=run_id,
            state="preparing",
            created_at=now,
            updated_at=now,
        )
        try:
            if not await self._repository.create_run(run):
                existing = await self._repository.get_run(
                    user_id=run.user_id,
                    job_id=run.job_id,
                    run_id=run.run_id,
                )
                if existing is None or existing.state != "queued":
                    return "skipped"
                run = await self._repository.update_run(
                    replace(
                        existing,
                        state="preparing",
                        updated_at=now,
                        error="",
                    )
                )
            await self._write_next_due(job, pointer)
            return await self._execute(job, run, now)
        # This is the durable failure boundary: unknown adapter/storage failures are
        # persisted and never retried as an already-acknowledged Runtime call.
        except Exception as error:  # noqa: BLE001
            existing = await self._repository.get_run(
                user_id=run.user_id,
                job_id=run.job_id,
                run_id=run.run_id,
            )
            if existing is not None and existing.state not in {
                "succeeded",
                "failed",
                "cancelled",
                "skipped",
            }:
                await self._repository.update_run(
                    replace(
                        existing,
                        state="failed",
                        error=str(error),
                        updated_at=now,
                        completed_at=now,
                    )
                )
            return "failed"
        finally:
            await self._repository.release_lock(
                user_id=job.user_id,
                job_id=job.job_id,
                run_id=run_id,
                released_at=now,
            )

    async def _execute(
        self, job: CronJob, run: ScheduledRun, now: datetime
    ) -> _Outcome:
        control = _RunControl(
            self._repository,
            user_id=run.user_id,
            job_id=run.job_id,
            run_id=run.run_id,
        )
        request = ExecutionRequest(
            run_id=run.run_id,
            session_id=run.session_id,
            user_id=run.user_id,
            job_id=run.job_id,
            prompt=job.prompt,
            runtime=job.runtime,
            timeout_seconds=job.max_runtime_seconds,
        )
        current = run
        for attempt in range(1, self._pre_ack_attempts + 1):
            if await control.is_cancel_requested():
                await self._finish(current, now, state="cancelled")
                return "started"
            current = await self._repository.update_run(
                replace(
                    current,
                    state="running" if attempt == 1 else "retrying",
                    attempt=attempt,
                    updated_at=now,
                    error="",
                )
            )
            try:
                result = await self._executor.execute(request, control)
            except RuntimeInvocationError as error:
                current = replace(
                    current,
                    acknowledged=error.acknowledged,
                    error=str(error),
                )
                can_retry = (
                    not error.acknowledged
                    and error.retryable
                    and attempt < self._pre_ack_attempts
                )
                if can_retry:
                    current = await self._repository.update_run(
                        replace(current, state="retrying", updated_at=now)
                    )
                    continue
                if await control.is_cancel_requested():
                    await self._finish(current, now, state="cancelled")
                else:
                    await self._finish(current, now, state="failed", error=str(error))
                return "started"
            # Providers may surface non-domain SDK exceptions. They are terminal;
            # only an explicit RuntimeInvocationError can opt into pre-ack retry.
            except Exception as error:  # noqa: BLE001
                detail = sanitize_diagnostic(error)
                await self._finish(
                    current,
                    now,
                    state="failed",
                    error=(
                        "Runtime execution failed before a structured result was returned."
                        + (f" Detail: {detail}." if detail else "")
                        + " Check the scheduler and Runtime logs, then retry this run."
                    ),
                )
                return "started"

            if await control.is_cancel_requested():
                await self._finish(current, now, state="cancelled")
            else:
                await self._finish(
                    current,
                    now,
                    state="succeeded",
                    acknowledged=True,
                    output=result.output,
                    runtime_version=result.runtime_version,
                    session_id=result.session_id or current.session_id,
                )
            return "started"
        return "failed"

    async def _finish(
        self,
        run: ScheduledRun,
        now: datetime,
        *,
        state: Literal["succeeded", "failed", "cancelled"],
        acknowledged: bool | None = None,
        output: str = "",
        runtime_version: str = "",
        session_id: str = "",
        error: str = "",
    ) -> ScheduledRun:
        return await self._repository.update_run(
            replace(
                run,
                state=state,
                acknowledged=(
                    run.acknowledged if acknowledged is None else acknowledged
                ),
                output=output,
                runtime_version=runtime_version,
                session_id=session_id or run.session_id,
                error=error,
                updated_at=now,
                completed_at=now,
            )
        )

    async def _write_next_due(self, job: CronJob, pointer: DuePointer) -> None:
        next_time = next_scheduled_time(job.schedule, pointer.scheduled_at)
        if next_time is None:
            return
        await self._repository.put_due(
            DuePointer(
                user_id=job.user_id,
                job_id=job.job_id,
                revision=job.revision,
                scheduled_at=next_time,
            )
        )

    async def _record_skipped(
        self, pointer: DuePointer, now: datetime, run_id: str
    ) -> None:
        run = ScheduledRun(
            user_id=pointer.user_id,
            job_id=pointer.job_id,
            run_id=run_id,
            revision=pointer.revision,
            scheduled_at=pointer.scheduled_at,
            session_id=run_id,
            state="skipped",
            created_at=now,
            updated_at=now,
            error="Previous execution is still running",
            completed_at=now,
        )
        await self._repository.create_run(run)

    async def _mark_abandoned(
        self, job: CronJob, abandoned_run_id: str, now: datetime
    ) -> None:
        abandoned = await self._repository.get_run(
            user_id=job.user_id,
            job_id=job.job_id,
            run_id=abandoned_run_id,
        )
        if abandoned is None or abandoned.state in {
            "succeeded",
            "failed",
            "cancelled",
            "skipped",
        }:
            return
        await self._repository.update_run(
            replace(
                abandoned,
                state="failed",
                error="Scheduler lease expired before completion",
                updated_at=now,
                completed_at=now,
            )
        )

    @staticmethod
    def _is_current(pointer: DuePointer, job: CronJob | None) -> bool:
        return bool(
            job
            and job.enabled
            and job.user_id == pointer.user_id
            and job.job_id == pointer.job_id
            and job.revision == pointer.revision
        )
