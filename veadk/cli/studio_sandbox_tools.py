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
import threading
import time
import zlib
from collections.abc import Callable
from typing import Any

from veadk.cli.studio_model_catalog import (
    BYTEPLUS_MODELARK_BASE_URL,
    BYTEPLUS_STUDIO_AGENT_MODEL_NAME,
    VOLCENGINE_MODELARK_BASE_URL,
    VOLCENGINE_STUDIO_AGENT_MODEL_NAME,
)

_PROJECT_NAME = "default"
_TOOL_TYPE = "CodeEnv"
_DEV_TOOL_TYPE = "DevEnv"
_TOOL_NAME_APP_MAX_LENGTH = 20
_TOOL_NAME_HASH_LENGTH = 6
STUDIO_SANDBOX_AGENT_MODEL_NAME = VOLCENGINE_STUDIO_AGENT_MODEL_NAME
STUDIO_SANDBOX_BYTEPLUS_AGENT_MODEL_NAME = BYTEPLUS_STUDIO_AGENT_MODEL_NAME
STUDIO_SANDBOX_MODEL_BASE_URLS = {
    "volcengine": VOLCENGINE_MODELARK_BASE_URL,
    "byteplus": BYTEPLUS_MODELARK_BASE_URL,
}
_AGENT_TOOL_TYPES = {
    "openclaw": "ArkClawEnv",
    "hermes": "HermesEnv",
}
_READY_STATUS = "Ready"
_FAILED_STATUSES = frozenset({"Error", "Failed", "CreateFailed", "Deleting", "Deleted"})
_RETRYABLE_CREATE_STATUS_CODES = frozenset({408, 409, 425, 429})
_RETRYABLE_CREATE_ERROR_CODES = frozenset(
    {
        "internalerror",
        "internalservererror",
        "requestlimitexceeded",
        "serviceunavailable",
        "throttling",
        "toomanyrequests",
    }
)
_RETRYABLE_CREATE_ERROR_MARKERS = (
    "connection aborted",
    "connection error",
    "connection reset",
    "internal server error",
    "network error",
    "qps",
    "rate limit",
    "request limit",
    "service unavailable",
    "temporarily unavailable",
    "throttl",
    "timed out",
    "timeout",
    "too many requests",
)
_CREATE_TOOL_RATE_LOCK = threading.Lock()
_NEXT_CREATE_TOOL_AT = 0.0


def studio_sandbox_agent_model_name(provider: str) -> str:
    if provider == "byteplus":
        return STUDIO_SANDBOX_BYTEPLUS_AGENT_MODEL_NAME
    return STUDIO_SANDBOX_AGENT_MODEL_NAME


def studio_sandbox_model_base_url(provider: str) -> str:
    try:
        return STUDIO_SANDBOX_MODEL_BASE_URLS[provider]
    except KeyError as error:
        raise ValueError(f"Unsupported Studio cloud provider: {provider}") from error


def studio_sandbox_tool_name(
    application_name: str,
    purpose: str,
    *,
    snapshot: bool = False,
) -> str:
    """Return a stable, account-local Tool name for one Studio capability."""
    safe_name = re.sub(r"[^a-z0-9-]+", "-", application_name.lower()).strip("-")
    suffix = "_snapshot" if snapshot else ""
    safe_name = safe_name[:_TOOL_NAME_APP_MAX_LENGTH].rstrip("-") or "app"
    digest = f"{zlib.crc32(application_name.encode()):08x}"[:_TOOL_NAME_HASH_LENGTH]
    name = f"studio-{safe_name}-{purpose}-{digest}"
    return f"{name}{suffix}"


def studio_sandbox_tool_name_candidates(
    application_name: str,
    purpose: str,
    *,
    snapshot: bool = False,
) -> tuple[str, ...]:
    """Return the preferred Tool name followed by compatible legacy names."""
    names = [
        studio_sandbox_tool_name(
            application_name,
            purpose,
            snapshot=snapshot,
        )
    ]
    if purpose == "codex":
        names.append(
            studio_sandbox_tool_name(
                application_name,
                "chat",
                snapshot=snapshot,
            )
        )
    return tuple(names)


