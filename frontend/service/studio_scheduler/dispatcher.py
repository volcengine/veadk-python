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
import logging
from collections.abc import Callable
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
Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)


class _RunControl(CancellationControl):
    def __init__(
        self,
        repository: SchedulerRepository,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._user_id = user_id
        self._job_id = job_id
        self._run_id = run_id
        self._clock = clock

    async def is_cancel_requested(self) -> bool:
        run = await self._repository.get_run(
            user_id=self._user_id,
            job_id=self._job_id,
            run_id=self._run_id,
        )
        return bool(run and run.cancel_requested)

    async def mark_acknowledged(self, session_id: str) -> None:
        run = await self._repository.get_run(
            user_id=self._user_id,
            job_id=self._job_id,
            run_id=self._run_id,
        )
        if run is None or run.state in {"succeeded", "failed", "cancelled", "skipped"}:
            return
        now = self._clock()
        await self._repository.update_run(
            replace(
                run,
                state="running",
                acknowledged=True,
                session_id=session_id or run.session_id,
                updated_at=now,
                started_at=run.started_at or now,
            )
        )


class Dispatcher:
    """Dispatch a single UTC minute without retaining in-memory schedule state."""

    def __init__(
        self,
        repository: SchedulerRepository,
        executor: RuntimeExecutor,
        *,
        replica_id: str,
        pre_ack_attempts: int = 2,
        ready_batch_size: int = 500,
        execution_concurrency: int = 8,
        clock: Clock | None = None,
    ) -> None:
        if not replica_id.strip():
            raise ValueError("replica_id must not be empty")
        if pre_ack_attempts < 1:
            raise ValueError("pre_ack_attempts must be positive")
        if ready_batch_size < 1:
            raise ValueError("ready_batch_size must be positive")
        if execution_concurrency < 1:
            raise ValueError("execution_concurrency must be positive")
        self._repository = repository
        self._executor = executor
        self._replica_id = replica_id
        self._pre_ack_attempts = pre_ack_attempts
        self._ready_batch_size = ready_batch_size
        self._execution_concurrency = execution_concurrency
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def dispatch_minute(self, now: datetime) -> DispatchSummary:
        """Copy one due bucket into the durable ready queue and return quickly."""
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("dispatch time must include a timezone")
        minute = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
        pointers = await self._repository.list_due(minute)
        outcomes = await asyncio.gather(
            *(self._enqueue_safely(pointer, minute) for pointer in pointers)
        )
        return DispatchSummary(
            scanned=len(pointers),
            queued=outcomes.count("started"),
            stale=outcomes.count("stale"),
            skipped=outcomes.count("skipped"),
            failed=outcomes.count("failed"),
        )

    async def _enqueue_safely(self, pointer: DuePointer, now: datetime) -> _Outcome:
        try:
            return await self._enqueue(pointer, now)
        except Exception:
            logger.exception(
                "Failed to enqueue scheduled run user=%s job=%s scheduled_at=%s",
                pointer.user_id,
                pointer.job_id,
                pointer.scheduled_at.isoformat(),
            )
            return "failed"

    async def _enqueue(self, pointer: DuePointer, now: datetime) -> _Outcome:
        if pointer.scheduled_at != now:
            return "stale"
        job = await self._repository.get_job(pointer.user_id, pointer.job_id)
        if not self._is_current(pointer, job):
            return "stale"
        assert job is not None

        await self._repository.put_ready(pointer)
        created_at = self._clock()
        run_id = deterministic_run_id(pointer)
        run = ScheduledRun(
            user_id=job.user_id,
            job_id=job.job_id,
            run_id=run_id,
            revision=job.revision,
            scheduled_at=pointer.scheduled_at,
            session_id=run_id,
            state="queued",
            created_at=created_at,
            updated_at=created_at,
        )
        await self._repository.create_run(run)
        await self._write_next_due(job, pointer)
        return "started"

    async def execute_ready(self, now: datetime | None = None) -> DispatchSummary:
        """Claim and execute a bounded ready batch independently from due scans."""
        observed = now or self._clock()
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("execution time must include a timezone")
        pointers = await self._repository.list_ready(self._ready_batch_size)
        semaphore = asyncio.Semaphore(self._execution_concurrency)

        async def execute(pointer: DuePointer) -> _Outcome:
            async with semaphore:
                return await self._execute_pointer(pointer)

        outcomes = await asyncio.gather(*(execute(pointer) for pointer in pointers))
        return DispatchSummary(
            scanned=len(pointers),
            started=outcomes.count("started"),
            stale=outcomes.count("stale"),
            skipped=outcomes.count("skipped"),
            failed=outcomes.count("failed"),
        )

    async def _execute_pointer(self, pointer: DuePointer) -> _Outcome:
        try:
            return await self._execute_pointer_inner(pointer)
        except Exception:
            logger.exception(
                "Failed to execute ready run user=%s job=%s scheduled_at=%s",
                pointer.user_id,
                pointer.job_id,
                pointer.scheduled_at.isoformat(),
            )
            return "failed"

    async def _execute_pointer_inner(self, pointer: DuePointer) -> _Outcome:
        now = self._clock()
        job = await self._repository.get_job(pointer.user_id, pointer.job_id)
        if not self._is_current(pointer, job):
            await self._terminalize_stale(pointer, now)
            await self._repository.delete_ready(pointer)
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
                await self._repository.delete_ready(pointer)
            return "skipped"

        try:
            if lock.abandoned_run_id:
                await self._mark_abandoned(job, lock.abandoned_run_id, now)
                if lock.abandoned_run_id == run_id:
                    await self._repository.delete_ready(pointer)
                    return "failed"

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
            if not await self._repository.create_run(run):
                existing = await self._repository.get_run(
                    user_id=run.user_id,
                    job_id=run.job_id,
                    run_id=run.run_id,
                )
                if existing is None:
                    raise RuntimeError(
                        "Scheduled run disappeared after create conflict"
                    )
                if existing.state in {"succeeded", "failed", "cancelled", "skipped"}:
                    await self._repository.delete_ready(pointer)
                    return "skipped"
                if existing.state != "queued":
                    await self._mark_abandoned(job, run_id, self._clock())
                    await self._repository.delete_ready(pointer)
                    return "failed"
                run = await self._repository.update_run(
                    replace(
                        existing,
                        state="preparing",
                        updated_at=self._clock(),
                        error="",
                    )
                )
            await self._write_next_due(job, pointer)
            outcome = await self._execute(job, run)
            terminal = await self._repository.get_run(
                user_id=run.user_id,
                job_id=run.job_id,
                run_id=run.run_id,
            )
            if terminal is None or terminal.state not in {
                "succeeded",
                "failed",
                "cancelled",
                "skipped",
            }:
                raise RuntimeError(
                    "Runtime execution ended without a durable terminal run"
                )
            await self._repository.delete_ready(pointer)
            return outcome
        # This is the durable failure boundary: unknown adapter/storage failures are
        # persisted and never retried as an already-acknowledged Runtime call.
        except Exception as error:  # noqa: BLE001
            existing = await self._repository.get_run(
                user_id=job.user_id,
                job_id=job.job_id,
                run_id=run_id,
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
                        updated_at=self._clock(),
                        completed_at=self._clock(),
                    )
                )
            terminal = await self._repository.get_run(
                user_id=job.user_id,
                job_id=job.job_id,
                run_id=run_id,
            )
            if terminal is not None and terminal.state in {
                "succeeded",
                "failed",
                "cancelled",
                "skipped",
            }:
                await self._repository.delete_ready(pointer)
            return "failed"
        finally:
            await self._repository.release_lock(
                user_id=job.user_id,
                job_id=job.job_id,
                run_id=run_id,
                released_at=self._clock(),
            )

    async def _execute(self, job: CronJob, run: ScheduledRun) -> _Outcome:
        control = _RunControl(
            self._repository,
            user_id=run.user_id,
            job_id=run.job_id,
            run_id=run.run_id,
            clock=self._clock,
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
                await self._finish(current, state="cancelled")
                return "started"
            current = await self._repository.update_run(
                replace(
                    current,
                    state="preparing" if attempt == 1 else "retrying",
                    attempt=attempt,
                    updated_at=self._clock(),
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
                        replace(current, state="retrying", updated_at=self._clock())
                    )
                    continue
                if await control.is_cancel_requested():
                    await self._finish(current, state="cancelled")
                else:
                    await self._finish(current, state="failed", error=str(error))
                return "started"
            # Providers may surface non-domain SDK exceptions. They are terminal;
            # only an explicit RuntimeInvocationError can opt into pre-ack retry.
            except Exception as error:  # noqa: BLE001
                detail = sanitize_diagnostic(error)
                await self._finish(
                    current,
                    state="failed",
                    error=(
                        "Runtime execution failed before a structured result was returned."
                        + (f" Detail: {detail}." if detail else "")
                        + " Check the scheduler and Runtime logs, then retry this run."
                    ),
                )
                return "started"

            if await control.is_cancel_requested():
                await self._finish(current, state="cancelled")
            else:
                await self._finish(
                    current,
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
        *,
        state: Literal["succeeded", "failed", "cancelled"],
        acknowledged: bool | None = None,
        output: str = "",
        runtime_version: str = "",
        session_id: str = "",
        error: str = "",
    ) -> ScheduledRun:
        now = self._clock()
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
        if await self._repository.create_run(run):
            return
        existing = await self._repository.get_run(
            user_id=pointer.user_id,
            job_id=pointer.job_id,
            run_id=run_id,
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
                    state="skipped",
                    error="Previous execution is still running",
                    updated_at=now,
                    completed_at=now,
                )
            )

    async def _terminalize_stale(self, pointer: DuePointer, now: datetime) -> None:
        run_id = deterministic_run_id(pointer)
        existing = await self._repository.get_run(
            user_id=pointer.user_id,
            job_id=pointer.job_id,
            run_id=run_id,
        )
        if existing is None or existing.state in {
            "succeeded",
            "failed",
            "cancelled",
            "skipped",
        }:
            return
        await self._repository.update_run(
            replace(
                existing,
                state="skipped",
                error="Task was changed, disabled, or deleted before execution",
                updated_at=now,
                completed_at=now,
            )
        )

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
                error=(
                    "Scheduler worker lease expired after Runtime acknowledgement; "
                    "the final Runtime outcome is unknown. Retry manually if needed."
                    if abandoned.acknowledged
                    else "Scheduler worker lease expired before Runtime acknowledgement."
                ),
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
