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

"""Single publishing API used by create/edit and run-now backend operations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import CronJob, DuePointer, deterministic_run_id
from .ports import SchedulerRepository
from .schedule import next_scheduled_time


class DuePublisher:
    """Publish immutable minute pointers without duplicating key logic in the BFF."""

    def __init__(self, repository: SchedulerRepository) -> None:
        self._repository = repository

    async def publish(self, job: CronJob, scheduled_at: datetime) -> DuePointer:
        return await self.publish_due(
            user_id=job.user_id,
            job_id=job.job_id,
            revision=job.revision,
            scheduled_at=scheduled_at,
        )

    async def publish_due(
        self,
        *,
        user_id: str,
        job_id: str,
        revision: int,
        scheduled_at: datetime,
    ) -> DuePointer:
        """Publish the four-field protocol consumed by the minute dispatcher."""
        pointer = DuePointer(
            user_id=user_id,
            job_id=job_id,
            revision=revision,
            scheduled_at=scheduled_at,
        )
        await self._repository.put_due(pointer)
        return pointer

    async def publish_next(self, job: CronJob, *, after: datetime) -> DuePointer | None:
        scheduled_at = next_scheduled_time(job.schedule, after)
        if scheduled_at is None:
            return None
        return await self.publish(job, scheduled_at)

    async def publish_run_now(
        self,
        job: CronJob | None = None,
        *,
        user_id: str = "",
        job_id: str = "",
        revision: int = 0,
        scheduled_at: datetime | None = None,
        now: datetime | None = None,
    ) -> str:
        """Publish a next-minute pointer and return its deterministic run id.

        The separate scheduler scans each minute exactly once. Queueing manual work
        for the following minute avoids racing a scan that already happened.
        """
        requested_at = scheduled_at or now or datetime.now(timezone.utc)
        if requested_at.tzinfo is None or requested_at.utcoffset() is None:
            raise ValueError("run-now time must include a timezone")
        current = requested_at.astimezone(timezone.utc).replace(
            second=0,
            microsecond=0,
        ) + timedelta(minutes=1)
        if job is not None:
            pointer = await self.publish(job, current)
        else:
            pointer = await self.publish_due(
                user_id=user_id,
                job_id=job_id,
                revision=revision,
                scheduled_at=current,
            )
        return deterministic_run_id(pointer)
