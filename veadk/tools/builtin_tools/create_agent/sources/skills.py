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
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from veadk.skills.skill import Skill
from veadk.skills.utils import load_skills_from_cloud
from veadk.tools.builtin_tools.create_agent.models import (
    ResourceDescriptor,
    ResourceSourceStatus,
)
from veadk.tools.builtin_tools.create_agent.resource_store import StoredResource
from veadk.tools.builtin_tools.create_agent.sources.cloud import (
    CloudCredentials,
    default_agentkit_region,
    resolve_cloud_credentials,
)
from veadk.tools.builtin_tools.create_agent.sources.base import SourceCollection
from veadk.utils.cloud_provider import cloud_provider_from_env
from veadk.utils.http_defaults import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
)

FINDSKILL_SEARCH_URL = os.getenv(
    "FINDSKILL_SEARCH_URL",
    "https://skills.volces.com/v1/skills",
)
FindSkillSearcher = Callable[[str], Awaitable[dict[str, Any]]]
_PAGE_SIZE = 100
_MAX_PAGES = 100
# Wall-clock ceiling for one sweep: spaces are paginated, then every space is
# paginated again. A per-request timeout bounds one call, not the fan-out.
_SWEEP_DEADLINE_SECONDS = 120.0


@dataclass(frozen=True)
class _AgentKitSkillSpace:
    id: str
    name: str
    project_name: str


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


