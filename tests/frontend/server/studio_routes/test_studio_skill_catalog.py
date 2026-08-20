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

from types import SimpleNamespace
from typing import Any

import pytest

import frontend.server.studio_routes.skill_catalog as skill_catalog


@pytest.mark.asyncio
async def test_skill_catalog_lists_spaces_and_space_skills_from_studio_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self, region: str) -> None:
            self.region = region

        def list_skill_spaces(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        id=f"space-{self.region}",
                        name="Writers",
                        description="Writing skills",
                        status="active",
                        project_name="default",
                        update_time_stamp="2026-08-18",
                        relations=[object()],
                    )
                ]
            )

        def list_skills_by_skill_space(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                items=[
                    SimpleNamespace(
                        skill_id="skill-1",
                        skill_name="writer",
                        skill_description="Write content",
                        version="1.0.0",
                        skill_status="active",
                    )
                ],
                total_count=1,
            )

    catalog = skill_catalog.StudioSkillCatalog()
    monkeypatch.setattr(catalog, "_client", lambda region: FakeClient(region))

    spaces = await catalog.list_spaces(region="all")
    skills = await catalog.list_skills(
        space_id="space-cn-beijing",
        region="cn-beijing",
    )

    assert [item["region"] for item in spaces["items"]] == [
        "cn-beijing",
        "cn-shanghai",
    ]
    assert skills == {
        "items": [
            {
                "skillId": "skill-1",
                "skillName": "writer",
                "skillDescription": "Write content",
                "version": "1.0.0",
                "skillStatus": "active",
            }
        ],
        "totalCount": 1,
    }


@pytest.mark.asyncio
async def test_skill_catalog_normalizes_public_findskill_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "Skills": [
                    {
                        "Slug": "/volcengine/example/pdf-reader/",
                        "Name": "pdf-reader",
                        "Metadata": {"DisplayDescription": "Read PDF files"},
                        "SourceType": "github",
                        "SourceRepo": "volcengine/example",
                        "DownloadCount": 42,
                        "EvaluationScore": 4.8,
                        "EvaluationMetadata": {"skill_version": "1.2.0"},
                        "UpdatedAt": "2026-08-18",
                    }
                ],
                "Total": 1,
            }

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            del args

        async def get(self, url: str, *, params: dict[str, str | int]) -> FakeResponse:
            assert url == skill_catalog.FINDSKILL_SEARCH_URL
            assert params == {"pageNumber": 2, "pageSize": 10, "query": "pdf"}
            return FakeResponse()

    monkeypatch.setattr(skill_catalog.httpx, "AsyncClient", FakeClient)

    response = await skill_catalog.StudioSkillCatalog().search_findskill(
        query=" pdf ",
        page_number=2,
        page_size=10,
    )

    assert response == {
        "items": [
            {
                "slug": "volcengine/example/pdf-reader",
                "name": "pdf-reader",
                "description": "Read PDF files",
                "sourceType": "github",
                "sourceRepo": "volcengine/example",
                "downloadCount": 42,
                "evaluationScore": 4.8,
                "version": "1.2.0",
                "updatedAt": "2026-08-18",
            }
        ],
        "totalCount": 1,
    }
