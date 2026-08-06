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

"""Provision the dedicated sandbox Tools used by a cloud Studio deployment."""

from __future__ import annotations

import re
import secrets
import time
import zlib
from collections.abc import Callable
from typing import Any

_PROJECT_NAME = "default"
_TOOL_TYPE = "CodeEnv"
STUDIO_SANDBOX_AGENT_MODEL_NAME = "doubao-seed-evolving"
_AGENT_TOOL_TYPES = {
    "openclaw": "ArkClawEnv",
    "hermes": "HermesEnv",
}
_READY_STATUS = "Ready"
_FAILED_STATUSES = frozenset({"Error", "Failed", "CreateFailed", "Deleting", "Deleted"})


def studio_sandbox_tool_name(application_name: str, purpose: str) -> str:
    """Return a stable, account-local Tool name for one Studio capability."""
    safe_name = re.sub(r"[^a-z0-9-]+", "-", application_name.lower()).strip("-")
    safe_name = safe_name[:30].rstrip("-") or "studio"
    digest = f"{zlib.crc32(application_name.encode()):08x}"
    return f"veadk-studio-{safe_name}-{purpose}-{digest}"


def _wait_for_ready_tool(
    tools_client: Any,
    tools_types: Any,
    *,
    tool_id: str,
    name: str,
    timeout_seconds: float,
    poll_interval: float,
    sleep: Callable[[float], None],
    enable_snapshot: bool = False,
) -> str:
    deadline = time.monotonic() + timeout_seconds
    snapshot_update_requested = False
    while True:
        tool = tools_client.get_tool(tools_types.GetToolRequest(ToolId=tool_id))
        status = (tool.status or "").strip()
        if status == _READY_STATUS:
            if not enable_snapshot or getattr(tool, "enable_snapshot", None) is True:
                return tool_id
            if not snapshot_update_requested:
                _enable_tool_snapshot(tools_client, tools_types, tool_id)
                snapshot_update_requested = True
        if status in _FAILED_STATUSES:
            raise RuntimeError(
                f"AgentKit Tool '{name}' failed to become ready: {status}."
            )
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for AgentKit Tool '{name}'.")
        sleep(poll_interval)


def _enable_tool_snapshot(tools_client: Any, tools_types: Any, tool_id: str) -> None:
    """Enable snapshots across SDK releases whose UpdateTool model lags the API."""
    from pydantic import Field

    request_type: Any = tools_types.UpdateToolRequest
    supports_snapshot = any(
        getattr(field, "alias", None) == "EnableSnapshot"
        for field in getattr(request_type, "model_fields", {}).values()
    )
    if not supports_snapshot:

        class _UpdateToolSnapshotRequest(request_type):
            enable_snapshot: bool = Field(alias="EnableSnapshot")

        request_type = _UpdateToolSnapshotRequest
    tools_client.update_tool(request_type(ToolId=tool_id, EnableSnapshot=True))


def _find_exact_tool(
    tools_client: Any,
    tools_types: Any,
    *,
    name: str,
    tool_type: str,
) -> Any | None:
    matches = []
    next_token: str | None = None
    while True:
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
        matches.extend(
            tool
            for tool in (response.tools or [])
            if tool.name == name
            and tool.project_name == _PROJECT_NAME
            and tool.tool_type == tool_type
        )
        next_token = response.next_token or None
        if not next_token:
            break
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple AgentKit {tool_type} Tools named '{name}' were found."
        )
    return matches[0] if matches else None


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
    enable_snapshot: bool = True,
) -> str:
    """Reuse or create one Ready CodeEnv Tool and return its Tool ID."""
    from agentkit.sdk.tools import types as tools_types
    from agentkit.sdk.tools.client import AgentkitToolsClient

    tools_client = client or AgentkitToolsClient(
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        session_token=session_token,
    )
    matches = []
    next_token: str | None = None
    while True:
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
        matches.extend(
            tool
            for tool in (response.tools or [])
            if tool.name == name
            and tool.project_name == _PROJECT_NAME
            and tool.tool_type == _TOOL_TYPE
        )
        next_token = response.next_token or None
        if not next_token:
            break

    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple AgentKit CodeEnv Tools named '{name}' were found."
        )
    if matches:
        tool_id = (matches[0].tool_id or "").strip()
        if not tool_id:
            raise RuntimeError(f"AgentKit Tool '{name}' did not return a Tool ID.")
    else:
        response = tools_client.create_tool(
            tools_types.CreateToolRequest(
                Name=name,
                ToolType=_TOOL_TYPE,
                ProjectName=_PROJECT_NAME,
                CpuMilli=4000,
                MemoryMb=8192,
                EnableSnapshot=True if enable_snapshot else None,
                AuthorizerConfiguration=tools_types.AuthorizerForCreateTool(
                    KeyAuth=tools_types.AuthorizerKeyAuthForCreateTool(
                        ApiKeyName=f"studio-{secrets.token_hex(8)}",
                        ApiKeyLocation="Header",
                    )
                ),
                NetworkConfiguration=tools_types.NetworkForCreateTool(
                    EnablePublicNetwork=True,
                    EnablePrivateNetwork=False,
                ),
            )
        )
        tool_id = (response.tool_id or "").strip()
        if not tool_id:
            raise RuntimeError(
                f"Creating AgentKit Tool '{name}' did not return a Tool ID."
            )

    return _wait_for_ready_tool(
        tools_client,
        tools_types,
        tool_id=tool_id,
        name=name,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        sleep=sleep,
        enable_snapshot=enable_snapshot,
    )


