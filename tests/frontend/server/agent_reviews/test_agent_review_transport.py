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

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from frontend.server.agent_reviews.access import authorize_shared_proxy
from frontend.server.agent_reviews.profiles import resolve_profile
from frontend.server.agent_reviews.repository import AgentReviewRepository
from frontend.server.agent_reviews.routes import cloud_error
from frontend.server.agent_reviews.tags import encode_record, write_runtime_tags


def test_cloud_error_preserves_original_body_status_and_log_id():
    body = json.dumps(
        {
            "ResponseMetadata": {
                "RequestId": "original-log-id",
                "Error": {"HTTPCode": 429, "Message": "请求过多"},
            }
        },
        ensure_ascii=False,
    )
    error = RuntimeError(f"Failed to TagResources: {body.encode()!r}")
    response = cloud_error(error)
    assert response.status_code == 429
    assert response.body.decode() == body


def test_tag_resources_uses_runtime_type_and_wire_aliases():
    sent = {}
    client = SimpleNamespace(
        api_info={}, _invoke_api=lambda **kwargs: sent.update(kwargs)
    )
    write_runtime_tags(client, "runtime-1", {"veadk:review:status": "approved"})
    assert sent["api_action"] == "TagResources"
    assert sent["request"].model_dump(by_alias=True) == {
        "ResourceType": "runtime",
        "ResourceIds": ["runtime-1"],
        "Tags": [{"Key": "veadk:review:status", "Value": "approved"}],
    }


def test_long_text_is_written_before_visibility_in_bounded_calls():
    calls = []
    client = SimpleNamespace(
        api_info={}, _invoke_api=lambda **kwargs: calls.append(kwargs)
    )
    values = encode_record(
        {
            "id": "review",
            "status": "approved",
            "comment": "😀" * 256,
            "reason": "，" * 256,
        }
    )
    write_runtime_tags(client, "runtime-1", values)
    assert len(calls) == 2
    sent = [call["request"].model_dump(by_alias=True)["Tags"] for call in calls]
    assert all(len(batch) <= 20 for batch in sent)
    assert not any(tag["Key"] == "veadk:visibility" for tag in sent[0])
    assert {tag["Key"]: tag["Value"] for tag in sent[-1]}[
        "veadk:visibility"
    ] == "enterprise"
    assert {tag["Key"]: tag["Value"] for batch in sent for tag in batch} == values


def test_failed_text_write_does_not_publish():
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("Cloud failed")

    client = SimpleNamespace(api_info={}, _invoke_api=fail)
    values = encode_record(
        {"id": "review", "status": "approved", "comment": "😀" * 256}
    )
    with pytest.raises(RuntimeError, match="Cloud failed"):
        write_runtime_tags(client, "runtime-1", values)
    assert len(calls) == 1
    assert all(tag.key != "veadk:visibility" for tag in calls[0]["request"].tags)


def test_review_api_enforces_text_boundaries():
    from pydantic import ValidationError
    from frontend.server.agent_reviews.routes import DecisionBody, ReviewBody

    ReviewBody(region="cn-beijing", message="字" * 20)
    DecisionBody(
        region="cn-beijing",
        applicationId="request",
        decision="returned",
        reason="😀" * 256,
    )
    with pytest.raises(ValidationError):
        ReviewBody(region="cn-beijing", message="字" * 21)
    with pytest.raises(ValidationError):
        DecisionBody(
            region="cn-beijing",
            applicationId="request",
            decision="returned",
            reason="字" * 257,
        )


def test_applicant_profile_resolves_deployment_subject_without_duplicate_tags():
    calls = []
    person = {
        "id": "subject-1",
        "name": "Author tag",
        "identityUid": "",
        "email": "",
        "avatarUrl": "",
    }

    def get_user(method, request):
        calls.append(request.user_uid)
        return SimpleNamespace(
            uid="uid-1",
            name="Owner profile",
            email="owner@example.test",
            picture="https://example.test/avatar.png",
        )

    directory = SimpleNamespace(
        pool_uid="pool",
        users=lambda: [SimpleNamespace(uid="uid-1", subject="subject-1")],
        _call=get_user,
    )
    result = resolve_profile(directory, person)
    assert result["name"] == "Owner profile"
    assert result["email"] == "owner@example.test"
    assert calls == ["uid-1"]


def test_list_uses_sdk_pagination_and_stops_repeated_tokens():
    requests = []

    def listing(request):
        requests.append(request.model_dump(by_alias=True))
        return SimpleNamespace(agent_kit_runtimes=["runtime"], next_token="same-token")

    repository = AgentReviewRepository("volcengine", lambda: ("", "", None))
    repository.client = lambda region: SimpleNamespace(list_runtimes=listing)
    with pytest.raises(RuntimeError, match="repeated Runtime page token"):
        list(repository.list("cn-beijing"))
    assert requests[0]["MaxResults"] == 100
    assert requests[1]["NextToken"] == "same-token"


def test_identity_profile_uses_directory_and_rejects_unsafe_avatar():
    calls = []

    def get_user(method, request):
        calls.append((method, request.user_uid))
        return SimpleNamespace(
            uid="uid-1",
            name="管理员姓名",
            email="admin@example.test",
            picture="javascript:alert(1)",
        )

    person = {
        "id": "owner",
        "identityUid": "uid-1",
        "name": "Stored name",
        "avatarUrl": "",
        "email": "",
    }
    result = resolve_profile(SimpleNamespace(pool_uid="pool", _call=get_user), person)
    assert result["name"] == "管理员姓名"
    assert result["email"] == "admin@example.test"
    assert result["avatarUrl"] == ""
    assert calls == [("get_user", "uid-1")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,payload",
    [
        ("run_sse", {"user_id": "viewer", "userId": "someone-else"}),
        ("run", {"user_id": "someone-else"}),
        ("run", []),
        ("apps/demo/users/viewer/sessions/../config", {}),
        ("apps/demo/users/viewer/sessions/%252e%252e/config", {}),
        ("apps/demo/users/other/sessions", {}),
    ],
)
async def test_shared_proxy_rejects_ambiguous_identity_and_traversal(path, payload):
    async def receive():
        return {"type": "http.request", "body": json.dumps(payload).encode()}

    request = Request(
        {"type": "http", "method": "POST", "path": path, "headers": []}, receive
    )
    principal = SimpleNamespace(identifiers=frozenset({"viewer"}))
    with pytest.raises(HTTPException) as failure:
        await authorize_shared_proxy(request, path, "POST", principal)
    assert failure.value.status_code == 403
