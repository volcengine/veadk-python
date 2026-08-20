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

"""TOS persistence for user-owned cronjobs, runs, and execution locks."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar, cast
from urllib.parse import quote
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX

from .schemas import Cronjob, CronjobLock, CronjobRun

_MAX_OBJECT_BYTES = 2 * 1024 * 1024
_Value = TypeVar("_Value", bound=BaseModel)


class CronjobNotFound(LookupError):
    """The requested owner-scoped object does not exist."""


class CronjobConflict(RuntimeError):
    """A conditional write failed or an active execution already exists."""


@dataclass(frozen=True)
class Stored(Generic[_Value]):
    value: _Value
    etag: str


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class TosCronjobRepository:
    """Keep TOS keys and CAS semantics outside business and HTTP layers."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        root_prefix: str = STUDIO_STORAGE_ROOT_PREFIX,
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS cronjob storage requires a bucket.")
        self._bucket = bucket
        self._client_factory = client_factory
        self._root_prefix = root_prefix.strip("/")

    async def create_job(self, job: Cronjob) -> Stored[Cronjob]:
        return await asyncio.to_thread(self._create_job, job)

    async def get_job(self, owner_id: str, job_id: str) -> Stored[Cronjob]:
        return await asyncio.to_thread(self._get_job, owner_id, job_id)

    async def list_jobs(self, owner_id: str) -> list[Cronjob]:
        return await asyncio.to_thread(self._list_jobs, owner_id)

    async def update_job(self, job: Cronjob, etag: str) -> Stored[Cronjob]:
        return await asyncio.to_thread(self._update_job, job, etag)

    async def delete_job(self, owner_id: str, job_id: str) -> None:
        await asyncio.to_thread(self._delete_job, owner_id, job_id)

    async def create_run(self, run: CronjobRun) -> Stored[CronjobRun]:
        return await asyncio.to_thread(self._create_run, run)

    async def get_run(
        self, owner_id: str, job_id: str, run_id: str
    ) -> Stored[CronjobRun]:
        return await asyncio.to_thread(self._get_run, owner_id, job_id, run_id)

    async def list_runs(self, owner_id: str, job_id: str) -> list[CronjobRun]:
        return await asyncio.to_thread(self._list_runs, owner_id, job_id)

    async def update_run(self, run: CronjobRun, etag: str) -> Stored[CronjobRun]:
        return await asyncio.to_thread(self._update_run, run, etag)

    async def request_cancel(
        self, owner_id: str, job_id: str, run_id: str, requested_at: datetime
    ) -> CronjobRun:
        return await asyncio.to_thread(
            self._request_cancel, owner_id, job_id, run_id, requested_at
        )

    async def get_lock(self, owner_id: str, job_id: str) -> Stored[CronjobLock] | None:
        return await asyncio.to_thread(self._get_lock, owner_id, job_id)

    async def acquire_lock(
        self,
        owner_id: str,
        job_id: str,
        run_id: str,
        now: datetime,
        expires_at: datetime,
    ) -> Stored[CronjobLock]:
        return await asyncio.to_thread(
            self._acquire_lock, owner_id, job_id, run_id, now, expires_at
        )

    async def release_lock(
        self, owner_id: str, job_id: str, run_id: str, now: datetime
    ) -> None:
        await asyncio.to_thread(self._release_lock, owner_id, job_id, run_id, now)

    def scheduler_job_payload(self, job: Cronjob) -> dict[str, Any]:
        """Return the exact durable job contract consumed by the dispatcher."""
        return self._job_payload(job)

    def _create_job(self, job: Cronjob) -> Stored[Cronjob]:
        key = self._job_key(job.owner_id, job.id)
        return self._create(self._client_factory(), key, job)

    def _get_job(self, owner_id: str, job_id: str) -> Stored[Cronjob]:
        return self._read(
            self._client_factory(), self._job_key(owner_id, job_id), Cronjob
        )

    def _list_jobs(self, owner_id: str) -> list[Cronjob]:
        client = self._client_factory()
        keys = self._list_keys(client, f"{self._owner_prefix(owner_id)}/")
        jobs = [
            self._read(client, key, Cronjob).value
            for key in keys
            if key.endswith("/job.json")
        ]
        return sorted(jobs, key=lambda item: (item.created_at, item.id), reverse=True)

    def _update_job(self, job: Cronjob, etag: str) -> Stored[Cronjob]:
        return self._replace(
            self._client_factory(), self._job_key(job.owner_id, job.id), job, etag
        )

    def _delete_job(self, owner_id: str, job_id: str) -> None:
        client = self._client_factory()
        prefix = f"{self._job_prefix(owner_id, job_id)}/"
        keys = self._list_keys(client, prefix)
        if self._job_key(owner_id, job_id) not in keys:
            raise CronjobNotFound("定时任务不存在或已被删除。")
        for key in keys:
            client.delete_object(bucket=self._bucket, key=key)

    def _create_run(self, run: CronjobRun) -> Stored[CronjobRun]:
        return self._create(
            self._client_factory(),
            self._run_key(run.owner_id, run.job_id, run.id),
            run,
        )

    def _get_run(self, owner_id: str, job_id: str, run_id: str) -> Stored[CronjobRun]:
        return self._read(
            self._client_factory(),
            self._run_key(owner_id, job_id, run_id),
            CronjobRun,
        )

    def _list_runs(self, owner_id: str, job_id: str) -> list[CronjobRun]:
        client = self._client_factory()
        prefix = f"{self._job_prefix(owner_id, job_id)}/runs/"
        runs = [
            self._read(client, key, CronjobRun).value
            for key in self._list_keys(client, prefix)
            if key.endswith(".json")
        ]
        return sorted(
            runs,
            key=lambda item: (item.created_at or item.scheduled_at, item.id),
            reverse=True,
        )

    def _update_run(self, run: CronjobRun, etag: str) -> Stored[CronjobRun]:
        return self._replace(
            self._client_factory(),
            self._run_key(run.owner_id, run.job_id, run.id),
            run,
            etag,
        )

    def _request_cancel(
        self, owner_id: str, job_id: str, run_id: str, requested_at: datetime
    ) -> CronjobRun:
        client = self._client_factory()
        key = self._run_key(owner_id, job_id, run_id)
        payload, etag = self._read_payload(client, key)
        state = str(payload.get("state") or payload.get("status") or "")
        if state in {"succeeded", "success", "failed", "cancelled", "skipped"}:
            raise CronjobConflict("A completed cronjob run cannot be cancelled.")
        if not payload.get("cancelRequested", False):
            payload["cancelRequested"] = True
            payload["updatedAt"] = self._iso(requested_at)
            self._replace_payload(client, key, payload, etag)
        return self._run_from_payload(payload)

    def _get_lock(self, owner_id: str, job_id: str) -> Stored[CronjobLock] | None:
        try:
            client = self._client_factory()
            payload, etag = self._read_payload(client, self._lock_key(owner_id, job_id))
            acquired_at = payload.get("acquiredAt")
            lock = CronjobLock.model_validate(
                {
                    "jobId": job_id,
                    "ownerId": owner_id,
                    "runId": payload["runId"],
                    "state": payload["state"],
                    "acquiredAt": acquired_at,
                    "updatedAt": payload.get("releasedAt") or acquired_at,
                    "expiresAt": payload["expiresAt"],
                }
            )
            return Stored(value=lock, etag=etag)
        except CronjobNotFound:
            return None

    def _acquire_lock(
        self,
        owner_id: str,
        job_id: str,
        run_id: str,
        now: datetime,
        expires_at: datetime,
    ) -> Stored[CronjobLock]:
        client = self._client_factory()
        key = self._lock_key(owner_id, job_id)
        lock = CronjobLock(
            jobId=job_id,
            ownerId=owner_id,
            runId=run_id,
            state="held",
            acquiredAt=now,
            updatedAt=now,
            expiresAt=expires_at,
        )
        try:
            return self._create(client, key, lock)
        except CronjobConflict:
            current = self._read(client, key, CronjobLock)
            if current.value.active_at(now):
                raise CronjobConflict("This cronjob already has an active run.")
            return self._replace(client, key, lock, current.etag)

    def _release_lock(
        self, owner_id: str, job_id: str, run_id: str, now: datetime
    ) -> None:
        current = self._get_lock(owner_id, job_id)
        if current is None or current.value.state == "released":
            return
        if current.value.run_id != run_id:
            raise CronjobConflict("Cronjob lock belongs to another run.")
        released = current.value.model_copy(
            update={"state": "released", "updated_at": now, "expires_at": now}
        )
        self._replace(
            self._client_factory(),
            self._lock_key(owner_id, job_id),
            released,
            current.etag,
        )

    def _create(self, client: Any, key: str, value: _Value) -> Stored[_Value]:
        content = self._encode(value)
        try:
            output = client.put_object(
                bucket=self._bucket,
                key=key,
                content=content,
                content_length=len(content),
                content_type="application/json",
                forbid_overwrite=True,
            )
        except Exception as error:
            if _status_code(error) in {409, 412}:
                raise CronjobConflict("Cronjob object already exists.") from error
            raise
        return Stored(value=value, etag=self._write_etag(output, client, key))

    def _replace(
        self, client: Any, key: str, value: _Value, etag: str
    ) -> Stored[_Value]:
        content = self._encode(value)
        try:
            output = client.put_object(
                bucket=self._bucket,
                key=key,
                content=content,
                content_length=len(content),
                content_type="application/json",
                if_match=etag,
            )
        except Exception as error:
            if _status_code(error) in {409, 412}:
                raise CronjobConflict(
                    "Cronjob changed concurrently; reload and try again."
                ) from error
            if _status_code(error) == 404:
                raise CronjobNotFound("定时任务不存在或已被删除。") from error
            raise
        return Stored(value=value, etag=self._write_etag(output, client, key))

    def _read(self, client: Any, key: str, model: type[_Value]) -> Stored[_Value]:
        payload, etag = self._read_payload(client, key)
        if model is Cronjob:
            value = self._job_from_payload(payload)
        elif model is CronjobRun:
            value = self._run_from_payload(payload)
        else:
            value = model.model_validate(payload)
        return cast(Stored[_Value], Stored(value=value, etag=etag))

    def _read_payload(self, client: Any, key: str) -> tuple[dict[str, Any], str]:
        try:
            response = client.get_object(bucket=self._bucket, key=key)
        except Exception as error:
            if _status_code(error) == 404:
                raise CronjobNotFound("定时任务不存在或已被删除。") from error
            raise
        content = response.read(_MAX_OBJECT_BYTES + 1)
        if not isinstance(content, bytes) or len(content) > _MAX_OBJECT_BYTES:
            raise ValueError("Cronjob object is invalid or too large.")
        etag = self._etag(response)
        if not etag:
            raise RuntimeError("TOS cronjob object did not include an ETag.")
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise TypeError("Cronjob object must be a JSON object.")
        return payload, etag

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
                str(item.key) for item in (getattr(output, "contents", None) or [])
            )
            if not getattr(output, "is_truncated", False):
                return keys
            continuation_token = str(
                getattr(output, "next_continuation_token", "") or ""
            )
            if not continuation_token:
                raise RuntimeError(
                    "TOS truncated a cronjob listing without a continuation token."
                )

    def _encode(self, value: BaseModel) -> bytes:
        if isinstance(value, Cronjob):
            payload = self._job_payload(value)
        elif isinstance(value, CronjobRun):
            payload = self._run_payload(value)
        else:
            payload = value.model_dump(mode="json", by_alias=True)
        content = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(content) > _MAX_OBJECT_BYTES:
            raise ValueError("Cronjob object is too large.")
        return content

    def _replace_payload(
        self, client: Any, key: str, payload: dict[str, Any], etag: str
    ) -> None:
        content = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        try:
            client.put_object(
                bucket=self._bucket,
                key=key,
                content=content,
                content_length=len(content),
                content_type="application/json",
                if_match=etag,
            )
        except Exception as error:
            if _status_code(error) in {409, 412}:
                raise CronjobConflict(
                    "Cronjob changed concurrently; reload and try again."
                ) from error
            raise

    @classmethod
    def _job_payload(cls, job: Cronjob) -> dict[str, Any]:
        provider = "volcengine" if job.region.startswith("cn-") else "byteplus"
        return {
            "userId": job.owner_id,
            "ownerId": job.owner_id,
            "jobId": job.id,
            "name": job.name,
            "revision": job.revision,
            "enabled": job.enabled,
            "prompt": job.prompt,
            "runtime": {
                "provider": provider,
                "runtimeId": job.runtime_id,
                "runtimeName": job.runtime_name,
                "agentName": job.agent_name,
                "region": job.region,
                "projectName": "default",
            },
            "schedule": cls._scheduler_schedule(job.schedule),
            "createdAt": cls._iso(job.created_at),
            "updatedAt": cls._iso(job.updated_at),
            "nextRunAt": cls._iso(job.next_run_at),
            "maxRuntimeSeconds": 1800,
        }

    @classmethod
    def _job_from_payload(cls, payload: dict[str, Any]) -> Cronjob:
        if "runtime" not in payload:
            return Cronjob.model_validate(payload)
        runtime = payload["runtime"]
        schedule = payload["schedule"]
        if not isinstance(runtime, dict) or not isinstance(schedule, dict):
            raise TypeError("Cronjob runtime and schedule must be objects.")
        created_at = payload.get("createdAt") or payload.get("updatedAt")
        updated_at = payload.get("updatedAt") or created_at
        return Cronjob.model_validate(
            {
                "jobId": payload["jobId"],
                "ownerId": payload.get("userId") or payload["ownerId"],
                "name": payload.get("name") or runtime.get("runtimeName") or "定时任务",
                "runtimeId": runtime["runtimeId"],
                "runtimeName": runtime.get("runtimeName") or runtime["runtimeId"],
                "agentName": runtime["agentName"],
                "region": runtime["region"],
                "prompt": payload["prompt"],
                "schedule": cls._api_schedule(schedule),
                "enabled": payload["enabled"],
                "revision": payload["revision"],
                "createdAt": created_at,
                "updatedAt": updated_at,
                "nextRunAt": payload.get("nextRunAt"),
            }
        )

    @classmethod
    def _scheduler_schedule(cls, schedule: Any) -> dict[str, Any]:
        if schedule.type == "once":
            run_at = datetime.fromisoformat(schedule.once_at.replace("Z", "+00:00"))
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=ZoneInfo(schedule.timezone))
            return {
                "kind": "once",
                "timezone": schedule.timezone,
                "runAt": cls._iso(run_at),
            }
        if schedule.type in {"daily", "weekly"}:
            hour, minute = (int(item) for item in schedule.time.split(":", 1))
            payload: dict[str, Any] = {
                "kind": schedule.type,
                "timezone": schedule.timezone,
                "hour": hour,
                "minute": minute,
            }
            if schedule.type == "weekly":
                payload["weekdays"] = [(schedule.weekday + 6) % 7]
            return payload
        return {
            "kind": "cron",
            "timezone": schedule.timezone,
            "cron": schedule.cron,
        }

    @staticmethod
    def _api_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
        kind = schedule.get("kind") or schedule.get("type")
        timezone_name = str(schedule["timezone"])
        if kind == "once":
            raw = schedule.get("runAt") or schedule.get("onceAt")
            run_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if run_at.tzinfo is not None:
                run_at = run_at.astimezone(ZoneInfo(timezone_name))
            return {
                "type": "once",
                "timezone": timezone_name,
                "onceAt": run_at.strftime("%Y-%m-%dT%H:%M"),
            }
        if kind == "daily":
            return {
                "type": "daily",
                "timezone": timezone_name,
                "time": f"{int(schedule['hour']):02d}:{int(schedule['minute']):02d}",
            }
        if kind == "weekly":
            weekdays = schedule.get("weekdays") or [0]
            return {
                "type": "weekly",
                "timezone": timezone_name,
                "time": f"{int(schedule['hour']):02d}:{int(schedule['minute']):02d}",
                "weekday": (int(weekdays[0]) + 1) % 7,
            }
        return {
            "type": "cron",
            "timezone": timezone_name,
            "cron": schedule.get("cron") or schedule.get("expression"),
        }

    @classmethod
    def _run_payload(cls, run: CronjobRun) -> dict[str, Any]:
        state = {"pending": "preparing", "success": "succeeded"}.get(
            run.status, run.status
        )
        updated_at = run.finished_at or run.started_at or run.created_at
        return {
            "userId": run.owner_id,
            "jobId": run.job_id,
            "runId": run.id,
            "revision": run.revision,
            "scheduledAt": cls._iso(run.scheduled_at),
            "sessionId": run.session_id,
            "state": state,
            "createdAt": cls._iso(run.created_at or run.scheduled_at),
            "updatedAt": cls._iso(updated_at or run.scheduled_at),
            "attempt": 0,
            "cancelRequested": run.cancellation_requested_at is not None,
            "acknowledged": run.status in {"running", "success"},
            "runtimeVersion": run.runtime_version,
            "output": run.output,
            "error": run.error,
            "completedAt": cls._iso(run.finished_at),
        }

    @classmethod
    def _run_from_payload(cls, payload: dict[str, Any]) -> CronjobRun:
        if "state" not in payload:
            return CronjobRun.model_validate(payload)
        state = str(payload["state"])
        status = {
            "preparing": "pending",
            "retrying": "retrying",
            "succeeded": "success",
        }.get(state, state)
        updated_at = payload.get("updatedAt")
        return CronjobRun.model_validate(
            {
                "runId": payload["runId"],
                "jobId": payload["jobId"],
                "ownerId": payload["userId"],
                "sessionId": payload["sessionId"],
                "status": status,
                "scheduledAt": payload["scheduledAt"],
                "createdAt": payload.get("createdAt"),
                "startedAt": (updated_at if state in {"running", "retrying"} else None),
                "finishedAt": payload.get("completedAt"),
                "cancellationRequestedAt": (
                    updated_at if payload.get("cancelRequested", False) else None
                ),
                "runtimeVersion": payload.get("runtimeVersion") or "",
                "output": payload.get("output") or "",
                "error": payload.get("error") or "",
                "attempt": payload.get("attempt") or 0,
                "revision": payload.get("revision") or 1,
            }
        )

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Cronjob timestamps must include a timezone.")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _write_etag(self, output: Any, client: Any, key: str) -> str:
        etag = self._etag(output)
        if etag:
            return etag
        response = client.get_object(bucket=self._bucket, key=key)
        etag = self._etag(response)
        if not etag:
            raise RuntimeError("TOS cronjob write did not include an ETag.")
        return etag

    @staticmethod
    def _etag(value: Any) -> str:
        direct = getattr(value, "etag", None)
        if direct:
            return str(direct)
        return str(getattr(getattr(value, "meta", None), "etag", "") or "")

    def _job_key(self, owner_id: str, job_id: str) -> str:
        return f"{self._job_prefix(owner_id, job_id)}/job.json"

    def _run_key(self, owner_id: str, job_id: str, run_id: str) -> str:
        return f"{self._job_prefix(owner_id, job_id)}/runs/{self._part(run_id)}.json"

    def _lock_key(self, owner_id: str, job_id: str) -> str:
        return f"{self._job_prefix(owner_id, job_id)}/lock.json"

    def _job_prefix(self, owner_id: str, job_id: str) -> str:
        return f"{self._owner_prefix(owner_id)}/{self._part(job_id)}"

    def _owner_prefix(self, owner_id: str) -> str:
        return (
            f"{self._root_prefix}/users/{self._part(owner_id)}/cronjobs"
            if self._root_prefix
            else f"users/{self._part(owner_id)}/cronjobs"
        )

    @staticmethod
    def _part(value: str) -> str:
        if not value:
            raise ValueError("Cronjob object key part is required.")
        return quote(value, safe="")


__all__ = [
    "CronjobConflict",
    "CronjobNotFound",
    "Stored",
    "TosCronjobRepository",
]
