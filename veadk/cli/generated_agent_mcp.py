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

from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from veadk.cli.generated_agent_codegen import AgentDraft, McpTool, prepare_mcp_auth


class McpDebugConnectionError(ValueError):
    """Raised when a configured MCP server cannot expose tools for debugging."""


async def _list_mcp_tools(
    tool: McpTool,
    url: str,
    env_values: dict[str, str],
) -> None:
    headers = None
    auth_token = tool.authToken.strip() or env_values.get(tool.authTokenEnv, "").strip()
    if auth_token:
        headers = {"Authorization": f"Bearer {auth_token}"}
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


async def _resolve_http_mcp_tool(
    tool: McpTool,
    env_values: dict[str, str],
) -> McpTool:
    url = tool.url.strip()
    try:
        await _list_mcp_tools(tool, url, env_values)
    except Exception:
        pass
    else:
        return tool.model_copy(update={"url": url})

    name = tool.name.strip() or "未命名 MCP"
    raise McpDebugConnectionError(
        f"MCP 工具 `{name}` 连接失败：无法通过 Streamable HTTP 完成工具发现。"
        "请确认 URL 指向实际 MCP Endpoint，并检查 Token。"
    ) from None


async def resolve_debug_mcp_endpoints(
    draft: AgentDraft,
    _env_values: dict[str, str] | None = None,
) -> AgentDraft:
    """Resolve HTTP MCP endpoints recursively without mutating the input draft."""
    env_values = _env_values
    if env_values is None:
        draft = prepare_mcp_auth(draft)
        env_values = draft.deployment.envValues
    tools: list[McpTool] = []
    for tool in draft.mcpTools:
        if tool.transport == "http" and tool.url.strip():
            tools.append(await _resolve_http_mcp_tool(tool, env_values))
        else:
            tools.append(tool)

    sub_agents = [
        await resolve_debug_mcp_endpoints(sub_agent, env_values)
        for sub_agent in draft.subAgents
    ]
    return draft.model_copy(
        deep=True,
        update={"mcpTools": tools, "subAgents": sub_agents},
    )
