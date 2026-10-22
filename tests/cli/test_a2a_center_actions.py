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

"""A2A management uses explicit scopes and never deletes source Runtimes."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server.a2a_center import mount_routes

AGENT = {
    "Id": "a-one",
    "A2aSpaceId": "as-one",
    "Name": "Research",
    "Status": "running",
    "Source": "Runtime",
    "DefaultVersion": "1",
    "RuntimeConfig": {"RuntimeId": "r-source", "NetworkType": "public"},
    "AgentCard": "private-card",
    "Reason": "private-error",
    "StandardConfig": {"AgentCardUrl": "https://example.test/?token=private"},
}


def setup_actions(*, bound=None, count=0, default=False, agent=None):
    app = FastAPI()

    async def dispatch(*, action, **_):
        return {
            "Result": {
                "GetA2aAgent": agent if agent is not None else AGENT,
                "GetA2aSpace": {"Id": "as-one", "IsDefault": default},
                "ListA2aAgents": {"Items": [], "TotalCount": count},
            }.get(action, {})
        }

    cloud = AsyncMock(side_effect=dispatch)
    admin, authorize = Mock(), Mock()
    runtime_request = AsyncMock(return_value={"space_id": bound, "revision": 1})
    mount_routes(
        app,
        admin=admin,
        authorize=authorize,
        region_for=lambda r: r or "cn-beijing",
        cloud=cloud,
        runtime_request=runtime_request,
    )
    return TestClient(app), cloud, admin, authorize, runtime_request


QUERY = "?targetRuntimeId=r-target&spaceId=as-one&region=cn-beijing"
SPACE_QUERY = "?targetRuntimeId=r-target&region=cn-beijing"


def test_details_are_scoped_and_do_not_return_cards_or_urls():
    client, cloud, _, authorize, _ = setup_actions()
    response = client.get("/web/a2a-agents/a-one" + QUERY)
    assert response.status_code == 200
    assert response.json()["name"] == "Research"
    assert response.json()["runtimeId"] == "r-source"
    assert "private" not in response.text
    authorize.assert_called_once()
    cloud.assert_awaited_once_with(
        region="cn-beijing",
        action="GetA2aAgent",
        payload={"Id": "a-one", "SpaceId": "as-one"},
    )


@pytest.mark.parametrize("method", ["get", "delete"])
def test_wrong_space_identity_fails_closed(method):
    client, cloud, *_ = setup_actions(agent={**AGENT, "A2aSpaceId": "as-other"})
    response = getattr(client, method)("/web/a2a-agents/a-one" + QUERY)
    assert response.status_code == 502
    assert all(
        call.kwargs["action"] != "DeleteA2aAgent" for call in cloud.await_args_list
    )


def test_deregister_only_deletes_the_verified_registration():
    client, cloud, *_ = setup_actions()
    response = client.delete("/web/a2a-agents/a-one" + QUERY)
    assert response.status_code == 200 and response.json() == {"deleted": True}
    assert [call.kwargs["action"] for call in cloud.await_args_list] == [
        "GetA2aAgent",
        "DeleteA2aAgent",
    ]
    assert cloud.await_args_list[-1].kwargs["payload"] == {"Id": "a-one"}


@pytest.mark.parametrize(
    "bound,count,default,reason",
    [
        ("as-one", 0, False, "space_bound"),
        (None, 1, False, "space_not_empty"),
    ],
)
def test_space_preflight_refusal_performs_no_delete(bound, count, default, reason):
    client, cloud, *_ = setup_actions(bound=bound, count=count, default=default)
    response = client.delete("/web/a2a-spaces/as-one" + SPACE_QUERY)
    assert response.status_code == 409 and response.json()["detail"]["reason"] == reason
    assert all(
        call.kwargs["action"] != "DeleteA2aSpace" for call in cloud.await_args_list
    )


def test_empty_unbound_space_is_deleted_with_exact_id():
    client, cloud, _, _, binding = setup_actions()
    response = client.delete("/web/a2a-spaces/as-one" + SPACE_QUERY)
    assert response.status_code == 200 and response.json() == {"deleted": True}
    assert binding.await_args is not None
    assert (
        binding.await_args.kwargs["path"]
        == "/api/v1/studio/collaborators/registry/binding"
    )
    assert cloud.await_args_list[-1].kwargs == {
        "region": "cn-beijing",
        "action": "DeleteA2aSpace",
        "payload": {"Id": "as-one"},
    }


@pytest.mark.parametrize(
    "path", ["/web/a2a-agents/a-one" + QUERY, "/web/a2a-spaces/as-one" + SPACE_QUERY]
)
@pytest.mark.parametrize("boundary", ["admin", "runtime"])
def test_delete_requires_authorization(path, boundary):
    client, cloud, admin, authorize, _ = setup_actions()
    (admin if boundary == "admin" else authorize).side_effect = HTTPException(
        403, "forbidden"
    )
    response = client.delete(path)
    assert response.status_code == 403
    cloud.assert_not_called()


def test_invalid_identity_never_reaches_cloud():
    client, cloud, *_ = setup_actions()
    response = client.delete("/web/a2a-agents/as-wrong" + QUERY)
    assert response.status_code == 422
    cloud.assert_not_called()


def test_network_delete_outcome_is_not_retried_or_exposed():
    client, cloud, *_ = setup_actions()
    cloud.side_effect = [{"Result": AGENT}, RuntimeError("private-error")]
    response = client.delete("/web/a2a-agents/a-one" + QUERY)
    assert response.status_code == 502
    assert "private-error" not in response.text
    assert cloud.await_count == 2


@pytest.mark.parametrize(
    "status,code,message,reason,expected",
    [
        (
            400,
            "InvalidParameter",
            "RuntimeId already exists, can't create agent",
            "runtime_already_registered",
            409,
        ),
        (403, "AccessDenied", "private-value", "forbidden", 403),
        (400, "InvalidParameter", "private-value", "invalid_parameter", 422),
        (500, "InternalError", "private-value", "outcome_unknown", 502),
    ],
)
def test_cloud_error_classification_is_safe(status, code, message, reason, expected):
    from frontend.server.a2a_center import cloud_error

    error = cloud_error(status, code, message)
    assert error.status == expected and error.reason == reason
    assert "private-value" not in str(error)


def test_runtime_duplicate_is_explicit_create_failure_not_uncertain():
    from frontend.server.a2a_center import cloud_error

    client, cloud, *_ = setup_actions()
    cloud.side_effect = cloud_error(
        400, "InvalidParameter", "RuntimeId already exists, can't create agent"
    )
    response = client.post(
        "/web/a2a-agents",
        json={
            "targetRuntimeId": "r-target",
            "spaceId": "as-one",
            "source": "Runtime",
            "runtimeId": "r-source",
            "networkType": "public",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "runtime_already_registered"
    assert cloud.await_count == 1


@pytest.mark.parametrize("value", [None, {"space_id": 123}, {}])
def test_invalid_binding_prevents_cloud_deletion(value):
    client, cloud, _, _, binding = setup_actions()
    binding.return_value = value
    response = client.delete("/web/a2a-spaces/as-one" + SPACE_QUERY)
    assert response.status_code == 502
    cloud.assert_not_called()


@pytest.mark.parametrize(
    "result",
    [
        {"Items": [], "TotalCount": -1},
        {"Items": [], "TotalCount": True},
        {"Items": None, "TotalCount": 0},
    ],
)
def test_invalid_membership_response_does_not_delete(result):
    client, cloud, *_ = setup_actions()
    cloud.side_effect = [{"Result": {"Id": "as-one"}}, {"Result": result}]
    response = client.delete("/web/a2a-spaces/as-one" + SPACE_QUERY)
    assert response.status_code == 502
    assert cloud.await_count == 2


def test_opt_in_signed_transport_preserves_refusal_without_changing_other_callers(
    monkeypatch,
):
    import ast
    import asyncio
    import json
    from pathlib import Path
    from typing import Any
    import httpx
    from frontend.server.a2a_center import A2ACenterCloudError

    source = Path("veadk/cli/cli_frontend.py").read_text()
    function = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_agentkit_openapi_post"
    )
    # Compile the actual nested helper to exercise transport without booting Studio.
    namespace = {
        "Any": Any,
        "json": json,
        "httpx": httpx,
        "HTTPException": HTTPException,
        "_agentkit_openapi_endpoint": lambda _: "https://agentkit.example.test",
        "_agentkit_openapi_headers": lambda **_: {},
    }
    exec(
        compile(
            ast.Module(body=[function], type_ignores=[]), "<signed helper>", "exec"
        ),
        namespace,
    )
    original = httpx.AsyncClient

    def respond(_):
        return httpx.Response(
            400,
            json={
                "ResponseMetadata": {
                    "Error": {
                        "Code": "InvalidParameter",
                        "Message": "RuntimeId already exists, can't create agent",
                    }
                }
            },
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    )
    call = namespace["_agentkit_openapi_post"]
    with pytest.raises(A2ACenterCloudError) as error:
        asyncio.run(
            call(
                region="cn-beijing",
                action="CreateA2aAgent",
                payload={},
                structured_errors=True,
            )
        )
    assert (
        error.value.status == 409 and error.value.reason == "runtime_already_registered"
    )
    with pytest.raises(RuntimeError, match="HTTP 400") as legacy:
        asyncio.run(call(region="cn-beijing", action="UnrelatedAction", payload={}))
    assert not isinstance(legacy.value, A2ACenterCloudError)


def test_unknown_source_fails_closed_before_deregistration():
    client, cloud, *_ = setup_actions(agent={**AGENT, "Source": "Other"})
    response = client.delete("/web/a2a-agents/a-one" + QUERY)
    assert response.status_code == 502
    assert cloud.await_count == 1


def test_failed_read_preflight_is_not_reported_as_uncertain_delete():
    from frontend.server.a2a_center import cloud_error

    client, cloud, *_ = setup_actions()
    cloud.side_effect = cloud_error(502)
    response = client.delete("/web/a2a-agents/a-one" + QUERY)
    assert response.status_code == 502
    assert response.json()["detail"]["reason"] == "read_failed"
    assert cloud.await_count == 1


def test_explicit_duplicate_business_message_is_preserved_even_with_5xx_status():
    from frontend.server.a2a_center import cloud_error

    error = cloud_error(
        500, "InternalError", "RuntimeId already exists, can't create agent"
    )
    assert error.status == 409 and error.reason == "runtime_already_registered"


def test_default_marker_does_not_invent_a_local_cloud_deletion_policy():
    client, cloud, *_ = setup_actions(default=True)
    response = client.delete("/web/a2a-spaces/as-one" + SPACE_QUERY)
    assert response.status_code == 200
    assert cloud.await_args_list[-1].kwargs["action"] == "DeleteA2aSpace"


@pytest.mark.parametrize("status", [401, 403])
def test_binding_auth_failure_is_safe_and_never_calls_cloud(status):
    client, cloud, _, _, binding = setup_actions()
    binding.side_effect = HTTPException(status, "private-upstream-credential")
    response = client.delete("/web/a2a-spaces/as-one" + SPACE_QUERY)
    assert response.status_code == status
    assert response.json() == {"detail": {"reason": "runtime_auth_failed"}}
    cloud.assert_not_called()


@pytest.mark.parametrize("serialized", [False, True])
def test_details_project_service_address_and_skills_without_card_credentials(
    serialized,
):
    import json

    card = {
        "url": "https://agent.example/a2a?token=private-value#private-value",
        "securitySchemes": {"secret": "private-value"},
        "skills": [
            {
                "id": "weather",
                "name": "Weather",
                "description": "Forecast",
                "tags": ["weather"],
                "examples": ["Hangzhou today"],
            }
        ],
    }
    client, cloud, *_ = setup_actions(
        agent={**AGENT, "AgentCard": json.dumps(card) if serialized else card}
    )
    response = client.get("/web/a2a-agents/a-one" + QUERY)
    assert response.status_code == 200
    assert response.json()["serviceAddress"] == "https://agent.example/a2a"
    assert response.json()["skills"] == card["skills"]
    assert response.json()["skillsTruncated"] is False
    assert (
        "private-value" not in response.text and "securitySchemes" not in response.text
    )
    assert cloud.await_count == 1


@pytest.mark.parametrize(
    "card",
    [None, "not-json", "x" * (128 * 1024 + 1), {"skills": "invalid"}],
    ids=["missing", "malformed", "oversized", "invalid-skills"],
)
def test_unavailable_card_metadata_is_explicit_without_hiding_basic_details(card):
    client, _, *_ = setup_actions(agent={**AGENT, "AgentCard": card})
    response = client.get("/web/a2a-agents/a-one" + QUERY)
    assert response.status_code == 200
    assert response.json()["name"] == "Research"
    assert response.json()["skills"] is None
    assert response.json()["serviceAddress"] is None


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://private-value@agent.example/a2a",
        "https://agent.example:bad/a2a",
        "https://agent.example/\nsecret",
    ],
)
def test_unsafe_service_addresses_are_not_exposed(url):
    client, _, *_ = setup_actions(
        agent={**AGENT, "AgentCard": {"url": url, "skills": []}}
    )
    response = client.get("/web/a2a-agents/a-one" + QUERY)
    assert response.json()["serviceAddress"] is None
    assert response.json()["skills"] == []
    assert "private-value" not in response.text


def test_skill_limits_and_empty_state_are_explicit():
    skill = {"id": "s", "name": "Skill", "description": "", "tags": [], "examples": []}
    client, _, *_ = setup_actions(
        agent={**AGENT, "AgentCard": {"skills": [skill] * 101}}
    )
    data = client.get("/web/a2a-agents/a-one" + QUERY).json()
    assert len(data["skills"]) == 100 and data["skillsTruncated"] is True
    client, _, *_ = setup_actions(agent={**AGENT, "AgentCard": {"skills": []}})
    assert client.get("/web/a2a-agents/a-one" + QUERY).json()["skills"] == []


@pytest.mark.parametrize(
    "network_types", [["public"], ["private"], ["public", "private"], []]
)
def test_runtime_endpoint_read_uses_both_authorizations_and_sanitized_configuration(
    network_types,
):
    from types import SimpleNamespace

    client, cloud, admin, authorize, _ = setup_actions()
    authorize.return_value = SimpleNamespace(
        network_configurations=[
            SimpleNamespace(
                network_type=kind,
                endpoint=f"https://{kind}.example/runtime?token=private-value",
            )
            for kind in network_types
        ]
    )
    response = client.get("/web/a2a-runtime-endpoints/r-source" + SPACE_QUERY)
    assert response.status_code == 200
    assert response.json() == {
        "runtimeId": "r-source",
        "endpoints": [
            {"networkType": kind, "url": f"https://{kind}.example/runtime"}
            for kind in network_types
        ],
    }
    assert [call.args[1] for call in authorize.call_args_list] == [
        "r-target",
        "r-source",
    ]
    admin.assert_called_once()
    cloud.assert_not_called()
    assert "private-value" not in response.text


@pytest.mark.parametrize("boundary", ["admin", "source"])
def test_runtime_endpoint_read_does_not_bypass_authorization(boundary):
    client, cloud, admin, authorize, _ = setup_actions()
    if boundary == "admin":
        admin.side_effect = HTTPException(403, "denied")
    else:
        authorize.side_effect = [object(), HTTPException(403, "denied")]
    response = client.get("/web/a2a-runtime-endpoints/r-source" + SPACE_QUERY)
    assert response.status_code == 403
    cloud.assert_not_called()


def test_runtime_endpoint_projection_rejects_unsafe_and_duplicate_entries():
    from types import SimpleNamespace

    client, _, _, authorize, _ = setup_actions()
    authorize.return_value = SimpleNamespace(
        network_configurations=[
            SimpleNamespace(
                network_type="public", endpoint="https://private-value@bad.example"
            ),
            SimpleNamespace(
                network_type="public", endpoint="https://safe.example/runtime#fragment"
            ),
            SimpleNamespace(
                network_type="public", endpoint="https://duplicate.example"
            ),
            SimpleNamespace(network_type="private", endpoint="javascript:alert(1)"),
            SimpleNamespace(network_type="unknown", endpoint="https://unknown.example"),
        ]
    )
    data = client.get("/web/a2a-runtime-endpoints/r-source" + SPACE_QUERY).json()
    assert data["endpoints"] == [
        {"networkType": "public", "url": "https://safe.example/runtime"}
    ]


@pytest.mark.parametrize(
    "skill",
    [
        {"id": "s", "name": "x" * 513},
        {"id": "s", "name": "Skill", "tags": ["x"] * 21},
        {"id": "s", "name": "Skill", "examples": ["x" * 1025]},
        {"id": "s", "name": "Skill", "description": {}},
    ],
)
def test_invalid_skill_metadata_is_unavailable_without_affecting_service_address(skill):
    client, _, *_ = setup_actions(
        agent={
            **AGENT,
            "AgentCard": {"url": "https://safe.example/a2a", "skills": [skill]},
        }
    )
    data = client.get("/web/a2a-agents/a-one" + QUERY).json()
    assert data["serviceAddress"] == "https://safe.example/a2a"
    assert data["skills"] is None


def test_optional_malformed_card_does_not_change_deregistration_eligibility():
    client, cloud, *_ = setup_actions(agent={**AGENT, "AgentCard": "malformed"})
    assert client.delete("/web/a2a-agents/a-one" + QUERY).status_code == 200
    assert cloud.await_args_list[-1].kwargs["action"] == "DeleteA2aAgent"
