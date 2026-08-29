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

"""Skill Hub and private Skill Space resource collection."""

from __future__ import annotations

import asyncio
from typing import Any

from veadk.skills.skill import Skill
from veadk.skills.utils import load_skills_from_cloud
from veadk.tools.builtin_tools.create_agent.models import (
    ResourceDescriptor,
    ResourceSourceStatus,
)
from veadk.tools.builtin_tools.create_agent.resource_store import StoredResource
from veadk.tools.builtin_tools.create_agent.sources.base import SourceCollection


class SkillResourceSource:
    """Enumerate one configured Skill Hub or private Skill Space."""

    def __init__(self, source_id: str) -> None:
        self.source_id = source_id
        self.name = (
            f"skill_hub:{source_id}"
            if source_id.startswith("sp-")
            else f"skill_space:{source_id}"
        )

    async def collect(self, tool_context: Any = None) -> SourceCollection:
        del tool_context
        try:
            skills = await asyncio.to_thread(
                load_skills_from_cloud,
                self.source_id,
                raise_on_error=True,
            )
            resources = [self._to_resource(skill) for skill in skills]
            return SourceCollection(
                resources=resources,
                status=ResourceSourceStatus(
                    source=self.name, status="ok", count=len(resources)
                ),
            )
        except Exception as exc:
            return SourceCollection(
                status=ResourceSourceStatus(
                    source=self.name,
                    status="error",
                    message=str(exc),
                )
            )

    def _to_resource(self, skill: Skill) -> StoredResource:
        skill_id = skill.id or skill.slug or skill.name
        ref = f"{self.source_id}:{skill_id}"
        version = skill.version_id or _version_from_path(skill.path)
        descriptor = ResourceDescriptor(
            ref=ref,
            kind="skill",
            name=skill.name,
            description=skill.description,
            source=self.name,
            version=version,
            metadata={
                "space_id": self.source_id,
                "skill_id": skill_id,
                "source_type": skill.source_type
                or ("skillhub" if self.source_id.startswith("sp-") else "skillspace"),
            },
        )
        return StoredResource(descriptor=descriptor, payload=skill)


def _version_from_path(path: str) -> str | None:
    parts = [part for part in path.split("/") if part]
    return parts[2] if len(parts) >= 3 else None
