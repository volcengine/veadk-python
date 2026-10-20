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

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.testclient import TestClient

from frontend.server.website_integration import (
    InMemoryWebsiteIntegrationService,
    mount_routes,
)
from frontend.server.website_integration.service import normalize_domain


class _RejectBrowserOriginMiddleware:
    """Mirror the ADK app's origin guard around Studio routes."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        headers = dict(scope.get("headers", []))
        if scope.get("type") == "http" and b"origin" in headers:
            response = PlainTextResponse(
                "Forbidden: origin not allowed", status_code=403
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _app() -> tuple[FastAPI, list[tuple[str, str]], list[dict[str, Any]]]:
    app = FastAPI()
    app.add_middleware(_RejectBrowserOriginMiddleware)
    authorized: list[tuple[str, str]] = []
    invocations: list[dict[str, Any]] = []

    async def invoke(integration: Any, payload: dict[str, Any]):
        invocations.append({"integration": integration, "payload": payload})

        async def stream():
            yield b'data: {"content":{"parts":[{"text":"hello"}]}}\n\n'

        return StreamingResponse(stream(), media_type="text/event-stream")

    mount_routes(
        app,
        InMemoryWebsiteIntegrationService(),
        owner_id=lambda request: request.headers.get("x-owner", "local"),
        authorize_runtime=lambda _request, runtime_id, region: authorized.append(
            (runtime_id, region)
        ),
        invoke_runtime=invoke,
    )
    return app, authorized, invocations


def _create(client: TestClient, *, domain: str = "example.com") -> dict[str, Any]:
    response = client.post(
        "/web/website-integrations",
        headers={"x-owner": "owner-a"},
        json={
            "domain": domain,
            "runtimeId": "runtime-1",
            "runtimeName": "Runtime One",
            "region": "cn-beijing",
            "appName": "agent",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_management_routes_scope_integrations_by_owner() -> None:
    app, authorized, _ = _app()
    client = TestClient(app)
    created = _create(client)

    assert created["token"].startswith("wsi_")
    assert len(created["token"]) >= 40
    assert authorized == [("runtime-1", "cn-beijing")]
    assert client.get(
        "/web/website-integrations", headers={"x-owner": "owner-b"}
    ).json() == {"integrations": []}
    assert (
        client.get("/web/website-integrations", headers={"x-owner": "owner-a"}).json()[
            "integrations"
        ][0]["id"]
        == created["id"]
    )

    forbidden = client.delete(
        f"/web/website-integrations/{created['id']}",
        headers={"x-owner": "owner-b"},
    )
    assert forbidden.status_code == 404
    assert (
        client.delete(
            f"/web/website-integrations/{created['id']}",
            headers={"x-owner": "owner-a"},
        ).status_code
        == 204
    )


def test_generated_tokens_are_unique() -> None:
    app, _, _ = _app()
    client = TestClient(app)
    first = _create(client)
    second = _create(client, domain="www.example.com")
    assert first["token"] != second["token"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("EXAMPLE.com", "example.com"),
        ("https://Example.com", "example.com"),
        ("localhost:5173", "localhost:5173"),
        ("127.0.0.1:8000", "127.0.0.1:8000"),
    ],
)
def test_normalize_domain(value: str, expected: str) -> None:
    assert normalize_domain(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "*.example.com", "example.com/path", "example.com?x=1", "user@example.com"],
)
def test_normalize_domain_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_domain(value)


def test_bootstrap_requires_matching_browser_origin() -> None:
    app, _, _ = _app()
    client = TestClient(app)
    created = _create(client)

    allowed = client.post(
        "/embed/session",
        headers={"origin": "https://example.com"},
        json={"token": created["token"]},
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://example.com"
    assert allowed.json()["sessionToken"].startswith("wsis_")

    denied = client.post(
        "/embed/session",
        headers={"origin": "https://attacker.example"},
        json={"token": created["token"]},
    )
    assert denied.status_code == 403

    missing = client.post(
        "/embed/session",
        json={"token": created["token"]},
    )
    assert missing.status_code == 403

    studio_api = client.get(
        "/web/website-integrations",
        headers={"origin": "https://example.com"},
    )
    assert studio_api.status_code == 403
    assert studio_api.text == "Forbidden: origin not allowed"


def test_configured_port_must_match_origin() -> None:
    app, _, _ = _app()
    client = TestClient(app)
    created = _create(client, domain="localhost:5173")

    assert (
        client.post(
            "/embed/session",
            headers={"origin": "http://localhost:5173"},
            json={"token": created["token"]},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/embed/session",
            headers={"origin": "http://localhost:3000"},
            json={"token": created["token"]},
        ).status_code
        == 403
    )


def test_chat_uses_session_binding_and_server_owned_runtime_payload() -> None:
    app, _, invocations = _app()
    client = TestClient(app)
    created = _create(client)
    bootstrap = client.post(
        "/embed/session",
        headers={"origin": "https://example.com"},
        json={"token": created["token"]},
    ).json()

    unauthorized = client.post(
        "/embed/run_sse",
        headers={"origin": "https://example.com"},
        json={
            "message": "ignored",
            "userId": "visitor-1",
            "sessionId": "session-1",
            "appName": "stolen",
        },
    )
    assert unauthorized.status_code == 401

    wrong_origin = client.post(
        "/embed/run_sse",
        headers={
            "authorization": f"Bearer {bootstrap['sessionToken']}",
            "origin": "https://attacker.example",
        },
        json={
            "message": "ignored",
            "userId": "visitor-1",
            "sessionId": "session-1",
        },
    )
    assert wrong_origin.status_code == 403

    response = client.post(
        "/embed/run_sse",
        headers={
            "authorization": f"Bearer {bootstrap['sessionToken']}",
            "origin": "https://example.com",
        },
        json={
            "message": "你好",
            "userId": "visitor-1",
            "sessionId": "session-1",
            "appName": "stolen",
            "runtimeId": "stolen",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "hello" in response.text
    assert invocations[0]["integration"].runtime_id == "runtime-1"
    assert invocations[0]["payload"] == {
        "app_name": "agent",
        "user_id": "visitor-1",
        "session_id": "session-1",
        "new_message": {"role": "user", "parts": [{"text": "你好"}]},
        "streaming": True,
    }
