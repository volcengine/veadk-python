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
import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Protocol
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
from .models import (
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
    EnvironmentSkillFile,
    EnvironmentSkillManifest,
    EnvironmentSkillManifestEntry,
    EnvironmentSkillSelection,
    EnvironmentView,
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


class EnvironmentService:
    def __init__(
        self,
        repository: TosEnvironmentRepository | None,
        cloud: EnvironmentCloudGateway | None,
        *,
        workspace_references: WorkspaceReferenceLookup | None = None,
        tool_provisioner: EnvironmentToolProvisioner | None = None,
        unavailable_reason: str = "管理员未配置环境持久化存储。",
    ) -> None:
        self._repository = repository
        self._cloud = cloud
        self._workspace_references = workspace_references
        self._tool_provisioner = tool_provisioner
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

    async def create(self, owner_id: str, body: EnvironmentInput) -> EnvironmentView:
        now = _now()
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
                )
            }
        )
        values["dockerfile"] = build_dockerfile(merged_input)
        updated = EnvironmentRecord.model_validate(values)
        saved = await repository.update(updated)
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
        version_dockerfile = _dockerfile_with_skill_layer(
            environment.dockerfile, bool(skill_files)
        )
        context = _build_context(version_dockerfile, skill_files, skill_manifest)
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
            apiVersion="agentkit.studio/v1alpha1",
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
        if version_config.base_environment == "aio-sandbox" and (
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
        if environment.base_environment != "aio-sandbox":
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
            )
        except asyncio.CancelledError:
            raise
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
                "current_step": "环境与 Sandbox Tool 已就绪",
                "steps": _with_tool_step(current.steps, "succeeded"),
                "updated_at": _now(),
            }
        )
        await repository.update_build(owner_id, ready)

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
):
    import asyncio

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


def _add_tar_file(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = 0o644
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


__all__ = ["EnvironmentService"]