class AgentKitSkillCenterSource:
    """Enumerate Skills from every accessible AgentKit Skill Space."""

    name = "skill_space:agentkit"

    def __init__(
        self,
        space_ids: Sequence[str] | None = None,
        *,
        region: str | None = None,
        client_factory=None,
        credential_resolver=None,
        max_concurrency: int = 2,
    ) -> None:
        self.space_ids = tuple(
            dict.fromkeys(
                str(space_id).strip()
                for space_id in space_ids or ()
                if str(space_id).strip()
            )
        )
        self.region = region or default_agentkit_region()
        self._client_factory = client_factory or _default_agentkit_client_factory
        self._credential_resolver = credential_resolver or resolve_cloud_credentials
        self._max_concurrency = max(1, max_concurrency)

    async def collect(self, tool_context: Any = None) -> SourceCollection:
        try:
            credentials = await asyncio.to_thread(
                self._credential_resolver, tool_context
            )
        except Exception as exc:
            return self._status("skipped", f"Credentials unavailable: {exc}")
        if credentials is None:
            return self._status("skipped", "AK/SK or STS credentials are unavailable.")

        # Per call, never on `self`: one source object serves every session,
        # so overlapping sweeps would otherwise reset each other's deadline and
        # answer for each other's breach.
        deadline = time.monotonic() + _SWEEP_DEADLINE_SECONDS
        try:
            spaces, spaces_exceeded = await asyncio.to_thread(
                self._list_spaces, credentials, deadline
            )
            if self.space_ids:
                allowed = set(self.space_ids)
                spaces = [space for space in spaces if space.id in allowed]
            if spaces_exceeded:
                # The budget is already spent. Do not instantiate one client
                # per collected Space merely to have every worker rediscover
                # the same expired deadline.
                return self._status(
                    "error",
                    f"Sweep gave up after {_SWEEP_DEADLINE_SECONDS:.0f}s; "
                    "returning 0 Skill(s) collected so far.",
                )
            resources, skills_exceeded = await self._collect_space_skills(
                credentials, spaces, deadline
            )
            if skills_exceeded:
                return self._status(
                    "error",
                    f"Sweep gave up after {_SWEEP_DEADLINE_SECONDS:.0f}s; "
                    f"returning {len(resources)} Skill(s) collected so far.",
                    resources=resources,
                )
            return SourceCollection(
                resources=resources,
                status=ResourceSourceStatus(
                    source=self.name,
                    status="ok",
                    count=len(resources),
                ),
            )
        except Exception as exc:
            return self._status("error", str(exc))

    def _status(
        self,
        status: Literal["skipped", "error"],
        message: str,
        resources: Sequence[StoredResource] = (),
    ) -> SourceCollection:
        return SourceCollection(
            resources=list(resources),
            status=ResourceSourceStatus(
                source=self.name,
                status=status,
                count=len(resources),
                message=message,
            ),
        )

    def _list_spaces(
        self,
        credentials: CloudCredentials,
        deadline: float,
    ) -> tuple[list[_AgentKitSkillSpace], bool]:
        """Return the Spaces collected, and whether the deadline cut them short."""
        from agentkit.sdk.skills.types import ListSkillSpacesRequest

        client = self._client_factory(credentials, self.region)
        spaces: list[_AgentKitSkillSpace] = []
        seen_ids: set[str] = set()
        collected_count = 0
        deadline_exceeded = False
        for page in range(1, _MAX_PAGES + 1):
            if time.monotonic() >= deadline:
                # Abandon the remaining pages; `collect` reports the partial
                # result rather than passing it off as a complete listing.
                deadline_exceeded = True
                break
            response = client.list_skill_spaces(
                ListSkillSpacesRequest(PageNumber=page, PageSize=_PAGE_SIZE)
            )
            items = list(getattr(response, "items", None) or [])
            collected_count += len(items)
            for item in items:
                space_id = str(getattr(item, "id", "") or "").strip()
                if not space_id or space_id in seen_ids:
                    continue
                seen_ids.add(space_id)
                spaces.append(
                    _AgentKitSkillSpace(
                        id=space_id,
                        name=str(getattr(item, "name", "") or space_id),
                        project_name=str(getattr(item, "project_name", "") or ""),
                    )
                )
            # The last page can finish after the deadline and still advertise
            # no successor, so check the clock before reporting a complete list.
            if time.monotonic() >= deadline:
                deadline_exceeded = True
                break
            if not _has_next_page(
                response,
                collected_count=collected_count,
                item_count=len(items),
                page_size=_PAGE_SIZE,
            ):
                break
        else:
            raise RuntimeError("AgentKit Skill Space pagination exceeded 100 pages.")
        return spaces, deadline_exceeded

    async def _collect_space_skills(
        self,
        credentials: CloudCredentials,
        spaces: Sequence[_AgentKitSkillSpace],
        deadline: float,
    ) -> tuple[list[StoredResource], bool]:
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def collect_one(
            space: _AgentKitSkillSpace,
        ) -> tuple[list[StoredResource], bool]:
            if time.monotonic() >= deadline:
                return [], True
            async with semaphore:
                if time.monotonic() >= deadline:
                    return [], True
                return await asyncio.to_thread(
                    self._list_skills,
                    credentials,
                    space,
                    deadline,
                )

        results = await asyncio.gather(*(collect_one(space) for space in spaces))
        resources = [resource for group, _ in results for resource in group]
        return resources, any(exceeded for _, exceeded in results)

    def _list_skills(
        self,
        credentials: CloudCredentials,
        space: _AgentKitSkillSpace,
        deadline: float,
    ) -> tuple[list[StoredResource], bool]:
        """Return the Skills collected, and whether the deadline cut them short."""
        from agentkit.sdk.skills.types import ListSkillsBySkillSpaceRequest

        if time.monotonic() >= deadline:
            return [], True
        client = self._client_factory(credentials, self.region)
        resources: list[StoredResource] = []
        seen_ids: set[str] = set()
        collected_count = 0
        deadline_exceeded = False
        for page in range(1, _MAX_PAGES + 1):
            if time.monotonic() >= deadline:
                # Abandon the remaining pages; `collect` reports the partial
                # result rather than passing it off as a complete listing.
                deadline_exceeded = True
                break
            response = client.list_skills_by_skill_space(
                ListSkillsBySkillSpaceRequest(
                    SkillSpaceId=space.id,
                    PageNumber=page,
                    PageSize=_PAGE_SIZE,
                )
            )
            items = list(getattr(response, "items", None) or [])
            collected_count += len(items)
            for item in items:
                resource = self._to_agentkit_resource(item, space)
                if resource is None or resource.descriptor.ref in seen_ids:
                    continue
                seen_ids.add(resource.descriptor.ref)
                resources.append(resource)
            # Check after each blocking request as well as before it. Otherwise
            # a slow final page would be labelled complete after the budget.
            if time.monotonic() >= deadline:
                deadline_exceeded = True
                break
            if not _has_next_page(
                response,
                collected_count=collected_count,
                item_count=len(items),
                page_size=_PAGE_SIZE,
            ):
                break
        else:
            raise RuntimeError(
                f"AgentKit Skill pagination exceeded 100 pages for Space '{space.id}'."
            )
        return resources, deadline_exceeded

    def _to_agentkit_resource(
        self,
        item: Any,
        space: _AgentKitSkillSpace,
    ) -> StoredResource | None:
        skill_id = str(getattr(item, "skill_id", "") or "").strip()
        if not skill_id:
            return None
        name = str(getattr(item, "skill_name", "") or skill_id).strip()
        description = str(getattr(item, "skill_description", "") or "")
        version = str(getattr(item, "version", "") or "") or None
        source = f"skill_space:{space.id}"
        skill = Skill(
            name=name,
            description=description,
            path=skill_id,
            skill_space_id=space.id,
            id=skill_id,
            source_type="skillspace",
            version_id=version,
        )
        descriptor = ResourceDescriptor(
            ref=f"{space.id}:{skill_id}",
            kind="skill",
            name=name,
            description=description,
            source=source,
            version=version,
            metadata={
                "space_id": space.id,
                "space_name": space.name,
                "project_name": space.project_name,
                "skill_id": skill_id,
                "skill_status": str(getattr(item, "skill_status", "") or ""),
                "source_type": "skillspace",
                "region": self.region,
            },
        )
        return StoredResource(descriptor=descriptor, payload=skill)


