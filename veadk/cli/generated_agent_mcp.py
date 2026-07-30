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

"""MCP endpoint discovery for generated-agent debug runs."""

from __future__ import annotations

from contextlib import suppress
from urllib.parse import urlsplit, urlunsplit

from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from veadk.cli.generated_agent_codegen import AgentDraft, McpTool


class McpDebugConnectionError(ValueError):
    """Raised when a configured MCP server cannot expose tools for debugging."""


def _normalize_mcp_endpoint(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.path.rstrip("/").endswith("/mcp"):
        return url
    path = f"{parsed.path.rstrip('/')}/mcp"
    return urlunsplit(parsed._replace(path=path))


async def _list_mcp_tools(tool: McpTool, url: str) -> None:
    headers = None
    if tool.authToken.strip():
        headers = {"Authorization": f"Bearer {tool.authToken.strip()}"}
    toolset = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=url,
            headers=headers,
            timeout=10,
        )
    )
    try:
        tools = await toolset.get_tools()
        if not tools:
            raise ConnectionError("MCP server returned no tools")
    finally:
        with suppress(Exception):
            await toolset.close()


async def _resolve_http_mcp_tool(tool: McpTool) -> McpTool:
    url = _normalize_mcp_endpoint(tool.url.strip())
    try:
        await _list_mcp_tools(tool, url)
    except Exception:
        pass
    else:
        return tool.model_copy(update={"url": url})

    name = tool.name.strip() or "未命名 MCP"
    raise McpDebugConnectionError(
        f"MCP 工具 `{name}` 连接失败：无法通过 Streamable HTTP 完成工具发现。"
        "请确认 URL 指向实际 MCP endpoint（通常以 /mcp 结尾），并检查 Token。"
    ) from None


async def resolve_debug_mcp_endpoints(draft: AgentDraft) -> AgentDraft:
    """Resolve HTTP MCP endpoints recursively without mutating the input draft."""
    tools: list[McpTool] = []
    for tool in draft.mcpTools:
        if tool.transport == "http" and tool.url.strip():
            tools.append(await _resolve_http_mcp_tool(tool))
        else:
            tools.append(tool)

    sub_agents = [
        await resolve_debug_mcp_endpoints(sub_agent) for sub_agent in draft.subAgents
    ]
    return draft.model_copy(
        deep=True,
        update={"mcpTools": tools, "subAgents": sub_agents},
    )
