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

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest

from veadk.cli.generated_agent_codegen import AgentDraft, McpTool
from veadk.cli.generated_agent_mcp import (
    McpDebugConnectionError,
    resolve_debug_mcp_endpoints,
)


class _FakeMcpToolset:
    attempted_urls: list[str] = []
    working_urls: set[str] = set()

    def __init__(self, *, connection_params) -> None:
        self.url = connection_params.url

    async def get_tools(self):
        self.attempted_urls.append(self.url)
        if self.url not in self.working_urls:
            raise ConnectionError("authorization=Bearer secret-token")
        return [SimpleNamespace(name="sequentialthinking")]

    async def close(self) -> None:
        return None


class _AuthenticatedMcpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    requests: list[tuple[str, str, str]] = []

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
        authorization = str(self.headers.get("Authorization") or "")
        self.requests.append((self.path, method, authorization))
        if self.path != "/athena-mcp" or authorization != "Bearer fixture-token":
            self._send_json(401, {"error": "unauthorized"})
            return
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
                session=True,
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
                                "name": "fixture_tool",
                                "description": "fixture",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                },
            )
            return
        self._send_json(400, {"error": "unsupported"})

    def _send_json(
        self,
        status: int,
        value: object,
        *,
        session: bool = False,
    ) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if session:
            self.send_header("Mcp-Session-Id", "fixture-session")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.mark.asyncio
async def test_debug_mcp_discovers_authenticated_custom_path_with_real_client(
    monkeypatch,
) -> None:
    _AuthenticatedMcpHandler.requests.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AuthenticatedMcpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    draft = AgentDraft(
        name="demo-agent",
        description="Demo agent",
        instruction="Use the tool.",
        mcpTools=[
            McpTool(
                name="athena",
                transport="http",
                url=f"http://{host}:{port}/athena-mcp",
                authToken="fixture-token",
            )
        ],
    )
    try:
        resolved = await resolve_debug_mcp_endpoints(draft)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    assert resolved.mcpTools[0].url == f"http://{host}:{port}/athena-mcp"
    assert _AuthenticatedMcpHandler.requests
    assert {
        path for path, _method, _authorization in _AuthenticatedMcpHandler.requests
    } == {"/athena-mcp"}
    assert {
        authorization
        for _path, _method, authorization in _AuthenticatedMcpHandler.requests
    } == {"Bearer fixture-token"}


@pytest.mark.asyncio
async def test_debug_mcp_keeps_configured_path_without_rewriting(monkeypatch) -> None:
    _FakeMcpToolset.attempted_urls = []
    _FakeMcpToolset.working_urls = {"https://mcp.example.com/mysqldiag"}
    monkeypatch.setattr(
        "veadk.cli.generated_agent_mcp.MCPToolset",
        _FakeMcpToolset,
    )
    draft = AgentDraft(
        name="demo-agent",
        description="Demo agent",
        instruction="Use the tool.",
        mcpTools=[
            McpTool(
                name="sequentialthinking",
                transport="http",
                url="https://mcp.example.com/mysqldiag",
                authToken="secret-token",
            )
        ],
    )

    resolved = await resolve_debug_mcp_endpoints(draft)

    assert _FakeMcpToolset.attempted_urls == ["https://mcp.example.com/mysqldiag"]
    assert resolved.mcpTools[0].url == "https://mcp.example.com/mysqldiag"
    assert draft.mcpTools[0].url == "https://mcp.example.com/mysqldiag"


@pytest.mark.asyncio
async def test_debug_mcp_keeps_existing_mcp_path(monkeypatch) -> None:
    url = "https://mcp.example.com/gateway/mcp/?region=cn-beijing"
    _FakeMcpToolset.attempted_urls = []
    _FakeMcpToolset.working_urls = {url}
    monkeypatch.setattr(
        "veadk.cli.generated_agent_mcp.MCPToolset",
        _FakeMcpToolset,
    )
    draft = AgentDraft(
        name="demo-agent",
        description="Demo agent",
        instruction="Use the tool.",
        mcpTools=[
            McpTool(
                name="sequentialthinking",
                transport="http",
                url=url,
            )
        ],
    )

    resolved = await resolve_debug_mcp_endpoints(draft)

    assert _FakeMcpToolset.attempted_urls == [url]
    assert resolved.mcpTools[0].url == url


