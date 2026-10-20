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

"""Ownership, lifecycle, and manual-run orchestration for cronjobs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import uuid4

from frontend.service.studio_scheduler.models import CronJob as SchedulerCronJob
from frontend.service.studio_scheduler.schedule import next_scheduled_time

from .repository import CronjobConflict, TosCronjobRepository
from .schemas import (
    CreateCronjobRequest,
    Cronjob,
    CronjobIdentity,
    CronjobRun,
    UpdateCronjobRequest,
)


class CronjobAccessDenied(PermissionError):
    """The caller may not access the requested owner's cronjobs."""


class CronjobRunQueueUnavailable(RuntimeError):
    """Manual runs cannot be published to the durable due queue."""


class CronjobAccessPolicy(Protocol):
    def resolve_owner(
        self,
        identity: CronjobIdentity,
        requested_owner_id: str | None,
    ) -> str: ...


class CronjobDuePublisher(Protocol):
    async def publish_next(
        self, job: SchedulerCronJob, *, after: datetime
    ) -> object | None: ...

    async def publish_run_now(
        self,
        *,
        user_id: str,
        job_id: str,
        revision: int,
        scheduled_at: datetime,
    ) -> str: ...


class OwnerOnlyAccessPolicy:
    """Default policy: callers can only operate on their own namespace."""

    def resolve_owner(
        self,
        identity: CronjobIdentity,
        requested_owner_id: str | None,
    ) -> str:
        if requested_owner_id and requested_owner_id != identity.owner_id:
            raise CronjobAccessDenied("无权访问其他用户的定时任务。")
        return identity.owner_id


