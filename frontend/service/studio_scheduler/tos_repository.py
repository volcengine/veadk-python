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

"""TOS repository using atomic create and ETag compare-and-set operations."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX

from .models import (
    CronJob,
    DuePointer,
    JobLock,
    LockAttempt,
    ProviderName,
    ScheduledRun,
)

_MAX_JSON_BYTES = 1024 * 1024
_CAS_ATTEMPTS = 5


class SchedulerStorageConflict(RuntimeError):
    """An immutable scheduler object already exists with different data."""


class TosSchedulerRepository:
    """Persist jobs, due pointers, locks, and run state independently of instances."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        provider: ProviderName = "volcengine",
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS scheduler storage requires a bucket")
        self._bucket = bucket
        self._client_factory = client_factory
        self._provider: ProviderName = provider

    async def list_due(self, minute: datetime) -> list[DuePointer]:
        return await asyncio.to_thread(self._list_due, minute)

    def _list_due(self, minute: datetime) -> list[DuePointer]:
        client = self._client_factory()
        prefix = self._due_prefix(minute)
        return [
            DuePointer.from_dict(self._get_json(client, key)[0])
            for key in self._list_keys(client, prefix)
        ]

    async def get_job(self, user_id: str, job_id: str) -> CronJob | None:
        return await asyncio.to_thread(self._get_job, user_id, job_id)

    def _get_job(self, user_id: str, job_id: str) -> CronJob | None:
        client = self._client_factory()
        try:
            payload, _ = self._get_json(client, self._job_key(user_id, job_id))
        except Exception as error:
            if _status_code(error) == 404:
                return None
            raise
        return CronJob.from_dict(payload, default_provider=self._provider)

    async def put_due(self, pointer: DuePointer) -> bool:
        return await asyncio.to_thread(self._put_due, pointer)

    def _put_due(self, pointer: DuePointer) -> bool:
        client = self._client_factory()
        key = self._due_key(pointer)
        content = _json_bytes(pointer.to_dict())
        try:
            self._put(client, key, content, forbid_overwrite=True)
            return True
        except Exception as error:
            if _status_code(error) not in {409, 412}:
                raise
        for _ in range(_CAS_ATTEMPTS):
            existing_payload, etag = self._get_json(client, key)
            existing = DuePointer.from_dict(existing_payload)
            if existing == pointer:
                return False
            same_occurrence = (
                existing.user_id == pointer.user_id
                and existing.job_id == pointer.job_id
                and existing.scheduled_at == pointer.scheduled_at
            )
            if not same_occurrence:
                raise SchedulerStorageConflict(
                    f"Due pointer already exists with different identity: {key}"
                )
            if existing.revision > pointer.revision:
                return False
            try:
                self._put(client, key, content, if_match=etag)
                return True
            except Exception as error:
                if _status_code(error) not in {409, 412}:
                    raise
        raise SchedulerStorageConflict(
            f"Unable to update due pointer after CAS retries: {key}"
        )

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
        return await asyncio.to_thread(
            self._acquire_lock,
            user_id,
            job_id,
            run_id,
            replica_id,
            now,
            expires_at,
        )

    def _acquire_lock(
        self,
        user_id: str,
        job_id: str,
        run_id: str,
        replica_id: str,
        now: datetime,
        expires_at: datetime,
    ) -> LockAttempt:
        client = self._client_factory()
        key = self._lock_key(user_id, job_id)
        requested = JobLock(
            run_id=run_id,
            replica_id=replica_id,
            state="held",
            acquired_at=now,
            expires_at=expires_at,
        )
        content = _json_bytes(requested.to_dict())
        try:
            self._put(client, key, content, forbid_overwrite=True)
            return LockAttempt(acquired=True)
        except Exception as error:
            if _status_code(error) not in {409, 412}:
                raise

        for _ in range(_CAS_ATTEMPTS):
            payload, etag = self._get_json(client, key)
            existing = JobLock.from_dict(payload)
            if existing.state == "held" and existing.expires_at > now:
                return LockAttempt(
                    acquired=False,
                    active_run_id=existing.run_id,
                )
            try:
                self._put(client, key, content, if_match=etag)
                abandoned = existing.run_id if existing.state == "held" else ""
                return LockAttempt(acquired=True, abandoned_run_id=abandoned)
            except Exception as error:
                if _status_code(error) not in {409, 412}:
                    raise
        raise SchedulerStorageConflict(
            "Unable to acquire cron job lock after CAS retries"
        )

    async def release_lock(
        self,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
        released_at: datetime,
    ) -> None:
        await asyncio.to_thread(
            self._release_lock, user_id, job_id, run_id, released_at
        )

    def _release_lock(
        self, user_id: str, job_id: str, run_id: str, released_at: datetime
    ) -> None:
        client = self._client_factory()
        key = self._lock_key(user_id, job_id)
        for _ in range(_CAS_ATTEMPTS):
            try:
                payload, etag = self._get_json(client, key)
            except Exception as error:
                if _status_code(error) == 404:
                    return
                raise
            existing = JobLock.from_dict(payload)
            if existing.run_id != run_id or existing.state != "held":
                return
            released = replace(
                existing,
                state="released",
                released_at=released_at,
            )
            try:
                self._put(
                    client,
                    key,
                    _json_bytes(released.to_dict()),
                    if_match=etag,
                )
                return
            except Exception as error:
                if _status_code(error) not in {409, 412}:
                    raise
        raise SchedulerStorageConflict(
            "Unable to release cron job lock after CAS retries"
        )

    async def create_run(self, run: ScheduledRun) -> bool:
        return await asyncio.to_thread(self._create_run, run)

    def _create_run(self, run: ScheduledRun) -> bool:
        client = self._client_factory()
        key = self._run_key(run.user_id, run.job_id, run.run_id)
        content = _json_bytes(run.to_dict())
        try:
            self._put(client, key, content, forbid_overwrite=True)
            return True
        except Exception as error:
            if _status_code(error) not in {409, 412}:
                raise
            existing, _ = self._get_bytes(client, key)
            existing_run = ScheduledRun.from_dict(json.loads(existing))
            if (
                existing_run.user_id,
                existing_run.job_id,
                existing_run.run_id,
                existing_run.scheduled_at,
            ) != (run.user_id, run.job_id, run.run_id, run.scheduled_at):
                raise SchedulerStorageConflict(
                    f"Run id already exists with different identity: {run.run_id}"
                ) from error
            return False

    async def get_run(
        self, *, user_id: str, job_id: str, run_id: str
    ) -> ScheduledRun | None:
        return await asyncio.to_thread(self._get_run, user_id, job_id, run_id)

    def _get_run(self, user_id: str, job_id: str, run_id: str) -> ScheduledRun | None:
        client = self._client_factory()
        try:
            payload, _ = self._get_json(client, self._run_key(user_id, job_id, run_id))
        except Exception as error:
            if _status_code(error) == 404:
                return None
            raise
        return ScheduledRun.from_dict(payload)

    async def update_run(self, run: ScheduledRun) -> ScheduledRun:
        return await asyncio.to_thread(self._update_run, run)

    def _update_run(self, run: ScheduledRun) -> ScheduledRun:
        client = self._client_factory()
        key = self._run_key(run.user_id, run.job_id, run.run_id)
        for _ in range(_CAS_ATTEMPTS):
            payload, etag = self._get_json(client, key)
            existing = ScheduledRun.from_dict(payload)
            merged = replace(
                run,
                cancel_requested=run.cancel_requested or existing.cancel_requested,
            )
            try:
                self._put(client, key, _json_bytes(merged.to_dict()), if_match=etag)
                return merged
            except Exception as error:
                if _status_code(error) not in {409, 412}:
                    raise
        raise SchedulerStorageConflict("Unable to update cron run after CAS retries")

    async def request_cancel(
        self,
        *,
        user_id: str,
        job_id: str,
        run_id: str,
        requested_at: datetime,
    ) -> ScheduledRun | None:
        return await asyncio.to_thread(
            self._request_cancel,
            user_id,
            job_id,
            run_id,
            requested_at,
        )

    def _request_cancel(
        self,
        user_id: str,
        job_id: str,
        run_id: str,
        requested_at: datetime,
    ) -> ScheduledRun | None:
        client = self._client_factory()
        key = self._run_key(user_id, job_id, run_id)
        for _ in range(_CAS_ATTEMPTS):
            try:
                payload, etag = self._get_json(client, key)
            except Exception as error:
                if _status_code(error) == 404:
                    return None
                raise
            existing = ScheduledRun.from_dict(payload)
            if existing.cancel_requested:
                return existing
            updated = replace(
                existing,
                cancel_requested=True,
                updated_at=requested_at,
            )
            try:
                self._put(client, key, _json_bytes(updated.to_dict()), if_match=etag)
                return updated
            except Exception as error:
                if _status_code(error) not in {409, 412}:
                    raise
        raise SchedulerStorageConflict("Unable to cancel cron run after CAS retries")

    def _list_keys(self, client: Any, prefix: str) -> list[str]:
        continuation_token = ""
        keys: list[str] = []
        while True:
            output = client.list_objects_type2(
                bucket=self._bucket,
                prefix=prefix,
                continuation_token=continuation_token,
                max_keys=1000,
            )
            keys.extend(
                str(item.key)
                for item in (getattr(output, "contents", None) or [])
                if str(getattr(item, "key", "")).endswith(".json")
            )
            if not getattr(output, "is_truncated", False):
                return keys
            continuation_token = str(
                getattr(output, "next_continuation_token", "") or ""
            )
            if not continuation_token:
                raise RuntimeError("TOS returned a truncated listing without a token")

    def _get_json(self, client: Any, key: str) -> tuple[dict[str, object], str]:
        content, etag = self._get_bytes(client, key)
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise TypeError(f"Scheduler object must be a JSON object: {key}")
        return payload, etag

    def _get_bytes(self, client: Any, key: str) -> tuple[bytes, str]:
        response = client.get_object(bucket=self._bucket, key=key)
        content = response.read() if hasattr(response, "read") else b"".join(response)
        if len(content) > _MAX_JSON_BYTES:
            raise ValueError(f"Scheduler object is too large: {key}")
        etag = str(getattr(response, "etag", "") or "").strip('"')
        if not etag:
            raise ValueError(f"Scheduler object is missing an ETag: {key}")
        return content, etag

    def _put(
        self,
        client: Any,
        key: str,
        content: bytes,
        *,
        forbid_overwrite: bool | None = None,
        if_match: str | None = None,
    ) -> None:
        client.put_object(
            bucket=self._bucket,
            key=key,
            content=content,
            content_type="application/json",
            forbid_overwrite=forbid_overwrite,
            if_match=if_match,
        )

    @staticmethod
    def _user_job_prefix(user_id: str, job_id: str) -> str:
        return (
            f"{STUDIO_STORAGE_ROOT_PREFIX}/users/{quote(user_id, safe='')}/"
            f"cronjobs/{quote(job_id, safe='')}"
        )

    @classmethod
    def _job_key(cls, user_id: str, job_id: str) -> str:
        return f"{cls._user_job_prefix(user_id, job_id)}/job.json"

    @classmethod
    def _lock_key(cls, user_id: str, job_id: str) -> str:
        return f"{cls._user_job_prefix(user_id, job_id)}/lock.json"

    @classmethod
    def _run_key(cls, user_id: str, job_id: str, run_id: str) -> str:
        return (
            f"{cls._user_job_prefix(user_id, job_id)}/runs/"
            f"{quote(run_id, safe='')}.json"
        )

    @staticmethod
    def _due_prefix(minute: datetime) -> str:
        # Due buckets are always named with their UTC minute, independent of host TZ.
        stamp = minute.astimezone(timezone.utc)
        return (
            f"{STUDIO_STORAGE_ROOT_PREFIX}/scheduler/cronjobs/due/{stamp:%Y%m%d%H%M}/"
        )

    @classmethod
    def _due_key(cls, pointer: DuePointer) -> str:
        identity = (
            f"{pointer.user_id}\0{pointer.job_id}\0{pointer.scheduled_at.isoformat()}"
        )
        name = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return f"{cls._due_prefix(pointer.scheduled_at)}{name}.json"


def _json_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
