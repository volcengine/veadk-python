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

"""Async Codex app-server client used by Studio's AgentKit Sessions.

The AgentKit Session Endpoint contains a private authorization query.  This
module keeps that Endpoint server-side and speaks Codex's JSON-RPC protocol
over the Session's app-server WebSocket.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import math
import posixpath
import re
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal, cast
from urllib.parse import urlsplit, urlunsplit

ApprovalPolicy = Literal["untrusted", "on-request", "never"]
ApprovalsReviewer = Literal["user", "auto_review"]
SandboxMode = Literal["read-only", "workspace-write", "danger-full-access"]
ApprovalDecision = Literal["accept", "acceptForSession", "decline", "cancel"]

APPROVAL_POLICIES = frozenset({"untrusted", "on-request", "never"})
APPROVALS_REVIEWERS = frozenset({"user", "auto_review"})
SANDBOX_MODES = frozenset({"read-only", "workspace-write", "danger-full-access"})
APPROVAL_DECISIONS = frozenset({"accept", "acceptForSession", "decline", "cancel"})

_REQUEST_TIMEOUT_SECONDS = 60
_TURN_TIMEOUT_SECONDS = 600
_APPROVAL_TIMEOUT_SECONDS = 300
_IMPORTED_HISTORY_INJECT_TIMEOUT_SECONDS = 180
_MAX_DIRECTORY_ENTRIES = 1_000
_IMPORTED_HISTORY_MAX_MESSAGES = 100
_IMPORTED_HISTORY_MAX_MESSAGE_CHARACTERS = 20_000
_IMPORTED_HISTORY_MAX_CHARACTERS = 100_000
_IMPORTED_HISTORY_MAX_IMAGES = 10
_IMPORTED_HISTORY_MAX_IMAGE_BYTES = 4 * 1024 * 1024
_IMPORTED_HISTORY_MAX_IMAGE_TOTAL_BYTES = 8 * 1024 * 1024
_IMPORTED_HISTORY_MAX_BASE64_BYTES = 18 * 1024 * 1024
_IMPORTED_HISTORY_PART_BYTES = 512 * 1024
_IMPORTED_HISTORY_MAX_PARTS = 64
_IMPORTED_HISTORY_READ_TIMEOUT_SECONDS = 15
_APP_SERVER_MAX_MESSAGE_BYTES = _IMPORTED_HISTORY_MAX_BASE64_BYTES + 2 * 1024 * 1024
_IMPORTED_HISTORY_IMAGE_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)
_GATEWAY_WEBSOCKET_MAX_LIFETIME_SECONDS = 30 * 60
_GATEWAY_WEBSOCKET_REFRESH_MARGIN_SECONDS = 30


class CodexAppServerError(RuntimeError):
    """The Sandbox Codex app-server rejected or interrupted an operation."""


def _app_server_error_detail(error: object) -> str:
    """Preserve the complete JSON-RPC error payload for upstream diagnostics."""
    if isinstance(error, (dict, list)):
        return json.dumps(error, ensure_ascii=False, separators=(",", ":"))
    return str(error)


def _is_thread_not_materialized_error(error: CodexAppServerError) -> bool:
    """Return True when the app-server reports a thread has no turns yet.

    A freshly-started thread returns JSON-RPC -32600 with the message
    "thread ... is not materialized yet; includeTurns is unavailable before
    first user message".
    """
    message = str(error)
    try:
        payload = json.loads(message)
    except (json.JSONDecodeError, TypeError):
        return "not materialized yet" in message
    if isinstance(payload, dict):
        if payload.get("code") == -32600 and "not materialized yet" in str(
            payload.get("message", "")
        ):
            return True
    return "not materialized yet" in message


@dataclass(frozen=True)
class CodexPermissionSettings:
    """Permission settings applied to every Codex thread in one cloud Session."""

    approval_policy: ApprovalPolicy = "on-request"
    approvals_reviewer: ApprovalsReviewer = "user"
    sandbox_mode: SandboxMode = "workspace-write"
    network_access: bool = False

    def public_dict(self) -> dict[str, object]:
        """Return the browser-facing camelCase representation."""
        return {
            "approvalPolicy": self.approval_policy,
            "approvalsReviewer": self.approvals_reviewer,
            "sandboxMode": self.sandbox_mode,
            "networkAccess": self.network_access,
        }


@dataclass(frozen=True)
class CodexDirectoryEntry:
    """One browsable remote Sandbox directory."""

    name: str
    path: str


@dataclass(frozen=True)
class CodexDirectoryListing:
    """A bounded directory listing returned by ``fs/readDirectory``."""

    path: str
    parent: str | None
    directories: tuple[CodexDirectoryEntry, ...]

    def public_dict(self) -> dict[str, object]:
        """Return the browser-facing representation."""
        return {
            "path": self.path,
            **({"parent": self.parent} if self.parent else {}),
            "directories": [asdict(entry) for entry in self.directories],
        }


@dataclass(frozen=True)
class CodexTokenUsage:
    """One exact token-usage breakdown reported by Codex app-server."""

    total_tokens: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0

    def public_dict(self) -> dict[str, int]:
        """Return the browser-facing camelCase representation."""
        return {
            "totalTokens": self.total_tokens,
            "inputTokens": self.input_tokens,
            "cachedInputTokens": self.cached_input_tokens,
            "outputTokens": self.output_tokens,
            "reasoningOutputTokens": self.reasoning_output_tokens,
        }


@dataclass(frozen=True)
class CodexModel:
    """One browser-safe model choice returned by ``model/list``."""

    id: str
    display_name: str
    description: str = ""
    is_default: bool = False

    def public_dict(self) -> dict[str, object]:
        """Return the browser-facing representation."""
        return {
            "id": self.id,
            "displayName": self.display_name,
            "description": self.description,
            "isDefault": self.is_default,
        }


@dataclass(frozen=True)
class CodexSkill:
    """One browser-safe Skill reference; its filesystem path stays private."""

    id: str
    name: str
    description: str = ""

    def public_dict(self) -> dict[str, str]:
        """Return the browser-facing representation."""
        return asdict(self)


@dataclass(frozen=True)
class _CodexPrivateSkill:
    id: str
    name: str
    description: str
    path: str


@dataclass(frozen=True)
class CodexImportedImage:
    """One bounded image attachment imported with a visible user message."""

    mime_type: str
    data: str
    name: str = ""
    alt: str = ""

    def data_url(self) -> str:
        """Return a Responses API compatible in-memory image URL."""
        return f"data:{self.mime_type};base64,{self.data}"

    def public_dict(self) -> dict[str, str]:
        """Return the browser-facing representation."""
        return {
            "mimeType": self.mime_type,
            "data": self.data,
            **({"name": self.name} if self.name else {}),
            **({"alt": self.alt} if self.alt else {}),
        }


@dataclass(frozen=True)
class CodexThreadMessage:
    """One sanitized user or assistant message restored from a Codex thread."""

    id: str
    role: Literal["user", "assistant"]
    content: str
    timestamp: int
    skill_names: tuple[str, ...] = ()
    images: tuple[CodexImportedImage, ...] = ()

    def public_dict(self) -> dict[str, object]:
        """Return the browser-facing representation."""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            **({"skillNames": list(self.skill_names)} if self.skill_names else {}),
            **(
                {"images": [image.public_dict() for image in self.images]}
                if self.images
                else {}
            ),
        }


@dataclass(frozen=True)
class CodexImportedMessage:
    """One user-visible message imported into a new Codex thread."""

    role: Literal["user", "assistant"]
    content: str
    images: tuple[CodexImportedImage, ...] = ()


@dataclass(frozen=True)
class CodexThreadSummary:
    """One browser-safe Codex thread list entry."""

    id: str
    name: str = ""
    preview: str = ""
    cwd: str = ""
    model_provider: str = ""
    created_at: int = 0
    updated_at: int = 0
    status: str = "unknown"

    def public_dict(self) -> dict[str, object]:
        """Return the browser-facing representation."""
        return {
            "id": self.id,
            **({"name": self.name} if self.name else {}),
            "preview": self.preview,
            "cwd": self.cwd,
            "modelProvider": self.model_provider,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class CodexThreadSnapshot:
    """The active thread plus its sanitized conversation history."""

    thread: CodexThreadSummary
    messages: tuple[CodexThreadMessage, ...]
    model: str = ""
    cwd: str = ""
    workspace_locked: bool = False

    def public_dict(self, permissions: CodexPermissionSettings) -> dict[str, object]:
        """Return the browser-facing representation."""
        return {
            "thread": self.thread.public_dict(),
            "threadId": self.thread.id,
            "messages": [message.public_dict() for message in self.messages],
            **({"model": self.model} if self.model else {}),
            **({"cwd": self.cwd} if self.cwd else {}),
            "workspaceLocked": self.workspace_locked,
            "permissions": permissions.public_dict(),
        }


@dataclass(frozen=True)
class CodexApproval:
    """One command or file approval requested by Codex."""

    id: str
    kind: Literal["command", "file"]
    method: str
    reason: str = ""
    command: str = ""
    cwd: str = ""
    grant_root: str = ""
    changes: object | None = None
    thread_id: str = ""
    turn_id: str = ""
    item_id: str = ""
    environment_id: str | None = None
    started_at_ms: int | None = None
    command_actions: object | None = None
    network_approval_context: object | None = None

    def public_dict(self) -> dict[str, object]:
        """Return a bounded browser-facing representation."""
        return {
            "id": self.id,
            "kind": self.kind,
            "method": self.method,
            **({"reason": self.reason} if self.reason else {}),
            **({"command": self.command} if self.command else {}),
            **({"cwd": self.cwd} if self.cwd else {}),
            **({"grantRoot": self.grant_root} if self.grant_root else {}),
            **({"changes": self.changes} if self.changes is not None else {}),
            **({"threadId": self.thread_id} if self.thread_id else {}),
            **({"turnId": self.turn_id} if self.turn_id else {}),
            **({"itemId": self.item_id} if self.item_id else {}),
            **(
                {"environmentId": self.environment_id}
                if self.environment_id is not None
                else {}
            ),
            **(
                {"startedAtMs": self.started_at_ms}
                if self.started_at_ms is not None
                else {}
            ),
            **(
                {"commandActions": self.command_actions}
                if self.command_actions is not None
                else {}
            ),
            **(
                {"networkApprovalContext": self.network_approval_context}
                if self.network_approval_context is not None
                else {}
            ),
        }


@dataclass(frozen=True)
class CodexAppServerEvent:
    """One event consumed by Studio's existing Sandbox SSE adapter."""

    kind: str = ""
    item_id: str = ""
    status: str = "done"
    text: str = ""
    name: str = ""
    arguments: object | None = None
    response: object | None = None
    approval: CodexApproval | None = None
    approval_resolved_id: str = ""
    turn_id: str = ""
    usage: CodexTokenUsage | None = None
    thread_total: CodexTokenUsage | None = None
    model_context_window: int | None = None


