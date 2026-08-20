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
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from frontend.service.studio_scheduler.dispatcher import Dispatcher
from frontend.service.studio_scheduler.models import (
    CronJob,
    DuePointer,
    ExecutionRequest,
    ExecutionResult,
    LockAttempt,
    RuntimeInvocationError,
    RuntimeTarget,
    Schedule,
    ScheduledRun,
    deterministic_run_id,
)
from frontend.service.studio_scheduler.ports import CancellationControl

NOW = datetime(2026, 8, 20, 10, 35, tzinfo=timezone.utc)


def _job(*, revision: int = 3, enabled: bool = True) -> CronJob:
    return CronJob(
        user_id="user@example.com",
        job_id="daily-report",
        revision=revision,
        enabled=enabled,
        prompt="Summarize yesterday",
        runtime=RuntimeTarget(
            provider="volcengine",
            runtime_id="runtime-1",
            agent_name="reporter",
            region="cn-beijing",
            project_name="default",
        ),
        schedule=Schedule(kind="daily", timezone="UTC", hour=10, minute=35),
    )


def _pointer(*, revision: int = 3) -> DuePointer:
    return DuePointer(
        user_id="user@example.com",
        job_id="daily-report",
        revision=revision,
        scheduled_at=NOW,
    )


class _Repository:
    def __init__(self, pointers: list[DuePointer], job: CronJob | None) -> None:
        self.pointers = pointers
        self.job = job
        self.runs: dict[str, ScheduledRun] = {}
        self.lock_run_id: str | None = None
        self.listed_minutes: list[datetime] = []
        self.events: list[str] = []
        self.next_due: list[DuePointer] = []

    async def list_due(self, minute: datetime) -> list[DuePointer]:
        self.listed_minutes.append(minute)
        return self.pointers

    async def get_job(self, user_id: str, job_id: str) -> CronJob | None:
        return self.job

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
        if self.lock_run_id is not None:
            return LockAttempt(acquired=False, active_run_id=self.lock_run_id)
        self.lock_run_id = run_id
        self.events.append("lock")
        return LockAttempt(acquired=True)

    async def release_lock(
        self, *, user_id: str, job_id: str, run_id: str, released_at: datetime
    ) -> None:
        if self.lock_run_id == run_id:
            self.lock_run_id = None

    async def create_run(self, run: ScheduledRun) -> bool:
        if run.run_id in self.runs:
            return False
        self.runs[run.run_id] = run
        self.events.append("run")
        return True

    async def update_run(self, run: ScheduledRun) -> ScheduledRun:
        existing = self.runs[run.run_id]
        if existing.cancel_requested:
            run = replace(run, cancel_requested=True)
        self.runs[run.run_id] = run
        self.events.append(f"state:{run.state}")
        return run

    async def get_run(
        self, *, user_id: str, job_id: str, run_id: str
    ) -> ScheduledRun | None:
        return self.runs.get(run_id)

    async def put_due(self, pointer: DuePointer) -> bool:
        self.next_due.append(pointer)
        self.events.append("next_due")
        return True

    async def request_cancel(
        self,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
        requested_at: datetime,
    ) -> ScheduledRun | None:
        existing = self.runs.get(run_id)
        if existing is None:
            return None
        updated = replace(existing, cancel_requested=True, updated_at=requested_at)
        self.runs[run_id] = updated
        return updated


class _Executor:
    def __init__(
        self, outcomes: list[ExecutionResult | BaseException] | None = None
    ) -> None:
        self.outcomes = list(outcomes or [ExecutionResult(output="done")])
        self.requests: list[ExecutionRequest] = []
        self.called_after: list[list[str]] = []
        self.repository: _Repository | None = None

    async def execute(
        self, request: ExecutionRequest, control: CancellationControl
    ) -> ExecutionResult:
        self.requests.append(request)
        if self.repository is not None:
            self.called_after.append(list(self.repository.events))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_dispatcher_lists_only_the_current_minute_and_ignores_stale_jobs() -> (
    None
):
    repository = _Repository([_pointer(revision=2)], _job(revision=3))
    executor = _Executor()
    dispatcher = Dispatcher(repository, executor, replica_id="replica-a")

    summary = await dispatcher.dispatch_minute(NOW.replace(second=42))

    assert repository.listed_minutes == [NOW]
    assert executor.requests == []
    assert summary.stale == 1


@pytest.mark.asyncio
async def test_next_due_is_durable_before_the_runtime_is_invoked() -> None:
    repository = _Repository([_pointer()], _job())
    executor = _Executor()
    executor.repository = repository
    dispatcher = Dispatcher(repository, executor, replica_id="replica-a")

    summary = await dispatcher.dispatch_minute(NOW)

    assert summary.started == 1
    assert executor.called_after[0].index("next_due") < len(executor.called_after[0])
    assert repository.next_due == [
        replace(_pointer(), scheduled_at=NOW + timedelta(days=1))
    ]
    request = executor.requests[0]
    assert request.session_id == request.run_id
    assert request.service_identity is True


