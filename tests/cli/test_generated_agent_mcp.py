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
