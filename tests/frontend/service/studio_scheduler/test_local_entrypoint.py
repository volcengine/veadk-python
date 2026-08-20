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

from datetime import datetime, timedelta, timezone

import pytest

from frontend.service.studio_scheduler.dispatcher import Dispatcher
from frontend.service.studio_scheduler.memory_repository import (
    InMemorySchedulerRepository,
)
from frontend.service.studio_scheduler.models import (
    CronJob,
    ExecutionResult,
    RuntimeTarget,
    Schedule,
)
from frontend.service.studio_scheduler.publisher import DuePublisher


@pytest.mark.asyncio
async def test_run_now_uses_the_same_due_publisher_and_local_dispatch_path() -> None:
    now = datetime(2026, 8, 20, 10, 35, 42, tzinfo=timezone.utc)
    repository = InMemorySchedulerRepository()
    job = CronJob(
        user_id="local-user",
        job_id="local-job",
        revision=1,
        enabled=True,
        prompt="hello",
        runtime=RuntimeTarget(
            provider="byteplus",
            runtime_id="runtime",
            agent_name="agent",
            region="ap-southeast-1",
        ),
        schedule=Schedule(kind="daily", timezone="UTC", hour=10, minute=35),
    )
    await repository.put_job(job)
    run_id = await DuePublisher(repository).publish_run_now(job, now=now)

    class _LocalExecutor:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, request, control):
            self.calls += 1
            return ExecutionResult(output="ok")

    executor = _LocalExecutor()
    queued_minute = now.replace(second=0) + timedelta(minutes=1)
    summary = await Dispatcher(
        repository,
        executor,
        replica_id="local",
    ).dispatch_minute(queued_minute)

    assert next(iter(repository.due.values())).scheduled_at == queued_minute
    assert next(iter(repository.runs.values())).run_id == run_id
    assert summary.started == 1
    assert executor.calls == 1


@pytest.mark.asyncio
async def test_backend_can_publish_run_now_with_only_job_coordinates() -> None:
    repository = InMemorySchedulerRepository()
    now = datetime(2026, 8, 20, 10, 35, 42, tzinfo=timezone.utc)

    run_id = await DuePublisher(repository).publish_run_now(
        user_id="owner-1",
        job_id="job-1",
        revision=7,
        scheduled_at=now,
    )

    pointer = next(iter(repository.due.values()))
    assert pointer.to_dict() == {
        "userId": "owner-1",
        "jobId": "job-1",
        "revision": 7,
        "scheduledAt": "2026-08-20T10:36:00Z",
    }
    assert len(run_id) == 64
