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

"""AgentKit Skills repository used by the Studio BFF."""

from __future__ import annotations

import base64
import io
import mimetypes
import os
import stat
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .archive import SkillArchive

DEGRADED_SKILLSPACE_WARNING = "部分关联异常，已恢复可读取技能"


@dataclass(frozen=True)
class SkillSpaceListResult:
    items: tuple[dict[str, object], ...]
    total_count: int
    degraded: bool = False


def _is_missing_skill_relation(error: BaseException) -> bool:
    expected = "ResourceNotFound.skill"
    for name in ("code", "error_code", "Code"):
        if str(getattr(error, name, "") or "").strip() == expected:
            return True
    return False


def list_skill_space_items(
    client: Any,
    skills_types: Any,
    *,
    space_id: str,
    page: int = 1,
    page_size: int = 100,
) -> SkillSpaceListResult:
    """List authoritative relations, recovering readable names only on one 404."""

    try:
        response = client.list_skills_by_skill_space(
            skills_types.ListSkillsBySkillSpaceRequest(
                SkillSpaceId=space_id,
                PageNumber=page,
                PageSize=page_size,
            )
        )
    except Exception as relation_error:
        if not _is_missing_skill_relation(relation_error):
            raise
        space = client.get_skill_space(skills_types.GetSkillSpaceRequest(Id=space_id))
        space_name = str(getattr(space, "name", "") or "").strip()
        if not space_name:
            raise relation_error
        fallback = client.list_skills_by_space_id(
            skills_types.ListSkillsBySpaceIdRequest(
                SkillSpaceId=space_id,
                SkillSpaceName=space_name,
            )
        )
        recovered: list[dict[str, object]] = []
        for basic in list(getattr(fallback, "items", None) or []):
            name = str(getattr(basic, "name", "") or "").strip()
            if not name:
                continue
            try:
                info = client.get_skill_info(
                    skills_types.GetSkillInfoRequest(
                        SkillName=name,
                        SkillSpaceName=space_name,
                        SkillSpaceId=space_id,
                    )
                )
            except Exception as info_error:
                if _is_missing_skill_relation(info_error):
                    continue
                raise
            recovered.append(
                {
                    "skillId": "",
                    "skillName": str(getattr(info, "skill_name", "") or name),
                    "skillDescription": str(
                        getattr(info, "description", "")
                        or getattr(basic, "description", "")
                        or ""
                    ),
                    "version": "",
                    "skillStatus": "",
                    "lookupByName": True,
                    "degraded": True,
                }
            )
        start = (page - 1) * page_size
        return SkillSpaceListResult(
            items=tuple(recovered[start : start + page_size]),
            total_count=len(recovered),
            degraded=True,
        )

    raw_items = list(getattr(response, "items", None) or [])
    return SkillSpaceListResult(
        items=tuple(
            {
                "skillId": str(getattr(item, "skill_id", "") or ""),
                "skillName": str(getattr(item, "skill_name", "") or ""),
                "skillDescription": str(getattr(item, "skill_description", "") or ""),
                "version": str(getattr(item, "version", "") or ""),
                "skillStatus": str(getattr(item, "skill_status", "") or ""),
            }
            for item in raw_items
        ),
        total_count=(
            int(response.total_count)
            if getattr(response, "total_count", None) is not None
            else len(raw_items)
        ),
    )


def _is_macos_metadata(path: PurePosixPath) -> bool:
    return bool(path.parts) and (
        path.parts[0] == "__MACOSX"
        or path.name == ".DS_Store"
        or path.name.startswith("._")
    )


class SkillRepositoryError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        retryable: bool = False,
        original_error: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.original_error = original_error

    def detail(self) -> dict[str, object]:
        detail: dict[str, object] = {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }
        if self.original_error is not None:
            detail["originalError"] = {
                "type": (
                    f"{type(self.original_error).__module__}."
                    f"{type(self.original_error).__qualname__}"
                ),
                "message": str(self.original_error).strip()
                or repr(self.original_error),
                "repr": repr(self.original_error),
            }
        return detail


def resolve_skill_response(
    client: Any,
    *,
    space_id: str,
    skill_id: str,
    version: str | None,
    skill_space_name: str | None = None,
    skill_name: str | None = None,
) -> Any:
    """Read either a managed Skill version or a legacy SkillSpace Skill."""
    from agentkit.sdk.skills import types as skills_types

    if (
        skill_space_name
        and skill_name
        and not version
        and (not skill_id or skill_id == skill_name)
    ):
        return client.get_skill_info(
            skills_types.GetSkillInfoRequest(
                SkillName=skill_name,
                SkillSpaceName=skill_space_name,
                SkillSpaceId=space_id,
            )
        )

    try:
        return client.get_skill_version(
            skills_types.GetSkillVersionRequest(Id=skill_id, SkillVersion=version)
        )
    except Exception as version_error:
        if (
            "interface type not consistent with skill type"
            not in str(version_error).casefold()
            or not skill_space_name
            or not skill_name
        ):
            raise
        try:
            return client.get_skill_info(
                skills_types.GetSkillInfoRequest(
                    SkillName=skill_name,
                    SkillSpaceName=skill_space_name,
                    SkillSpaceId=space_id,
                )
            )
        except Exception as info_error:
            raise info_error from version_error


