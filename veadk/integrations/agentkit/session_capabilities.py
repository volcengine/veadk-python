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

"""Session-scoped tool and skill overlays for AgentKit applications."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, FastAPI, HTTPException, Query
from google.adk.agents.base_agent import BaseAgent
from google.adk.events import Event, EventActions
from google.adk.sessions import BaseSessionService, Session
from google.adk.tools.skill_toolset import SkillToolset
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from veadk.agent_metadata import agent_skill_summaries
from veadk.tools import get_builtin_tool, list_builtin_tools

SESSION_CAPABILITIES_STATE_KEY = "__agentkit_harness__"
SESSION_CAPABILITIES_SCHEMA_VERSION = 1
FINDSKILL_SOURCE_PREFIX = "findskill:"
FINDSKILL_SEARCH_URL = os.getenv(
    "FINDSKILL_SEARCH_URL", "https://skills.volces.com/v1/skills"
)


class StoredTool(BaseModel):
    """A lazily resolved built-in tool reference."""

    ref: str


class StoredSkill(BaseModel):
    """A lazily resolved remote skill reference."""

    id: str
    skill_source_id: str
    name: str
    description: str = ""
    version: str = ""


class SessionCapabilityOverlay(BaseModel):
    """The versioned value persisted in ``Session.state``."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = SESSION_CAPABILITIES_SCHEMA_VERSION
    revision: int = 0
    tools: list[StoredTool] = Field(default_factory=list)
    skills: list[StoredSkill] = Field(default_factory=list)


class AddCapabilityRequest(BaseModel):
    """Add one built-in tool or one remote skill to a session."""

    kind: Literal["tool", "skill"]
    name: str
    skill_source_id: str | None = None
    description: str = ""
    version: str = ""
    expected_revision: int | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> AddCapabilityRequest:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("name is required")
        if self.kind == "skill":
            self.skill_source_id = (self.skill_source_id or "").strip()
            if not self.skill_source_id:
                raise ValueError("skill_source_id is required for a skill")
        return self


class CapabilityItem(BaseModel):
    id: str
    kind: Literal["tool", "skill"]
    name: str
    custom: bool
    description: str = ""
    skill_source_id: str | None = None
    version: str = ""


class SessionCapabilitiesResponse(BaseModel):
    schema_version: int
    revision: int
    tools: list[CapabilityItem]
    skills: list[CapabilityItem]


class CapabilityError(Exception):
    status_code = 400


class SessionNotFoundError(CapabilityError):
    status_code = 404


class CapabilityConflictError(CapabilityError):
    status_code = 409


def _tool_name(tool: object) -> str:
    name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
    return str(name or type(tool).__name__)


def _skill_id(skill_source_id: str, name: str) -> str:
    digest = hashlib.sha256(f"{skill_source_id}\0{name}".encode()).hexdigest()[:16]
    return f"session:skill:{digest}"


async def _load_remote_skill(
    skill_source_id: str,
    name: str,
    version: str = "",
) -> object:
    if skill_source_id.startswith(FINDSKILL_SOURCE_PREFIX):
        slug = skill_source_id.removeprefix(FINDSKILL_SOURCE_PREFIX).strip("/")
        if not slug:
            raise CapabilityError("FindSkill slug is empty.")
        return await asyncio.to_thread(
            _load_findskill_skill,
            slug,
            name,
            version,
        )

    from veadk.skills.registry import VeSkillRegistry

    registry = VeSkillRegistry(skill_source_id=skill_source_id)
    return await registry.get_skill(name=name)


def _load_findskill_skill(slug: str, name: str, version: str) -> object:
    from google.adk.skills import load_skill_from_dir

    from veadk.cloud.harness_app.utils import _download_and_extract_skill

    cache_key = hashlib.sha256(f"{slug}\0{version}".encode()).hexdigest()[:16]
    cache_dir = Path(tempfile.gettempdir()) / "veadk" / "session-skills" / cache_key
    expected_dir = cache_dir / name
    if (expected_dir / "SKILL.md").is_file() or (expected_dir / "skill.md").is_file():
        return load_skill_from_dir(expected_dir)

    cache_dir.mkdir(parents=True, exist_ok=True)
    return load_skill_from_dir(_download_and_extract_skill(slug, cache_dir))