@pytest.mark.asyncio
async def test_dispatcher_promotes_an_existing_queued_manual_run() -> None:
    pointer = _pointer()
    queued = ScheduledRun(
        user_id=pointer.user_id,
        job_id=pointer.job_id,
        run_id=deterministic_run_id(pointer),
        revision=pointer.revision,
        scheduled_at=pointer.scheduled_at,
        session_id=deterministic_run_id(pointer),
        state="queued",
        created_at=NOW - timedelta(seconds=20),
        updated_at=NOW - timedelta(seconds=20),
    )
    repository = _Repository([pointer], _job())
    repository.runs[queued.run_id] = queued
    executor = _Executor()

    summary = await Dispatcher(
        repository,
        executor,
        replica_id="replica-a",
    ).dispatch_minute(NOW)

    assert summary.started == 1
    assert repository.runs[queued.run_id].state == "succeeded"
    assert len(executor.requests) == 1


@pytest.mark.asyncio
async def test_only_pre_ack_infrastructure_failures_are_retried() -> None:
    retryable = RuntimeInvocationError(
        "gateway timeout", acknowledged=False, retryable=True
    )
    repository = _Repository([_pointer()], _job())
    executor = _Executor([retryable, ExecutionResult(output="done")])
    dispatcher = Dispatcher(
        repository,
        executor,
        replica_id="replica-a",
        pre_ack_attempts=2,
    )

    await dispatcher.dispatch_minute(NOW)

    assert len(executor.requests) == 2
    run = next(iter(repository.runs.values()))
    assert run.state == "succeeded"
    assert run.attempt == 2

    repository = _Repository([_pointer()], _job())
    post_ack = RuntimeInvocationError("agent failed", acknowledged=True, retryable=True)
    executor = _Executor([post_ack, ExecutionResult(output="must not run")])
    dispatcher = Dispatcher(
        repository,
        executor,
        replica_id="replica-a",
        pre_ack_attempts=3,
    )

    await dispatcher.dispatch_minute(NOW)

    assert len(executor.requests) == 1
    assert next(iter(repository.runs.values())).state == "failed"


@pytest.mark.asyncio
async def test_terminal_runtime_error_is_persisted_for_manual_retry() -> None:
    repository = _Repository([_pointer()], _job())
    executor = _Executor(
        [
            RuntimeInvocationError(
                "Runtime create session returned HTTP 500. Detail: model boot failed",
                acknowledged=False,
                retryable=False,
            )
        ]
    )

    await Dispatcher(
        repository,
        executor,
        replica_id="replica-a",
        pre_ack_attempts=3,
    ).dispatch_minute(NOW)

    run = next(iter(repository.runs.values()))
    assert run.state == "failed"
    assert run.attempt == 1
    assert run.acknowledged is False
    assert "model boot failed" in run.error
    assert len(executor.requests) == 1


@pytest.mark.asyncio
async def test_unknown_scheduler_error_is_stored_with_stage_and_redacted() -> None:
    repository = _Repository([_pointer()], _job())
    executor = _Executor([RuntimeError("TOS failed token=storage-secret")])

    await Dispatcher(repository, executor, replica_id="replica-a").dispatch_minute(NOW)

    run = next(iter(repository.runs.values()))
    assert run.state == "failed"
    assert "Runtime execution failed" in run.error
    assert "TOS failed" in run.error
    assert "storage-secret" not in run.error
    assert "[REDACTED]" in run.error


@pytest.mark.asyncio
async def test_cancel_requested_is_persisted_and_stops_a_retry() -> None:
    repository = _Repository([_pointer()], _job())

    class _CancellingExecutor(_Executor):
        async def execute(
            self, request: ExecutionRequest, control: CancellationControl
        ) -> ExecutionResult:
            run = repository.runs[request.run_id]
            repository.runs[request.run_id] = replace(run, cancel_requested=True)
            raise RuntimeInvocationError(
                "not acknowledged", acknowledged=False, retryable=True
            )

    executor = _CancellingExecutor()
    dispatcher = Dispatcher(
        repository,
        executor,
        replica_id="replica-a",
        pre_ack_attempts=3,
    )

    await dispatcher.dispatch_minute(NOW)

    run = next(iter(repository.runs.values()))
    assert run.cancel_requested is True
    assert run.state == "cancelled"


@pytest.mark.asyncio
async def test_two_replicas_execute_the_same_due_pointer_once() -> None:
    repository = _Repository([_pointer()], _job())
    gate = asyncio.Event()

    class _BlockingExecutor(_Executor):
        async def execute(
            self, request: ExecutionRequest, control: CancellationControl
        ) -> ExecutionResult:
            self.requests.append(request)
            gate.set()
            await asyncio.sleep(0)
            return ExecutionResult(output="done")

    executor = _BlockingExecutor()
    first = Dispatcher(repository, executor, replica_id="replica-a")
    second = Dispatcher(repository, executor, replica_id="replica-b")

    await asyncio.gather(first.dispatch_minute(NOW), second.dispatch_minute(NOW))

    assert len(executor.requests) == 1
    assert list(repository.runs) == [deterministic_run_id(_pointer())]