class AgentKitSkillRepository:
    """Keep cloud SDK and TOS details outside route and UI code."""

    def __init__(self, client_factory: Callable[[str], Any]) -> None:
        self._client_factory = client_factory

    def list_spaces(
        self,
        *,
        region: str,
        page: int,
        page_size: int,
        project_name: str | None,
        author: str | None,
    ) -> dict[str, object]:
        from agentkit.sdk.skills import types as skills_types

        tag_filters = None
        if author:
            tag_filters = [
                skills_types.TagFilterForSkill(Key="author", Values=[author])
            ]
        response = self._client_factory(region).list_skill_spaces(
            skills_types.ListSkillSpacesRequest(
                PageNumber=page,
                PageSize=page_size,
                ProjectName=project_name,
                TagFilters=tag_filters,
            )
        )
        items = list(response.items or [])
        return {
            "items": [self._space_item(item, region) for item in items],
            "totalCount": response.total_count
            if response.total_count is not None
            else len(items),
            "page": page,
            "pageSize": page_size,
        }

    def create_space(
        self,
        *,
        region: str,
        name: str,
        description: str | None,
        project_name: str | None,
        author: str,
    ) -> dict[str, object]:
        from agentkit.sdk.skills import types as skills_types

        effective_project = project_name or os.getenv("VEADK_STUDIO_PROJECT") or None
        response = self._client_factory(region).create_skill_space(
            skills_types.CreateSkillSpaceRequest(
                Name=name,
                Description=description,
                ProjectName=effective_project,
                Tags=[skills_types.TagForSkill(Key="author", Value=author)],
            )
        )
        space_id = str(response.id or "")
        if not space_id:
            raise SkillRepositoryError(
                "SKILL_SPACE_CREATE_FAILED",
                "AgentKit 未返回 Skill 空间 ID",
                status_code=502,
            )
        return {
            "id": space_id,
            "name": name,
            "description": description or "",
            "status": "Creating",
            "region": region,
            "projectName": effective_project or "",
            "author": author,
            "skillCount": 0,
        }

    def update_space(
        self,
        *,
        region: str,
        space_id: str,
        name: str,
        description: str | None,
    ) -> dict[str, object]:
        from agentkit.sdk.skills import types as skills_types

        client = self._client_factory(region)
        client.update_skill_space(
            skills_types.UpdateSkillSpaceRequest(
                Id=space_id,
                Name=name,
                Description=description or "",
            )
        )
        value = client.get_skill_space(skills_types.GetSkillSpaceRequest(Id=space_id))
        return self._space_item(value, region)

    def delete_space(self, *, region: str, space_id: str) -> None:
        from agentkit.sdk.skills import types as skills_types

        self._client_factory(region).delete_skill_space(
            skills_types.DeleteSkillSpaceRequest(Id=space_id)
        )

    def delete_skill(self, *, region: str, skill_id: str) -> None:
        from agentkit.sdk.skills import types as skills_types

        self._client_factory(region).delete_skill(
            skills_types.DeleteSkillRequest(Id=skill_id)
        )

    def skill_archive(
        self,
        *,
        region: str,
        space_id: str,
        skill_id: str,
        version: str | None,
        skill_space_name: str | None = None,
        skill_name: str | None = None,
    ) -> tuple[bytes, str]:
        response = resolve_skill_response(
            self._client_factory(region),
            space_id=space_id,
            skill_id=skill_id,
            version=version,
            skill_space_name=skill_space_name,
            skill_name=skill_name,
        )
        name = str(
            getattr(response, "name", "")
            or getattr(response, "skill_name", "")
            or skill_name
            or skill_id
        )
        bucket = str(getattr(response, "bucket_name", "") or "")
        path = str(getattr(response, "tos_path", "") or "")
        if bucket and path:
            from veadk.skills.materializer import _download_legacy_skill_space_skill
            from veadk.skills.skill import Skill

            remote = Skill(
                name=name,
                description=str(getattr(response, "description", "") or ""),
                path=path,
                skill_space_id=space_id,
                bucket_name=bucket,
                id=skill_id,
                version_id=version or str(getattr(response, "version", "") or ""),
            )
            with tempfile.TemporaryDirectory(prefix="veadk-skill-view-") as directory:
                archive_path = Path(directory) / "skill.zip"
                try:
                    downloaded = _download_legacy_skill_space_skill(
                        remote,
                        archive_path,
                        region=region,
                        raise_on_error=True,
                    )
                except Exception as error:
                    raise SkillRepositoryError(
                        "SKILL_ARCHIVE_DOWNLOAD_FAILED",
                        "暂时无法下载 Skill 文件，请稍后重试。",
                        status_code=502,
                        retryable=True,
                        original_error=error,
                    ) from error
                if not downloaded:
                    raise SkillRepositoryError(
                        "SKILL_ARCHIVE_DOWNLOAD_FAILED",
                        "暂时无法下载 Skill 文件，请稍后重试。",
                        status_code=502,
                        retryable=True,
                    )
                content = archive_path.read_bytes()
        else:
            skill_md = str(getattr(response, "skill_md", "") or "")
            if not skill_md:
                raise SkillRepositoryError(
                    "SKILL_ARCHIVE_NOT_FOUND",
                    "该 Skill 版本没有可下载的文件。",
                    status_code=404,
                )
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(f"{name}/SKILL.md", skill_md)
            content = buffer.getvalue()
        if len(content) > 20 * 1024 * 1024:
            raise SkillRepositoryError(
                "SKILL_ARCHIVE_TOO_LARGE",
                "Skill ZIP 超过 20 MiB，无法在 Studio 中打开。",
                status_code=413,
            )
        return content, f"{name}.zip"

    def skill_files(
        self,
        *,
        region: str,
        space_id: str,
        skill_id: str,
        version: str | None,
        skill_space_name: str | None = None,
        skill_name: str | None = None,
    ) -> dict[str, object]:
        content, filename = self.skill_archive(
            region=region,
            space_id=space_id,
            skill_id=skill_id,
            version=version,
            skill_space_name=skill_space_name,
            skill_name=skill_name,
        )
        files: list[dict[str, object]] = []
        total = 0
        seen: set[str] = set()
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                infos = [
                    item
                    for item in archive.infolist()
                    if not item.is_dir()
                    and not _is_macos_metadata(PurePosixPath(item.filename))
                ]
                if len(infos) > 100:
                    raise SkillRepositoryError(
                        "SKILL_ARCHIVE_FILE_COUNT",
                        "Skill 文件数超过 100 个，无法在 Studio 中打开。",
                        status_code=413,
                    )
                for info in infos:
                    path = PurePosixPath(info.filename)
                    normalized = path.as_posix()
                    if (
                        path.is_absolute()
                        or not path.parts
                        or ".." in path.parts
                        or "\\" in info.filename
                        or normalized.casefold() in seen
                    ):
                        raise SkillRepositoryError(
                            "SKILL_ARCHIVE_UNSAFE_PATH",
                            f"Skill ZIP 包含不安全或重复路径：{info.filename}",
                            status_code=422,
                        )
                    seen.add(normalized.casefold())
                    if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                        raise SkillRepositoryError(
                            "SKILL_ARCHIVE_SYMLINK",
                            f"Skill ZIP 不允许符号链接：{info.filename}",
                            status_code=422,
                        )
                    total += info.file_size
                    if total > 20 * 1024 * 1024:
                        raise SkillRepositoryError(
                            "SKILL_ARCHIVE_EXPANDED_TOO_LARGE",
                            "Skill 解压后超过 20 MiB，无法在 Studio 中打开。",
                            status_code=413,
                        )
                    raw = archive.read(info)
                    mime = (
                        mimetypes.guess_type(normalized)[0]
                        or "application/octet-stream"
                    )
                    item: dict[str, object] = {
                        "path": normalized,
                        "size": info.file_size,
                        "mimeType": mime,
                        "kind": "binary",
                        "content": f"data:{mime};base64,{base64.b64encode(raw).decode()}",
                    }
                    if mime.startswith("image/"):
                        item["kind"] = "image"
                        item["content"] = (
                            f"data:{mime};base64,{base64.b64encode(raw).decode()}"
                        )
                    elif mime.startswith("text/") or path.suffix.lower() in {
                        ".json",
                        ".yaml",
                        ".yml",
                        ".toml",
                        ".py",
                        ".js",
                        ".ts",
                        ".tsx",
                        ".md",
                    }:
                        try:
                            item["content"] = raw.decode("utf-8")
                            item["kind"] = "text"
                        except UnicodeDecodeError:
                            pass
                    files.append(item)
        except zipfile.BadZipFile as error:
            raise SkillRepositoryError(
                "SKILL_ARCHIVE_INVALID",
                "Skill 文件包不是有效的 ZIP。",
                status_code=502,
            ) from error
        return {"filename": filename, "files": files}

    def publish_archive(
        self,
        *,
        region: str,
        project_name: str | None,
        space_id: str,
        archive: SkillArchive,
        author: str,
    ) -> dict[str, object]:
        from agentkit.sdk.skills import types as skills_types
        from agentkit.toolkit.cli.cli_skills_workflow import (
            _make_content_hashed_zip_copy,
            _wait_for_running_version,
        )
        from agentkit.toolkit.config import GlobalConfigManager

        from .storage import (
            ensure_skill_publish_bucket,
            resolve_skill_publish_credentials,
            resolve_skill_publish_storage,
            upload_skill_archive,
        )

        client = self._client_factory(region)
        if self._space_has_skill_named(
            client,
            skills_types,
            space_id=space_id,
            name=archive.name,
        ):
            raise SkillRepositoryError(
                "SKILL_NAME_CONFLICT",
                f"已存在同名 Skill“{archive.name}”，请重命名后上传，或使用优化功能覆盖。",
                status_code=409,
            )

        config = GlobalConfigManager().load()
        storage = resolve_skill_publish_storage(
            region=region,
            config_bucket=config.tos.bucket or "",
            config_prefix=config.tos.prefix or "",
        )
        credentials = resolve_skill_publish_credentials(provider=storage.provider)
        ensure_skill_publish_bucket(storage, credentials)
        with tempfile.TemporaryDirectory(prefix="veadk-skill-upload-") as directory:
            archive_path = Path(directory) / f"{archive.name}.zip"
            archive_path.write_bytes(archive.content)
            hashed_path = _make_content_hashed_zip_copy(
                str(archive_path), archive.name, directory
            )
            tos_url = upload_skill_archive(hashed_path, storage, credentials)
        created = client.create_skill(
            skills_types.CreateSkillRequest(
                Name=archive.name,
                Description=archive.description,
                TosUrl=tos_url,
                SkillSpaces=[space_id],
                BucketName=storage.bucket,
                ProjectName=project_name,
                Tags=[skills_types.TagForSkill(Key="author", Value=author)],
            )
        )
        skill_id = str(created.id or "")
        if not skill_id:
            raise SkillRepositoryError(
                "SKILL_UPLOAD_FAILED",
                "AgentKit 未返回 Skill ID",
                status_code=502,
            )
        latest = _wait_for_running_version(
            client=client,
            skill_id=skill_id,
            timeout_seconds=300,
            poll_interval_seconds=5,
        )
        version = str(latest.version or "")
        client.publish_skill_to_skill_space(
            skills_types.PublishSkillToSkillSpaceRequest(
                SkillSpaces=[space_id],
                Skills=[skills_types.SkillBasicInfo(SkillId=skill_id, Version=version)],
            )
        )
        return {
            "skillId": skill_id,
            "name": archive.name,
            "description": archive.description,
            "version": version,
            "skillSpaceId": space_id,
        }

    @staticmethod
    def _space_has_skill_named(
        client: Any,
        skills_types: Any,
        *,
        space_id: str,
        name: str,
    ) -> bool:
        page = 1
        page_size = 100
        expected = name.casefold()
        while True:
            result = list_skill_space_items(
                client,
                skills_types,
                space_id=space_id,
                page=page,
                page_size=page_size,
            )
            items = list(result.items)
            if any(
                str(item.get("skillName") or "").casefold() == expected
                for item in items
            ):
                return True
            if page * page_size >= result.total_count:
                return False
            if len(items) < page_size:
                return False
            page += 1

    @staticmethod
    def _skill_relation_name(value: Any) -> str:
        return str(
            getattr(value, "skill_name", None)
            or getattr(value, "skillName", None)
            or getattr(value, "name", None)
            or getattr(value, "Name", None)
            or ""
        )

    @staticmethod
    def _space_item(value: Any, region: str) -> dict[str, object]:
        tags = {
            str(getattr(tag, "key", "") or ""): str(getattr(tag, "value", "") or "")
            for tag in (getattr(value, "tags", None) or [])
        }
        return {
            "id": str(getattr(value, "id", "") or ""),
            "name": str(getattr(value, "name", "") or ""),
            "description": str(getattr(value, "description", "") or ""),
            "status": str(getattr(value, "status", "") or ""),
            "region": region,
            "projectName": str(getattr(value, "project_name", "") or ""),
            "updatedAt": str(getattr(value, "update_time_stamp", "") or ""),
            "skillCount": len(getattr(value, "relations", None) or []),
            "author": tags.get("author", ""),
        }


__all__ = [
    "AgentKitSkillRepository",
    "DEGRADED_SKILLSPACE_WARNING",
    "SkillRepositoryError",
    "SkillSpaceListResult",
    "list_skill_space_items",
]
