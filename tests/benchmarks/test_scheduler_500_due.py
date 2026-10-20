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

"""Deterministic 500-pointer benchmark for the instance-free scheduler core."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from time import perf_counter_ns

import pytest

from frontend.service.studio_scheduler.dispatcher import Dispatcher
from frontend.service.studio_scheduler.models import (
    CronJob,
    DuePointer,
    ExecutionRequest,
    ExecutionResult,
    JobLock,
    LockAttempt,
    RuntimeTarget,
    Schedule,
    ScheduledRun,
    deterministic_run_id,
)
from frontend.service.studio_scheduler.ports import CancellationControl

_COUNT = 500
_NOW = datetime(2026, 8, 21, 1, 30, tzinfo=timezone.utc)
_TERMINAL_STATES = {"succeeded", "failed", "cancelled", "skipped"}


def _jobs_and_pointers() -> tuple[dict[tuple[str, str], CronJob], list[DuePointer]]:
    jobs: dict[tuple[str, str], CronJob] = {}
    pointers: list[DuePointer] = []
    for index in range(_COUNT):
        user_id = f"user-{index:04d}"
        job_id = f"job-{index:04d}"
        job = CronJob(
            user_id=user_id,
            job_id=job_id,
            revision=1,
            enabled=True,
            prompt=f"Execute benchmark task {index}",
            runtime=RuntimeTarget(
                provider="volcengine",
                runtime_id="runtime-benchmark",
                agent_name="benchmark_agent",
                region="cn-beijing",
            ),
            schedule=Schedule(
                kind="daily",
                timezone="UTC",
                hour=_NOW.hour,
                minute=_NOW.minute,
            ),
        )
        jobs[(user_id, job_id)] = job
        pointers.append(
            DuePointer(
                user_id=user_id,
                job_id=job_id,
                revision=job.revision,
                scheduled_at=_NOW,
            )
        )
    return jobs, pointers


class _BenchmarkRepository:
    """Concurrency-safe fake with lock, deduplication, and scan instrumentation."""

    def __init__(
        self,
        jobs: dict[tuple[str, str], CronJob],
        pointers: list[DuePointer],
    ) -> None:
        self.jobs = jobs
        self.pointers = pointers
        self.ready: dict[str, DuePointer] = {}
        self.runs: dict[tuple[str, str, str], ScheduledRun] = {}
        self.locks: dict[tuple[str, str], JobLock] = {}
        self.next_due: dict[tuple[str, str, datetime], DuePointer] = {}
        self.scan_durations_ns: list[int] = []
        self.scan_completed_ns: list[int] = []
        self.lock_attempts: Counter[tuple[str, str]] = Counter()
        self.lock_acquisitions: Counter[tuple[str, str]] = Counter()
        self.lock_denials: Counter[tuple[str, str]] = Counter()
        self.active_holders: Counter[tuple[str, str]] = Counter()
        self.max_active_holders: Counter[tuple[str, str]] = Counter()
        self.run_create_attempts: Counter[str] = Counter()
        self.queued_ns: dict[str, int] = {}
        self._mutex = asyncio.Lock()

    async def list_due(self, minute: datetime) -> list[DuePointer]:
        started = perf_counter_ns()
        result = [
            pointer for pointer in self.pointers if pointer.scheduled_at == minute
        ]
        self.scan_durations_ns.append(perf_counter_ns() - started)
        self.scan_completed_ns.append(perf_counter_ns())
        return result

    async def get_job(self, user_id: str, job_id: str) -> CronJob | None:
        return self.jobs.get((user_id, job_id))

    async def put_ready(self, pointer: DuePointer) -> bool:
        run_id = deterministic_run_id(pointer)
        async with self._mutex:
            existing = self.ready.get(run_id)
            self.ready[run_id] = pointer
            self.queued_ns.setdefault(run_id, perf_counter_ns())
            return existing is None

    async def list_ready(self, limit: int) -> list[DuePointer]:
        async with self._mutex:
            return sorted(
                self.ready.values(),
                key=lambda pointer: deterministic_run_id(pointer),
            )[:limit]

    async def delete_ready(self, pointer: DuePointer) -> None:
        async with self._mutex:
            self.ready.pop(deterministic_run_id(pointer), None)

    async def put_due(self, pointer: DuePointer) -> bool:
        key = (pointer.user_id, pointer.job_id, pointer.scheduled_at)
        async with self._mutex:
            existing = self.next_due.get(key)
            if existing is not None and existing != pointer:
                raise AssertionError("same due identity received different content")
            self.next_due[key] = pointer
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
        async with self._mutex:
            self.lock_attempts[key] += 1
            existing = self.locks.get(key)
            if existing and existing.state == "held" and existing.expires_at > now:
                self.lock_denials[key] += 1
                return LockAttempt(acquired=False, active_run_id=existing.run_id)
            self.locks[key] = JobLock(
                run_id=run_id,
                replica_id=replica_id,
                state="held",
                acquired_at=now,
                expires_at=expires_at,
            )
            self.lock_acquisitions[key] += 1
            self.active_holders[key] += 1
            self.max_active_holders[key] = max(
                self.max_active_holders[key], self.active_holders[key]
            )
            return LockAttempt(acquired=True)

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
            if existing and existing.state == "held" and existing.run_id == run_id:
                self.locks[key] = replace(
                    existing,
                    state="released",
                    released_at=released_at,
                )
                self.active_holders[key] -= 1

    async def create_run(self, run: ScheduledRun) -> bool:
        key = (run.user_id, run.job_id, run.run_id)
        async with self._mutex:
            self.run_create_attempts[run.run_id] += 1
            if key in self.runs:
                return False
            self.runs[key] = run
            return True

    async def update_run(self, run: ScheduledRun) -> ScheduledRun:
        key = (run.user_id, run.job_id, run.run_id)
        async with self._mutex:
            existing = self.runs[key]
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


class _BenchmarkExecutor:
    """Hold primary executions open while a second replica tests every lock."""

    def __init__(self, repository: _BenchmarkRepository) -> None:
        self._repository = repository
        self._release = asyncio.Event()
        self.all_started = asyncio.Event()
        self.requests: list[ExecutionRequest] = []
        self.started_ns: dict[str, int] = {}
        self.finished_ns: dict[str, int] = {}

    async def execute(
        self, request: ExecutionRequest, control: CancellationControl
    ) -> ExecutionResult:
        self.requests.append(request)
        self.started_ns[request.run_id] = perf_counter_ns()
        assert await control.is_cancel_requested() is False
        await control.mark_acknowledged(f"runtime-{request.run_id}")
        if len(self.requests) == _COUNT:
            self.all_started.set()
        await self._release.wait()
        self.finished_ns[request.run_id] = perf_counter_ns()
        return ExecutionResult(output=f"ok:{request.job_id}", runtime_version="bench")

    def release(self) -> None:
        self._release.set()


def _percentile_ms(samples_ns: list[int], percentile: float) -> float:
    ordered = sorted(samples_ns)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * percentile) - 1))
    return round(ordered[index] / 1_000_000, 3)


@pytest.mark.asyncio
async def test_500_due_pointers_finish_once_with_per_job_locking() -> None:
    jobs, pointers = _jobs_and_pointers()
    repository = _BenchmarkRepository(jobs, pointers)
    executor = _BenchmarkExecutor(repository)
    primary = Dispatcher(
        repository,
        executor,
        replica_id="benchmark-primary",
        ready_batch_size=_COUNT,
        execution_concurrency=_COUNT,
    )
    contender = Dispatcher(
        repository,
        executor,
        replica_id="benchmark-contender",
        ready_batch_size=_COUNT,
        execution_concurrency=_COUNT,
    )

    total_started_ns = perf_counter_ns()
    scan_started_ns = perf_counter_ns()
    scan_summary = await primary.dispatch_minute(_NOW)
    scan_finished_ns = perf_counter_ns()
    assert executor.requests == []

    primary_task = asyncio.create_task(primary.execute_ready(_NOW))
    contender_task = asyncio.create_task(contender.execute_ready(_NOW))
    try:
        await asyncio.wait_for(executor.all_started.wait(), timeout=10)
    finally:
        executor.release()
    primary_summary, contender_summary = await asyncio.gather(
        primary_task,
        contender_task,
    )
    total_finished_ns = perf_counter_ns()

    assert scan_summary.scanned == _COUNT
    assert scan_summary.queued == _COUNT
    assert scan_summary.failed == 0
    assert primary_summary.scanned == _COUNT
    assert contender_summary.scanned == _COUNT
    assert primary_summary.started + contender_summary.started == _COUNT
    assert primary_summary.failed == 0
    assert contender_summary.failed == 0

    expected_run_ids = {deterministic_run_id(pointer) for pointer in pointers}
    actual_run_ids = {run.run_id for run in repository.runs.values()}
    assert actual_run_ids == expected_run_ids
    assert len(repository.runs) == _COUNT
    assert all(run.state == "succeeded" for run in repository.runs.values())
    assert all(run.state in _TERMINAL_STATES for run in repository.runs.values())
    assert len(executor.requests) == _COUNT
    assert len({request.run_id for request in executor.requests}) == _COUNT
    assert repository.ready == {}
    assert all(count == 2 for count in repository.run_create_attempts.values())

    job_keys = set(jobs)
    assert set(repository.lock_attempts) == job_keys
    assert all(repository.lock_attempts[key] == 2 for key in job_keys)
    assert all(repository.lock_acquisitions[key] == 1 for key in job_keys)
    assert all(repository.lock_denials[key] == 1 for key in job_keys)
    assert all(repository.max_active_holders[key] == 1 for key in job_keys)
    assert all(repository.active_holders[key] == 0 for key in job_keys)
    assert all(lock.state == "released" for lock in repository.locks.values())

    assert len(repository.scan_durations_ns) == 1
    assert len(repository.scan_completed_ns) == 1
    queue_samples = [
        executor.started_ns[run_id] - repository.queued_ns[run_id]
        for run_id in executor.started_ns
    ]
    execute_samples = [
        executor.finished_ns[run_id] - started
        for run_id, started in executor.started_ns.items()
    ]
    assert len(queue_samples) == len(execute_samples) == _COUNT
    assert min(queue_samples) >= 0
    assert min(execute_samples) >= 0

    metrics = {
        "pointers": _COUNT,
        "scan_ms": round((scan_finished_ns - scan_started_ns) / 1_000_000, 3),
        "due_list_ms": round(repository.scan_durations_ns[0] / 1_000_000, 3),
        "scan_finished_before_runtime": all(
            started >= scan_finished_ns for started in executor.started_ns.values()
        ),
        "queue_ms": {
            "p50": _percentile_ms(queue_samples, 0.50),
            "p95": _percentile_ms(queue_samples, 0.95),
            "p99": _percentile_ms(queue_samples, 0.99),
            "max": round(max(queue_samples) / 1_000_000, 3),
        },
        "execute_ms": {
            "p50": _percentile_ms(execute_samples, 0.50),
            "p95": _percentile_ms(execute_samples, 0.95),
            "p99": _percentile_ms(execute_samples, 0.99),
            "max": round(max(execute_samples) / 1_000_000, 3),
        },
        "terminal_successes": sum(
            run.state == "succeeded" for run in repository.runs.values()
        ),
        "runtime_executions": len(executor.requests),
        "ready_remaining": len(repository.ready),
        "total_ms": round((total_finished_ns - total_started_ns) / 1_000_000, 3),
    }
    assert metrics["scan_finished_before_runtime"] is True
    print("scheduler_500_due_benchmark=" + json.dumps(metrics, sort_keys=True))
