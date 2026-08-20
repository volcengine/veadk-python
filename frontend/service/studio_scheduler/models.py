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

"""Small validated domain contracts shared by scheduler adapters."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ProviderName = Literal["volcengine", "byteplus"]
ScheduleKind = Literal["once", "daily", "weekly", "cron"]
RunState = Literal[
    "queued",
    "preparing",
    "running",
    "retrying",
    "succeeded",
    "failed",
    "cancelled",
    "skipped",
]


def _aware_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(timezone.utc)


def _required(data: dict[str, object], camel: str, snake: str | None = None) -> object:
    if camel in data:
        return data[camel]
    if snake and snake in data:
        return data[snake]
    raise ValueError(f"Missing required field: {camel}")


def _datetime(value: object, name: str) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value, name)
    if not isinstance(value, str):
        raise TypeError(f"{name} must be an ISO-8601 datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 datetime") from error
    return _aware_utc(parsed, name)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError(f"{name} must be an integer")
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


@dataclass(frozen=True)
class Schedule:
    """One user-visible schedule, evaluated in its declared IANA timezone."""

    kind: ScheduleKind
    timezone: str
    run_at: datetime | None = None
    hour: int | None = None
    minute: int | None = None
    weekdays: tuple[int, ...] = ()
    cron: str = ""

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown schedule timezone: {self.timezone}") from error
        if self.kind == "once":
            if self.run_at is None:
                raise ValueError("once schedule requires runAt")
            object.__setattr__(self, "run_at", _aware_utc(self.run_at, "runAt"))
        elif self.kind in {"daily", "weekly"}:
            if self.hour is None or not 0 <= self.hour <= 23:
                raise ValueError(f"{self.kind} schedule requires hour from 0 to 23")
            if self.minute is None or not 0 <= self.minute <= 59:
                raise ValueError(f"{self.kind} schedule requires minute from 0 to 59")
            if self.kind == "weekly" and (
                not self.weekdays or any(day not in range(7) for day in self.weekdays)
            ):
                raise ValueError("weekly schedule requires weekdays from 0 to 6")
            object.__setattr__(self, "weekdays", tuple(sorted(set(self.weekdays))))
        elif self.kind == "cron" and len(self.cron.split()) != 5:
            raise ValueError("cron schedule requires a five-field expression")

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Schedule:
        kind = str(data.get("kind", data.get("type", "")))
        if kind not in {"once", "daily", "weekly", "cron"}:
            raise ValueError(f"Unsupported schedule kind: {kind}")
        run_at_value = data.get("runAt", data.get("run_at"))
        weekdays_value = data.get("weekdays") or ()
        if not isinstance(weekdays_value, (list, tuple)):
            raise TypeError("weekdays must be an array")
        return cls(
            kind=cast(ScheduleKind, kind),
            timezone=str(_required(data, "timezone")),
            run_at=_datetime(run_at_value, "runAt") if run_at_value else None,
            hour=_int(data["hour"], "hour") if data.get("hour") is not None else None,
            minute=(
                _int(data["minute"], "minute")
                if data.get("minute") is not None
                else None
            ),
            weekdays=tuple(_int(day, "weekday") for day in weekdays_value),
            cron=str(data.get("cron", data.get("expression", "")) or ""),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "timezone": self.timezone,
            "runAt": _iso(self.run_at),
            "hour": self.hour,
            "minute": self.minute,
            "weekdays": list(self.weekdays),
            "cron": self.cron,
        }


@dataclass(frozen=True)
class RuntimeTarget:
    """Non-secret Runtime coordinates stored with a job."""

    provider: ProviderName
    runtime_id: str
    agent_name: str
    region: str
    project_name: str = "default"

    def __post_init__(self) -> None:
        if self.provider not in {"volcengine", "byteplus"}:
            raise ValueError(f"Unsupported Runtime provider: {self.provider}")
        if not all(
            value.strip()
            for value in (
                self.runtime_id,
                self.agent_name,
                self.region,
                self.project_name,
            )
        ):
            raise ValueError("Runtime target fields must not be empty")

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> RuntimeTarget:
        provider = str(_required(data, "provider"))
        return cls(
            provider=cast(ProviderName, provider),
            runtime_id=str(_required(data, "runtimeId", "runtime_id")),
            agent_name=str(_required(data, "agentName", "agent_name")),
            region=str(_required(data, "region")),
            project_name=str(
                data.get("projectName", data.get("project_name", "default"))
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "runtimeId": self.runtime_id,
            "agentName": self.agent_name,
            "region": self.region,
            "projectName": self.project_name,
        }


@dataclass(frozen=True)
class CronJob:
    """Durable job definition loaded from a user's TOS namespace."""

    user_id: str
    job_id: str
    revision: int
    enabled: bool
    prompt: str
    runtime: RuntimeTarget
    schedule: Schedule
    max_runtime_seconds: int = 3600

    def __post_init__(self) -> None:
        if not self.user_id or not self.job_id or not self.prompt.strip():
            raise ValueError("Cron job identity and prompt must not be empty")
        if self.revision < 1:
            raise ValueError("Cron job revision must be positive")
        if not 60 <= self.max_runtime_seconds <= 86400:
            raise ValueError("maxRuntimeSeconds must be between 60 and 86400")

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
        *,
        default_provider: ProviderName | None = None,
    ) -> CronJob:
        runtime = data.get("runtime")
        schedule = _required(data, "schedule")
        if not isinstance(schedule, dict):
            raise TypeError("schedule must be an object")
        if runtime is None:
            provider = data.get("provider") or default_provider
            if provider is None:
                raise ValueError("Cron job is missing its Runtime provider")
            runtime = {
                "provider": provider,
                "runtimeId": _required(data, "runtimeId", "runtime_id"),
                "agentName": _required(data, "agentName", "agent_name"),
                "region": _required(data, "region"),
                "projectName": data.get("projectName", "default"),
            }
        if not isinstance(runtime, dict):
            raise TypeError("runtime must be an object")
        return cls(
            user_id=str(
                data.get("userId", data.get("user_id", data.get("ownerId", "")))
            ),
            job_id=str(_required(data, "jobId", "job_id")),
            revision=_int(_required(data, "revision"), "revision"),
            enabled=bool(_required(data, "enabled")),
            prompt=str(_required(data, "prompt")),
            runtime=RuntimeTarget.from_dict(runtime),
            schedule=Schedule.from_dict(schedule),
            max_runtime_seconds=_int(
                data.get("maxRuntimeSeconds", data.get("max_runtime_seconds", 3600)),
                "maxRuntimeSeconds",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "userId": self.user_id,
            "jobId": self.job_id,
            "revision": self.revision,
            "enabled": self.enabled,
            "prompt": self.prompt,
            "runtime": self.runtime.to_dict(),
            "schedule": self.schedule.to_dict(),
            "maxRuntimeSeconds": self.max_runtime_seconds,
        }


@dataclass(frozen=True)
class DuePointer:
    """Minimal global pointer used to find jobs due in one minute."""

    user_id: str
    job_id: str
    revision: int
    scheduled_at: datetime

    def __post_init__(self) -> None:
        if not self.user_id or not self.job_id or self.revision < 1:
            raise ValueError("Due pointer identity and revision are invalid")
        object.__setattr__(
            self,
            "scheduled_at",
            _aware_utc(self.scheduled_at, "scheduledAt").replace(
                second=0, microsecond=0
            ),
        )

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DuePointer:
        return cls(
            user_id=str(_required(data, "userId", "user_id")),
            job_id=str(_required(data, "jobId", "job_id")),
            revision=_int(_required(data, "revision"), "revision"),
            scheduled_at=_datetime(
                _required(data, "scheduledAt", "scheduled_at"), "scheduledAt"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "userId": self.user_id,
            "jobId": self.job_id,
            "revision": self.revision,
            "scheduledAt": _iso(self.scheduled_at),
        }


def deterministic_run_id(pointer: DuePointer) -> str:
    """Return the same opaque run id for every delivery of one due pointer."""
    value = "\0".join(
        (
            pointer.user_id,
            pointer.job_id,
            _iso(pointer.scheduled_at) or "",
        )
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScheduledRun:
    """Complete mutable-by-CAS execution state stored in TOS."""

    user_id: str
    job_id: str
    run_id: str
    revision: int
    scheduled_at: datetime
    session_id: str
    state: RunState
    created_at: datetime
    updated_at: datetime
    attempt: int = 0
    cancel_requested: bool = False
    acknowledged: bool = False
    runtime_version: str = ""
    output: str = ""
    error: str = ""
    completed_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ScheduledRun:
        state = str(_required(data, "state"))
        valid_states = {
            "queued",
            "preparing",
            "running",
            "retrying",
            "succeeded",
            "failed",
            "cancelled",
            "skipped",
        }
        if state not in valid_states:
            raise ValueError(f"Unsupported run state: {state}")
        completed = data.get("completedAt", data.get("completed_at"))
        return cls(
            user_id=str(_required(data, "userId", "user_id")),
            job_id=str(_required(data, "jobId", "job_id")),
            run_id=str(_required(data, "runId", "run_id")),
            revision=_int(_required(data, "revision"), "revision"),
            scheduled_at=_datetime(
                _required(data, "scheduledAt", "scheduled_at"), "scheduledAt"
            ),
            session_id=str(_required(data, "sessionId", "session_id")),
            state=cast(RunState, state),
            created_at=_datetime(
                _required(data, "createdAt", "created_at"), "createdAt"
            ),
            updated_at=_datetime(
                _required(data, "updatedAt", "updated_at"), "updatedAt"
            ),
            attempt=_int(data.get("attempt") or 0, "attempt"),
            cancel_requested=bool(
                data.get("cancelRequested", data.get("cancel_requested", False))
            ),
            acknowledged=bool(data.get("acknowledged", False)),
            runtime_version=str(
                data.get("runtimeVersion", data.get("runtime_version", "")) or ""
            ),
            output=str(data.get("output") or ""),
            error=str(data.get("error") or ""),
            completed_at=_datetime(completed, "completedAt") if completed else None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "userId": self.user_id,
            "jobId": self.job_id,
            "runId": self.run_id,
            "revision": self.revision,
            "scheduledAt": _iso(self.scheduled_at),
            "sessionId": self.session_id,
            "state": self.state,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
            "attempt": self.attempt,
            "cancelRequested": self.cancel_requested,
            "acknowledged": self.acknowledged,
            "runtimeVersion": self.runtime_version,
            "output": self.output,
            "error": self.error,
            "completedAt": _iso(self.completed_at),
        }


@dataclass(frozen=True)
class JobLock:
    run_id: str
    replica_id: str
    state: Literal["held", "released"]
    acquired_at: datetime
    expires_at: datetime
    released_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> JobLock:
        state = str(_required(data, "state"))
        if state not in {"held", "released"}:
            raise ValueError(f"Unsupported lock state: {state}")
        released = data.get("releasedAt")
        return cls(
            run_id=str(_required(data, "runId")),
            replica_id=str(_required(data, "replicaId")),
            state=cast(Literal["held", "released"], state),
            acquired_at=_datetime(_required(data, "acquiredAt"), "acquiredAt"),
            expires_at=_datetime(_required(data, "expiresAt"), "expiresAt"),
            released_at=_datetime(released, "releasedAt") if released else None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "runId": self.run_id,
            "replicaId": self.replica_id,
            "state": self.state,
            "acquiredAt": _iso(self.acquired_at),
            "expiresAt": _iso(self.expires_at),
            "releasedAt": _iso(self.released_at),
        }


@dataclass(frozen=True)
class LockAttempt:
    acquired: bool
    active_run_id: str = ""
    abandoned_run_id: str = ""


@dataclass(frozen=True)
class ExecutionRequest:
    run_id: str
    session_id: str
    user_id: str
    job_id: str
    prompt: str
    runtime: RuntimeTarget
    timeout_seconds: int
    service_identity: bool = True


@dataclass(frozen=True)
class ExecutionResult:
    output: str
    runtime_version: str = ""
    session_id: str = ""


class RuntimeInvocationError(RuntimeError):
    """Runtime failure annotated with the only safe automatic-retry boundary."""

    def __init__(self, message: str, *, acknowledged: bool, retryable: bool) -> None:
        super().__init__(message)
        self.acknowledged = acknowledged
        self.retryable = retryable


@dataclass(frozen=True)
class DispatchSummary:
    scanned: int = 0
    started: int = 0
    stale: int = 0
    skipped: int = 0
    failed: int = 0
