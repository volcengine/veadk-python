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

"""Environment CRUD and image-build orchestration independent from FastAPI."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import io
import ipaddress
import json
import re
import tarfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from veadk.cli.generated_agent_codegen import (
    AgentDraft,
    GeneratedFile,
    GeneratedProject,
    SelectedSkill,
)
from veadk.cli.generated_agent_skills import (
    SkillSpaceResolver,
    materialize_selected_skills,
    skill_name_from_markdown,
)

from .dockerfile import (
    build_dockerfile,
    environment_base_image,
    environment_capabilities,
)
from .git_repository import (
    GitRepositoryInspector,
    PublicGitRepositoryInspector,
    RepositoryFile,
)
from .models import (
    ContainerRepository,
    EnvironmentBuild,
    EnvironmentBuildStatus,
    EnvironmentBuildStep,
    EnvironmentBuildStepStatus,
    EnvironmentInput,
    EnvironmentManifest,
    EnvironmentManifestMetadata,
    EnvironmentManifestSpec,
    EnvironmentManifestStatus,
    EnvironmentPatch,
    EnvironmentRecord,
    EnvironmentResourceInfo,
    EnvironmentResources,
    EnvironmentShareCodeExport,
    EnvironmentShareCodeImportItem,
    EnvironmentShareCodeImportResponse,
    EnvironmentShareCodeInspection,
    EnvironmentShareCodeInspectionResponse,
    EnvironmentSkillFile,
    EnvironmentSkillManifest,
    EnvironmentSkillManifestEntry,
    EnvironmentSkillSelection,
    EnvironmentView,
    RepositoryInspection,
    ResolvedEnvironment,
)
from .repository import (
    EnvironmentConflict,
    EnvironmentStorageUnavailable,
    TosEnvironmentRepository,
)
from .resources import EnvironmentCloudGateway
from .tool_provisioning import EnvironmentToolProvisioner


class WorkspaceReferenceLookup(Protocol):
    async def workspace_names_for_environment(
        self, owner_id: str, environment_id: str
    ) -> list[str]: ...


class EnvironmentShareCodeError(ValueError):
    pass


@dataclass(frozen=True)
class _ShareBuildSnapshot:
    image: str
    tool_id: str
    tool_status: Literal["", "ready"]
    resources: EnvironmentResources
    source_commit_sha: str = ""
    skill_manifest: EnvironmentSkillManifest = field(
        default_factory=EnvironmentSkillManifest
    )
    skill_files: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class _DecodedEnvironmentShareCode:
    environment: EnvironmentInput
    build: _ShareBuildSnapshot | None = None


class EnvironmentService:
    def __init__(
        self,
        repository: TosEnvironmentRepository | None,
        cloud: EnvironmentCloudGateway | None,
        *,
        workspace_references: WorkspaceReferenceLookup | None = None,
        tool_provisioner: EnvironmentToolProvisioner | None = None,
        git_inspector: GitRepositoryInspector | None = None,
        unavailable_reason: str = "管理员未配置环境持久化存储。",
    ) -> None:
        self._repository = repository
        self._cloud = cloud
        self._workspace_references = workspace_references
        self._tool_provisioner = tool_provisioner
        self._git_inspector = git_inspector or PublicGitRepositoryInspector()
        self._unavailable_reason = unavailable_reason
        self._skillspace_resolver: SkillSpaceResolver | None = None
        self._tool_tasks: dict[tuple[str, str, str], asyncio.Task[None]] = {}

    def set_skillspace_resolver(self, resolver: SkillSpaceResolver) -> None:
        self._skillspace_resolver = resolver

    async def list(self, owner_id: str) -> list[EnvironmentView]:
        repository = self._require_repository()
        records = await repository.list(owner_id)
        return [await self._view(repository, owner_id, record) for record in records]

    async def get(self, owner_id: str, environment_id: str) -> EnvironmentView:
        repository = self._require_repository()
        record = await repository.get(owner_id, environment_id)
        return await self._view(repository, owner_id, record)

    async def inspect_repository(
        self, repository_url: str, ref: str = ""
    ) -> RepositoryInspection:
        return await asyncio.to_thread(self._git_inspector.inspect, repository_url, ref)

    async def export_share_code(
        self, owner_id: str, environment_id: str
    ) -> EnvironmentShareCodeExport:
        repository = self._require_repository()
        record = await repository.get(owner_id, environment_id)
        shareable = await self._shareable_environment_input(
            repository, owner_id, record
        )
        build = await self._shareable_available_build(repository, owner_id, record)
        return EnvironmentShareCodeExport(
            shareCode=_encode_environment_share_code(shareable, build),
            name=record.name,
        )

    async def inspect_share_codes(
        self, share_codes: list[str]
    ) -> EnvironmentShareCodeInspectionResponse:
        _validate_share_code_batch(share_codes)
        items: list[EnvironmentShareCodeInspection] = []
        for index, code in enumerate(share_codes):
            try:
                decoded = _decode_environment_share_code(code)
                items.append(
                    EnvironmentShareCodeInspection(
                        index=index,
                        valid=True,
                        name=decoded.environment.name,
                    )
                )
            except EnvironmentShareCodeError as error:
                items.append(
                    EnvironmentShareCodeInspection(
                        index=index,
                        valid=False,
                        error=str(error),
                    )
                )
        return EnvironmentShareCodeInspectionResponse(items=items)

    async def import_share_codes(
        self, owner_id: str, share_codes: list[str]
    ) -> EnvironmentShareCodeImportResponse:
        _validate_share_code_batch(share_codes)
        items: list[EnvironmentShareCodeImportItem] = []
        imported: dict[str, EnvironmentView] = {}
        created_count = 0
        duplicate_count = 0
        failed_count = 0
        for index, code in enumerate(share_codes):
            try:
                decoded = _decode_environment_share_code(code)
                if decoded.build is not None:
                    current_provider = self._require_cloud().describe().provider
                    if decoded.build.resources.provider != current_provider:
                        raise EnvironmentShareCodeError(
                            "分享环境的云厂商与当前 Studio 不一致，"
                            "无法复用镜像和 Sandbox Tool。"
                        )
                canonical_code = _encode_environment_share_code(
                    decoded.environment, decoded.build
                )
                fingerprint = hashlib.sha256(canonical_code.encode("ascii")).hexdigest()
                existing = imported.get(fingerprint)
                if existing is not None:
                    duplicate_count += 1
                    items.append(
                        EnvironmentShareCodeImportItem(
                            index=index,
                            status="duplicate",
                            name=existing.name,
                            environment=existing,
                        )
                    )
                    continue
                environment = await self.create(owner_id, decoded.environment)
                if decoded.build is not None:
                    existing_version_id = ""
                    if environment.latest_version is not None:
                        if environment.latest_version.image != decoded.build.image:
                            raise EnvironmentShareCodeError(
                                "分享环境的镜像与当前 CR 解析结果不一致，无法复用。"
                            )
                        existing_version_id = environment.latest_version.version_id
                    environment = await self._import_available_build(
                        owner_id,
                        environment.id,
                        decoded.build,
                        version_id=existing_version_id,
                    )
                imported[fingerprint] = environment
                created_count += 1
                items.append(
                    EnvironmentShareCodeImportItem(
                        index=index,
                        status="created",
                        name=environment.name,
                        environment=environment,
                    )
                )
            except Exception as error:  # noqa: BLE001 - batch items fail independently
                failed_count += 1
                items.append(
                    EnvironmentShareCodeImportItem(
                        index=index,
                        status="failed",
                        error=_share_code_import_error(error),
                    )
                )
        return EnvironmentShareCodeImportResponse(
            items=items,
            createdCount=created_count,
            duplicateCount=duplicate_count,
            failedCount=failed_count,
        )

    async def create(self, owner_id: str, body: EnvironmentInput) -> EnvironmentView:
        now = _now()
        external_binding: tuple[EnvironmentResources, str] | None = None
        if body.image_source is not None:
            cloud = self._require_cloud()
            external_binding = await asyncio.to_thread(
                cloud.resolve_image_source, body.image_source
            )
            body = body.model_copy(update={"dockerfile": ""})
        elif body.git_source is not None:
            body = body.model_copy(update={"dockerfile": ""})
        else:
            body = body.model_copy(update={"dockerfile": build_dockerfile(body)})
        environment_id = uuid4().hex
        selected_skills = await self._persist_local_skill_assets(
            owner_id, environment_id, body.selected_skills
        )
        record = EnvironmentRecord(
            **body.model_dump(exclude={"selected_skills"}),
            selectedSkills=selected_skills,
            id=environment_id,
            ownerId=owner_id,
            createdAt=now,
            updatedAt=now,
        )
        created = await self._require_repository().create(record)
        if external_binding is not None:
            resources, image = external_binding
            version_id = _version_id()
            build = EnvironmentBuild(
                environmentId=environment_id,
                versionId=version_id,
                status="available",
                image=image,
                resources=resources,
                currentStep="已有镜像已绑定",
                steps=[],
                createdAt=now,
                updatedAt=now,
            )
            created = await self._require_repository().create_external_version(
                created, build
            )
            return self._view_from_record(created, build)
        return self._view_from_record(created)

    async def update(
        self,
        owner_id: str,
        environment_id: str,
        patch: EnvironmentPatch,
    ) -> EnvironmentView:
        repository = self._require_repository()
        current = await repository.get(owner_id, environment_id)
        values = current.model_dump()
        changed = patch.model_dump(exclude_unset=True)
        values.update(changed)
        values["updated_at"] = _now()
        values["id"] = current.id
        values["owner_id"] = current.owner_id
        values["created_at"] = current.created_at
        values["latest_version_id"] = current.latest_version_id
        if "selected_skills" in changed:
            values["selected_skills"] = await self._persist_local_skill_assets(
                owner_id,
                environment_id,
                patch.selected_skills or [],
                current=current.selected_skills,
            )
        if {
            "base_environment",
            "operating_system",
            "language",
            "option_ids",
        } & changed.keys() and "dockerfile" not in changed:
            values["dockerfile"] = ""
        merged_input = EnvironmentInput.model_validate(
            {
                key: values[key]
                for key in (
                    "name",
                    "description",
                    "base_environment",
                    "operating_system",
                    "language",
                    "execution_runtime",
                    "option_ids",
                    "selected_skills",
                    "dockerfile",
                    "git_source",
                    "image_source",
                    "container_repository",
                )
            }
        )
        values["dockerfile"] = (
            ""
            if merged_input.git_source is not None
            or merged_input.image_source is not None
            else build_dockerfile(merged_input)
        )
        external_binding: tuple[EnvironmentResources, str] | None = None
        if (
            merged_input.image_source is not None
            and merged_input.image_source != current.image_source
        ):
            cloud = self._require_cloud()
            external_binding = await asyncio.to_thread(
                cloud.resolve_image_source, merged_input.image_source
            )
        updated = EnvironmentRecord.model_validate(values)
        saved = await repository.update(updated)
        if external_binding is not None:
            resources, image = external_binding
            now = _now()
            build = EnvironmentBuild(
                environmentId=environment_id,
                versionId=_version_id(),
                status="available",
                image=image,
                resources=resources,
                currentStep="已有镜像已绑定",
                steps=[],
                createdAt=now,
                updatedAt=now,
            )
            saved = await repository.create_external_version(saved, build)
            return self._view_from_record(saved, build)
        return await self._view(repository, owner_id, saved)

    async def delete(self, owner_id: str, environment_id: str) -> None:
        if self._workspace_references is not None:
            workspace_names = (
                await self._workspace_references.workspace_names_for_environment(
                    owner_id, environment_id
                )
            )
            if workspace_names:
                names = "、".join(workspace_names[:3])
                suffix = "等工作区" if len(workspace_names) > 3 else "工作区"
                raise EnvironmentConflict(
                    f"该环境正在被 {names}{suffix} 使用，请先从工作区中移除。"
                )
        await self._require_repository().delete(owner_id, environment_id)

    async def start_build(self, owner_id: str, environment_id: str) -> EnvironmentBuild:
        repository = self._require_repository()
        cloud = self._require_cloud()
        environment = await repository.get(owner_id, environment_id)
        if environment.image_source is not None:
            raise ValueError("已有镜像环境不需要触发 CodePipeline 构建。")
        version_id = _version_id()
        now = _now()
        build = EnvironmentBuild(
            environmentId=environment_id,
            versionId=version_id,
            status="preparing",
            currentStep="准备构建资源",
            steps=_default_steps("preparing"),
            createdAt=now,
            updatedAt=now,
        )
        skill_files, skill_manifest = await self._materialize_environment_skills(
            repository, owner_id, environment
        )
        dockerfile_path = "Dockerfile"
        source_commit_sha = ""
        if environment.git_source is not None:
            snapshot = await asyncio.to_thread(
                self._git_inspector.snapshot, environment.git_source
            )
            dockerfile_path = environment.git_source.dockerfile_path
            source_commit_sha = snapshot.inspection.commit_sha
            selected = next(
                (file for file in snapshot.files if file.path == dockerfile_path),
                None,
            )
            if selected is None:
                raise ValueError(
                    "所选 Dockerfile 已不在当前仓库提交中，请重新探查并选择。"
                )
            try:
                source_dockerfile = selected.content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("所选 Dockerfile 必须是 UTF-8 文本。") from error
            version_dockerfile = _dockerfile_with_skill_layer(
                source_dockerfile, bool(skill_files)
            )
            context = _build_repository_context(
                snapshot.files,
                dockerfile_path,
                version_dockerfile,
                skill_files,
                skill_manifest,
            )
        else:
            version_dockerfile = _dockerfile_with_skill_layer(
                environment.dockerfile, bool(skill_files)
            )
            context = _build_context(version_dockerfile, skill_files, skill_manifest)
        build = build.model_copy(update={"source_commit_sha": source_commit_sha})
        environment = await repository.create_version(
            environment,
            build,
            version_dockerfile,
            context,
            skill_manifest,
            [
                (file.path.removeprefix("skills/"), file.content.encode("utf-8"))
                for file in skill_files
            ],
        )
        try:
            resources, run_id, image = await _to_thread_start(
                cloud,
                context_key=repository.context_key(
                    owner_id, environment_id, version_id
                ),
                image_tag=version_id.lower(),
                dockerfile_path=dockerfile_path,
                container_repository=environment.container_repository,
            )
            build = build.model_copy(
                update={
                    "status": "building",
                    "resources": resources,
                    "run_id": run_id,
                    "image": image,
                    "current_step": "等待 CodePipeline 分配构建资源",
                    "steps": _default_steps("queued"),
                    "updated_at": _now(),
                }
            )
        except Exception as error:  # noqa: BLE001 - persist asynchronous build failures
            build = build.model_copy(
                update={
                    "status": "failed",
                    "error": str(error).strip() or type(error).__name__,
                    "updated_at": _now(),
                }
            )
        return await repository.update_build(owner_id, build)

    async def get_build(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str,
        *,
        include_logs: bool = False,
    ) -> EnvironmentBuild:
        repository = self._require_repository()
        build = await repository.get_build(owner_id, environment_id, version_id)
        if build.status == "preparing":
            return build
        if build.status == "available" and (
            not build.tool_id or build.tool_status != "ready"
        ):
            build = await self._begin_aio_tool_provisioning(
                repository,
                owner_id,
                build,
            )
        if build.status == "building" and build.tool_status == "creating":
            self._schedule_tool_provisioning(repository, owner_id, build)
            return build
        active = build.status in {"queued", "building", "scanning"}
        if not active:
            if not include_logs:
                return build
            persisted_log = await repository.get_build_log(
                owner_id, environment_id, version_id
            )
            if persisted_log:
                return _with_log_snapshot(build, persisted_log)
            # A failure while resolving CP/CR resources happens before a
            # pipeline run exists. Preserve that actionable startup error when
            # the detail view asks for logs instead of replacing it with a
            # secondary "missing run information" message.
            if (
                not isinstance(build.resources, EnvironmentResources)
                or not build.run_id
            ):
                return build

        if not isinstance(build.resources, EnvironmentResources) or not build.run_id:
            failed = build.model_copy(
                update={
                    "status": "failed",
                    "error": "构建记录缺少 CodePipeline 运行信息，无法继续查询。",
                    "updated_at": _now(),
                }
            )
            return await repository.update_build(owner_id, failed)

        cloud = self._require_cloud()
        try:
            status = (
                await _to_thread_status(cloud, build.resources, build.run_id)
                if active
                else build.status
            )
            progress_error = ""
            steps = build.steps
            try:
                steps = await _to_thread_steps(cloud, build.resources, build.run_id)
            except Exception as error:  # noqa: BLE001 - status remains authoritative
                progress_error = str(error).strip() or type(error).__name__
            if not steps:
                steps = _default_steps(status)
            updated = build.model_copy(
                update={
                    "status": status,
                    "steps": steps,
                    "current_step": _current_step(status, steps),
                    "progress_error": progress_error,
                    "updated_at": _now(),
                }
            )
            log = None
            if status == "failed":
                updated = updated.model_copy(
                    update={"error": "环境镜像构建失败，请检查 CodePipeline 构建日志。"}
                )
            if include_logs or status in {"available", "failed"}:
                log = await _to_thread_log(cloud, build.resources, build.run_id)
                updated = _with_log_snapshot(updated, log)
            if status == "available":
                updated = await self._begin_aio_tool_provisioning(
                    repository,
                    owner_id,
                    updated,
                )
            return await repository.update_build(owner_id, updated, log=log)
        except Exception as error:  # noqa: BLE001 - persist status lookup failures
            failed = build.model_copy(
                update={
                    "status": "failed",
                    "error": str(error).strip() or type(error).__name__,
                    "updated_at": _now(),
                }
            )
            return await repository.update_build(owner_id, failed)

    async def get_manifest(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str,
    ) -> EnvironmentManifest:
        repository = self._require_repository()
        environment = await repository.get_version_config(
            owner_id, environment_id, version_id
        )
        build = await repository.get_build(owner_id, environment_id, version_id)
        skills = await repository.get_skill_manifest(
            owner_id, environment_id, version_id
        )
        return EnvironmentManifest(
            apiVersion="agentkit.studio/v3",
            metadata=EnvironmentManifestMetadata(
                id=environment.id,
                name=environment.name,
                version=version_id,
                description=environment.description,
            ),
            spec=EnvironmentManifestSpec(
                image=build.image,
                baseEnvironment=environment.base_environment,
                baseImage=environment_base_image(environment),
                operatingSystem=environment.operating_system,
                language=environment.language,
                executionRuntime=environment.execution_runtime,
                packages=environment.option_ids,
                capabilities=environment_capabilities(environment),
                skills=skills.skills,
            ),
            status=EnvironmentManifestStatus(
                phase=build.status,
                toolId=build.tool_id,
                toolStatus=build.tool_status,
                createdAt=build.created_at,
                updatedAt=build.updated_at,
            ),
        )

    async def ensure_sandbox_tool_ready(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str,
    ) -> EnvironmentBuild:
        """Validate or repair the Tool for an already-built Sandbox image."""

        repository = self._require_repository()
        environment = await repository.get_version_config(
            owner_id, environment_id, version_id
        )
        if environment.base_environment not in {"aio-sandbox", "codex-sandbox"}:
            raise ValueError("所选环境不支持 Sandbox 命令执行。")
        build = await repository.get_build(owner_id, environment_id, version_id)
        if build.status != "available" or not build.image.strip():
            raise ValueError("所选环境版本尚未构建完成。")
        if self._tool_provisioner is None:
            raise RuntimeError("AgentKit Sandbox Tool 服务未配置。")
        resources = build.resources
        if not isinstance(resources, EnvironmentResources):
            raise TypeError("环境构建记录缺少云资源信息。")

        tool = await self._tool_provisioner.ensure_ready(
            image=build.image,
            provider=resources.provider,
            region=resources.region,
            existing_tool_id=build.tool_id,
        )
        if build.tool_id == tool.tool_id and build.tool_status == tool.status:
            return build
        current = await repository.get_build(owner_id, environment_id, version_id)
        repaired = current.model_copy(
            update={
                "status": "available",
                "tool_id": tool.tool_id,
                "tool_status": tool.status,
                "error": "",
                "progress_error": "",
                "current_step": "环境与 Sandbox Tool 已就绪",
                "steps": _with_tool_step(current.steps, "succeeded"),
                "updated_at": _now(),
            }
        )
        return await repository.update_build(owner_id, repaired)

    def resource_info(self) -> EnvironmentResourceInfo:
        return self._require_cloud().describe()

    async def resolve_for_agent(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str = "",
    ) -> ResolvedEnvironment:
        repository = self._require_repository()
        record = await repository.get(owner_id, environment_id)
        resolved_version = version_id.strip() or (record.latest_version_id or "")
        if not resolved_version:
            raise ValueError("所选环境尚未构建。")
        build = await repository.get_build(owner_id, environment_id, resolved_version)
        if build.status == "building" and build.tool_status == "creating":
            self._schedule_tool_provisioning(repository, owner_id, build)
        if build.status != "available" or not build.image.strip():
            raise ValueError("所选环境版本尚未构建完成。")
        version_config = await repository.get_version_config(
            owner_id,
            environment_id,
            resolved_version,
        )
        if version_config.base_environment in {"aio-sandbox", "codex-sandbox"} and (
            not build.tool_id or build.tool_status != "ready"
        ):
            build = await self._begin_aio_tool_provisioning(repository, owner_id, build)
            raise ValueError("环境 Sandbox Tool 正在准备，请稍后重试。")
        manifest = await repository.get_skill_manifest(
            owner_id, environment_id, resolved_version
        )
        return ResolvedEnvironment(
            environmentId=environment_id,
            environmentVersionId=resolved_version,
            image=build.image,
            toolId=build.tool_id,
            toolStatus=build.tool_status,
            skills=manifest.skills,
            resources=build.resources,
        )

    async def _begin_aio_tool_provisioning(
        self,
        repository: TosEnvironmentRepository,
        owner_id: str,
        build: EnvironmentBuild,
    ) -> EnvironmentBuild:
        environment = await repository.get_version_config(
            owner_id,
            build.environment_id,
            build.version_id,
        )
        if environment.base_environment not in {"aio-sandbox", "codex-sandbox"}:
            return build
        if build.tool_id and build.tool_status == "ready":
            return build
        steps = _with_tool_step(build.steps, "running")
        creating = build.model_copy(
            update={
                "status": "building",
                "tool_status": "creating",
                "current_step": "创建 AgentKit Sandbox Tool",
                "steps": steps,
                "updated_at": _now(),
            }
        )
        creating = await repository.update_build(owner_id, creating)
        self._schedule_tool_provisioning(repository, owner_id, creating)
        return creating

    def _schedule_tool_provisioning(
        self,
        repository: TosEnvironmentRepository,
        owner_id: str,
        build: EnvironmentBuild,
    ) -> None:
        key = (owner_id, build.environment_id, build.version_id)
        current = self._tool_tasks.get(key)
        if current is not None and not current.done():
            return
        task = asyncio.create_task(
            self._complete_tool_provisioning(repository, owner_id, build)
        )
        self._tool_tasks[key] = task
        task.add_done_callback(
            lambda completed, task_key=key: self._tool_task_done(task_key, completed)
        )

    def _tool_task_done(
        self,
        key: tuple[str, str, str],
        task: asyncio.Task[None],
    ) -> None:
        if self._tool_tasks.get(key) is task:
            self._tool_tasks.pop(key, None)
        if not task.cancelled():
            task.exception()

    async def _complete_tool_provisioning(
        self,
        repository: TosEnvironmentRepository,
        owner_id: str,
        build: EnvironmentBuild,
    ) -> None:
        try:
            if self._tool_provisioner is None:
                raise RuntimeError("AgentKit Sandbox Tool 服务未配置。")
            resources = build.resources
            if not isinstance(resources, EnvironmentResources):
                raise TypeError("环境构建记录缺少云资源信息。")
            tool = await self._tool_provisioner.ensure_ready(
                image=build.image,
                provider=resources.provider,
                region=resources.region,
                existing_tool_id=build.tool_id,
                on_created=lambda state: self._persist_creating_tool(
                    repository,
                    owner_id,
                    build,
                    state.tool_id,
                ),
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError as error:
            current = await repository.get_build(
                owner_id, build.environment_id, build.version_id
            )
            if current.tool_id and current.tool_status == "ready":
                return
            waiting = current.model_copy(
                update={
                    "status": "building",
                    "tool_status": "creating",
                    "progress_error": str(error).strip() or type(error).__name__,
                    "current_step": "AgentKit Sandbox Tool 仍在准备",
                    "steps": _with_tool_step(current.steps, "running"),
                    "updated_at": _now(),
                }
            )
            await repository.update_build(owner_id, waiting)
            return
        except Exception as error:  # noqa: BLE001 - persist provisioning failure
            current = await repository.get_build(
                owner_id, build.environment_id, build.version_id
            )
            if current.tool_id and current.tool_status == "ready":
                return
            failed = current.model_copy(
                update={
                    "status": "failed",
                    "tool_status": "failed",
                    "error": str(error).strip() or type(error).__name__,
                    "current_step": "创建 AgentKit Sandbox Tool 失败",
                    "steps": _with_tool_step(current.steps, "failed"),
                    "updated_at": _now(),
                }
            )
            await repository.update_build(owner_id, failed)
            return
        current = await repository.get_build(
            owner_id, build.environment_id, build.version_id
        )
        if current.tool_id and current.tool_status == "ready":
            return
        ready = current.model_copy(
            update={
                "status": "available",
                "tool_id": tool.tool_id,
                "tool_status": tool.status,
                "error": "",
                "progress_error": "",
                "current_step": "环境与 Sandbox Tool 已就绪",
                "steps": _with_tool_step(current.steps, "succeeded"),
                "updated_at": _now(),
            }
        )
        await repository.update_build(owner_id, ready)

    async def _persist_creating_tool(
        self,
        repository: TosEnvironmentRepository,
        owner_id: str,
        build: EnvironmentBuild,
        tool_id: str,
    ) -> None:
        current = await repository.get_build(
            owner_id, build.environment_id, build.version_id
        )
        if current.tool_id and current.tool_status == "ready":
            return
        if current.tool_id and current.tool_id != tool_id:
            raise RuntimeError("环境构建记录关联了不同的 Sandbox Tool。")
        if (
            current.tool_id == tool_id
            and current.tool_status == "creating"
            and not current.error
            and not current.progress_error
        ):
            return
        creating = current.model_copy(
            update={
                "status": "building",
                "tool_id": tool_id,
                "tool_status": "creating",
                "error": "",
                "progress_error": "",
                "updated_at": _now(),
            }
        )
        await repository.update_build(owner_id, creating)

    async def get_skill_files_for_agent(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str,
    ) -> list[GeneratedFile]:
        resolved = await self.resolve_for_agent(owner_id, environment_id, version_id)
        files = await self._require_repository().get_version_skill_files(
            owner_id, environment_id, resolved.version_id
        )
        result: list[GeneratedFile] = []
        for path, content in files:
            parts = PurePosixPath(path).parts
            if not parts or any(part in {"", ".", ".."} for part in parts):
                raise ValueError(f"环境技能快照路径无效：{path}")
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError(f"环境技能快照不是 UTF-8 文本：{path}") from error
            result.append(GeneratedFile(path="/".join(parts), content=text))
        return result

    async def stage_skill_files_for_agent(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str,
        target: Path,
    ) -> Path:
        import asyncio

        files = await self.get_skill_files_for_agent(
            owner_id, environment_id, version_id
        )
        return await asyncio.to_thread(_stage_skill_files, files, target)

    async def _persist_local_skill_assets(
        self,
        owner_id: str,
        environment_id: str,
        selections: list[EnvironmentSkillSelection],
        *,
        current: list[EnvironmentSkillSelection] | None = None,
    ) -> list[EnvironmentSkillSelection]:
        repository = self._require_repository()
        current_by_artifact = {
            item.artifact_id: item
            for item in (current or [])
            if item.source == "local" and item.artifact_id
        }
        current_by_identity = {
            (item.folder.casefold(), item.name.casefold()): item
            for item in (current or [])
            if item.source == "local" and item.artifact_id
        }
        persisted: list[EnvironmentSkillSelection] = []
        for selection in selections:
            item = selection.model_copy(deep=True)
            if item.source != "local":
                item.local_files = []
                persisted.append(item)
                continue
            if item.local_files:
                payload = json.dumps(
                    [file.model_dump() for file in item.local_files],
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                if len(payload) > 2 * 1024 * 1024:
                    raise ValueError("本地技能文件总大小不能超过 2 MiB。")
                artifact_id = hashlib.sha256(payload).hexdigest()
                await repository.put_skill_asset(
                    owner_id, environment_id, artifact_id, payload
                )
                item.artifact_id = artifact_id
                item.local_files = []
            elif item.artifact_id not in current_by_artifact:
                previous = current_by_identity.get(
                    (item.folder.casefold(), item.name.casefold())
                )
                if previous is None:
                    raise ValueError("本地技能资产不存在，请重新上传。")
                item.artifact_id = previous.artifact_id
            persisted.append(item)
        return persisted

    async def _shareable_environment_input(
        self,
        repository: TosEnvironmentRepository,
        owner_id: str,
        environment: EnvironmentRecord,
    ) -> EnvironmentInput:
        _validate_shareable_git_source(environment)
        selections: list[EnvironmentSkillSelection] = []
        for selection in environment.selected_skills:
            item = selection.model_copy(deep=True)
            item.artifact_id = ""
            if item.source == "local":
                raw = await repository.get_skill_asset(
                    owner_id, environment.id, selection.artifact_id
                )
                try:
                    values = json.loads(raw)
                    item.local_files = [
                        EnvironmentSkillFile.model_validate(value) for value in values
                    ]
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    raise ValueError("本地技能资产无效，无法导出分享码。") from error
            else:
                item.local_files = []
            selections.append(item)
        return EnvironmentInput(
            name=environment.name,
            description=environment.description,
            baseEnvironment=environment.base_environment,
            operatingSystem=environment.operating_system,
            language=environment.language,
            executionRuntime=environment.execution_runtime,
            optionIds=environment.option_ids,
            selectedSkills=selections,
            dockerfile=environment.dockerfile,
            gitSource=environment.git_source,
            imageSource=environment.image_source,
            containerRepository=environment.container_repository,
        )

    async def _shareable_available_build(
        self,
        repository: TosEnvironmentRepository,
        owner_id: str,
        environment: EnvironmentRecord,
    ) -> _ShareBuildSnapshot | None:
        if not environment.latest_version_id:
            return None
        build = await repository.get_build(
            owner_id,
            environment.id,
            environment.latest_version_id,
        )
        if (
            build.status != "available"
            or not build.image.strip()
            or not isinstance(build.resources, EnvironmentResources)
        ):
            return None
        registry = build.resources.container_registry
        try:
            ContainerRepository(
                region=registry.region or build.resources.region,
                registry=registry.registry,
                namespace=registry.namespace,
                repository=registry.repository,
            )
        except ValueError:
            return None
        return _ShareBuildSnapshot(
            image=build.image,
            tool_id=build.tool_id if build.tool_status == "ready" else "",
            tool_status=build.tool_status if build.tool_status == "ready" else "",
            resources=build.resources.model_copy(deep=True),
            source_commit_sha=build.source_commit_sha,
            skill_manifest=await repository.get_skill_manifest(
                owner_id,
                environment.id,
                environment.latest_version_id,
            ),
            skill_files=tuple(
                (path, _decode_share_skill_file(path, content))
                for path, content in await repository.get_version_skill_files(
                    owner_id,
                    environment.id,
                    environment.latest_version_id,
                )
            ),
        )

    async def _import_available_build(
        self,
        owner_id: str,
        environment_id: str,
        snapshot: _ShareBuildSnapshot,
        *,
        version_id: str = "",
    ) -> EnvironmentView:
        repository = self._require_repository()
        record = await repository.get(owner_id, environment_id)
        now = _now()
        build = EnvironmentBuild(
            environmentId=environment_id,
            versionId=version_id or _version_id(),
            status="available",
            image=snapshot.image,
            toolId=snapshot.tool_id,
            toolStatus=snapshot.tool_status,
            resources=snapshot.resources.model_copy(deep=True),
            currentStep="已从分享码导入可用镜像",
            steps=[],
            sourceCommitSha=snapshot.source_commit_sha,
            createdAt=now,
            updatedAt=now,
        )
        saved = await repository.create_external_version(
            record,
            build,
            snapshot.skill_manifest,
            [(path, content.encode("utf-8")) for path, content in snapshot.skill_files],
        )
        return self._view_from_record(saved, build)

    async def _materialize_environment_skills(
        self,
        repository: TosEnvironmentRepository,
        owner_id: str,
        environment: EnvironmentRecord,
    ) -> tuple[list[GeneratedFile], EnvironmentSkillManifest]:
        selected: list[SelectedSkill] = []
        for item in environment.selected_skills:
            payload = item.model_dump(by_alias=True)
            if item.source == "local":
                raw = await repository.get_skill_asset(
                    owner_id, environment.id, item.artifact_id
                )
                files = [
                    EnvironmentSkillFile.model_validate(value)
                    for value in json.loads(raw)
                ]
                payload["localFiles"] = [file.model_dump() for file in files]
            payload.pop("artifactId", None)
            skill = SelectedSkill.model_validate(payload)
            selected.append(skill)
        if not selected:
            return [], EnvironmentSkillManifest()
        project = GeneratedProject(name="environment", files=[])
        await materialize_selected_skills(
            AgentDraft(name="environment", selectedSkills=selected),
            project,
            resolve_skillspace_detail=self._skillspace_resolver,
        )
        source_by_folder = {
            skill.folder: source
            for skill, source in zip(selected, environment.selected_skills, strict=True)
        }
        folders: dict[str, list[GeneratedFile]] = {}
        for file in project.files:
            parts = PurePosixPath(file.path).parts
            if len(parts) < 3 or parts[0] != "skills":
                raise ValueError(f"环境技能文件路径无效：{file.path}")
            folders.setdefault(parts[1], []).append(file)
        seen_folders: set[str] = set()
        seen_names: set[str] = set()
        entries: list[EnvironmentSkillManifestEntry] = []
        for folder, files in sorted(folders.items()):
            folder_key = folder.casefold()
            skill_md = next(
                (
                    file.content
                    for file in files
                    if PurePosixPath(file.path).name.casefold() == "skill.md"
                ),
                "",
            )
            name = skill_name_from_markdown(skill_md) or folder
            name_key = name.casefold()
            if folder_key in seen_folders or name_key in seen_names:
                raise ValueError(f"环境技能名称冲突：{folder}")
            seen_folders.add(folder_key)
            seen_names.add(name_key)
            source = source_by_folder.get(folder) or environment.selected_skills[0]
            digest = hashlib.sha256(
                b"".join(
                    file.path.encode("utf-8") + b"\0" + file.content.encode("utf-8")
                    for file in sorted(files, key=lambda value: value.path)
                )
            ).hexdigest()
            entries.append(
                EnvironmentSkillManifestEntry(
                    name=name,
                    folder=folder,
                    source=source.source,
                    version=source.version,
                    digest=digest,
                )
            )
        return project.files, EnvironmentSkillManifest(skills=entries)

    async def _view(
        self,
        repository: TosEnvironmentRepository,
        owner_id: str,
        record: EnvironmentRecord,
    ) -> EnvironmentView:
        latest = None
        if record.latest_version_id:
            latest = await repository.get_build(
                owner_id,
                record.id,
                record.latest_version_id,
            )
            if latest.status in {"queued", "building", "scanning"} or (
                latest.status == "available"
                and (not latest.tool_id or latest.tool_status != "ready")
            ):
                latest = await self.get_build(
                    owner_id,
                    record.id,
                    record.latest_version_id,
                )
        return self._view_from_record(record, latest)

    @staticmethod
    def _view_from_record(
        record: EnvironmentRecord,
        latest: EnvironmentBuild | None = None,
    ) -> EnvironmentView:
        return EnvironmentView(
            id=record.id,
            name=record.name,
            description=record.description,
            baseEnvironment=record.base_environment,
            operatingSystem=record.operating_system,
            language=record.language,
            executionRuntime=record.execution_runtime,
            optionIds=record.option_ids,
            selectedSkills=record.selected_skills,
            dockerfile=record.dockerfile,
            gitSource=record.git_source,
            imageSource=record.image_source,
            containerRepository=record.container_repository,
            createdAt=record.created_at,
            updatedAt=record.updated_at,
            latestVersion=latest,
        )

    def _require_repository(self) -> TosEnvironmentRepository:
        if self._repository is None:
            raise EnvironmentStorageUnavailable(self._unavailable_reason)
        return self._repository

    def _require_cloud(self) -> EnvironmentCloudGateway:
        if self._cloud is None:
            raise EnvironmentStorageUnavailable(
                "管理员未配置环境镜像构建所需的云资源或凭据。"
            )
        return self._cloud


async def _to_thread_start(
    cloud: EnvironmentCloudGateway,
    *,
    context_key: str,
    image_tag: str,
    dockerfile_path: str,
    container_repository: ContainerRepository | None,
):
    if container_repository is not None:
        return await asyncio.to_thread(
            cloud.start_build,
            context_key=context_key,
            image_tag=image_tag,
            dockerfile_path=dockerfile_path,
            container_repository=container_repository,
        )
    if dockerfile_path != "Dockerfile":
        return await asyncio.to_thread(
            cloud.start_build,
            context_key=context_key,
            image_tag=image_tag,
            dockerfile_path=dockerfile_path,
        )
    return await asyncio.to_thread(
        cloud.start_build,
        context_key=context_key,
        image_tag=image_tag,
    )


async def _to_thread_status(cloud, resources, run_id):
    import asyncio

    return await asyncio.to_thread(cloud.build_status, resources, run_id)


async def _to_thread_steps(cloud, resources, run_id):
    import asyncio

    return await asyncio.to_thread(cloud.build_steps, resources, run_id)


async def _to_thread_log(cloud, resources, run_id):
    import asyncio

    return await asyncio.to_thread(cloud.build_log, resources, run_id)


def _default_steps(status: EnvironmentBuildStatus) -> list[EnvironmentBuildStep]:
    terminal_status = (
        "succeeded"
        if status == "available"
        else "failed"
        if status == "failed"
        else "pending"
    )
    labels = (
        ("download", "下载构建上下文"),
        ("extract", "解压构建上下文"),
        ("build", "构建并推送镜像"),
    )
    return [
        EnvironmentBuildStep(key=key, label=label, status=terminal_status)
        for key, label in labels
    ]


def _with_tool_step(
    steps: list[EnvironmentBuildStep],
    status: EnvironmentBuildStepStatus,
) -> list[EnvironmentBuildStep]:
    now = _now()
    existing = next((item for item in steps if item.key == "sandbox-tool"), None)
    tool_step = EnvironmentBuildStep(
        key="sandbox-tool",
        label="创建 AgentKit Sandbox Tool",
        status=status,
        startedAt=(existing.started_at if existing is not None else now),
        finishedAt=now if status in {"succeeded", "failed"} else None,
    )
    return [item for item in steps if item.key != "sandbox-tool"] + [tool_step]


def _current_step(
    status: EnvironmentBuildStatus,
    steps: list[EnvironmentBuildStep],
) -> str:
    for step in steps:
        if step.status == "running":
            return step.label
    for step in steps:
        if step.status == "failed":
            return f"{step.label}失败"
    for step in steps:
        if step.status == "pending":
            return (
                step.label if status != "queued" else "等待 CodePipeline 分配构建资源"
            )
    if status == "available":
        return "镜像已构建并推送"
    if status == "failed":
        return "镜像构建失败"
    return "正在同步构建状态"


def _with_log_snapshot(build: EnvironmentBuild, log: str) -> EnvironmentBuild:
    limit = 64 * 1024
    truncated = len(log) > limit
    return build.model_copy(
        update={
            "log_tail": log[-limit:],
            "log_truncated": truncated,
            "log_updated_at": _now(),
            "log_error": log if log.startswith("无法读取构建日志：") else "",
        }
    )


def _dockerfile_with_skill_layer(dockerfile: str, has_skills: bool) -> str:
    if not has_skills:
        return dockerfile
    return (
        dockerfile.rstrip()
        + "\n\n# Studio managed environment skills\n"
        + "COPY --chmod=0555 .studio/environment-skills/ "
        + "/opt/veadk/environment/skills/\n"
        + "COPY --chmod=0444 .studio/environment-skills-manifest.json "
        + "/opt/veadk/environment/skills-manifest.json\n"
        + 'ENV VEADK_ENVIRONMENT_SKILLS_DIR="/opt/veadk/environment/skills"\n'
    )


def _build_context(
    dockerfile: str,
    skill_files: list[GeneratedFile] | None = None,
    skill_manifest: EnvironmentSkillManifest | None = None,
) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        _add_tar_file(archive, "Dockerfile", dockerfile.encode("utf-8"))
        _add_tar_file(archive, ".dockerignore", b".git\n.env\n")
        if skill_files:
            manifest = skill_manifest or EnvironmentSkillManifest()
            _add_tar_file(
                archive,
                ".studio/environment-skills-manifest.json",
                manifest.model_dump_json(by_alias=True).encode("utf-8"),
            )
            for file in skill_files:
                relative = file.path.removeprefix("skills/")
                _add_tar_file(
                    archive,
                    f".studio/environment-skills/{relative}",
                    file.content.encode("utf-8"),
                )
    return output.getvalue()


def _build_repository_context(
    repository_files: tuple[RepositoryFile, ...],
    dockerfile_path: str,
    dockerfile: str,
    skill_files: list[GeneratedFile] | None = None,
    skill_manifest: EnvironmentSkillManifest | None = None,
) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for file in repository_files:
            if file.path == dockerfile_path:
                content = dockerfile.encode("utf-8")
            elif file.path == ".dockerignore" and skill_files:
                content = (
                    file.content.rstrip()
                    + b"\n!.studio/\n!.studio/environment-skills/\n"
                    + b"!.studio/environment-skills/**\n"
                    + b"!.studio/environment-skills-manifest.json\n"
                )
            else:
                content = file.content
            _add_tar_file(archive, file.path, content, mode=file.mode)
        if skill_files:
            if not any(file.path == ".dockerignore" for file in repository_files):
                _add_tar_file(
                    archive,
                    ".dockerignore",
                    b".git\n.env\n!.studio/\n!.studio/**\n",
                )
            manifest = skill_manifest or EnvironmentSkillManifest()
            _add_tar_file(
                archive,
                ".studio/environment-skills-manifest.json",
                manifest.model_dump_json(by_alias=True).encode("utf-8"),
            )
            for file in skill_files:
                relative = file.path.removeprefix("skills/")
                _add_tar_file(
                    archive,
                    f".studio/environment-skills/{relative}",
                    file.content.encode("utf-8"),
                )
    return output.getvalue()


def _add_tar_file(
    archive: tarfile.TarFile, name: str, content: bytes, *, mode: int = 0o644
) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = mode
    info.mtime = 0
    archive.addfile(info, io.BytesIO(content))


def _stage_skill_files(files: list[GeneratedFile], target: Path) -> Path:
    root = target.resolve()
    root.mkdir(parents=True, exist_ok=True)
    for file in files:
        destination = (root / file.path).resolve()
        if root not in destination.parents:
            raise ValueError(f"环境技能快照路径无效：{file.path}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(file.content, encoding="utf-8")
    return root


def _version_id() -> str:
    now = _now().strftime("%Y%m%dT%H%M%SZ")
    return f"{now}-{uuid4().hex[:8]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


_ENVIRONMENT_SHARE_CODE_PREFIX = "akenv://v1/"
_MAX_ENVIRONMENT_SHARE_CODE_CHARS = 4 * 1024 * 1024
_MAX_ENVIRONMENT_SHARE_BATCH_CHARS = 16 * 1024 * 1024
_MAX_ENVIRONMENT_SHARE_PAYLOAD_BYTES = 4 * 1024 * 1024
_SHARE_ENVIRONMENT_KEYS = frozenset(
    {"n", "d", "o", "l", "r", "p", "s", "f", "g", "i", "c"}
)
_SHARE_ENVIRONMENT_OPTIONAL_KEYS = frozenset({"a", "b"})
_SHARE_SKILL_KEYS = frozenset(
    {"x", "f", "n", "d", "u", "ns", "lf", "si", "sn", "sr", "id", "v"}
)
_SHARE_LOCAL_FILE_KEYS = frozenset({"p", "c"})
_SHARE_GIT_KEYS = frozenset({"u", "r", "f"})
_SHARE_CONTAINER_KEYS = frozenset({"l", "g", "n", "r"})
_SHARE_IMAGE_KEYS = frozenset({"l", "g", "n", "r", "x"})
_SHARE_BUILD_KEYS = frozenset({"i", "t", "u", "e", "s", "m", "f"})
_SHARE_BUILD_LEGACY_KEYS = frozenset({"i", "t", "u", "e", "s"})
_SHARE_MANIFEST_ENTRY_KEYS = frozenset({"n", "f", "s", "v", "d"})
_SHARE_VERSION_SKILL_FILE_KEYS = frozenset({"p", "c"})
_SHARE_RESOURCES_KEYS = frozenset(
    {"provider", "region", "codePipeline", "containerRegistry"}
)
_SHARE_CODE_PIPELINE_KEYS = frozenset(
    {
        "source",
        "workspaceId",
        "workspaceName",
        "pipelineId",
        "pipelineName",
        "consoleUrl",
    }
)
_SHARE_CONTAINER_REGISTRY_KEYS = frozenset(
    {
        "source",
        "region",
        "registry",
        "namespace",
        "repository",
        "domain",
        "imageRepository",
        "consoleUrl",
    }
)
_SHARE_BASE64_RE = re.compile(r"[A-Za-z0-9_-]+")
_SHARE_IMAGE_RE = re.compile(r"[^\s\x00-\x1f\x7f]{1,2048}")
_SHARE_COMMIT_RE = re.compile(r"[0-9a-fA-F]{7,128}")


def _encode_environment_share_code(
    environment: EnvironmentInput,
    build: _ShareBuildSnapshot | None = None,
) -> str:
    payload = _environment_share_payload(environment, build)
    try:
        compact = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, UnicodeEncodeError) as error:
        raise EnvironmentShareCodeError("环境内容无法编码为分享码。") from error
    if len(compact) > _MAX_ENVIRONMENT_SHARE_PAYLOAD_BYTES:
        raise EnvironmentShareCodeError("环境内容过大，无法生成分享码。")
    compressed = zlib.compress(compact, level=9)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    share_code = f"{_ENVIRONMENT_SHARE_CODE_PREFIX}{encoded}"
    if len(share_code) > _MAX_ENVIRONMENT_SHARE_CODE_CHARS:
        raise EnvironmentShareCodeError("环境内容过大，无法生成分享码。")
    return share_code


def _decode_environment_share_code(
    share_code: str,
) -> _DecodedEnvironmentShareCode:
    if len(share_code) > _MAX_ENVIRONMENT_SHARE_CODE_CHARS:
        raise EnvironmentShareCodeError("分享码超过大小限制。")
    if not share_code.startswith(_ENVIRONMENT_SHARE_CODE_PREFIX):
        raise EnvironmentShareCodeError("分享码格式无效。")
    encoded = share_code.removeprefix(_ENVIRONMENT_SHARE_CODE_PREFIX)
    if not encoded or not _SHARE_BASE64_RE.fullmatch(encoded):
        raise EnvironmentShareCodeError("分享码格式无效。")
    try:
        padding = "=" * (-len(encoded) % 4)
        compressed = base64.b64decode(
            (encoded + padding).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
        raw = _decompress_share_payload(compressed)
        payload = json.loads(raw.decode("utf-8"))
        return _environment_from_share_payload(payload)
    except EnvironmentShareCodeError:
        raise
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
    ) as error:
        raise EnvironmentShareCodeError("分享码内容损坏或不完整。") from error
    except (TypeError, ValueError) as error:
        raise EnvironmentShareCodeError("分享码中的环境配置无效。") from error


def _decompress_share_payload(compressed: bytes) -> bytes:
    decompressor = zlib.decompressobj()
    try:
        raw = decompressor.decompress(
            compressed,
            _MAX_ENVIRONMENT_SHARE_PAYLOAD_BYTES + 1,
        )
        if (
            len(raw) > _MAX_ENVIRONMENT_SHARE_PAYLOAD_BYTES
            or decompressor.unconsumed_tail
        ):
            raise EnvironmentShareCodeError("分享码解压后超过大小限制。")
        if not decompressor.eof or decompressor.unused_data:
            raise EnvironmentShareCodeError("分享码内容损坏或不完整。")
        remaining = _MAX_ENVIRONMENT_SHARE_PAYLOAD_BYTES + 1 - len(raw)
        raw += decompressor.flush(remaining)
    except zlib.error as error:
        raise EnvironmentShareCodeError("分享码内容损坏或不完整。") from error
    if len(raw) > _MAX_ENVIRONMENT_SHARE_PAYLOAD_BYTES:
        raise EnvironmentShareCodeError("分享码解压后超过大小限制。")
    return raw


def _validate_share_code_batch(share_codes: list[str]) -> None:
    if not share_codes or len(share_codes) > 20:
        raise ValueError("每批必须提供 1 到 20 个环境分享码。")
    total = sum(len(code) for code in share_codes)
    if total > _MAX_ENVIRONMENT_SHARE_BATCH_CHARS:
        raise ValueError("本批环境分享码总大小超过 16 MiB 限制。")


def _environment_share_payload(
    environment: EnvironmentInput,
    build: _ShareBuildSnapshot | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "n": environment.name,
        "d": environment.description,
        "o": environment.operating_system,
        "l": environment.language,
        "r": environment.execution_runtime,
        "p": list(environment.option_ids),
        "s": [_skill_share_payload(skill) for skill in environment.selected_skills],
        "f": environment.dockerfile,
        "g": _git_share_payload(environment.git_source),
        "i": _image_share_payload(environment.image_source),
        "c": _container_share_payload(environment.container_repository),
    }
    if environment.base_environment != "ubuntu":
        payload["b"] = environment.base_environment
    if build is not None:
        payload["a"] = _build_share_payload(build)
    return payload


def _skill_share_payload(skill: EnvironmentSkillSelection) -> dict[str, Any]:
    return {
        "x": skill.source,
        "f": skill.folder,
        "n": skill.name,
        "d": skill.description,
        "u": skill.slug,
        "ns": skill.namespace,
        "lf": [{"p": file.path, "c": file.content} for file in skill.local_files],
        "si": skill.skill_space_id,
        "sn": skill.skill_space_name,
        "sr": skill.skill_space_region,
        "id": skill.skill_id,
        "v": skill.version,
    }


def _git_share_payload(source: Any) -> dict[str, str] | None:
    if source is None:
        return None
    return {"u": source.repository_url, "r": source.ref, "f": source.dockerfile_path}


def _container_share_payload(source: Any) -> dict[str, str] | None:
    if source is None:
        return None
    return {
        "l": source.region,
        "g": source.registry,
        "n": source.namespace,
        "r": source.repository,
    }


def _image_share_payload(source: Any) -> dict[str, str] | None:
    if source is None:
        return None
    payload = _container_share_payload(source)
    assert payload is not None
    payload["x"] = source.reference
    return payload


def _environment_from_share_payload(value: Any) -> _DecodedEnvironmentShareCode:
    if (
        not isinstance(value, dict)
        or not _SHARE_ENVIRONMENT_KEYS.issubset(value)
        or not set(value).issubset(
            _SHARE_ENVIRONMENT_KEYS | _SHARE_ENVIRONMENT_OPTIONAL_KEYS
        )
    ):
        raise EnvironmentShareCodeError("分享码中的环境字段不完整。")
    payload = value
    skills = payload["s"]
    if not isinstance(skills, list):
        raise EnvironmentShareCodeError("分享码中的技能列表无效。")
    environment = EnvironmentInput.model_validate(
        {
            "name": payload["n"],
            "description": payload["d"],
            "baseEnvironment": payload.get("b", "ubuntu"),
            "operatingSystem": payload["o"],
            "language": payload["l"],
            "executionRuntime": payload["r"],
            "optionIds": payload["p"],
            "selectedSkills": [_skill_from_share_payload(skill) for skill in skills],
            "dockerfile": payload["f"],
            "gitSource": _git_from_share_payload(payload["g"]),
            "imageSource": _image_from_share_payload(payload["i"]),
            "containerRepository": _container_from_share_payload(payload["c"]),
        }
    )
    return _DecodedEnvironmentShareCode(
        environment=environment,
        build=_build_from_share_payload(payload.get("a")),
    )


def _build_share_payload(build: _ShareBuildSnapshot) -> dict[str, Any]:
    return {
        "i": build.image,
        "t": build.tool_id,
        "u": build.tool_status,
        "e": build.resources.model_dump(mode="json", by_alias=True),
        "s": build.source_commit_sha,
        "m": [
            {
                "n": entry.name,
                "f": entry.folder,
                "s": entry.source,
                "v": entry.version,
                "d": entry.digest,
            }
            for entry in build.skill_manifest.skills
        ],
        "f": [{"p": path, "c": content} for path, content in build.skill_files],
    }


def _build_from_share_payload(value: Any) -> _ShareBuildSnapshot | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) not in {
        _SHARE_BUILD_KEYS,
        _SHARE_BUILD_LEGACY_KEYS,
    }:
        raise EnvironmentShareCodeError("分享码中的可用版本字段不完整。")
    payload = value
    image = payload["i"]
    tool_id = payload["t"]
    tool_status = payload["u"]
    source_commit_sha = payload["s"]
    resources = _resources_from_share_payload(payload["e"])
    manifest = _manifest_from_share_payload(payload.get("m", []))
    skill_files = _version_skill_files_from_share_payload(payload.get("f", []))
    if (
        not isinstance(image, str)
        or not _SHARE_IMAGE_RE.fullmatch(image)
        or "://" in image
        or not isinstance(tool_id, str)
        or len(tool_id) > 1024
        or any(ord(char) < 32 or ord(char) == 127 for char in tool_id)
        or tool_status not in {"", "ready"}
        or bool(tool_id) != (tool_status == "ready")
        or not isinstance(source_commit_sha, str)
        or (source_commit_sha and not _SHARE_COMMIT_RE.fullmatch(source_commit_sha))
    ):
        raise EnvironmentShareCodeError("分享码中的可用版本无效。")
    return _ShareBuildSnapshot(
        image=image,
        tool_id=tool_id,
        tool_status=tool_status,
        resources=resources,
        source_commit_sha=source_commit_sha,
        skill_manifest=manifest,
        skill_files=skill_files,
    )


def _manifest_from_share_payload(value: Any) -> EnvironmentSkillManifest:
    if not isinstance(value, list):
        raise EnvironmentShareCodeError("分享码中的技能 Manifest 无效。")
    entries: list[EnvironmentSkillManifestEntry] = []
    for item in value:
        payload = _share_mapping(item, _SHARE_MANIFEST_ENTRY_KEYS, "技能 Manifest")
        try:
            entries.append(
                EnvironmentSkillManifestEntry(
                    name=payload["n"],
                    folder=payload["f"],
                    source=payload["s"],
                    version=payload["v"],
                    digest=payload["d"],
                )
            )
        except ValueError as error:
            raise EnvironmentShareCodeError("分享码中的技能 Manifest 无效。") from error
    return EnvironmentSkillManifest(skills=entries)


def _version_skill_files_from_share_payload(
    value: Any,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list) or len(value) > 1600:
        raise EnvironmentShareCodeError("分享码中的版本技能文件无效。")
    files: list[tuple[str, str]] = []
    total_bytes = 0
    seen: set[str] = set()
    for item in value:
        payload = _share_mapping(
            item,
            _SHARE_VERSION_SKILL_FILE_KEYS,
            "版本技能文件",
        )
        path = payload["p"]
        content = payload["c"]
        if not isinstance(path, str) or not isinstance(content, str):
            raise EnvironmentShareCodeError("分享码中的版本技能文件无效。")
        normalized = _validate_share_skill_path(path)
        encoded = content.encode("utf-8")
        total_bytes += len(encoded)
        if (
            normalized in seen
            or len(encoded) > 256 * 1024
            or total_bytes > 2 * 1024 * 1024
        ):
            raise EnvironmentShareCodeError("分享码中的版本技能文件无效。")
        seen.add(normalized)
        files.append((normalized, content))
    return tuple(files)


def _validate_share_skill_path(path: str) -> str:
    parts = PurePosixPath(path).parts
    if (
        not path
        or len(path) > 512
        or path.startswith("/")
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise EnvironmentShareCodeError("分享码中的版本技能文件路径无效。")
    return "/".join(parts)


def _decode_share_skill_file(path: str, content: bytes) -> str:
    _validate_share_skill_path(path)
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EnvironmentShareCodeError(
            f"环境技能快照不是 UTF-8 文本：{path}"
        ) from error


def _resources_from_share_payload(value: Any) -> EnvironmentResources:
    payload = _share_mapping(value, _SHARE_RESOURCES_KEYS, "云资源")
    _share_mapping(payload["codePipeline"], _SHARE_CODE_PIPELINE_KEYS, "CodePipeline")
    _share_mapping(
        payload["containerRegistry"],
        _SHARE_CONTAINER_REGISTRY_KEYS,
        "Container Registry",
    )
    try:
        resources = EnvironmentResources.model_validate(payload)
    except ValueError as error:
        raise EnvironmentShareCodeError("分享码中的云资源无效。") from error
    if (
        not resources.region.strip()
        or len(resources.region) > 128
        or any(char.isspace() for char in resources.region)
    ):
        raise EnvironmentShareCodeError("分享码中的云资源无效。")
    return resources


def _skill_from_share_payload(value: Any) -> dict[str, Any]:
    payload = _share_mapping(value, _SHARE_SKILL_KEYS, "技能")
    local_files = payload["lf"]
    if not isinstance(local_files, list):
        raise EnvironmentShareCodeError("分享码中的本地技能文件无效。")
    return {
        "source": payload["x"],
        "folder": payload["f"],
        "name": payload["n"],
        "description": payload["d"],
        "slug": payload["u"],
        "namespace": payload["ns"],
        "localFiles": [_local_file_from_share_payload(file) for file in local_files],
        "skillSpaceId": payload["si"],
        "skillSpaceName": payload["sn"],
        "skillSpaceRegion": payload["sr"],
        "skillId": payload["id"],
        "version": payload["v"],
    }


def _local_file_from_share_payload(value: Any) -> dict[str, Any]:
    payload = _share_mapping(value, _SHARE_LOCAL_FILE_KEYS, "本地技能文件")
    return {"path": payload["p"], "content": payload["c"]}


def _git_from_share_payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    payload = _share_mapping(value, _SHARE_GIT_KEYS, "Git 来源")
    return {
        "repositoryUrl": payload["u"],
        "ref": payload["r"],
        "dockerfilePath": payload["f"],
    }


def _container_from_share_payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    payload = _share_mapping(value, _SHARE_CONTAINER_KEYS, "CR Repository")
    return {
        "region": payload["l"],
        "registry": payload["g"],
        "namespace": payload["n"],
        "repository": payload["r"],
    }


def _image_from_share_payload(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    payload = _share_mapping(value, _SHARE_IMAGE_KEYS, "镜像来源")
    return {
        "region": payload["l"],
        "registry": payload["g"],
        "namespace": payload["n"],
        "repository": payload["r"],
        "reference": payload["x"],
    }


def _share_mapping(
    value: Any, expected_keys: frozenset[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise EnvironmentShareCodeError(f"分享码中的{label}字段不完整。")
    return value


def _share_code_import_error(error: Exception) -> str:
    if isinstance(error, EnvironmentShareCodeError):
        return str(error)
    detail = str(error).strip()
    return (detail or "环境分享码导入失败。")[:1000]


def _validate_shareable_git_source(environment: EnvironmentRecord) -> None:
    source = environment.git_source
    if source is None:
        return
    parsed = urlsplit(source.repository_url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("Git 环境中的 HTTPS 地址端口无效，无法导出分享码。") from error
    hostname = parsed.hostname or ""
    private_literal = False
    try:
        private_literal = not ipaddress.ip_address(hostname).is_global
    except ValueError:
        pass
    if (
        parsed.scheme.casefold() != "https"
        or not hostname
        or hostname.casefold().rstrip(".") == "localhost"
        or private_literal
        or port not in {None, 443}
        or not parsed.path.strip("/")
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        raise ValueError(
            "Git 环境仅能导出不含用户名、密码、Token 或查询参数的公开 HTTPS 地址。"
        )


__all__ = ["EnvironmentService"]
