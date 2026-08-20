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

from __future__ import annotations

import pytest

from frontend.server.studio_routes.registry import (
    StudioRouteRegistry,
    build_studio_route_registry,
)
from frontend.server.studio_routes.skill_catalog import StudioSkillCatalog


class _FakeCatalog(StudioSkillCatalog):
    def __init__(self) -> None:
        super().__init__("volcengine")
        self.calls: list[tuple[object, ...]] = []

    async def search_findskill(
        self,
        *,
        query: str,
        page_number: int,
        page_size: int,
    ) -> dict[str, object]:
        self.calls.append(("findskill", query, page_number, page_size))
        return {"items": [{"slug": "volcengine/example"}], "totalCount": 1}

    async def list_spaces(self, *, region: str) -> dict[str, object]:
        self.calls.append(("spaces", region))
        return {"items": [{"id": "space-1"}], "totalCount": 1}

    async def list_skills(
        self,
        *,
        space_id: str,
        region: str,
    ) -> dict[str, object]:
        self.calls.append(("skills", space_id, region))
        return {"items": [{"skillId": "skill-1"}], "totalCount": 1}


def _route_revision(registry: StudioRouteRegistry, route_id: str) -> str:
    manifests = registry.manifests()
    return next(
        item["handler_revision"] for item in manifests if item["id"] == route_id
    )


@pytest.mark.asyncio
async def test_skill_catalog_registry_executes_all_three_migrated_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VEADK_STUDIO_ROUTE_CHANNEL", "skill-catalog")
    catalog = _FakeCatalog()
    registry = build_studio_route_registry(skill_catalog=catalog)

    assert [(item["method"], item["path"]) for item in registry.manifests()] == [
        ("GET", "/harness/skills/findskill"),
        ("GET", "/harness/skills/spaces"),
        ("GET", "/harness/skills/spaces/{space_id}/skills"),
    ]

    findskill = await registry.execute(
        route_id="studio_findskill",
        handler_revision=_route_revision(registry, "studio_findskill"),
        request={"query_string": "query=pdf&page_number=2&page_size=10"},
    )
    spaces = await registry.execute(
        route_id="studio_list_skill_spaces",
        handler_revision=_route_revision(registry, "studio_list_skill_spaces"),
        request={"query_string": "region=cn-shanghai"},
    )
    skills = await registry.execute(
        route_id="studio_list_skills_in_space",
        handler_revision=_route_revision(registry, "studio_list_skills_in_space"),
        request={
            "query_string": "region=cn-beijing",
            "path_params": {"space_id": "space-1"},
        },
    )

    assert findskill.body["items"][0]["slug"] == "volcengine/example"
    assert spaces.body["items"][0]["id"] == "space-1"
    assert skills.body["items"][0]["skillId"] == "skill-1"
    assert catalog.calls == [
        ("findskill", "pdf", 2, 10),
        ("spaces", "cn-shanghai"),
        ("skills", "space-1", "cn-beijing"),
    ]


@pytest.mark.asyncio
async def test_skill_catalog_registry_returns_validation_error_as_http_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VEADK_STUDIO_ROUTE_CHANNEL", "skill-catalog")
    registry = build_studio_route_registry(skill_catalog=_FakeCatalog())

    response = await registry.execute(
        route_id="studio_findskill",
        handler_revision=_route_revision(registry, "studio_findskill"),
        request={"query_string": "page_size=invalid"},
    )

    assert response.status == 400
    assert response.body == {"detail": "invalid integer query parameter: page_size"}
