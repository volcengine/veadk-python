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

import io
import zipfile
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from frontend.server.skills.consts import (
    REVIEW_SPACE,
    SHARE_SPACE,
    SHARED_SOURCE_VERSION_TAG,
)
from frontend.server.skills.models import SkillIdentity
from frontend.server.skills.repository import (
    AgentKitSkillRepository,
    SkillRepositoryError,
)
from frontend.server.skills.routes import mount_skill_routes
from frontend.server.skills.service import SkillService
from frontend.server.skills.versions import SkillVersionRepository


def package(name: str = "daily-summary") -> bytes:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr(
            f"{name}/SKILL.md",
            f"---\nname: {name}\ndescription: Updated version\n---\nVersion content",
        )
    return content.getvalue()


def version(name: str, status: str = "running") -> Any:
    return SimpleNamespace(
        version=name,
        status=status,
        name="daily-summary",
        description="Description " + name,
        create_time_stamp="1789116575",
        update_time_stamp="1789116575",
        error_message="",
    )


class VersionClient:
    def __init__(self) -> None:
        self.space = SimpleNamespace(name="personal", description="", tags=[])
        self.skill = SimpleNamespace(
            name="daily-summary", tags=[SimpleNamespace(key="author", value="alice")]
        )
        self.items = [version("v1")]
        self.current = "v1"
        self.updated: list[Any] = []
        self.published: list[Any] = []
        self.read_pages: list[int] = []

    def get_skill_space(self, _: Any) -> Any:
        return self.space

    def get_skill(self, _: Any) -> Any:
        return self.skill

    def list_skills_by_skill_space(self, request: Any) -> Any:
        items = (
            [SimpleNamespace(skill_id="skill", version=self.current)]
            if request.skill_space_id == "space"
            else []
        )
        return SimpleNamespace(items=items, total_count=len(items))

    def list_skill_versions(self, request: Any) -> Any:
        self.read_pages.append(request.page_number)
        start = (request.page_number - 1) * request.page_size
        return SimpleNamespace(
            items=self.items[start : start + request.page_size],
            total_count=len(self.items),
        )

    def update_skill(self, request: Any) -> None:
        self.updated.append(request)
        self.items.append(version("v2"))

    def publish_skill_to_skill_space(self, request: Any) -> None:
        self.published.append(request)
        self.current = request.skills[0].version


@pytest.fixture
def setup():
    cloud = VersionClient()
    repository = AgentKitSkillRepository(lambda _: cloud)
    return cloud, repository, SkillVersionRepository(repository, lambda _: cloud)


def listed(
    versions: SkillVersionRepository, author: str = "alice", is_admin: bool = False
):
    return versions.list(
        SkillIdentity(author, is_admin),
        region="cn-beijing",
        space_id="space",
        skill_id="skill",
    )


def test_lists_every_native_version_with_numeric_order_and_current_relation(setup):
    cloud, _, versions = setup
    cloud.items = [version(f"v{number}") for number in range(1, 103)]
    cloud.current = "v99"
    result = listed(versions)
    assert result["totalCount"] == 102
    assert [item["version"] for item in result["items"][:3]] == ["v102", "v101", "v100"]
    assert [item["version"] for item in result["items"] if item["isCurrent"]] == ["v99"]
    assert result["items"][0]["createdAt"] == "2026-09-11T08:49:35+00:00"
    assert cloud.read_pages == [1, 2]
    assert result["canUpdate"] is True


def test_list_requires_actual_space_membership(setup):
    _, _, versions = setup
    with pytest.raises(SkillRepositoryError) as error:
        versions.list(
            SkillIdentity("alice"),
            region="cn-beijing",
            space_id="other",
            skill_id="skill",
        )
    assert error.value.status_code == 404


def test_other_user_cannot_read_personal_version_history(setup):
    _, _, versions = setup
    with pytest.raises(SkillRepositoryError) as error:
        listed(versions, "bob")
    assert error.value.status_code == 403


def test_shared_history_only_exposes_shared_versions_without_update(setup):
    from agentkit.sdk.skills import types as sdk
    from frontend.server.skills.repository import list_skill_space_items

    cloud, _, versions = setup
    cloud.space = SimpleNamespace(
        name=SHARE_SPACE.name, description=SHARE_SPACE.managed_description
    )
    cloud.items.append(version("v2"))
    cloud.skill.tags.append(SimpleNamespace(key=SHARED_SOURCE_VERSION_TAG, value="v8"))
    result = listed(versions, "bob")
    assert [item["version"] for item in result["items"]] == ["v1"]
    assert result["items"][0]["sourceVersion"] == "v8"
    assert result["items"][0]["author"] == "alice"
    catalog = list_skill_space_items(
        cloud, sdk, space_id="space", include_display_metadata=True
    )
    assert catalog.items[0]["version"] == "v1"
    assert catalog.items[0]["sourceVersion"] == "v8"
    assert catalog.items[0]["author"] == "alice"
    assert result["canUpdate"] is False
    with pytest.raises(SkillRepositoryError) as error:
        versions.upload(
            SkillIdentity("admin", True),
            region="cn-beijing",
            space_id="space",
            skill_id="skill",
            content=package(),
        )
    assert error.value.code == "SKILL_VERSION_UPDATE_FORBIDDEN"
    assert not cloud.updated


