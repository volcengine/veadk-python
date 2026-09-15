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

import base64
import json
import zlib
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
                SimpleNamespace(key="veadk:author", value="开发者"),
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


@pytest.mark.parametrize("text", ["同意公开", "中文，标点。\n" * 20, "😀" * 256])
def test_explicit_tag_fields_round_trip(text):
    record = {"id": "request", "status": "returned", "comment": text}
    values = encode_record(record)
    assert "veadk:review:comment" in values
    assert not any(key.startswith("veadk:review:data") for key in values)
    assert all(len(value) <= 256 for value in values.values())
    assert decode_record(values)["comment"] == text


def test_review_does_not_persist_runtime_or_applicant_details(setup):
    repo, service = setup
    record = service.submit(DEVELOPER, "cn-beijing", "r-demo", "请审核")
    saved = decode_record(repo.writes[-1])
    assert not {"snapshot", "agent", "submitter", "runtimeId", "region"} & saved.keys()
    assert record["submitter"]["id"] == "developer"
    assert record["submitter"]["name"] == "开发者"
    repo.runtime.name = "Updated runtime name"
    assert (
        service.read(DEVELOPER, "cn-beijing", "r-demo")["agent"]["name"]
        == repo.runtime.name
    )
    assert service.list(ADMIN, "cn-beijing")[0]["agent"]["name"] == repo.runtime.name


def test_direct_publication_keeps_runtime_owner_as_applicant(setup):
    _, service = setup
    record = service.publish(ADMIN, "cn-beijing", "r-demo")
    assert record["submitter"]["id"] == "developer"
    assert record["reviewer"]["id"] == "admin"


@pytest.mark.parametrize("region", ["cn-beijing", "ap-southeast-1"])
def test_review_text_limits_are_checked_before_cloud_write(setup, region):
    repo, service = setup
    application = service.submit(DEVELOPER, region, "r-demo", "字" * 20)
    assert application["message"] == "字" * 20
    before = len(repo.writes)
    for callback in [
        lambda: service.submit(DEVELOPER, region, "r-demo", "字" * 21),
        lambda: service.decide(
            ADMIN, region, "r-demo", application["id"], "returned", "字" * 257
        ),
        lambda: service.decide(
            ADMIN, region, "r-demo", application["id"], "approved", comment="字" * 257
        ),
        lambda: service.publish(ADMIN, region, "r-demo", "字" * 257),
    ]:
        with pytest.raises(HTTPException) as failure:
            callback()
        assert failure.value.status_code == 422
    assert len(repo.writes) == before
    service.decide(
        ADMIN,
        region,
        "r-demo",
        application["id"],
        "returned",
        "😀" * 256,
        "意见。" * 85,
    )
    saved = service.read(DEVELOPER, region, "r-demo")
    assert saved["reason"] == "😀" * 256
    next_application = service.submit(DEVELOPER, region, "r-demo", "已补充")
    assert next_application["reviewer"] is None
    saved = service.read(DEVELOPER, region, "r-demo")
    assert saved["reason"] == saved["comment"] == saved["reviewedAt"] == ""
    assert saved["reviewer"] is None


def test_existing_application_is_readable_and_rewritten_without_snapshot(setup):
    repo, service = setup
    record = service.submit(DEVELOPER, "cn-beijing", "r-demo", "请审核")
    record["snapshot"] = record.pop("agent")
    record["fingerprint"] = decode_record(repo.writes[-1])["fingerprint"]
    payload = base64.urlsafe_b64encode(
        zlib.compress(json.dumps(record).encode())
    ).decode()
    parts = [payload[i : i + 240] for i in range(0, len(payload), 240)]
    repo.runtime.tags = [
        tag for tag in repo.runtime.tags if not tag.key.startswith("veadk:review:")
    ]
    repo.write(
        "cn-beijing",
        "r-demo",
        {
            "veadk:review:id": record["id"],
            "veadk:review:status": "pending",
            "veadk:review:parts": str(len(parts)),
            **{f"veadk:review:data{i}": part for i, part in enumerate(parts)},
        },
    )
    assert service.read(DEVELOPER, "cn-beijing", "r-demo")["id"] == record["id"]
    service.decide(ADMIN, "cn-beijing", "r-demo", record["id"], "approved")
    assert "snapshot" not in decode_record(repo.writes[-1])
    assert service.read(DEVELOPER, "cn-beijing", "r-demo")["status"] == "approved"


def test_tag_quota_failure_does_not_write(setup):
    repo, service = setup
    repo.runtime.tags.extend(
        SimpleNamespace(key=f"other-{i}", value="x") for i in range(50)
    )
    with pytest.raises(HTTPException):
        service.submit(DEVELOPER, "cn-beijing", "r-demo")
    assert not repo.writes
