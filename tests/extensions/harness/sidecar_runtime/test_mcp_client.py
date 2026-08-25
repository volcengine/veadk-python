# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from veadk.extensions.harness.sidecar_runtime.mcp_client import (
    managed_mcp_http_client_factory,
)


class _AlternateSessionHeaderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    requests: ClassVar[list[tuple[str, bool]]] = []

    def log_message(self, *_args: object) -> None:
        return

    def do_DELETE(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        method = str(payload.get("method") or "")
        has_standard_session = bool(self.headers.get("Mcp-Session-Id"))
        self.requests.append((method, has_standard_session))

        if method == "initialize":
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fixture", "version": "1"},
                    },
                },
                session_header=True,
            )
            return
        if not has_standard_session:
            self._send_json(
                404,
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "error": {"code": -32001, "message": "session missing"},
                },
            )
            return
        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if method == "tools/list":
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "tools": [
                            {
                                "name": "safe_fixture_tool",
                                "description": "fixture",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                },
            )
            return
        self.send_response(400)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_json(
        self,
        status: int,
        value: object,
        *,
        session_header: bool = False,
    ) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if session_header:
            self.send_header("X-Session-Id", "fixture-session")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _RejectingProxyHandler(BaseHTTPRequestHandler):
    requests: ClassVar[int] = 0

    def log_message(self, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        type(self).requests += 1
        body = b'{"error":"proxy must not receive managed loopback traffic"}'
        self.send_response(502)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.mark.asyncio
async def test_managed_client_normalizes_runtime_gateway_session_header() -> None:
    _AlternateSessionHeaderHandler.requests.clear()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _AlternateSessionHeaderHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    toolset = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=f"http://{host}:{port}/mcp",
            timeout=2,
            sse_read_timeout=2,
            httpx_client_factory=managed_mcp_http_client_factory,
        )
    )
    try:
        tools = await toolset.get_tools()
    finally:
        await toolset.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    assert [tool.name for tool in tools] == ["safe_fixture_tool"]
    assert any(
        method != "initialize" and has_standard_session
        for method, has_standard_session in _AlternateSessionHeaderHandler.requests
    )


@pytest.mark.asyncio
async def test_managed_client_ignores_proxy_environment_for_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _AlternateSessionHeaderHandler.requests.clear()
    upstream = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        _AlternateSessionHeaderHandler,
    )
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    upstream_host, upstream_port = upstream.server_address[:2]

    _RejectingProxyHandler.requests = 0
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), _RejectingProxyHandler)
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()
    proxy_host, proxy_port = proxy.server_address[:2]
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.setenv(name, proxy_url)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)

    toolset = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=f"http://{upstream_host}:{upstream_port}/mcp",
            timeout=2,
            sse_read_timeout=2,
            httpx_client_factory=managed_mcp_http_client_factory,
        )
    )
    try:
        tools = await toolset.get_tools()
    finally:
        await toolset.close()
        proxy.shutdown()
        proxy.server_close()
        proxy_thread.join(timeout=3)
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=3)

    assert [tool.name for tool in tools] == ["safe_fixture_tool"]
    assert _RejectingProxyHandler.requests == 0
