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

from concurrent.futures import ThreadPoolExecutor
import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.skills.models import SkillIdentity
from frontend.server.skills.repository import (
    AgentKitSkillRepository,
    SkillRepositoryError,
)
from frontend.server.skills.routes import mount_skill_routes
from frontend.server.skills.service import SkillService
from frontend.server.skills.consts import SHARE_SPACE, REVIEW_SPACE
from frontend.server.skills.system_spaces import SystemSpaceManager

SHARED_SPACE_NAME = SHARE_SPACE.name
SHARED_SPACE_DESCRIPTION = SHARE_SPACE.managed_description


class Client:
    def __init__(self):
        self.spaces = []
        self.created = []
        self.fail_list = False
        self.race = False
        self.omit_tags = False
        self.ignore_tag_filters = False

    def list_skill_spaces(self, request):
        if self.fail_list:
            raise RuntimeError("list unavailable")
        items = [
            space
            for space in self.spaces
            if (
                self.ignore_tag_filters
                or all(
                    any(
                        tag.key == query.key and tag.value in query.values
                        for tag in space.tags or []
                    )
                    for query in request.tag_filters or []
                )
            )
            and (not request.project_name or space.project_name == request.project_name)
        ]
        start = ((request.page_number or 1) - 1) * (request.page_size or 100)
        return SimpleNamespace(
            items=items[start : start + (request.page_size or 100)],
            total_count=len(items),
        )

    def create_skill_space(self, request):
        assert re.fullmatch(r"[a-z0-9_]+", request.name)
        self.created.append(request)
        space = SimpleNamespace(
            id=f"space-{len(self.spaces)}",
            name=request.name,
            description=request.description,
            project_name=request.project_name,
            status="Running",
            tags=None if self.omit_tags else request.tags,
            relations=[],
            update_time_stamp="",
        )
        self.spaces.append(space)
        if self.race:
            raise RuntimeError("created concurrently")
        return SimpleNamespace(id=space.id)

    def get_skill_space(self, request):
        return next(space for space in self.spaces if space.id == request.id)


@pytest.mark.parametrize("region", ["cn-beijing", "cn-shanghai", "ap-southeast-1"])
def test_default_space_is_created_once_and_reused_across_users(region, monkeypatch):
    monkeypatch.setenv("VEADK_STUDIO_PROJECT", "test-project")
    client = Client()
    repository = AgentKitSkillRepository(lambda _: client)
    service = SkillService(repository)
    user = SkillIdentity(author="user")
    admin = SkillIdentity(author="admin", is_admin=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda _: service.ensure_shared_space(user, region=region), range(12)
            )
        )
    assert len(client.created) == 1
    assert len({result["id"] for result in results}) == 1
    assert results[0]["isShared"] is True
    assert results[0]["canWrite"] is False
    assert service.ensure_shared_space(admin, region=region)["canWrite"] is True
    tags = {tag.key: tag.value for tag in client.created[0].tags}
    assert tags["veadk:visibility"] == "shared"
    assert "author" not in tags
    assert client.created[0].project_name == "test-project"


@pytest.mark.parametrize("region", ["cn-beijing", "ap-southeast-1"])
def test_restarts_reuse_shared_space_when_native_api_omits_tags(region, monkeypatch):
    monkeypatch.delenv("VEADK_STUDIO_PROJECT", raising=False)
    client = Client()
    client.omit_tags = True
    client.ignore_tag_filters = True
    first = AgentKitSkillRepository(lambda _: client).ensure_shared_space(region=region)
    second_repository = AgentKitSkillRepository(lambda _: client)
    second = second_repository.ensure_shared_space(region=region)
    assert first["id"] == second["id"]
    assert second["isShared"] is True
    assert len(client.created) == 1
    with pytest.raises(SkillRepositoryError, match="管理员"):
        second_repository.delete_space(region=region, space_id=str(second["id"]))


