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

"""Validated contracts for durable Studio artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

ArtifactType = Literal["document", "image", "video"]


class ArtifactOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    runtime_id: str = Field(default="", alias="runtimeId", max_length=512)
    region: str = Field(default="", max_length=128)
    event_id: str = Field(default="", alias="eventId", max_length=512)
    invocation_id: str = Field(default="", alias="invocationId", max_length=512)
    tool_name: str = Field(default="", alias="toolName", max_length=256)
    provider_task_id: str = Field(default="", alias="taskId", max_length=512)


class ArtifactRecord(BaseModel):
    """Private persisted metadata; object keys never leave the server."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(min_length=1, max_length=128)
    owner_id: str = Field(alias="ownerId", min_length=1, max_length=1024)
    app_name: str = Field(alias="appName", min_length=1, max_length=512)
    agent_id: str = Field(default="", alias="agentId", max_length=512)
    agent_name: str = Field(alias="agentName", min_length=1, max_length=512)
    session_id: str = Field(alias="sessionId", min_length=1, max_length=512)
    session_title: str = Field(alias="sessionTitle", min_length=1, max_length=1024)
    session_updated_at: datetime = Field(alias="sessionUpdatedAt")
    name: str = Field(min_length=1, max_length=512)
    content_name: str = Field(alias="contentName", min_length=1, max_length=512)
    content_key: str = Field(alias="contentKey", min_length=1, max_length=4096)
    type: ArtifactType
    mime_type: str = Field(alias="mimeType", min_length=1, max_length=256)
    size_bytes: int = Field(alias="sizeBytes", ge=1)
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    description: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source_url_hash: str = Field(alias="sourceUrlHash", min_length=64, max_length=64)
    origin: ArtifactOrigin = Field(default_factory=ArtifactOrigin)


class ArtifactIngestCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_url: HttpUrl = Field(alias="sourceUrl")
    name: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(default="", alias="mimeType", max_length=256)
    app_name: str = Field(alias="appName", min_length=1, max_length=512)
    agent_id: str = Field(default="", alias="agentId", max_length=512)
    agent_name: str = Field(alias="agentName", min_length=1, max_length=512)
    session_id: str = Field(alias="sessionId", min_length=1, max_length=512)
    session_title: str = Field(alias="sessionTitle", min_length=1, max_length=1024)
    session_updated_at: datetime = Field(alias="sessionUpdatedAt")
    created_at: datetime = Field(alias="createdAt")
    origin: ArtifactOrigin


class ArtifactSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    candidates: list[ArtifactIngestCandidate] = Field(
        default_factory=list, max_length=100
    )


class ArtifactMetadataPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_update(self) -> ArtifactMetadataPatch:
        if self.name is None and self.description is None and self.tags is None:
            raise ValueError("At least one artifact field must be updated.")
        if self.tags is not None:
            normalized: list[str] = []
            for raw in self.tags:
                tag = raw.strip()
                if not tag or len(tag) > 64:
                    raise ValueError("Artifact tags must contain 1 to 64 characters.")
                if tag not in normalized:
                    normalized.append(tag)
            self.tags = normalized
        return self


class ArtifactLibraryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    app_name: str = Field(alias="appName")
    agent_id: str = Field(default="", alias="agentId")
    session_id: str = Field(alias="sessionId")
    session_title: str = Field(alias="sessionTitle")
    agent_name: str = Field(alias="agentName")
    session_updated_at: datetime = Field(alias="sessionUpdatedAt")
    name: str
    version: int
    type: ArtifactType
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    mime_type: str = Field(alias="mimeType")
    size_bytes: int = Field(alias="sizeBytes")
    can_manage: bool = Field(default=True, alias="canManage")
    thumbnail_url: str = Field(default="", alias="thumbnailUrl")
    content_url: str = Field(default="", alias="contentUrl")
    origin: ArtifactOrigin
    preview: dict[str, str | int]


class ArtifactListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    items: list[ArtifactLibraryItem]


__all__ = [
    "ArtifactIngestCandidate",
    "ArtifactLibraryItem",
    "ArtifactListResponse",
    "ArtifactMetadataPatch",
    "ArtifactOrigin",
    "ArtifactRecord",
    "ArtifactSyncRequest",
    "ArtifactType",
]
