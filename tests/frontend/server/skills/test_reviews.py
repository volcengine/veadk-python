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
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from frontend.server.skills.consts import (
    REVIEW_SPACE,
    SHARE_SPACE,
    REVIEW_STATUS_TAG,
    REVIEW_SOURCE_SKILL_TAG,
    SHARED_SOURCE_VERSION_TAG,
)
from frontend.server.skills.models import SkillIdentity
from frontend.server.skills.repository import (
    AgentKitSkillRepository,
    SkillRepositoryError,
)
from frontend.server.skills.routes import mount_skill_routes
from frontend.server.skills.service import SkillService


def package(name: str, text: str) -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(
            f"{name}/SKILL.md",
            f"---\nname: {name}\ndescription: Review test\n---\n{text}",
        )
        archive.writestr(f"{name}/references/data.txt", text)
    return data.getvalue()


class ReviewClient:
    def __init__(self) -> None:
        self.spaces: dict[str, Any] = {}
        self.skills: dict[str, Any] = {}
        self.relations: dict[str, list[Any]] = {"review": [], "shared": []}
        self.spaces["shared"] = SimpleNamespace(
            name=SHARE_SPACE.name, description=SHARE_SPACE.managed_description
        )
        self.api_info: dict[str, Any] = {}
        self.tag_calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_tag_call = 0
        self.ignore_tag_writes = False
        self.copies: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.omit_tags = False
        self.fail_publish = False
        for owner in ["alice", "bob"]:
            self.spaces[owner] = SimpleNamespace(
                name=owner,
                description="",
                tags=[SimpleNamespace(key="author", value=owner)],
            )
            self.skills[owner] = SimpleNamespace(
                id=owner,
                name="same-name",
                description="Review test",
                tags=[SimpleNamespace(key="author", value=owner)],
            )
            self.relations[owner] = [SimpleNamespace(skill_id=owner, version="v3")]

    def get_skill_space(self, request: Any) -> Any:
        return self.spaces[request.id]

    def _invoke_api(self, *, api_action: str, request: Any, response_type: Any) -> Any:
        body = request.model_dump(by_alias=True)
        self.tag_calls.append((api_action, body))
        if len(self.tag_calls) == self.fail_tag_call:
            raise RuntimeError("tag write failed")
        if not self.ignore_tag_writes:
            for skill_id in body["ResourceIds"]:
                skill = self.skills[skill_id]
                tags = {tag.key: tag.value for tag in skill.tags}
                if api_action == "UntagResources":
                    for key in body["TagKeys"]:
                        tags.pop(key, None)
                else:
                    tags.update({tag["Key"]: tag["Value"] for tag in body["Tags"]})
                skill.tags = [
                    SimpleNamespace(key=key, value=value) for key, value in tags.items()
                ]
        return response_type()

    def get_skill(self, request: Any) -> Any:
        return self.skills[request.id]

    def get_skill_version(self, request: Any) -> Any:
        return SimpleNamespace(status="running", version=request.skill_version)

    def list_skills_by_skill_space(self, request: Any) -> Any:
        items = self.relations[request.skill_space_id]
        start = (request.page_number - 1) * request.page_size
        return SimpleNamespace(
            items=items[start : start + request.page_size], total_count=len(items)
        )

    def publish_skill_to_skill_space(self, request: Any) -> None:
        if self.fail_publish:
            raise RuntimeError("publish failed")
        for space_id in request.skill_spaces:
            for skill in request.skills:
                self.relations[space_id].append(
                    SimpleNamespace(
                        skill_id=skill.skill_id,
                        skill_space_id=space_id,
                        version=skill.version,
                        skill_name=self.skills[skill.skill_id].name,
                    )
                )

    def delete_skill(self, request: Any) -> None:
        self.deleted.append(request.id)
        self.skills.pop(request.id)

    def copy(
        self, _client: Any, archive: Any, *, tags: dict[str, str], **_: Any
    ) -> tuple[str, str]:
        skill_id = f"copy-{len(self.copies)}"
        self.copies[skill_id] = bytes(archive.content)
        self.skills[skill_id] = SimpleNamespace(
            id=skill_id,
            name=archive.name,
            description=archive.description,
            tags=[]
            if self.omit_tags
            else [SimpleNamespace(key=key, value=value) for key, value in tags.items()],
        )
        return skill_id, "v1"


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch):
    cloud = ReviewClient()
    repository = AgentKitSkillRepository(lambda _: cloud)
    monkeypatch.setattr(
        repository,
        "ensure_review_space",
        lambda **_: {"id": "review", "projectName": "default"},
    )
    monkeypatch.setattr(
        repository,
        "ensure_shared_space",
        lambda **_: {"id": "shared", "projectName": "default"},
    )
    monkeypatch.setattr(
        repository,
        "skill_archive",
        lambda **kwargs: (
            cloud.copies.get(
                kwargs["skill_id"], package("same-name", kwargs["skill_id"])
            ),
            "same-name.zip",
        ),
    )
    monkeypatch.setattr(repository.reviews, "_copy_archive", cloud.copy)
    return cloud, repository