def test_same_name_personal_space_is_never_adopted_or_overwritten(monkeypatch):
    monkeypatch.delenv("VEADK_STUDIO_PROJECT", raising=False)
    client = Client()
    client.spaces.append(
        SimpleNamespace(
            id="personal",
            name=SHARED_SPACE_NAME,
            project_name="default",
            tags=None,
            relations=[],
            description="My private skills",
        )
    )
    with pytest.raises(SkillRepositoryError) as raised:
        AgentKitSkillRepository(lambda _: client).ensure_shared_space(
            region="cn-beijing"
        )
    assert raised.value.code == "SYSTEM_SKILL_SPACE_NAME_CONFLICT"
    assert not client.created


@pytest.mark.parametrize(
    "name,description",
    [
        (SHARED_SPACE_NAME, ""),
        (REVIEW_SPACE.name, ""),
        (f"  {REVIEW_SPACE.name.upper()}  ", ""),
        ("personal", SHARED_SPACE_DESCRIPTION),
        ("personal", REVIEW_SPACE.managed_description),
    ],
)
@pytest.mark.parametrize("operation", ["create", "update"])
def test_personal_space_cannot_impersonate_system_identity(
    name, description, operation
):
    client = Client()
    repository = AgentKitSkillRepository(lambda _: client)
    with pytest.raises(SkillRepositoryError) as raised:
        if operation == "create":
            repository.create_space(
                region="cn-beijing",
                name=name,
                description=description,
                project_name="default",
                author="member",
            )
        else:
            repository.update_space(
                region="cn-beijing",
                space_id="personal",
                name=name,
                description=description,
            )
    assert raised.value.status_code == 409
    assert not client.created


def test_lookup_failure_does_not_create_and_can_be_retried():
    client = Client()
    repository = AgentKitSkillRepository(lambda _: client)
    client.fail_list = True
    with pytest.raises(RuntimeError, match="list unavailable"):
        repository.ensure_shared_space(region="cn-beijing")
    assert not client.created
    client.fail_list = False
    assert repository.ensure_shared_space(region="cn-beijing")["id"]


def test_concurrent_create_conflict_reuses_managed_space():
    client = Client()
    client.race = True
    assert AgentKitSkillRepository(lambda _: client).ensure_shared_space(
        region="cn-beijing"
    )["id"]
    assert len(client.created) == 1


def test_shared_space_cannot_be_renamed_deleted_or_written_by_regular_users():
    client = Client()
    repository = AgentKitSkillRepository(lambda _: client)
    space = repository.ensure_shared_space(region="cn-beijing")
    for operation in [
        lambda: repository.update_space(
            region="cn-beijing",
            space_id=str(space["id"]),
            name="changed",
            description=None,
        ),
        lambda: repository.delete_space(region="cn-beijing", space_id=str(space["id"])),
        lambda: repository.require_space_write(
            region="cn-beijing", space_id=str(space["id"]), is_admin=False
        ),
    ]:
        with pytest.raises(SkillRepositoryError) as raised:
            operation()
        assert raised.value.status_code == 403
    repository.require_space_write(
        region="cn-beijing", space_id=str(space["id"]), is_admin=True
    )


def test_shared_endpoint_uses_trusted_identity_and_preserves_personal_filter():
    client = Client()
    service = SkillService(AgentKitSkillRepository(lambda _: client))
    app = FastAPI()
    mount_skill_routes(app, service, lambda _: SkillIdentity(author="user"))
    with TestClient(app) as http:
        response = http.post(
            "/web/skill-management/shared-space/ensure?region=cn-beijing"
        )
        assert response.status_code == 200
        assert response.json()["canWrite"] is False
        assert (
            http.get("/web/skill-management/spaces?region=cn-beijing").json()["items"]
            == []
        )


