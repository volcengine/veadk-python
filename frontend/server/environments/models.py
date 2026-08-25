# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Validated contracts for Studio execution environments."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EnvironmentOperatingSystem = Literal["ubuntu-22.04", "ubuntu-24.04"]
EnvironmentLanguage = Literal["python-3.10", "python-3.12"]
EnvironmentBuildStatus = Literal[
    "preparing",
    "queued",
    "building",
    "scanning",
    "available",
    "failed",
]
EnvironmentBuildStepStatus = Literal["pending", "running", "succeeded", "failed"]
ResourceSource = Literal["managed", "provided"]
EnvironmentSkillSource = Literal["skillhub", "local", "skillspace"]

SUPPORTED_OPTION_IDS = frozenset(
    {
        "lark-cli",
        "pandoc",
        "opencli",
        "uv",
        "ripgrep",
        "jq",
        "github-cli",
        "playwright",
        "chromium",
        "git",
        "curl",
        "ffmpeg",
        "imagemagick",
    }
)


class EnvironmentSkillFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=512)
    content: str = Field(max_length=256 * 1024)


class EnvironmentSkillSelection(BaseModel):
    """A source reference; local file bodies are moved to TOS before persistence."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source: EnvironmentSkillSource
    folder: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    slug: str = Field(default="", max_length=512)
    namespace: str = Field(default="public", max_length=128)
    local_files: list[EnvironmentSkillFile] = Field(
        default_factory=list, alias="localFiles", max_length=80
    )
    artifact_id: str = Field(default="", alias="artifactId", max_length=64)
    skill_space_id: str = Field(default="", alias="skillSpaceId", max_length=256)
    skill_space_name: str = Field(default="", alias="skillSpaceName", max_length=256)
    skill_space_region: str = Field(default="", alias="skillSpaceRegion", max_length=64)
    skill_id: str = Field(default="", alias="skillId", max_length=256)
    version: str = Field(default="", max_length=256)

    @model_validator(mode="after")
    def normalize(self) -> EnvironmentSkillSelection:
        for field in (
            "folder",
            "name",
            "description",
            "slug",
            "namespace",
            "artifact_id",
            "skill_space_id",
            "skill_space_name",
            "skill_space_region",
            "skill_id",
            "version",
        ):
            setattr(self, field, getattr(self, field).strip())
        if self.source == "skillhub" and not self.slug:
            raise ValueError("Skill Hub 技能缺少 slug。")
        if self.source == "skillspace" and (
            not self.skill_space_id or not self.skill_id
        ):
            raise ValueError("AgentKit Skill 缺少 Skill Space 或 Skill ID。")
        return self


class EnvironmentSkillManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    folder: str
    source: EnvironmentSkillSource
    version: str = ""
    digest: str


class EnvironmentSkillManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills: list[EnvironmentSkillManifestEntry] = Field(default_factory=list)


class EnvironmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    operating_system: EnvironmentOperatingSystem = Field(alias="operatingSystem")
    language: EnvironmentLanguage
    execution_runtime: Literal["veadk"] = Field(
        default="veadk", alias="executionRuntime"
    )
    option_ids: list[str] = Field(
        default_factory=list, alias="optionIds", max_length=32
    )
    selected_skills: list[EnvironmentSkillSelection] = Field(
        default_factory=list, alias="selectedSkills", max_length=20
    )
    dockerfile: str = Field(default="", max_length=128 * 1024)

    @model_validator(mode="after")
    def normalize(self) -> EnvironmentInput:
        self.name = self.name.strip()
        self.description = self.description.strip()
        if not self.name:
            raise ValueError("环境名称不能为空。")
        normalized: list[str] = []
        for option_id in self.option_ids:
            option = option_id.strip()
            if option not in SUPPORTED_OPTION_IDS:
                raise ValueError(f"不支持的环境组件：{option or option_id}")
            if option not in normalized:
                normalized.append(option)
        self.option_ids = normalized
        self.dockerfile = self.dockerfile.strip()
        return self


class EnvironmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    operating_system: EnvironmentOperatingSystem | None = Field(
        default=None, alias="operatingSystem"
    )
    language: EnvironmentLanguage | None = None
    execution_runtime: Literal["veadk"] | None = Field(
        default=None, alias="executionRuntime"
    )
    option_ids: list[str] | None = Field(default=None, alias="optionIds", max_length=32)
    selected_skills: list[EnvironmentSkillSelection] | None = Field(
        default=None, alias="selectedSkills", max_length=20
    )
    dockerfile: str | None = Field(default=None, max_length=128 * 1024)

    @model_validator(mode="after")
    def normalize(self) -> EnvironmentPatch:
        if not self.model_fields_set:
            raise ValueError("至少需要更新一个环境字段。")
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("环境名称不能为空。")
        if self.description is not None:
            self.description = self.description.strip()
        if self.option_ids is not None:
            normalized: list[str] = []
            for option_id in self.option_ids:
                option = option_id.strip()
                if option not in SUPPORTED_OPTION_IDS:
                    raise ValueError(f"不支持的环境组件：{option or option_id}")
                if option not in normalized:
                    normalized.append(option)
            self.option_ids = normalized
        if self.dockerfile is not None:
            self.dockerfile = self.dockerfile.strip()
        return self


class EnvironmentRecord(EnvironmentInput):
    id: str = Field(min_length=32, max_length=32)
    owner_id: str = Field(alias="ownerId", min_length=1, max_length=1024)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    latest_version_id: str | None = Field(default=None, alias="latestVersionId")


class CodePipelineResource(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: ResourceSource
    workspace_id: str = Field(default="", alias="workspaceId")
    workspace_name: str = Field(default="", alias="workspaceName")
    pipeline_id: str = Field(default="", alias="pipelineId")
    pipeline_name: str = Field(default="", alias="pipelineName")
    console_url: str = Field(default="", alias="consoleUrl")


class ContainerRegistryResource(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: ResourceSource
    registry: str
    namespace: str
    repository: str
    domain: str = ""
    image_repository: str = Field(default="", alias="imageRepository")
    console_url: str = Field(default="", alias="consoleUrl")


class EnvironmentResources(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: Literal["volcengine", "byteplus"]
    region: str
    code_pipeline: CodePipelineResource = Field(alias="codePipeline")
    container_registry: ContainerRegistryResource = Field(alias="containerRegistry")


class EnvironmentBuildStep(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=256)
    status: EnvironmentBuildStepStatus
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")


class EnvironmentBuild(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    environment_id: str = Field(alias="environmentId", min_length=32, max_length=32)
    version_id: str = Field(alias="versionId", min_length=1, max_length=128)
    status: EnvironmentBuildStatus
    image: str = ""
    error: str = ""
    run_id: str = Field(default="", alias="runId")
    resources: EnvironmentResources | dict[str, object] = Field(default_factory=dict)
    current_step: str = Field(default="", alias="currentStep")
    steps: list[EnvironmentBuildStep] = Field(default_factory=list)
    progress_error: str = Field(default="", alias="progressError")
    log_tail: str = Field(default="", alias="logTail")
    log_truncated: bool = Field(default=False, alias="logTruncated")
    log_updated_at: datetime | None = Field(default=None, alias="logUpdatedAt")
    log_error: str = Field(default="", alias="logError")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class ResolvedEnvironment(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    environment_id: str = Field(alias="environmentId")
    version_id: str = Field(alias="environmentVersionId")
    image: str
    skills: list[EnvironmentSkillManifestEntry] = Field(default_factory=list)
    resources: EnvironmentResources | dict[str, object] = Field(default_factory=dict)


class EnvironmentView(EnvironmentInput):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(min_length=32, max_length=32)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    latest_version: EnvironmentBuild | None = Field(default=None, alias="latestVersion")


class EnvironmentResourceInfo(EnvironmentResources):
    """System-information contract for the environment build resources."""


__all__ = [
    "SUPPORTED_OPTION_IDS",
    "CodePipelineResource",
    "ContainerRegistryResource",
    "EnvironmentBuild",
    "EnvironmentBuildStatus",
    "EnvironmentBuildStep",
    "EnvironmentBuildStepStatus",
    "EnvironmentInput",
    "EnvironmentLanguage",
    "EnvironmentOperatingSystem",
    "EnvironmentPatch",
    "EnvironmentRecord",
    "EnvironmentResourceInfo",
    "EnvironmentResources",
    "EnvironmentSkillFile",
    "EnvironmentSkillManifest",
    "EnvironmentSkillManifestEntry",
    "EnvironmentSkillSelection",
    "EnvironmentView",
    "ResolvedEnvironment",
    "ResourceSource",
]
