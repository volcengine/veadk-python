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
from typing import Iterator

import httpx
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from veadk.cli.generated_agent_codegen import AgentDraft, McpTool, prepare_mcp_auth


class McpDebugConnectionError(ValueError):
    """Raised when a configured MCP server cannot expose tools for debugging."""


class _McpNoToolsError(RuntimeError):
    """Internal marker for an endpoint that completed discovery without tools."""


def _error_tree(error: BaseException) -> Iterator[BaseException]:
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        yield current
        grouped = getattr(current, "exceptions", ())
        if isinstance(grouped, tuple) and all(
            isinstance(item, BaseException) for item in grouped
        ):
            pending.extend(grouped)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)


def _mcp_debug_failure_kind(error: BaseException) -> str:
    failures = tuple(_error_tree(error))
    statuses = {
        int(getattr(getattr(item, "response", None), "status_code", 0) or 0)
        for item in failures
    }
    if statuses & {401, 403}:
        return "auth"
    if statuses & {404, 405, 410}:
        return "endpoint"
    if 429 in statuses:
        return "rate_limit"
    if any(500 <= status <= 599 for status in statuses):
        return "upstream"
    if any(isinstance(item, _McpNoToolsError) for item in failures):
        return "empty"
    if any(isinstance(item, httpx.TimeoutException) for item in failures):
        return "timeout"
    if any(isinstance(item, (httpx.NetworkError, OSError)) for item in failures):
        return "network"
    return "protocol"


def _mcp_debug_failure_detail(name: str, error: BaseException) -> str:
    reason = {
        "auth": "认证被服务拒绝。请确认 Token 与该 Endpoint 匹配。",
        "endpoint": (
            "地址未提供可用的 Streamable HTTP MCP 服务。"
            "请确认完整 Endpoint（包括业务路径）。"
        ),
        "rate_limit": "服务当前限流，请稍后重试。",
        "upstream": "服务暂时不可用。请稍后重试，或检查 MCP 服务状态。",
        "empty": "连接成功，但未发现可用工具。",
        "timeout": "连接超时。请确认网络可达，并检查服务响应时间。",
        "network": "网络连接失败。请确认域名、网络和 TLS 配置。",
        "protocol": "服务响应不符合 Streamable HTTP MCP 协议。",
    }[_mcp_debug_failure_kind(error)]
    return (
        f"MCP 工具 `{name}` 连接失败：{reason}"
        "调试环境尚未启动；该错误发生在 MCP 连接预检阶段，与 Sidecar 无关。"
    )


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
            raise _McpNoToolsError
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
    except Exception as error:
        name = tool.name.strip() or "未命名 MCP"
        raise McpDebugConnectionError(_mcp_debug_failure_detail(name, error)) from None
    else:
        return tool.model_copy(update={"url": url})


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
