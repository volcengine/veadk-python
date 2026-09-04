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

"""Delegate a Studio tool call to Codex in a mounted CodeEnv Sandbox."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

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
    StudioToolRuntimeError,
)
from frontend.server.studio_tools.sandbox_shell import (
    SandboxExecutionTarget,
    SandboxResolutionError,
    SandboxTargetResolver,
)
from veadk.cli.codex_app_server import (
    CodexAppServerError,
    CodexAppServerEvent,
    CodexAppServerSession,
    CodexAppServerTransportError,
    CodexAppServerTurnTimeoutError,
    CodexPermissionSettings,
    sandbox_service_url,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_CODEX_PERMISSIONS = CodexPermissionSettings(
    approval_policy="never",
    approvals_reviewer="auto_review",
    sandbox_mode="danger-full-access",
    network_access=True,
)
_CONNECT_RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)
_READINESS_TIMEOUT_SECONDS = 5.0
_CODEX_TOOL_TIMEOUT_MS = 30 * 60 * 1_000
_MAX_RESULT_CHARACTERS = 32_768
_MAX_RESULT_BYTES = 96 * 1024
_MAX_PROGRESS_BYTES = 64 * 1024
_MAX_PROGRESS_STRING_CHARACTERS = 16_000
_MAX_PROGRESS_COLLECTION_ITEMS = 100
_MAX_ACTIVITY_BYTES = 16 * 1024
_MAX_ACTIVITY_EVENTS = 100
_MAX_ACTIVITY_STRING_CHARACTERS = 4_000
_MAX_ACTIVITY_COLLECTION_ITEMS = 30
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?key|secret|token|authorization|password)"
)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)((?:api[_-]?key|access[_-]?key|secret|token|authorization|password)"
    r"\s*[:=]\s*)(?:[\"'][^\"']*[\"']|[^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)(\bbearer\s+)\S+")
_URL_QUERY_RE = re.compile(r"https?://[^\s?]+\?[^\s]+")


class CodexSandboxConnection(Protocol):
    """The narrow app-server surface required by the Studio adapter."""

    thread_id: str

    async def connect(self) -> None: ...

    async def stream_turn(
        self,
        prompt: str,
        skill_ids: tuple[str, ...] = (),
        *,
        permissions: CodexPermissionSettings | None = None,
        timeout_seconds: float | None = None,
        output_schema: dict[str, object] | None = None,
    ) -> AsyncIterator[CodexAppServerEvent]:
        if False:
            yield CodexAppServerEvent()

    async def close(self) -> None: ...


@dataclass
class _CodexConnectionEntry:
    connection: CodexSandboxConnection
    lock: asyncio.Lock


class CodexSandboxDelegate:
    """Reuse one Codex app-server thread for each mounted Studio session."""

    def __init__(
        self,
        target_resolver: SandboxTargetResolver,
        *,
        connection_factory: Callable[[str], CodexSandboxConnection] = (
            CodexAppServerSession
        ),
        readiness_probe: Callable[[SandboxExecutionTarget], Awaitable[bool]]
        | None = None,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self._target_resolver = target_resolver
        self._connection_factory = connection_factory
        self._readiness_probe = readiness_probe or (
            _codex_app_server_ready
            if connection_factory is CodexAppServerSession
            else _always_ready
        )
        self._sleep = sleep
        self._connections: dict[
            tuple[str, str, str, str, str, str], _CodexConnectionEntry
        ] = {}
        self._connections_lock = asyncio.Lock()

    async def execute(
        self,
        mount: SessionEnvironmentMount,
        task: str,
        context: StudioToolExecutionContext,
    ) -> dict[str, Any]:
        """Run one delegated task and forward every app-server event."""

        _require_codex_mount(mount)
        target = await self._target_resolver.resolve(mount, context)
        prompt = _delegated_prompt(mount, task)
        text_parts: list[str] = []
        final_text = ""
        activity_events: list[dict[str, Any]] = []
        text_event_id = f"assistant:{context.tool_request_id or context.run_id}"

        existing = await self._connection(target, mount, context)
        if existing.lock.locked():
            failure = await _report_failure(
                context,
                mount,
                "Codex Sandbox 正在执行上一项任务",
            )
            _append_activity_event(activity_events, failure)
            raise StudioToolRuntimeError(
                "Codex Sandbox 正忙，请等待当前任务完成；不要重复提交同一任务。",
                content=_activity_result(
                    mount,
                    context,
                    activity_events,
                    target=target,
                    thread_id=existing.connection.thread_id,
                    ok=False,
                ),
            )

        try:
            entry = await self._ready_connection(target, mount, context)
        except CodexAppServerTransportError as error:
            failure = await _report_failure(context, mount, "Codex Sandbox 连接失败")
            _append_activity_event(activity_events, failure)
            raise StudioToolRuntimeError(
                "Codex Sandbox 服务尚未就绪，多次连接仍失败，请稍后重试。",
                content=_activity_result(
                    mount,
                    context,
                    activity_events,
                    ok=False,
                ),
            ) from error

        async with entry.lock:
            _append_activity_event(
                activity_events,
                await _report(
                    context,
                    mount,
                    {
                        "id": f"turn:{context.tool_request_id or context.run_id}",
                        "kind": "status",
                        "status": "running",
                        "text": "Codex Sandbox 已接收任务",
                        "agentSessionId": context.session_id,
                        "sandboxSessionId": target.session_id,
                        "threadId": entry.connection.thread_id,
                    },
                ),
            )
            try:
                async for event in entry.connection.stream_turn(
                    prompt,
                    permissions=_CODEX_PERMISSIONS,
                ):
                    if event.kind == "text":
                        if event.text:
                            _append_text_part(text_parts, event.text)
                        # The activity card describes execution. The authoritative
                        # assistant answer is emitted once as ordinary message text
                        # after the function response, not duplicated in the card.
                        continue
                    if event.kind in {"assistant_final", "final"}:
                        if event.text:
                            final_text = event.text
                        continue
                    _append_activity_event(
                        activity_events,
                        await _report(
                            context,
                            mount,
                            _progress_event(event, fallback_id=text_event_id),
                        ),
                    )
            except CodexAppServerTurnTimeoutError as error:
                failure = await _report_failure(
                    context, mount, "Codex Sandbox 执行超时"
                )
                _append_activity_event(activity_events, failure)
                raise StudioToolRuntimeError(
                    "Codex Sandbox 长时间没有返回新进度，请重试。",
                    content=_activity_result(
                        mount,
                        context,
                        activity_events,
                        target=target,
                        thread_id=entry.connection.thread_id,
                        ok=False,
                    ),
                ) from error
            except CodexAppServerTransportError as error:
                failure = await _report_failure(
                    context, mount, "Codex Sandbox 连接中断"
                )
                _append_activity_event(activity_events, failure)
                await self._discard(target, mount, context, entry)
                raise StudioToolRuntimeError(
                    "Codex Sandbox 连接中断，请重试本次任务。",
                    content=_activity_result(
                        mount,
                        context,
                        activity_events,
                        target=target,
                        thread_id=entry.connection.thread_id,
                        ok=False,
                    ),
                ) from error
            except CodexAppServerError as error:
                failure = await _report_failure(
                    context, mount, "Codex Sandbox 执行失败"
                )
                _append_activity_event(activity_events, failure)
                raise StudioToolRuntimeError(
                    "Codex Sandbox 未能完成任务，请检查任务描述后重试。",
                    content=_activity_result(
                        mount,
                        context,
                        activity_events,
                        target=target,
                        thread_id=entry.connection.thread_id,
                        ok=False,
                    ),
                ) from error

            _append_activity_event(
                activity_events,
                await _report(
                    context,
                    mount,
                    {
                        "id": f"turn:{context.tool_request_id or context.run_id}",
                        "kind": "status",
                        "status": "completed",
                        "text": "Codex Sandbox 已完成任务",
                        "agentSessionId": context.session_id,
                        "sandboxSessionId": target.session_id,
                        "threadId": entry.connection.thread_id,
                    },
                ),
            )
        message = _redact_text((final_text or "".join(text_parts)).strip())
        return {
            "ok": True,
            "environment_id": mount.environment_id,
            "agent_session_id": context.session_id,
            "sandbox_session_id": target.session_id,
            "thread_id": entry.connection.thread_id,
            "codex_activity": _activity_snapshot(
                mount,
                context,
                activity_events,
                target=target,
                thread_id=entry.connection.thread_id,
            ),
            "message": _bounded_result_message(message),
        }

    async def _ready_connection(
        self,
        target: SandboxExecutionTarget,
        mount: SessionEnvironmentMount,
        context: StudioToolExecutionContext,
    ) -> _CodexConnectionEntry:
        attempts = len(_CONNECT_RETRY_DELAYS_SECONDS) + 1
        for attempt in range(1, attempts + 1):
            entry: _CodexConnectionEntry | None = None
            try:
                if not await self._readiness_probe(target):
                    raise CodexAppServerTransportError(
                        "Codex app-server readiness check did not pass."
                    )
                entry = await self._connection(target, mount, context)
                # Several outer-agent runs can target the same mounted Sandbox.
                # Serialize the initial handshake with turns so one failed opener
                # cannot close the transport while another caller is connecting.
                async with entry.lock:
                    await entry.connection.connect()
                return entry
            except CodexAppServerTransportError as error:
                logger.warning(
                    "Codex Sandbox app-server connection failed "
                    "environment_id_prefix=%s attempt=%d/%d error_type=%s",
                    mount.environment_id[:8],
                    attempt,
                    attempts,
                    type(error).__name__,
                )
                if entry is not None:
                    await self._discard(target, mount, context, entry)
                if attempt >= attempts:
                    raise
                await _report(
                    context,
                    mount,
                    {
                        "id": f"turn:{context.tool_request_id or context.run_id}",
                        "kind": "status",
                        "status": "running",
                        "text": (
                            "Codex Sandbox 正在启动，"
                            f"准备第 {attempt + 1}/{attempts} 次连接"
                        ),
                    },
                )
                await self._sleep(_CONNECT_RETRY_DELAYS_SECONDS[attempt - 1])
        raise AssertionError("unreachable")

    async def _connection(
        self,
        target: SandboxExecutionTarget,
        mount: SessionEnvironmentMount,
        context: StudioToolExecutionContext,
    ) -> _CodexConnectionEntry:
        key = _connection_key(target, mount, context)
        async with self._connections_lock:
            entry = self._connections.get(key)
            if entry is None:
                entry = _CodexConnectionEntry(
                    connection=self._connection_factory(target.endpoint),
                    lock=asyncio.Lock(),
                )
                self._connections[key] = entry
            return entry

    async def _discard(
        self,
        target: SandboxExecutionTarget,
        mount: SessionEnvironmentMount,
        context: StudioToolExecutionContext,
        entry: _CodexConnectionEntry,
    ) -> None:
        key = _connection_key(target, mount, context)
        async with self._connections_lock:
            if self._connections.get(key) is entry:
                self._connections.pop(key, None)
        try:
            await entry.connection.close()
        except Exception as error:  # noqa: BLE001 - preserve the primary failure
            logger.warning(
                "Codex Sandbox connection cleanup failed "
                "environment_id_prefix=%s error_type=%s",
                mount.environment_id[:8],
                type(error).__name__,
            )

    async def close(self) -> None:
        """Close every cached app-server transport during Studio shutdown."""

        async with self._connections_lock:
            entries = tuple(self._connections.values())
            self._connections.clear()
        if entries:
            await asyncio.gather(
                *(entry.connection.close() for entry in entries),
                return_exceptions=True,
            )


def register_codex_sandbox_tool(
    registry: StudioToolRegistry,
    *,
    mounts: SessionEnvironmentMountRegistry,
    delegate: CodexSandboxDelegate,
) -> None:
    """Register the context-bound Codex delegation tool."""

    async def execute(
        arguments: dict[str, Any],
        context: StudioToolExecutionContext,
    ) -> dict[str, Any]:
        try:
            mount = mounts.get(context, str(arguments["environment_id"]))
            return await delegate.execute(mount, str(arguments["task"]), context)
        except StudioToolExecutionError:
            raise
        except (KeyError, TypeError, ValueError, SandboxResolutionError) as error:
            raise StudioToolExecutionError(str(error)) from error
        except Exception as error:
            raise StudioToolRuntimeError(
                "Codex Sandbox 当前不可用，请稍后重试。"
            ) from error

    registry.register(
        StudioTool(
            name="delegate_to_codex_sandbox",
            display_name="交给 Codex Sandbox",
            description=(
                "Delegate a complete coding, review, authoring, or engineering task "
                "to Codex inside a mounted Codex Sandbox environment. Use this tool "
                "instead of execute_in_sandbox when the selected environment has "
                "baseEnvironment=codex-sandbox. Pass a self-contained task with the "
                "desired outcome, constraints, relevant context, and verification "
                "requirements; Codex will inspect the environment and invoke its "
                "installed CLIs end to end. This is execution within an already "
                "mounted environment, not creation of a new agent."
                " Preserve the user's requested scope instead of adding new length "
                "or format requirements. The inner Codex final response must contain "
                "the user-visible deliverable; a Sandbox-local file path alone is "
                "not a deliverable unless the user explicitly requested a file."
                " Call this tool at most once per outer user turn. If it reports "
                "busy or timeout, surface that state and do not retry automatically."
                " Treat a successful delegation as the final tool call of the outer "
                "turn because its message is returned directly to the user."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "environment_id": {
                        "type": "string",
                        "minLength": 32,
                        "maxLength": 32,
                        "description": (
                            "ID of the Codex environment returned by list_envs."
                        ),
                    },
                    "task": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 32_768,
                        "description": (
                            "A self-contained task for the inner Codex agent, "
                            "including "
                            "the expected deliverable and how to verify it."
                        ),
                    },
                },
                "required": ["environment_id", "task"],
                "additionalProperties": False,
            },
            executor=execute,
            executor_revision="codex-app-server-v1",
            # Codex performs complete repository workflows. Keep this absolute
            # channel deadline separate from ordinary tools; the app-server turn
            # still enforces its shorter inactivity timeout and interrupts on it.
            timeout_ms=_CODEX_TOOL_TIMEOUT_MS,
            idempotent=False,
            risk_level="high",
            requires_context=True,
        )
    )


async def _always_ready(target: SandboxExecutionTarget) -> bool:
    del target
    return True


async def _codex_app_server_ready(target: SandboxExecutionTarget) -> bool:
    """Probe the app-server without exposing the private Sandbox endpoint."""

    url = sandbox_service_url(target.endpoint, "/v1/codex/app-server/readyz")
    try:
        async with httpx.AsyncClient(
            timeout=_READINESS_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.get(url, headers=dict(target.headers or {}))
    except httpx.HTTPError:
        return False
    return 200 <= response.status_code < 300


def _require_codex_mount(mount: SessionEnvironmentMount) -> None:
    spec = mount.manifest.get("spec")
    base_environment = (
        spec.get("baseEnvironment") if isinstance(spec, Mapping) else None
    )
    if base_environment != "codex-sandbox":
        raise ValueError("所选环境不是 Codex Sandbox，无法委派 Codex 任务。")


def _delegated_prompt(mount: SessionEnvironmentMount, task: str) -> str:
    capabilities = []
    spec = mount.manifest.get("spec")
    if isinstance(spec, Mapping) and isinstance(spec.get("capabilities"), list):
        capabilities = [
            value.strip()
            for value in spec["capabilities"]
            if isinstance(value, str) and value.strip()
        ]
    context_lines = [
        "You are executing inside a prebuilt AgentKit environment.",
        f"Environment name: {mount.name or mount.environment_id}",
    ]
    if mount.description:
        context_lines.append(f"Environment description: {mount.description}")
    if capabilities:
        context_lines.append("Available capabilities: " + ", ".join(capabilities))
    context_lines.extend(
        [
            (
                "Inspect the workspace and installed CLI help when needed, then "
                "complete the task end to end. Run relevant verification before "
                "reporting the result."
            ),
            (
                "Batch related non-destructive shell checks into as few tool calls "
                "as practical, avoid repeating successful checks, and return a "
                "concise final result as soon as verification is complete."
            ),
            (
                "Put the complete user-visible deliverable in your final response. "
                "Do not only save it to a Sandbox-local file or return a file path "
                "unless the task explicitly requests a file."
            ),
            (
                "Unless the user explicitly requests a file, do not create a file "
                "for prose-only deliverables. Return exactly one final answer, do "
                "not emit the full deliverable as an intermediate update, and do "
                "not repeat it after the final answer. When no length is specified, "
                "keep the final answer complete but concise enough to return "
                "directly to the user."
            ),
            "Do not ask the outer agent to run commands that you can run here.",
            "",
            "Task from the outer agent:",
            task.strip(),
        ]
    )
    return "\n".join(context_lines)


def _progress_event(
    event: CodexAppServerEvent,
    *,
    fallback_id: str,
) -> dict[str, Any]:
    event_id = event.item_id or event.turn_id or fallback_id
    payload: dict[str, Any] = {
        "id": event_id,
        "kind": event.kind,
        "status": event.status,
    }
    if event.text:
        if event.kind == "text" and not event.item_id:
            payload["delta"] = event.text
        else:
            payload["text"] = event.text
    if event.name:
        payload["name"] = event.name
    if event.arguments is not None:
        payload["arguments"] = event.arguments
    if event.response is not None:
        payload["response"] = event.response
    if event.approval is not None:
        payload["approval"] = event.approval.public_dict()
    if event.approval_resolved_id:
        payload["approvalResolvedId"] = event.approval_resolved_id
    if event.usage is not None:
        payload["usage"] = event.usage.public_dict()
    if event.thread_total is not None:
        payload["threadTotal"] = event.thread_total.public_dict()
    if event.model_context_window is not None:
        payload["modelContextWindow"] = event.model_context_window
    return payload


def _append_text_part(parts: list[str], value: str) -> bool:
    """Append streamed text while dropping repeated completed-message payloads."""

    if parts and parts[-1] == value:
        return False
    parts.append(value)
    return True


def _bounded_result_message(value: str) -> str:
    """Keep complete ordinary results and preserve the start of oversized ones."""

    if not value:
        return "Codex Sandbox 已完成任务。"
    encoded = value.encode("utf-8")
    if len(value) <= _MAX_RESULT_CHARACTERS and len(encoded) <= _MAX_RESULT_BYTES:
        return value
    marker = "\n\n…内容过长，已截断"
    marker_bytes = marker.encode("utf-8")
    candidate = value[:_MAX_RESULT_CHARACTERS].encode("utf-8")
    available = _MAX_RESULT_BYTES - len(marker_bytes)
    return candidate[:available].decode("utf-8", errors="ignore") + marker


async def _report(
    context: StudioToolExecutionContext,
    mount: SessionEnvironmentMount,
    event: dict[str, Any],
) -> dict[str, Any]:
    safe_event = _bounded_progress_event(event)
    if context.report_progress is not None:
        await context.report_progress(
            {
                "kind": "codex",
                "title": _redact_text(mount.name or "Codex Sandbox")[:200],
                "event": safe_event,
            }
        )
    return safe_event


async def _report_failure(
    context: StudioToolExecutionContext,
    mount: SessionEnvironmentMount,
    message: str,
) -> dict[str, Any]:
    return await _report(
        context,
        mount,
        {
            "id": f"turn:{context.tool_request_id or context.run_id}",
            "kind": "status",
            "status": "failed",
            "text": message,
        },
    )


def _append_activity_event(
    events: list[dict[str, Any]],
    event: dict[str, Any],
) -> None:
    compact = _safe_activity_value(event)
    if not isinstance(compact, dict):
        return
    events.append(compact)
    while (
        len(events) > _MAX_ACTIVITY_EVENTS or _json_size(events) > _MAX_ACTIVITY_BYTES
    ):
        events.pop(0)


def _safe_activity_value(value: Any, *, depth: int = 0) -> Any:
    """Keep persisted tool responses compact; live progress is sent separately."""

    if depth >= 6:
        return "[truncated]"
    if isinstance(value, str):
        if len(value) <= _MAX_ACTIVITY_STRING_CHARACTERS:
            return value
        return value[:_MAX_ACTIVITY_STRING_CHARACTERS] + "…内容已截断"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (raw_key, item) in enumerate(value.items()):
            if index >= _MAX_ACTIVITY_COLLECTION_ITEMS:
                result["truncated"] = True
                break
            key = str(raw_key)[:200]
            result[key] = _safe_activity_value(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        items = [
            _safe_activity_value(item, depth=depth + 1)
            for item in value[:_MAX_ACTIVITY_COLLECTION_ITEMS]
        ]
        if len(value) > _MAX_ACTIVITY_COLLECTION_ITEMS:
            items.append("[truncated]")
        return items
    return str(value)[:_MAX_ACTIVITY_STRING_CHARACTERS]


def _json_size(value: Any) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def _activity_snapshot(
    mount: SessionEnvironmentMount,
    context: StudioToolExecutionContext,
    events: list[dict[str, Any]],
    *,
    target: SandboxExecutionTarget | None = None,
    thread_id: str = "",
) -> dict[str, Any]:
    return {
        "title": _redact_text(mount.name or "Codex Sandbox")[:200],
        "agent_session_id": context.session_id,
        "sandbox_session_id": target.session_id if target is not None else "",
        "thread_id": thread_id,
        "events": list(events),
    }


def _activity_result(
    mount: SessionEnvironmentMount,
    context: StudioToolExecutionContext,
    events: list[dict[str, Any]],
    *,
    target: SandboxExecutionTarget | None = None,
    thread_id: str = "",
    ok: bool,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "environment_id": mount.environment_id,
        "codex_activity": _activity_snapshot(
            mount,
            context,
            events,
            target=target,
            thread_id=thread_id,
        ),
    }


def _connection_key(
    target: SandboxExecutionTarget,
    mount: SessionEnvironmentMount,
    context: StudioToolExecutionContext,
) -> tuple[str, str, str, str, str, str]:
    return (
        context.runtime_id,
        context.app_name,
        context.user_id,
        context.session_id,
        mount.environment_id,
        target.session_id,
    )


def _bounded_progress_event(event: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = _safe_progress_value(event)
    if not isinstance(sanitized, dict):
        return {
            "id": "codex-progress",
            "kind": "status",
            "status": "failed",
            "text": "Codex Sandbox 返回了无效进度。",
        }
    encoded = json.dumps(
        sanitized,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) <= _MAX_PROGRESS_BYTES:
        return sanitized
    preview = _redact_text(
        encoded[: _MAX_PROGRESS_BYTES // 2].decode("utf-8", errors="replace")
    )
    return {
        "id": str(sanitized.get("id") or "codex-progress")[:200],
        "kind": str(sanitized.get("kind") or "status")[:100],
        "status": str(sanitized.get("status") or "running")[:100],
        "name": str(sanitized.get("name") or "Codex 输出")[:200],
        "response": {
            "truncated": True,
            "preview": preview,
        },
    }


def _safe_progress_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 8:
        return "[truncated]"
    if isinstance(value, str):
        return _redact_text(value)[:_MAX_PROGRESS_STRING_CHARACTERS]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (raw_key, item) in enumerate(value.items()):
            if index >= _MAX_PROGRESS_COLLECTION_ITEMS:
                result["truncated"] = True
                break
            key = str(raw_key)[:200]
            result[key] = (
                "***"
                if _SENSITIVE_KEY_RE.search(key)
                else _safe_progress_value(item, depth=depth + 1)
            )
        return result
    if isinstance(value, (list, tuple)):
        items = [
            _safe_progress_value(item, depth=depth + 1)
            for item in value[:_MAX_PROGRESS_COLLECTION_ITEMS]
        ]
        if len(value) > _MAX_PROGRESS_COLLECTION_ITEMS:
            items.append("[truncated]")
        return items
    return _redact_text(str(value))[:_MAX_PROGRESS_STRING_CHARACTERS]


def _redact_text(value: str) -> str:
    result = value
    for key, secret in os.environ.items():
        if secret and len(secret) >= 8 and _SENSITIVE_KEY_RE.search(key):
            result = result.replace(secret, "***")
    result = _BEARER_RE.sub(r"\1***", result)
    result = _SENSITIVE_VALUE_RE.sub(r"\1***", result)
    return _URL_QUERY_RE.sub("[sandbox endpoint]", result)


__all__ = [
    "CodexSandboxConnection",
    "CodexSandboxDelegate",
    "register_codex_sandbox_tool",
]
