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

"""Validated contracts for Studio-owned automatic evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    model_validator,
)

EvaluationKind = Literal["good", "bad"]
AutomaticEvaluationState = Literal["pending", "running"]
OptimizationPriority = Literal["high", "medium", "low"]
OptimizationModule = Literal[
    "agent_structure",
    "prompt",
    "tool",
    "knowledge",
    "memory",
    "workflow",
    "other",
]


class RunSseActivity(BaseModel):
    """Minimum trusted context retained after a Studio ``run_sse`` request."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    runtime_id: str = Field(alias="runtimeId", min_length=1)
    region: str = Field(min_length=1)
    project_name: str = Field(alias="projectName", min_length=1)
    app_name: str = Field(alias="appName", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)
    session_id: str = Field(alias="sessionId", min_length=1)
    runtime_endpoint: str = Field(alias="runtimeEndpoint", min_length=1)
    runtime_authorization: SecretStr = Field(
        alias="runtimeAuthorization",
        exclude=True,
        repr=False,
    )
    completed_at: datetime = Field(
        alias="completedAt",
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @property
    def key(self) -> tuple[str, str, str, str]:
        return self.runtime_id, self.app_name, self.user_id, self.session_id

    @classmethod
    def from_proxy(
        cls,
        payload: dict[str, object],
        *,
        runtime_id: str,
        region: str,
        project_name: str,
        runtime_endpoint: str,
        runtime_authorization: str,
    ) -> RunSseActivity:
        def required(*names: str) -> str:
            for name in names:
                value = payload.get(name)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            raise ValueError(f"run_sse payload is missing {names[0]}")

        return cls(
            runtimeId=runtime_id,
            region=region,
            projectName=project_name or "default",
            appName=required("app_name", "appName"),
            userId=required("user_id", "userId"),
            sessionId=required("session_id", "sessionId"),
            runtimeEndpoint=runtime_endpoint.rstrip("/"),
            runtimeAuthorization=SecretStr(runtime_authorization),
        )


class AutomaticEvaluationStatus(BaseModel):
    """Current server-owned automatic evaluation state for one Session."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    runtime_id: str = Field(alias="runtimeId", min_length=1)
    app_name: str = Field(alias="appName", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)
    session_id: str = Field(alias="sessionId", min_length=1)
    state: AutomaticEvaluationState
    scheduled_at: datetime = Field(alias="scheduledAt")
    due_at: datetime = Field(alias="dueAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")


class AutoEvaluationOutput(BaseModel):
    """Strict model output for one completed conversational turn."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)


class OptimizationSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=2000)


class OptimizationGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    priority: OptimizationPriority
    module: OptimizationModule
    custom_module: str | None = Field(
        default=None,
        alias="customModule",
        validation_alias=AliasChoices("customModule", "custom_module"),
        max_length=100,
    )
    items: list[OptimizationSuggestion] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_custom_module(self) -> OptimizationGroup:
        custom = (self.custom_module or "").strip()
        if self.module == "other" and not custom:
            raise ValueError("customModule is required when module is other")
        if self.module != "other" and custom:
            raise ValueError("customModule must be null unless module is other")
        self.custom_module = custom or None
        return self


class OptimizationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: list[OptimizationGroup] = Field(max_length=30)

    @model_validator(mode="after")
    def validate_unique_groups(self) -> OptimizationOutput:
        keys = [
            (group.priority, group.module, group.custom_module or "")
            for group in self.groups
        ]
        if len(keys) != len(set(keys)):
            raise ValueError(
                "optimization groups must be unique per priority and module"
            )
        return self


class AutoEvaluationCase(BaseModel):
    """One automatic evaluation item in the shape consumed by the frontend."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = ""
    item_key: str = Field(alias="itemKey", min_length=1)
    kind: EvaluationKind
    input: str
    output: str
    reference_output: str = Field(default="", alias="referenceOutput")
    comment: str = ""
    agent_name: str = Field(alias="agentName")
    session_id: str = Field(alias="sessionId")
    message_id: str = Field(alias="messageId")
    runtime_id: str = Field(alias="runtimeId")
    invocation_id: str = Field(default="", alias="invocationId")
    user_id: str = Field(alias="userId")
    created_at: str = Field(default="", alias="createdAt")
    evaluation_set_id: str = Field(default="", alias="evaluationSetId")
    evaluation_set_name: str = Field(default="", alias="evaluationSetName")
    workspace_id: str = Field(default="", alias="workspaceId")
    source: Literal["auto"] = "auto"
    score: float = Field(ge=0, le=1)
    reason: str
    evaluator_version: str = Field(alias="evaluatorVersion")

    def field_values(self) -> dict[str, str]:
        return {
            "input": self.input,
            "reference_output": self.reference_output,
            "output": self.output,
            "feedback_comment": self.comment,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "runtime_id": self.runtime_id,
            "invocation_id": self.invocation_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "source": self.source,
            "score": str(self.score),
            "reason": self.reason,
            "evaluator_version": self.evaluator_version,
        }


class OptimizationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    runtime_id: str = Field(alias="runtimeId")
    app_name: str = Field(alias="appName")
    generated_at: datetime = Field(
        alias="generatedAt",
        default_factory=lambda: datetime.now(timezone.utc),
    )
    optimizer_version: str = Field(alias="optimizerVersion")
    source_item_keys: list[str] = Field(alias="sourceItemKeys")
    groups: list[OptimizationGroup]
