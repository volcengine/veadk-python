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

import pytest
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from veadk.extensions.harness.sidecar_runtime.mcp_client import (
    managed_mcp_http_client_factory,
)
from veadk.extensions.harness.sidecar_runtime.mcp_loopback_proxy import (
    SidecarMcpHttpRelay,
)


class _AlternateSessionHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, bool, str]] = []

    def log_message(self, *_args: object) -> None:
        return

    def do_DELETE(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        request = json.loads(self.rfile.read(length) or b"{}")
        method = str(request.get("method") or "")
        has_alternate_session = bool(self.headers.get("X-Session-Id"))
        self.requests.append((method, has_alternate_session, self.path))
        if method == "initialize":
            self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fixture", "version": "1"},
                    },
                },
                session=True,
            )
            return
        if not has_alternate_session:
            self._json(404, {"jsonrpc": "2.0", "id": request.get("id")})
            return
        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._json(
            200,
            {
                "jsonrpc": "2.0",
                "id": request.get("id"),
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

    def _json(self, status: int, value: object, *, session: bool = False) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if session:
            self.send_header("X-Session-Id", "fixture-session")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint_path", ["/mcp", "/vmetrics"])
async def test_loopback_relay_preserves_alternate_session_without_env_proxy(
    monkeypatch: pytest.MonkeyPatch,
    endpoint_path: str,
) -> None:
    _AlternateSessionHandler.requests.clear()
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _AlternateSessionHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    host, port = upstream.server_address[:2]
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    relay = SidecarMcpHttpRelay(
        f"http://{host}:{port}{endpoint_path}",
        timeout_seconds=2,
    )
    toolset = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=relay.url,
            timeout=2,
            sse_read_timeout=2,
            httpx_client_factory=managed_mcp_http_client_factory,
        )
    )
    try:
        tools = await toolset.get_tools()
    finally:
        await toolset.close()
        relay.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=3)

    assert [tool.name for tool in tools] == ["safe_fixture_tool"]
    assert any(
        method != "initialize" and has_alternate_session
        for method, has_alternate_session, _path in _AlternateSessionHandler.requests
    )
    assert {
        path for _method, _has_session, path in _AlternateSessionHandler.requests
    } == {endpoint_path}