def _wait_for_ready_tool(
    tools_client: Any,
    tools_types: Any,
    *,
    tool_id: str,
    name: str,
    enable_snapshot: bool,
    timeout_seconds: float,
    poll_interval: float,
    sleep: Callable[[float], None],
) -> str:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            tool = tools_client.get_tool(tools_types.GetToolRequest(ToolId=tool_id))
        except Exception as error:
            raise RuntimeError(
                f"Failed to query AgentKit Tool '{name}' "
                f"(Tool ID: '{tool_id}') status: {error}"
            ) from error
        status = (tool.status or "").strip()
        if status == _READY_STATUS:
            actual_snapshot = bool(getattr(tool, "enable_snapshot", False))
            if actual_snapshot != enable_snapshot:
                expected = "enabled" if enable_snapshot else "disabled"
                actual = "enabled" if actual_snapshot else "disabled"
                raise RuntimeError(
                    f"AgentKit Tool '{name}' (Tool ID: '{tool_id}') "
                    f"has snapshot {actual}; "
                    f"expected snapshot {expected}."
                )
            return tool_id
        if status in _FAILED_STATUSES:
            raise RuntimeError(
                f"AgentKit Tool '{name}' (Tool ID: '{tool_id}') "
                f"failed to become ready: {status}."
            )
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Timed out waiting for AgentKit Tool '{name}' (Tool ID: '{tool_id}')."
            )
        sleep(poll_interval)


def _is_retryable_tool_creation_error(error: Exception) -> bool:
    """Return whether a Tool creation failure is safe to retry."""
    candidates: list[Any] = []
    current: BaseException | None = error
    while current is not None and current not in candidates:
        candidates.append(current)
        current = current.__cause__ or current.__context__
    response = getattr(error, "response", None)
    if response is not None and response not in candidates:
        candidates.append(response)

    details = []
    for candidate in candidates:
        if isinstance(candidate, (ConnectionError, TimeoutError)):
            return True
        details.append(str(candidate))
        for attribute in ("status_code", "status", "code", "error_code"):
            value = getattr(candidate, attribute, None)
            if value is not None:
                details.append(str(value))
                normalized_code = re.sub(r"[^a-z0-9]", "", str(value).lower())
                if normalized_code in _RETRYABLE_CREATE_ERROR_CODES:
                    return True
            try:
                status_code = int(value)
            except (TypeError, ValueError):
                continue
            if (
                status_code in _RETRYABLE_CREATE_STATUS_CODES
                or 500 <= status_code < 600
            ):
                return True

    detail = " ".join(details).lower()
    return any(marker in detail for marker in _RETRYABLE_CREATE_ERROR_MARKERS)


def _created_tool_id(match: Any | None, *, name: str) -> str | None:
    if match is None:
        return None
    tool_id = (match.tool_id or "").strip()
    if not tool_id:
        raise RuntimeError(f"AgentKit Tool '{name}' did not return a Tool ID.")
    return tool_id


def _wait_for_tool_creation_slot(
    interval_seconds: float,
    *,
    sleep: Callable[[float], None],
) -> None:
    """Serialize create_tool starts while leaving other provisioning work parallel."""
    if interval_seconds < 0:
        raise ValueError("create_min_interval must not be negative")
    if interval_seconds == 0:
        return

    global _NEXT_CREATE_TOOL_AT
    with _CREATE_TOOL_RATE_LOCK:
        now = time.monotonic()
        delay = max(0.0, _NEXT_CREATE_TOOL_AT - now)
        if delay:
            sleep(delay)
            now = time.monotonic()
        _NEXT_CREATE_TOOL_AT = max(now, _NEXT_CREATE_TOOL_AT) + interval_seconds


