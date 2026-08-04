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
_DEV_TOOL_TYPE = "DevEnv"
_DEVENV_IMAGE_URL = (
    "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/devenv:0.0.1"
)
STUDIO_SANDBOX_AGENT_MODEL_NAME = "doubao-seed-2-1-pro-260628"
STUDIO_SANDBOX_BYTEPLUS_AGENT_MODEL_NAME = "seed-2-0-lite-260228"
STUDIO_SANDBOX_MODEL_BASE_URLS = {
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
    "byteplus": "https://ark.ap-southeast.bytepluses.com/api/v3",
}
_AGENT_TOOL_TYPES = {
    "openclaw": "ArkClawEnv",
    "hermes": "HermesEnv",
}
_READY_STATUS = "Ready"
_FAILED_STATUSES = frozenset({"Error", "Failed", "CreateFailed", "Deleting", "Deleted"})


def studio_sandbox_agent_model_name(provider: str) -> str:
    if provider == "byteplus":
        return STUDIO_SANDBOX_BYTEPLUS_AGENT_MODEL_NAME
    return STUDIO_SANDBOX_AGENT_MODEL_NAME


def studio_sandbox_model_base_url(provider: str) -> str:
    try:
        return STUDIO_SANDBOX_MODEL_BASE_URLS[provider]
    except KeyError as error:
        raise ValueError(f"Unsupported Studio cloud provider: {provider}") from error


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
) -> str:
    deadline = time.monotonic() + timeout_seconds
    while True:
        tool = tools_client.get_tool(tools_types.GetToolRequest(ToolId=tool_id))
        status = (tool.status or "").strip()
        if status == _READY_STATUS:
            return tool_id
        if status in _FAILED_STATUSES:
            raise RuntimeError(
                f"AgentKit Tool '{name}' failed to become ready: {status}."
            )
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for AgentKit Tool '{name}'.")
        sleep(poll_interval)


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


def _ensure_studio_environment_tool(
    *,
    name: str,
    tool_type: str,
    access_key: str = "",
    secret_key: str = "",
    region: str = "cn-beijing",
    session_token: str = "",
    client: Any | None = None,
    timeout_seconds: float = 600.0,
    poll_interval: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Reuse or create one ready managed environment Tool."""
    from agentkit.sdk.tools import types as tools_types
    from agentkit.sdk.tools.client import AgentkitToolsClient

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
                CpuMilli=4000,
                MemoryMb=8192,
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
    )


def ensure_studio_code_env_tool(**kwargs: Any) -> str:
    """Reuse or create one Ready CodeEnv Tool and return its Tool ID."""
    return _ensure_studio_environment_tool(tool_type=_TOOL_TYPE, **kwargs)


def ensure_studio_dev_env_tool(**kwargs: Any) -> str:
    """Reuse or create one Ready DevEnv Tool and return its Tool ID."""
    return _ensure_studio_environment_tool(tool_type=_DEV_TOOL_TYPE, **kwargs)


def ensure_studio_devenv_tool(
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
    """Reuse or create the Ready DevEnv Tool dedicated to the Skill workbench."""
    from agentkit.sdk.tools import types as tools_types
    from agentkit.sdk.tools.client import AgentkitToolsClient

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
        tool_type=_DEV_TOOL_TYPE,
    )
    if match is not None:
        tool_id = (match.tool_id or "").strip()
        if not tool_id:
            raise RuntimeError(f"AgentKit Tool '{name}' did not return a Tool ID.")
    else:
        response = tools_client.create_tool(
            tools_types.CreateToolRequest(
                Name=name,
                ToolType=_DEV_TOOL_TYPE,
                ProjectName=_PROJECT_NAME,
                ImageUrl=_DEVENV_IMAGE_URL,
                Command="/opt/gem/run.sh",
                Port=8080,
                CpuMilli=4000,
                MemoryMb=8192,
                AuthorizerConfiguration=tools_types.AuthorizerForCreateTool(
                    KeyAuth=tools_types.AuthorizerKeyAuthForCreateTool(
                        ApiKeyName=f"studio-devenv-{secrets.token_hex(8)}",
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
                f"Creating AgentKit DevEnv Tool '{name}' did not return a Tool ID."
            )
    return _wait_for_ready_tool(
        tools_client,
        tools_types,
        tool_id=tool_id,
        name=name,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
        sleep=sleep,
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
    model_base_url: str = STUDIO_SANDBOX_MODEL_BASE_URLS["volcengine"],
    provider: str = "volcengine",
    client: Any | None = None,
) -> None:
    """Bind the complete model environment required by Hermes/OpenClaw."""
    if kind not in _AGENT_TOOL_TYPES:
        raise ValueError(f"Unsupported Studio sandbox agent kind: {kind}")
    normalized_model_name = model_name.strip()
    if not normalized_model_name:
        raise ValueError("model_name must not be empty")

    from veadk.auth.veauth.ark_veauth import get_ark_token

    from agentkit.sdk.tools import types as tools_types
    from agentkit.sdk.tools.client import AgentkitToolsClient

    tools_client = client or AgentkitToolsClient(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token or "",
        region=region,
    )
    tool = tools_client.get_tool(tools_types.GetToolRequest(ToolId=tool_id))
    envs = {item.key: item.value for item in tool.envs or [] if item.key}
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
    current_model_name = str(getattr(tool, "model_agent_name", "") or "").strip()
    if current_model_name == normalized_model_name and all(
        envs.get(key) == value for key, value in updates.items()
    ):
        return
    envs.update(updates)
    updated_envs = [{"Key": key, "Value": value} for key, value in envs.items()]
    tools_client.update_tool(
        tools_types.UpdateToolRequest(
            ToolId=tool_id,
            ModelAgentName=normalized_model_name,
            Envs=updated_envs,
        )
    )
