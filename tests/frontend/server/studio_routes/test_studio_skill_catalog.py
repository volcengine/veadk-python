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


@pytest.mark.parametrize(
    ("provider", "region", "configured_provider", "expected_host"),
    [
        (
            "volcengine",
            "cn-beijing",
            "byteplus",
            "open.volcengineapi.com",
        ),
        (
            "byteplus",
            "ap-southeast-1",
            "volcengine",
            "agentkit.ap-southeast-1.byteplusapi.com",
        ),
    ],
)
def test_skill_catalog_client_uses_studio_provider_over_global_config(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    region: str,
    configured_provider: str,
    expected_host: str,
) -> None:
    from agentkit.platform.context import (
        default_cloud_provider,
        get_default_cloud_provider,
    )

    monkeypatch.setattr(
        skill_catalog,
        "resolve_skill_publish_credentials",
        lambda **_: SimpleNamespace(
            access_key="placeholder-ak",
            secret_key="placeholder-sk",
            session_token=None,
        ),
    )
    monkeypatch.setattr(
        "agentkit.platform.configuration.read_cloud_provider_from_env",
        lambda: None,
    )
    monkeypatch.setattr(
        "agentkit.platform.configuration.read_global_config_dict",
        lambda: {"defaults": {"cloud_provider": configured_provider}},
    )

    with default_cloud_provider(None):
        client = skill_catalog.StudioSkillCatalog(provider)._client(region)  # type: ignore[arg-type]
        assert get_default_cloud_provider() is None

    assert client.host == expected_host
    assert client.region == region


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
async def test_skill_catalog_recovers_readable_skills_from_dangling_relation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DanglingRelationError(RuntimeError):
        code = "ResourceNotFound.skill"

    class FakeClient:
        def list_skills_by_skill_space(self, request: object) -> SimpleNamespace:
            del request
            raise DanglingRelationError("ResourceNotFound.skill")

        def get_skill_space(self, request: object) -> SimpleNamespace:
            assert getattr(request, "id") == "space-1"
            return SimpleNamespace(name="Writers")

        def list_skills_by_space_id(self, request: object) -> SimpleNamespace:
            assert getattr(request, "skill_space_id") == "space-1"
            assert getattr(request, "skill_space_name") == "Writers"
            return SimpleNamespace(
                items=[SimpleNamespace(name="writer", description="basic")]
            )

        def get_skill_info(self, request: object) -> SimpleNamespace:
            assert getattr(request, "skill_name") == "writer"
            assert getattr(request, "skill_space_name") == "Writers"
            return SimpleNamespace(
                skill_name="writer",
                description="Write content",
                skill_md="# Writer",
            )

    catalog = skill_catalog.StudioSkillCatalog()
    monkeypatch.setattr(catalog, "_client", lambda _region: FakeClient())

    result = await catalog.list_skills(space_id="space-1", region="cn-beijing")

    assert result == {
        "items": [
            {
                "skillId": "",
                "skillName": "writer",
                "skillDescription": "Write content",
                "version": "",
                "skillStatus": "",
                "lookupByName": True,
                "degraded": True,
            }
        ],
        "totalCount": 1,
        "degraded": True,
        "warnings": ["部分关联异常，已恢复可读取技能"],
    }


@pytest.mark.asyncio
async def test_skill_catalog_does_not_fallback_for_other_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def list_skills_by_skill_space(self, request: object) -> SimpleNamespace:
            del request
            raise RuntimeError("AccessDenied")

        def list_skills_by_space_id(self, request: object) -> SimpleNamespace:
            del request
            raise AssertionError("must not fallback")

    catalog = skill_catalog.StudioSkillCatalog()
    monkeypatch.setattr(catalog, "_client", lambda _region: FakeClient())

    with pytest.raises(skill_catalog.StudioSkillCatalogError) as raised:
        await catalog.list_skills(space_id="space-1", region="cn-beijing")

    assert raised.value.status_code == 502


@pytest.mark.asyncio
async def test_skill_catalog_requires_exact_missing_skill_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SimilarError(RuntimeError):
        code = "ResourceNotFound.skillset"

    class FakeClient:
        def list_skills_by_skill_space(self, request: object) -> SimpleNamespace:
            del request
            raise SimilarError("ResourceNotFound.skill")

        def list_skills_by_space_id(self, request: object) -> SimpleNamespace:
            del request
            raise AssertionError("must not fallback for a similar code")

    catalog = skill_catalog.StudioSkillCatalog()
    monkeypatch.setattr(catalog, "_client", lambda _region: FakeClient())

    with pytest.raises(skill_catalog.StudioSkillCatalogError) as raised:
        await catalog.list_skills(space_id="space-1", region="cn-beijing")

    assert raised.value.status_code == 502


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