class CodexAppServerSession:
    """Persistent JSON-RPC connection for one AgentKit cloud Session."""

    def __init__(
        self,
        endpoint: str,
        *,
        websocket_factory: Callable[[str], Awaitable[Any]] | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._websocket_factory = websocket_factory
        self._websocket: Any | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._server_request_tasks: set[asyncio.Task[None]] = set()
        self._connection_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._next_request_id = 1
        self._pending_requests: dict[int, asyncio.Future[dict[str, object]]] = {}
        self._turn_events: asyncio.Queue[CodexAppServerEvent] | None = None
        self._turn_completion: asyncio.Future[dict[str, object]] | None = None
        self._active_turn_id = ""
        self._pending_approvals: dict[str, asyncio.Future[ApprovalDecision]] = {}
        self._closed = False
        self._connected_at = 0.0
        self._connection_failure: CodexAppServerError | None = None
        self._workspace_locked = False
        self._agent_message_delta_ids: set[str] = set()
        self._received_unidentified_agent_delta = False
        self._reasoning_delta_text: dict[str, str] = {}
        self._skills_by_id: dict[str, _CodexPrivateSkill] = {}
        self._skills_cwd = ""
        self._skills_loaded = False
        self._thread_token_total: CodexTokenUsage | None = None
        self._usage_by_turn_id: dict[str, CodexTokenUsage] = {}
        self._model_context_window: int | None = None
        self._imported_history_by_thread: dict[
            str, tuple[CodexImportedMessage, ...]
        ] = {}
        self.thread_id = ""
        self.cwd = ""
        self.model = ""
        self.permissions = CodexPermissionSettings()

    @property
    def active(self) -> bool:
        """Whether a turn is currently running."""
        return self._turn_completion is not None

    @property
    def workspace_locked(self) -> bool:
        """Whether the current thread already accepted its first turn."""
        return self._workspace_locked

    @property
    def healthy(self) -> bool:
        """Whether the current app-server WebSocket can accept requests."""
        return (
            not self._closed
            and self._websocket is not None
            and self._reader_task is not None
            and not self._reader_task.done()
            and self._connection_failure is None
        )

    @property
    def thread_token_total(self) -> CodexTokenUsage | None:
        """The latest exact cumulative usage reported for the active thread."""
        return self._thread_token_total

    @property
    def model_context_window(self) -> int | None:
        """The active model context window when app-server reported it."""
        return self._model_context_window

    async def connect(self) -> None:
        """Connect to app-server, creating or resuming the active thread."""
        if self.healthy:
            return
        if self._closed:
            raise CodexAppServerError("Codex app-server connection is closed.")
        async with self._connection_lock:
            if self.healthy:
                return
            if self._websocket is not None:
                await self._close_transport()
            active_thread_id = self.thread_id
            previous_workspace_locked = self._workspace_locked
            previous_thread_total = self._thread_token_total
            previous_context_window = self._model_context_window
            try:
                await self._open_transport()
                await self._initialize_transport()
                if active_thread_id:
                    method, result = await self._resume_or_start_thread(
                        active_thread_id,
                        previous_workspace_locked=previous_workspace_locked,
                    )
                    self._activate_thread_snapshot(method, result)
                    if method == "thread/resume":
                        self._workspace_locked = previous_workspace_locked
                        self._thread_token_total = previous_thread_total
                        self._model_context_window = previous_context_window
                else:
                    snapshot = await self._request("thread/start", {})
                    self._apply_thread_snapshot(snapshot)
            except Exception:
                await self._close_transport()
                raise

    async def ensure_connected(
        self,
        *,
        minimum_lifetime_seconds: float = _REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """Refresh a closed or aging transport without replacing its thread."""
        if self._closed:
            raise CodexAppServerError("Codex app-server 连接已关闭。")
        if not self.thread_id:
            raise CodexAppServerError("Codex app-server 尚未连接。")
        if not self._transport_needs_refresh(minimum_lifetime_seconds):
            return
        if self.active:
            if not self.healthy:
                raise self._connection_failure or CodexAppServerError(
                    "Codex app-server 连接已断开。"
                )
            return
        async with self._connection_lock:
            if not self._transport_needs_refresh(minimum_lifetime_seconds):
                return
            if self.active:
                if not self.healthy:
                    raise self._connection_failure or CodexAppServerError(
                        "Codex app-server 连接已断开。"
                    )
                return
            if any(not future.done() for future in self._pending_requests.values()):
                if self.healthy:
                    return
                raise self._connection_failure or CodexAppServerError(
                    "Codex app-server 连接已断开。"
                )
            await self._reconnect_transport()

    async def _open_transport(self) -> None:
        """Open one WebSocket transport and start its reader."""
        try:
            url = _app_server_url(self._endpoint)
            if self._websocket_factory is not None:
                self._websocket = await self._websocket_factory(url)
            else:
                import websockets

                self._websocket = await websockets.connect(
                    url,
                    open_timeout=30,
                    close_timeout=5,
                    ping_timeout=60,
                    max_size=_APP_SERVER_MAX_MESSAGE_BYTES,
                )
        except Exception as error:
            raise CodexAppServerError(
                "无法连接 AgentKit Session 中的 Codex 服务。"
            ) from error
        self._connected_at = time.monotonic()
        self._connection_failure = None
        self._reader_task = asyncio.create_task(self._read_messages())

    async def _initialize_transport(self) -> None:
        """Initialize the app-server protocol on the current transport."""
        await self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "agentkit_codex_app_server_client",
                    "title": "AgentKit Studio",
                    "version": "1",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        await self._send({"method": "initialized"})

    def _transport_needs_refresh(self, minimum_lifetime_seconds: float) -> bool:
        if not self.healthy:
            return True
        minimum_lifetime_seconds = max(0.0, minimum_lifetime_seconds)
        maximum_age = (
            _GATEWAY_WEBSOCKET_MAX_LIFETIME_SECONDS
            - _GATEWAY_WEBSOCKET_REFRESH_MARGIN_SECONDS
            - minimum_lifetime_seconds
        )
        return time.monotonic() - self._connected_at >= max(0.0, maximum_age)

    async def _resume_or_start_thread(
        self,
        thread_id: str,
        *,
        previous_workspace_locked: bool,
    ) -> tuple[str, dict[str, object]]:
        try:
            result = await self._request(
                "thread/resume",
                {
                    "threadId": thread_id,
                    **self._thread_options(),
                },
            )
            return "thread/resume", result
        except CodexAppServerError as error:
            if (
                previous_workspace_locked
                or "no rollout found" not in str(error).lower()
            ):
                raise
            result = await self._request("thread/start", self._thread_options())
            return "thread/start", result

    async def _reconnect_transport(self) -> None:
        """Replace the transport and resume the active Codex thread."""
        previous_thread_id = self.thread_id
        previous_workspace_locked = self._workspace_locked
        previous_thread_total = self._thread_token_total
        previous_context_window = self._model_context_window
        await self._close_transport()
        try:
            await self._open_transport()
            await self._initialize_transport()
            method, result = await self._resume_or_start_thread(
                previous_thread_id,
                previous_workspace_locked=previous_workspace_locked,
            )
            self._activate_thread_snapshot(method, result)
            if method == "thread/resume":
                self._workspace_locked = previous_workspace_locked
                self._thread_token_total = previous_thread_total
                self._model_context_window = previous_context_window
        except Exception:
            await self._close_transport()
            raise

    async def request(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        timeout: float = _REQUEST_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        """Send one JSON-RPC request and validate its object result."""
        if not self.thread_id:
            await self.connect()
        else:
            await self.ensure_connected(minimum_lifetime_seconds=timeout)
        return await self._request(method, params, timeout=timeout)

    async def _request(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        timeout: float = _REQUEST_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        """Send one request on an already-checked WebSocket transport."""
        if self._websocket is None or self._closed:
            raise CodexAppServerError("Codex app-server 尚未连接。")
        request_id = self._next_request_id
        self._next_request_id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        try:
            await self._send(
                {
                    "id": request_id,
                    "method": method,
                    **({"params": params} if params is not None else {}),
                }
            )
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as error:
            raise CodexAppServerError(f"Codex 操作 {method} 响应超时。") from error
        finally:
            self._pending_requests.pop(request_id, None)

    async def notify(
        self, method: str, params: dict[str, object] | None = None
    ) -> None:
        """Send a JSON-RPC notification."""
        if not self.thread_id:
            await self.connect()
        else:
            await self.ensure_connected()
        await self._send(
            {
                "method": method,
                **({"params": params} if params is not None else {}),
            }
        )

    async def stream_turn(
        self,
        prompt: str,
        skill_ids: tuple[str, ...] = (),
        *,
        permissions: CodexPermissionSettings | None = None,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[CodexAppServerEvent]:
        """Start one Codex turn and stream its public events."""
        if self.active:
            raise CodexAppServerError("当前 Codex 任务仍在运行。")
        if not self.thread_id:
            await self.connect()
        else:
            await self.ensure_connected(
                minimum_lifetime_seconds=_TURN_TIMEOUT_SECONDS,
            )
        if not self.thread_id:
            raise CodexAppServerError("Codex Thread 尚未初始化。")
        prompt = prompt.strip()
        if not prompt:
            raise CodexAppServerError("消息内容不能为空。")
        skills = await self._resolve_skills(prompt, skill_ids)
        turn_permissions = permissions or self.permissions
        turn_timeout = (
            _TURN_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        )
        if turn_timeout <= 0 or not math.isfinite(turn_timeout):
            raise CodexAppServerError("Codex Turn 超时时间无效。")

        queue: asyncio.Queue[CodexAppServerEvent] = asyncio.Queue()
        completion: asyncio.Future[dict[str, object]] = (
            asyncio.get_running_loop().create_future()
        )
        self._turn_events = queue
        self._turn_completion = completion
        self._active_turn_id = ""
        self._agent_message_delta_ids.clear()
        self._received_unidentified_agent_delta = False
        self._reasoning_delta_text.clear()
        try:
            result = await self.request(
                "turn/start",
                {
                    "threadId": self.thread_id,
                    "input": [
                        {"type": "text", "text": prompt},
                        *(
                            {
                                "type": "skill",
                                "name": skill.name,
                                "path": skill.path,
                            }
                            for skill in skills
                        ),
                    ],
                    **_runtime_permission_params(turn_permissions, self.cwd),
                },
            )
            turn = result.get("turn")
            if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
                raise CodexAppServerError("Codex turn/start 未返回有效的 Turn。")
            self._active_turn_id = turn["id"]
            self._workspace_locked = True

            try:
                deadline = asyncio.get_running_loop().time() + turn_timeout
                while True:
                    if completion.done() and queue.empty():
                        break
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError
                    event_task = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait(
                        {event_task, completion},
                        timeout=remaining,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        event_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await event_task
                        raise TimeoutError
                    if event_task in done:
                        yield event_task.result()
                        # Treat the turn timeout as an inactivity bound, not an
                        # absolute wall-clock limit. Long coding tasks can run
                        # well beyond ten minutes while continuing to emit
                        # reasoning, tool, and progress events.
                        deadline = (
                            asyncio.get_running_loop().time() + _TURN_TIMEOUT_SECONDS
                        )
                    else:
                        event_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await event_task
            except TimeoutError as error:
                await self.interrupt()
                raise CodexAppServerError(
                    "Codex 智能体长时间没有新进度，已停止本次任务，请重试。"
                ) from error

            turn_result = completion.result()
            status = str(turn_result.get("status") or "completed")
            if status.lower() in {"failed", "cancelled"}:
                error = turn_result.get("error")
                detail = (
                    _app_server_error_detail(error)
                    if error is not None
                    else f"Codex Turn 状态：{status}。"
                )
                raise CodexAppServerError(detail)
        except asyncio.CancelledError:
            await self.interrupt()
            raise
        finally:
            self._turn_events = None
            self._turn_completion = None
            self._active_turn_id = ""

    async def interrupt(self) -> None:
        """Interrupt the active turn when possible."""
        if not self.thread_id or not self._active_turn_id:
            return
        with contextlib.suppress(CodexAppServerError):
            await self.request(
                "turn/interrupt",
                {
                    "threadId": self.thread_id,
                    "turnId": self._active_turn_id,
                },
                timeout=10,
            )

    async def list_models(self) -> tuple[CodexModel, ...]:
        """Return every visible Codex model, following bounded pagination."""
        models: list[CodexModel] = []
        cursor = ""
        seen_cursors: set[str] = set()
        while len(models) < 500:
            result = await self.request(
                "model/list",
                {
                    "limit": 100,
                    "includeHidden": False,
                    **({"cursor": cursor} if cursor else {}),
                },
            )
            data = result.get("data")
            if not isinstance(data, list):
                raise CodexAppServerError("Codex model/list 返回格式无效。")
            for value in data:
                if not isinstance(value, dict):
                    continue
                model_id = value.get("model")
                if not isinstance(model_id, str):
                    model_id = value.get("id")
                if not isinstance(model_id, str) or not model_id.strip():
                    continue
                models.append(
                    CodexModel(
                        id=model_id,
                        display_name=(
                            value["displayName"]
                            if isinstance(value.get("displayName"), str)
                            else model_id
                        ),
                        description=_string(value.get("description"), 2_000),
                        is_default=value.get("isDefault") is True,
                    )
                )
                if len(models) >= 500:
                    break
            next_cursor = result.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            if next_cursor in seen_cursors:
                raise CodexAppServerError("Codex model/list 返回了重复游标。")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return tuple(models)

    async def set_model(self, model: str) -> str:
        """Update the model for the active thread."""
        self._ensure_thread_idle("切换模型")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("模型名称不能为空。")
        model = model.strip()
        await self.request(
            "thread/settings/update",
            {"threadId": self.thread_id, "model": model},
        )
        self.model = model
        return model

    async def list_skills(self, force_reload: bool = False) -> tuple[CodexSkill, ...]:
        """List enabled Skills while retaining their private paths server-side."""
        if not force_reload and self._skills_loaded and self._skills_cwd == self.cwd:
            return self._public_skills()
        requested_cwd = self.cwd
        result = await self.request(
            "skills/list",
            {
                "forceReload": force_reload,
                **({"cwds": [requested_cwd]} if requested_cwd else {}),
            },
        )
        data = result.get("data")
        if not isinstance(data, list):
            raise CodexAppServerError("Codex skills/list 返回格式无效。")
        previous_ids = {skill.path: skill.id for skill in self._skills_by_id.values()}
        next_skills: dict[str, _CodexPrivateSkill] = {}
        for entry in data:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("skills"), list)
                or (
                    requested_cwd
                    and isinstance(entry.get("cwd"), str)
                    and entry.get("cwd") != requested_cwd
                )
            ):
                continue
            for value in entry["skills"]:
                if (
                    not isinstance(value, dict)
                    or value.get("enabled") is not True
                    or not isinstance(value.get("name"), str)
                    or not value["name"].strip()
                    or not isinstance(value.get("path"), str)
                    or not value["path"]
                ):
                    continue
                path = value["path"]
                skill = _CodexPrivateSkill(
                    id=previous_ids.get(path) or str(uuid.uuid4()),
                    name=value["name"],
                    description=_string(value.get("description"), 1_000),
                    path=path,
                )
                next_skills[skill.id] = skill
                if len(next_skills) >= 500:
                    break
            if len(next_skills) >= 500:
                break
        if requested_cwd != self.cwd:
            return await self.list_skills(force_reload)
        self._skills_by_id = next_skills
        self._skills_cwd = requested_cwd
        self._skills_loaded = True
        return self._public_skills()

    async def new_thread(self) -> CodexThreadSnapshot:
        """Start and activate a fresh thread with current runtime settings."""
        self._ensure_thread_idle("创建新对话")
        result = await self.request("thread/start", self._thread_options())
        return self._activate_thread_snapshot("thread/start", result)

    async def list_threads(
        self,
        *,
        cursor: str = "",
        search_term: str = "",
        archived: bool = False,
    ) -> tuple[tuple[CodexThreadSummary, ...], str]:
        """List recent threads using the same ordering as Codex clients."""
        result = await self.request(
            "thread/list",
            {
                "limit": 30,
                "sortKey": "updated_at",
                "sortDirection": "desc",
                "sourceKinds": ["appServer", "cli", "vscode"],
                "archived": archived,
                **({"cursor": cursor} if cursor else {}),
                **({"searchTerm": search_term} if search_term else {}),
            },
        )
        data = result.get("data")
        if not isinstance(data, list):
            raise CodexAppServerError("Codex thread/list 返回格式无效。")
        threads: list[CodexThreadSummary] = []
        for value in data:
            if not isinstance(value, dict):
                continue
            summary = _thread_summary(value)
            if summary is not None:
                threads.append(summary)
        next_cursor = result.get("nextCursor")
        return tuple(threads), next_cursor if isinstance(next_cursor, str) else ""

    async def resume_thread(self, thread_id: str) -> CodexThreadSnapshot:
        """Resume and activate one existing thread."""
        self._ensure_thread_idle("切换对话")
        thread_id = _required_identifier(thread_id, "Thread ID")
        result = await self.request(
            "thread/resume",
            {"threadId": thread_id, **self._thread_options()},
        )
        self._activate_thread_snapshot("thread/resume", result)
        snapshot = await self.read_thread(thread_id)
        self._workspace_locked = snapshot.workspace_locked
        return snapshot

    async def read_thread(self, thread_id: str) -> CodexThreadSnapshot:
        """Read one thread's complete stored history without activating it."""
        thread_id = _required_identifier(thread_id, "Thread ID")
        try:
            result = await self.request(
                "thread/read",
                {"threadId": thread_id, "includeTurns": True},
            )
        except CodexAppServerError as error:
            # A freshly-started thread has no user message yet, so the Codex
            # app-server rejects includeTurns with -32600 ("not materialized
            # yet"). Fall back to a metadata-only read and return an empty
            # conversation instead of surfacing a 500 to the browser.
            if not _is_thread_not_materialized_error(error):
                raise
            result = await self.request(
                "thread/read",
                {"threadId": thread_id},
            )
        snapshot = self._thread_snapshot("thread/read", result)
        imported = self._imported_history_by_thread.get(thread_id)
        if imported is None:
            imported = await self._read_imported_history(thread_id, snapshot.cwd)
            if imported:
                self._imported_history_by_thread[thread_id] = imported
        return _prepend_imported_history(snapshot, imported)

    async def inject_history(self, messages: tuple[CodexImportedMessage, ...]) -> None:
        """Persist visible history without starting or replaying a turn."""
        self._ensure_thread_idle("导入历史消息")
        if not messages:
            return
        items: list[dict[str, object]] = []
        for message in messages:
            if message.role == "assistant" and message.images:
                raise CodexAppServerError(
                    "Imported assistant messages cannot contain images"
                )
            content: list[dict[str, str]] = []
            if message.content:
                content.append(
                    {
                        "type": (
                            "input_text" if message.role == "user" else "output_text"
                        ),
                        "text": message.content,
                    }
                )
            content.extend(
                {
                    "type": "input_image",
                    "image_url": image.data_url(),
                }
                for image in message.images
            )
            items.append(
                {
                    "type": "message",
                    "role": message.role,
                    "content": content,
                }
            )
        await self.request(
            "thread/inject_items",
            {
                "threadId": self.thread_id,
                "items": items,
            },
            timeout=_IMPORTED_HISTORY_INJECT_TIMEOUT_SECONDS,
        )
        await self._write_imported_history(messages)
        self._imported_history_by_thread[self.thread_id] = messages

    async def _write_imported_history(
        self, messages: tuple[CodexImportedMessage, ...]
    ) -> None:
        payload = json.dumps(
            {
                "schemaVersion": 2,
                "threadId": self.thread_id,
                "messages": [asdict(message) for message in messages],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > _IMPORTED_HISTORY_MAX_BASE64_BYTES:
            raise CodexAppServerError("Imported history payload is too large")
        path = _imported_history_path(self.thread_id, self.cwd)
        parts = tuple(
            payload[offset : offset + _IMPORTED_HISTORY_PART_BYTES]
            for offset in range(0, len(payload), _IMPORTED_HISTORY_PART_BYTES)
        )
        if not parts or len(parts) > _IMPORTED_HISTORY_MAX_PARTS:
            raise CodexAppServerError("Imported history has too many storage parts")
        for index, part in enumerate(parts):
            await self.request(
                "fs/writeFile",
                {
                    "path": _imported_history_part_path(path, index),
                    "dataBase64": base64.b64encode(part).decode("ascii"),
                },
            )
        manifest = json.dumps(
            {
                "schemaVersion": 1,
                "storage": "chunked",
                "threadId": self.thread_id,
                "partCount": len(parts),
                "sizeBytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        await self.request(
            "fs/writeFile",
            {
                "path": path,
                "dataBase64": base64.b64encode(manifest).decode("ascii"),
            },
        )

    async def _read_imported_history(
        self, thread_id: str, cwd: str
    ) -> tuple[CodexImportedMessage, ...]:
        for path in _imported_history_read_paths(thread_id, cwd):
            try:
                result = await self.request(
                    "fs/readFile",
                    {"path": path},
                    timeout=_IMPORTED_HISTORY_READ_TIMEOUT_SECONDS,
                )
            except CodexAppServerError:
                continue
            encoded = result.get("dataBase64")
            if (
                not isinstance(encoded, str)
                or not encoded
                or len(encoded) > _IMPORTED_HISTORY_MAX_BASE64_BYTES
            ):
                continue
            try:
                stored = base64.b64decode(encoded, validate=True)
                value = json.loads(stored)
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(value, dict) and value.get("storage") == "chunked":
                stored = await self._read_imported_history_parts(
                    path,
                    thread_id,
                    value,
                )
                if stored is None:
                    continue
                try:
                    value = json.loads(stored)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
            if (
                not isinstance(value, dict)
                or value.get("schemaVersion") not in {1, 2}
                or value.get("threadId") != thread_id
                or not isinstance(value.get("messages"), list)
            ):
                continue
            messages: list[CodexImportedMessage] = []
            raw_messages = value["messages"]
            if len(raw_messages) > _IMPORTED_HISTORY_MAX_MESSAGES:
                continue
            total_characters = 0
            total_image_bytes = 0
            total_images = 0
            valid = True
            for item in raw_messages:
                if not isinstance(item, dict):
                    valid = False
                    break
                role = item.get("role")
                content = item.get("content")
                if role not in {"user", "assistant"} or not isinstance(content, str):
                    valid = False
                    break
                if len(content) > _IMPORTED_HISTORY_MAX_MESSAGE_CHARACTERS:
                    valid = False
                    break
                total_characters += len(content)
                if total_characters > _IMPORTED_HISTORY_MAX_CHARACTERS:
                    valid = False
                    break
                images: list[CodexImportedImage] = []
                raw_images = item.get("images", [])
                if not isinstance(raw_images, list) or (
                    role == "assistant" and raw_images
                ):
                    valid = False
                    break
                for raw_image in raw_images:
                    image = _imported_image(raw_image)
                    if image is None:
                        valid = False
                        break
                    try:
                        decoded = base64.b64decode(image.data, validate=True)
                    except ValueError:
                        valid = False
                        break
                    if not _imported_image_matches(image, decoded):
                        valid = False
                        break
                    image_bytes = len(decoded)
                    total_images += 1
                    total_image_bytes += image_bytes
                    if (
                        total_images > _IMPORTED_HISTORY_MAX_IMAGES
                        or image_bytes > _IMPORTED_HISTORY_MAX_IMAGE_BYTES
                        or total_image_bytes > _IMPORTED_HISTORY_MAX_IMAGE_TOTAL_BYTES
                    ):
                        valid = False
                        break
                    images.append(image)
                if not valid or (not content and not images):
                    valid = False
                    break
                messages.append(
                    CodexImportedMessage(
                        role=role,
                        content=content,
                        images=tuple(images),
                    )
                )
            if valid and messages:
                return tuple(messages)
        return ()

    async def _read_imported_history_parts(
        self,
        path: str,
        thread_id: str,
        manifest: dict[str, object],
    ) -> bytes | None:
        part_count = manifest.get("partCount")
        size_bytes = manifest.get("sizeBytes")
        digest = manifest.get("sha256")
        if (
            manifest.get("schemaVersion") != 1
            or manifest.get("threadId") != thread_id
            or not isinstance(part_count, int)
            or not 1 <= part_count <= _IMPORTED_HISTORY_MAX_PARTS
            or not isinstance(size_bytes, int)
            or not 1 <= size_bytes <= _IMPORTED_HISTORY_MAX_BASE64_BYTES
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            return None
        parts: list[bytes] = []
        for index in range(part_count):
            try:
                result = await self.request(
                    "fs/readFile",
                    {"path": _imported_history_part_path(path, index)},
                    timeout=_IMPORTED_HISTORY_READ_TIMEOUT_SECONDS,
                )
            except CodexAppServerError:
                return None
            encoded = result.get("dataBase64")
            if not isinstance(encoded, str) or not encoded:
                return None
            try:
                part = base64.b64decode(encoded, validate=True)
            except ValueError:
                return None
            if not part or len(part) > _IMPORTED_HISTORY_PART_BYTES:
                return None
            parts.append(part)
        payload = b"".join(parts)
        if len(payload) != size_bytes:
            return None
        if not secrets.compare_digest(hashlib.sha256(payload).hexdigest(), digest):
            return None
        return payload

    async def fork_thread(self) -> CodexThreadSnapshot:
        """Fork and activate the current thread."""
        self._ensure_thread_idle("分叉对话")
        result = await self.request(
            "thread/fork",
            {"threadId": self.thread_id, **self._thread_options()},
        )
        return self._activate_thread_snapshot("thread/fork", result)

    async def archive_thread(self, thread_id: str) -> CodexThreadSnapshot | None:
        """Archive a thread and create a replacement when it was active."""
        self._ensure_thread_idle("归档对话")
        thread_id = _required_identifier(thread_id, "Thread ID")
        active_thread_id = self.thread_id
        if thread_id != active_thread_id:
            try:
                await self.resume_thread(thread_id)
            except CodexAppServerError as error:
                if "no rollout found for thread id" not in str(error):
                    raise
                return None
        await self.request("thread/unsubscribe", {"threadId": thread_id})
        await self.request("thread/archive", {"threadId": thread_id})
        if thread_id == active_thread_id:
            return await self.new_thread()
        try:
            await self.resume_thread(active_thread_id)
            return None
        except CodexAppServerError as error:
            if "no rollout found for thread id" not in str(error):
                raise
            return await self.new_thread()

    async def delete_thread(self, thread_id: str) -> CodexThreadSnapshot | None:
        """Remove a thread from history using the app-server archive method."""
        return await self.archive_thread(thread_id)

    async def compact_thread(self) -> None:
        """Start app-server compaction for the active thread."""
        self._ensure_thread_idle("压缩对话")
        await self.request(
            "thread/compact/start",
            {"threadId": self.thread_id},
        )

    async def update_permissions(
        self, settings: CodexPermissionSettings
    ) -> CodexPermissionSettings:
        """Persist settings globally and hot-apply them to the current thread."""
        if self.active:
            raise CodexAppServerError("当前任务运行中，暂时不能修改权限。")
        normalized = CodexPermissionSettings(
            approval_policy=settings.approval_policy,
            approvals_reviewer=settings.approvals_reviewer,
            sandbox_mode=settings.sandbox_mode,
            network_access=(
                True
                if settings.sandbox_mode == "danger-full-access"
                else settings.network_access
            ),
        )
        config = await self.request("config/read", {"includeLayers": True})
        expected_version = _user_config_version(config)
        await self.request(
            "config/batchWrite",
            {
                "edits": [
                    _config_edit("sandbox_mode", normalized.sandbox_mode),
                    _config_edit("approval_policy", normalized.approval_policy),
                    _config_edit("approvals_reviewer", normalized.approvals_reviewer),
                    _config_edit(
                        "sandbox_workspace_write.network_access",
                        normalized.network_access,
                    ),
                ],
                **({"expectedVersion": expected_version} if expected_version else {}),
                "reloadUserConfig": True,
            },
        )
        self.permissions = normalized
        await self._sync_current_thread_permissions()
        return normalized

    async def apply_session_permissions(
        self, settings: CodexPermissionSettings
    ) -> None:
        """Adopt settings persisted by another thread in this cloud Session."""
        normalized = CodexPermissionSettings(
            approval_policy=settings.approval_policy,
            approvals_reviewer=settings.approvals_reviewer,
            sandbox_mode=settings.sandbox_mode,
            network_access=(
                True
                if settings.sandbox_mode == "danger-full-access"
                else settings.network_access
            ),
        )
        self.permissions = normalized
        if not self.active:
            await self._sync_current_thread_permissions()

    async def update_workspace(self, cwd: str) -> str:
        """Change the current thread CWD before its first turn."""
        if self.workspace_locked:
            raise CodexAppServerError("当前对话已经开始，工作空间不能再修改。")
        cwd = _normalize_directory(cwd)
        await self.request(
            "thread/settings/update",
            {"threadId": self.thread_id, "cwd": cwd},
        )
        self.cwd = cwd
        return cwd

    async def list_directories(self, path: str) -> CodexDirectoryListing:
        """Browse remote directories without exposing arbitrary file content."""
        path = _normalize_directory(path)
        result = await self.request("fs/readDirectory", {"path": path})
        entries = result.get("entries")
        if not isinstance(entries, list):
            raise CodexAppServerError("远程目录响应格式无效。")
        directories: list[CodexDirectoryEntry] = []
        for value in entries[:_MAX_DIRECTORY_ENTRIES]:
            if (
                not isinstance(value, dict)
                or value.get("isDirectory") is not True
                or not isinstance(value.get("fileName"), str)
            ):
                continue
            name = value["fileName"]
            if not name or name in {".", ".."} or "/" in name:
                continue
            directories.append(
                CodexDirectoryEntry(
                    name=name,
                    path=(f"/{name}" if path == "/" else f"{path.rstrip('/')}/{name}"),
                )
            )
        directories.sort(key=lambda entry: entry.name.casefold())
        parent = None if path == "/" else posixpath.dirname(path) or "/"
        return CodexDirectoryListing(
            path=path,
            parent=parent,
            directories=tuple(directories),
        )

    def resolve_approval(self, approval_id: str, decision: ApprovalDecision) -> None:
        """Resolve a pending app-server approval."""
        future = self._pending_approvals.get(approval_id)
        if future is None or future.done():
            raise CodexAppServerError("审批请求不存在或已经处理。")
        future.set_result(decision)

    async def close(self) -> None:
        """Close the local app-server connection and reject pending work."""
        if self._closed:
            return
        self._closed = True
        error = CodexAppServerError("Codex app-server 连接已关闭。")
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(error)
        self._pending_requests.clear()
        for future in self._pending_approvals.values():
            if not future.done():
                future.set_result("decline")
        self._pending_approvals.clear()
        for task in tuple(self._server_request_tasks):
            task.cancel()
        if self._server_request_tasks:
            await asyncio.gather(
                *tuple(self._server_request_tasks), return_exceptions=True
            )
        await self._close_transport()
        self._endpoint = ""

    async def _close_transport(self) -> None:
        """Close only the current WebSocket so the Session can reconnect."""
        reader_task = self._reader_task
        self._reader_task = None
        if reader_task is not None and reader_task is not asyncio.current_task():
            reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader_task
        websocket = self._websocket
        self._websocket = None
        if websocket is not None:
            with contextlib.suppress(Exception):
                await websocket.close()
        self._connected_at = 0.0

    async def _send(self, message: dict[str, object]) -> None:
        if self._websocket is None or self._closed:
            raise CodexAppServerError("Codex app-server 连接已关闭。")
        async with self._send_lock:
            try:
                await self._websocket.send(json.dumps(message, ensure_ascii=False))
            except Exception as error:
                failure = CodexAppServerError("向 Codex app-server 发送请求失败。")
                failure.__cause__ = error
                self._connection_failure = failure
                raise failure

    async def _read_messages(self) -> None:
        failure: CodexAppServerError | None = None
        websocket = self._websocket
        try:
            assert websocket is not None
            async for raw_message in websocket:
                if not isinstance(raw_message, str):
                    raise CodexAppServerError(
                        "Codex app-server 返回了不支持的二进制消息。"
                    )
                message = json.loads(raw_message)
                if not isinstance(message, dict):
                    raise CodexAppServerError("Codex app-server 返回了无效消息。")
                method = message.get("method")
                if isinstance(method, str) and "id" in message:
                    task = asyncio.create_task(
                        self._handle_server_request(
                            message["id"], method, message.get("params")
                        )
                    )
                    self._server_request_tasks.add(task)
                    task.add_done_callback(self._server_request_tasks.discard)
                    continue
                if "id" in message:
                    self._handle_response(message)
                    continue
                if isinstance(method, str):
                    params = message.get("params")
                    if not isinstance(params, dict):
                        params = {}
                    self._handle_notification(method, params)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - transport boundary
            if isinstance(error, CodexAppServerError):
                failure = error
            else:
                failure = CodexAppServerError("Codex app-server 连接异常。")
                failure.__cause__ = error
        else:
            if not self._closed:
                failure = CodexAppServerError("Codex app-server 连接已断开。")
        if failure is not None:
            self._connection_failure = failure
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(failure)
            if self._turn_completion is not None and not self._turn_completion.done():
                self._turn_completion.set_exception(failure)
        if self._websocket is websocket:
            self._websocket = None
        if self._reader_task is asyncio.current_task():
            self._reader_task = None

    def _handle_response(self, message: dict[str, object]) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        future = self._pending_requests.get(request_id)
        if future is None or future.done():
            return
        error = message.get("error")
        if error is not None:
            future.set_exception(CodexAppServerError(_app_server_error_detail(error)))
            return
        result = message.get("result")
        if not isinstance(result, dict):
            future.set_exception(
                CodexAppServerError("Codex app-server 返回了无效结果。")
            )
            return
        future.set_result(result)

    def _handle_notification(self, method: str, params: dict[str, object]) -> None:
        if method == "thread/tokenUsage/updated":
            self._handle_token_usage(params)
            return
        if method == "item/agentMessage/delta":
            delta = params.get("delta")
            if isinstance(delta, str) and delta:
                item_id = params.get("itemId")
                if isinstance(item_id, str) and item_id:
                    self._agent_message_delta_ids.add(item_id)
                else:
                    self._received_unidentified_agent_delta = True
                self._emit(CodexAppServerEvent(kind="text", text=delta))
            return
        if method in {
            "item/reasoning/summaryTextDelta",
            "item/reasoning/textDelta",
        }:
            delta = params.get("delta")
            item_id = params.get("itemId")
            if (
                isinstance(delta, str)
                and delta
                and isinstance(item_id, str)
                and item_id
            ):
                text = self._reasoning_delta_text.get(item_id, "") + delta
                self._reasoning_delta_text[item_id] = text
                self._emit(
                    CodexAppServerEvent(
                        kind="thinking",
                        item_id=item_id,
                        status="running",
                        text=text,
                    )
                )
            return
        if method in {"item/started", "item/completed"}:
            item = params.get("item")
            if isinstance(item, dict):
                if (
                    method == "item/completed"
                    and item.get("type") == "agentMessage"
                    and item.get("phase") != "commentary"
                ):
                    item_id = item.get("id")
                    received_delta = (
                        isinstance(item_id, str)
                        and item_id in self._agent_message_delta_ids
                    ) or self._received_unidentified_agent_delta
                    text = _string(item.get("text"), 100_000)
                    if text and not received_delta:
                        self._emit(CodexAppServerEvent(kind="text", text=text))
                event = _event_from_item(item, completed=method == "item/completed")
                if event is not None:
                    self._emit(event)
            return
        if method == "turn/started":
            turn = params.get("turn")
            if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                self._active_turn_id = turn["id"]
            return
        if method == "turn/completed":
            turn = params.get("turn")
            if (
                isinstance(turn, dict)
                and self._turn_completion is not None
                and not self._turn_completion.done()
            ):
                self._turn_completion.set_result(turn)
            return
        if method == "thread/settings/updated":
            self._apply_runtime_settings(params)
            return
        if method == "error":
            message = params.get("message")
            if (
                isinstance(message, str)
                and self._turn_completion is not None
                and not self._turn_completion.done()
            ):
                self._turn_completion.set_exception(CodexAppServerError(message))

    def _handle_token_usage(self, params: dict[str, object]) -> None:
        update = _token_usage_update(params)
        if update is None:
            return
        thread_id, turn_id, total, last, context_window = update
        if thread_id != self.thread_id:
            return
        increment = (
            _subtract_usage(total, self._thread_token_total)
            if self._thread_token_total is not None
            else last
        )
        if increment is None:
            increment = last
        self._thread_token_total = total
        if context_window is not None:
            self._model_context_window = context_window
        current = self._usage_by_turn_id.get(turn_id, CodexTokenUsage())
        usage = _add_usage(current, increment)
        self._usage_by_turn_id[turn_id] = usage
        if self._turn_events is None:
            return
        if self._active_turn_id and self._active_turn_id != turn_id:
            return
        self._emit(
            CodexAppServerEvent(
                kind="usage",
                turn_id=turn_id,
                usage=usage,
                thread_total=total,
                model_context_window=context_window,
            )
        )

    async def _handle_server_request(
        self, request_id: object, method: str, raw_params: object
    ) -> None:
        if not isinstance(raw_params, dict):
            await self._send(
                {
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": f"invalid params for {method}",
                    },
                }
            )
            return
        params = raw_params
        if method == "item/permissions/requestApproval":
            await self._send(
                {
                    "id": request_id,
                    "result": {"permissions": {}, "scope": "turn"},
                }
            )
            return
        if method not in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        }:
            await self._send(
                {
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"unsupported server request: {method}",
                    },
                }
            )
            return
        if not _has_approval_identity(params):
            await self._send(
                {
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": f"invalid params for {method}",
                    },
                }
            )
            return

        approval_id = str(uuid.uuid4())
        approval = CodexApproval(
            id=approval_id,
            kind=(
                "command"
                if method == "item/commandExecution/requestApproval"
                else "file"
            ),
            method=method,
            reason=_string(params.get("reason"), 2_000),
            command=_string(params.get("command"), 20_000),
            cwd=_string(params.get("cwd"), 4_096),
            grant_root=_string(params.get("grantRoot"), 4_096),
            changes=_bounded_value(params.get("changes")),
            thread_id=_string(params.get("threadId"), 200),
            turn_id=_string(params.get("turnId"), 200),
            item_id=_string(params.get("itemId"), 200),
            environment_id=(
                _string(params.get("environmentId"), 200)
                if params.get("environmentId") is not None
                else None
            ),
            started_at_ms=(
                int(params["startedAtMs"])
                if isinstance(params.get("startedAtMs"), (int, float))
                else None
            ),
            command_actions=_bounded_value(params.get("commandActions")),
            network_approval_context=_bounded_value(
                params.get("networkApprovalContext")
            ),
        )
        future: asyncio.Future[ApprovalDecision] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_approvals[approval_id] = future
        self._emit(
            CodexAppServerEvent(
                kind="approval",
                item_id=approval_id,
                status="running",
                name=(
                    "允许执行命令？" if approval.kind == "command" else "允许修改文件？"
                ),
                approval=approval,
            )
        )
        try:
            decision = await asyncio.wait_for(future, timeout=_APPROVAL_TIMEOUT_SECONDS)
        except TimeoutError:
            decision = "decline"
        finally:
            self._pending_approvals.pop(approval_id, None)
        await self._send({"id": request_id, "result": {"decision": decision}})
        self._emit(
            CodexAppServerEvent(
                kind="approval",
                item_id=approval_id,
                status="done",
                response={"decision": decision},
                approval_resolved_id=approval_id,
            )
        )

    def _emit(self, event: CodexAppServerEvent) -> None:
        if self._turn_events is not None:
            self._turn_events.put_nowait(event)

    def _apply_thread_snapshot(self, result: dict[str, object]) -> None:
        self._activate_thread_snapshot("thread/start", result)

    def _activate_thread_snapshot(
        self, method: str, result: dict[str, object]
    ) -> CodexThreadSnapshot:
        snapshot = self._thread_snapshot(method, result)
        self.thread_id = snapshot.thread.id
        if snapshot.cwd:
            self.cwd = snapshot.cwd
        self._workspace_locked = snapshot.workspace_locked
        self._apply_runtime_settings(result)
        if snapshot.model:
            self.model = snapshot.model
        self._skills_loaded = False
        self._usage_by_turn_id.clear()
        self._thread_token_total = None
        self._model_context_window = None
        return CodexThreadSnapshot(
            thread=snapshot.thread,
            messages=snapshot.messages,
            model=self.model,
            cwd=self.cwd,
            workspace_locked=self._workspace_locked,
        )

    def _thread_snapshot(
        self, method: str, result: dict[str, object]
    ) -> CodexThreadSnapshot:
        """Parse one app-server thread response without changing active state."""
        thread = result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise CodexAppServerError(f"Codex {method} 未返回有效的 Thread。")
        summary = _thread_summary(thread)
        if summary is None:
            raise CodexAppServerError(f"Codex {method} 未返回有效的 Thread。")
        cwd = result.get("cwd")
        if not isinstance(cwd, str):
            cwd = thread.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            cwd = self.cwd
        turns = thread.get("turns")
        workspace_locked = isinstance(turns, list) and bool(turns)
        model = result.get("model")
        if not isinstance(model, str):
            model = thread.get("model")
        if not isinstance(model, str) or not model:
            model = self.model
        return CodexThreadSnapshot(
            thread=summary,
            messages=_thread_messages(turns, summary.updated_at),
            model=model,
            cwd=cwd,
            workspace_locked=workspace_locked,
        )

    def _ensure_thread_idle(self, action: str) -> None:
        if self.active:
            raise CodexAppServerError(f"当前任务运行中，暂时不能{action}。")
        if not self.thread_id:
            raise CodexAppServerError("Codex Thread 尚未初始化。")

    def _thread_options(self) -> dict[str, object]:
        return {
            **({"cwd": self.cwd} if self.cwd else {}),
            **({"model": self.model} if self.model else {}),
            **_runtime_permission_params(self.permissions, self.cwd),
        }

    def _public_skills(self) -> tuple[CodexSkill, ...]:
        return tuple(
            CodexSkill(
                id=skill.id,
                name=skill.name,
                description=skill.description,
            )
            for skill in self._skills_by_id.values()
        )

    async def _resolve_skills(
        self, prompt: str, skill_ids: tuple[str, ...]
    ) -> tuple[_CodexPrivateSkill, ...]:
        if not skill_ids:
            return ()
        if len(skill_ids) > 20:
            raise CodexAppServerError("单次消息最多选择 20 个 Skill。")
        await self.list_skills()
        selected_by_name: dict[str, _CodexPrivateSkill] = {}
        for skill_id in skill_ids:
            skill = self._skills_by_id.get(skill_id)
            if skill is None:
                raise CodexAppServerError("所选 Skill 已不可用，请重新选择。")
            existing = selected_by_name.get(skill.name)
            if existing is not None and existing.path != skill.path:
                raise CodexAppServerError(
                    f"同一条消息不能选择两个名为 ${skill.name} 的 Skill。"
                )
            selected_by_name[skill.name] = skill
        leading_names = _leading_skill_names(
            prompt, {skill.name for skill in self._skills_by_id.values()}
        )
        if not leading_names:
            raise CodexAppServerError("所选 Skill 必须位于消息开头。")
        if set(leading_names) != set(selected_by_name):
            raise CodexAppServerError("消息开头的 Skill 与所选 Skill 不一致。")
        return tuple(selected_by_name[name] for name in leading_names)

    def _apply_runtime_settings(self, value: dict[str, object]) -> None:
        approval_policy = value.get("approvalPolicy")
        approvals_reviewer = value.get("approvalsReviewer")
        sandbox = value.get("sandbox") or value.get("sandboxPolicy")
        sandbox_mode, network_access = _sandbox_settings(sandbox)
        self.permissions = CodexPermissionSettings(
            approval_policy=(
                cast(ApprovalPolicy, approval_policy)
                if approval_policy in APPROVAL_POLICIES
                else self.permissions.approval_policy
            ),
            approvals_reviewer=(
                cast(ApprovalsReviewer, approvals_reviewer)
                if approvals_reviewer in APPROVALS_REVIEWERS
                else self.permissions.approvals_reviewer
            ),
            sandbox_mode=sandbox_mode or self.permissions.sandbox_mode,
            network_access=(
                network_access
                if network_access is not None
                else self.permissions.network_access
            ),
        )
        cwd = value.get("cwd")
        if isinstance(cwd, str) and cwd:
            self.cwd = cwd
        model = value.get("model")
        if isinstance(model, str) and model:
            self.model = model

    async def _sync_current_thread_permissions(self) -> None:
        await self.request(
            "thread/settings/update",
            {
                "threadId": self.thread_id,
                **_runtime_permission_params(self.permissions, self.cwd),
            },
        )


def permission_settings_from_payload(
    value: object,
) -> CodexPermissionSettings:
    """Validate a browser permission payload."""
    if not isinstance(value, dict):
        raise TypeError("权限配置格式无效。")
    approval_policy = value.get("approvalPolicy")
    approvals_reviewer = value.get("approvalsReviewer")
    sandbox_mode = value.get("sandboxMode")
    network_access = value.get("networkAccess")
    if not isinstance(approval_policy, str) or approval_policy not in APPROVAL_POLICIES:
        raise ValueError("Approval policy 配置无效。")
    if (
        not isinstance(approvals_reviewer, str)
        or approvals_reviewer not in APPROVALS_REVIEWERS
    ):
        raise ValueError("Approvals reviewer 配置无效。")
    if not isinstance(sandbox_mode, str) or sandbox_mode not in SANDBOX_MODES:
        raise ValueError("Sandbox mode 配置无效。")
    if not isinstance(network_access, bool):
        raise TypeError("网络访问配置必须是布尔值。")
    return CodexPermissionSettings(
        approval_policy=cast(ApprovalPolicy, approval_policy),
        approvals_reviewer=cast(ApprovalsReviewer, approvals_reviewer),
        sandbox_mode=cast(SandboxMode, sandbox_mode),
        network_access=(
            True if sandbox_mode == "danger-full-access" else network_access
        ),
    )


def approval_decision_from_payload(value: object) -> ApprovalDecision:
    """Validate one browser approval decision."""
    if not isinstance(value, str) or value not in APPROVAL_DECISIONS:
        raise ValueError("审批决定无效。")
    return cast(ApprovalDecision, value)


def sandbox_service_url(
    endpoint: str,
    pathname: str,
    *,
    websocket: bool = False,
    query: dict[str, str] | None = None,
) -> str:
    """Build a private Sandbox data-plane URL while preserving Endpoint auth."""
    if not pathname.startswith("/"):
        raise ValueError("Sandbox 服务路径必须以 / 开头。")
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        raise ValueError("AgentKit Session 返回了无效 Endpoint。")
    scheme = (
        ("wss" if parsed.scheme in {"https", "wss"} else "ws")
        if websocket
        else ("https" if parsed.scheme in {"https", "wss"} else "http")
    )
    base_path = parsed.path.rstrip("/")
    if base_path.endswith("/v1/codex/app-server"):
        base_path = base_path.removesuffix("/v1/codex/app-server")
    path = f"{base_path}{pathname}"
    from urllib.parse import parse_qsl, urlencode

    values = list(parse_qsl(parsed.query, keep_blank_values=True))
    if query:
        values = [(key, value) for key, value in values if key not in query]
        values.extend(query.items())
    return urlunsplit((scheme, parsed.netloc, path, urlencode(values), ""))


def _app_server_url(endpoint: str) -> str:
    return sandbox_service_url(endpoint, "/v1/codex/app-server/", websocket=True)


def _config_edit(key_path: str, value: object) -> dict[str, object]:
    return {
        "keyPath": key_path,
        "value": value,
        "mergeStrategy": "replace",
    }


def _user_config_version(result: dict[str, object]) -> str:
    layers = result.get("layers")
    if not isinstance(layers, list):
        return ""
    for candidate in layers:
        if not isinstance(candidate, dict):
            continue
        name = candidate.get("name")
        if (
            isinstance(name, dict)
            and name.get("type") == "user"
            and name.get("profile") in {None, ""}
            and isinstance(candidate.get("version"), str)
        ):
            return candidate["version"]
    return ""


def _runtime_permission_params(
    settings: CodexPermissionSettings, cwd: str
) -> dict[str, object]:
    return {
        "approvalPolicy": settings.approval_policy,
        "approvalsReviewer": settings.approvals_reviewer,
        "sandboxPolicy": _sandbox_policy(settings, cwd),
    }


def _sandbox_policy(settings: CodexPermissionSettings, cwd: str) -> dict[str, object]:
    if settings.sandbox_mode == "danger-full-access":
        return {"type": "dangerFullAccess"}
    if settings.sandbox_mode == "read-only":
        return {
            "type": "readOnly",
            "networkAccess": settings.network_access,
        }
    return {
        "type": "workspaceWrite",
        "writableRoots": [cwd] if cwd else [],
        "networkAccess": settings.network_access,
        "excludeTmpdirEnvVar": False,
        "excludeSlashTmp": False,
    }


def _sandbox_settings(
    value: object,
) -> tuple[SandboxMode | None, bool | None]:
    if isinstance(value, str) and value in SANDBOX_MODES:
        return cast(SandboxMode, value), None
    if not isinstance(value, dict):
        return None, None
    kind = value.get("type")
    network = (
        value.get("networkAccess")
        if isinstance(value.get("networkAccess"), bool)
        else None
    )
    if kind == "dangerFullAccess":
        return "danger-full-access", True
    if kind == "readOnly":
        return "read-only", network
    if kind == "workspaceWrite":
        return "workspace-write", network
    return None, None


def _normalize_directory(path: str) -> str:
    if not isinstance(path, str):
        raise TypeError("工作目录必须是文本。")
    path = path.strip()
    if not path.startswith("/") or "\0" in path or len(path) > 4_096:
        raise ValueError("工作目录必须是远程沙箱中的绝对路径。")
    normalized = posixpath.normpath(path)
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _has_approval_identity(value: dict[str, object]) -> bool:
    started_at_ms = value.get("startedAtMs")
    return (
        isinstance(value.get("threadId"), str)
        and isinstance(value.get("turnId"), str)
        and isinstance(value.get("itemId"), str)
        and isinstance(started_at_ms, (int, float))
        and not isinstance(started_at_ms, bool)
        and math.isfinite(started_at_ms)
    )


def _event_from_item(
    item: dict[str, object], *, completed: bool
) -> CodexAppServerEvent | None:
    item_id = _string(item.get("id"), 200) or str(uuid.uuid4())
    item_type = item.get("type")
    status = _completion_status(item.get("status")) if completed else "running"
    if item_type == "reasoning":
        summary = item.get("summary")
        text = (
            "\n".join(
                _string(entry, 4_000) for entry in summary if isinstance(entry, str)
            )
            if isinstance(summary, list)
            else _string(summary, 4_000)
        )
        return CodexAppServerEvent(
            kind="thinking",
            item_id=item_id,
            status=status,
            text=text,
        )
    if item_type == "agentMessage":
        phase = item.get("phase")
        text = _string(item.get("text"), 100_000)
        if phase == "commentary":
            return CodexAppServerEvent(
                kind="commentary",
                item_id=item_id,
                status=status,
                text=text,
            )
        return None
    if item_type == "commandExecution":
        response = None
        if completed:
            response = {
                "status": _string(item.get("status"), 100) or "completed",
                "exitCode": _bounded_value(item.get("exitCode")),
                "output": _bounded_value(
                    item.get("aggregatedOutput") or item.get("output")
                ),
            }
        return CodexAppServerEvent(
            kind="tool",
            item_id=item_id,
            status=status,
            name="运行命令",
            arguments={
                "command": _string(item.get("command"), 20_000),
                "cwd": _string(item.get("cwd"), 4_096),
            },
            response=response,
        )
    if item_type == "fileChange":
        return CodexAppServerEvent(
            kind="tool",
            item_id=item_id,
            status=status,
            name="修改文件",
            arguments={"changes": _bounded_value(item.get("changes"))},
            response=(
                {"status": _string(item.get("status"), 100) or status}
                if completed
                else None
            ),
        )
    if item_type == "mcpToolCall":
        server = _string(item.get("server"), 100)
        tool = _string(item.get("tool"), 100)
        return CodexAppServerEvent(
            kind="tool",
            item_id=item_id,
            status=status,
            name=f"MCP · {'/'.join(filter(None, (server, tool)))}",
            arguments=_bounded_value(item.get("arguments")),
            response=(
                _bounded_value(item.get("result") or item.get("error"))
                if completed
                else None
            ),
        )
    if item_type == "webSearch":
        return CodexAppServerEvent(
            kind="tool",
            item_id=item_id,
            status=status,
            name="网络搜索",
            arguments={"query": _string(item.get("query"), 4_000)},
            response=(_bounded_value(item.get("result")) if completed else None),
        )
    return None


def _completion_status(value: object) -> str:
    return "error" if value in {"failed", "declined", "cancelled"} else "done"


def _string(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    return value[:maximum]


def _bounded_value(value: object, depth: int = 0) -> object:
    if depth > 4:
        return "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:20_000]
    if isinstance(value, list):
        return [_bounded_value(item, depth + 1) for item in value[:50]]
    if isinstance(value, dict):
        return {
            _string(key, 100): _bounded_value(item, depth + 1)
            for key, item in list(value.items())[:50]
            if isinstance(key, str)
        }
    return _string(str(value), 2_000)


def _required_identifier(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 500
        or "\0" in value
    ):
        raise ValueError(f"{label} 无效。")
    return value.strip()


def _finite_int(value: object) -> int | None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        return None
    return int(value)


def _thread_summary(value: dict[str, object]) -> CodexThreadSummary | None:
    thread_id = value.get("id")
    if not isinstance(thread_id, str) or not thread_id:
        return None
    created_at = _finite_int(value.get("createdAt")) or 0
    updated_at = _finite_int(value.get("updatedAt"))
    raw_status = value.get("status")
    if isinstance(raw_status, str):
        status = raw_status
    elif isinstance(raw_status, dict) and isinstance(raw_status.get("type"), str):
        status = raw_status["type"]
    else:
        status = "unknown"
    return CodexThreadSummary(
        id=thread_id,
        name=_string(value.get("name"), 500),
        preview=_string(value.get("preview"), 4_000),
        cwd=_string(value.get("cwd"), 4_096),
        model_provider=_string(value.get("modelProvider"), 500),
        created_at=created_at,
        updated_at=updated_at if updated_at is not None else created_at,
        status=status,
    )


def _imported_history_path(thread_id: str, cwd: str) -> str:
    parent = posixpath.dirname(cwd.rstrip("/")) if cwd else ""
    directory = parent if parent not in {"", "/"} else "/tmp"
    digest = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()[:24]
    return posixpath.join(directory, f".agentkit-studio-history-{digest}.json")


def _imported_history_part_path(path: str, index: int) -> str:
    return f"{path}.part-{index + 1:02d}"


def _imported_history_read_paths(thread_id: str, cwd: str) -> tuple[str, ...]:
    """Cover both the original thread CWD and its selected project child."""
    digest = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()[:24]
    filename = f".agentkit-studio-history-{digest}.json"
    normalized = cwd.rstrip("/") if cwd else ""
    directories = (
        normalized if normalized not in {"", "/"} else "/tmp",
        posixpath.dirname(normalized) if normalized else "/tmp",
        "/tmp",
    )
    return tuple(
        posixpath.join(directory, filename)
        for index, directory in enumerate(directories)
        if directory not in {"", "/"} and directory not in directories[:index]
    )


def _imported_image(value: object) -> CodexImportedImage | None:
    if not isinstance(value, dict):
        return None
    mime_type = value.get("mime_type", value.get("mimeType"))
    data = value.get("data")
    name = value.get("name", "")
    alt = value.get("alt", "")
    if (
        mime_type not in _IMPORTED_HISTORY_IMAGE_MIME_TYPES
        or not isinstance(data, str)
        or not data
        or not isinstance(name, str)
        or not isinstance(alt, str)
        or len(name) > 255
        or len(alt) > 500
    ):
        return None
    return CodexImportedImage(
        mime_type=mime_type,
        data=data,
        name=name,
        alt=alt,
    )


def _imported_image_matches(image: CodexImportedImage, data: bytes) -> bool:
    if image.mime_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if image.mime_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if image.mime_type == "image/gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if image.mime_type == "image/webp":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    return False


def _prepend_imported_history(
    snapshot: CodexThreadSnapshot,
    imported: tuple[CodexImportedMessage, ...],
) -> CodexThreadSnapshot:
    if not imported:
        return snapshot
    existing = snapshot.messages[: len(imported)]
    if len(existing) == len(imported) and all(
        current.role == previous.role
        and current.content == previous.content
        and current.images == previous.images
        for current, previous in zip(existing, imported, strict=True)
    ):
        return snapshot
    first_timestamp = (
        snapshot.messages[0].timestamp
        if snapshot.messages
        else snapshot.thread.updated_at * 1_000
    )
    base_timestamp = max(0, first_timestamp - len(imported) - 1)
    imported_messages = tuple(
        CodexThreadMessage(
            id=f"imported-{snapshot.thread.id}-{index}",
            role=message.role,
            content=message.content,
            timestamp=base_timestamp + index,
            images=message.images,
        )
        for index, message in enumerate(imported)
    )
    return CodexThreadSnapshot(
        thread=snapshot.thread,
        messages=imported_messages + snapshot.messages,
        model=snapshot.model,
        cwd=snapshot.cwd,
        workspace_locked=snapshot.workspace_locked,
    )


def _thread_messages(
    value: object, fallback_seconds: int
) -> tuple[CodexThreadMessage, ...]:
    if not isinstance(value, list):
        return ()
    messages: list[CodexThreadMessage] = []
    sequence = 0
    for turn in value:
        if not isinstance(turn, dict) or not isinstance(turn.get("items"), list):
            continue
        started_at = _finite_int(turn.get("startedAt"))
        timestamp = (started_at if started_at is not None else fallback_seconds) * 1_000
        for item in turn["items"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            role: Literal["user", "assistant"] | None = None
            content = ""
            skill_names: tuple[str, ...] = ()
            if item.get("type") == "userMessage":
                role = "user"
                content, skill_names = _user_message_display(item.get("content"))
            elif item.get("type") == "agentMessage":
                role = "assistant"
                content = _string(item.get("text"), 100_000)
            if role is None or (not content and not skill_names):
                continue
            messages.append(
                CodexThreadMessage(
                    id=item["id"],
                    role=role,
                    content=content,
                    timestamp=timestamp + sequence,
                    skill_names=skill_names,
                )
            )
            sequence += 1
    return tuple(messages)


def _user_message_display(value: object) -> tuple[str, tuple[str, ...]]:
    if not isinstance(value, list):
        return "", ()
    skill_names: list[str] = []
    visible: list[str] = []
    mentions: list[str] = []
    for part in value:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "skill" and isinstance(part.get("name"), str) and part["name"]:
            if part["name"] not in skill_names:
                skill_names.append(part["name"])
        elif part_type == "text" and isinstance(part.get("text"), str):
            visible.append(part["text"])
        elif part_type == "localImage" and isinstance(part.get("path"), str):
            visible.append(f"[本地图片: {part['path']}]")
        elif part_type == "image":
            visible.append("[图片]")
        elif part_type == "mention" and isinstance(part.get("name"), str):
            mentions.append(f"@{part['name']}")
    content = "\n".join(visible) if visible else "\n".join(mentions)
    leading = _leading_skill_names(content, set(skill_names))
    for name in leading:
        marker = f"${name}"
        if content.startswith(marker):
            content = content[len(marker) :]
            if content and content[0].isspace():
                content = content.lstrip()
    return content, tuple(leading)


def _leading_skill_names(text: str, available_names: set[str]) -> list[str]:
    remaining = text
    names: list[str] = []
    while remaining:
        matched = _leading_skill_name(remaining, available_names)
        if matched is None:
            break
        if matched not in names:
            names.append(matched)
        remaining = remaining[len(matched) + 1 :]
        if not remaining or not remaining[0].isspace():
            break
        remaining = remaining.lstrip()
    return names


def _leading_skill_name(text: str, available_names: set[str]) -> str | None:
    matched: str | None = None
    for name in available_names:
        marker = f"${name}"
        if not text.startswith(marker):
            continue
        next_character = text[len(marker) : len(marker) + 1]
        if next_character and not (
            next_character.isspace() or next_character in ")]},.!?;:，。！？；："
        ):
            continue
        if matched is None or len(name) > len(matched):
            matched = name
    return matched


def _token_usage_update(
    params: dict[str, object],
) -> (
    tuple[
        str,
        str,
        CodexTokenUsage,
        CodexTokenUsage,
        int | None,
    ]
    | None
):
    thread_id = _field_string(params, "threadId", "thread_id")
    turn_id = _field_string(params, "turnId", "turn_id")
    token_usage = _field_dict(params, "tokenUsage", "token_usage")
    if not thread_id or not turn_id or token_usage is None:
        return None
    total = _usage_breakdown(_field_dict(token_usage, "total"))
    last = _usage_breakdown(_field_dict(token_usage, "last"))
    if total is None or last is None:
        return None
    context_window = _field_nonnegative_int(
        token_usage, "modelContextWindow", "model_context_window"
    )
    return thread_id, turn_id, total, last, context_window


def _usage_breakdown(value: dict[str, object] | None) -> CodexTokenUsage | None:
    if value is None:
        return None
    total_tokens = _field_nonnegative_int(value, "totalTokens", "total_tokens")
    if total_tokens is None:
        return None
    return CodexTokenUsage(
        total_tokens=total_tokens,
        input_tokens=_field_nonnegative_int(value, "inputTokens", "input_tokens") or 0,
        cached_input_tokens=_field_nonnegative_int(
            value, "cachedInputTokens", "cached_input_tokens"
        )
        or 0,
        output_tokens=_field_nonnegative_int(value, "outputTokens", "output_tokens")
        or 0,
        reasoning_output_tokens=_field_nonnegative_int(
            value, "reasoningOutputTokens", "reasoning_output_tokens"
        )
        or 0,
    )


def _field_string(value: dict[str, object], *keys: str) -> str:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return ""


def _field_dict(value: dict[str, object], *keys: str) -> dict[str, object] | None:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, dict):
            return candidate
    return None


def _field_nonnegative_int(value: dict[str, object], *keys: str) -> int | None:
    for key in keys:
        candidate = _finite_int(value.get(key))
        if candidate is not None and candidate >= 0:
            return candidate
    return None


def _add_usage(left: CodexTokenUsage, right: CodexTokenUsage) -> CodexTokenUsage:
    return CodexTokenUsage(
        total_tokens=left.total_tokens + right.total_tokens,
        input_tokens=left.input_tokens + right.input_tokens,
        cached_input_tokens=left.cached_input_tokens + right.cached_input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        reasoning_output_tokens=(
            left.reasoning_output_tokens + right.reasoning_output_tokens
        ),
    )


def _subtract_usage(
    current: CodexTokenUsage, previous: CodexTokenUsage
) -> CodexTokenUsage | None:
    current_values = current.public_dict().values()
    previous_values = previous.public_dict().values()
    if any(now < before for now, before in zip(current_values, previous_values)):
        return None
    return CodexTokenUsage(
        total_tokens=current.total_tokens - previous.total_tokens,
        input_tokens=current.input_tokens - previous.input_tokens,
        cached_input_tokens=(
            current.cached_input_tokens - previous.cached_input_tokens
        ),
        output_tokens=current.output_tokens - previous.output_tokens,
        reasoning_output_tokens=(
            current.reasoning_output_tokens - previous.reasoning_output_tokens
        ),
    )


__all__ = [
    "APPROVAL_DECISIONS",
    "CodexAppServerError",
    "CodexAppServerEvent",
    "CodexAppServerSession",
    "CodexApproval",
    "CodexDirectoryListing",
    "CodexImportedImage",
    "CodexImportedMessage",
    "CodexModel",
    "CodexPermissionSettings",
    "CodexSkill",
    "CodexThreadMessage",
    "CodexThreadSnapshot",
    "CodexThreadSummary",
    "CodexTokenUsage",
    "approval_decision_from_payload",
    "permission_settings_from_payload",
    "sandbox_service_url",
]
