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
import secrets
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
STUDIO_SANDBOX_PROJECT_NAME = "default"
STUDIO_SANDBOX_TOOL_TYPE = "CodeEnv"
STUDIO_SANDBOX_TTL_SECONDS = 3_600
STUDIO_SANDBOX_MAX_ACTIVE = 20
_READY_TOOL_STATUS = "Ready"
_FAILED_TOOL_STATUSES = frozenset(
    {"Error", "Failed", "CreateFailed", "Deleting", "Deleted"}
)
_CREATE_SESSION_START_FAIL_CODE = "ErrCreateSessionFail"
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

    text: str = ""
    thread_id: str | None = None


class SandboxCloudGateway(Protocol):
    """AgentKit operations needed by the Studio conversation service."""

    async def ensure_studio_tool(self) -> str:
        """Find or create the Studio-owned Sandbox tool."""
        raise NotImplementedError

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
        *,
        tool_ready_timeout: float = 600.0,
        poll_interval: float = 5.0,
    ) -> None:
        self._client = client
        self._tool_ready_timeout = tool_ready_timeout
        self._poll_interval = poll_interval
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _track_cleanup(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _call(self, method_name: str, request: Any) -> Any:
        client = self._client() if callable(self._client) else self._client
        method = getattr(client, method_name)
        return await asyncio.to_thread(method, request)

    async def _list_studio_tools(self) -> list[Any]:
        from agentkit.sdk.tools import types as tools_types

        tools: list[Any] = []
        next_token: str | None = None
        while True:
            response = await self._call(
                "list_tools",
                tools_types.ListToolsRequest(
                    ProjectName=STUDIO_SANDBOX_PROJECT_NAME,
                    MaxResults=100,
                    NextToken=next_token,
                    Filters=[
                        tools_types.FiltersItemForListTools(
                            Name="Name",
                            Values=[STUDIO_SANDBOX_TOOL_NAME],
                        )
                    ],
                ),
            )
            tools.extend(response.tools or [])
            next_token = response.next_token or None
            if not next_token:
                return [
                    tool
                    for tool in tools
                    if tool.name == STUDIO_SANDBOX_TOOL_NAME
                    and tool.project_name == STUDIO_SANDBOX_PROJECT_NAME
                    and tool.tool_type == STUDIO_SANDBOX_TOOL_TYPE
                ]

    def _model_configuration(self) -> tuple[str, str, str | None, str | None]:
        api_key = (os.getenv("MODEL_AGENT_API_KEY") or "").strip()
        model_name = (os.getenv("MODEL_AGENT_NAME") or "").strip()
        base_url = (os.getenv("MODEL_AGENT_API_BASE") or "").strip() or None
        provider = (os.getenv("AGENTKIT_SANDBOX_MODEL_PROVIDER") or "").strip() or None
        if not api_key or not model_name:
            raise SandboxConfigurationError(
                "临时会话需要在 Studio 服务端配置 MODEL_AGENT_API_KEY 和 "
                "MODEL_AGENT_NAME。"
            )
        return api_key, model_name, base_url, provider

    def _tool_envs(self) -> list[Any]:
        from agentkit.toolkit.cli.sandbox.env_config import build_create_tool_envs

        api_key, model_name, base_url, provider = self._model_configuration()
        return (
            build_create_tool_envs(
                tool_type=STUDIO_SANDBOX_TOOL_TYPE,
                model_name=model_name,
                model_api_key=api_key,
                model_provider=provider,
                model_base_url=base_url,
                model_provider_was_provided=provider is not None,
                model_base_url_was_provided=base_url is not None,
            )
            or []
        )

    def _session_envs(self) -> list[Any]:
        from agentkit.toolkit.cli.sandbox.env_config import build_exec_session_envs

        api_key, model_name, base_url, provider = self._model_configuration()
        return (
            build_exec_session_envs(
                model_name=model_name,
                model_api_key=api_key,
                model_provider=provider,
                model_base_url=base_url,
                model_provider_was_provided=provider is not None,
                model_base_url_was_provided=base_url is not None,
                include_codex_config=True,
            )
            or []
        )

    async def _wait_for_tool(self, tool_id: str) -> None:
        from agentkit.sdk.tools import types as tools_types

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._tool_ready_timeout
        while True:
            tool = await self._call(
                "get_tool", tools_types.GetToolRequest(ToolId=tool_id)
            )
            status = (tool.status or "").strip()
            if status == _READY_TOOL_STATUS:
                return
            if status in _FAILED_TOOL_STATUSES:
                raise SandboxProvisioningError(
                    f"AgentKit 沙箱创建失败，当前状态：{status}。"
                )
            if loop.time() >= deadline:
                raise SandboxProvisioningError("等待 AgentKit 沙箱就绪超时。")
            await asyncio.sleep(self._poll_interval)

    async def ensure_studio_tool(self) -> str:
        from agentkit.sdk.tools import types as tools_types

        try:
            tools = await self._list_studio_tools()
            if len(tools) > 1:
                raise SandboxProvisioningError(
                    "检测到多个 Studio 临时会话沙箱，请删除重复资源后重试。"
                )
            if tools:
                tool_id = (tools[0].tool_id or "").strip()
                if not tool_id:
                    raise SandboxProvisioningError("AgentKit 工具响应缺少 ToolId。")
                await self._wait_for_tool(tool_id)
                return tool_id

            response = await self._call(
                "create_tool",
                tools_types.CreateToolRequest(
                    Name=STUDIO_SANDBOX_TOOL_NAME,
                    ToolType=STUDIO_SANDBOX_TOOL_TYPE,
                    ProjectName=STUDIO_SANDBOX_PROJECT_NAME,
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
                    Envs=self._tool_envs(),
                ),
            )
            tool_id = (response.tool_id or "").strip()
            if not tool_id:
                raise SandboxProvisioningError("AgentKit 创建工具响应缺少 ToolId。")
            await self._wait_for_tool(tool_id)
            return tool_id
        except SandboxError:
            raise
        except Exception as error:
            raise SandboxProvisioningError(
                f"访问 AgentKit 工具服务失败：{_safe_error_message(error)}"
            ) from error

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
            Envs=self._session_envs(),
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
        if event.get("type") != "item.completed":
            return None
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            return None
        text = item.get("text")
        return SandboxStreamEvent(text=text) if isinstance(text, str) and text else None

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

    def __init__(self, gateway: SandboxCloudGateway) -> None:
        self._gateway = gateway
        self._sessions: dict[str, SandboxConversation] = {}
        self._provision_lock = asyncio.Lock()
        self._registry_lock = asyncio.Lock()
        self._sessions_starting = 0

    async def start(self, owner_id: str) -> SandboxConversation:
        cloud: SandboxCloudSession | None = None
        await self.cleanup_expired()
        async with self._registry_lock:
            if len(self._sessions) + self._sessions_starting >= (
                STUDIO_SANDBOX_MAX_ACTIVE
            ):
                raise SandboxCapacityError("临时会话并发数已达上限，请稍后重试。")
            self._sessions_starting += 1
        try:
            async with self._provision_lock:
                tool_id = await self._gateway.ensure_studio_tool()
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
    ) -> AsyncIterator[str]:
        session = self._owned(session_id, owner_id)
        async with session.lock:
            async for event in self._gateway.stream_codex(
                session.cloud, prompt, session.thread_id
            ):
                if event.thread_id:
                    session.thread_id = event.thread_id
                if event.text:
                    yield event.text

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
                async for text in service.stream_message(
                    session_id, owner_id, prompt.strip()
                ):
                    yield f"event: delta\ndata: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
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
