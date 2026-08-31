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

"""Create or reuse the AgentKit Private Tool backing an AIO environment."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

_PROJECT_NAME = "default"
_PRIVATE_TOOL_TYPE = "Private"
_PRIVATE_TOOL_COMMAND = "/opt/gem/run.sh"
_PRIVATE_TOOL_PORT = 8080
_PRIVATE_TOOL_ENVS = {
    "PATH": (
        "/usr/local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    ),
    "DEBIAN_FRONTEND": "noninteractive",
    "USER": "gem",
    "USER_UID": "1000",
    "USER_GID": "1000",
    "DISPLAY": ":99.0",
    "DISPLAY_WIDTH": "1280",
    "DISPLAY_HEIGHT": "1024",
    "DISPLAY_DEPTH": "24",
    "XDG_RUNTIME_DIR": "/tmp/runtime-gem",
    "BROWSER_EXECUTABLE_PATH": "/usr/local/bin/browser",
    "BROWSER_REMOTE_DEBUGGING_PORT": "9222",
    "BROWSER_COMMANDLINE_ARGS": (
        "--disable-backgrounding-occluded-windows "
        "--disable-background-timer-throttling "
        "--disable-blink-features=AutomationControlled "
        "--disable-dev-shm-usage "
        "--disable-external-intent-requests "
        "--disable-features=IPH_DesktopCustomizeChrome,IsolateOrigins,"
        "site-per-proces,Translate "
        "--disable-focus-on-load --disable-gpu --disable-infobars "
        "--disable-popup-blocking --disable-prompt-on-repost "
        "--disable-renderer-backgrounding --disable-site-isolation-trials "
        "--disable-web-security --disable-window-activation --mute-audio "
        "--no-default-browser-check --no-first-run --noerrdialogs "
        "--remote-allow-origins=* --remote-debugging-port=9222 "
        "--suppress-message-center-popups --start-maximized"
    ),
    "BROWSER_EXTRA_ARGS": "",
    "DNS_OVER_HTTPS_TEMPLATES": "",
    "LOG_DIR": "/var/log/gem",
    "JWT_PUBLIC_KEY": "",
    "VNC_SERVER_PORT": "5900",
    "WEBSOCKET_PROXY_PORT": "6080",
    "GEM_SERVER_PORT": "8088",
    "MCP_SERVER_PORT": "8089",
    "PUBLIC_PORT": "8080",
    "AUTH_BACKEND_PORT": "8081",
    "WAIT_PORTS": "8091",
    "WAIT_TIMEOUT": "300",
    "WAIT_INTERVAL": "0.25",
    "RUN_HOOK_INIT": "",
    "RUN_HOOK_PRE_SERVICES": "",
    "RUN_HOOK_POST_READY": "",
    "RUN_HOOKS_STRICT": "false",
    "SANDBOX_SRV_PORT": "8091",
    "JUPYTER_LAB_PORT": "8888",
    "CODE_SERVER_PORT": "8200",
    "MCP_SERVER_BROWSER_PORT": "8100",
    "TINYPROXY_PORT": "8118",
    "MAX_SHELL_SESSIONS": "50",
    "PYTHONPATH": "",
    "LOG_TOOL_TRACE": "false",
    "LANG": "en_US.UTF-8",
    "LANGUAGE": "en_US:en",
    "LC_ALL": "en_US.UTF-8",
    "PUPPETEER_EXECUTABLE_PATH": "/usr/local/bin/browser",
    "PUPPETEER_SKIP_CHROMIUM_DOWNLOAD": "true",
    "BROWSER_NO_SANDBOX": "",
    "BROWSER_LANG": "en-US",
    "BROWSER_USER_AGENT": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 "
        "Safari/537.36"
    ),
    "UV_TOOL_BIN_DIR": "/usr/local/bin/",
    "UV_TOOL_DIR": "/usr/local/share/uv/tools",
    "DISABLE_JUPYTER": "false",
    "DISABLE_CODE_SERVER": "false",
    "EXTRA_MCP_SERVERS": "",
    "OTEL_SDK_DISABLED": "false",
    "SRV_PYTHONPATH": (
        "/otel-auto-instrumentation-python/opentelemetry/instrumentation/"
        "auto_instrumentation:/otel-auto-instrumentation-python"
    ),
    "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS": "redis",
    "FAAS_SANDBOX_RUNTIME_INJECTION_ENABLE_SANDBOXD": "false",
    "PYTHON_CODE_EXEC_VERSION": "python3",
    "GO_PATH": "/usr/local/go",
}
_MODEL_TOOL_ENV_KEYS = frozenset(
    {
        "MODEL_AGENT_API_KEY",
        "MODEL_AGENT_NAME",
        "MODEL_AGENT_API_BASE",
        "MODEL_AGENT_BASE_URL",
        "MODEL_AGENT_PROVIDER",
        "CODEX_API_KEY",
        "CODEX_BASE_URL",
        "CODEX_MODEL",
    }
)
_READY_STATUS = "ready"
_FAILED_STATUSES = frozenset({"error", "failed", "createfailed", "deleting", "deleted"})
_TOOL_READY_TIMEOUT_SECONDS = 300.0
_POLL_INTERVAL_SECONDS = 2.0


@dataclass(frozen=True)
class EnvironmentToolState:
    tool_id: str
    name: str
    status: str


class EnvironmentToolProvisioner(Protocol):
    async def ensure_ready(
        self,
        *,
        image: str,
        provider: str,
        region: str,
    ) -> EnvironmentToolState: ...


class AgentkitEnvironmentToolProvisioner:
    """Idempotently provision one ready Private Tool per immutable image."""

    def __init__(
        self,
        client_factory: Callable[[str, str], Any],
        *,
        model_environment_resolver: Callable[[str, str], Mapping[str, str]]
        | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout_seconds: float = _TOOL_READY_TIMEOUT_SECONDS,
        poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
    ) -> None:
        self._client_factory = client_factory
        self._model_environment_resolver = model_environment_resolver
        self._sleep = sleep
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._locks: dict[tuple[str, str, str], asyncio.Lock] = {}

    async def ensure_ready(
        self,
        *,
        image: str,
        provider: str,
        region: str,
    ) -> EnvironmentToolState:
        normalized_image = image.strip()
        if not normalized_image:
            raise ValueError("AIO environment image must not be empty.")
        key = (provider.strip(), region.strip(), normalized_image)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            client = self._client_factory(key[0], key[1])
            tool_envs = dict(_PRIVATE_TOOL_ENVS)
            if self._model_environment_resolver is not None:
                tool_envs.update(
                    {
                        env_key: str(value).strip()
                        for env_key, value in self._model_environment_resolver(
                            key[0], key[1]
                        ).items()
                        if env_key in _MODEL_TOOL_ENV_KEYS and str(value).strip()
                    }
                )
            return await asyncio.to_thread(
                self._ensure_ready,
                client,
                normalized_image,
                tool_envs,
            )

    def _ensure_ready(
        self,
        client: Any,
        image: str,
        tool_envs: Mapping[str, str],
    ) -> EnvironmentToolState:
        from agentkit.sdk.tools import types as tools_types

        name = environment_tool_name(image)
        match = _find_tool(client, tools_types, name)
        created_new = match is None
        if match is None:
            try:
                created = client.create_tool(
                    tools_types.CreateToolRequest(
                        Name=name,
                        ToolType=_PRIVATE_TOOL_TYPE,
                        ProjectName=_PROJECT_NAME,
                        ClientToken=secrets.token_hex(16),
                        Description="Studio session environment",
                        ImageUrl=image,
                        ModelAgentName=tool_envs.get("MODEL_AGENT_NAME", ""),
                        Command=_PRIVATE_TOOL_COMMAND,
                        Port=_PRIVATE_TOOL_PORT,
                        CpuMilli=2000,
                        MemoryMb=4096,
                        Envs=[
                            tools_types.EnvsItemForCreateTool(Key=key, Value=value)
                            for key, value in tool_envs.items()
                        ],
                        AuthorizerConfiguration=tools_types.AuthorizerForCreateTool(
                            KeyAuth=tools_types.AuthorizerKeyAuthForCreateTool(
                                ApiKeyName=f"studio-env-{secrets.token_hex(8)}",
                                ApiKeyLocation="Header",
                            )
                        ),
                        NetworkConfiguration=tools_types.NetworkForCreateTool(
                            EnablePublicNetwork=True,
                            EnablePrivateNetwork=False,
                        ),
                    )
                )
                tool_id = _tool_id(created)
            except Exception:
                # Another Studio worker can win the deterministic create.
                match = _find_tool(client, tools_types, name)
                if match is None:
                    raise
                tool_id = _validated_tool_id(match, image)
        else:
            tool_id = _validated_tool_id(match, image)
        if not tool_id:
            raise RuntimeError("AgentKit did not return a Tool ID.")
        if not created_new:
            current = client.get_tool(tools_types.GetToolRequest(ToolId=tool_id))
            if _tool_requires_update(current, image, tool_envs):
                current_envs = {
                    str(getattr(item, "key", "") or ""): str(
                        getattr(item, "value", "") or ""
                    )
                    for item in (getattr(current, "envs", None) or [])
                    if str(getattr(item, "key", "") or "")
                }
                current_envs.update(tool_envs)
                client.update_tool(
                    tools_types.UpdateToolRequest(
                        ToolId=tool_id,
                        ToolType=_PRIVATE_TOOL_TYPE,
                        ImageUrl=image,
                        ModelAgentName=tool_envs.get("MODEL_AGENT_NAME", ""),
                        Command=_PRIVATE_TOOL_COMMAND,
                        Port=_PRIVATE_TOOL_PORT,
                        CpuMilli=2000,
                        MemoryMb=4096,
                        Envs=[
                            tools_types.EnvsItemForUpdateTool(Key=key, Value=value)
                            for key, value in current_envs.items()
                        ],
                    )
                )

        deadline = time.monotonic() + self._timeout_seconds
        while True:
            tool = client.get_tool(tools_types.GetToolRequest(ToolId=tool_id))
            status = str(getattr(tool, "status", "") or "").strip().lower()
            if status == _READY_STATUS:
                return EnvironmentToolState(
                    tool_id=tool_id,
                    name=name,
                    status=_READY_STATUS,
                )
            if status in _FAILED_STATUSES:
                raise RuntimeError("AgentKit environment Tool failed to become ready.")
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for the environment Tool.")
            self._sleep(self._poll_interval_seconds)


def environment_tool_name(image: str) -> str:
    digest = hashlib.sha256(image.encode()).hexdigest()[:16]
    return f"studio-env-{digest}"


def _validated_tool_id(tool: Any, image: str) -> str:
    current_image = str(getattr(tool, "image_url", "") or "").strip()
    if current_image and current_image != image:
        raise RuntimeError("Managed environment Tool image does not match.")
    return _tool_id(tool)


def _tool_id(tool: Any) -> str:
    return str(getattr(tool, "tool_id", "") or "").strip()


def _tool_requires_update(
    tool: Any,
    image: str,
    required_envs: Mapping[str, str],
) -> bool:
    envs = {
        str(getattr(item, "key", "") or ""): str(getattr(item, "value", "") or "")
        for item in (getattr(tool, "envs", None) or [])
        if str(getattr(item, "key", "") or "")
    }
    return (
        str(getattr(tool, "image_url", "") or "").strip() != image
        or str(getattr(tool, "model_agent_name", "") or "").strip()
        != required_envs.get("MODEL_AGENT_NAME", "")
        or str(getattr(tool, "command", "") or "").strip() != _PRIVATE_TOOL_COMMAND
        or int(getattr(tool, "port", 0) or 0) != _PRIVATE_TOOL_PORT
        or any(envs.get(key) != value for key, value in required_envs.items())
    )


def _find_tool(client: Any, tools_types: Any, name: str) -> Any | None:
    next_token: str | None = None
    matches: list[Any] = []
    while True:
        response = client.list_tools(
            tools_types.ListToolsRequest(
                ProjectName=_PROJECT_NAME,
                MaxResults=100,
                NextToken=next_token,
                Filters=[
                    tools_types.FiltersItemForListTools(Name="Name", Values=[name])
                ],
            )
        )
        matches.extend(
            item
            for item in (getattr(response, "tools", None) or [])
            if str(getattr(item, "name", "") or "") == name
            and str(getattr(item, "project_name", "") or _PROJECT_NAME) == _PROJECT_NAME
            and str(getattr(item, "tool_type", "") or "") == _PRIVATE_TOOL_TYPE
        )
        next_token = str(getattr(response, "next_token", "") or "") or None
        if next_token is None:
            break
    if len(matches) > 1:
        raise RuntimeError("Multiple managed environment Tools were found.")
    return matches[0] if matches else None


__all__ = [
    "AgentkitEnvironmentToolProvisioner",
    "EnvironmentToolProvisioner",
    "EnvironmentToolState",
    "environment_tool_name",
]
