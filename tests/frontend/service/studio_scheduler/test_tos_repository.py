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

import hashlib
from datetime import datetime, timedelta, timezone
from threading import Lock
from types import SimpleNamespace

import pytest

from frontend.service.studio_scheduler.models import DuePointer, ScheduledRun
from frontend.service.studio_scheduler.tos_repository import TosSchedulerRepository


class _TosError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeTos:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.listed_prefixes: list[str] = []
        self._lock = Lock()

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        content: bytes,
        forbid_overwrite: bool | None = None,
        if_match: str | None = None,
        **_: object,
    ) -> SimpleNamespace:
        with self._lock:
            current = self.objects.get((bucket, key))
            if forbid_overwrite and current is not None:
                raise _TosError(409)
            if if_match is not None and (current is None or current[1] != if_match):
                raise _TosError(412)
            etag = hashlib.sha256(content).hexdigest()
            self.objects[(bucket, key)] = (bytes(content), etag)
            return SimpleNamespace(etag=etag)

    def get_object(self, *, bucket: str, key: str) -> SimpleNamespace:
        with self._lock:
            try:
                content, etag = self.objects[(bucket, key)]
            except KeyError as error:
                raise _TosError(404) from error
        return SimpleNamespace(read=lambda: content, etag=etag)

    def list_objects_type2(
        self,
        *,
        bucket: str,
        prefix: str,
        continuation_token: str,
        max_keys: int,
    ) -> SimpleNamespace:
        self.listed_prefixes.append(prefix)
        keys = sorted(
            key
            for object_bucket, key in self.objects
            if object_bucket == bucket and key.startswith(prefix)
        )
        return SimpleNamespace(
            contents=[SimpleNamespace(key=key) for key in keys],
            is_truncated=False,
            next_continuation_token=None,
        )


@pytest.mark.asyncio
async def test_due_listing_uses_only_the_requested_minute_prefix() -> None:
    client = _FakeTos()
    repository = TosSchedulerRepository(bucket="studio", client_factory=lambda: client)
    minute = datetime(2026, 8, 20, 10, 35, tzinfo=timezone.utc)
    pointer = DuePointer(
        user_id="user@example.com",
        job_id="job/one",
        revision=4,
        scheduled_at=minute,
    )
    await repository.put_due(pointer)

    assert await repository.list_due(minute) == [pointer]
    assert client.listed_prefixes == [
        "veadk-studio/v1/scheduler/cronjobs/due/202608201035/"
    ]


@pytest.mark.asyncio
async def test_due_pointer_cas_advances_revision_for_the_same_occurrence() -> None:
    client = _FakeTos()
    repository = TosSchedulerRepository(bucket="studio", client_factory=lambda: client)
    minute = datetime(2026, 8, 20, 10, 35, tzinfo=timezone.utc)
    original = DuePointer(
        user_id="owner",
        job_id="job",
        revision=1,
        scheduled_at=minute,
    )
    updated = DuePointer(
        user_id="owner",
        job_id="job",
        revision=3,
        scheduled_at=minute,
    )

    assert await repository.put_due(original) is True
    assert await repository.put_due(updated) is True
    assert await repository.put_due(original) is False
    assert await repository.list_due(minute) == [updated]


@pytest.mark.asyncio
async def test_lock_uses_atomic_create_and_etag_cas_for_reuse() -> None:
    client = _FakeTos()
    repositories = [
        TosSchedulerRepository(bucket="studio", client_factory=lambda: client)
        for _ in range(2)
    ]
    now = datetime(2026, 8, 20, 10, 35, tzinfo=timezone.utc)

    first, second = await __import__("asyncio").gather(
        repositories[0].acquire_lock(
            user_id="user@example.com",
            job_id="job-1",
            run_id="run-1",
            replica_id="a",
            now=now,
            expires_at=now + timedelta(hours=1),
        ),
        repositories[1].acquire_lock(
            user_id="user@example.com",
            job_id="job-1",
            run_id="run-2",
            replica_id="b",
            now=now,
            expires_at=now + timedelta(hours=1),
        ),
    )

    assert sum(item.acquired for item in (first, second)) == 1
    winner = "run-1" if first.acquired else "run-2"
    await repositories[0].release_lock(
        user_id="user@example.com",
        job_id="job-1",
        run_id=winner,
        released_at=now + timedelta(minutes=1),
    )
    third = await repositories[1].acquire_lock(
        user_id="user@example.com",
        job_id="job-1",
        run_id="run-3",
        replica_id="b",
        now=now + timedelta(minutes=2),
        expires_at=now + timedelta(hours=1),
    )
    assert third.acquired is True


@pytest.mark.asyncio
async def test_cancel_request_is_a_durable_idempotent_cas_update() -> None:
    client = _FakeTos()
    repository = TosSchedulerRepository(bucket="studio", client_factory=lambda: client)
    now = datetime(2026, 8, 20, 10, 35, tzinfo=timezone.utc)
    run = ScheduledRun(
        user_id="user@example.com",
        job_id="job-1",
        run_id="run-1",
        revision=1,
        scheduled_at=now,
        session_id="run-1",
        state="running",
        created_at=now,
        updated_at=now,
    )
    await repository.create_run(run)

    first = await repository.request_cancel(
        user_id=run.user_id,
        job_id=run.job_id,
        run_id=run.run_id,
        requested_at=now + timedelta(seconds=10),
    )
    second = await repository.request_cancel(
        user_id=run.user_id,
        job_id=run.job_id,
        run_id=run.run_id,
        requested_at=now + timedelta(seconds=20),
    )

    assert first is not None and first.cancel_requested is True
    assert second == first