def submit(
    repository: AgentKitSkillRepository,
    owner: str = "alice",
    region: str = "cn-beijing",
):
    return repository.reviews.submit(
        SkillIdentity(owner),
        region=region,
        space_id=owner,
        skill_id=owner,
        version="v3",
    )


@pytest.mark.parametrize("region", ["cn-beijing", "ap-southeast-1"])
def test_same_names_keep_independent_author_tags_and_archives(setup, region):
    cloud, repository = setup
    alice = submit(repository, "alice", region)
    bob = submit(repository, "bob", region)
    assert alice["id"] != bob["id"]
    assert alice["name"] == bob["name"] == "same-name"
    assert (alice["author"], bob["author"]) == ("alice", "bob")
    assert alice["version"] == "v3" and alice["reviewVersion"] == "v1"
    assert cloud.copies[alice["id"]] == package("same-name", "alice")
    assert len(cloud.relations["alice"]) == 1
    items = repository.reviews.list(
        SkillIdentity("admin", is_admin=True), region=region
    )["items"]
    assert {item["author"] for item in items} == {"alice", "bob"}
    assert all(item["status"] == "pending" for item in items)


def test_repeat_version_is_rejected_using_persisted_tags(setup):
    cloud, repository = setup
    submit(repository)
    with pytest.raises(SkillRepositoryError) as error:
        submit(repository)
    assert error.value.code == "SKILL_REVIEW_ALREADY_PENDING"
    assert len(cloud.copies) == 1
    cloud.relations["alice"][0].version = "v4"
    updated = repository.reviews.submit(
        SkillIdentity("alice"),
        region="cn-beijing",
        space_id="alice",
        skill_id="alice",
        version="v4",
    )
    assert updated["version"] == "v4"
    assert len(cloud.relations["review"]) == 2


def test_unowned_or_unlinked_versions_cannot_be_submitted(setup):
    cloud, repository = setup
    with pytest.raises(SkillRepositoryError) as error:
        repository.reviews.submit(
            SkillIdentity("bob"),
            region="cn-beijing",
            space_id="alice",
            skill_id="alice",
            version="v3",
        )
    assert error.value.status_code == 403
    with pytest.raises(SkillRepositoryError) as error:
        repository.reviews.submit(
            SkillIdentity("alice"),
            region="cn-beijing",
            space_id="alice",
            skill_id="bob",
            version="v3",
        )
    assert error.value.status_code == 409
    assert cloud.copies == {}


def test_historical_version_can_be_submitted_after_current_version_changes(setup):
    cloud, repository = setup
    cloud.relations["alice"][0].version = "v4"
    application = submit(repository)
    assert application["version"] == "v3"


@pytest.mark.parametrize("definition", [REVIEW_SPACE, SHARE_SPACE])
def test_system_spaces_cannot_be_submission_sources(setup, definition):
    cloud, repository = setup
    cloud.spaces["alice"].name = definition.name
    cloud.spaces["alice"].description = definition.managed_description
    with pytest.raises(SkillRepositoryError) as error:
        submit(repository)
    assert error.value.code == "SKILL_REVIEW_SOURCE_INVALID"


@pytest.mark.parametrize("failure", ["omit_tags", "fail_publish"])
def test_failed_submission_removes_unpublished_copy(setup, failure):
    cloud, repository = setup
    setattr(cloud, failure, True)
    with pytest.raises((SkillRepositoryError, RuntimeError)):
        submit(repository)
    assert cloud.deleted == ["copy-0"]
    assert cloud.relations["review"] == []


