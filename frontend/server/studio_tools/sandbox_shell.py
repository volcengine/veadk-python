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

"""Execute shell commands in a session-mounted Studio environment."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from frontend.server.environments.session_mounts import (
    SessionEnvironmentMount,
    SessionEnvironmentMountRegistry,
)
from frontend.server.studio_tools.registry import (
    StudioTool,
    StudioToolExecutionContext,
    StudioToolExecutionError,
    StudioToolRegistry,
)
from veadk.cli.agentkit_session_metadata import build_create_session_request
from veadk.cli.codex_app_server import sandbox_service_url

_READY_STATUS = "ready"
_FAILED_TOOL_STATUSES = frozenset(
    {"error", "failed", "createfailed", "deleting", "deleted"}
)
_SESSION_TTL_SECONDS = 4 * 60 * 60
_SESSION_READY_TIMEOUT_SECONDS = 90
_POLL_INTERVAL_SECONDS = 2.0
_MAX_RESPONSE_BYTES = 128 * 1024
_MAX_OUTPUT_BYTES = 96 * 1024
_ALLOWED_TARGET_HEADERS = frozenset({"authorization", "x-api-key"})


class SandboxTargetResolver(Protocol):
    async def resolve(
        self,
        mount: SessionEnvironmentMount,
        context: StudioToolExecutionContext,
    ) -> SandboxExecutionTarget: ...


class SandboxResolutionError(RuntimeError):
    """A safe, actionable failure while resolving a mounted Sandbox."""


@dataclass(frozen=True)
class SandboxExecutionTarget:
    """A server-only Sandbox data-plane capability."""

    endpoint: str
    session_id: str
    tool_id: str = ""
    headers: Mapping[str, str] | None = None


@dataclass(frozen=True)
class _CachedTarget:
    image: str
    tool_id: str
    target: SandboxExecutionTarget


class AgentkitEnvironmentSandboxResolver:
    """Create one reusable Private Sandbox Session per mounted Agent session."""

    def __init__(
        self,
        client_factory: Callable[[str, str], Any],
        *,
        sleep: Callable[[float], Any] = asyncio.sleep,
        poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
    ) -> None:
        self._client_factory = client_factory
        self._sleep = sleep
        self._poll_interval_seconds = poll_interval_seconds
        self._targets: dict[tuple[str, str, str, str, str], _CachedTarget] = {}
        self._locks: dict[tuple[str, str, str, str, str], asyncio.Lock] = {}

    async def resolve(
        self,
        mount: SessionEnvironmentMount,
        context: StudioToolExecutionContext,
    ) -> SandboxExecutionTarget:
        key = (*_context_key(context), mount.environment_id)
        cached = self._targets.get(key)
        if (
            cached is not None
            and cached.image == mount.image
            and cached.tool_id == mount.tool_id
        ):
            return cached.target

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._targets.get(key)
            if (
                cached is not None
                and cached.image == mount.image
                and cached.tool_id == mount.tool_id
            ):
                return cached.target

            if not mount.tool_id or mount.tool_status != _READY_STATUS:
                raise SandboxResolutionError(
                    "The mounted environment version does not have a persisted Tool "
                    "in Ready status. Rebuild the environment before running commands."
                )
            client = self._client_factory(mount.provider, mount.region)
            tool_id = mount.tool_id
            await _require_ready_tool(client, tool_id, mount.image)
            target = await self._session_for_mount(client, tool_id, mount, context)
            self._targets[key] = _CachedTarget(
                image=mount.image,
                tool_id=tool_id,
                target=target,
            )
            return target

    async def _session_for_mount(
        self,
        client: Any,
        tool_id: str,
        mount: SessionEnvironmentMount,
        context: StudioToolExecutionContext,
    ) -> SandboxExecutionTarget:
        from agentkit.sdk.tools import types as tools_types

        user_session_id = _user_session_id(context, mount)
        existing = await asyncio.to_thread(
            _find_session,
            client,
            tools_types,
            tool_id,
            user_session_id,
        )
        if existing is None:
            request = build_create_session_request(
                tool_id=tool_id,
                ttl_seconds=_SESSION_TTL_SECONDS,
                user_session_id=user_session_id,
                display_name=f"Environment {mount.environment_id[:8]}",
                username=context.owner_id or context.user_id,
                agent_kind="environment-execution",
            )
            try:
                existing = await asyncio.to_thread(client.create_session, request)
            except Exception:
                existing = await asyncio.to_thread(
                    _find_session,
                    client,
                    tools_types,
                    tool_id,
                    user_session_id,
                )
                if existing is None:
                    raise

        session_id = str(getattr(existing, "session_id", "") or "").strip()
        endpoint = str(getattr(existing, "endpoint", "") or "").strip()
        if not session_id:
            raise RuntimeError("AgentKit did not return a Sandbox Session ID.")
        deadline = time.monotonic() + _SESSION_READY_TIMEOUT_SECONDS
        while not endpoint:
            session = await asyncio.to_thread(
                client.get_session,
                tools_types.GetSessionRequest(ToolId=tool_id, SessionId=session_id),
            )
            status = str(getattr(session, "status", "") or "").strip().lower()
            endpoint = str(getattr(session, "endpoint", "") or "").strip()
            if endpoint and status in {"", _READY_STATUS}:
                break
            if status in _FAILED_TOOL_STATUSES:
                raise RuntimeError("AgentKit Sandbox Session failed to become ready.")
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for the Sandbox Session.")
            await self._sleep(self._poll_interval_seconds)
        _validated_endpoint(endpoint)
        return SandboxExecutionTarget(
            endpoint=endpoint,
            session_id=session_id,
            tool_id=tool_id,
        )


def register_sandbox_shell_tool(
    registry: StudioToolRegistry,
    *,
    mounts: SessionEnvironmentMountRegistry,
    target_resolver: SandboxTargetResolver,
) -> None:
    """Mount environment discovery and execution on the Studio tool channel."""

    async def list_envs(
        arguments: dict[str, Any],
        context: StudioToolExecutionContext,
    ) -> dict[str, Any]:
        del arguments
        try:
            mounted = mounts.get_all(context)
        except (TypeError, ValueError) as error:
            raise StudioToolExecutionError(str(error)) from error
        return {
            "environments": [
                {
                    "environment_id": mount.environment_id,
                    "environment_version_id": mount.environment_version_id,
                    "name": mount.name,
                    "description": mount.description,
                    "capabilities": _manifest_capabilities(mount.manifest),
                }
                for mount in mounted
            ]
        }

    async def get_env_manifest(
        arguments: dict[str, Any],
        context: StudioToolExecutionContext,
    ) -> dict[str, Any]:
        try:
            mount = mounts.get(context, str(arguments["environment_id"]))
        except (KeyError, TypeError, ValueError) as error:
            raise StudioToolExecutionError(str(error)) from error
        return dict(mount.manifest)

    async def execute(
        arguments: dict[str, Any],
        context: StudioToolExecutionContext,
    ) -> dict[str, Any]:
        try:
            mount = mounts.get(context, str(arguments["environment_id"]))
        except (KeyError, TypeError, ValueError) as error:
            raise StudioToolExecutionError(str(error)) from error
        try:
            target = await target_resolver.resolve(mount, context)
            command_arguments = {
                key: value
                for key, value in arguments.items()
                if key != "environment_id"
            }
            return await execute_in_sandbox(target, command_arguments)
        except StudioToolExecutionError:
            raise
        except SandboxResolutionError as error:
            raise StudioToolExecutionError(str(error)) from error
        except Exception as error:
            raise StudioToolExecutionError(
                "The selected Sandbox environment is unavailable."
            ) from error

    environment_id_schema = {
        "type": "string",
        "minLength": 32,
        "maxLength": 32,
        "description": "ID of an environment returned by list_envs.",
    }
    registry.register(
        StudioTool(
            name="list_envs",
            display_name="查看会话环境",
            description=(
                "List the environments mounted to this conversation and summarize "
                "their capabilities. Use this as the first tool for every substantive "
                "request unless the user explicitly asks to create a new agent. Make "
                "a semantic match between the task and each environment's name, "
                "description, and capabilities; the user does not need to name an "
                "environment. If the user names a mounted environment, select it "
                "exactly; otherwise choose one primary environment by the requested "
                "deliverable and action. Respect negative scope statements as "
                "disqualifying. Requirement/design/ADR work matches authoring/design, "
                "review/verification matches review, and implementation/fix/test work "
                "matches engineering. A matching mounted "
                "environment has priority over creating or delegating to a new agent."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            executor=list_envs,
            executor_revision="environment-catalog-v1",
            timeout_ms=5_000,
            idempotent=True,
            risk_level="low",
            requires_context=True,
        )
    )
    registry.register(
        StudioTool(
            name="get_env_manifest",
            display_name="查看环境 Manifest",
            description=(
                "Return the immutable manifest for one environment mounted to this "
                "conversation."
            ),
            input_schema={
                "type": "object",
                "properties": {"environment_id": environment_id_schema},
                "required": ["environment_id"],
                "additionalProperties": False,
            },
            executor=get_env_manifest,
            executor_revision="environment-catalog-v1",
            timeout_ms=5_000,
            idempotent=True,
            risk_level="low",
            requires_context=True,
        )
    )
    registry.register(
        StudioTool(
            name="execute_in_sandbox",
            display_name="在环境中执行命令",
            description=(
                "Execute a non-interactive shell command, including installed CLI "
                "tools, inside the environment mounted to this conversation. Use a "
                "matching mounted environment to complete the task instead of "
                "creating a new agent unless the user explicitly requests agent "
                "creation or delegation. When the user explicitly names a mounted "
                "environment, execute in that environment."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "environment_id": environment_id_schema,
                    "command": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 32_768,
                        "description": "The shell command to execute.",
                    },
                    "command_id": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 1_024,
                        "description": (
                            "ID returned by a still-running command. Omit command "
                            "and pass this ID to wait for its result."
                        ),
                    },
                    "cwd": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 1_024,
                        "pattern": "^/",
                        "description": "Absolute working directory in the Sandbox.",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 90,
                        "default": 60,
                    },
                    "hard_timeout_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 1_800,
                        "default": 300,
                        "description": "Maximum command runtime before termination.",
                    },
                },
                "oneOf": [
                    {
                        "required": ["environment_id", "command"],
                        "not": {"required": ["command_id"]},
                    },
                    {
                        "required": ["environment_id", "command_id"],
                        "not": {"required": ["command"]},
                    },
                ],
                "additionalProperties": False,
            },
            executor=execute,
            executor_revision="aio-shell-v2",
            timeout_ms=120_000,
            idempotent=False,
            risk_level="high",
            requires_context=True,
        )
    )


async def execute_in_sandbox(
    target: SandboxExecutionTarget,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Call AIO's one-shot shell API without exposing its endpoint or auth."""

    endpoint = _validated_endpoint(target.endpoint)
    timeout_seconds = int(arguments.get("timeout_seconds") or 60)
    command_id = str(arguments.get("command_id") or "").strip()
    command = str(arguments.get("command") or "")
    if command_id:
        url = sandbox_service_url(endpoint, "/v1/shell/wait")
        body: dict[str, Any] = {
            "id": command_id,
            "seconds": timeout_seconds,
            "max_wait_seconds": timeout_seconds,
        }
    else:
        hard_timeout_seconds = int(arguments.get("hard_timeout_seconds") or 300)
        if hard_timeout_seconds < timeout_seconds:
            raise StudioToolExecutionError(
                "hard_timeout_seconds must be greater than or equal to timeout_seconds."
            )
        cwd = str(arguments.get("cwd") or "/home/gem")
        url = sandbox_service_url(endpoint, "/v1/shell/exec")
        body = {
            "id": "",
            "exec_dir": cwd,
            "command": command,
            "timeout": timeout_seconds,
            "hard_timeout": hard_timeout_seconds,
            "strict": True,
        }
    headers = _safe_headers(target.headers)
    headers["content-type"] = "application/json"
    timeout = httpx.Timeout(timeout_seconds + 10, connect=10)
    try:
        async with (
            httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client,
            client.stream(
                "POST",
                url,
                headers=headers,
                json=body,
            ) as response,
        ):
            content = await _bounded_response(response)
            status_code = response.status_code
    except httpx.TimeoutException as error:
        raise StudioToolExecutionError(
            f"Sandbox command timed out after {timeout_seconds} seconds."
        ) from error
    except httpx.HTTPError as error:
        raise StudioToolExecutionError(
            "Unable to connect to the selected Sandbox environment."
        ) from error
    if not 200 <= status_code < 300:
        raise StudioToolExecutionError(
            f"Sandbox command service returned HTTP {status_code}."
        )
    return _normalize_result(content)


