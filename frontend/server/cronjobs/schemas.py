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

"""Validated API and persistence contracts for Studio cronjobs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _ZonedSchedule(_Model):
    timezone: str = Field(min_length=1, max_length=128)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError(
                "schedule timezone must be a valid IANA timezone"
            ) from error
        return value


class OnceSchedule(_ZonedSchedule):
    type: Literal["once"] = "once"
    once_at: str = Field(alias="onceAt", min_length=1, max_length=64)

    @field_validator("once_at")
    @classmethod
    def validate_once_at(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("onceAt must be an ISO-8601 datetime") from error
        return value


class DailySchedule(_ZonedSchedule):
    type: Literal["daily"] = "daily"
    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class WeeklySchedule(_ZonedSchedule):
    type: Literal["weekly"] = "weekly"
    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    weekday: int = Field(ge=0, le=6)


class CronSchedule(_ZonedSchedule):
    type: Literal["cron"] = "cron"
    cron: str = Field(min_length=1, max_length=256)

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized.split(" ")) != 5:
            raise ValueError("cron expression must contain exactly five fields")
        return normalized


Schedule = Annotated[
    OnceSchedule | DailySchedule | WeeklySchedule | CronSchedule,
    Field(discriminator="type"),
]


class CreateCronjobRequest(_Model):
    name: str = Field(min_length=1, max_length=256)
    runtime_id: str = Field(alias="runtimeId", min_length=1, max_length=512)
    runtime_name: str = Field(alias="runtimeName", min_length=1, max_length=512)
    agent_name: str = Field(alias="agentName", min_length=1, max_length=512)
    region: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=32_768)
    schedule: Schedule
    enabled: bool = True

    @field_validator(
        "name", "runtime_id", "runtime_name", "agent_name", "region", "prompt"
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class UpdateCronjobRequest(_Model):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    runtime_id: str | None = Field(
        default=None, alias="runtimeId", min_length=1, max_length=512
    )
    runtime_name: str | None = Field(
        default=None, alias="runtimeName", min_length=1, max_length=512
    )
    agent_name: str | None = Field(
        default=None, alias="agentName", min_length=1, max_length=512
    )
    region: str | None = Field(default=None, min_length=1, max_length=128)
    prompt: str | None = Field(default=None, min_length=1, max_length=32_768)
    schedule: Schedule | None = None
    enabled: bool | None = None

    @field_validator(
        "name", "runtime_id", "runtime_name", "agent_name", "region", "prompt"
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> UpdateCronjobRequest:
        if not self.model_fields_set:
            raise ValueError("At least one cronjob field must be updated.")
        return self


class Cronjob(_Model):
    job_id: str = Field(alias="jobId", min_length=1, max_length=128)
    owner_id: str = Field(alias="ownerId", min_length=1, max_length=1024)
    name: str = Field(min_length=1, max_length=256)
    runtime_id: str = Field(alias="runtimeId", min_length=1, max_length=512)
    runtime_name: str = Field(alias="runtimeName", min_length=1, max_length=512)
    agent_name: str = Field(alias="agentName", min_length=1, max_length=512)
    region: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=32_768)
    schedule: Schedule
    enabled: bool = True
    revision: int = Field(ge=1)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    next_run_at: datetime | None = Field(default=None, alias="nextRunAt")
    latest_run: CronjobRun | None = Field(default=None, alias="latestRun")

    @property
    def id(self) -> str:
        return self.job_id


RunStatus = Literal[
    "queued",
    "pending",
    "running",
    "retrying",
    "success",
    "failed",
    "cancelled",
    "skipped",
]
RunTrigger = Literal["scheduled", "manual"]


class CronjobRun(_Model):
    run_id: str = Field(alias="runId", min_length=1, max_length=128)
    job_id: str = Field(alias="jobId", min_length=1, max_length=128)
    owner_id: str = Field(alias="ownerId", min_length=1, max_length=1024)
    session_id: str = Field(alias="sessionId", min_length=1, max_length=512)
    status: RunStatus
    scheduled_at: datetime = Field(alias="scheduledAt")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    cancellation_requested_at: datetime | None = Field(
        default=None, alias="cancellationRequestedAt"
    )
    runtime_version: str = Field(default="", alias="runtimeVersion", max_length=512)
    output: str = Field(default="", max_length=1_000_000)
    error: str = Field(default="", max_length=32_768)
    attempt: int = Field(default=0, ge=0)
    revision: int = Field(default=1, ge=1, exclude=True)

    @property
    def terminal(self) -> bool:
        return self.status in {"success", "failed", "cancelled", "skipped"}

    @property
    def id(self) -> str:
        return self.run_id


class CronjobLock(_Model):
    job_id: str = Field(alias="jobId", min_length=1, max_length=128)
    owner_id: str = Field(alias="ownerId", min_length=1, max_length=1024)
    run_id: str = Field(alias="runId", min_length=1, max_length=128)
    state: Literal["held", "released"]
    acquired_at: datetime = Field(alias="acquiredAt")
    updated_at: datetime = Field(alias="updatedAt")
    expires_at: datetime = Field(alias="expiresAt")

    def active_at(self, now: datetime) -> bool:
        return self.state == "held" and self.expires_at > now


class CronjobIdentity(_Model):
    owner_id: str = Field(alias="ownerId", min_length=1, max_length=1024)
    is_admin: bool = Field(default=False, alias="isAdmin", exclude=True)


class CronjobListResponse(_Model):
    items: list[Cronjob]


class CronjobRunListResponse(_Model):
    items: list[CronjobRun]


__all__ = [
    "CreateCronjobRequest",
    "CronSchedule",
    "Cronjob",
    "CronjobIdentity",
    "CronjobListResponse",
    "CronjobLock",
    "CronjobRun",
    "CronjobRunListResponse",
    "DailySchedule",
    "OnceSchedule",
    "RunStatus",
    "RunTrigger",
    "Schedule",
    "UpdateCronjobRequest",
    "WeeklySchedule",
]