def test_review_routes_require_admin_and_reject_client_author(setup):
    _, repository = setup
    app = FastAPI()

    def identity(request: Request):
        name = request.headers.get("test-user", "alice")
        return SkillIdentity(name, is_admin=name == "admin")

    mount_skill_routes(app, SkillService(repository), identity)
    with TestClient(app) as client:
        payload = {"version": "v3", "region": "cn-beijing"}
        path = "/web/skill-management/spaces/alice/skills/alice/review"
        assert client.post(path, json={**payload, "author": "admin"}).status_code == 422
        submitted = client.post(path, json=payload)
        assert submitted.status_code == 200
        assert submitted.json()["author"] == "alice"
        assert (
            client.get("/web/skill-management/reviews?region=cn-beijing").status_code
            == 403
        )
        assert (
            client.get(
                "/web/skill-management/reviews/copy-0/files?region=cn-beijing"
            ).status_code
            == 403
        )
        reviews = client.get(
            "/web/skill-management/reviews?region=cn-beijing",
            headers={"test-user": "admin"},
        )
        assert reviews.status_code == 200
        assert reviews.json()["items"][0]["id"] == submitted.json()["id"]


def test_generic_download_guard_rejects_review_copy_with_spoofed_space(setup):
    from frontend.server.skills.system_spaces import require_review_read

    cloud, repository = setup
    application = submit(repository)
    with pytest.raises(SkillRepositoryError) as error:
        require_review_read(cloud, "bob", skill_id=application["id"])
    assert error.value.status_code == 403
    require_review_read(cloud, "bob", skill_id=application["id"], is_admin=True)
    require_review_read(cloud, "alice", skill_id="alice")


def decide(repository, application_id, decision="approved", reason="", actor="admin"):
    return repository.reviews.decide(
        SkillIdentity(actor, is_admin=True),
        region="cn-beijing",
        application_id=application_id,
        decision=decision,
        reason=reason,
    )


def test_approval_publishes_exact_snapshot_and_retains_audit_on_retry(setup):
    from frontend.server.skills.system_spaces import require_review_read

    cloud, repository = setup
    pending = submit(repository)
    approved = decide(repository, pending["id"])
    assert approved["status"] == "approved"
    assert approved["reviewedBy"] == "admin" and approved["reviewedAt"]
    assert approved["sharedSkillId"] not in {pending["id"], "alice"}
    assert cloud.copies[approved["sharedSkillId"]] == cloud.copies[pending["id"]]
    shared_tags = {
        tag.key: tag.value for tag in cloud.skills[approved["sharedSkillId"]].tags
    }
    assert shared_tags["author"] == "alice"
    assert shared_tags[SHARED_SOURCE_VERSION_TAG] == "v3"
    assert REVIEW_SOURCE_SKILL_TAG not in shared_tags
    require_review_read(cloud, "shared", skill_id=approved["sharedSkillId"])
    assert decide(repository, pending["id"], actor="another-admin") == approved
    assert len(cloud.relations["shared"]) == 1
    with pytest.raises(SkillRepositoryError) as error:
        decide(repository, pending["id"], "returned", "changed my mind")
    assert error.value.status_code == 409


def test_return_records_reason_allows_new_application_and_keeps_history(setup):
    cloud, repository = setup
    pending = submit(repository)
    returned = decide(repository, pending["id"], "returned", "  请补充示例\n再提交  ")
    assert returned["status"] == "returned"
    assert returned["reason"] == "请补充示例\n再提交"
    assert returned["reviewedBy"] == "admin" and returned["reviewedAt"]
    assert cloud.relations["shared"] == []
    assert decide(repository, pending["id"], "returned", "other reason") == returned
    resubmitted = submit(repository)
    assert resubmitted["id"] != returned["id"] and resubmitted["status"] == "pending"
    assert len(cloud.relations["review"]) == 2
    own = repository.reviews.list_for_source(
        SkillIdentity("alice"), region="cn-beijing", space_id="alice"
    )["items"]
    assert [item["status"] for item in own] == ["pending", "returned"]
    assert (
        repository.reviews.list_for_source(
            SkillIdentity("bob"), region="cn-beijing", space_id="alice"
        )["items"]
        == []
    )


