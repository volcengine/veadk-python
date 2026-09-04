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

"""Tests for the same-origin managed-agent WebUI proxy."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from starlette.websockets import WebSocketDisconnect
from fastapi.testclient import TestClient
from typing_extensions import Self

from veadk.cli.frontend_agent_proxy import (
    _rewrite_body,
    _websocket_origin,
    mount_agent_surface_proxy_routes,
)
from veadk.cli.frontend_sandbox_proxy import SandboxProxyTarget


def test_hermes_port_proxy_websocket_uses_local_service_origin() -> None:
    target = "https://sandbox.example/proxy/4500/api/ws?Authorization=secret"

    assert (
        _websocket_origin("hermes", "proxy/4500/api/ws", target)
        == "http://localhost:4500"
    )
    assert (
        _websocket_origin("openclaw", "openclaw/api/ws", target)
        == "https://sandbox.example"
    )


def test_agent_surface_rewrite_only_changes_the_agent_base_path() -> None:
    prefix = "/web/hermes/sessions/session-1/surface/token-1"
    body = (
        b'<script>const slash = "/"; const api = "/api/status";'
        b'window.__HERMES_BASE_PATH__ = "/hermes";</script>'
        b'<script src="/hermes/assets/app.js"></script>'
    )

    rewritten = _rewrite_body(body, "text/html", prefix, "hermes").decode()

    assert 'const slash = "/"' in rewritten
    assert 'const api = "/api/status"' in rewritten
    assert f'window.__HERMES_BASE_PATH__ = "{prefix}/hermes"' in rewritten
    assert f'src="{prefix}/hermes/assets/app.js"' in rewritten


def test_hermes_surface_rewrite_removes_private_gateway_query() -> None:
    prefix = "/web/hermes/sessions/session-1/surface/token-1"
    body = (
        b'<script src="/hermes/assets/app.js?faasInstanceName=hermes-instance'
        b'&amp;Authorization=hermes-secret&amp;theme=dark"></script>'
        b'<link href="./assets/app.css?Authorization=hermes-secret" rel="stylesheet">'
        b'<link href="./favicon.ico?faasInstanceName=hermes-instance" rel="icon">'
    )

    rewritten = _rewrite_body(body, "text/html", prefix, "hermes").decode()

    assert f'src="{prefix}/hermes/assets/app.js?theme=dark"' in rewritten
    assert 'href="./assets/app.css"' in rewritten
    assert 'href="./favicon.ico"' in rewritten
    assert "faasInstanceName" not in rewritten
    assert "Authorization" not in rewritten
    assert "hermes-instance" not in rewritten
    assert "hermes-secret" not in rewritten


def test_hermes_aio_rewrite_routes_workspace_panels_through_surface() -> None:
    prefix = "/web/hermes/sessions/session-1/surface/token-1"
    body = (
        b'<script>const code = "/code-server/";'
        b'const terminal = "/terminal";'
        b'const jupyter = "/jupyter/lab";'
        b'const api = "/v1/ping";'
        b"const proxy = `/proxy/8642/v1/chat/completions`;</script>"
        b'<link href="/static/sandbox/app.css" rel="stylesheet">'
    )

    rewritten = _rewrite_body(body, "text/html", prefix, "hermes").decode()

    for path in (
        "/code-server/",
        "/terminal",
        "/jupyter/lab",
        "/v1/ping",
        "/proxy/8642/v1/chat/completions",
        "/static/sandbox/app.css",
    ):
        assert f"{prefix}{path}" in rewritten


def test_hermes_aio_entrypoint_keeps_its_relative_panel_resolution() -> None:
    prefix = "/web/hermes/sessions/session-1/surface/token-1"
    body = (
        b"<html><head><title>AIO Sandbox</title></head>"
        b'<script>const code = "/code-server/";'
        b'const terminal = "/terminal";</script></html>'
    )

    rewritten = _rewrite_body(body, "text/html", prefix, "hermes").decode()

    assert 'const code = "/code-server/"' in rewritten
    assert 'const terminal = "/terminal"' in rewritten
    assert f"{prefix}/code-server/" not in rewritten


@pytest.mark.parametrize("proxy_kind", ["proxy", "absproxy"])
@pytest.mark.parametrize("port", ["4500", "9119"])
def test_hermes_dashboard_rewrite_preserves_its_port_proxy_mount(
    proxy_kind: str,
    port: str,
) -> None:
    prefix = "/web/hermes/sessions/session-1/surface/token-1"
    body = (
        b"<html><head><title>Hermes Agent - Dashboard</title>"
        b'<link rel="icon" href="/favicon.ico">'
        b'<script type="module" src="/assets/app.js"></script></head>'
        b'<script>const api = "/api/status";'
        b'const ws = new WebSocket("/api/ws");'
        b'const files = "/files";'
        b'const chat = "/chat";'
        b'const logs = "/logs";'
        b'const cron = "/cron";'
        b'const channels = "/channels";'
        b'const mcp = "/mcp";</script></html>'
    )

    rewritten = _rewrite_body(
        body,
        "text/html",
        prefix,
        "hermes",
        upstream_path=f"{proxy_kind}/{port}/",
    ).decode()

    for path in (
        "/favicon.ico",
        "/assets/app.js",
        "/api/status",
        "/api/ws",
        "/files",
        "/chat",
        "/logs",
        "/cron",
        "/channels",
        "/mcp",
    ):
        assert f"{prefix}/{proxy_kind}/{port}{path}" in rewritten


def test_deepseek_harness_rewrite_routes_root_assets_through_surface() -> None:
    prefix = "/web/deepseek-harness/sessions/session-1/surface/token-1"
    body = (
        b'<html><head><script src="/deepseek-harness-auth-query.js?Authorization=secret">'
        b"</script>"
        b'<script>const slash = "/"; const api = "/api/status";'
        b'const ws = new WebSocket("/api/events");'
        b'window.__DSH_BASE_PATH__ = "/deepseek-harness";</script>'
        b'<script src="/assets/app.js"></script>'
        b'<link href="/plugins/plugin-a/index.css" rel="stylesheet">'
        b"</head></html>"
    )

    rewritten = _rewrite_body(
        body,
        "text/html",
        prefix,
        "deepseek-harness",
    ).decode()

    assert 'const slash = "/"' in rewritten
    assert f'src="{prefix}/deepseek-harness-auth-query.js"' in rewritten
    assert 'const api = "/api/status"' in rewritten
    assert 'new WebSocket("/api/events")' in rewritten
    assert f'window.__DSH_BASE_PATH__ = "{prefix}/deepseek-harness"' in rewritten
    assert f'src="{prefix}/assets/app.js"' in rewritten
    assert f'href="{prefix}/plugins/plugin-a/index.css"' in rewritten
    assert f'const surfacePrefix = "{prefix}"' in rewritten
    assert "url.pathname = surfacePrefix + url.pathname" in rewritten
    assert "Authorization" not in rewritten
    assert "secret" not in rewritten


def test_deepseek_harness_rewrite_preserves_api_transport_semantics() -> None:
    prefix = "/web/deepseek-harness/sessions/session-1/surface/token-1"
    body = (
        b'const API_PATH = "/api";'
        b'connection.rpc.call("/api", endpoint, { args });'
        b"const response = await this.postJson(`/api/${method}`, message);"
    )

    rewritten = _rewrite_body(
        body,
        "text/javascript; charset=utf-8",
        prefix,
        "deepseek-harness",
    ).decode()

    assert rewritten == body.decode()


def test_agent_surface_proxy_keeps_endpoint_auth_server_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []

    class _Client:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def request(self, _method: str, url: str, **_: object) -> httpx.Response:
            requested_urls.append(url)
            return httpx.Response(
                200,
                content=(
                    b'<script src="/openclaw/assets/app.js"></script>'
                    b'<script>const base64 = "/"; const api = "/api/status";</script>'
                ),
                headers={"content-type": "text/html"},
            )

    monkeypatch.setattr("veadk.cli.frontend_agent_proxy.httpx.AsyncClient", _Client)
    app = FastAPI()

    def _target(kind: str, session_id: str, token: str) -> SandboxProxyTarget:
        if (kind, session_id, token) != ("openclaw", "session-1", "token-1"):
            raise KeyError(session_id)
        return SandboxProxyTarget(
            endpoint=(
                "https://sandbox.example/?faasInstanceName=instance-1"
                "&Authorization=server-secret"
            )
        )

    mount_agent_surface_proxy_routes(
        app,
        _target,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/openclaw/sessions/session-1/surface/token-1/openclaw/"
        )

    assert response.status_code == 200
    expected_url = (
        "https://sandbox.example/openclaw/"
        "?faasInstanceName=instance-1&Authorization=server-secret"
    )
    assert requested_urls == [expected_url]
    assert (
        'src="/web/openclaw/sessions/session-1/surface/token-1/openclaw/assets/app.js"'
        in response.text
    )
    assert 'const base64 = "/"' in response.text
    assert 'const api = "/api/status"' in response.text
    assert "server-secret" not in response.text


def test_agent_surface_proxy_accepts_async_target_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def request(self, _method: str, _url: str, **_: object) -> httpx.Response:
            return httpx.Response(
                200, content=b"ok", headers={"content-type": "text/plain"}
            )

    monkeypatch.setattr("veadk.cli.frontend_agent_proxy.httpx.AsyncClient", _Client)
    app = FastAPI()

    async def _target(
        kind: str,
        session_id: str,
        token: str,
    ) -> SandboxProxyTarget:
        assert (kind, session_id, token) == ("hermes", "session-1", "token-1")
        return SandboxProxyTarget(endpoint="https://sandbox.example/")

    mount_agent_surface_proxy_routes(app, _target)

    with TestClient(app) as client:
        response = client.get(
            "/web/hermes/sessions/session-1/surface/token-1/proxy/4500/"
        )

    assert response.status_code == 200
    assert response.text == "ok"


def test_agent_surface_websocket_upgrades_before_invalid_capability_close() -> None:
    app = FastAPI()

    def _missing_target(
        _kind: str,
        _session_id: str,
        _token: str,
    ) -> SandboxProxyTarget:
        raise KeyError("expired session")

    mount_agent_surface_proxy_routes(app, _missing_target)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(
                "/web/hermes/sessions/expired/surface/expired/proxy/4500/api/pty"
            ) as websocket:
                websocket.receive_text()

    assert error.value.code == 1008


def test_deepseek_harness_proxy_keeps_endpoint_auth_server_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []

    class _Client:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def request(self, _method: str, url: str, **_: object) -> httpx.Response:
            requested_urls.append(url)
            return httpx.Response(
                200,
                content=b'<script>fetch("/api/status")</script>',
                headers={"content-type": "text/html"},
            )

    monkeypatch.setattr("veadk.cli.frontend_agent_proxy.httpx.AsyncClient", _Client)
    app = FastAPI()

    def _target(kind: str, session_id: str, token: str) -> SandboxProxyTarget:
        if (kind, session_id, token) != (
            "deepseek-harness",
            "session-1",
            "token-1",
        ):
            raise KeyError(session_id)
        return SandboxProxyTarget(
            endpoint=(
                "https://sandbox.example/?faasInstanceName=instance-1"
                "&Authorization=server-secret"
            )
        )

    mount_agent_surface_proxy_routes(app, _target)

    with TestClient(app) as client:
        response = client.get(
            "/web/deepseek-harness/sessions/session-1/surface/token-1/api/status"
        )

    assert response.status_code == 200
    expected_url = (
        "https://sandbox.example/api/status"
        "?faasInstanceName=instance-1&Authorization=server-secret"
    )
    assert requested_urls == [expected_url]
    assert 'fetch("/api/status")' in response.text
    assert "server-secret" not in response.text


def test_hermes_proxy_forwards_the_session_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forwarded_headers: list[dict[str, str]] = []

    class _Client:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def request(
            self,
            _method: str,
            _url: str,
            **kwargs: object,
        ) -> httpx.Response:
            forwarded_headers.append(dict(kwargs["headers"]))  # type: ignore[arg-type]
            return httpx.Response(
                200,
                json={"authenticated": True},
                headers={"content-type": "application/json"},
            )

    monkeypatch.setattr("veadk.cli.frontend_agent_proxy.httpx.AsyncClient", _Client)
    app = FastAPI()

    def _target(kind: str, session_id: str, token: str) -> SandboxProxyTarget:
        assert (kind, session_id, token) == ("hermes", "session-1", "proxy-1")
        return SandboxProxyTarget(
            endpoint="https://sandbox.example/?Authorization=secret"
        )

    mount_agent_surface_proxy_routes(app, _target)

    with TestClient(app) as client:
        response = client.get(
            "/web/hermes/sessions/session-1/surface/proxy-1/hermes/api/auth/me",
            headers={"X-Hermes-Session-Token": "hermes-session-token"},
        )

    assert response.status_code == 200
    assert forwarded_headers[0]["x-hermes-session-token"] == "hermes-session-token"
