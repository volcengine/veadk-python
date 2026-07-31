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

"""Tests for Studio's disposable Hermes and OpenClaw iframe Sessions."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from veadk.cli.frontend_embedded_agents import (
    EmbeddedAgentService,
    _rewrite_text,
    _upstream_url,
    mount_embedded_agent_routes,
)
from veadk.cli.frontend_sandbox import (
    SandboxCloudSession,
    SandboxProvisioningError,
)


class _Gateway:
    def __init__(self, *, failed: bool = False) -> None:
        self.failed = failed
        self.deleted: list[SandboxCloudSession] = []
        self.created_tool_ids: list[str] = []

    async def create_session(
        self, tool_id: str, display_name: str = ""
    ) -> SandboxCloudSession:
        del display_name
        self.created_tool_ids.append(tool_id)
        return SandboxCloudSession(
            tool_id=tool_id,
            instance_id="session-1",
            user_session_id="user-session-1",
            endpoint="https://sandbox.example?Authorization=private",
            region="cn-beijing",
            status="Creating",
        )

    async def get_session(self, tool_id: str, session_id: str) -> SandboxCloudSession:
        return SandboxCloudSession(
            tool_id=tool_id,
            instance_id=session_id,
            user_session_id="user-session-1",
            endpoint="https://sandbox.example?Authorization=private",
            region="cn-beijing",
            status="Failed" if self.failed else "Ready",
            created_at="2026-07-31T08:00:00Z",
            expire_at="2026-07-31T16:00:00Z",
            tool_type="ArkClawEnv",
            webshell_url="/vnc/index.html",
            vnc_url="/terminal",
        )

    async def delete_session(self, session: SandboxCloudSession) -> None:
        self.deleted.append(session)

    async def drain(self) -> None:
        return None


async def _no_wait(_: float) -> None:
    return None


def _app(gateway: _Gateway) -> FastAPI:
    app = FastAPI()

    def _owner(request: Request) -> str:
        owner = request.headers.get("X-Test-User", "")
        if not owner:
            raise HTTPException(status_code=401, detail="identity required")
        return owner

    mount_embedded_agent_routes(
        app,
        EmbeddedAgentService(gateway, sleep=_no_wait),
        _owner,
    )
    return app


def test_openclaw_session_returns_only_same_origin_iframe_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_OPENCLAW_TOOL", "arkclaw-tool")
    gateway = _Gateway()
    with TestClient(_app(gateway)) as client:
        response = client.post(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "alice"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "openclaw"
        assert body["webuiUrl"] == ("/web/embedded/session-1/openclaw/webui/")
        assert body["terminalUrl"] == ("/web/embedded/session-1/openclaw/terminal/")
        assert "sandbox.example" not in response.text
        assert "private" not in response.text
        assert "HttpOnly" in response.headers["set-cookie"]

        denied = client.get(
            body["webuiUrl"],
            headers={"X-Test-User": "bob"},
        )
        assert denied.status_code == 404

        closed = client.delete(
            "/web/openclaw/sessions/session-1",
            headers={"X-Test-User": "alice"},
        )

    assert closed.status_code == 204
    assert gateway.created_tool_ids == ["arkclaw-tool"]
    assert [session.instance_id for session in gateway.deleted] == ["session-1"]


def test_missing_tool_configuration_disables_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_HERMES_TOOL", raising=False)
    with TestClient(_app(_Gateway())) as client:
        capability = client.get(
            "/web/hermes/capabilities",
            headers={"X-Test-User": "alice"},
        )
        create = client.post(
            "/web/hermes/sessions",
            headers={"X-Test-User": "alice"},
        )

    assert capability.status_code == 200
    assert capability.json()["enabled"] is False
    assert "SANDBOX_HERMES_TOOL" in capability.json()["reason"]
    assert create.status_code == 503


def test_failed_session_is_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_OPENCLAW_TOOL", "arkclaw-tool")
    gateway = _Gateway(failed=True)
    service = EmbeddedAgentService(gateway, sleep=_no_wait)

    async def _run() -> None:
        try:
            await service.start("openclaw", "alice")
        except SandboxProvisioningError:
            return
        raise AssertionError("failed AgentKit Session must not be returned")

    asyncio.run(_run())
    assert [session.instance_id for session in gateway.deleted] == ["session-1"]


def test_proxy_rewrites_agent_roots_without_exposing_endpoint_query() -> None:
    prefix = "/web/embedded/session-1/openclaw/webui"
    target = "https://sandbox.example/openclaw?Authorization=private"

    rewritten = _rewrite_text(
        (
            '<script src="/openclaw/assets/app.js"></script>'
            '<link href="/assets/base.css">'
            '<a href="https://sandbox.example/openclaw/share'
            '?Authorization=private&view=compact">share</a>'
        ),
        target=target,
        prefix=prefix,
    )

    assert f'src="{prefix}/assets/app.js"' in rewritten
    assert f'href="{prefix}/__root__/assets/base.css"' in rewritten
    assert (
        f'href="{prefix}/share?view=compact"' in rewritten
    )
    assert "sandbox.example" not in rewritten
    assert "private" not in rewritten
    upstream = _upstream_url(
        target,
        "api/messages",
        "page=1&Authorization=browser-value",
    )
    assert upstream == (
        "https://sandbox.example/openclaw/api/messages?page=1&Authorization=private"
    )