async def _bounded_response(response: httpx.Response) -> bytes:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
            raise StudioToolExecutionError("Sandbox command response is too large.")
        body.extend(chunk)
    return bytes(body)


def _normalize_result(content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {"output": content.decode("utf-8", errors="replace")}
    payload_mapping = payload if isinstance(payload, dict) else None
    nested_data = payload_mapping.get("data") if payload_mapping is not None else None
    if isinstance(nested_data, dict):
        data: dict[str, Any] = nested_data
    elif payload_mapping is not None:
        data = payload_mapping
    else:
        data = {"output": str(payload)}

    output = data.get("output", "")
    if output is None:
        output = ""
    if not isinstance(output, str):
        output = json.dumps(output, ensure_ascii=False)
    encoded = output.encode("utf-8")
    truncated = len(encoded) > _MAX_OUTPUT_BYTES
    if truncated:
        output = encoded[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    exit_code = data.get("exit_code")
    if not isinstance(exit_code, int):
        exit_code = None
    status = data.get("status")
    if not isinstance(status, str):
        status = "completed" if exit_code in {None, 0} else "failed"
    status = status.strip().lower()
    command_id = data.get("session_id")
    result = {
        "ok": status == "completed" and exit_code == 0,
        "running": status == "running",
        "status": status,
        "exit_code": exit_code,
        "output": output,
        "output_truncated": truncated,
    }
    if isinstance(command_id, str) and command_id.strip():
        result["command_id"] = command_id.strip()
    return result


def _safe_headers(values: Mapping[str, str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in (values or {}).items():
        normalized = key.strip().lower()
        if normalized not in _ALLOWED_TARGET_HEADERS:
            continue
        if "\r" in value or "\n" in value:
            raise StudioToolExecutionError("Sandbox authorization header is invalid.")
        result[normalized] = value
    return result


def _validated_endpoint(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise StudioToolExecutionError("Sandbox returned an invalid endpoint.")
    return value.strip()


def _user_session_id(
    context: StudioToolExecutionContext,
    mount: SessionEnvironmentMount,
) -> str:
    value = "\x00".join((*_context_key(context), mount.environment_id, mount.image))
    return "studio-env-" + hashlib.sha256(value.encode()).hexdigest()[:32]


def _context_key(
    context: StudioToolExecutionContext,
) -> tuple[str, str, str, str]:
    return (
        context.runtime_id,
        context.app_name,
        context.user_id,
        context.session_id,
    )


def _manifest_capabilities(manifest: Mapping[str, Any]) -> list[str]:
    spec = manifest.get("spec")
    if not isinstance(spec, Mapping):
        return []
    capabilities = spec.get("capabilities")
    if not isinstance(capabilities, list):
        return []
    return [item for item in capabilities if isinstance(item, str)]


def _find_session(
    client: Any,
    tools_types: Any,
    tool_id: str,
    user_session_id: str,
) -> Any | None:
    response = client.list_sessions(
        tools_types.ListSessionsRequest(
            ToolId=tool_id,
            MaxResults=10,
            Filters=[
                tools_types.FiltersItemForListSessions(
                    Name="UserSessionId", Values=[user_session_id]
                )
            ],
        )
    )
    for session in getattr(response, "session_infos", None) or []:
        if str(getattr(session, "user_session_id", "") or "") != user_session_id:
            continue
        status = str(getattr(session, "status", "") or "").strip().lower()
        if status not in _FAILED_TOOL_STATUSES:
            return session
    return None


async def _require_ready_tool(client: Any, tool_id: str, image: str) -> None:
    from agentkit.sdk.tools import types as tools_types

    try:
        tool = await asyncio.to_thread(
            client.get_tool,
            tools_types.GetToolRequest(ToolId=tool_id),
        )
    except Exception as error:
        raise SandboxResolutionError(
            "The persisted Sandbox Tool is unavailable. Rebuild the environment."
        ) from error
    status = str(getattr(tool, "status", "") or "").strip().lower()
    if status != _READY_STATUS:
        raise SandboxResolutionError(
            f"The persisted Sandbox Tool is not Ready (status: {status or 'unknown'})."
        )
    persisted_image = str(getattr(tool, "image_url", "") or "").strip()
    if persisted_image and persisted_image != image:
        raise SandboxResolutionError(
            "The persisted Sandbox Tool image does not match the environment version."
        )


__all__ = [
    "AgentkitEnvironmentSandboxResolver",
    "SandboxExecutionTarget",
    "SandboxResolutionError",
    "SandboxTargetResolver",
    "execute_in_sandbox",
    "register_sandbox_shell_tool",
]
