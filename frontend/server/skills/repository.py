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
from pathlib import Path, PurePosixPath
from typing import Any

from .archive import SkillArchive


class SkillRepositoryError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code

    def detail(self) -> dict[str, object]:
        return {"code": self.code, "message": str(self), "retryable": False}


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
    ) -> tuple[bytes, str]:
        from agentkit.sdk.skills import types as skills_types

        response = self._client_factory(region).get_skill_version(
            skills_types.GetSkillVersionRequest(Id=skill_id, SkillVersion=version)
        )
        name = str(getattr(response, "name", "") or skill_id)
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
                if not _download_legacy_skill_space_skill(remote, archive_path):
                    raise SkillRepositoryError(
                        "SKILL_ARCHIVE_DOWNLOAD_FAILED",
                        "暂时无法下载 Skill 文件，请稍后重试。",
                        status_code=502,
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
    ) -> dict[str, object]:
        content, filename = self.skill_archive(
            region=region,
            space_id=space_id,
            skill_id=skill_id,
            version=version,
        )
        files: list[dict[str, object]] = []
        total = 0
        seen: set[str] = set()
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                infos = [item for item in archive.infolist() if not item.is_dir()]
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
            _ensure_bucket_ready,
            _make_content_hashed_zip_copy,
            _tos_upload,
            _wait_for_running_version,
        )
        from agentkit.toolkit.config import GlobalConfigManager
        from agentkit.toolkit.volcengine.services.tos_service import TOSService

        client = self._client_factory(region)
        existing = client.list_skills(
            skills_types.ListSkillsRequest(
                PageNumber=1,
                PageSize=50,
                Filter=skills_types.SkillFilter(Name=archive.name),
                ProjectName=project_name,
            )
        )
        if existing.items:
            raise SkillRepositoryError(
                "SKILL_NAME_CONFLICT",
                f"已存在同名 Skill“{archive.name}”，请重命名后上传，或使用优化功能覆盖。",
                status_code=409,
            )

        config = GlobalConfigManager().load()
        configured_bucket = (
            os.getenv("VEADK_SKILL_CREATOR_TOS_BUCKET") or config.tos.bucket or ""
        ).strip()
        bucket = configured_bucket or TOSService.generate_bucket_name()
        prefix = (
            os.getenv("VEADK_SKILL_CREATOR_TOS_PREFIX")
            or config.tos.prefix
            or "agentkit/skills"
        ).strip()
        _ensure_bucket_ready(
            bucket_name=bucket,
            prefix=prefix,
            region=region,
            auto_bucket=not bool(configured_bucket),
            assume_yes=True,
            assume_no=False,
        )
        with tempfile.TemporaryDirectory(prefix="veadk-skill-upload-") as directory:
            archive_path = Path(directory) / f"{archive.name}.zip"
            archive_path.write_bytes(archive.content)
            hashed_path = _make_content_hashed_zip_copy(
                str(archive_path), archive.name, directory
            )
            tos_url = _tos_upload(
                hashed_path, bucket, prefix, region, verify_bucket=False
            )
        created = client.create_skill(
            skills_types.CreateSkillRequest(
                Name=archive.name,
                Description=archive.description,
                TosUrl=tos_url,
                SkillSpaces=[space_id],
                BucketName=bucket,
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


__all__ = ["AgentKitSkillRepository", "SkillRepositoryError"]