def _default_agentkit_client_factory(
    credentials: CloudCredentials,
    region: str,
):
    from agentkit.platform.context import default_cloud_provider
    from agentkit.sdk.skills.client import AgentkitSkillsClient

    with default_cloud_provider(cloud_provider_from_env()):
        client = AgentkitSkillsClient(
            access_key=credentials.access_key,
            secret_key=credentials.secret_key,
            session_token=credentials.session_token,
            region=region,
        )
    # The client takes no timeout argument, but it subclasses the volcengine
    # `Service`, whose setters are re-read on every request. Guarded so an SDK
    # shape change degrades to the SDK default instead of raising.
    for setter, seconds in (
        ("set_connection_timeout", DEFAULT_CONNECT_TIMEOUT),
        ("set_socket_timeout", DEFAULT_READ_TIMEOUT),
    ):
        apply_timeout = getattr(client, setter, None)
        if callable(apply_timeout):
            apply_timeout(int(seconds))
    return client


def resolve_agentkit_skill(
    skill: Skill,
    *,
    credentials: CloudCredentials,
    region: str,
    skill_space_name: str | None = None,
    client_factory=None,
) -> Skill:
    """Resolve the storage metadata required to materialize one selected Skill."""
    from agentkit.sdk.skills.types import GetSkillInfoRequest, GetSkillVersionRequest

    if not skill.id:
        raise ValueError(f"AgentKit Skill '{skill.name}' has no Skill ID.")
    factory = client_factory or _default_agentkit_client_factory
    client = factory(credentials, region)
    try:
        response = client.get_skill_version(
            GetSkillVersionRequest(Id=skill.id, SkillVersion=skill.version_id)
        )
    except Exception as version_error:
        if (
            "interface type not consistent with skill type"
            not in str(version_error).casefold()
            or not skill.skill_space_id
            or not skill_space_name
        ):
            raise
        try:
            response = client.get_skill_info(
                GetSkillInfoRequest(
                    SkillName=skill.name,
                    SkillSpaceName=skill_space_name,
                    SkillSpaceId=skill.skill_space_id,
                )
            )
        except Exception as info_error:
            raise info_error from version_error
    bucket_name = str(getattr(response, "bucket_name", "") or "").strip()
    tos_path = str(getattr(response, "tos_path", "") or "").strip()
    if not bucket_name or not tos_path:
        raise ValueError(
            f"AgentKit Skill '{skill.name}' version metadata has no archive location."
        )
    return skill.model_copy(
        update={
            "name": str(getattr(response, "name", "") or skill.name),
            "description": str(
                getattr(response, "description", "") or skill.description
            ),
            "path": tos_path,
            "bucket_name": bucket_name,
            "version_id": str(
                getattr(response, "version", "") or skill.version_id or ""
            )
            or None,
        }
    )


def _has_next_page(
    response: Any,
    *,
    collected_count: int,
    item_count: int,
    page_size: int,
) -> bool:
    total_count = getattr(response, "total_count", None)
    if total_count is not None:
        try:
            return collected_count < int(total_count)
        except (TypeError, ValueError):
            pass
    return item_count >= page_size


def _version_from_path(path: str) -> str | None:
    parts = [part for part in path.split("/") if part]
    return parts[2] if len(parts) >= 3 else None
