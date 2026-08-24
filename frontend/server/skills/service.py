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

"""Skill management workflow rules independent from FastAPI and the SDK."""

from __future__ import annotations

from .archive import validate_skill_archive
from .models import CreateSkillSpaceBody, SkillIdentity, UpdateSkillSpaceBody
from .repository import AgentKitSkillRepository


class SkillService:
    def __init__(self, repository: AgentKitSkillRepository) -> None:
        self._repository = repository

    def list_spaces(
        self,
        identity: SkillIdentity,
        *,
        region: str,
        page: int,
        page_size: int,
        project_name: str | None,
    ) -> dict[str, object]:
        return self._repository.list_spaces(
            region=region,
            page=page,
            page_size=page_size,
            project_name=project_name,
            author=None if identity.is_admin else identity.author,
        )

    def create_space(
        self,
        identity: SkillIdentity,
        body: CreateSkillSpaceBody,
    ) -> dict[str, object]:
        return self._repository.create_space(
            region=body.region,
            name=body.name,
            description=body.description,
            project_name=body.project_name,
            author=identity.author,
        )

    def update_space(
        self,
        identity: SkillIdentity,
        space_id: str,
        body: UpdateSkillSpaceBody,
    ) -> dict[str, object]:
        del identity  # Filtering is intentionally not an ownership ACL.
        return self._repository.update_space(
            region=body.region,
            space_id=space_id,
            name=body.name,
            description=body.description,
        )

    def delete_space(
        self,
        identity: SkillIdentity,
        *,
        region: str,
        space_id: str,
    ) -> None:
        del identity  # Filtering is intentionally not an ownership ACL.
        self._repository.delete_space(region=region, space_id=space_id)

    def upload_skill(
        self,
        identity: SkillIdentity,
        *,
        region: str,
        project_name: str | None,
        space_id: str,
        content: bytes,
    ) -> dict[str, object]:
        archive = validate_skill_archive(content)
        return self._repository.publish_archive(
            region=region,
            project_name=project_name,
            space_id=space_id,
            archive=archive,
            author=identity.author,
        )

    def validate_archive(
        self,
        identity: SkillIdentity,
        content: bytes,
    ) -> dict[str, object]:
        del identity
        archive = validate_skill_archive(content)
        return {
            "valid": True,
            "name": archive.name,
            "description": archive.description,
            "files": archive.files,
        }

    def delete_skill(
        self,
        identity: SkillIdentity,
        *,
        region: str,
        skill_id: str,
    ) -> None:
        del identity  # Filtering is intentionally not an ownership ACL.
        self._repository.delete_skill(region=region, skill_id=skill_id)

    def skill_files(
        self,
        identity: SkillIdentity,
        *,
        region: str,
        space_id: str,
        skill_id: str,
        version: str | None,
        skill_space_name: str | None = None,
        skill_name: str | None = None,
    ) -> dict[str, object]:
        del identity
        return self._repository.skill_files(
            region=region,
            space_id=space_id,
            skill_id=skill_id,
            version=version,
            skill_space_name=skill_space_name,
            skill_name=skill_name,
        )

    def skill_archive(
        self,
        identity: SkillIdentity,
        *,
        region: str,
        space_id: str,
        skill_id: str,
        version: str | None,
        skill_space_name: str | None = None,
        skill_name: str | None = None,
    ) -> tuple[bytes, str]:
        del identity
        return self._repository.skill_archive(
            region=region,
            space_id=space_id,
            skill_id=skill_id,
            version=version,
            skill_space_name=skill_space_name,
            skill_name=skill_name,
        )


__all__ = ["SkillService"]
