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

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


DEV_SANDBOX_TTL_SECONDS = 28_800
MAX_CLOUD_ATTEMPTS = 3
MIN_CLOUD_ATTEMPT_REMAINING_SECONDS = 1_800
INTENT_SUMMARY_PATH = "/home/gem/.vibe/task/intent-summary.json"


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class VibeModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel,
        populate_by_name=True,
        extra="forbid",
    )


class TaskState(StrEnum):
    PROVISIONING = "provisioning"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TaskStage(StrEnum):
    PROVISIONING = "provisioning"
    UNDERSTANDING = "understanding"
    BUILDING = "building"
    LOCAL_VALIDATION = "local_validation"
    CLOUD_BUILD = "cloud_build"
    RUNTIME_VALIDATION = "runtime_validation"
    DELIVERING = "delivering"
    CLEANUP = "cleanup"
    DONE = "done"


TERMINAL_STATES = {
    TaskState.COMPLETED,
    TaskState.PARTIAL,
    TaskState.BLOCKED,
    TaskState.FAILED,
    TaskState.CANCELLED,
    TaskState.EXPIRED,
}


class CreateTaskRequest(VibeModel):
    goal: str = Field(min_length=1, max_length=20_000)
    display_name: str = Field(default="", max_length=80)

    @field_validator("goal")
    @classmethod
    def normalize_goal(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("goal must not be blank")
        return value


class CredentialUpload(VibeModel):
    access_key_id: SecretStr = Field(repr=False)
    secret_access_key: SecretStr = Field(repr=False)
    session_token: SecretStr | None = Field(default=None, repr=False)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude", {"access_key_id", "secret_access_key", "session_token"})
        return super().model_dump(*args, **kwargs)


class IntentSummary(VibeModel):
    revision: int = Field(default=0, ge=0)
    goal: str = Field(default="", max_length=20_000)
    confirmed_requirements: list[str] = Field(default_factory=list, max_length=100)
    constraints: list[str] = Field(default_factory=list, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    open_questions: list[str] = Field(default_factory=list, max_length=100)
    success_criteria: list[str] = Field(default_factory=list, max_length=100)
    architecture_summary: dict[str, Any] = Field(default_factory=dict)
    current_status: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    updated_at: str = ""

    def next_revision(self) -> "IntentSummary":
        return self.model_copy(
            update={
                "revision": self.revision + 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )


class IntentSummaryUpdate(VibeModel):
    expected_revision: int = Field(ge=0)
    summary: IntentSummary


class TaskEvent(VibeModel):
    sequence: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=80)
    stage: TaskStage
    timestamp: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ArtifactInfo(VibeModel):
    revision: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    filename: str


class TaskStatus(VibeModel):
    task_id: str
    display_name: str = ""
    goal: str
    state: TaskState
    stage: TaskStage
    created_at: str
    expires_at: str
    attempt: int = Field(default=0, ge=0, le=MAX_CLOUD_ATTEMPTS)
    last_sequence: int = Field(default=0, ge=0)
    credentials_configured: bool = False
    intent_revision: int = Field(default=0, ge=0)
    validation_runtime_id: str = ""
    validation_runtime_status: str = ""
    artifact: ArtifactInfo | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str = ""

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES
