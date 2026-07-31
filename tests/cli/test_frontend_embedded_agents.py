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
from types import SimpleNamespace
from typing import Self, cast

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
    AgentkitSandboxGateway,
    SandboxCloudGateway,
    SandboxCloudSession,
    SandboxProvisioningError,
)


class _Gateway:
    def __init__(
        self,
        *,
        failed: bool = False,
        tool_type: str = "ArkClawEnv",
    ) -> None:
        self.failed = failed
        self.tool_type = tool_type
        self.deleted: list[SandboxCloudSession] = []
        self.created_tool_ids: list[str] = []
        self.created_display_names: list[str] = []
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
        self.created_tool_ids.append(tool_id)
        self.created_display_names.append(display_name)
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
            tool_type=self.tool_type,
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


async def _ready_terminal_target(cloud: SandboxCloudSession) -> str:
    target = _target_from_endpoint(cloud.endpoint, "/terminal")
    separator = "&" if "?" in target else "?"
    return f"{target}{separator}session_id=native-shell-1"


async def _ready_openclaw_bootstrap(_: SandboxCloudSession) -> str:
    return "openclaw-bootstrap-token"


def _app(
    gateway: _Gateway,
    *,
    capability_secret: str = "test-shared-embedded-secret",
) -> FastAPI:
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
        return None

    mount_embedded_agent_routes(
        app,
        EmbeddedAgentService(
            cast(SandboxCloudGateway, gateway),
            sleep=_no_wait,
            endpoint_probe=_ready_probe,
            terminal_target_resolver=_ready_terminal_target,
            openclaw_bootstrap_resolver=_ready_openclaw_bootstrap,
            openclaw_gateway_token_factory=lambda: "openclaw-gateway-token",
            session_env_resolver=lambda: {
                "MODEL_AGENT_API_KEY": "test-key",
                "MODEL_AGENT_NAME": "test-model",
            },
            capability_secret=capability_secret,
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
            json={"displayName": "  我的研究助手  "},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "openclaw"
        assert body["webuiUrl"] == (
            "/web/embedded/session-1/openclaw/webui/#token=openclaw-bootstrap-token"
        )
        assert body["terminalUrl"] == (
            "/web/embedded/session-1/openclaw/terminal/?session_id=native-shell-1"
        )
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
    assert gateway.created_display_names == ["我的研究助手"]
    assert gateway.created_envs == [
        {
            "MODEL_AGENT_API_KEY": "test-key",
            "MODEL_AGENT_NAME": "test-model",
            "OPENCLAW_GATEWAY_TOKEN": "openclaw-gateway-token",
        }
    ]
    assert [session.instance_id for session in gateway.deleted] == ["session-1"]


def test_embedded_session_rejects_invalid_display_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_HERMES_TOOL", "hermes-tool")
    gateway = _Gateway(tool_type="HermesEnv")
    with TestClient(_app(gateway)) as client:
        wrong_type = client.post(
            "/web/hermes/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": 42},
        )
        too_long = client.post(
            "/web/hermes/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "名" * 41},
        )

    assert wrong_type.status_code == 422
    assert wrong_type.json()["detail"]["message"] == "智能体名称必须是文本。"
    assert too_long.status_code == 422
    assert "不能超过 40 个字符" in too_long.json()["detail"]["message"]
    assert gateway.created_tool_ids == []


@pytest.mark.asyncio
async def test_embedded_display_name_is_sent_as_agentkit_session_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_HERMES_TOOL", "hermes-tool")
    requests: list[dict[str, object]] = []

    class _Client:
        def create_session(self, request: object) -> object:
            requests.append(request.model_dump(by_alias=True, exclude_none=True))
            return SimpleNamespace(
                session_id="session-1",
                user_session_id="studio-session",
                endpoint="https://sandbox.example?Authorization=private",
            )

        def get_session(self, _request: object) -> object:
            return SimpleNamespace(
                session_id="session-1",
                user_session_id="studio-session",
                endpoint="https://sandbox.example?Authorization=private",
                status="Ready",
                tool_type="HermesEnv",
            )

    gateway = AgentkitSandboxGateway(_Client())
    service = EmbeddedAgentService(
        gateway,
        sleep=_no_wait,
        endpoint_probe=_ready_probe,
        terminal_target_resolver=_ready_terminal_target,
    )

    await service.start("hermes", "alice", "我的分析助手")

    assert requests[0]["Metadata"] == [
        {
            "Key": "veadk_display_name",
            "Type": "String",
            "Value": "我的分析助手",
        }
    ]


def test_local_iframe_uses_scoped_capability_without_custom_identity_header(
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


def test_iframe_connection_recovers_across_server_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_HERMES_TOOL", "hermes-tool")
    gateway = _Gateway(tool_type="HermesEnv")

    async def _proxy_stub(*args: object, **kwargs: object) -> Response:
        del args, kwargs
        return Response("proxied by second instance")

    monkeypatch.setattr(embedded_agents, "_proxy_http", _proxy_stub)

    with (
        TestClient(_app(gateway)) as first_instance,
        TestClient(_app(gateway)) as second_instance,
    ):
        connected = first_instance.post(
            "/web/hermes/sessions",
            headers={"X-Test-User": "alice"},
        )
        second_instance.cookies.update(first_instance.cookies)
        iframe = second_instance.get(
            connected.json()["webuiUrl"],
            headers={"X-Test-User": "alice"},
        )

    assert connected.status_code == 200
    assert iframe.status_code == 200
    assert iframe.text == "proxied by second instance"


def test_cross_instance_iframe_rejects_a_different_deployment_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_OPENCLAW_TOOL", "arkclaw-tool")
    gateway = _Gateway()

    with (
        TestClient(_app(gateway, capability_secret="first-secret")) as first_instance,
        TestClient(_app(gateway, capability_secret="second-secret")) as second_instance,
    ):
        connected = first_instance.post(
            "/web/openclaw/sessions",
            headers={"X-Test-User": "alice"},
        )
        second_instance.cookies.update(first_instance.cookies)
        iframe = second_instance.get(
            connected.json()["webuiUrl"],
            headers={"X-Test-User": "alice"},
        )

    assert iframe.status_code == 403
    assert iframe.json()["detail"] == "智能体页面授权已失效。"


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


@pytest.mark.asyncio
async def test_existing_openclaw_without_gateway_token_still_connects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_OPENCLAW_TOOL", "arkclaw-tool")

    async def _missing_bootstrap(_: SandboxCloudSession) -> str:
        raise SandboxProvisioningError("gateway auth is not configured")

    service = EmbeddedAgentService(
        cast(SandboxCloudGateway, _Gateway()),
        sleep=_no_wait,
        endpoint_probe=_ready_probe,
        terminal_target_resolver=_ready_terminal_target,
        openclaw_bootstrap_resolver=_missing_bootstrap,
    )

    session = await service.connect("openclaw", "session-1", "alice")

    assert session.openclaw_bootstrap_token == ""
    assert "#token=" not in str(embedded_agents._public_session(session)["webuiUrl"])


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


def test_iframe_subrequests_use_capability_without_repeating_studio_identity(
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

    assert iframe.status_code == 200
    assert iframe.text == "proxied"


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


def test_proxy_forwards_runtime_auth_and_scopes_upstream_cookies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_HERMES_TOOL", "hermes-tool")
    captured: dict[str, object] = {}

    class _ProxyClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def build_request(self, *args: object, **kwargs: object) -> object:
            return embedded_agents.httpx.Request(*args, **kwargs)

        async def send(self, request: object, *, stream: bool) -> object:
            captured["request"] = request
            captured["stream"] = stream
            return embedded_agents.httpx.Response(
                200,
                headers=[
                    ("content-type", "application/json"),
                    (
                        "set-cookie",
                        (
                            "hermes_state=rotated; Domain=sandbox.example; Path=/; "
                            "Secure; HttpOnly"
                        ),
                    ),
                    ("set-cookie", "hermes_theme=dark; SameSite=Lax"),
                ],
                content=b'{"ok":true}',
            )

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(embedded_agents.httpx, "AsyncClient", _ProxyClient)

    gateway = _Gateway(tool_type="HermesEnv")
    with TestClient(_app(gateway), base_url="https://studio.example") as client:
        created = client.post(
            "/web/hermes/sessions",
            headers={"X-Test-User": "alice"},
        )
        capability = created.headers["set-cookie"].split(";", 1)[0]
        prefix = created.json()["webuiUrl"].rstrip("/")
        proxied = client.get(
            f"{prefix}/api/profiles/active",
            headers={
                "X-Test-User": "alice",
                "Authorization": "Bearer hermes-runtime-token",
                "X-Hermes-Session-Token": "hermes-session-token",
                "Cookie": (
                    f"{capability}; veadk_session=studio-secret; "
                    "veadk_user_id=alice; hermes_state=ready"
                ),
            },
        )

    request = cast(embedded_agents.httpx.Request, captured["request"])
    assert proxied.status_code == 200
    assert request.headers["authorization"] == "Bearer hermes-runtime-token"
    assert request.headers["x-hermes-session-token"] == "hermes-session-token"
    assert request.headers["cookie"] == "hermes_state=ready"
    assert "Authorization=private" in str(request.url)
    assert "studio-secret" not in str(request.headers)
    set_cookies = proxied.headers.get_list("set-cookie")
    assert len(set_cookies) == 2
    assert all(f"Path={prefix}" in value for value in set_cookies)
    assert all("Domain=" not in value for value in set_cookies)
    assert "Secure" in set_cookies[0]


def test_runtime_cookie_filter_is_shared_by_http_and_websocket() -> None:
    assert (
        embedded_agents._upstream_cookie_header(
            "veadk_embedded_capability=secret; veadk_session=identity; "
            "hermes_state=ready; openclaw_theme=dark"
        )
        == "hermes_state=ready; openclaw_theme=dark"
    )
    assert "Secure" not in embedded_agents._local_set_cookie(
        "runtime=ready; Domain=sandbox.example; Path=/; Secure; HttpOnly",
        "/web/embedded/session-1/hermes/webui",
        secure=False,
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


def test_terminal_metadata_keeps_the_agentkit_endpoint_credentials() -> None:
    target = embedded_agents._target_from_session_meta(
        "https://sandbox.example?faasInstanceName=instance-1&Authorization=private",
        "http://127.0.0.1:8080/terminal?session_id=native-shell-1",
    )

    assert target == (
        "https://sandbox.example/terminal?session_id=native-shell-1&"
        "faasInstanceName=instance-1&Authorization=private"
    )


def test_endpoint_already_at_openclaw_entry_is_not_appended_again() -> None:
    target = _target_from_endpoint(
        "https://sandbox.example/openclaw/chat?"
        "faasInstanceName=instance-redacted&Authorization=auth-redacted&"
        "session_id=chat-session&session=main",
        "/openclaw",
    )

    assert target == (
        "https://sandbox.example/openclaw/chat?"
        "faasInstanceName=instance-redacted&Authorization=auth-redacted&"
        "session_id=chat-session&session=main"
    )


@pytest.mark.asyncio
async def test_terminal_target_uses_native_shell_session_and_keeps_gateway_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _TerminalClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str, **kwargs: object) -> object:
            captured["url"] = url
            captured["headers"] = kwargs.get("headers")
            return embedded_agents.httpx.Response(
                200,
                json={
                    "data": (
                        "http://127.0.0.1:8080/terminal?session_id=native-shell-42"
                    )
                },
                request=embedded_agents.httpx.Request("GET", url),
            )

    monkeypatch.setattr(embedded_agents.httpx, "AsyncClient", _TerminalClient)
    cloud = SandboxCloudSession(
        tool_id="tool-1",
        instance_id="session-1",
        user_session_id="studio-session-1",
        endpoint=(
            "https://sandbox.example?faasInstanceName=instance-1&"
            "Authorization=gateway-secret"
        ),
    )

    target = await embedded_agents._resolve_terminal_target(cloud)

    assert captured["url"] == (
        "https://sandbox.example/v1/shell/terminal-url?"
        "faasInstanceName=instance-1&Authorization=gateway-secret"
    )
    assert captured["headers"] == {"accept": "application/json"}
    assert target == (
        "https://sandbox.example/terminal?session_id=native-shell-42&"
        "faasInstanceName=instance-1&Authorization=gateway-secret"
    )


@pytest.mark.asyncio
async def test_openclaw_bootstrap_auth_is_issued_without_exposing_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    setup_code = embedded_agents._base64url_encode(
        embedded_agents.json.dumps(
            {
                "url": "wss://localhost",
                "bootstrapToken": "short-lived-pairing-token",
            }
        ).encode("utf-8")
    )

    class _BootstrapClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> object:
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            return embedded_agents.httpx.Response(
                200,
                json={
                    "data": {
                        "exit_code": 0,
                        "output": f'\x1b[32mOpenClaw\x1b[0m\n{{"setupCode":"{setup_code}"}}',
                    }
                },
                request=embedded_agents.httpx.Request("POST", url),
            )

    monkeypatch.setattr(embedded_agents.httpx, "AsyncClient", _BootstrapClient)
    cloud = SandboxCloudSession(
        tool_id="tool-1",
        instance_id="session-1",
        user_session_id="studio-session-1",
        endpoint=(
            "https://sandbox.example?faasInstanceName=instance-1&"
            "Authorization=gateway-secret"
        ),
    )

    token = await embedded_agents._resolve_openclaw_bootstrap_token(cloud)

    assert token == "short-lived-pairing-token"
    assert captured["url"] == (
        "https://sandbox.example/v1/shell/exec?"
        "faasInstanceName=instance-1&Authorization=gateway-secret"
    )
    assert captured["json"] == {"command": embedded_agents._OPENCLAW_QR_COMMAND}


def test_openclaw_chat_upstream_restores_gateway_auth_after_public_query() -> None:
    upstream = _upstream_url(
        "https://sandbox.example/openclaw?"
        "faasInstanceName=instance-redacted&Authorization=auth-redacted",
        "chat",
        "session_id=chat-session&session=main",
    )

    assert upstream == (
        "https://sandbox.example/openclaw/chat?"
        "session_id=chat-session&session=main&"
        "faasInstanceName=instance-redacted&Authorization=auth-redacted"
    )


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


@pytest.mark.asyncio
async def test_websocket_proxy_preserves_upstream_auth_close_reason() -> None:
    import websockets

    async def _reject(websocket: object) -> None:
        await websocket.close(4401, "sandbox auth rejected")

    class _BrowserWebSocket:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.accepted = False
            self.closed: tuple[int, str] | None = None

        async def accept(self, subprotocol: str | None = None) -> None:
            assert subprotocol is None
            self.accepted = True

        async def receive(self) -> object:
            await asyncio.Future()

        async def send_bytes(self, _value: bytes) -> None:
            return None

        async def send_text(self, _value: str) -> None:
            return None

        async def close(self, code: int = 1000, reason: str = "") -> None:
            self.closed = (code, reason)

    async with websockets.serve(_reject, "127.0.0.1", 0) as server:
        socket = server.sockets[0]
        address = socket.getsockname()
        browser = _BrowserWebSocket()
        await embedded_agents._relay_websocket(
            cast(embedded_agents.WebSocket, browser),
            f"ws://127.0.0.1:{address[1]}/v1/shell/ws?Authorization=private",
        )

    assert browser.accepted is True
    assert browser.closed == (4401, "sandbox auth rejected")