def test_review_version_history_is_admin_only_and_never_updatable(setup):
    cloud, _, versions = setup
    cloud.space = SimpleNamespace(
        name=REVIEW_SPACE.name, description=REVIEW_SPACE.managed_description
    )
    with pytest.raises(SkillRepositoryError) as error:
        listed(versions)
    assert error.value.status_code == 403
    assert listed(versions, "admin", True)["canUpdate"] is False


def test_legacy_missing_author_history_readable_but_not_claimed_for_update(setup):
    cloud, _, versions = setup
    cloud.skill.tags = []
    assert listed(versions)["canUpdate"] is False
    cloud.space.tags = [SimpleNamespace(key="author", value="alice")]
    assert listed(versions)["canUpdate"] is True


def test_upload_rejects_renamed_archive_before_cloud_mutation(setup):
    cloud, _, versions = setup
    with pytest.raises(SkillRepositoryError) as error:
        versions.upload(
            SkillIdentity("alice"),
            region="cn-beijing",
            space_id="space",
            skill_id="skill",
            content=package("different"),
        )
    assert error.value.code == "SKILL_VERSION_NAME_MISMATCH"
    assert not cloud.updated


def test_wait_does_not_return_old_running_version(setup, monkeypatch):
    cloud, _, versions = setup
    calls = []

    def delayed(_: float):
        calls.append(True)
        cloud.items.append(version("v2"))

    monkeypatch.setattr("frontend.server.skills.versions.time.sleep", delayed)
    latest = versions._wait_for_new_version(cloud, "skill", {"v1"})
    assert latest.version == "v2"
    assert calls == [True]


def test_wait_reports_failed_new_version(setup):
    cloud, _, versions = setup
    cloud.items.append(version("v2", "failed"))
    with pytest.raises(SkillRepositoryError) as error:
        versions._wait_for_new_version(cloud, "skill", {"v1"})
    assert error.value.code == "SKILL_VERSION_FAILED"


def test_wait_times_out_without_inventing_new_version(setup):
    cloud, _, versions = setup
    with pytest.raises(SkillRepositoryError) as error:
        versions._wait_for_new_version(cloud, "skill", {"v1"}, timeout_seconds=0)
    assert error.value.code == "SKILL_VERSION_PENDING"
    assert error.value.status_code == 504


def test_upload_updates_same_skill_and_only_personal_space(setup, monkeypatch):
    from frontend.server.skills import storage

    cloud, _, versions = setup
    config = SimpleNamespace(tos=SimpleNamespace(bucket="", prefix=""))
    monkeypatch.setattr(
        "agentkit.toolkit.config.GlobalConfigManager.load", lambda _: config
    )
    monkeypatch.setattr(
        storage,
        "resolve_skill_publish_storage",
        lambda **_: SimpleNamespace(provider="volcengine", bucket="bucket"),
    )
    monkeypatch.setattr(
        storage, "resolve_skill_publish_credentials", lambda **_: object()
    )
    monkeypatch.setattr(storage, "ensure_skill_publish_bucket", lambda *_: None)
    monkeypatch.setattr(
        storage, "upload_skill_archive", lambda *_: "tos://bucket/version.zip"
    )
    result = versions.upload(
        SkillIdentity("alice"),
        region="cn-beijing",
        space_id="space",
        skill_id="skill",
        content=package(),
    )
    assert result["version"] == "v2"
    assert cloud.updated[0].id == "skill"
    assert cloud.updated[0].skill_spaces == ["space"]
    assert cloud.published[0].skill_spaces == ["space"]
    assert [item.version for item in cloud.items] == ["v1", "v2"]
    assert cloud.skill.tags[0].value == "alice"


def test_version_routes_reuse_identity_and_archive_validation(setup):
    _, repository, _ = setup
    app = FastAPI()

    def identity(request: Request):
        author = request.headers.get("test-author")
        if not author:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        return SkillIdentity(author)

    mount_skill_routes(app, SkillService(repository), identity)
    with TestClient(app) as client:
        path = (
            "/web/skill-management/spaces/space/skills/skill/versions?region=cn-beijing"
        )
        assert client.get(path).status_code == 401
        assert (
            client.get(path, headers={"test-author": "alice"}).json()["items"][0][
                "version"
            ]
            == "v1"
        )
        assert client.get(path, headers={"test-author": "bob"}).status_code == 403
        assert (
            client.post(
                path,
                headers={"test-author": "alice", "Content-Type": "text/plain"},
                content=b"not zip",
            ).status_code
            == 415
        )


