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
from typing import cast

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.testclient import TestClient

import veadk.cli.frontend_embedded_agents as embedded_agents
from veadk.cli.frontend_embedded_agents import (
    EmbeddedAgentService,
    _rewrite_text,
    _target_from_endpoint,
    _upstream_url,
    mount_embedded_agent_routes,
)
from veadk.cli.frontend_sandbox import (
    SandboxCloudGateway,
    SandboxCloudSession,
    SandboxProvisioningError,
)


class _Gateway:
    def __init__(self, *, failed: bool = False) -> None:
        self.failed = failed
        self.deleted: list[SandboxCloudSession] = []
        self.created_tool_ids: list[str] = []
        self.created_envs: list[dict[str, str]] = []
        self.has_session = False

    async def list_sessions(self, tool_id: str) -> list[SandboxCloudSession]:
        if not self.has_session:
            return []
        return [await self.get_session(tool_id, "session-1")]

    async def create_session(
        self,
        tool_id: str,
        display_name: str = "",
        envs: dict[str, str] | None = None,
    ) -> SandboxCloudSession:
        del display_name
        self.created_tool_ids.append(tool_id)
        self.created_envs.append(envs or {})
        self.has_session = True
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


async def _ready_probe(_: str) -> int:
    return 200


def _app(gateway: _Gateway, *, allow_local_iframe: bool = False) -> FastAPI:
    app = FastAPI()

    def _owner(request: Request) -> str:
        owner = request.headers.get("X-Test-User", "")
        if not owner:
            raise HTTPException(status_code=401, detail="identity required")
        return owner

    def _proxy_owner(request: Request) -> str | None:
        owner = request.headers.get("X-Test-User", "")
        if owner:
            return owner
        if allow_local_iframe:
            return None
        raise HTTPException(status_code=401, detail="identity required")

    mount_embedded_agent_routes(
        app,
        EmbeddedAgentService(
            cast(SandboxCloudGateway, gateway),
            sleep=_no_wait,
            endpoint_probe=_ready_probe,
            session_env_resolver=lambda: {
                "MODEL_AGENT_API_KEY": "test-key",
                "MODEL_AGENT_NAME": "test-model",
            },
        ),
        _owner,
        _proxy_owner,
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

        disconnected = client.post(
            "/web/embedded/session-1/openclaw/disconnect",
            headers={"X-Test-User": "alice"},
        )
        deleted = client.delete(
            "/web/openclaw/sessions/session-1",
            headers={"X-Test-User": "alice"},
        )

    assert disconnected.status_code == 204
    assert deleted.status_code == 204
    assert gateway.created_tool_ids == ["arkclaw-tool"]
    assert gateway.created_envs == [
        {
            "MODEL_AGENT_API_KEY": "test-key",
            "MODEL_AGENT_NAME": "test-model",
        }
    ]
    assert [session.instance_id for session in gateway.deleted] == ["session-1"]


def test_local_iframe_uses_scoped_capability_without_custom_identity_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_OPENCLAW_TOOL", "arkclaw-tool")

    async def _proxy_stub(*args: object, **kwargs: object) -> Response:
        del args, kwargs
        return Response("proxied")

    monkeypatch.setattr(embedded_agents, "_proxy_http", _proxy_stub)

    with TestClient(_app(_Gateway(), allow_local_iframe=True)) as client:
        created = client.post(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "alice"},
        )
        iframe_url = created.json()["webuiUrl"]

        iframe = client.get(iframe_url)
        wrong_owner = client.get(
            iframe_url,
            headers={"X-Test-User": "bob"},
        )
        client.cookies.clear()
        missing_capability = client.get(iframe_url)

    assert iframe.status_code == 200
    assert iframe.text == "proxied"
    assert wrong_owner.status_code == 404
    assert missing_capability.status_code == 403


def test_existing_session_is_listed_and_can_be_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_OPENCLAW_TOOL", "arkclaw-tool")
    gateway = _Gateway()
    gateway.has_session = True

    with TestClient(_app(gateway)) as client:
        listed = client.get(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "alice"},
        )
        connected = client.post(
            "/web/openclaw/sessions/session-1/connect",
            headers={"X-Test-User": "alice"},
        )

    assert listed.status_code == 200
    assert listed.json()["sessions"] == [
        {
            "kind": "openclaw",
            "sessionId": "session-1",
            "userSessionId": "user-session-1",
            "displayName": "",
            "status": "Ready",
            "createdAt": "2026-07-31T08:00:00Z",
            "expireAt": "2026-07-31T16:00:00Z",
        }
    ]
    assert "sandbox.example" not in listed.text
    assert "private" not in listed.text
    assert connected.status_code == 200
    assert connected.json()["sessionId"] == "session-1"
    assert gateway.deleted == []


def test_leaving_studio_does_not_delete_cloud_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_OPENCLAW_TOOL", "arkclaw-tool")
    gateway = _Gateway()

    with TestClient(_app(gateway)) as client:
        created = client.post(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "alice"},
        )
        assert created.status_code == 200

    assert gateway.deleted == []


def test_authenticated_proxy_mode_still_requires_studio_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_OPENCLAW_TOOL", "arkclaw-tool")

    async def _proxy_stub(*args: object, **kwargs: object) -> Response:
        del args, kwargs
        return Response("proxied")

    monkeypatch.setattr(embedded_agents, "_proxy_http", _proxy_stub)

    with TestClient(_app(_Gateway())) as client:
        created = client.post(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "alice"},
        )
        iframe = client.get(created.json()["webuiUrl"])

    assert iframe.status_code == 401
    assert iframe.json()["detail"] == "identity required"


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
    service = EmbeddedAgentService(
        cast(SandboxCloudGateway, gateway),
        sleep=_no_wait,
        endpoint_probe=_ready_probe,
    )

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
    assert f'href="{prefix}/share?view=compact"' in rewritten
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


def test_endpoint_paths_are_appended_to_agentkit_prefix() -> None:
    assert _target_from_endpoint(
        "https://sandbox.example/runtime/root?Authorization=private",
        "/openclaw",
    ) == ("https://sandbox.example/runtime/root/openclaw?Authorization=private")
    assert _upstream_url(
        "https://sandbox.example/openclaw?Authorization=private",
        "",
        "view=compact",
        trailing_slash=True,
    ) == ("https://sandbox.example/openclaw/?view=compact&Authorization=private")


def test_terminal_rewrites_root_assets_and_websocket_base() -> None:
    prefix = "/web/embedded/session-1/openclaw/terminal"
    rewritten = _rewrite_text(
        (
            '<link href="static/sandbox/xterm.css">'
            '<script src="./static/sandbox/xterm.js"></script>'
            "<script>"
            "const baseUrl = window.location.origin + basePath;"
            "this.baseLocation = new URL('.', window.location.href);"
            "</script>"
        ),
        target="https://sandbox.example/terminal?Authorization=private",
        prefix=prefix,
        root_relative_assets=True,
    )

    assert f'href="{prefix}/__root__/static/sandbox/xterm.css"' in rewritten
    assert f'src="{prefix}/__root__/static/sandbox/xterm.js"' in rewritten
    assert f"window.location.origin + '{prefix}/__root__'" in rewritten
    assert "new URL(document.baseURI)" in rewritten