@pytest.mark.asyncio
async def test_debug_mcp_reports_discovery_failure_without_credentials(
    monkeypatch,
) -> None:
    _FakeMcpToolset.attempted_urls = []
    _FakeMcpToolset.working_urls = set()
    monkeypatch.setattr(
        "veadk.cli.generated_agent_mcp.MCPToolset",
        _FakeMcpToolset,
    )
    draft = AgentDraft(
        name="demo-agent",
        description="Demo agent",
        instruction="Use the tool.",
        mcpTools=[
            McpTool(
                name="sequentialthinking",
                transport="http",
                url="https://mcp.example.com",
                authToken="secret-token",
            )
        ],
    )

    with pytest.raises(McpDebugConnectionError) as exc_info:
        await resolve_debug_mcp_endpoints(draft)

    message = str(exc_info.value)
    assert "sequentialthinking" in message
    assert "MCP 连接预检" in message
    assert "Sidecar" in message
    assert "secret-token" not in message
    assert "Bearer" not in message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("auth", "认证被服务拒绝"),
        ("endpoint", "完整 Endpoint"),
        ("rate_limit", "服务当前限流"),
        ("upstream", "服务暂时不可用"),
        ("timeout", "连接超时"),
        ("network", "网络连接失败"),
        ("protocol", "不符合 Streamable HTTP MCP 协议"),
        ("empty", "未发现可用工具"),
    ],
)
async def test_debug_mcp_classifies_failures_without_exposing_details(
    monkeypatch,
    failure: str,
    expected: str,
) -> None:
    request = httpx.Request("POST", "https://mcp.example.com/athena-mcp")
    sensitive_marker = "private-debug-detail-marker"

    class FailingMcpToolset:
        def __init__(self, *, connection_params) -> None:
            del connection_params

        async def get_tools(self):
            if failure == "auth":
                response = httpx.Response(401, request=request, text=sensitive_marker)
                raise httpx.HTTPStatusError(
                    sensitive_marker,
                    request=request,
                    response=response,
                )
            if failure == "endpoint":
                response = httpx.Response(404, request=request, text=sensitive_marker)
                raise httpx.HTTPStatusError(
                    sensitive_marker,
                    request=request,
                    response=response,
                )
            if failure == "rate_limit":
                response = httpx.Response(429, request=request, text=sensitive_marker)
                raise httpx.HTTPStatusError(
                    sensitive_marker,
                    request=request,
                    response=response,
                )
            if failure == "upstream":
                response = httpx.Response(503, request=request, text=sensitive_marker)
                raise httpx.HTTPStatusError(
                    sensitive_marker,
                    request=request,
                    response=response,
                )
            if failure == "timeout":
                raise httpx.ReadTimeout(sensitive_marker, request=request)
            if failure == "network":
                raise httpx.ConnectError(sensitive_marker, request=request)
            if failure == "protocol":
                raise RuntimeError(sensitive_marker)
            return []

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        "veadk.cli.generated_agent_mcp.MCPToolset",
        FailingMcpToolset,
    )
    draft = AgentDraft(
        name="demo-agent",
        description="Demo agent",
        instruction="Use the tool.",
        mcpTools=[
            McpTool(
                name="",
                transport="http",
                url="https://mcp.example.com/athena-mcp",
                authToken="private-token-marker",
            )
        ],
    )

    with pytest.raises(McpDebugConnectionError) as exc_info:
        await resolve_debug_mcp_endpoints(draft)

    message = str(exc_info.value)
    assert expected in message
    assert "MCP 连接预检" in message
    assert "Sidecar" in message
    assert sensitive_marker not in message
    assert "private-token-marker" not in message