def test_shared_skill_cannot_be_deleted_through_another_space_id():
    client = SimpleNamespace()
    deleted = []
    client.list_skill_spaces_by_skill = lambda request: SimpleNamespace(
        items=[SimpleNamespace(skill_space_id="shared-space")], total_count=1
    )
    client.get_skill_space = lambda request: SimpleNamespace(
        name=SHARED_SPACE_NAME, description=SHARED_SPACE_DESCRIPTION, tags=None
    )
    client.delete_skill = lambda request: deleted.append(request.id)
    service = SkillService(AgentKitSkillRepository(lambda _: client))
    with pytest.raises(SkillRepositoryError) as raised:
        service.delete_skill(
            SkillIdentity(author="member"), region="cn-beijing", skill_id="shared-skill"
        )
    assert raised.value.status_code == 403
    assert deleted == []
    service.delete_skill(
        SkillIdentity(author="admin", is_admin=True),
        region="cn-beijing",
        skill_id="shared-skill",
    )
    assert deleted == ["shared-skill"]


def test_shared_space_cannot_be_a_direct_generation_destination():
    from frontend.server.skills.system_spaces import require_space_write

    client = Client()
    repository = AgentKitSkillRepository(lambda _: client)
    space = repository.ensure_shared_space(region="cn-beijing")
    with pytest.raises(SkillRepositoryError) as raised:
        require_space_write(client, str(space["id"]))
    assert raised.value.status_code == 403


@pytest.mark.parametrize("region", ["cn-beijing", "ap-southeast-1"])
def test_system_spaces_have_distinct_ids_and_are_reused(region):
    client = Client()
    first = SystemSpaceManager(lambda _: client)
    shared = first.ensure(region, SHARE_SPACE)
    review = first.ensure(region, REVIEW_SPACE)
    second = SystemSpaceManager(lambda _: client)
    assert shared.id != review.id
    assert second.ensure(region, SHARE_SPACE).id == shared.id
    assert second.ensure(region, REVIEW_SPACE).id == review.id
    assert [request.name for request in client.created] == [
        "studio_share_space",
        "studio_review_space",
    ]


def test_review_space_endpoint_requires_admin_and_denies_direct_writes():
    client = Client()
    repository = AgentKitSkillRepository(lambda _: client)
    service = SkillService(repository)
    identity = SkillIdentity(author="member")
    app = FastAPI()
    mount_skill_routes(app, service, lambda _: identity)
    with TestClient(app) as http:
        url = "/web/skill-management/review-space/ensure?region=cn-beijing"
        assert http.post(url).status_code == 403
        assert not client.created
        identity = SkillIdentity(author="admin", is_admin=True)
        response = http.post(url)
        assert response.status_code == 200
        space = response.json()
        assert space["name"] == REVIEW_SPACE.name
        assert space["canWrite"] is False
        assert http.post(url).json()["id"] == space["id"]
    for admin in (False, True):
        with pytest.raises(SkillRepositoryError) as raised:
            repository.require_space_write(
                region="cn-beijing", space_id=space["id"], is_admin=admin
            )
        assert raised.value.status_code == 403


def test_hidden_review_space_does_not_end_personal_space_pagination():
    client = Client()
    repository = AgentKitSkillRepository(lambda _: client)
    repository.ensure_review_space(region="cn-beijing")
    repository.create_space(
        region="cn-beijing",
        name="personal",
        description="Private skills",
        project_name="default",
        author="member",
    )
    first = repository.list_spaces(
        region="cn-beijing", page=1, page_size=1, project_name=None, author=None
    )
    assert first["items"] == []
    assert first["scannedCount"] == 1
    assert first["totalCount"] == 2
    second = repository.list_spaces(
        region="cn-beijing", page=2, page_size=1, project_name=None, author=None
    )
    second_items = second["items"]
    assert isinstance(second_items, list)
    assert second_items[0]["displayName"] == "personal"
    assert second_items[0]["name"] == client.created[-1].name


def test_cloud_rejection_does_not_change_name_or_create_a_fallback():
    client = Client()
    attempted = []

    def reject(request):
        attempted.append(request.name)
        raise RuntimeError("cloud create rejected")

    client.create_skill_space = reject
    manager = SystemSpaceManager(lambda _: client)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="cloud create rejected"):
            manager.ensure("cn-beijing", REVIEW_SPACE)
    assert attempted == [REVIEW_SPACE.name, REVIEW_SPACE.name]
    assert not client.spaces