def test_document_edit_preserves_binary_files_and_requires_version(setup, monkeypatch):
    from frontend.server.skills.documents import replace_skill_document

    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr(
            "daily-summary/SKILL.md",
            "---\nname: daily-summary\ndescription: Original\n---\nOld",
        )
        info = zipfile.ZipInfo("daily-summary/run.bin")
        info.external_attr = 0o100755 << 16
        archive.writestr(info, b"\x00\xff\x10")
    updated = replace_skill_document(
        content.getvalue(), "---\nname: daily-summary\ndescription: Updated\n---\nNew"
    )
    with zipfile.ZipFile(io.BytesIO(updated)) as archive:
        assert archive.read("daily-summary/run.bin") == b"\x00\xff\x10"
        assert archive.getinfo("daily-summary/run.bin").external_attr == 0o100755 << 16
        assert archive.read("daily-summary/SKILL.md").endswith(b"New")
    cloud, _, versions = setup
    cloud.items.append(version("v2"))
    with pytest.raises(SkillRepositoryError) as error:
        versions.upload(
            SkillIdentity("alice"),
            region="cn-beijing",
            space_id="space",
            skill_id="skill",
            content=updated,
            expected_version="v1",
        )
    assert error.value.status_code == 409
    assert not cloud.updated


def test_document_edit_rejects_name_change():
    from frontend.server.skills.documents import replace_skill_document

    with pytest.raises(SkillRepositoryError) as error:
        replace_skill_document(
            package(), "---\nname: other\ndescription: Changed\n---\nNew"
        )
    assert error.value.code == "SKILL_VERSION_NAME_MISMATCH"


def test_document_routes_preserve_identity_permissions_and_source_version(
    setup, monkeypatch
):
    cloud, repository, versions = setup
    monkeypatch.setattr(
        repository, "skill_archive", lambda **_: (package(), "skill.zip")
    )
    app = FastAPI()

    def identity(request: Request):
        author = request.headers.get("test-author")
        if not author:
            raise HTTPException(401)
        return SkillIdentity(author)

    mount_skill_routes(app, SkillService(repository), identity)
    path = "/web/skill-management/spaces/space/skills/skill/document?region=cn-beijing"
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        result = client.get(path, headers={"test-author": "alice"})
        assert result.status_code == 200
        assert result.json()["baseVersion"] == "v1"
        assert result.json()["canUpdate"] is True
        assert "Version content" in result.json()["content"]
        assert client.get(path, headers={"test-author": "bob"}).status_code == 403
        assert (
            client.put(
                path,
                headers={"test-author": "alice"},
                json={"baseVersion": "v0", "content": "Changed"},
            ).status_code
            == 409
        )
        saved = []

        def upload(identity, **kwargs):
            saved.append(kwargs)
            return {"version": "v2"}

        monkeypatch.setattr(
            type(versions),
            "upload",
            lambda self, identity, **kwargs: upload(identity, **kwargs),
        )
        content = "---\nname: daily-summary\ndescription: Changed\n---\nUpdated"
        assert client.put(
            path,
            headers={"test-author": "alice"},
            json={"baseVersion": "v1", "content": content},
        ).json() == {"version": "v2"}
        assert saved[0]["expected_version"] == "v1"
        cloud.space = SimpleNamespace(
            name=SHARE_SPACE.name, description=SHARE_SPACE.managed_description
        )
        assert (
            client.get(path, headers={"test-author": "alice"}).json()["canUpdate"]
            is False
        )
        assert (
            client.put(
                path,
                headers={"test-author": "alice"},
                json={"baseVersion": "v1", "content": content},
            ).status_code
            == 403
        )
        assert len(saved) == 1


@pytest.mark.parametrize("path", ["./SKILL.md", "wrapped/SKILL.md"])
def test_document_edit_ignores_macos_metadata_and_normalizes_paths(path):
    from frontend.server.skills.documents import replace_skill_document

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("__MACOSX/SKILL.md", "Keep metadata")
        archive.writestr(
            path, "---\nname: daily-summary\ndescription: Original\n---\nOld"
        )
    updated = replace_skill_document(
        output.getvalue(), "---\nname: daily-summary\ndescription: Updated\n---\nNew"
    )
    with zipfile.ZipFile(io.BytesIO(updated)) as archive:
        assert archive.read(path).endswith(b"New")
        assert archive.read("__MACOSX/SKILL.md") == b"Keep metadata"
