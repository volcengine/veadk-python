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
import contextlib
import json
import math
import posixpath
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal
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
_MAX_DIRECTORY_ENTRIES = 1_000


class CodexAppServerError(RuntimeError):
    """The Sandbox Codex app-server rejected or interrupted an operation."""


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
        self._send_lock = asyncio.Lock()
        self._next_request_id = 1
        self._pending_requests: dict[int, asyncio.Future[dict[str, object]]] = {}
        self._turn_events: asyncio.Queue[CodexAppServerEvent] | None = None
        self._turn_completion: asyncio.Future[dict[str, object]] | None = None
        self._active_turn_id = ""
        self._pending_approvals: dict[str, asyncio.Future[ApprovalDecision]] = {}
        self._closed = False
        self._workspace_locked = False
        self._agent_message_delta_ids: set[str] = set()
        self._received_unidentified_agent_delta = False
        self.thread_id = ""
        self.cwd = ""
        self.permissions = CodexPermissionSettings()

    @property
    def active(self) -> bool:
        """Whether a turn is currently running."""
        return self._turn_completion is not None

    @property
    def workspace_locked(self) -> bool:
        """Whether the current thread already accepted its first turn."""
        return self._workspace_locked

    async def connect(self) -> None:
        """Connect, initialize the app-server, and create a fresh thread."""
        if self._websocket is not None:
            return
        if self._closed:
            raise CodexAppServerError("Codex app-server connection is closed.")
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
                    max_size=8 * 1024 * 1024,
                )
        except Exception as error:
            raise CodexAppServerError(
                "无法连接 AgentKit Session 中的 Codex 服务。"
            ) from error
        self._reader_task = asyncio.create_task(self._read_messages())
        try:
            await self.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "agentkit_codex_app_server_client",
                        "title": "VeADK Studio",
                        "version": "1",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            )
            await self.notify("initialized")
            snapshot = await self.request("thread/start", {})
            self._apply_thread_snapshot(snapshot)
        except Exception:
            await self.close()
            raise

    async def request(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        timeout: float = _REQUEST_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        """Send one JSON-RPC request and validate its object result."""
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
        await self._send(
            {
                "method": method,
                **({"params": params} if params is not None else {}),
            }
        )

    async def stream_turn(self, prompt: str) -> AsyncIterator[CodexAppServerEvent]:
        """Start one Codex turn and stream its public events."""
        if self.active:
            raise CodexAppServerError("当前 Codex 任务仍在运行。")
        if not self.thread_id:
            raise CodexAppServerError("Codex Thread 尚未初始化。")
        prompt = prompt.strip()
        if not prompt:
            raise CodexAppServerError("消息内容不能为空。")

        queue: asyncio.Queue[CodexAppServerEvent] = asyncio.Queue()
        completion: asyncio.Future[dict[str, object]] = (
            asyncio.get_running_loop().create_future()
        )
        self._turn_events = queue
        self._turn_completion = completion
        self._active_turn_id = ""
        self._agent_message_delta_ids.clear()
        self._received_unidentified_agent_delta = False
        try:
            result = await self.request(
                "turn/start",
                {
                    "threadId": self.thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    **_runtime_permission_params(self.permissions, self.cwd),
                },
            )
            turn = result.get("turn")
            if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
                raise CodexAppServerError("Codex turn/start 未返回有效的 Turn。")
            self._active_turn_id = turn["id"]
            self._workspace_locked = True

            try:
                deadline = asyncio.get_running_loop().time() + _TURN_TIMEOUT_SECONDS
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
                    else:
                        event_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await event_task
            except TimeoutError as error:
                await self.interrupt()
                raise CodexAppServerError("Codex 智能体响应超时，请重试。") from error

            turn_result = completion.result()
            status = str(turn_result.get("status") or "completed")
            if status.lower() in {"failed", "cancelled"}:
                error = turn_result.get("error")
                if isinstance(error, dict):
                    error = error.get("message")
                raise CodexAppServerError(str(error or f"Codex Turn 状态：{status}。"))
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
        if self._websocket is not None:
            with contextlib.suppress(Exception):
                await self._websocket.close()
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        self._websocket = None
        self._endpoint = ""

    async def _send(self, message: dict[str, object]) -> None:
        if self._websocket is None or self._closed:
            raise CodexAppServerError("Codex app-server 连接已关闭。")
        async with self._send_lock:
            try:
                await self._websocket.send(json.dumps(message, ensure_ascii=False))
            except Exception as error:
                raise CodexAppServerError(
                    "向 Codex app-server 发送请求失败。"
                ) from error

    async def _read_messages(self) -> None:
        failure: CodexAppServerError | None = None
        try:
            assert self._websocket is not None
            async for raw_message in self._websocket:
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
            failure = (
                error
                if isinstance(error, CodexAppServerError)
                else CodexAppServerError("Codex app-server 连接异常。")
            )
        else:
            if not self._closed:
                failure = CodexAppServerError("Codex app-server 连接已断开。")
        if failure is not None:
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(failure)
            if self._turn_completion is not None and not self._turn_completion.done():
                self._turn_completion.set_exception(failure)

    def _handle_response(self, message: dict[str, object]) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        future = self._pending_requests.get(request_id)
        if future is None or future.done():
            return
        error = message.get("error")
        if error is not None:
            if isinstance(error, dict):
                detail = str(error.get("message") or "未知错误")
            else:
                detail = str(error)
            future.set_exception(CodexAppServerError(detail))
            return
        result = message.get("result")
        if not isinstance(result, dict):
            future.set_exception(
                CodexAppServerError("Codex app-server 返回了无效结果。")
            )
            return
        future.set_result(result)

    def _handle_notification(self, method: str, params: dict[str, object]) -> None:
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
        thread = result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise CodexAppServerError("Codex thread/start 未返回有效的 Thread。")
        self.thread_id = thread["id"]
        cwd = result.get("cwd")
        if not isinstance(cwd, str):
            cwd = thread.get("cwd")
        if isinstance(cwd, str) and cwd:
            self.cwd = cwd
        turns = thread.get("turns")
        self._workspace_locked = isinstance(turns, list) and bool(turns)
        self._apply_runtime_settings(result)

    def _apply_runtime_settings(self, value: dict[str, object]) -> None:
        approval_policy = value.get("approvalPolicy")
        approvals_reviewer = value.get("approvalsReviewer")
        sandbox = value.get("sandbox") or value.get("sandboxPolicy")
        sandbox_mode, network_access = _sandbox_settings(sandbox)
        self.permissions = CodexPermissionSettings(
            approval_policy=(
                approval_policy
                if approval_policy in APPROVAL_POLICIES
                else self.permissions.approval_policy
            ),
            approvals_reviewer=(
                approvals_reviewer
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
        approval_policy=approval_policy,
        approvals_reviewer=approvals_reviewer,
        sandbox_mode=sandbox_mode,
        network_access=(
            True if sandbox_mode == "danger-full-access" else network_access
        ),
    )


def approval_decision_from_payload(value: object) -> ApprovalDecision:
    """Validate one browser approval decision."""
    if not isinstance(value, str) or value not in APPROVAL_DECISIONS:
        raise ValueError("审批决定无效。")
    return value


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
        return value, None
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
                kind="thinking",
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


__all__ = [
    "APPROVAL_DECISIONS",
    "CodexAppServerError",
    "CodexAppServerEvent",
    "CodexAppServerSession",
    "CodexApproval",
    "CodexDirectoryListing",
    "CodexPermissionSettings",
    "approval_decision_from_payload",
    "permission_settings_from_payload",
    "sandbox_service_url",
]