def ensure_studio_agent_tool(
    *,
    name: str,
    kind: str,
    model_name: str,
    access_key: str = "",
    secret_key: str = "",
    region: str = "cn-beijing",
    session_token: str = "",
    client: Any | None = None,
    timeout_seconds: float = 600.0,
    poll_interval: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    enable_snapshot: bool = True,
) -> str:
    """Reuse or create one ready managed Hermes/OpenClaw Tool."""
    from agentkit.sdk.tools import types as tools_types
    from agentkit.sdk.tools.client import AgentkitToolsClient

    tool_type = _AGENT_TOOL_TYPES.get(kind)
    if tool_type is None:
        raise ValueError(f"Unsupported Studio sandbox agent kind: {kind}")
    normalized_model_name = model_name.strip()
    if not normalized_model_name:
        raise ValueError("model_name must not be empty")

    tools_client = client or AgentkitToolsClient(
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        session_token=session_token,
    )
    match = _find_exact_tool(
        tools_client,
        tools_types,
        name=name,
        tool_type=tool_type,
    )
    if match is not None:
        tool_id = (match.tool_id or "").strip()
        if not tool_id:
            raise RuntimeError(f"AgentKit Tool '{name}' did not return a Tool ID.")
    else:
        response = tools_client.create_tool(
            tools_types.CreateToolRequest(
                Name=name,
                ToolType=tool_type,
                ProjectName=_PROJECT_NAME,
                ModelAgentName=normalized_model_name,
                CpuMilli=4000,
                MemoryMb=8192,
                EnableSnapshot=True if enable_snapshot else None,
                AuthorizerConfiguration=tools_types.AuthorizerForCreateTool(
                    KeyAuth=tools_types.AuthorizerKeyAuthForCreateTool(
                        ApiKeyName=f"studio-{kind}-{secrets.token_hex(8)}",
                        ApiKeyLocation="Header",
                    )
                ),
                NetworkConfiguration=tools_types.NetworkForCreateTool(
                    EnablePublicNetwork=True,
                    EnablePrivateNetwork=False,
                ),
            )
        )
        tool_id = (response.tool_id or "").strip()
        if not tool_id:
            raise RuntimeError(
                f"Creating AgentKit {tool_type} Tool '{name}' did not return a Tool ID."
            )

    return _wait_for_ready_tool(
        tools_client,
        tools_types,
        tool_id=tool_id,
        name=name,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        sleep=sleep,
        enable_snapshot=enable_snapshot,
    )


def ensure_studio_tool_snapshot(
    *,
    tool_id: str,
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
    """Ensure an explicitly configured Studio Tool has snapshots enabled."""
    from agentkit.sdk.tools import types as tools_types
    from agentkit.sdk.tools.client import AgentkitToolsClient

    tools_client = client or AgentkitToolsClient(
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        session_token=session_token,
    )
    return _wait_for_ready_tool(
        tools_client,
        tools_types,
        tool_id=tool_id,
        name=name,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        sleep=sleep,
        enable_snapshot=True,
    )


def ensure_studio_agent_model_credential(
    *,
    tool_id: str,
    kind: str,
    model_name: str,
    access_key: str,
    secret_key: str,
    session_token: str | None = None,
    region: str = "cn-beijing",
    model_base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
) -> None:
    """Bind the complete model environment required by Hermes/OpenClaw."""
    if kind not in _AGENT_TOOL_TYPES:
        raise ValueError(f"Unsupported Studio sandbox agent kind: {kind}")
    normalized_model_name = model_name.strip()
    if not normalized_model_name:
        raise ValueError("model_name must not be empty")

    from agentkit.auth._openapi import OpenApiClient

    from veadk.auth.veauth.ark_veauth import get_ark_token

    api = OpenApiClient(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
    )
    response = api.call("agentkit", "GetTool", "2025-10-30", {"ToolId": tool_id})
    tool = response.get("Tool") if isinstance(response.get("Tool"), dict) else response
    if not isinstance(tool, dict):
        raise TypeError("AgentKit Tool response is invalid.")
    envs = {
        item.get("Key"): item.get("Value")
        for item in tool.get("Envs", [])
        if isinstance(item, dict) and item.get("Key")
    }
    model_api_key = get_ark_token(
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
    )
    normalized_base_url = model_base_url.strip().rstrip("/")
    if not normalized_base_url:
        raise ValueError("model_base_url must not be empty")
    updates = {
        "MODEL_AGENT_API_KEY": model_api_key,
        "MODEL_AGENT_NAME": normalized_model_name,
        "MODEL_AGENT_BASE_URL": normalized_base_url,
        "ARK_BASE_URL": normalized_base_url,
    }
    if all(envs.get(key) == value for key, value in updates.items()):
        return
    envs.update(updates)
    api.call(
        "agentkit",
        "UpdateTool",
        "2025-10-30",
        {
            "ToolId": tool_id,
            "Envs": [{"Key": key, "Value": value} for key, value in envs.items()],
        },
    )
