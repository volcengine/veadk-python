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
from frontend.server.agent_reviews.tags import write_runtime_tags


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
