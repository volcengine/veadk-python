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

"""Studio BFF-owned route declarations and local handler execution."""

from __future__ import annotations

import asyncio
import inspect
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

from frontend.server.storage import StudioProvider
from frontend.server.studio_routes.skill_catalog import (
    StudioSkillCatalog,
    StudioSkillCatalogError,
)
from veadk.integrations.agentkit.studio_routes import (
    StudioRouteManifest,
    route_catalog_revision,
)

RouteExecutor = Callable[[dict[str, Any]], Any]


class StudioRouteExecutionError(RuntimeError):
    """A safe BFF handler error that may cross the reverse-route channel."""


@dataclass(frozen=True)
class StudioRouteResponse:
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None


@dataclass(frozen=True)
class StudioRoute:
    id: str
    method: str
    path: str
    executor: RouteExecutor
    handler_revision: str = "v1"
    timeout_ms: int = 30_000
    response_mode: str = "json"

    def manifest(self) -> StudioRouteManifest:
        return StudioRouteManifest(
            id=self.id,
            method=self.method.upper(),
            path=self.path,
            handler_revision=self.handler_revision,
            timeout_ms=self.timeout_ms,
            response_mode=self.response_mode,
        )


class StudioRouteRegistry:
    """Own local route handlers; only declarative manifests leave the BFF."""

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], StudioRoute] = {}
        self._routes_by_id: dict[tuple[str, str], StudioRoute] = {}

    def register(self, route: StudioRoute) -> None:
        manifest = route.manifest()
        route_key = (manifest.method, manifest.path)
        id_key = (manifest.id, manifest.handler_revision)
        if route_key in self._routes:
            raise ValueError(
                f"Studio route already registered: {manifest.method} {manifest.path}"
            )
        if id_key in self._routes_by_id:
            raise ValueError(
                f"Studio route id already registered: "
                f"{manifest.id}@{manifest.handler_revision}"
            )
        self._routes[route_key] = route
        self._routes_by_id[id_key] = route

    def manifests(self) -> list[dict[str, Any]]:
        return [
            route.manifest().model_dump(mode="json")
            for _, route in sorted(self._routes.items())
        ]

    @property
    def revision(self) -> str:
        return route_catalog_revision(self.manifests())

    @property
    def enabled(self) -> bool:
        return bool(self._routes)

    async def execute(
        self,
        *,
        route_id: str,
        handler_revision: str,
        request: dict[str, Any],
    ) -> StudioRouteResponse:
        route = self._routes_by_id.get((route_id, handler_revision))
        if route is None:
            raise StudioRouteExecutionError(
                f"Studio route handler is unavailable: {route_id}@{handler_revision}"
            )
        if inspect.iscoroutinefunction(route.executor):
            result = await route.executor(request)
        else:
            result = await asyncio.to_thread(route.executor, request)
        if isinstance(result, StudioRouteResponse):
            return result
        return StudioRouteResponse(body=result)


def _query_values(request: dict[str, Any]) -> dict[str, list[str]]:
    raw_query = request.get("query_string")
    if not isinstance(raw_query, str):
        raise StudioSkillCatalogError(400, "invalid route query string")
    try:
        return parse_qs(
            raw_query,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=20,
        )
    except ValueError as error:
        raise StudioSkillCatalogError(400, "invalid route query string") from error


def _single_query(
    query: dict[str, list[str]],
    name: str,
    default: str,
) -> str:
    values = query.get(name)
    if not values:
        return default
    if len(values) != 1:
        raise StudioSkillCatalogError(400, f"duplicate query parameter: {name}")
    return values[0]


def _positive_int_query(
    query: dict[str, list[str]],
    name: str,
    default: int,
) -> int:
    raw_value = _single_query(query, name, str(default))
    try:
        return int(raw_value)
    except ValueError as error:
        raise StudioSkillCatalogError(
            400,
            f"invalid integer query parameter: {name}",
        ) from error


def _catalog_response(error: StudioSkillCatalogError) -> StudioRouteResponse:
    return StudioRouteResponse(
        status=error.status_code,
        headers={"content-type": "application/json"},
        body={"detail": error.detail},
    )


def _register_skill_catalog_routes(
    registry: StudioRouteRegistry,
    catalog: StudioSkillCatalog,
) -> None:
    async def findskill(request: dict[str, Any]) -> StudioRouteResponse:
        try:
            query = _query_values(request)
            body = await catalog.search_findskill(
                query=_single_query(query, "query", ""),
                page_number=_positive_int_query(query, "page_number", 1),
                page_size=_positive_int_query(query, "page_size", 20),
            )
        except StudioSkillCatalogError as error:
            return _catalog_response(error)
        return StudioRouteResponse(body=body)

    async def list_spaces(request: dict[str, Any]) -> StudioRouteResponse:
        try:
            query = _query_values(request)
            body = await catalog.list_spaces(
                region=_single_query(query, "region", "all"),
            )
        except StudioSkillCatalogError as error:
            return _catalog_response(error)
        return StudioRouteResponse(body=body)

    async def list_skills(request: dict[str, Any]) -> StudioRouteResponse:
        try:
            query = _query_values(request)
            path_params = request.get("path_params")
            if not isinstance(path_params, dict):
                raise StudioSkillCatalogError(400, "missing route path parameters")
            space_id = path_params.get("space_id")
            if not isinstance(space_id, str):
                raise StudioSkillCatalogError(400, "missing Skill Space id")
            body = await catalog.list_skills(
                space_id=space_id,
                region=_single_query(
                    query,
                    "region",
                    "ap-southeast-1"
                    if catalog.provider == "byteplus"
                    else "cn-beijing",
                ),
            )
        except StudioSkillCatalogError as error:
            return _catalog_response(error)
        return StudioRouteResponse(body=body)

    registry.register(
        StudioRoute(
            id="studio_findskill",
            method="GET",
            path="/harness/skills/findskill",
            executor=findskill,
            handler_revision="studio-skill-catalog-v1",
        )
    )
    registry.register(
        StudioRoute(
            id="studio_list_skill_spaces",
            method="GET",
            path="/harness/skills/spaces",
            executor=list_spaces,
            handler_revision="studio-skill-catalog-v1",
        )
    )
    registry.register(
        StudioRoute(
            id="studio_list_skills_in_space",
            method="GET",
            path="/harness/skills/spaces/{space_id}/skills",
            executor=list_skills,
            handler_revision="studio-skill-catalog-v1",
        )
    )


def build_studio_route_registry(
    *,
    provider: StudioProvider = "volcengine",
    skill_catalog: StudioSkillCatalog | None = None,
) -> StudioRouteRegistry:
    """Build the BFF route registry selected by server-owned configuration."""

    registry = StudioRouteRegistry()
    mode = os.getenv("VEADK_STUDIO_ROUTE_CHANNEL", "").strip().lower()
    if mode in {"1", "true", "yes", "demo", "skill-catalog"}:
        _register_skill_catalog_routes(
            registry,
            skill_catalog or StudioSkillCatalog(provider),
        )
    return registry
