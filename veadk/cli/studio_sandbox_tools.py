# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Provision the dedicated AgentKit Tools used by a cloud Studio deployment."""

from __future__ import annotations

import re
import secrets
import time
import zlib
from collections.abc import Callable
from typing import Any

_PROJECT_NAME = "default"
_CODE_ENV_TOOL_TYPE = "CodeEnv"
_ARKCLAW_TOOL_TYPE = "ArkClawEnv"
_HERMES_TOOL_TYPE = "HermesEnv"
_READY_STATUS = "Ready"
_FAILED_STATUSES = frozenset({"Error", "Failed", "CreateFailed", "Deleting", "Deleted"})


def studio_sandbox_tool_name(application_name: str, purpose: str) -> str:
    """Return a stable, account-local Tool name for one Studio capability."""
    safe_name = re.sub(r"[^a-z0-9-]+", "-", application_name.lower()).strip("-")
    safe_name = safe_name[:30].rstrip("-") or "studio"
    digest = f"{zlib.crc32(application_name.encode()):08x}"
    return f"veadk-studio-{safe_name}-{purpose}-{digest}"


def ensure_studio_code_env_tool(
    *,
    name: str,
    access_key: str = "",
    secret_key: str = "",
    region: str = "cn-beijing",
    session_token: str = "",
    client: Any | None = None,
    timeout_seconds: float = 600.0,
    poll_interval: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Reuse or create one Ready CodeEnv Tool and return its Tool ID."""
    return _ensure_studio_tool(
        name=name,
        tool_type=_CODE_ENV_TOOL_TYPE,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        session_token=session_token,
        client=client,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        sleep=sleep,
        include_code_env_resources=True,
    )


def ensure_studio_arkclaw_tool(
    *,
    name: str,
    access_key: str = "",
    secret_key: str = "",
    region: str = "cn-beijing",
    session_token: str = "",
    client: Any | None = None,
    timeout_seconds: float = 600.0,
    poll_interval: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Reuse or create one Ready ArkClawEnv Tool and return its Tool ID."""
    return _ensure_studio_tool(
        name=name,
        tool_type=_ARKCLAW_TOOL_TYPE,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        session_token=session_token,
        client=client,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        sleep=sleep,
    )


def ensure_studio_hermes_tool(
    *,
    name: str,
    access_key: str = "",
    secret_key: str = "",
    region: str = "cn-beijing",
    session_token: str = "",
    client: Any | None = None,
    timeout_seconds: float = 600.0,
    poll_interval: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Reuse or create one Ready HermesEnv Tool and return its Tool ID."""
    return _ensure_studio_tool(
        name=name,
        tool_type=_HERMES_TOOL_TYPE,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        session_token=session_token,
        client=client,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        sleep=sleep,
    )


def _ensure_studio_tool(
    *,
    name: str,
    tool_type: str,
    access_key: str,
    secret_key: str,
    region: str,
    session_token: str,
    client: Any | None,
    timeout_seconds: float,
    poll_interval: float,
    sleep: Callable[[float], None],
    include_code_env_resources: bool = False,
) -> str:
    """Reuse or create one Ready Tool of an exact preset type."""
    from agentkit.sdk.tools import types as tools_types
    from agentkit.sdk.tools.client import AgentkitToolsClient

    tools_client = client or AgentkitToolsClient(
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        session_token=session_token,
    )
    named_tools = []
    next_token: str | None = None
    seen_tokens: set[str] = set()
    for _page in range(100):
        response = tools_client.list_tools(
            tools_types.ListToolsRequest(
                ProjectName=_PROJECT_NAME,
                MaxResults=100,
                NextToken=next_token,
                Filters=[
                    tools_types.FiltersItemForListTools(
                        Name="Name",
                        Values=[name],
                    )
                ],
            )
        )
        named_tools.extend(
            tool
            for tool in (response.tools or [])
            if tool.name == name and tool.project_name == _PROJECT_NAME
        )
        next_token = response.next_token or None
        if not next_token:
            break
        if next_token in seen_tokens:
            raise RuntimeError("AgentKit ListTools returned a repeated NextToken.")
        seen_tokens.add(next_token)
    else:
        raise RuntimeError("AgentKit ListTools exceeded the safe pagination limit.")

    wrong_types = sorted(
        {
            str(tool.tool_type or "Unknown")
            for tool in named_tools
            if tool.tool_type != tool_type
        }
    )
    if wrong_types:
        raise RuntimeError(
            f"AgentKit Tool '{name}' already exists with ToolType "
            f"{', '.join(wrong_types)}; expected {tool_type}."
        )
    matches = [tool for tool in named_tools if tool.tool_type == tool_type]
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple AgentKit {tool_type} Tools named '{name}' were found."
        )
    if matches:
        tool_id = (matches[0].tool_id or "").strip()
        if not tool_id:
            raise RuntimeError(f"AgentKit Tool '{name}' did not return a Tool ID.")
    else:
        request_values: dict[str, Any] = {
            "Name": name,
            "ToolType": tool_type,
            "ProjectName": _PROJECT_NAME,
            "AuthorizerConfiguration": tools_types.AuthorizerForCreateTool(
                KeyAuth=tools_types.AuthorizerKeyAuthForCreateTool(
                    ApiKeyName=f"studio-{secrets.token_hex(8)}",
                    ApiKeyLocation="Header",
                )
            ),
            "NetworkConfiguration": tools_types.NetworkForCreateTool(
                EnablePublicNetwork=True,
                EnablePrivateNetwork=False,
            ),
        }
        if include_code_env_resources:
            request_values.update(CpuMilli=4000, MemoryMb=8192)
        response = tools_client.create_tool(
            tools_types.CreateToolRequest(**request_values)
        )
        tool_id = (response.tool_id or "").strip()
        if not tool_id:
            raise RuntimeError(
                f"Creating AgentKit Tool '{name}' did not return a Tool ID."
            )

    deadline = time.monotonic() + timeout_seconds
    while True:
        tool = tools_client.get_tool(tools_types.GetToolRequest(ToolId=tool_id))
        status = (tool.status or "").strip()
        if status == _READY_STATUS:
            returned_type = str(getattr(tool, "tool_type", "") or "").strip()
            if returned_type and returned_type != tool_type:
                raise RuntimeError(
                    f"AgentKit Tool '{name}' became ready with ToolType "
                    f"{returned_type}; expected {tool_type}."
                )
            return tool_id
        if status in _FAILED_STATUSES:
            raise RuntimeError(
                f"AgentKit Tool '{name}' failed to become ready: {status}."
            )
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for AgentKit Tool '{name}'.")
        sleep(poll_interval)