async def _search_findskill(
    *,
    query: str,
    page_number: int,
    page_size: int,
) -> dict[str, Any]:
    import httpx

    params: dict[str, str | int] = {
        "pageNumber": page_number,
        "pageSize": page_size,
    }
    if query.strip():
        params["query"] = query.strip()
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(FINDSKILL_SEARCH_URL, params=params)
        response.raise_for_status()
    payload = response.json()
    raw_items = payload.get("Skills", []) if isinstance(payload, dict) else []
    items = []
    for raw in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("Slug") or "").strip("/")
        name = str(raw.get("Name") or "").strip()
        if not slug or not name:
            continue
        metadata = raw.get("Metadata") if isinstance(raw.get("Metadata"), dict) else {}
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
                    metadata.get("DisplayDescription") or raw.get("Description") or ""
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


def _skill_catalog_client(region: str) -> Any:
    from agentkit.sdk.skills.client import AgentkitSkillsClient

    from veadk.skills.utils import _get_cloud_credentials

    access_key, secret_key, session_token = _get_cloud_credentials()
    return AgentkitSkillsClient(
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        session_token=session_token,
    )


async def _list_skill_spaces(region: str) -> dict[str, Any]:
    from agentkit.sdk.skills.types import ListSkillSpacesRequest

    regions = ["cn-beijing", "cn-shanghai"] if region == "all" else [region]
    items: list[dict[str, Any]] = []
    for current_region in regions:
        client = _skill_catalog_client(current_region)
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
    return {"items": items, "totalCount": len(items)}


async def _list_skills_in_space(
    *,
    space_id: str,
    region: str,
) -> dict[str, Any]:
    from agentkit.sdk.skills.types import ListSkillsBySkillSpaceRequest

    client = _skill_catalog_client(region)
    response = await asyncio.to_thread(
        client.list_skills_by_skill_space,
        ListSkillsBySkillSpaceRequest(
            SkillSpaceId=space_id,
            PageNumber=1,
            PageSize=100,
        ),
    )
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


