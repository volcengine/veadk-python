"""Studio registers in AgentKit, with no per-MPA registration copy."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server.a2a_center import mount_routes

CARD = {"name": "Research", "url": "https://agent.example/a2a", "version": "1"}


def setup_app():
    app = FastAPI()
    cloud = AsyncMock(
        return_value={"Result": {"Id": "a-new", "AgentCard": "do-not-return"}}
    )
    admin = Mock()
    authorize = Mock()
    mount_routes(
        app,
        admin=admin,
        authorize=authorize,
        region_for=lambda r: r or "cn-beijing",
        cloud=cloud,
    )
    return TestClient(app), cloud, admin, authorize


@pytest.mark.parametrize(
    "specific,expected",
    [
        (
            {"source": "Runtime", "runtimeId": "r-source", "networkType": "public"},
            {
                "Source": "Runtime",
                "RuntimeConfig": {"RuntimeId": "r-source", "NetworkType": "public"},
            },
        ),
        (
            {
                "source": "Standard",
                "importType": "url",
                "cardUrl": "https://agent.example/card",
            },
            {
                "Source": "Standard",
                "StandardConfig": {
                    "ImportType": "url",
                    "AgentCardUrl": "https://agent.example/card",
                },
            },
        ),
        (
            {"source": "Standard", "importType": "json", "agentCard": CARD},
            {"Source": "Standard", "StandardConfig": {"ImportType": "json"}},
        ),
    ],
)
def test_sources_are_forwarded_to_official_center(specific, expected):
    client, cloud, admin, authorize = setup_app()
    with client:
        result = client.post(
            "/web/a2a-agents?region=cn-beijing",
            json={"targetRuntimeId": "r-mpa", "spaceId": "as-one", **specific},
        )
    assert result.status_code == 201
    assert result.json() == {"id": "a-new"}
    admin.assert_called_once()
    assert authorize.call_args_list[0].args[1:] == ("r-mpa", "cn-beijing")
    payload = cloud.call_args.kwargs["payload"]
    assert cloud.call_args.kwargs["action"] == "CreateA2aAgent"
    assert payload.items() >= expected.items()
    assert payload["A2aSpaceId"] == "as-one"
    assert payload["SetDefaultVersion"] is True
    if specific.get("importType") == "json":
        import json

        assert json.loads(payload["AgentCard"]) == CARD
    if specific["source"] == "Runtime":
        assert authorize.call_args_list[-1].args[1:] == ("r-source", "cn-beijing")


@pytest.mark.parametrize(
    "override",
    [
        {"source": "Other"},
        {"spaceId": "bad"},
        {"targetRuntimeId": ""},
        {"source": "Standard", "importType": "url", "cardUrl": "http://127.0.0.1/card"},
        {
            "source": "Standard",
            "importType": "url",
            "cardUrl": "https://secret@agent.example/card",
        },
        {"source": "Standard", "importType": "json", "agentCard": {}},
        {
            "source": "Standard",
            "importType": "json",
            "agentCard": {"name": "x" * 140000},
        },
        {"source": "Runtime", "runtimeId": "r-source", "networkType": "invalid"},
        {"source": "Runtime", "runtimeId": "r-source", "agentCard": CARD},
    ],
)
def test_invalid_inputs_never_reach_cloud(override):
    client, cloud, _, _ = setup_app()
    with client:
        result = client.post(
            "/web/a2a-agents",
            json={"targetRuntimeId": "r-mpa", "spaceId": "as-one", **override},
        )
    assert result.status_code in {413, 422}
    assert "secret" not in result.text
    cloud.assert_not_called()


@pytest.mark.parametrize("boundary", ["admin", "runtime"])
def test_denied_request_cannot_create(boundary):
    client, cloud, admin, authorize = setup_app()
    (admin if boundary == "admin" else authorize).side_effect = HTTPException(
        403, "forbidden"
    )
    with client:
        response = client.post(
            "/web/a2a-agents",
            json={
                "targetRuntimeId": "r-mpa",
                "spaceId": "as-one",
                "source": "Runtime",
                "runtimeId": "r-source",
                "networkType": "public",
            },
        )
    assert response.status_code == 403
    cloud.assert_not_called()


def test_cloud_failure_is_sanitized_and_not_retried():
    client, cloud, _, _ = setup_app()
    cloud.side_effect = RuntimeError("secret-card-value")
    with client:
        response = client.post(
            "/web/a2a-agents",
            json={
                "targetRuntimeId": "r-mpa",
                "spaceId": "as-one",
                "source": "Standard",
                "importType": "json",
                "agentCard": CARD,
            },
        )
    assert response.status_code == 502
    assert "secret-card-value" not in response.text
    assert cloud.call_count == 1


def test_project_is_forwarded_and_card_is_never_persisted_locally():
    client, cloud, _, _ = setup_app()
    with client:
        response = client.post(
            "/web/a2a-agents",
            json={
                "targetRuntimeId": "r-mpa",
                "spaceId": "as-one",
                "projectName": "research",
                "source": "Standard",
                "importType": "json",
                "agentCard": CARD,
            },
        )
    assert response.status_code == 201
    assert cloud.call_args.kwargs["payload"]["ProjectName"] == "research"
    assert response.json() == {"id": "a-new"}


@pytest.mark.parametrize(
    "options,expected",
    [
        ({}, {"ProjectName": "default", "IntentEnabled": False}),
        (
            {"projectName": " research ", "intentEnabled": True},
            {"ProjectName": "research", "IntentEnabled": True},
        ),
    ],
)
def test_create_space_uses_authorized_identity_and_official_payload(options, expected):
    client, cloud, admin, authorize = setup_app()
    cloud.return_value = {"Result": {"Id": "as-new", "Tags": []}}
    with client:
        response = client.post(
            "/web/a2a-spaces?region=cn-beijing",
            json={
                "targetRuntimeId": "r-mpa",
                "name": " Team ",
                **options,
            },
        )
    assert response.status_code == 201
    assert response.json() == {"id": "as-new"}
    admin.assert_called_once()
    authorize.assert_called_once()
    assert authorize.call_args.args[1:] == ("r-mpa", "cn-beijing")
    cloud.assert_awaited_once_with(
        region="cn-beijing",
        action="CreateA2aSpace",
        payload={"Name": "Team", **expected},
    )


@pytest.mark.parametrize(
    "override",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 129},
        {"name": "a\x00b"},
        {"projectName": ""},
        {"projectName": "x" * 129},
        {"projectName": "a\nb"},
        {"intentEnabled": "false"},
        {"intentEnabled": 1},
        {"targetRuntimeId": "invalid"},
        {"Tags": []},
        {"name": "x" * 5000},
    ],
)
def test_invalid_space_input_never_creates(override):
    client, cloud, _, _ = setup_app()
    with client:
        response = client.post(
            "/web/a2a-spaces",
            json={"targetRuntimeId": "r-mpa", "name": "Team", **override},
        )
    assert response.status_code in {413, 422}
    cloud.assert_not_called()


@pytest.mark.parametrize("boundary", ["admin", "runtime"])
def test_space_creation_requires_both_authorization_boundaries(boundary):
    client, cloud, admin, authorize = setup_app()
    (admin if boundary == "admin" else authorize).side_effect = HTTPException(
        403, "forbidden"
    )
    with client:
        response = client.post(
            "/web/a2a-spaces", json={"targetRuntimeId": "r-mpa", "name": "Team"}
        )
    assert response.status_code == 403
    cloud.assert_not_called()


@pytest.mark.parametrize(
    "result", [RuntimeError("private-provider-detail"), {"Result": {"Id": "a-wrong"}}]
)
def test_space_unknown_outcome_is_sanitized_without_retry(result):
    client, cloud, _, _ = setup_app()
    if isinstance(result, Exception):
        cloud.side_effect = result
    else:
        cloud.return_value = result
    with client:
        response = client.post(
            "/web/a2a-spaces", json={"targetRuntimeId": "r-mpa", "name": "Team"}
        )
    assert response.status_code == 502
    assert "private-provider-detail" not in response.text
    assert cloud.call_count == 1
