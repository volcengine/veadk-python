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
import os
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import httpx

from veadk.skills.skill import Skill
from veadk.skills.utils import load_skills_from_cloud
from veadk.tools.builtin_tools.create_agent.models import (
    ResourceDescriptor,
    ResourceSourceStatus,
)
from veadk.tools.builtin_tools.create_agent.resource_store import StoredResource
from veadk.tools.builtin_tools.create_agent.sources.base import SourceCollection


FINDSKILL_SEARCH_URL = os.getenv(
    "FINDSKILL_SEARCH_URL",
    "https://skills.volces.com/v1/skills",
)
FindSkillSearcher = Callable[[str], Awaitable[dict[str, Any]]]


class SkillHubSearchSource:
    """Search the public Skill Hub with task-specific keywords."""

    name = "skill_hub:public"

    def __init__(
        self,
        keywords: Sequence[str],
        *,
        searcher: FindSkillSearcher | None = None,
    ) -> None:
        self.keywords = list(keywords)
        self._searcher = searcher or self._search

    async def collect(self, tool_context: Any = None) -> SourceCollection:
        del tool_context
        try:
            payloads = await asyncio.gather(
                *(self._searcher(keyword) for keyword in self.keywords)
            )
            resources_by_ref: dict[str, StoredResource] = {}
            for keyword, payload in zip(self.keywords, payloads):
                for item in _findskill_items(payload):
                    resource = self._to_resource(item, keyword)
                    if resource is not None:
                        resources_by_ref.setdefault(
                            resource.descriptor.ref,
                            resource,
                        )
            resources = list(resources_by_ref.values())
            return SourceCollection(
                resources=resources,
                status=ResourceSourceStatus(
                    source=self.name,
                    status="ok",
                    count=len(resources),
                    search_keywords=self.keywords,
                ),
            )
        except Exception as exc:
            return SourceCollection(
                status=ResourceSourceStatus(
                    source=self.name,
                    status="error",
                    message=str(exc),
                    search_keywords=self.keywords,
                )
            )

    async def _search(self, keyword: str) -> dict[str, Any]:
        params = {"query": keyword, "pageNumber": 1, "pageSize": 20}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(FINDSKILL_SEARCH_URL, params=params)
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Skill Hub returned an invalid response.")
        return payload

    def _to_resource(
        self,
        item: dict[str, Any],
        keyword: str,
    ) -> StoredResource | None:
        slug = _item_text(item, "Slug").strip("/")
        name = _item_text(item, "Name")
        if not slug or not name:
            return None
        metadata = item.get("Metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        evaluation = item.get("EvaluationMetadata")
        evaluation = evaluation if isinstance(evaluation, dict) else {}
        description = str(
            metadata.get("DisplayDescription") or item.get("Description") or ""
        )
        version = str(evaluation.get("skill_version") or "") or None
        descriptor = ResourceDescriptor(
            ref=f"skill_hub:{slug}",
            kind="skill",
            name=name,
            description=description,
            source=self.name,
            version=version,
            metadata={
                "slug": slug,
                "source_type": "skillhub",
                "matched_keyword": keyword,
            },
        )
        skill = Skill(
            name=name,
            description=description,
            path=slug,
            id=slug,
            slug=slug,
            source_type="findskill",
            version_id=version,
        )
        return StoredResource(descriptor=descriptor, payload=skill)


def _findskill_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = payload.get("Skills") or payload.get("Items") or payload.get("skills")
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, dict)]


def _item_text(item: dict[str, Any], key: str) -> str:
    value = item.get(key) or item.get(key.lower())
    return str(value or "").strip()


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