class CronjobService:
    def __init__(
        self,
        repository: TosCronjobRepository,
        *,
        access_policy: CronjobAccessPolicy | None = None,
        due_publisher: CronjobDuePublisher | None = None,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.repository = repository
        self._access_policy = access_policy or OwnerOnlyAccessPolicy()
        self._due_publisher = due_publisher
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def create(
        self,
        identity: CronjobIdentity,
        request: CreateCronjobRequest,
        *,
        owner_id: str | None = None,
    ) -> Cronjob:
        owner = self._owner(identity, owner_id)
        now = self._clock()
        job = Cronjob(
            jobId=self._id_factory(),
            ownerId=owner,
            **request.model_dump(by_alias=True),
            revision=1,
            createdAt=now,
            updatedAt=now,
        )
        if job.enabled:
            job = job.model_copy(update={"next_run_at": self._next_time(job, now)})
        created = (await self.repository.create_job(job)).value
        if created.enabled:
            await self._publish_next(created, after=now)
        return created

    async def list(
        self, identity: CronjobIdentity, *, owner_id: str | None = None
    ) -> list[Cronjob]:
        owner = self._owner(identity, owner_id)
        jobs = await self.repository.list_jobs(owner)
        return list(
            await asyncio.gather(*(self._with_latest(owner, job) for job in jobs))
        )

    async def get(
        self,
        identity: CronjobIdentity,
        job_id: str,
        *,
        owner_id: str | None = None,
    ) -> Cronjob:
        owner = self._owner(identity, owner_id)
        job = (await self.repository.get_job(owner, job_id)).value
        return await self._with_latest(owner, job)

    async def update(
        self,
        identity: CronjobIdentity,
        job_id: str,
        patch: UpdateCronjobRequest,
        *,
        owner_id: str | None = None,
    ) -> Cronjob:
        owner = self._owner(identity, owner_id)
        current = await self.repository.get_job(owner, job_id)
        # ``model_copy(update=...)`` intentionally skips validation. Keep nested
        # Pydantic values such as ``Schedule`` as models instead of flattening
        # them to dictionaries with ``model_dump``.
        changes = {
            field: getattr(patch, field)
            for field in patch.model_fields_set
            if getattr(patch, field) is not None
        }
        updated = current.value.model_copy(
            update={
                **changes,
                "revision": current.value.revision + 1,
                "updated_at": self._clock(),
            }
        )
        updated = updated.model_copy(
            update={
                "next_run_at": (
                    self._next_time(updated, updated.updated_at)
                    if updated.enabled
                    else None
                )
            }
        )
        saved = (await self.repository.update_job(updated, current.etag)).value
        if saved.enabled:
            await self._publish_next(saved, after=saved.updated_at)
        return saved

    async def enable(
        self,
        identity: CronjobIdentity,
        job_id: str,
        *,
        owner_id: str | None = None,
    ) -> Cronjob:
        return await self._set_enabled(identity, job_id, True, owner_id)

    async def disable(
        self,
        identity: CronjobIdentity,
        job_id: str,
        *,
        owner_id: str | None = None,
    ) -> Cronjob:
        return await self._set_enabled(identity, job_id, False, owner_id)

    async def request_run(
        self,
        identity: CronjobIdentity,
        job_id: str,
        *,
        owner_id: str | None = None,
    ) -> CronjobRun:
        if self._due_publisher is None:
            raise CronjobRunQueueUnavailable("定时任务执行队列尚未配置，请联系管理员。")
        owner = self._owner(identity, owner_id)
        job = (await self.repository.get_job(owner, job_id)).value
        if not job.enabled:
            raise CronjobConflict("Enable this cronjob before running it.")
        now = self._clock().astimezone(timezone.utc).replace(second=0, microsecond=0)
        scheduled_at = now + timedelta(minutes=1)
        try:
            run_id = await self._due_publisher.publish_run_now(
                user_id=owner,
                job_id=job.id,
                revision=job.revision,
                scheduled_at=now,
            )
        except Exception as error:
            raise CronjobRunQueueUnavailable(
                "无法提交定时任务执行请求，请稍后重试。"
            ) from error
        queued = CronjobRun(
            runId=run_id,
            jobId=job.id,
            ownerId=owner,
            sessionId=run_id,
            status="queued",
            scheduledAt=scheduled_at,
            createdAt=now,
        )
        try:
            return (await self.repository.create_run(queued)).value
        except CronjobConflict:
            return (await self.repository.get_run(owner, job.id, run_id)).value

    async def list_runs(
        self,
        identity: CronjobIdentity,
        job_id: str,
        *,
        owner_id: str | None = None,
    ) -> list[CronjobRun]:
        owner = self._owner(identity, owner_id)
        await self.repository.get_job(owner, job_id)
        return await self.repository.list_runs(owner, job_id)

    async def cancel(
        self,
        identity: CronjobIdentity,
        job_id: str,
        run_id: str,
        *,
        owner_id: str | None = None,
    ) -> CronjobRun:
        owner = self._owner(identity, owner_id)
        await self.repository.get_job(owner, job_id)
        return await self.repository.request_cancel(
            owner, job_id, run_id, self._clock()
        )

    async def delete(
        self,
        identity: CronjobIdentity,
        job_id: str,
        *,
        owner_id: str | None = None,
    ) -> None:
        owner = self._owner(identity, owner_id)
        await self.repository.get_job(owner, job_id)
        lock = await self.repository.get_lock(owner, job_id)
        if lock is not None and lock.value.active_at(self._clock()):
            raise CronjobConflict("Stop the active run before deleting this cronjob.")
        await self.repository.delete_job(owner, job_id)

    async def _set_enabled(
        self,
        identity: CronjobIdentity,
        job_id: str,
        enabled: bool,
        owner_id: str | None,
    ) -> Cronjob:
        owner = self._owner(identity, owner_id)
        current = await self.repository.get_job(owner, job_id)
        if current.value.enabled is enabled:
            return current.value
        updated = current.value.model_copy(
            update={
                "enabled": enabled,
                "revision": current.value.revision + 1,
                "updated_at": self._clock(),
                "next_run_at": None,
            }
        )
        if enabled:
            updated = updated.model_copy(
                update={"next_run_at": self._next_time(updated, updated.updated_at)}
            )
        saved = (await self.repository.update_job(updated, current.etag)).value
        if enabled:
            await self._publish_next(saved, after=saved.updated_at)
        return saved

    async def _publish_next(self, job: Cronjob, *, after: datetime) -> None:
        if self._due_publisher is None:
            raise CronjobRunQueueUnavailable("定时任务执行队列尚未配置，请联系管理员。")
        scheduler_job = SchedulerCronJob.from_dict(
            self.repository.scheduler_job_payload(job)
        )
        try:
            await self._due_publisher.publish_next(scheduler_job, after=after)
        except Exception as error:
            raise CronjobRunQueueUnavailable(
                "无法提交定时任务计划，请稍后重试。"
            ) from error

    def _next_time(self, job: Cronjob, after: datetime) -> datetime | None:
        scheduler_job = SchedulerCronJob.from_dict(
            self.repository.scheduler_job_payload(job)
        )
        return next_scheduled_time(scheduler_job.schedule, after)

    async def _with_latest(self, owner_id: str, job: Cronjob) -> Cronjob:
        runs = await self.repository.list_runs(owner_id, job.id)
        return job.model_copy(update={"latest_run": runs[0] if runs else None})

    def _owner(self, identity: CronjobIdentity, requested_owner_id: str | None) -> str:
        return self._access_policy.resolve_owner(identity, requested_owner_id)


__all__ = [
    "CronjobAccessDenied",
    "CronjobAccessPolicy",
    "CronjobDuePublisher",
    "CronjobRunQueueUnavailable",
    "CronjobService",
    "OwnerOnlyAccessPolicy",
]
