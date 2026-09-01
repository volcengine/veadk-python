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

"""Tests for Studio's bounded Sandbox data-plane helpers."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from typing_extensions import Self

from veadk.cli import frontend_sandbox_proxy
from veadk.cli.frontend_sandbox_proxy import (
    SANDBOX_UPLOAD_MAX_BYTES,
    SandboxProxyTarget,
    mount_sandbox_proxy_routes,
    proxy_cookie_name,
    proxy_prefix,
    terminal_initial_command_url,
    terminal_launch_url,
    upload_sandbox_file,
)


def test_terminal_initial_command_url_uses_compact_terminal_style() -> None:
    url = terminal_initial_command_url(
        "cloud-session",
        "clear; agentkit --help; agentkit --version",
    )

    assert url == (
        "/web/sandbox/proxy/cloud-session/terminal/terminal"
        "?command=clear%3B+agentkit+--help%3B+agentkit+--version&font_size=12"
    )


@pytest.mark.asyncio
async def test_upload_preserves_content_and_sanitizes_remote_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, bool]:
            return {"success": True}

    class _Client:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> _Response:
            captured.update({"url": url, **kwargs})
            return _Response()

    monkeypatch.setattr(
        frontend_sandbox_proxy.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(),
    )
    content = b"keep this upload"

    path = await upload_sandbox_file(
        "https://sandbox.example/root?Authorization=private",
        "/workspace/project/",
        "../report\n.pdf",
        "application/pdf",
        content,
    )

    assert path == "/workspace/project/.._report.pdf"
    assert captured["url"] == (
        "https://sandbox.example/root/v1/file/upload?Authorization=private"
    )
    assert captured["data"] == {"path": path}
    assert captured["files"] == {"file": (".._report.pdf", content, "application/pdf")}


@pytest.mark.asyncio
async def test_upload_rejects_ambiguous_names_and_oversized_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert frontend_sandbox_proxy._safe_upload_name("..") == "attachment"
    assert frontend_sandbox_proxy._safe_upload_name(".") == "attachment"

    class _UnexpectedClient:
        async def __aenter__(self) -> Self:
            raise AssertionError("oversized uploads must not reach HTTP")

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        frontend_sandbox_proxy.httpx,
        "AsyncClient",
        lambda **_kwargs: _UnexpectedClient(),
    )

    with pytest.raises(ValueError, match="大小限制"):
        await upload_sandbox_file(
            "https://sandbox.example?Authorization=private",
            "/workspace",
            "..",
            "application/octet-stream",
            b"x" * (SANDBOX_UPLOAD_MAX_BYTES + 1),
        )


@pytest.mark.asyncio
async def test_terminal_launch_uses_an_opaque_same_origin_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, str]:
            return {
                "data": (
                    "https://sandbox.example/terminal"
                    "?session_id=native-shell-1&Authorization=private"
                )
            }

    class _Client:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str, **kwargs: object) -> _Response:
            captured.update({"url": url, **kwargs})
            return _Response()

    monkeypatch.setattr(
        frontend_sandbox_proxy.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(),
    )

    url, shell_session_id = await terminal_launch_url(
        "https://sandbox.example/root?Authorization=private",
        "cloud-session",
    )

    assert shell_session_id == "native-shell-1"
    assert url == (
        "/web/sandbox/proxy/cloud-session/terminal/terminal?session_id=native-shell-1"
    )
    assert captured["url"] == (
        "https://sandbox.example/root/v1/shell/terminal-url?Authorization=private"
    )
    assert "private" not in url


@pytest.mark.asyncio
async def test_terminal_launch_can_return_the_native_browser_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native_url = "https://sandbox.example/terminal?session_id=native-shell-1"

    class _Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, str]:
            return {"data": native_url}

    class _Client:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, _url: str, **_kwargs: object) -> _Response:
            return _Response()

    monkeypatch.setattr(
        frontend_sandbox_proxy.httpx,
        "AsyncClient",
        lambda **_kwargs: _Client(),
    )

    url, shell_session_id = await terminal_launch_url(
        (
            "https://sandbox.example/root"
            "?faasInstanceName=instance-1&Authorization=private"
        ),
        "cloud-session",
        direct=True,
    )

    assert url == (
        "https://sandbox.example/root/terminal"
        "?faasInstanceName=instance-1"
        "&Authorization=private"
        "&session_id=native-shell-1"
    )
    assert shell_session_id == "native-shell-1"


def test_browser_launch_can_return_the_native_browser_url() -> None:
    url = frontend_sandbox_proxy.browser_launch_url(
        "cloud-session",
        endpoint="https://sandbox.example/root?Authorization=private",
        direct=True,
    )

    assert url == "https://sandbox.example/root/browser-ui?Authorization=private"


@pytest.mark.asyncio
async def test_browser_info_rewrites_cdp_and_removes_private_urls() -> None:
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/browser/info",
            "raw_path": b"/browser/info",
            "query_string": b"",
            "headers": [
                (b"host", b"studio.example"),
                (b"x-forwarded-proto", b"https"),
            ],
            "client": ("127.0.0.1", 1234),
            "server": ("studio.example", 80),
        }
    )
    upstream = httpx.Response(
        200,
        json={
            "data": {
                "cdp_url": (
                    "ws://sandbox.example/cdp/devtools/browser/browser-1"
                    "?Authorization=private"
                ),
                "vnc_url": "https://sandbox.example/vnc?Authorization=private",
            }
        },
    )

    class _Client:
        closed = False

        async def aclose(self) -> None:
            self.closed = True

    client = _Client()
    prefix = proxy_prefix("cloud-session", "browser")
    response = await frontend_sandbox_proxy._browser_info_response(
        request,
        upstream,
        client,  # type: ignore[arg-type]
        prefix,
    )
    payload = json.loads(response.body)

    assert payload["data"]["cdp_url"] == (
        "wss://studio.example/web/sandbox/proxy/cloud-session/browser"
        "/cdp/devtools/browser/browser-1"
    )
    assert payload["data"]["cdp_ui_url"] == (
        "https://studio.example/web/sandbox/proxy/cloud-session/browser/browser-ui"
    )
    assert "vnc_url" not in payload["data"]
    assert "private" not in response.body.decode()
    assert client.closed is True


def test_proxy_requires_the_sandbox_capability_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()

    def _resolve(session_id: str, token: str) -> SandboxProxyTarget:
        if session_id != "cloud-session":
            raise KeyError(session_id)
        if token != "opaque-capability":
            raise PermissionError("invalid capability")
        return SandboxProxyTarget(
            endpoint="https://sandbox.example?Authorization=private"
        )

    async def _proxy_response(*_args: object, **_kwargs: object) -> JSONResponse:
        return JSONResponse({"proxied": True})

    monkeypatch.setattr(
        frontend_sandbox_proxy,
        "_proxy_http_response",
        _proxy_response,
    )
    mount_sandbox_proxy_routes(app, _resolve)
    path = f"{proxy_prefix('cloud-session', 'browser')}/browser-ui"
    cookie = proxy_cookie_name("cloud-session")

    with TestClient(app) as client:
        denied = client.get(path)
        allowed = client.get(
            path,
            headers={"cookie": f"{cookie}=opaque-capability"},
        )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json() == {"proxied": True}