def test_failed_final_tag_write_resumes_without_duplicate_public_copy(setup):
    cloud, repository = setup
    pending = submit(repository)
    cloud.fail_tag_call = 2
    with pytest.raises(RuntimeError, match="tag write failed"):
        decide(repository, pending["id"])
    application = repository.reviews.list(
        SkillIdentity("admin", True), region="cn-beijing"
    )["items"][0]
    assert application["status"] == "approving"
    assert len(cloud.relations["shared"]) == 1
    with pytest.raises(SkillRepositoryError) as error:
        decide(repository, pending["id"], "returned", "cannot return while publishing")
    assert error.value.code == "SKILL_REVIEW_PUBLISHING"
    cloud.fail_tag_call = 0
    approved = decide(repository, pending["id"], actor="second-admin")
    assert approved["reviewedBy"] == "admin"
    assert approved["status"] == "approved"
    assert len(cloud.relations["shared"]) == 1


def test_failed_initial_tags_never_publish_and_failed_publication_can_retry(setup):
    cloud, repository = setup
    pending = submit(repository)
    cloud.fail_tag_call = 1
    with pytest.raises(RuntimeError):
        decide(repository, pending["id"])
    assert cloud.relations["shared"] == []
    cloud.fail_tag_call = 0
    cloud.fail_publish = True
    with pytest.raises(RuntimeError, match="publish failed"):
        decide(repository, pending["id"])
    assert cloud.relations["shared"] == []
    cloud.fail_publish = False
    assert decide(repository, pending["id"])["status"] == "approved"
    assert len(cloud.relations["shared"]) == 1


def test_tag_updates_preserve_unrelated_tags_and_verify_cloud_readback(setup):
    from frontend.server.skills.tags import update_skill_tags

    cloud, _ = setup
    update_skill_tags(cloud, "alice", {"display_name": "before"})
    cloud.tag_calls.clear()
    update_skill_tags(cloud, "alice", {"display_name": "after"})
    assert [call[0] for call in cloud.tag_calls] == ["TagResources"]
    assert cloud.tag_calls[0][1]["ResourceType"] == "skill"
    assert cloud.tag_calls[0][1]["Tags"] == [{"Key": "display_name", "Value": "after"}]
    assert {tag.key: tag.value for tag in cloud.skills["alice"].tags} == {
        "author": "alice",
        "display_name": "after",
    }
    cloud.ignore_tag_writes = True
    with pytest.raises(SkillRepositoryError) as error:
        update_skill_tags(cloud, "alice", {REVIEW_STATUS_TAG: "returned"})
    assert error.value.code == "SKILL_REVIEW_TAG_WRITE_FAILED"


def test_long_review_metadata_writes_status_after_all_chunks(setup):
    from frontend.server.skills.tags import update_skill_tags

    cloud, _ = setup
    tags = {REVIEW_STATUS_TAG: "returned", **{f"comment.{i}": "x" for i in range(24)}}
    update_skill_tags(cloud, "alice", tags)
    assert len(cloud.tag_calls) == 2
    assert all(len(call[1]["Tags"]) <= 20 for call in cloud.tag_calls)
    assert all(tag["Key"] != REVIEW_STATUS_TAG for tag in cloud.tag_calls[0][1]["Tags"])
    assert cloud.tag_calls[-1][1]["Tags"][-1]["Key"] == REVIEW_STATUS_TAG


def test_decision_routes_require_admin_and_server_generated_audit(setup):
    _, repository = setup
    pending = submit(repository)
    app = FastAPI()
    mount_skill_routes(
        app,
        SkillService(repository),
        lambda request: SkillIdentity(
            request.headers.get("test-user", "alice"),
            is_admin=request.headers.get("test-user") == "admin",
        ),
    )
    path = f"/web/skill-management/reviews/{pending['id']}/decision"
    body = {"region": "cn-beijing", "decision": "returned", "reason": "补充说明"}
    with TestClient(app) as client:
        assert client.post(path, json=body).status_code == 403
        admin = {"test-user": "admin"}
        for invalid in [
            {"reason": "  "},
            {"reason": "x" * 257},
            {"reviewedBy": "other"},
            {"reviewedAt": "yesterday"},
        ]:
            assert (
                client.post(path, json={**body, **invalid}, headers=admin).status_code
                == 422
            )
        assert (
            client.post(
                path.replace(pending["id"], "alice"), json=body, headers=admin
            ).status_code
            == 404
        )
        response = client.post(path, json=body, headers=admin)
        assert response.status_code == 200 and response.json()["reviewedBy"] == "admin"