def _create_tool_with_retry(
    tools_client: Any,
    tools_types: Any,
    *,
    request: Any,
    name: str,
    tool_type: str,
    create_max_attempts: int,
    create_retry_delay: float,
    create_min_interval: float,
    sleep: Callable[[float], None],
) -> str:
    if create_max_attempts < 1:
        raise ValueError("create_max_attempts must be at least 1")
    if create_retry_delay < 0:
        raise ValueError("create_retry_delay must not be negative")
    if create_min_interval < 0:
        raise ValueError("create_min_interval must not be negative")

    for attempt in range(1, create_max_attempts + 1):
        if attempt > 1:
            sleep(create_retry_delay * (2 ** (attempt - 2)))
            try:
                recovered_id = _created_tool_id(
                    _find_exact_tool(
                        tools_client,
                        tools_types,
                        name=name,
                        tool_type=tool_type,
                    ),
                    name=name,
                )
            except Exception:
                recovered_id = None
            if recovered_id:
                return recovered_id

        try:
            _wait_for_tool_creation_slot(create_min_interval, sleep=sleep)
            response = tools_client.create_tool(request)
        except Exception as error:
            if attempt < create_max_attempts and _is_retryable_tool_creation_error(
                error
            ):
                continue
            raise RuntimeError(
                f"Creating AgentKit Tool '{name}' failed after {attempt} attempt(s)."
            ) from error

        tool_id = (response.tool_id or "").strip()
        if not tool_id:
            raise RuntimeError(
                f"Creating AgentKit Tool '{name}' did not return a Tool ID."
            )
        return tool_id

    raise AssertionError("unreachable")


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
    enable_snapshot: bool = False,
    legacy_names: tuple[str, ...] = (),
    client: Any | None = None,
    timeout_seconds: float = 600.0,
    poll_interval: float = 5.0,
    create_max_attempts: int = 3,
    create_retry_delay: float = 1.0,
    create_min_interval: float = 0.0,
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
    matched_name = name
    match = None
    seen_names: set[str] = set()
    for candidate_name in (name, *legacy_names):
        if candidate_name in seen_names:
            continue
        seen_names.add(candidate_name)
        match = _find_exact_tool(
            tools_client,
            tools_types,
            name=candidate_name,
            tool_type=tool_type,
        )
        if match is not None:
            matched_name = candidate_name
            break
    if match is not None:
        tool_id = _created_tool_id(match, name=matched_name)
        assert tool_id is not None
    else:
        tool_id = _create_tool_with_retry(
            tools_client,
            tools_types,
            request=tools_types.CreateToolRequest(
                Name=name,
                ToolType=tool_type,
                ProjectName=_PROJECT_NAME,
                ClientToken=secrets.token_hex(16),
                EnableSnapshot=enable_snapshot,
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
            ),
            name=name,
            tool_type=tool_type,
            create_max_attempts=create_max_attempts,
            create_retry_delay=create_retry_delay,
            create_min_interval=create_min_interval,
            sleep=sleep,
        )

    return _wait_for_ready_tool(
        tools_client,
        tools_types,
        tool_id=tool_id,
        name=matched_name,
        enable_snapshot=enable_snapshot,
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


def ensure_studio_agent_tool(
    *,
    name: str,
    kind: str,
    model_name: str,
    access_key: str = "",
    secret_key: str = "",
    region: str = "cn-beijing",
    session_token: str = "",
    enable_snapshot: bool = False,
    client: Any | None = None,
    timeout_seconds: float = 600.0,
    poll_interval: float = 5.0,
    create_max_attempts: int = 3,
    create_retry_delay: float = 1.0,
    create_min_interval: float = 0.0,
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
        tool_id = _created_tool_id(match, name=name)
        assert tool_id is not None
    else:
        tool_id = _create_tool_with_retry(
            tools_client,
            tools_types,
            request=tools_types.CreateToolRequest(
                Name=name,
                ToolType=tool_type,
                ProjectName=_PROJECT_NAME,
                ClientToken=secrets.token_hex(16),
                EnableSnapshot=enable_snapshot,
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
            ),
            name=name,
            tool_type=tool_type,
            create_max_attempts=create_max_attempts,
            create_retry_delay=create_retry_delay,
            create_min_interval=create_min_interval,
            sleep=sleep,
        )

    return _wait_for_ready_tool(
        tools_client,
        tools_types,
        tool_id=tool_id,
        name=name,
        enable_snapshot=enable_snapshot,
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
