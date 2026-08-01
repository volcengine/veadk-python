# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0

"""Tests for the same-origin managed-agent WebUI proxy."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing_extensions import Self

from veadk.cli.frontend_agent_proxy import (
    _rewrite_body,
    mount_agent_surface_proxy_routes,
)
from veadk.cli.frontend_sandbox_proxy import SandboxProxyTarget


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
