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

"""Provision and protect Studio system SkillSpaces in the current cloud account."""

from __future__ import annotations

import os
from collections.abc import Callable
from threading import Lock
from typing import Any

from .consts import (
    RESERVED_SKILL_SPACE_NAMES,
    REVIEW_SPACE,
    SHARE_SPACE,
    SYSTEM_SKILL_SPACES,
    SystemSkillSpace,
)
from .repository import SkillRepositoryError


def is_system_space(value: Any, definition: SystemSkillSpace) -> bool:
    # Identify system spaces independently of provider-specific tag support
    return (
        getattr(value, "name", "") == definition.name
        and getattr(value, "description", "") == definition.managed_description
    )


def is_shared_space(value: Any) -> bool:
    return is_system_space(value, SHARE_SPACE)


def is_review_space(value: Any) -> bool:
    return is_system_space(value, REVIEW_SPACE)


def require_review_read(
    client: Any, space_id: str, *, skill_id: str | None = None, is_admin: bool = False
) -> None:
    from agentkit.sdk.skills import types as sdk
    from .consts import REVIEW_SOURCE_SKILL_TAG

    if is_admin:
        return
    space = client.get_skill_space(sdk.GetSkillSpaceRequest(Id=space_id))
    blocked = is_review_space(space)
    if not blocked and skill_id:
        skill = client.get_skill(sdk.GetSkillRequest(Id=skill_id))
        blocked = any(
            tag.key == REVIEW_SOURCE_SKILL_TAG
            for tag in getattr(skill, "tags", None) or []
        )
    if blocked:
        raise SkillRepositoryError(
            "SKILL_REVIEW_FORBIDDEN", "仅管理员可以查看审核申请", status_code=403
        )


def validate_personal_space(name: str, description: str | None) -> None:
    if name.strip().lower() in RESERVED_SKILL_SPACE_NAMES or any(
        space.marker in (description or "") for space in SYSTEM_SKILL_SPACES
    ):
        raise SkillRepositoryError(
            "SKILL_SPACE_RESERVED_IDENTITY",
            "此名称或标识由系统空间保留，请使用其他名称和描述",
            status_code=409,
        )


class SystemSpaceManager:
    def __init__(self, client_factory: Callable[[str], Any]) -> None:
        self._client_factory = client_factory
        self._locks: dict[tuple[str, str, str], Any] = {}
        self._created_ids: dict[tuple[str, str, str], str] = {}

    def ensure(self, region: str, definition: SystemSkillSpace) -> Any:
        from agentkit.sdk.skills import types as sdk

        project = os.getenv("VEADK_STUDIO_PROJECT", "").strip() or "default"
        key = (region, project, definition.name)
        with self._locks.setdefault(key, Lock()):
            client = self._client_factory(region)
            existing = self._find(client, project, definition)
            if existing is not None:
                return existing
            # Creation can precede ListSkillSpaces index visibility
            if key in self._created_ids:
                return client.get_skill_space(
                    sdk.GetSkillSpaceRequest(Id=self._created_ids[key])
                )
            tags = [
                sdk.TagForSkill(Key="veadk:space-role", Value=definition.name),
                sdk.TagForSkill(Key="veadk:visibility", Value=definition.visibility),
                sdk.TagForSkill(Key="veadk:managed", Value="true"),
            ]
            try:
                result = client.create_skill_space(
                    sdk.CreateSkillSpaceRequest(
                        Name=definition.name,
                        Description=definition.managed_description,
                        ProjectName=project,
                        Tags=tags,
                    )
                )
            except Exception:
                # Another Studio instance may have completed the same create
                existing = self._find(client, project, definition)
                if existing is not None:
                    return existing
                raise
            space_id = str(result.id or "")
            if not space_id:
                raise SkillRepositoryError(
                    "SYSTEM_SKILL_SPACE_CREATE_FAILED",
                    f"{definition.label}创建失败，服务未返回空间 ID，请重试",
                    status_code=502,
                    retryable=True,
                )
            self._created_ids[key] = space_id
            return sdk.GetSkillSpaceResponse(
                Id=space_id,
                Name=definition.name,
                ProjectName=project,
                Description=definition.managed_description,
                Status="Creating",
                Tags=tags,
            )

    @staticmethod
    def _find(client: Any, project: str, definition: SystemSkillSpace) -> Any | None:
        from agentkit.sdk.skills import types as sdk

        page = 1
        matches = {}
        while True:
            result = client.list_skill_spaces(
                sdk.ListSkillSpacesRequest(
                    PageNumber=page,
                    PageSize=100,
                    ProjectName=project,
                )
            )
            items = result.items or []
            for space in items:
                if (space.project_name or "default") != project:
                    continue
                if getattr(space, "name", "") != definition.name:
                    continue
                if not is_system_space(space, definition):
                    raise SkillRepositoryError(
                        "SYSTEM_SKILL_SPACE_NAME_CONFLICT",
                        f"{definition.label}的系统名称已被其他空间占用，请联系管理员处理",
                        status_code=409,
                    )
                matches[space.id] = space
            if len(matches) > 1:
                raise SkillRepositoryError(
                    "SYSTEM_SKILL_SPACE_CONFLICT",
                    f"存在多个{definition.label}，请联系管理员检查空间标识",
                    status_code=409,
                )
            if len(items) < 100 or page * 100 >= (result.total_count or 0):
                break
            page += 1
        return next(iter(matches.values()), None)


def require_space_write(client: Any, space_id: str, *, is_admin: bool = False) -> bool:
    from agentkit.sdk.skills import types as sdk

    space = client.get_skill_space(sdk.GetSkillSpaceRequest(Id=space_id))
    if is_review_space(space):
        raise SkillRepositoryError(
            "REVIEW_SKILL_SPACE_READ_ONLY",
            "待审核空间由审核流程管理，不能直接修改",
            status_code=403,
        )
    shared = is_shared_space(space)
    if shared and not is_admin:
        raise SkillRepositoryError(
            "SHARED_SKILL_SPACE_READ_ONLY",
            "企业共享空间中的技能由管理员发布和维护",
            status_code=403,
        )
    return shared


def require_skill_write(client: Any, skill_id: str, *, is_admin: bool = False) -> None:
    from agentkit.sdk.skills import types as sdk

    page = 1
    checked: set[str] = set()
    while True:
        result = client.list_skill_spaces_by_skill(
            sdk.ListSkillSpacesBySkillRequest(
                SkillId=skill_id, PageNumber=page, PageSize=100
            )
        )
        items = result.items or []
        for relation in items:
            if relation.skill_space_id in checked:
                continue
            checked.add(relation.skill_space_id)
            require_space_write(client, relation.skill_space_id, is_admin=is_admin)
        if len(items) < 100 or page * 100 >= (result.total_count or 0):
            break
        page += 1
