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

"""Persistent contracts for intelligent-development projects and versions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IntelligentDevelopmentProject(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default="1", alias="schemaVersion")
    project_id: str = Field(alias="projectId", pattern=r"^[0-9a-f]{32}$")
    owner_id: str = Field(alias="ownerId", min_length=1, max_length=1024)
    name: str = Field(min_length=1, max_length=128)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    latest_version_id: str = Field(alias="latestVersionId", pattern=r"^[0-9a-f]{32}$")
    latest_version_created_at: datetime = Field(alias="latestVersionCreatedAt")
    latest_version_verified: bool = Field(alias="latestVersionVerified")
    latest_agent_name: str = Field(
        alias="latestAgentName", min_length=1, max_length=256
    )
    version_count: int = Field(alias="versionCount", ge=1)


class IntelligentDevelopmentVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default="1", alias="schemaVersion")
    project_id: str = Field(alias="projectId", pattern=r"^[0-9a-f]{32}$")
    version_id: str = Field(alias="versionId", pattern=r"^[0-9a-f]{32}$")
    parent_version_id: str | None = Field(
        default=None, alias="parentVersionId", pattern=r"^[0-9a-f]{32}$"
    )
    source_session_id: str = Field(
        alias="sourceSessionId", min_length=1, max_length=256
    )
    created_at: datetime = Field(alias="createdAt")
    intent_summary: str = Field(alias="intentSummary", max_length=2000)
    acceptance_criteria: list[str] = Field(alias="acceptanceCriteria", max_length=50)
    artifact_sha256: str = Field(alias="artifactSha256", pattern=r"^[0-9a-f]{64}$")
    validation_report_sha256: str = Field(
        alias="validationReportSha256", pattern=r"^[0-9a-f]{64}$"
    )
    artifact_size: int = Field(alias="artifactSize", ge=1, le=20 * 1024 * 1024)
    file_count: int = Field(alias="fileCount", ge=1, le=2000)
    agent_name: str = Field(alias="agentName", min_length=1, max_length=256)
    entry_point: str = Field(alias="entryPoint", min_length=1, max_length=512)
    verified: bool
    validation_summary: str = Field(alias="validationSummary", max_length=4000)
    gate_summary: list[str] = Field(alias="gateSummary", max_length=50)
    validated_at: str = Field(alias="validatedAt", max_length=128)


class IntelligentDevelopmentSessionBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default="1", alias="schemaVersion")
    owner_id: str = Field(alias="ownerId", min_length=1, max_length=1024)
    session_id: str = Field(alias="sessionId", min_length=1, max_length=256)
    project_id: str = Field(alias="projectId", pattern=r"^[0-9a-f]{32}$")
    project_name: str = Field(alias="projectName", min_length=1, max_length=128)
    base_version_id: str | None = Field(
        default=None, alias="baseVersionId", pattern=r"^[0-9a-f]{32}$"
    )
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


@dataclass(frozen=True)
class StoredDevelopmentVersion:
    metadata: IntelligentDevelopmentVersion
    artifact: bytes
    validation_report: bytes
