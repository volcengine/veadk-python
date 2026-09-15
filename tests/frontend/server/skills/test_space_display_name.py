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

from types import SimpleNamespace
from typing import Any
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.skills.models import SkillIdentity
from frontend.server.skills.repository import AgentKitSkillRepository
from frontend.server.skills.routes import mount_skill_routes
from frontend.server.skills.service import SkillService


class SpaceClient:
    def __init__(self, *, return_tags: bool = True) -> None:
        self.return_tags = return_tags
        self.created: list[Any] = []
        self.spaces: list[Any] = []

    def create_skill_space(self, request: Any) -> SimpleNamespace:
        self.created.append(request)
        space = SimpleNamespace(
            id=f"space-{len(self.created)}",
            name=request.name,
            description=request.description,
            project_name=request.project_name,
            tags=request.tags if self.return_tags else None,
        )
        self.spaces.append(space)
        return SimpleNamespace(id=space.id)

    def list_skill_spaces(self, request: Any) -> SimpleNamespace:
        return SimpleNamespace(items=self.spaces, total_count=len(self.spaces))


@pytest.mark.parametrize("region", ["cn-beijing", "ap-southeast-1"])
def test_create_chinese_display_name_and_read_it_after_reload(region: str) -> None:
    cloud = SpaceClient()
    app = FastAPI()
    mount_skill_routes(
        app,
        SkillService(AgentKitSkillRepository(lambda _: cloud)),
        lambda _: SkillIdentity(author="test-user"),
    )
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post(
                "/web/skill-management/spaces",
                json={
                    "name": "  中文 Skill 空间  ",
                    "region": region,
                },
            )
            assert response.status_code == 200
            created = response.json()
            assert created["displayName"] == "中文 Skill 空间"
            assert re.fullmatch(r"[a-z0-9_]+", created["name"])
        response = client.get("/web/skill-management/spaces", params={"region": region})
    assert [item["displayName"] for item in response.json()["items"]] == [
        "中文 Skill 空间"
    ] * 2
    assert cloud.created[0].name != cloud.created[1].name
    assert {tag.key: tag.value for tag in cloud.created[0].tags} == {
        "author": "test-user",
        "display_name": "中文 Skill 空间",
    }


@pytest.mark.parametrize(
    "tags", [None, [], [SimpleNamespace(key="display_name", value="  ")]]
)
def test_missing_display_name_falls_back_to_cloud_name(tags: Any) -> None:
    cloud = SpaceClient()
    cloud.spaces = [SimpleNamespace(id="legacy", name="legacy_space", tags=tags)]
    result = AgentKitSkillRepository(lambda _: cloud).list_spaces(
        region="cn-beijing",
        page=1,
        page_size=20,
        project_name=None,
        author=None,
    )
    items = result["items"]
    assert isinstance(items, list)
    assert items[0]["name"] == "legacy_space"
    assert items[0]["displayName"] == "legacy_space"


def test_provider_without_tag_readback_keeps_real_name_available() -> None:
    cloud = SpaceClient(return_tags=False)
    repository = AgentKitSkillRepository(lambda _: cloud)
    created = repository.create_space(
        region="ap-southeast-1",
        name="中文名称",
        description=None,
        project_name=None,
        author="test-user",
    )
    result = repository.list_spaces(
        region="ap-southeast-1",
        page=1,
        page_size=20,
        project_name=None,
        author=None,
    )
    items = result["items"]
    assert isinstance(items, list)
    listed = items[0]
    assert created["displayName"] == "中文名称"
    assert listed["displayName"] == created["name"] == listed["name"]
