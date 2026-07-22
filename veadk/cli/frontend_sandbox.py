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

"""Reusable AgentKit Sandbox access for temporary Studio conversations."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import re
import shlex
import time
import uuid

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from fastapi import Request

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

STUDIO_SANDBOX_TOOL_NAME = "veadk-studio-codex"
STUDIO_SANDBOX_TTL_SECONDS = 3_600
STUDIO_SANDBOX_MAX_ACTIVE = 20
_SANDBOX_CHAT_TOOL_ENV = "SANDBOX_CHAT_CODEX"
_CREATE_SESSION_START_FAIL_CODE = "ErrCreateSessionFail"
_SESSION_NOT_FOUND_CODE = "InvalidResource.NotFound"
_SENSITIVE_PATTERN = re.compile(
    r"(?i)((?:api[_-]?key|access[_-]?key|secret|token|authorization|password)"
    r"\s*[:=]\s*)(?:[\"'][^\"']*[\"']|[^\s,;]+)"
)


class SandboxError(RuntimeError):
    """Base error safe to translate at the HTTP boundary."""

    code = "SANDBOX_ERROR"
    retryable = False


class SandboxConfigurationError(SandboxError):
    """Required server-side Sandbox configuration is missing."""

    code = "SANDBOX_NOT_CONFIGURED"


class SandboxProvisioningError(SandboxError):
    """AgentKit could not provision the requested Sandbox resource."""

    code = "SANDBOX_PROVISIONING_FAILED"
    retryable = True


class SandboxSessionNotFoundError(SandboxError):
    """The temporary conversation does not exist or is not owned by the user."""

    code = "SANDBOX_SESSION_NOT_FOUND"


class SandboxInvocationError(SandboxError):
    """The coding agent failed while serving a conversation turn."""

    code = "SANDBOX_INVOCATION_FAILED"
    retryable = True


class SandboxCapacityError(SandboxError):
    """The user or Studio has reached the temporary-session limit."""

    code = "SANDBOX_CAPACITY_EXCEEDED"
    retryable = True


def _safe_error_message(error: object) -> str:
    """Return a bounded credential-safe diagnostic message."""
    message = str(error).strip()
    for key, value in os.environ.items():
        if (
            value
            and len(value) >= 8
            and any(
                token in key.upper() for token in ("KEY", "SECRET", "TOKEN", "PASSWORD")
            )
        ):
            message = message.replace(value, "***")
    message = re.sub(r"(?i)(\bbearer\s+)\S+", r"\1***", message)
    message = _SENSITIVE_PATTERN.sub(r"\1***", message)
    message = re.sub(r"https?://[^\s?]+\?[^\s]+", "[sandbox endpoint]", message)
    return message[:1000] or type(error).__name__


def _safe_public_value(value: object, depth: int = 0) -> object:
    """Return a bounded, credential-safe value for browser-visible events."""
    if depth >= 4:
        return "…"
    if isinstance(value, str):
        return _safe_error_message(value)
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in list(value.items())[:30]:
            safe_key = _safe_error_message(key)[:100]
            if any(
                marker in str(key).upper()
                for marker in ("KEY", "PASSWORD", "SECRET", "TOKEN", "AUTHORIZATION")
            ):
                result[safe_key] = "***"
            else:
                result[safe_key] = _safe_public_value(item, depth + 1)
        return result
    if isinstance(value, list):
        return [_safe_public_value(item, depth + 1) for item in value[:30]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_error_message(value)


def _public_event_text(value: object) -> str:
    """Extract readable text from a Codex event field."""
    if isinstance(value, str):
        return _safe_error_message(value)
    if isinstance(value, list):
        return "\n".join(filter(None, (_public_event_text(item) for item in value)))
    if isinstance(value, dict):
        return _public_event_text(
            value.get("text") or value.get("content") or value.get("summary")
        )
    return ""


@dataclass(frozen=True)
class SandboxCloudSession:
    """Remote AgentKit Sandbox session data kept only on the server."""

    tool_id: str
    instance_id: str
    user_session_id: str
    endpoint: str


@dataclass
class SandboxConversation:
    """Server-side state for one non-persistent Studio conversation."""

    session_id: str
    owner_id: str
    cloud: SandboxCloudSession
    thread_id: str | None = None
    expires_at: float = field(
        default_factory=lambda: time.monotonic() + STUDIO_SANDBOX_TTL_SECONDS
    )
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass(frozen=True)
class SandboxStreamEvent:
    """One typed event emitted while the coding agent is running."""

    kind: str = ""
    item_id: str = ""
    status: str = "done"
    text: str = ""
    name: str = ""
    arguments: object | None = None
    response: object | None = None
    thread_id: str | None = None


class SandboxCloudGateway(Protocol):
    """AgentKit operations needed by the Studio conversation service."""

    async def create_session(self, tool_id: str) -> SandboxCloudSession:
        """Create a fresh remote Sandbox session."""
        raise NotImplementedError

    async def delete_session(self, session: SandboxCloudSession) -> None:
        """Delete a remote Sandbox session."""
        raise NotImplementedError

    async def stream_codex(
        self,
        session: SandboxCloudSession,
        prompt: str,
        thread_id: str | None,
    ) -> AsyncIterator[SandboxStreamEvent]:
        """Stream one turn from the coding agent inside the Sandbox."""
        if False:
            yield SandboxStreamEvent()

    async def drain(self) -> None:
        """Wait for asynchronous cloud cleanup started by cancelled requests."""
        raise NotImplementedError


class AgentkitSandboxGateway:
    """AgentKit SDK and Sandbox terminal adapter.

    The AgentKit management SDK is synchronous, so each API call runs in a
    worker thread. Conversation output uses the Sandbox terminal WebSocket;
    the session endpoint, including its authorization query, never leaves this
    process.
    """

    def __init__(
        self,
        client: Any | Callable[[], Any],
    ) -> None:
        self._client = client
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _track_cleanup(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _call(self, method_name: str, request: Any) -> Any:
        client = self._client() if callable(self._client) else self._client
        method = getattr(client, method_name)
        return await asyncio.to_thread(method, request)

    async def _reconcile_created_session(
        self, tool_id: str, user_session_id: str
    ) -> SandboxCloudSession | None:
        from agentkit.sdk.tools import types as tools_types

        for attempt in range(6):
            response = await self._call(
                "list_sessions",
                tools_types.ListSessionsRequest(
                    ToolId=tool_id,
                    MaxResults=10,
                    Filters=[
                        tools_types.FiltersItemForListSessions(
                            Name="UserSessionId", Values=[user_session_id]
                        )
                    ],
                ),
            )
            for session in response.session_infos or []:
                if session.user_session_id != user_session_id:
                    continue
                if (session.status or "").lower() != "ready":
                    continue
                if session.session_id and session.endpoint:
                    return SandboxCloudSession(
                        tool_id=tool_id,
                        instance_id=session.session_id,
                        user_session_id=user_session_id,
                        endpoint=session.endpoint,
                    )
            if attempt < 5:
                await asyncio.sleep(5)
        return None

    async def create_session(self, tool_id: str) -> SandboxCloudSession:
        from agentkit.sdk.tools import types as tools_types

        user_session_id = f"studio-{uuid.uuid4()}"
        request = tools_types.CreateSessionRequest(
            ToolId=tool_id,
            Ttl=STUDIO_SANDBOX_TTL_SECONDS,
            TtlUnit="second",
            UserSessionId=user_session_id,
        )
        create_task = asyncio.create_task(self._call("create_session", request))
        try:
            response = await asyncio.shield(create_task)
        except asyncio.CancelledError:
            self._track_cleanup(
                self._cleanup_cancelled_create(
                    create_task, tool_id=tool_id, user_session_id=user_session_id
                )
            )
            raise
        except Exception as error:
            if _CREATE_SESSION_START_FAIL_CODE not in str(error):
                raise SandboxProvisioningError(
                    f"创建 AgentKit 沙箱会话失败：{_safe_error_message(error)}"
                ) from error
            reconciled = await self._reconcile_created_session(tool_id, user_session_id)
            if reconciled is not None:
                return reconciled
            raise SandboxProvisioningError(
                "AgentKit 返回会话启动失败，且未找到已就绪的会话。"
            ) from error

        instance_id = (response.session_id or "").strip()
        endpoint = (response.endpoint or "").strip()
        if not instance_id or not endpoint:
            raise SandboxProvisioningError(
                "AgentKit 创建会话响应缺少 SessionId 或 Endpoint。"
            )
        return SandboxCloudSession(
            tool_id=tool_id,
            instance_id=instance_id,
            user_session_id=response.user_session_id or user_session_id,
            endpoint=endpoint,
        )

    async def _cleanup_cancelled_create(
        self,
        create_task: asyncio.Task[Any],
        *,
        tool_id: str,
        user_session_id: str,
    ) -> None:
        """Delete a cloud session whose synchronous create outlived its request."""
        cloud: SandboxCloudSession | None = None
        try:
            response = await create_task
            if response.session_id and response.endpoint:
                cloud = SandboxCloudSession(
                    tool_id=tool_id,
                    instance_id=response.session_id,
                    user_session_id=response.user_session_id or user_session_id,
                    endpoint=response.endpoint,
                )
        except Exception as error:
            if _CREATE_SESSION_START_FAIL_CODE in str(error):
                cloud = await self._reconcile_created_session(tool_id, user_session_id)
            else:
                logger.warning(
                    "Cancelled Sandbox create failed before cleanup: %s",
                    _safe_error_message(error),
                )
        if cloud is not None:
            try:
                await self.delete_session(cloud)
            except SandboxError as error:
                logger.warning(
                    "Failed to clean up cancelled Sandbox create: %s",
                    _safe_error_message(error),
                )

    async def delete_session(self, session: SandboxCloudSession) -> None:
        from agentkit.sdk.tools import types as tools_types

        try:
            await self._call(
                "delete_session",
                tools_types.DeleteSessionRequest(
                    ToolId=session.tool_id,
                    SessionId=session.instance_id,
                ),
            )
        except Exception as error:
            if _SESSION_NOT_FOUND_CODE in str(error):
                return
            raise SandboxProvisioningError(
                f"删除 AgentKit 沙箱会话失败：{_safe_error_message(error)}"
            ) from error

    async def drain(self) -> None:
        if self._background_tasks:
            await asyncio.gather(*tuple(self._background_tasks), return_exceptions=True)

    @staticmethod
    def _terminal_url(endpoint: str) -> str:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SandboxProvisioningError("AgentKit 沙箱返回了无效 Endpoint。")
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = f"{parsed.path.rstrip('/')}/v1/shell/ws"
        return urlunsplit((scheme, parsed.netloc, path, parsed.query, ""))

    @staticmethod
    def _command(thread_id: str | None, input_marker: str, marker: str) -> str:
        stdin = (
            "python3 -c 'import base64,sys;"
            "sys.stdout.buffer.write(base64.b64decode(sys.stdin.buffer.readline()))'"
        )
        if thread_id:
            invocation = (
                "codex exec resume --json --dangerously-bypass-approvals-and-sandbox "
                f"{shlex.quote(thread_id)} -"
            )
        else:
            invocation = (
                "codex exec --json --color never --skip-git-repo-check "
                "--dangerously-bypass-approvals-and-sandbox -"
            )
        return (
            f"stty -echo; printf '\\n{input_marker}\\n'; "
            f"{stdin} | {invocation}; __veadk_status=$?; stty echo; "
            f"printf '\\n{marker}%s\\n' \"$__veadk_status\"; exit"
        )

    @staticmethod
    def _completion_status(line: str, marker: str) -> int | None:
        match = re.fullmatch(rf"{re.escape(marker)}(\d+)", line.strip())
        return int(match.group(1)) if match else None

    @staticmethod
    def _parse_codex_event(line: str) -> SandboxStreamEvent | None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict):
            return None
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                return SandboxStreamEvent(thread_id=thread_id)
            return None
        event_type = event.get("type")
        if event_type not in {"item.started", "item.completed"}:
            return None
        item = event.get("item")
        if not isinstance(item, dict):
            return None
        item_type = str(item.get("type") or "")
        item_id = str(item.get("id") or f"item-{uuid.uuid4().hex}")[:100]
        status = "running" if event_type == "item.started" else "done"

        if item_type == "reasoning":
            text = _public_event_text(
                item.get("text") or item.get("summary") or item.get("content")
            )
            return (
                SandboxStreamEvent(
                    kind="thinking",
                    item_id=item_id,
                    status=status,
                    text=text,
                )
                if text
                else None
            )
        if item_type == "agent_message":
            text = _public_event_text(item.get("text"))
            return SandboxStreamEvent(kind="text", text=text) if text else None
        if item_type == "command_execution":
            response = None
            if status == "done":
                response = {
                    "status": _safe_public_value(item.get("status") or "completed"),
                    "exitCode": _safe_public_value(item.get("exit_code")),
                    "output": _safe_public_value(item.get("aggregated_output")),
                }
            return SandboxStreamEvent(
                kind="tool",
                item_id=item_id,
                status=status,
                name="运行命令",
                arguments={"command": _safe_public_value(item.get("command") or "")},
                response=response,
            )
        if item_type in {"file_change", "file_changes"}:
            changes = item.get("changes")
            arguments = (
                {"changes": _safe_public_value(changes)}
                if isinstance(changes, list)
                else {"path": _safe_public_value(item.get("path") or "")}
            )
            return SandboxStreamEvent(
                kind="tool",
                item_id=item_id,
                status=status,
                name="修改文件",
                arguments=arguments,
                response={"status": _safe_public_value(item.get("status") or status)}
                if status == "done"
                else None,
            )
        if item_type == "mcp_tool_call":
            server = _safe_error_message(item.get("server") or "MCP")[:100]
            tool = _safe_error_message(item.get("tool") or item.get("name") or "工具")[
                :100
            ]
            return SandboxStreamEvent(
                kind="tool",
                item_id=item_id,
                status=status,
                name=f"MCP · {server}/{tool}",
                arguments=_safe_public_value(item.get("arguments")),
                response=_safe_public_value(item.get("result") or item.get("error"))
                if status == "done"
                else None,
            )
        if item_type in {"web_search", "web_search_call"}:
            return SandboxStreamEvent(
                kind="tool",
                item_id=item_id,
                status=status,
                name="网络搜索",
                arguments=_safe_public_value(
                    item.get("query") or item.get("arguments")
                ),
                response=_safe_public_value(item.get("result") or item.get("output"))
                if status == "done"
                else None,
            )
        text = _public_event_text(item.get("text") or item.get("summary"))
        return (
            SandboxStreamEvent(
                kind="thinking",
                item_id=item_id,
                status=status,
                text=text,
            )
            if text
            else None
        )

    async def stream_codex(
        self,
        session: SandboxCloudSession,
        prompt: str,
        thread_id: str | None,
    ) -> AsyncIterator[SandboxStreamEvent]:
        import websockets

        input_marker = f"__VEADK_INPUT_{uuid.uuid4().hex}__"
        marker = f"__VEADK_DONE_{uuid.uuid4().hex}__"
        command = self._command(thread_id, input_marker, marker)
        encoded_prompt = base64.b64encode(prompt.encode("utf-8")).decode("ascii")
        buffer = ""
        exit_status: int | None = None
        prompt_sent = False
        try:
            async with websockets.connect(
                self._terminal_url(session.endpoint),
                open_timeout=30,
                close_timeout=5,
                max_size=8 * 1024 * 1024,
            ) as websocket:
                await websocket.send(
                    json.dumps({"type": "resize", "data": {"cols": 120, "rows": 40}})
                )
                async with asyncio.timeout(30):
                    while True:
                        payload = json.loads(await websocket.recv())
                        if payload.get("type") == "ping":
                            await websocket.send(
                                json.dumps(
                                    {"type": "pong", "data": payload.get("data")}
                                )
                            )
                        if payload.get("type") == "ready":
                            await websocket.send(
                                json.dumps({"type": "input", "data": f"{command}\n"})
                            )
                            break

                try:
                    async with asyncio.timeout(600):
                        async for raw_message in websocket:
                            payload = json.loads(raw_message)
                            if payload.get("type") == "ping":
                                await websocket.send(
                                    json.dumps(
                                        {"type": "pong", "data": payload.get("data")}
                                    )
                                )
                                continue
                            if payload.get("type") == "error":
                                raise SandboxInvocationError(
                                    _safe_error_message(
                                        payload.get("data") or "terminal error"
                                    )
                                )
                            if payload.get("type") != "output":
                                continue
                            buffer += str(payload.get("data") or "")
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                if not prompt_sent and line.strip() == input_marker:
                                    await websocket.send(
                                        json.dumps(
                                            {
                                                "type": "input",
                                                "data": f"{encoded_prompt}\n",
                                            }
                                        )
                                    )
                                    prompt_sent = True
                                    continue
                                status = self._completion_status(line, marker)
                                if status is not None:
                                    exit_status = status
                                    break
                                event = self._parse_codex_event(line.strip())
                                if event is not None:
                                    yield event
                            if exit_status is not None:
                                break
                except asyncio.CancelledError:
                    await websocket.send(
                        json.dumps({"type": "input", "data": "\u0003exit\n"})
                    )
                    await websocket.close()
                    raise
        except asyncio.CancelledError:
            raise
        except TimeoutError as error:
            raise SandboxInvocationError("临时会话响应超时，请重试。") from error
        except SandboxError:
            raise
        except Exception as error:
            raise SandboxInvocationError(
                f"连接 AgentKit 沙箱失败：{_safe_error_message(error)}"
            ) from error
        if exit_status != 0:
            raise SandboxInvocationError(
                f"沙箱中的对话进程退出，状态码：{exit_status}。"
            )


class SandboxConversationService:
    """Own temporary conversation lifecycle and per-user isolation."""

    def __init__(
        self, gateway: SandboxCloudGateway, tool_id: str | None = None
    ) -> None:
        self._gateway = gateway
        self._configured_tool_id = (tool_id or "").strip()
        self._sessions: dict[str, SandboxConversation] = {}
        self._registry_lock = asyncio.Lock()
        self._sessions_starting = 0

    def capabilities(self) -> dict[str, object]:
        """Report whether the dedicated temporary-chat Tool is configured."""
        enabled = bool(self._tool_id(required=False))
        return {"enabled": enabled, "reason": "" if enabled else "管理员未配置"}

    def _tool_id(self, *, required: bool = True) -> str:
        tool_id = (
            self._configured_tool_id
            or (os.getenv(_SANDBOX_CHAT_TOOL_ENV) or "").strip()
        )
        if required and not tool_id:
            raise SandboxConfigurationError("管理员未配置")
        return tool_id

    async def start(self, owner_id: str) -> SandboxConversation:
        cloud: SandboxCloudSession | None = None
        tool_id = self._tool_id()
        await self.cleanup_expired()
        async with self._registry_lock:
            if len(self._sessions) + self._sessions_starting >= (
                STUDIO_SANDBOX_MAX_ACTIVE
            ):
                raise SandboxCapacityError("临时会话并发数已达上限，请稍后重试。")
            self._sessions_starting += 1
        try:
            cloud = await self._gateway.create_session(tool_id)
            session = SandboxConversation(
                session_id=str(uuid.uuid4()),
                owner_id=owner_id,
                cloud=cloud,
            )
            self._sessions[session.session_id] = session
            return session
        except asyncio.CancelledError:
            if cloud is not None:
                await asyncio.shield(self._gateway.delete_session(cloud))
            raise
        finally:
            async with self._registry_lock:
                self._sessions_starting -= 1

    def _owned(self, session_id: str, owner_id: str) -> SandboxConversation:
        session = self._sessions.get(session_id)
        if session is None or session.owner_id != owner_id:
            raise SandboxSessionNotFoundError("临时会话不存在或已过期。")
        return session

    def require_owned(self, session_id: str, owner_id: str) -> None:
        """Fail before an SSE response starts when a session is unavailable."""
        self._owned(session_id, owner_id)

    async def stream_message(
        self, session_id: str, owner_id: str, prompt: str
    ) -> AsyncIterator[SandboxStreamEvent]:
        session = self._owned(session_id, owner_id)
        async with session.lock:
            async for event in self._gateway.stream_codex(
                session.cloud, prompt, session.thread_id
            ):
                if event.thread_id:
                    session.thread_id = event.thread_id
                if event.kind:
                    yield event

    async def close(self, session_id: str, owner_id: str) -> None:
        session = self._owned(session_id, owner_id)
        async with session.lock:
            await self._gateway.delete_session(session.cloud)
            self._sessions.pop(session_id, None)

    async def cleanup_expired(self) -> None:
        """Delete sessions that exceeded their remote TTL."""
        now = time.monotonic()
        expired = [
            (session.session_id, session.owner_id)
            for session in self._sessions.values()
            if session.expires_at <= now
        ]
        for session_id, owner_id in expired:
            try:
                await self.close(session_id, owner_id)
            except SandboxError as error:
                logger.warning(
                    "Failed to clean up expired Sandbox session %s: %s",
                    session_id,
                    _safe_error_message(error),
                )

    async def close_all(self) -> None:
        """Best-effort process-shutdown cleanup for all cloud sessions."""
        sessions = [
            (session.session_id, session.owner_id)
            for session in self._sessions.values()
        ]
        for session_id, owner_id in sessions:
            try:
                await self.close(session_id, owner_id)
            except SandboxError as error:
                logger.warning(
                    "Failed to clean up Sandbox session %s at shutdown: %s",
                    session_id,
                    _safe_error_message(error),
                )
        await self._gateway.drain()


def mount_sandbox_routes(
    app: Any,
    service: SandboxConversationService,
    owner_resolver: Callable[[Any], str],
) -> None:
    """Mount thin Studio HTTP routes for temporary Sandbox conversations."""
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse

    def _http_error(error: SandboxError) -> HTTPException:
        status_code = 500
        if isinstance(error, SandboxConfigurationError):
            status_code = 503
        elif isinstance(error, SandboxSessionNotFoundError):
            status_code = 404
        elif isinstance(error, SandboxProvisioningError):
            status_code = 502
        elif isinstance(error, SandboxCapacityError):
            status_code = 409
        return HTTPException(
            status_code=status_code,
            detail={
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
            },
        )

    @app.get("/web/sandbox/capabilities")
    async def _sandbox_capabilities(request: Request) -> dict[str, object]:
        owner_resolver(request)
        return service.capabilities()

    @app.post("/web/sandbox/sessions")
    async def _start_sandbox_session(request: Request) -> dict[str, str]:
        try:
            session = await service.start(owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {
            "sessionId": session.session_id,
            "status": "ready",
            "toolName": STUDIO_SANDBOX_TOOL_NAME,
        }

    @app.post("/web/sandbox/sessions/{session_id}/messages")
    async def _send_sandbox_message(
        session_id: str, request: Request
    ) -> StreamingResponse:
        data = await request.json()
        prompt = data.get("message") if isinstance(data, dict) else None
        if not isinstance(prompt, str) or not prompt.strip():
            raise HTTPException(status_code=422, detail="message must not be empty")
        if len(prompt) > 100_000:
            raise HTTPException(status_code=413, detail="message is too large")
        owner_id = owner_resolver(request)
        try:
            service.require_owned(session_id, owner_id)
        except SandboxError as error:
            raise _http_error(error) from error

        async def _stream() -> AsyncIterator[str]:
            try:
                async for event in service.stream_message(
                    session_id, owner_id, prompt.strip()
                ):
                    if event.kind == "text":
                        payload = {"text": event.text}
                        yield f"event: delta\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        continue
                    payload = {
                        "id": event.item_id,
                        "kind": event.kind,
                        "status": event.status,
                        "text": event.text or None,
                        "name": event.name or None,
                        "args": event.arguments,
                        "response": event.response,
                    }
                    yield f"event: activity\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield "event: done\ndata: {}\n\n"
            except asyncio.CancelledError:
                try:
                    await asyncio.shield(service.close(session_id, owner_id))
                except SandboxError:
                    logger.warning(
                        "Failed to clean up cancelled Sandbox session %s", session_id
                    )
                raise
            except SandboxError as error:
                payload = {
                    "code": error.code,
                    "message": str(error),
                    "retryable": error.retryable,
                }
                yield (
                    f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                )
                yield 'event: done\ndata: {"reason": "failed"}\n\n'

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.delete("/web/sandbox/sessions/{session_id}")
    async def _delete_sandbox_session(
        session_id: str, request: Request
    ) -> dict[str, bool]:
        try:
            await service.close(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {"deleted": True}

    cleanup_task: asyncio.Task[None] | None = None

    async def _cleanup_loop() -> None:
        while True:
            await asyncio.sleep(60)
            await service.cleanup_expired()

    async def _start_cleanup() -> None:
        nonlocal cleanup_task
        cleanup_task = asyncio.create_task(_cleanup_loop())

    async def _stop_cleanup() -> None:
        if cleanup_task is not None:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
        await service.close_all()

    app.router.on_startup.append(_start_cleanup)
    app.router.on_shutdown.append(_stop_cleanup)
