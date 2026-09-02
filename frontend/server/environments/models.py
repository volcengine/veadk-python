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

"""Validated contracts for Studio execution environments."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EnvironmentOperatingSystem = Literal["ubuntu-22.04", "ubuntu-24.04"]
EnvironmentBaseEnvironment = Literal["ubuntu", "aio-sandbox", "codex-sandbox"]
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
_IMAGE_TAG_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")

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


class GitSource(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    repository_url: str = Field(alias="repositoryUrl", min_length=1, max_length=2048)
    ref: str = Field(default="", max_length=512)
    dockerfile_path: str = Field(alias="dockerfilePath", min_length=1, max_length=1024)

    @model_validator(mode="after")
    def normalize(self) -> GitSource:
        self.repository_url = self.repository_url.strip()
        self.ref = self.ref.strip()
        self.dockerfile_path = _safe_repository_path(
            self.dockerfile_path, label="Dockerfile"
        )
        return self


class ContainerRepository(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str = Field(min_length=1, max_length=128)
    registry: str = Field(min_length=1, max_length=256)
    namespace: str = Field(min_length=1, max_length=256)
    repository: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def normalize(self) -> ContainerRepository:
        for field in ("region", "registry", "namespace", "repository"):
            value = getattr(self, field).strip()
            if (
                not value
                or value in {".", ".."}
                or any(char.isspace() for char in value)
            ):
                raise ValueError(f"容器镜像仓库 {field} 无效。")
            setattr(self, field, value)
        return self


class ImageSource(ContainerRepository):
    reference: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def normalize_reference(self) -> ImageSource:
        self.reference = self.reference.strip()
        if not self.reference or any(char.isspace() for char in self.reference):
            raise ValueError("镜像 Tag 或 Digest 无效。")
        if self.reference.startswith("sha256:"):
            digest = self.reference.removeprefix("sha256:")
            if len(digest) != 64 or any(
                char not in "0123456789abcdefABCDEF" for char in digest
            ):
                raise ValueError("镜像 Digest 必须是完整的 sha256 值。")
        elif not _IMAGE_TAG_RE.fullmatch(self.reference):
            raise ValueError("镜像 Tag 无效。")
        return self


class RepositoryInspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    repository_url: str = Field(alias="repositoryUrl", min_length=1, max_length=2048)
    ref: str = Field(default="", max_length=512)


class RepositoryInspection(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    repository_url: str = Field(alias="repositoryUrl")
    ref: str
    commit_sha: str = Field(alias="commitSha")
    dockerfiles: list[str]


class EnvironmentShareCodesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    share_codes: list[str] = Field(alias="shareCodes", min_length=1, max_length=20)

    @model_validator(mode="after")
    def normalize(self) -> EnvironmentShareCodesRequest:
        normalized: list[str] = []
        for value in self.share_codes:
            code = value.strip()
            if not code:
                raise ValueError("分享码不能为空。")
            normalized.append(code)
        self.share_codes = normalized
        return self


class EnvironmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    base_environment: EnvironmentBaseEnvironment = Field(
        default="ubuntu", alias="baseEnvironment"
    )
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
    git_source: GitSource | None = Field(default=None, alias="gitSource")
    image_source: ImageSource | None = Field(default=None, alias="imageSource")
    container_repository: ContainerRepository | None = Field(
        default=None, alias="containerRepository"
    )

    @model_validator(mode="after")
    def normalize(self) -> EnvironmentInput:
        self.name = self.name.strip()
        self.description = self.description.strip()
        self.dockerfile = self.dockerfile.strip()
        if (
            "base_environment" not in self.model_fields_set
            and "/codexenv:" in self.dockerfile.lower()
        ):
            self.base_environment = "codex-sandbox"
        elif (
            "base_environment" not in self.model_fields_set
            and "aio.sandbox" in self.dockerfile.lower()
        ):
            self.base_environment = "aio-sandbox"
        if self.base_environment in {"aio-sandbox", "codex-sandbox"}:
            self.operating_system = "ubuntu-22.04"
            self.language = "python-3.12"
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
        if self.git_source is not None and self.image_source is not None:
            raise ValueError("代码仓库构建与已有镜像绑定不能同时配置。")
        if self.container_repository is not None and self.git_source is None:
            raise ValueError("仅代码仓库构建可以指定目标 CR Repository。")
        if self.image_source is not None and self.selected_skills:
            raise ValueError("已有镜像无法追加环境技能，请在镜像流水线中预先安装。")
        return self


class EnvironmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    base_environment: EnvironmentBaseEnvironment | None = Field(
        default=None, alias="baseEnvironment"
    )
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
    git_source: GitSource | None = Field(default=None, alias="gitSource")
    image_source: ImageSource | None = Field(default=None, alias="imageSource")
    container_repository: ContainerRepository | None = Field(
        default=None, alias="containerRepository"
    )

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
    region: str = ""
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
    tool_id: str = Field(default="", alias="toolId")
    tool_status: Literal["", "creating", "ready", "failed"] = Field(
        default="", alias="toolStatus"
    )
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
    source_commit_sha: str = Field(default="", alias="sourceCommitSha")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class EnvironmentManifestMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    version: str
    description: str = ""


class EnvironmentManifestSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    image: str
    base_environment: EnvironmentBaseEnvironment = Field(alias="baseEnvironment")
    base_image: str = Field(alias="baseImage")
    operating_system: EnvironmentOperatingSystem = Field(alias="operatingSystem")
    language: EnvironmentLanguage
    execution_runtime: Literal["veadk"] = Field(alias="executionRuntime")
    packages: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    skills: list[EnvironmentSkillManifestEntry] = Field(default_factory=list)


class EnvironmentManifestStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    phase: EnvironmentBuildStatus
    tool_id: str = Field(default="", alias="toolId")
    tool_status: Literal["", "creating", "ready", "failed"] = Field(
        default="", alias="toolStatus"
    )
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class EnvironmentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_version: Literal["agentkit.studio/v1alpha1"] = Field(alias="apiVersion")
    kind: Literal["Environment"] = "Environment"
    metadata: EnvironmentManifestMetadata
    spec: EnvironmentManifestSpec
    status: EnvironmentManifestStatus


class ResolvedEnvironment(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    environment_id: str = Field(alias="environmentId")
    version_id: str = Field(alias="environmentVersionId")
    image: str
    tool_id: str = Field(default="", alias="toolId")
    tool_status: Literal["", "creating", "ready", "failed"] = Field(
        default="", alias="toolStatus"
    )
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


class EnvironmentShareCodeExport(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    share_code: str = Field(alias="shareCode")
    name: str


class EnvironmentShareCodeInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    valid: bool
    name: str = ""
    error: str = ""


class EnvironmentShareCodeInspectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EnvironmentShareCodeInspection]


class EnvironmentShareCodeImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    status: Literal["created", "duplicate", "failed"]
    name: str = ""
    error: str = ""
    environment: EnvironmentView | None = None


class EnvironmentShareCodeImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    items: list[EnvironmentShareCodeImportItem]
    created_count: int = Field(alias="createdCount")
    duplicate_count: int = Field(alias="duplicateCount")
    failed_count: int = Field(alias="failedCount")


__all__ = [
    "SUPPORTED_OPTION_IDS",
    "CodePipelineResource",
    "ContainerRegistryResource",
    "ContainerRepository",
    "EnvironmentBaseEnvironment",
    "EnvironmentBuild",
    "EnvironmentBuildStatus",
    "EnvironmentBuildStep",
    "EnvironmentBuildStepStatus",
    "EnvironmentInput",
    "EnvironmentLanguage",
    "EnvironmentManifest",
    "EnvironmentManifestMetadata",
    "EnvironmentManifestSpec",
    "EnvironmentManifestStatus",
    "EnvironmentOperatingSystem",
    "EnvironmentPatch",
    "EnvironmentRecord",
    "EnvironmentResourceInfo",
    "EnvironmentResources",
    "EnvironmentShareCodeExport",
    "EnvironmentShareCodeImportItem",
    "EnvironmentShareCodeImportResponse",
    "EnvironmentShareCodeInspection",
    "EnvironmentShareCodeInspectionResponse",
    "EnvironmentShareCodesRequest",
    "EnvironmentSkillFile",
    "EnvironmentSkillManifest",
    "EnvironmentSkillManifestEntry",
    "EnvironmentSkillSelection",
    "EnvironmentView",
    "GitSource",
    "ImageSource",
    "RepositoryInspectRequest",
    "RepositoryInspection",
    "ResolvedEnvironment",
    "ResourceSource",
]


def _safe_repository_path(value: str, *, label: str) -> str:
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{label} 路径必须是仓库内的安全相对路径。")
    return path.as_posix()
