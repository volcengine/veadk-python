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

"""Read and create native AgentKit Skill versions without changing shared copies."""

from __future__ import annotations

import re
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from .archive import validate_skill_archive
from .models import SkillIdentity
from .consts import SHARED_SOURCE_VERSION_TAG
from .repository import SkillRepositoryError
from .system_spaces import is_review_space, is_shared_space, require_review_read

if TYPE_CHECKING:
    from .repository import AgentKitSkillRepository


def version_order(value: str) -> tuple[int, str]:
    match = re.fullmatch(r"v(\d+)", value)
    return (int(match.group(1)) if match else -1, value)


def _timestamp(value: Any) -> str:
    text = str(value or "")
    if text.isdigit():
        return datetime.fromtimestamp(int(text), timezone.utc).isoformat()
    return text


def _tags(value: Any) -> dict[str, str]:
    return {str(tag.key): str(tag.value) for tag in getattr(value, "tags", None) or []}


class SkillVersionRepository:
    def __init__(
        self, repository: AgentKitSkillRepository, client_factory: Callable[[str], Any]
    ) -> None:
        self._repository = repository
        self._client_factory = client_factory
        self._update_lock = Lock()

    @staticmethod
    def _versions(client: Any, skill_id: str) -> list[Any]:
        from agentkit.sdk.skills import types as sdk

        items = []
        page = 1
        while True:
            response = client.list_skill_versions(
                sdk.ListSkillVersionsRequest(Id=skill_id, PageNumber=page, PageSize=100)
            )
            chunk = response.items or []
            items.extend(chunk)
            if len(chunk) < 100 or (
                response.total_count is not None and len(items) >= response.total_count
            ):
                return sorted(
                    items, key=lambda item: version_order(item.version), reverse=True
                )
            page += 1

    def _source(
        self, client: Any, identity: SkillIdentity, space_id: str, skill_id: str
    ) -> tuple[Any, Any, list[Any], bool]:
        from agentkit.sdk.skills import types as sdk

        require_review_read(
            client, space_id, skill_id=skill_id, is_admin=identity.is_admin
        )
        space = client.get_skill_space(sdk.GetSkillSpaceRequest(Id=space_id))
        skill = client.get_skill(sdk.GetSkillRequest(Id=skill_id))
        relations = [
            item
            for item in self._repository.reviews._relations(client, space_id)
            if item.skill_id == skill_id
        ]
        if not relations:
            raise SkillRepositoryError(
                "SKILL_VERSION_SOURCE_NOT_FOUND",
                "该技能不属于当前空间",
                status_code=404,
            )
        personal = not is_shared_space(space) and not is_review_space(space)
        author = _tags(skill).get("author") or _tags(space).get("author")
        if personal and author and author != identity.author and not identity.is_admin:
            raise SkillRepositoryError(
                "SKILL_VERSION_FORBIDDEN", "只能查看自己创建的技能版本", status_code=403
            )
        can_update = personal and (identity.is_admin or author == identity.author)
        return space, skill, relations, can_update

    def list(
        self, identity: SkillIdentity, *, region: str, space_id: str, skill_id: str
    ) -> dict[str, Any]:
        client = self._client_factory(region)
        space, skill, relations, can_update = self._source(
            client, identity, space_id, skill_id
        )
        published = {str(item.version) for item in relations}
        items = self._versions(client, skill_id)
        display_metadata = {}
        if is_shared_space(space):
            items = [item for item in items if item.version in published]
            display_metadata = {
                "sourceVersion": _tags(skill).get(SHARED_SOURCE_VERSION_TAG, ""),
                "author": _tags(skill).get("author", ""),
            }
        return {
            "items": [
                {
                    "skillId": skill_id,
                    "version": item.version,
                    "name": item.name,
                    "description": item.description,
                    "status": item.status,
                    "createdAt": _timestamp(item.create_time_stamp),
                    "updatedAt": _timestamp(item.update_time_stamp),
                    "error": item.error_message or "",
                    "isCurrent": item.version in published,
                    **display_metadata,
                }
                for item in items
            ],
            "totalCount": len(items),
            "canUpdate": can_update,
        }

    @classmethod
    def _wait_for_new_version(
        cls,
        client: Any,
        skill_id: str,
        previous: set[str],
        *,
        timeout_seconds: float = 90,
    ) -> Any:
        deadline = time.monotonic() + timeout_seconds
        while True:
            new = [
                item
                for item in cls._versions(client, skill_id)
                if item.version not in previous
            ]
            if new:
                latest = new[0]
                status = str(latest.status or "").lower()
                if status in {"running", "ready"}:
                    return latest
                if status == "failed":
                    raise SkillRepositoryError(
                        "SKILL_VERSION_FAILED",
                        latest.error_message or "新版本创建失败，请检查文件后重试",
                        status_code=502,
                    )
            if time.monotonic() >= deadline:
                raise SkillRepositoryError(
                    "SKILL_VERSION_PENDING",
                    "新版本仍在处理中，请刷新版本列表查看结果",
                    status_code=504,
                    retryable=True,
                )
            time.sleep(2)

    def upload(
        self,
        identity: SkillIdentity,
        *,
        region: str,
        space_id: str,
        skill_id: str,
        content: bytes,
    ) -> dict[str, Any]:
        from agentkit.sdk.skills import types as sdk
        from agentkit.toolkit.cli.cli_skills_workflow import (
            _make_content_hashed_zip_copy,
        )
        from agentkit.toolkit.config import GlobalConfigManager

        from .storage import (
            ensure_skill_publish_bucket,
            resolve_skill_publish_credentials,
            resolve_skill_publish_storage,
            upload_skill_archive,
        )

        archive = validate_skill_archive(content)
        client = self._client_factory(region)
        with self._update_lock:
            _, skill, _, can_update = self._source(client, identity, space_id, skill_id)
            if not can_update:
                raise SkillRepositoryError(
                    "SKILL_VERSION_UPDATE_FORBIDDEN",
                    "只能为自己的个人技能上传新版本",
                    status_code=403,
                )
            if archive.name != skill.name:
                raise SkillRepositoryError(
                    "SKILL_VERSION_NAME_MISMATCH",
                    "新版本必须保留原技能名称",
                    status_code=422,
                )
            previous = {item.version for item in self._versions(client, skill_id)}
            config = GlobalConfigManager().load()
            storage = resolve_skill_publish_storage(
                region=region,
                config_bucket=config.tos.bucket or "",
                config_prefix=config.tos.prefix or "",
            )
            credentials = resolve_skill_publish_credentials(provider=storage.provider)
            ensure_skill_publish_bucket(storage, credentials)
            with tempfile.TemporaryDirectory(
                prefix="veadk-skill-version-"
            ) as directory:
                path = Path(directory) / f"{archive.name}.zip"
                path.write_bytes(archive.content)
                hashed = _make_content_hashed_zip_copy(
                    str(path), archive.name, directory
                )
                tos_url = upload_skill_archive(hashed, storage, credentials)
            client.update_skill(
                sdk.UpdateSkillRequest(
                    Id=skill_id,
                    Name=archive.name,
                    Description=archive.description,
                    TosUrl=tos_url,
                    BucketName=storage.bucket,
                    SkillSpaces=[space_id],
                )
            )
            latest = self._wait_for_new_version(client, skill_id, previous)
            client.publish_skill_to_skill_space(
                sdk.PublishSkillToSkillSpaceRequest(
                    SkillSpaces=[space_id],
                    Skills=[
                        sdk.SkillBasicInfo(SkillId=skill_id, Version=latest.version)
                    ],
                )
            )
            return {
                "skillId": skill_id,
                "name": archive.name,
                "version": latest.version,
                "description": archive.description,
                "skillSpaceId": space_id,
            }