class SessionCapabilityService:
    """Persist capability overlays and assemble an agent for a single run."""

    def __init__(
        self,
        *,
        root_agent: BaseAgent,
        session_service: BaseSessionService,
    ) -> None:
        self.root_agent = root_agent
        self.session_service = session_service

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> Session:
        session = await self.session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        if session is None:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return session

    def overlay_from_session(self, session: Session) -> SessionCapabilityOverlay:
        raw = (session.state or {}).get(SESSION_CAPABILITIES_STATE_KEY)
        if raw is None:
            return SessionCapabilityOverlay()
        try:
            overlay = SessionCapabilityOverlay.model_validate(raw)
        except ValidationError as exc:
            raise CapabilityConflictError(
                "The session capability configuration is invalid."
            ) from exc
        if overlay.schema_version != SESSION_CAPABILITIES_SCHEMA_VERSION:
            raise CapabilityConflictError(
                f"Unsupported capability schema version: {overlay.schema_version}"
            )
        return overlay

    async def get_capabilities(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> SessionCapabilitiesResponse:
        session = await self.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        return self._response(self.overlay_from_session(session))

    async def add_capability(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        request: AddCapabilityRequest,
    ) -> SessionCapabilitiesResponse:
        session = await self.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        overlay = self.overlay_from_session(session)
        self._check_revision(overlay, request.expected_revision)

        if request.kind == "tool":
            self._add_tool(overlay, request.name)
        else:
            self._add_skill(overlay, request)

        overlay.revision += 1
        await self._persist(session, overlay)
        return self._response(overlay)

    async def remove_capability(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        capability_id: str,
        expected_revision: int | None = None,
    ) -> SessionCapabilitiesResponse:
        session = await self.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        overlay = self.overlay_from_session(session)
        self._check_revision(overlay, expected_revision)

        if capability_id.startswith("base:"):
            raise CapabilityConflictError("Base capabilities cannot be removed.")

        before = len(overlay.tools) + len(overlay.skills)
        overlay.tools = [
            tool
            for tool in overlay.tools
            if f"session:tool:{tool.ref.removeprefix('builtin:')}" != capability_id
        ]
        overlay.skills = [
            skill for skill in overlay.skills if skill.id != capability_id
        ]
        if len(overlay.tools) + len(overlay.skills) == before:
            raise SessionNotFoundError(f"Capability not found: {capability_id}")

        overlay.revision += 1
        await self._persist(session, overlay)
        return self._response(overlay)

    async def build_agent(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> BaseAgent:
        session = await self.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        overlay = self.overlay_from_session(session)
        agent = self.root_agent.clone(update={})

        agent_tools = getattr(agent, "tools", None)
        if agent_tools is None and (overlay.tools or overlay.skills):
            raise CapabilityConflictError(
                "Session capabilities can only be mounted on an agent with tools."
            )
        if agent_tools is None:
            agent_tools = []
        existing_tools = {_tool_name(tool) for tool in agent_tools}
        for stored_tool in overlay.tools:
            name = stored_tool.ref.removeprefix("builtin:")
            if name not in existing_tools:
                agent_tools.append(get_builtin_tool(name))
                existing_tools.add(name)

        generation_hints = []
        if "ppt_generate" in existing_tools:
            generation_hints.append(
                "A PowerPoint generation tool is mounted for this session. "
                "When the user requests a presentation, plan concise "
                "audience-facing slide content and call `ppt_generate`; do "
                "not merely describe the deck. Include source URLs per slide "
                "when external claims or assets are used."
            )
        if "image_generate" in existing_tools:
            generation_hints.append(
                "An image generation tool is mounted for this session. When "
                "the user requests an image, call `image_generate`; do not "
                "claim that image generation is unavailable."
            )
        if "video_generate" in existing_tools:
            generation_hints.append(
                "Video generation tools are mounted for this session. When "
                "the user requests a video, call `video_generate` and use "
                "`video_task_query` when the result requires status polling; "
                "do not claim that video generation is unavailable."
            )
        if generation_hints:
            instruction = getattr(agent, "instruction", None)
            if isinstance(instruction, str):
                hint = "\n\n".join(generation_hints)
                setattr(
                    agent,
                    "instruction",
                    f"{instruction.rstrip()}\n\n{hint}"
                    if instruction.strip()
                    else hint,
                )

        loaded_skills = []
        for stored_skill in overlay.skills:
            loaded_skills.append(
                await _load_remote_skill(
                    stored_skill.skill_source_id,
                    stored_skill.name,
                    stored_skill.version,
                )
            )
        if loaded_skills:
            agent_tools.append(SkillToolset(skills=loaded_skills))
            instruction = getattr(agent, "instruction", None)
            if isinstance(instruction, str):
                skill_names = ", ".join(
                    f"`{getattr(skill, 'name', stored.name)}`"
                    for skill, stored in zip(loaded_skills, overlay.skills)
                )
                skill_hint = (
                    "Session-mounted skills available in this conversation: "
                    f"{skill_names}. Before calling load_skill, call list_skills "
                    "and pass the exact skill name it returns; do not abbreviate "
                    "or translate the name."
                )
                setattr(
                    agent,
                    "instruction",
                    f"{instruction.rstrip()}\n\n{skill_hint}"
                    if instruction.strip()
                    else skill_hint,
                )
        return agent

    def _base_tool_names(self) -> list[str]:
        return sorted(
            {_tool_name(tool) for tool in getattr(self.root_agent, "tools", None) or []}
        )

    def _base_skills(self) -> list[dict[str, str]]:
        return agent_skill_summaries(self.root_agent)

    def _response(
        self, overlay: SessionCapabilityOverlay
    ) -> SessionCapabilitiesResponse:
        tools = [
            CapabilityItem(
                id=f"base:tool:{name}",
                kind="tool",
                name=name,
                custom=False,
            )
            for name in self._base_tool_names()
        ]
        tools.extend(
            CapabilityItem(
                id=f"session:tool:{tool.ref.removeprefix('builtin:')}",
                kind="tool",
                name=tool.ref.removeprefix("builtin:"),
                custom=True,
            )
            for tool in overlay.tools
        )

        skills = [
            CapabilityItem(
                id=f"base:skill:{skill['name']}",
                kind="skill",
                name=skill["name"],
                description=skill.get("description", ""),
                custom=False,
            )
            for skill in self._base_skills()
        ]
        skills.extend(
            CapabilityItem(
                id=skill.id,
                kind="skill",
                name=skill.name,
                description=skill.description,
                skill_source_id=skill.skill_source_id,
                version=skill.version,
                custom=True,
            )
            for skill in overlay.skills
        )
        return SessionCapabilitiesResponse(
            schema_version=overlay.schema_version,
            revision=overlay.revision,
            tools=tools,
            skills=skills,
        )

    def _add_tool(self, overlay: SessionCapabilityOverlay, name: str) -> None:
        if name not in list_builtin_tools():
            raise CapabilityError(f"Unknown built-in tool: {name}")
        if name in self._base_tool_names():
            raise CapabilityConflictError(
                f"Tool is already provided by the base agent: {name}"
            )
        ref = f"builtin:{name}"
        if any(tool.ref == ref for tool in overlay.tools):
            raise CapabilityConflictError(f"Tool is already mounted: {name}")
        overlay.tools.append(StoredTool(ref=ref))

    def _add_skill(
        self,
        overlay: SessionCapabilityOverlay,
        request: AddCapabilityRequest,
    ) -> None:
        base_skill_names = {skill["name"] for skill in self._base_skills()}
        if request.name in base_skill_names:
            raise CapabilityConflictError(
                f"Skill is already provided by the base agent: {request.name}"
            )
        if any(skill.name == request.name for skill in overlay.skills):
            raise CapabilityConflictError(f"Skill is already mounted: {request.name}")
        skill_source_id = request.skill_source_id or ""
        overlay.skills.append(
            StoredSkill(
                id=_skill_id(skill_source_id, request.name),
                skill_source_id=skill_source_id,
                name=request.name,
                description=request.description.strip(),
                version=request.version.strip(),
            )
        )

    @staticmethod
    def _check_revision(
        overlay: SessionCapabilityOverlay,
        expected_revision: int | None,
    ) -> None:
        if expected_revision is not None and expected_revision != overlay.revision:
            raise CapabilityConflictError(
                f"Capability revision changed: expected {expected_revision}, "
                f"current {overlay.revision}"
            )

    async def _persist(
        self,
        session: Session,
        overlay: SessionCapabilityOverlay,
    ) -> None:
        event = Event(
            invocation_id=f"harness-config-{uuid4().hex}",
            author=str(getattr(self.root_agent, "name", "") or "system"),
            actions=EventActions(
                state_delta={
                    SESSION_CAPABILITIES_STATE_KEY: overlay.model_dump(mode="json")
                }
            ),
        )
        await self.session_service.append_event(session, event)


def mount_session_capability_routes(
    *,
    app: FastAPI,
    service: SessionCapabilityService | None = None,
    service_resolver: Callable[[str], Awaitable[SessionCapabilityService]]
    | None = None,
) -> None:
    """Mount the capability management API under the reserved harness prefix."""

    if service is None and service_resolver is None:
        raise ValueError("service or service_resolver is required")

    async def resolve_service(app_name: str) -> SessionCapabilityService:
        if service is not None:
            return service
        assert service_resolver is not None
        return await service_resolver(app_name)

    router = APIRouter(prefix="/harness")

    @router.get("/capabilities/tools")
    async def list_tools() -> dict[str, list[dict[str, str]]]:
        return {
            "tools": [
                {"name": name, "ref": f"builtin:{name}"}
                for name in list_builtin_tools()
            ]
        }

    @router.get("/skills/spaces")
    async def list_skill_spaces(region: str = "all") -> dict[str, Any]:
        try:
            return await _list_skill_spaces(region)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=409,
                detail="服务端未配置火山引擎凭证，无法读取 Skill Hub。",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="暂时无法加载 Skill Space，请稍后重试。",
            ) from exc

    @router.get("/skills/findskill")
    async def search_findskill(
        query: str = "",
        page_number: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=50),
    ) -> dict[str, Any]:
        try:
            return await _search_findskill(
                query=query,
                page_number=page_number,
                page_size=page_size,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="暂时无法搜索 Skill Hub，请稍后重试。",
            ) from exc

    @router.get("/skills/spaces/{space_id}/skills")
    async def list_skills_in_space(
        space_id: str,
        region: str = "cn-beijing",
    ) -> dict[str, Any]:
        try:
            return await _list_skills_in_space(
                space_id=space_id,
                region=region,
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=409,
                detail="服务端未配置火山引擎凭证，无法读取 Skill Hub。",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="暂时无法加载该 Skill Space 的技能，请稍后重试。",
            ) from exc

    @router.get("/apps/{app_name}/users/{user_id}/sessions/{session_id}/capabilities")
    async def get_capabilities(
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> SessionCapabilitiesResponse:
        resolved_service = await resolve_service(app_name)
        return await _translate_errors(
            resolved_service.get_capabilities(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
            )
        )

    @router.post("/apps/{app_name}/users/{user_id}/sessions/{session_id}/capabilities")
    async def add_capability(
        app_name: str,
        user_id: str,
        session_id: str,
        request: AddCapabilityRequest,
    ) -> SessionCapabilitiesResponse:
        resolved_service = await resolve_service(app_name)
        return await _translate_errors(
            resolved_service.add_capability(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                request=request,
            )
        )

    @router.delete(
        "/apps/{app_name}/users/{user_id}/sessions/{session_id}/capabilities/{capability_id}"
    )
    async def remove_capability(
        app_name: str,
        user_id: str,
        session_id: str,
        capability_id: str,
        expected_revision: int | None = Query(default=None),
    ) -> SessionCapabilitiesResponse:
        resolved_service = await resolve_service(app_name)
        return await _translate_errors(
            resolved_service.remove_capability(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                capability_id=capability_id,
                expected_revision=expected_revision,
            )
        )

    app.include_router(router)


async def _translate_errors(awaitable: Any) -> Any:
    try:
        return await awaitable
    except CapabilityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