@pytest.mark.parametrize("region", ["cn-beijing", "ap-southeast-1"])
def test_review_submitter_uid_survives_rename_and_rejects_same_name_other_uid(
    setup, region
):
    cloud, repository = setup
    from frontend.server.skills.consts import (
        REVIEW_SUBMITTER_ID_TAG,
        REVIEW_SUBMITTER_OWNER_TAG,
    )

    submitter = SkillIdentity("alice", owner_id="owner-alice", identity_uid="uid-alice")
    application = repository.reviews.submit(
        submitter, region=region, space_id="alice", skill_id="alice", version="v3"
    )
    tags = {tag.key: tag.value for tag in cloud.skills[application["id"]].tags}
    assert tags[REVIEW_SUBMITTER_ID_TAG] == "uid-alice"
    assert tags[REVIEW_SUBMITTER_OWNER_TAG] == "owner-alice"
    renamed = SkillIdentity(
        "Alice New Name", owner_id="owner-new", identity_uid="uid-alice"
    )
    assert (
        repository.reviews.get(
            renamed, region=region, application_id=application["id"]
        )["id"]
        == application["id"]
    )
    assert [
        item["id"]
        for item in repository.reviews.list_for_source(
            renamed, region=region, space_id="alice"
        )["items"]
    ] == [application["id"]]
    for other in [
        SkillIdentity("alice", owner_id="owner-alice", identity_uid="uid-imposter"),
        SkillIdentity("alice", owner_id="owner-alice"),
    ]:
        with pytest.raises(SkillRepositoryError) as denied:
            repository.reviews.get(
                other, region=region, application_id=application["id"]
            )
        assert denied.value.status_code == 403
        assert (
            repository.reviews.list_for_source(other, region=region, space_id="alice")[
                "items"
            ]
            == []
        )
    assert (
        repository.reviews.get(
            SkillIdentity("admin", True),
            region=region,
            application_id=application["id"],
        )["id"]
        == application["id"]
    )


def test_review_without_uid_uses_stable_owner_before_display_name(setup):
    _, repository = setup
    application = repository.reviews.submit(
        SkillIdentity("alice", owner_id="owner-alice"),
        region="cn-beijing",
        space_id="alice",
        skill_id="alice",
        version="v3",
    )
    renamed = SkillIdentity(
        "Alice New Name", owner_id="owner-alice", identity_uid="new-uid"
    )
    assert (
        repository.reviews.get(
            renamed, region="cn-beijing", application_id=application["id"]
        )["id"]
        == application["id"]
    )
    assert (
        repository.reviews.list_for_source(
            renamed, region="cn-beijing", space_id="alice"
        )["totalCount"]
        == 1
    )
    for other in [
        SkillIdentity("alice", owner_id="owner-other"),
        SkillIdentity("alice"),
    ]:
        with pytest.raises(SkillRepositoryError) as denied:
            repository.reviews.get(
                other, region="cn-beijing", application_id=application["id"]
            )
        assert denied.value.status_code == 403
        assert (
            repository.reviews.list_for_source(
                other, region="cn-beijing", space_id="alice"
            )["items"]
            == []
        )


def test_legacy_review_without_stable_identity_keeps_author_fallback(setup):
    _, repository = setup
    application = submit(repository)
    identity = SkillIdentity("alice", owner_id="owner-alice", identity_uid="uid-alice")
    assert (
        repository.reviews.get(
            identity, region="cn-beijing", application_id=application["id"]
        )["id"]
        == application["id"]
    )
    assert (
        repository.reviews.list_for_source(
            identity, region="cn-beijing", space_id="alice"
        )["totalCount"]
        == 1
    )
    with pytest.raises(SkillRepositoryError) as denied:
        repository.reviews.get(
            SkillIdentity("bob"), region="cn-beijing", application_id=application["id"]
        )
    assert denied.value.status_code == 403
    assert (
        repository.reviews.list_for_source(
            SkillIdentity("bob"), region="cn-beijing", space_id="alice"
        )["items"]
        == []
    )
