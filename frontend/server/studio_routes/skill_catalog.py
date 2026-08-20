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

"""Studio-owned read-only Skill catalog used by reverse HTTP routes."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import httpx

from frontend.server.skills.storage import resolve_skill_publish_credentials
from frontend.server.storage import StudioProvider

FINDSKILL_SEARCH_URL = os.getenv(
    "FINDSKILL_SEARCH_URL",
    "https://skills.volces.com/v1/skills",
)
_REGION_PATTERN = re.compile(r"^[a-z]{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")


class StudioSkillCatalogError(RuntimeError):
    """A sanitized Skill catalog failure safe to return through Runtime."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class StudioSkillCatalog:
    """Query public and account Skill catalogs with Studio-side credentials."""

    def __init__(self, provider: StudioProvider = "volcengine") -> None:
        self.provider = provider

    def regions(self, requested: str) -> list[str]:
        candidate = requested.strip()
        if candidate in {"", "all", "*"}:
            if self.provider == "byteplus":
                return [os.getenv("BYTEPLUS_REGION") or "ap-southeast-1"]
            return ["cn-beijing", "cn-shanghai"]
        if len(candidate) > 64 or not _REGION_PATTERN.fullmatch(candidate):
            raise StudioSkillCatalogError(400, "invalid Skill catalog region")
        if self.provider == "byteplus" and not candidate.startswith("ap-"):
            raise StudioSkillCatalogError(400, "invalid BytePlus Skill catalog region")
        if self.provider == "volcengine" and not candidate.startswith("cn-"):
            raise StudioSkillCatalogError(
                400,
                "invalid Volcengine Skill catalog region",
            )
        return [candidate]

    def _client(self, region: str) -> Any:
        from agentkit.sdk.skills.client import AgentkitSkillsClient

        try:
            credentials = resolve_skill_publish_credentials(provider=self.provider)
        except Exception as error:
            raise StudioSkillCatalogError(
                409,
                "Studio cloud credentials are not configured for Skill catalog access.",
            ) from error
        return AgentkitSkillsClient(
            access_key=credentials.access_key,
            secret_key=credentials.secret_key,
            region=region,
            session_token=credentials.session_token,
        )

    async def list_spaces(self, *, region: str) -> dict[str, Any]:
        from agentkit.sdk.skills.types import ListSkillSpacesRequest

        items: list[dict[str, Any]] = []
        try:
            for current_region in self.regions(region):
                client = self._client(current_region)
                response = await asyncio.to_thread(
                    client.list_skill_spaces,
                    ListSkillSpacesRequest(PageNumber=1, PageSize=100),
                )
                for space in response.items or []:
                    items.append(
                        {
                            "id": space.id or "",
                            "name": space.name or "",
                            "description": space.description or "",
                            "status": space.status or "",
                            "region": current_region,
                            "projectName": space.project_name or "",
                            "updatedAt": space.update_time_stamp or "",
                            "skillCount": len(space.relations or []),
                        }
                    )
        except StudioSkillCatalogError:
            raise
        except Exception as error:
            raise StudioSkillCatalogError(
                502,
                "Studio could not load Skill Spaces.",
            ) from error
        return {"items": items, "totalCount": len(items)}

    async def list_skills(
        self,
        *,
        space_id: str,
        region: str,
    ) -> dict[str, Any]:
        from agentkit.sdk.skills.types import ListSkillsBySkillSpaceRequest

        if not re.fullmatch(r"[A-Za-z0-9._~-]{1,256}", space_id):
            raise StudioSkillCatalogError(400, "invalid Skill Space id")
        resolved_region = self.regions(region)[0]
        try:
            response = await asyncio.to_thread(
                self._client(resolved_region).list_skills_by_skill_space,
                ListSkillsBySkillSpaceRequest(
                    SkillSpaceId=space_id,
                    PageNumber=1,
                    PageSize=100,
                ),
            )
        except StudioSkillCatalogError:
            raise
        except Exception as error:
            raise StudioSkillCatalogError(
                502,
                "Studio could not load Skills from this Skill Space.",
            ) from error
        items = list(response.items or [])
        return {
            "items": [
                {
                    "skillId": skill.skill_id or "",
                    "skillName": skill.skill_name or "",
                    "skillDescription": skill.skill_description or "",
                    "version": skill.version or "",
                    "skillStatus": skill.skill_status or "",
                }
                for skill in items
            ],
            "totalCount": (
                response.total_count if response.total_count is not None else len(items)
            ),
        }

    async def search_findskill(
        self,
        *,
        query: str,
        page_number: int,
        page_size: int,
    ) -> dict[str, Any]:
        if page_number < 1 or not 1 <= page_size <= 50:
            raise StudioSkillCatalogError(400, "invalid FindSkill pagination")
        params: dict[str, str | int] = {
            "pageNumber": page_number,
            "pageSize": page_size,
        }
        if query.strip():
            params["query"] = query.strip()
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                response = await client.get(FINDSKILL_SEARCH_URL, params=params)
                response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise StudioSkillCatalogError(
                502,
                "Studio could not search the public Skill catalog.",
            ) from error
        raw_items = payload.get("Skills", []) if isinstance(payload, dict) else []
        items = []
        for raw in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(raw, dict):
                continue
            slug = str(raw.get("Slug") or "").strip("/")
            name = str(raw.get("Name") or "").strip()
            if not slug or not name:
                continue
            metadata = (
                raw.get("Metadata") if isinstance(raw.get("Metadata"), dict) else {}
            )
            evaluation = (
                raw.get("EvaluationMetadata")
                if isinstance(raw.get("EvaluationMetadata"), dict)
                else {}
            )
            items.append(
                {
                    "slug": slug,
                    "name": name,
                    "description": str(
                        metadata.get("DisplayDescription")
                        or raw.get("Description")
                        or ""
                    ),
                    "sourceType": str(raw.get("SourceType") or ""),
                    "sourceRepo": str(raw.get("SourceRepo") or ""),
                    "downloadCount": int(raw.get("DownloadCount") or 0),
                    "evaluationScore": float(raw.get("EvaluationScore") or 0),
                    "version": str(evaluation.get("skill_version") or ""),
                    "updatedAt": str(raw.get("UpdatedAt") or ""),
                }
            )
        total = (
            int(payload.get("Total") or len(items))
            if isinstance(payload, dict)
            else len(items)
        )
        return {"items": items, "totalCount": total}


__all__ = [
    "StudioSkillCatalog",
    "StudioSkillCatalogError",
]
