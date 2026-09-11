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

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from frontend.server.agent_reviews.service import AgentReviewService, ReviewActor
from frontend.server.agent_reviews.tags import (
    decode_record,
    encode_record,
    runtime_tags,
)


class Repository:
    def __init__(self):
        self.runtime = SimpleNamespace(
            runtime_id="r-demo",
            name="demo",
            description="Example agent",
            current_version_number=1,
            status="Running",
            envs=[],
            tags=[
                SimpleNamespace(key="veadk:owner", value="developer"),
                SimpleNamespace(key="veadk:managed", value="true"),
            ],
        )
        self.writes = []

    def get(self, region, runtime_id):
        return deepcopy(self.runtime)

    def list(self, region):
        return [self.get(region, "r-demo")]

    def write(self, region, runtime_id, values):
        tags = {**runtime_tags(self.runtime), **values}
        self.runtime.tags = [SimpleNamespace(key=k, value=v) for k, v in tags.items()]
        self.writes.append(values)


@pytest.fixture
def setup():
    repo = Repository()
    service = AgentReviewService(repo)
    return repo, service


DEVELOPER = ReviewActor("developer", "开发者", "developer")
ADMIN = ReviewActor("admin", "管理员", "admin")
USER = ReviewActor("user", "普通用户", "user")


def test_submit_return_resubmit_and_approve(setup):
    repo, service = setup
    first = service.submit(DEVELOPER, "cn-beijing", "r-demo")
    assert first["status"] == "pending"
    assert runtime_tags(repo.runtime)["veadk:visibility"] == "private"
    returned = service.decide(
        ADMIN,
        "cn-beijing",
        "r-demo",
        first["id"],
        "returned",
        "补充说明\n及示例",
        "请完善",
    )
    assert returned["reason"] == "补充说明\n及示例"
    assert returned["reviewer"]["name"] == "管理员"
    assert returned["reviewedAt"]
    assert service.read(DEVELOPER, "cn-beijing", "r-demo")["status"] == "returned"
    second = service.submit(DEVELOPER, "cn-beijing", "r-demo")
    assert second["id"] != first["id"]
    approved = service.decide(
        ADMIN, "cn-beijing", "r-demo", second["id"], "approved", "", "同意公开"
    )
    assert approved["status"] == "approved"
    assert runtime_tags(repo.runtime)["veadk:visibility"] == "enterprise"
    assert approved["comment"] == "同意公开"


def test_ordinary_user_cannot_submit_even_if_owner(setup):
    _, service = setup
    with pytest.raises(HTTPException) as failure:
        service.submit(ReviewActor("developer", "伪装", "user"), "cn-beijing", "r-demo")
    assert failure.value.status_code == 403


def test_other_developer_cannot_read_or_submit(setup):
    _, service = setup
    for operation in (service.read, service.submit):
        with pytest.raises(HTTPException) as failure:
            operation(
                ReviewActor("other", "other", "developer"), "cn-beijing", "r-demo"
            )
        assert failure.value.status_code == 404


def test_only_admin_can_decide_and_list(setup):
    _, service = setup
    application = service.submit(DEVELOPER, "cn-beijing", "r-demo")
    with pytest.raises(HTTPException) as failure:
        service.decide(
            DEVELOPER, "cn-beijing", "r-demo", application["id"], "approved", "", ""
        )
    assert failure.value.status_code == 403
    with pytest.raises(HTTPException):
        service.list(USER, "cn-beijing")


def test_duplicate_submission_and_stale_decision(setup):
    repo, service = setup
    application = service.submit(DEVELOPER, "cn-beijing", "r-demo")
    assert service.submit(DEVELOPER, "cn-beijing", "r-demo")["id"] == application["id"]
    with pytest.raises(HTTPException):
        service.decide(ADMIN, "cn-beijing", "r-demo", "old-request", "approved", "", "")
    repo.runtime.current_version_number = 2
    with pytest.raises(HTTPException) as failure:
        service.decide(
            ADMIN, "cn-beijing", "r-demo", application["id"], "approved", "", ""
        )
    assert failure.value.status_code == 409
    assert runtime_tags(repo.runtime)["veadk:visibility"] == "private"


def test_direct_publish_unpublish_and_mutation_guard(setup):
    repo, service = setup
    record = service.publish(ADMIN, "cn-beijing", "r-demo", "管理员直接公开")
    assert record["status"] == "approved"
    assert record["direct"] is True
    with pytest.raises(HTTPException):
        service.require_editable(repo.runtime)
    service.unpublish(DEVELOPER, "cn-beijing", "r-demo")
    service.require_editable(repo.runtime)
    assert (
        service.read(DEVELOPER, "cn-beijing", "r-demo")["reviewer"]["name"] == "管理员"
    )


def test_pending_can_be_withdrawn_but_not_edited(setup):
    repo, service = setup
    service.submit(DEVELOPER, "cn-beijing", "r-demo")
    with pytest.raises(HTTPException):
        service.require_editable(repo.runtime)
    service.withdraw(DEVELOPER, "cn-beijing", "r-demo")
    service.require_editable(repo.runtime)


def test_tag_payload_round_trip_preserves_unicode_comments():
    record = {"id": "request", "status": "returned", "comment": "这是审批意见\n" * 50}
    values = encode_record(record)
    assert len(values) <= 20
    assert all(len(value.encode()) <= 256 for value in values.values())
    assert decode_record(values) == record


def test_tag_quota_failure_does_not_write(setup):
    repo, service = setup
    repo.runtime.tags.extend(
        SimpleNamespace(key=f"other-{i}", value="x") for i in range(50)
    )
    with pytest.raises(HTTPException):
        service.submit(DEVELOPER, "cn-beijing", "r-demo")
    assert not repo.writes
