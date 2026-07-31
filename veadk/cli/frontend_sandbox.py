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

"""Reusable AgentKit Sandbox Sessions for Studio Codex agents."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Protocol

from fastapi import File, Request, UploadFile

from veadk.cli.agentkit_sandbox_region import is_agentkit_resource_not_found
from veadk.cli.agentkit_session_metadata import (
    SESSION_DISPLAY_NAME_MAX_LENGTH,
    build_create_session_request,
    call_session_client,
    session_display_name,
)
from veadk.cli.codex_app_server import (
    ApprovalDecision,
    CodexAppServerError,
    CodexAppServerEvent,
    CodexAppServerSession,
    CodexDirectoryListing,
    CodexModel,
    CodexPermissionSettings,
    CodexSkill,
    CodexThreadSnapshot,
    CodexThreadSummary,
    CodexTokenUsage,
    approval_decision_from_payload,
    permission_settings_from_payload,
)
from veadk.cli.frontend_sandbox_proxy import (
    SANDBOX_UPLOAD_MAX_BYTES,
    SandboxProxyTarget,
    browser_launch_url,
    mount_sandbox_proxy_routes,
    proxy_cookie_name,
    proxy_prefix,
    terminal_launch_url,
    upload_sandbox_file,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

STUDIO_SANDBOX_TOOL_NAME = "veadk-studio-codex"
STUDIO_SANDBOX_TTL_SECONDS = 28_800
STUDIO_SANDBOX_MAX_ACTIVE = 20
STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH = SESSION_DISPLAY_NAME_MAX_LENGTH
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


class SandboxValidationError(SandboxError):
    """A Studio Sandbox request did not satisfy the public contract."""

    code = "SANDBOX_INVALID_REQUEST"


class SandboxProvisioningError(SandboxError):
    """AgentKit could not provision the requested Sandbox resource."""

    code = "SANDBOX_PROVISIONING_FAILED"
    retryable = True


class SandboxSessionNotFoundError(SandboxError):
    """The cloud Session or local conversation connection is unavailable."""

    code = "SANDBOX_SESSION_NOT_FOUND"


class SandboxSessionUnavailableError(SandboxError):
    """The cloud Session exists but cannot accept a conversation yet."""

    code = "SANDBOX_SESSION_UNAVAILABLE"
    retryable = True


class SandboxInvocationError(SandboxError):
    """The coding agent failed while serving a conversation turn."""

    code = "SANDBOX_INVOCATION_FAILED"
    retryable = True


class SandboxCapacityError(SandboxError):
    """Studio has reached its local conversation-bridge limit."""

    code = "SANDBOX_CAPACITY_EXCEEDED"
    retryable = True


def _safe_error_message(error: object) -> str:
    """Return a bounded credential-safe diagnostic message."""
    message = _redact_public_text(str(error).strip(), maximum=1_000)
    return message or type(error).__name__


def _redact_public_text(value: str, *, maximum: int) -> str:
    """Redact credentials from browser-visible text without inventing content."""
    message = value
    for key, env_value in os.environ.items():
        if (
            env_value
            and len(env_value) >= 8
            and any(
                token in key.upper() for token in ("KEY", "SECRET", "TOKEN", "PASSWORD")
            )
        ):
            message = message.replace(env_value, "***")
    message = re.sub(r"(?i)(\bbearer\s+)\S+", r"\1***", message)
    message = _SENSITIVE_PATTERN.sub(r"\1***", message)
    message = re.sub(r"https?://[^\s?]+\?[^\s]+", "[sandbox endpoint]", message)
    return message[:maximum]


def _safe_public_value(value: object, depth: int = 0) -> object:
    """Return a bounded, credential-safe value for browser-visible events."""
    if depth > 4:
        return "…"
    if isinstance(value, str):
        return _redact_public_text(value, maximum=20_000)
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in list(value.items())[:30]:
            safe_key = _redact_public_text(key, maximum=100)
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
        return _redact_public_text(value, maximum=100_000)
    if isinstance(value, list):
        return "\n".join(filter(None, (_public_event_text(item) for item in value)))
    if isinstance(value, dict):
        return _public_event_text(
            value.get("text") or value.get("content") or value.get("summary")
        )
    return ""


@dataclass(frozen=True)
class SandboxCloudSession:
    """Remote AgentKit Sandbox Session data kept only on the server."""

    tool_id: str
    instance_id: str
    user_session_id: str
    endpoint: str
    region: str = ""
    status: str = "Unknown"
    created_at: str = ""
    expire_at: str = ""
    tool_type: str = ""
    display_name: str = ""


@dataclass
class SandboxConversation:
    """Server-side connection state for one reusable cloud Session."""

    session_id: str
    owner_id: str
    cloud: SandboxCloudSession
    codex: SandboxCodexConnection
    proxy_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
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
    approval: object | None = None
    approval_resolved_id: str = ""
    turn_id: str = ""
    usage: CodexTokenUsage | None = None
    thread_total: CodexTokenUsage | None = None
    model_context_window: int | None = None


class SandboxCodexConnection(Protocol):
    """Persistent Codex app-server connection owned by one Studio session."""

    thread_id: str
    cwd: str
    model: str
    permissions: CodexPermissionSettings

    @property
    def active(self) -> bool:
        """Whether a turn is currently running."""
        raise NotImplementedError

    @property
    def workspace_locked(self) -> bool:
        """Whether the first turn has already started."""
        raise NotImplementedError

    async def stream_turn(
        self, prompt: str, skill_ids: tuple[str, ...] = ()
    ) -> AsyncIterator[CodexAppServerEvent]:
        """Run and stream one turn."""
        if False:
            yield CodexAppServerEvent()

    @property
    def thread_token_total(self) -> CodexTokenUsage | None:
        """Latest cumulative token usage for the active thread."""
        raise NotImplementedError

    @property
    def model_context_window(self) -> int | None:
        """Current model context window when reported by app-server."""
        raise NotImplementedError

    async def list_models(self) -> tuple[CodexModel, ...]:
        """List visible Codex models."""
        raise NotImplementedError

    async def set_model(self, model: str) -> str:
        """Change the active thread model."""
        raise NotImplementedError

    async def list_skills(self, force_reload: bool = False) -> tuple[CodexSkill, ...]:
        """List browser-safe Skills."""
        raise NotImplementedError

    async def new_thread(self) -> CodexThreadSnapshot:
        """Start a fresh thread."""
        raise NotImplementedError

    async def list_threads(
        self,
        *,
        cursor: str = "",
        search_term: str = "",
        archived: bool = False,
    ) -> tuple[tuple[CodexThreadSummary, ...], str]:
        """List recent threads."""
        raise NotImplementedError

    async def resume_thread(self, thread_id: str) -> CodexThreadSnapshot:
        """Resume an existing thread."""
        raise NotImplementedError

    async def fork_thread(self) -> CodexThreadSnapshot:
        """Fork the active thread."""
        raise NotImplementedError

    async def archive_thread(self, thread_id: str) -> CodexThreadSnapshot | None:
        """Archive one thread."""
        raise NotImplementedError

    async def compact_thread(self) -> None:
        """Compact the active thread."""
        raise NotImplementedError

    async def update_permissions(
        self, settings: CodexPermissionSettings
    ) -> CodexPermissionSettings:
        """Persist and hot-apply Session permissions."""
        raise NotImplementedError

    async def apply_session_permissions(
        self, settings: CodexPermissionSettings
    ) -> None:
        """Adopt permissions persisted by another thread."""
        raise NotImplementedError

    async def update_workspace(self, cwd: str) -> str:
        """Update the CWD before the first turn."""
        raise NotImplementedError

    async def list_directories(self, path: str) -> CodexDirectoryListing:
        """List remote directories."""
        raise NotImplementedError

    def resolve_approval(self, approval_id: str, decision: ApprovalDecision) -> None:
        """Resolve one pending user approval."""
        raise NotImplementedError

    async def close(self) -> None:
        """Close the persistent connection."""
        raise NotImplementedError


class SandboxCloudGateway(Protocol):
    """AgentKit operations needed by the Studio Session service."""

    async def list_sessions(self, tool_id: str) -> list[SandboxCloudSession]:
        """List every Session belonging to the configured Tool."""
        raise NotImplementedError

    async def get_session(self, tool_id: str, session_id: str) -> SandboxCloudSession:
        """Resolve one existing Session and its private Endpoint."""
        raise NotImplementedError

    async def create_session(
        self, tool_id: str, display_name: str = ""
    ) -> SandboxCloudSession:
        """Create a fresh remote Sandbox session."""
        raise NotImplementedError

    async def delete_session(self, session: SandboxCloudSession) -> None:
        """Delete a remote Sandbox session."""
        raise NotImplementedError

    async def open_codex(self, session: SandboxCloudSession) -> SandboxCodexConnection:
        """Open one persistent Codex app-server connection."""
        raise NotImplementedError

    async def drain(self) -> None:
        """Wait for asynchronous cloud cleanup started by cancelled requests."""
        raise NotImplementedError


class AgentkitSandboxGateway:
    """AgentKit SDK and persistent Codex app-server adapter.

    The AgentKit management SDK is synchronous, so each API call runs in a
    worker thread. Conversation output uses the Sandbox app-server WebSocket;
    the Session Endpoint, including its authorization query, never leaves this
    process.
    """

    def __init__(
        self,
        client: Any | Callable[..., Any],
        *,
        region_candidates: tuple[str, ...] = (),
    ) -> None:
        self._client = client
        self._region_candidates = region_candidates
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _track_cleanup(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _call(self, method_name: str, request: Any, *, region: str = "") -> Any:
        if callable(self._client):
            client = self._client(region) if self._region_candidates else self._client()
        else:
            client = self._client
        return await asyncio.to_thread(
            call_session_client,
            client,
            method_name,
            request,
        )

    async def _reconcile_created_session(
        self, tool_id: str, user_session_id: str, region: str = ""
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
                region=region,
            )
            for session in response.session_infos or []:
                if session.user_session_id != user_session_id:
                    continue
                if (session.status or "").lower() != "ready":
                    continue
                if session.session_id and session.endpoint:
                    return self._cloud_session(
                        tool_id,
                        session,
                        region=region,
                        fallback_user_session_id=user_session_id,
                    )
            if attempt < 5:
                await asyncio.sleep(5)
        return None

    @staticmethod
    def _cloud_session(
        tool_id: str,
        value: Any,
        *,
        region: str = "",
        fallback_user_session_id: str = "",
    ) -> SandboxCloudSession:
        instance_id = str(getattr(value, "session_id", "") or "").strip()
        if not instance_id:
            raise SandboxProvisioningError("AgentKit Session 响应缺少 SessionId。")
        return SandboxCloudSession(
            tool_id=tool_id,
            instance_id=instance_id,
            user_session_id=str(
                getattr(value, "user_session_id", "") or fallback_user_session_id
            ).strip(),
            endpoint=str(getattr(value, "endpoint", "") or "").strip(),
            region=region,
            status=str(getattr(value, "status", "") or "Unknown").strip(),
            created_at=str(getattr(value, "created_at", "") or "").strip(),
            expire_at=str(getattr(value, "expire_at", "") or "").strip(),
            tool_type=str(getattr(value, "tool_type", "") or "").strip(),
            display_name=session_display_name(value),
        )

    async def list_sessions(self, tool_id: str) -> list[SandboxCloudSession]:
        from agentkit.sdk.tools import types as tools_types

        regions = self._region_candidates or ("",)
        for index, region in enumerate(regions):
            sessions: dict[str, SandboxCloudSession] = {}
            next_token: str | None = None
            seen_tokens: set[str] = set()
            try:
                for _page in range(100):
                    response = await self._call(
                        "list_sessions",
                        tools_types.ListSessionsRequest(
                            ToolId=tool_id,
                            MaxResults=100,
                            NextToken=next_token,
                        ),
                        region=region,
                    )
                    for value in response.session_infos or []:
                        session = self._cloud_session(
                            tool_id,
                            value,
                            region=region,
                        )
                        sessions[session.instance_id] = session
                    next_token = str(response.next_token or "").strip() or None
                    if next_token is None:
                        return sorted(
                            sessions.values(),
                            key=lambda item: item.created_at,
                            reverse=True,
                        )
                    if next_token in seen_tokens:
                        raise SandboxProvisioningError(
                            "AgentKit ListSessions 返回了重复的 NextToken。"
                        )
                    seen_tokens.add(next_token)
                raise SandboxProvisioningError(
                    "AgentKit ListSessions 分页超过安全上限。"
                )
            except SandboxError:
                raise
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(regions):
                    continue
                raise SandboxProvisioningError(
                    f"读取 AgentKit Session 失败：{_safe_error_message(error)}"
                ) from error
        raise SandboxProvisioningError("无法在支持的地域读取 AgentKit Session。")

    async def get_session(self, tool_id: str, session_id: str) -> SandboxCloudSession:
        from agentkit.sdk.tools import types as tools_types

        regions = self._region_candidates or ("",)
        for index, region in enumerate(regions):
            try:
                response = await self._call(
                    "get_session",
                    tools_types.GetSessionRequest(
                        ToolId=tool_id,
                        SessionId=session_id,
                    ),
                    region=region,
                )
                return self._cloud_session(tool_id, response, region=region)
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(regions):
                    continue
                if is_agentkit_resource_not_found(error):
                    raise SandboxSessionNotFoundError(
                        "AgentKit Session 不存在或已过期。"
                    ) from error
                raise SandboxProvisioningError(
                    f"读取 AgentKit Session 失败：{_safe_error_message(error)}"
                ) from error
        raise SandboxSessionNotFoundError("AgentKit Session 不存在或已过期。")

    async def create_session(
        self, tool_id: str, display_name: str = ""
    ) -> SandboxCloudSession:
        user_session_id = f"studio-{uuid.uuid4()}"
        regions = self._region_candidates or ("",)
        for index, region in enumerate(regions):
            request = build_create_session_request(
                tool_id=tool_id,
                ttl_seconds=STUDIO_SANDBOX_TTL_SECONDS,
                user_session_id=user_session_id,
                display_name=display_name,
            )
            create_task = asyncio.create_task(
                self._call("create_session", request, region=region)
            )
            try:
                response = await asyncio.shield(create_task)
            except asyncio.CancelledError:
                self._track_cleanup(
                    self._cleanup_cancelled_create(
                        create_task,
                        tool_id=tool_id,
                        user_session_id=user_session_id,
                        region=region,
                    )
                )
                raise
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(regions):
                    continue
                if _CREATE_SESSION_START_FAIL_CODE not in str(error):
                    raise SandboxProvisioningError(
                        f"创建 AgentKit 沙箱会话失败：{_safe_error_message(error)}"
                    ) from error
                reconciled = await self._reconcile_created_session(
                    tool_id, user_session_id, region
                )
                if reconciled is not None:
                    return reconciled
                raise SandboxProvisioningError(
                    "AgentKit 返回会话启动失败，且未找到已就绪的会话。"
                ) from error

            instance_id = (response.session_id or "").strip()
            endpoint = (response.endpoint or "").strip()
            if not instance_id:
                raise SandboxProvisioningError("AgentKit 创建会话响应缺少 SessionId。")
            return SandboxCloudSession(
                tool_id=tool_id,
                instance_id=instance_id,
                user_session_id=response.user_session_id or user_session_id,
                endpoint=endpoint,
                region=region,
                status="Ready" if endpoint else "Creating",
                display_name=display_name,
            )
        raise SandboxProvisioningError("无法在支持的地域创建 AgentKit 沙箱会话。")

    async def _cleanup_cancelled_create(
        self,
        create_task: asyncio.Task[Any],
        *,
        tool_id: str,
        user_session_id: str,
        region: str = "",
    ) -> None:
        """Delete a cloud session whose synchronous create outlived its request."""
        cloud: SandboxCloudSession | None = None
        try:
            response = await create_task
            if response.session_id:
                cloud = SandboxCloudSession(
                    tool_id=tool_id,
                    instance_id=response.session_id,
                    user_session_id=response.user_session_id or user_session_id,
                    endpoint=response.endpoint or "",
                    region=region,
                    status="Ready" if response.endpoint else "Creating",
                )
        except Exception as error:  # noqa: BLE001 - cleanup boundary
            if _CREATE_SESSION_START_FAIL_CODE in str(error):
                cloud = await self._reconcile_created_session(
                    tool_id, user_session_id, region
                )
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
                region=session.region,
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

    async def open_codex(self, session: SandboxCloudSession) -> SandboxCodexConnection:
        """Connect to Codex without exposing the private Session Endpoint."""
        connection = CodexAppServerSession(session.endpoint)
        try:
            await connection.connect()
        except CodexAppServerError as error:
            await connection.close()
            raise SandboxInvocationError(
                f"连接 AgentKit 沙箱失败：{_safe_error_message(error)}"
            ) from error
        return connection


class SandboxConversationService:
    """Manage reusable cloud Sessions and per-user conversation connections."""

    def __init__(
        self, gateway: SandboxCloudGateway, tool_id: str | None = None
    ) -> None:
        self._gateway = gateway
        self._configured_tool_id = (tool_id or "").strip()
        self._sessions: dict[tuple[str, str], SandboxConversation] = {}
        self._registry_lock = asyncio.Lock()
        self._sessions_starting = 0

    def capabilities(self) -> dict[str, object]:
        """Report whether the dedicated Codex Tool is configured."""
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

    async def list_sessions(self, owner_id: str) -> list[SandboxCloudSession]:
        """List the configured account's Sessions without exposing Endpoints."""
        del owner_id
        return await self._gateway.list_sessions(self._tool_id())

    async def create(
        self, owner_id: str, display_name: object = ""
    ) -> SandboxCloudSession:
        """Create a cloud Session without opening a conversation connection."""
        del owner_id
        if not isinstance(display_name, str):
            raise SandboxValidationError("智能体名称必须是文本。")
        display_name = display_name.strip()
        if len(display_name) > STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH:
            raise SandboxValidationError(
                f"智能体名称不能超过 {STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH} 个字符。"
            )
        tool_id = self._tool_id()
        await self.cleanup_expired()
        async with self._registry_lock:
            if len(self._sessions) + self._sessions_starting >= (
                STUDIO_SANDBOX_MAX_ACTIVE
            ):
                raise SandboxCapacityError("Sandbox 创建或连接数已达上限，请稍后重试。")
            self._sessions_starting += 1
        try:
            return await self._gateway.create_session(tool_id, display_name)
        finally:
            async with self._registry_lock:
                self._sessions_starting -= 1

    async def connect(self, session_id: str, owner_id: str) -> SandboxConversation:
        """Attach an existing Ready cloud Session to the conversation bridge."""
        key = (owner_id, session_id)
        existing = self._sessions.get(key)
        if existing is not None:
            return existing
        await self.cleanup_expired()
        async with self._registry_lock:
            existing = self._sessions.get(key)
            if existing is not None:
                return existing
            if len(self._sessions) + self._sessions_starting >= (
                STUDIO_SANDBOX_MAX_ACTIVE
            ):
                raise SandboxCapacityError("智能体连接数已达上限，请稍后重试。")
            self._sessions_starting += 1
        try:
            cloud = await self._gateway.get_session(self._tool_id(), session_id)
            if cloud.status.lower() != "ready" or not cloud.endpoint:
                status = cloud.status or "Unknown"
                raise SandboxSessionUnavailableError(
                    f"AgentKit Session 尚未就绪，当前状态：{status}。"
                )
            codex = await self._gateway.open_codex(cloud)
            conversation = SandboxConversation(
                session_id=cloud.instance_id,
                owner_id=owner_id,
                cloud=cloud,
                codex=codex,
            )
            async with self._registry_lock:
                existing = self._sessions.get(key)
                if existing is not None:
                    await codex.close()
                    return existing
                self._sessions[key] = conversation
                return conversation
        finally:
            async with self._registry_lock:
                self._sessions_starting -= 1

    def _owned(self, session_id: str, owner_id: str) -> SandboxConversation:
        session = self._sessions.get((owner_id, session_id))
        if session is None:
            raise SandboxSessionNotFoundError("智能体尚未连接，请返回列表后重新进入。")
        return session

    def require_owned(self, session_id: str, owner_id: str) -> None:
        """Fail before an SSE response starts when a session is unavailable."""
        self._owned(session_id, owner_id)

    async def stream_message(
        self,
        session_id: str,
        owner_id: str,
        prompt: str,
        skill_ids: tuple[str, ...] = (),
    ) -> AsyncIterator[SandboxStreamEvent]:
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                events = (
                    session.codex.stream_turn(prompt, skill_ids)
                    if skill_ids
                    else session.codex.stream_turn(prompt)
                )
                async for event in events:
                    if event.kind:
                        yield SandboxStreamEvent(
                            kind=event.kind,
                            item_id=event.item_id,
                            status=event.status,
                            text=_public_event_text(event.text),
                            name=_safe_error_message(event.name),
                            arguments=_safe_public_value(event.arguments),
                            response=_safe_public_value(event.response),
                            thread_id=session.codex.thread_id,
                            approval=(
                                _safe_public_value(event.approval.public_dict())
                                if event.approval is not None
                                else None
                            ),
                            approval_resolved_id=(event.approval_resolved_id),
                            turn_id=event.turn_id,
                            usage=event.usage,
                            thread_total=event.thread_total,
                            model_context_window=event.model_context_window,
                        )
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error

    def settings(self, session_id: str, owner_id: str) -> dict[str, object]:
        """Return the current permissions, workspace, and lock state."""
        session = self._owned(session_id, owner_id)
        return {
            "threadId": session.codex.thread_id,
            "cwd": session.codex.cwd,
            **(
                {"model": session.codex.model}
                if getattr(session.codex, "model", "")
                else {}
            ),
            "workspaceLocked": session.codex.workspace_locked,
            "busy": session.codex.active,
            "permissions": session.codex.permissions.public_dict(),
        }

    def status(self, session_id: str, owner_id: str) -> dict[str, object]:
        """Return current thread settings and exact usage when available."""
        session = self._owned(session_id, owner_id)
        total = getattr(session.codex, "thread_token_total", None)
        context_window = getattr(session.codex, "model_context_window", None)
        return {
            **self.settings(session_id, owner_id),
            **(
                {"threadTotal": total.public_dict()}
                if isinstance(total, CodexTokenUsage)
                else {}
            ),
            **(
                {"modelContextWindow": context_window}
                if isinstance(context_window, int)
                else {}
            ),
        }

    async def list_models(
        self, session_id: str, owner_id: str
    ) -> tuple[CodexModel, ...]:
        """List visible models for the connected Codex session."""
        session = self._owned(session_id, owner_id)
        try:
            return await session.codex.list_models()
        except CodexAppServerError as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    async def set_model(self, session_id: str, owner_id: str, model: str) -> str:
        """Change the model without forwarding slash syntax as a prompt."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                return await session.codex.set_model(model)
            except (TypeError, ValueError) as error:
                raise SandboxValidationError(str(error)) from error
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error

    async def list_skills(
        self,
        session_id: str,
        owner_id: str,
        *,
        force_reload: bool = False,
    ) -> tuple[CodexSkill, ...]:
        """List Skills without exposing server-side paths."""
        session = self._owned(session_id, owner_id)
        try:
            return await session.codex.list_skills(force_reload)
        except CodexAppServerError as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    def _public_snapshot(
        self, session: SandboxConversation, snapshot: CodexThreadSnapshot
    ) -> dict[str, object]:
        value = _safe_public_value(snapshot.public_dict(session.codex.permissions))
        if not isinstance(value, dict):
            raise SandboxInvocationError("Codex Thread 响应格式无效。")
        return value

    async def new_thread(self, session_id: str, owner_id: str) -> dict[str, object]:
        """Create and activate a fresh Codex thread."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                snapshot = await session.codex.new_thread()
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error
        return self._public_snapshot(session, snapshot)

    async def list_threads(
        self,
        session_id: str,
        owner_id: str,
        *,
        cursor: str = "",
        search_term: str = "",
        archived: bool = False,
    ) -> tuple[tuple[CodexThreadSummary, ...], str]:
        """List recent Codex threads."""
        session = self._owned(session_id, owner_id)
        try:
            return await session.codex.list_threads(
                cursor=cursor,
                search_term=search_term,
                archived=archived,
            )
        except CodexAppServerError as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    async def resume_thread(
        self, session_id: str, owner_id: str, thread_id: str
    ) -> dict[str, object]:
        """Resume and activate a selected Codex thread."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                snapshot = await session.codex.resume_thread(thread_id)
            except ValueError as error:
                raise SandboxValidationError(str(error)) from error
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error
        return self._public_snapshot(session, snapshot)

    async def fork_thread(self, session_id: str, owner_id: str) -> dict[str, object]:
        """Fork and activate the current Codex thread."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                snapshot = await session.codex.fork_thread()
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error
        return self._public_snapshot(session, snapshot)

    async def archive_thread(
        self, session_id: str, owner_id: str, thread_id: str
    ) -> dict[str, object]:
        """Archive a thread and return a replacement snapshot when needed."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                snapshot = await session.codex.archive_thread(thread_id)
            except ValueError as error:
                raise SandboxValidationError(str(error)) from error
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error
        return {
            "archived": True,
            **(
                self._public_snapshot(session, snapshot) if snapshot is not None else {}
            ),
        }

    async def compact_thread(self, session_id: str, owner_id: str) -> None:
        """Start compacting the current Codex thread."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                await session.codex.compact_thread()
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error

    async def update_permissions(
        self,
        session_id: str,
        owner_id: str,
        settings: CodexPermissionSettings,
    ) -> CodexPermissionSettings:
        """Persist permissions and adopt them in every local thread."""
        session = self._owned(session_id, owner_id)
        if session.codex.active:
            raise SandboxSessionUnavailableError("当前任务运行中，暂时不能修改权限。")
        async with session.lock:
            try:
                applied = await session.codex.update_permissions(settings)
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error

        peers = [
            candidate
            for candidate in self._sessions.values()
            if candidate.session_id == session_id and candidate is not session
        ]
        results = await asyncio.gather(
            *(peer.codex.apply_session_permissions(applied) for peer in peers),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "Failed to hot-apply Sandbox permissions to a peer: %s",
                    _safe_error_message(result),
                )
        return applied

    async def update_workspace(self, session_id: str, owner_id: str, cwd: str) -> str:
        """Change the thread workspace before the first conversation turn."""
        session = self._owned(session_id, owner_id)
        if session.codex.active or session.codex.workspace_locked:
            raise SandboxSessionUnavailableError(
                "当前对话已经开始，工作空间不能再修改。"
            )
        async with session.lock:
            try:
                return await session.codex.update_workspace(cwd)
            except (TypeError, ValueError) as error:
                raise SandboxValidationError(str(error)) from error
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error

    async def list_directories(
        self, session_id: str, owner_id: str, path: str
    ) -> CodexDirectoryListing:
        """List directories in the remote Sandbox."""
        session = self._owned(session_id, owner_id)
        try:
            return await session.codex.list_directories(path)
        except (TypeError, ValueError) as error:
            raise SandboxValidationError(str(error)) from error
        except CodexAppServerError as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    def resolve_approval(
        self,
        session_id: str,
        owner_id: str,
        approval_id: str,
        decision: ApprovalDecision,
    ) -> None:
        """Resolve an approval without waiting on the active turn lock."""
        session = self._owned(session_id, owner_id)
        try:
            session.codex.resolve_approval(approval_id, decision)
        except CodexAppServerError as error:
            raise SandboxValidationError(str(error)) from error

    async def launch_terminal(
        self, session_id: str, owner_id: str
    ) -> tuple[str, str, str]:
        """Create a shell and return its same-origin URL and capability."""
        session = self._owned(session_id, owner_id)
        try:
            url, shell_session_id = await terminal_launch_url(
                session.cloud.endpoint, session_id
            )
        except (RuntimeError, TypeError, ValueError) as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error
        return url, shell_session_id, session.proxy_token

    def launch_browser(self, session_id: str, owner_id: str) -> tuple[str, str]:
        """Return the Browser UI's same-origin URL and capability."""
        session = self._owned(session_id, owner_id)
        return browser_launch_url(session_id), session.proxy_token

    async def upload_file(
        self,
        session_id: str,
        owner_id: str,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> str:
        """Upload a browser attachment into the current remote workspace."""
        session = self._owned(session_id, owner_id)
        try:
            return await upload_sandbox_file(
                session.cloud.endpoint,
                session.codex.cwd,
                file_name,
                content_type,
                content,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    def resolve_proxy_target(self, session_id: str, token: str) -> SandboxProxyTarget:
        """Resolve an opaque data-plane capability without browser identity."""
        found = False
        for session in self._sessions.values():
            if session.session_id != session_id:
                continue
            found = True
            if token and secrets.compare_digest(token, session.proxy_token):
                return SandboxProxyTarget(endpoint=session.cloud.endpoint)
        if found:
            raise PermissionError("invalid Sandbox proxy capability")
        raise KeyError(session_id)

    async def close(self, session_id: str, owner_id: str) -> None:
        """Disconnect the local bridge without deleting the cloud Session."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            self._sessions.pop((owner_id, session_id), None)
            await session.codex.close()

    async def cleanup_expired(self) -> None:
        """Drop local connections that exceeded their remote TTL window."""
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
                    "Failed to disconnect expired Sandbox Session %s: %s",
                    session_id,
                    _safe_error_message(error),
                )

    async def close_all(self) -> None:
        """Drop local connections while leaving cloud Sessions reusable."""
        sessions = tuple(self._sessions.values())
        self._sessions.clear()
        if sessions:
            await asyncio.gather(
                *(session.codex.close() for session in sessions),
                return_exceptions=True,
            )
        await self._gateway.drain()


def mount_sandbox_routes(
    app: Any,
    service: SandboxConversationService,
    owner_resolver: Callable[[Any], str],
) -> None:
    """Mount Studio HTTP routes for reusable Sandbox Sessions."""
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse

    def _http_error(error: SandboxError) -> HTTPException:
        status_code = 500
        if isinstance(error, SandboxConfigurationError):
            status_code = 503
        elif isinstance(error, SandboxValidationError):
            status_code = 422
        elif isinstance(error, SandboxSessionNotFoundError):
            status_code = 404
        elif isinstance(error, SandboxSessionUnavailableError):
            status_code = 409
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

    def _public_session(session: SandboxCloudSession) -> dict[str, str]:
        return {
            "sessionId": session.instance_id,
            "userSessionId": session.user_session_id,
            "status": session.status,
            "createdAt": session.created_at,
            "expireAt": session.expire_at,
            "toolType": session.tool_type,
            "region": session.region,
            "displayName": session.display_name,
        }

    async def _request_object(
        request: Request, *, maximum: int = 64 * 1024
    ) -> dict[str, object]:
        body = await request.body()
        if len(body) > maximum:
            raise SandboxValidationError("请求内容过大。")
        try:
            value = json.loads(body) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise SandboxValidationError("请求不是有效 JSON。") from error
        if not isinstance(value, dict):
            raise SandboxValidationError("请求必须是 JSON 对象。")
        return value

    def _launch_response(
        request: Request,
        session_id: str,
        token: str,
        value: dict[str, object],
    ) -> JSONResponse:
        response = JSONResponse(value)
        response.headers["Cache-Control"] = "no-store"
        common_path = proxy_prefix(session_id, "terminal").rsplit("/", 1)[0]
        forwarded_protocol = (
            request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        )
        response.set_cookie(
            proxy_cookie_name(session_id),
            token,
            max_age=STUDIO_SANDBOX_TTL_SECONDS,
            httponly=True,
            secure=(request.url.scheme == "https" or forwarded_protocol == "https"),
            samesite="strict",
            path=common_path,
        )
        return response

    @app.get("/web/sandbox/capabilities")
    async def _sandbox_capabilities(request: Request) -> dict[str, object]:
        owner_resolver(request)
        return service.capabilities()

    @app.get("/web/sandbox/sessions")
    async def _list_sandbox_sessions(request: Request) -> dict[str, object]:
        try:
            sessions = await service.list_sessions(owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {"sessions": [_public_session(session) for session in sessions]}

    @app.post("/web/sandbox/sessions")
    async def _start_sandbox_session(request: Request) -> dict[str, str]:
        owner_id = owner_resolver(request)
        try:
            body = await request.body()
            if body:
                try:
                    data = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise SandboxValidationError(
                        "创建智能体的请求不是有效 JSON。"
                    ) from error
                if not isinstance(data, dict):
                    raise SandboxValidationError("创建智能体的请求格式无效。")
            else:
                data = {}
            session = await service.create(owner_id, data.get("displayName", ""))
        except SandboxError as error:
            raise _http_error(error) from error
        return {
            **_public_session(session),
            "toolName": STUDIO_SANDBOX_TOOL_NAME,
        }

    @app.post("/web/sandbox/sessions/{session_id}/connect")
    async def _connect_sandbox_session(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            session = await service.connect(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {
            **_public_session(session.cloud),
            "toolName": STUDIO_SANDBOX_TOOL_NAME,
            **service.settings(session_id, session.owner_id),
        }

    @app.get("/web/sandbox/sessions/{session_id}/settings")
    async def _sandbox_settings(session_id: str, request: Request) -> dict[str, object]:
        try:
            return service.settings(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error

    @app.get("/web/sandbox/sessions/{session_id}/status")
    async def _sandbox_status(session_id: str, request: Request) -> dict[str, object]:
        try:
            return service.status(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error

    @app.get("/web/sandbox/sessions/{session_id}/models")
    async def _list_sandbox_models(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            models = await service.list_models(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {"models": [model.public_dict() for model in models]}

    @app.put("/web/sandbox/sessions/{session_id}/model")
    async def _set_sandbox_model(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            model = data.get("model")
            if not isinstance(model, str):
                raise SandboxValidationError("模型名称必须是文本。")
            applied = await service.set_model(session_id, owner_id, model)
        except SandboxError as error:
            raise _http_error(error) from error
        return {"model": applied}

    @app.get("/web/sandbox/sessions/{session_id}/skills")
    async def _list_sandbox_skills(
        session_id: str,
        request: Request,
        force_reload: bool = False,
    ) -> dict[str, object]:
        try:
            skills = await service.list_skills(
                session_id,
                owner_resolver(request),
                force_reload=force_reload,
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {"skills": [skill.public_dict() for skill in skills]}

    @app.get("/web/sandbox/sessions/{session_id}/threads")
    async def _list_sandbox_threads(
        session_id: str,
        request: Request,
        cursor: str = "",
        search: str = "",
        archived: bool = False,
    ) -> dict[str, object]:
        if len(cursor) > 2_000 or len(search) > 500:
            raise _http_error(SandboxValidationError("Thread 查询参数过长。"))
        try:
            threads, next_cursor = await service.list_threads(
                session_id,
                owner_resolver(request),
                cursor=cursor,
                search_term=search,
                archived=archived,
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {
            "threads": [thread.public_dict() for thread in threads],
            **({"nextCursor": next_cursor} if next_cursor else {}),
        }

    @app.post("/web/sandbox/sessions/{session_id}/threads/new")
    async def _new_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            return await service.new_thread(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error

    @app.post("/web/sandbox/sessions/{session_id}/threads/resume")
    async def _resume_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            thread_id = data.get("threadId")
            if not isinstance(thread_id, str):
                raise SandboxValidationError("Thread ID 必须是文本。")
            return await service.resume_thread(session_id, owner_id, thread_id)
        except SandboxError as error:
            raise _http_error(error) from error

    @app.post("/web/sandbox/sessions/{session_id}/threads/fork")
    async def _fork_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            return await service.fork_thread(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error

    @app.post("/web/sandbox/sessions/{session_id}/threads/archive")
    async def _archive_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            thread_id = data.get("threadId")
            if not isinstance(thread_id, str):
                raise SandboxValidationError("Thread ID 必须是文本。")
            return await service.archive_thread(session_id, owner_id, thread_id)
        except SandboxError as error:
            raise _http_error(error) from error

    @app.post("/web/sandbox/sessions/{session_id}/threads/compact")
    async def _compact_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            await service.compact_thread(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {"started": True}

    @app.put("/web/sandbox/sessions/{session_id}/permissions")
    async def _update_sandbox_permissions(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            try:
                settings = permission_settings_from_payload(data)
            except (TypeError, ValueError) as error:
                raise SandboxValidationError(str(error)) from error
            applied = await service.update_permissions(session_id, owner_id, settings)
        except SandboxError as error:
            raise _http_error(error) from error
        return {"permissions": applied.public_dict()}

    @app.put("/web/sandbox/sessions/{session_id}/workspace")
    async def _update_sandbox_workspace(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            cwd = data.get("cwd")
            if not isinstance(cwd, str):
                raise SandboxValidationError("工作目录必须是文本。")
            applied = await service.update_workspace(session_id, owner_id, cwd)
        except SandboxError as error:
            raise _http_error(error) from error
        return {"cwd": applied, "workspaceLocked": False}

    @app.get("/web/sandbox/sessions/{session_id}/directories")
    async def _list_sandbox_directories(
        session_id: str, request: Request, path: str = "/"
    ) -> dict[str, object]:
        try:
            listing = await service.list_directories(
                session_id, owner_resolver(request), path
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return listing.public_dict()

    @app.post("/web/sandbox/sessions/{session_id}/approvals/{approval_id}")
    async def _resolve_sandbox_approval(
        session_id: str, approval_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            try:
                decision = approval_decision_from_payload(data.get("decision"))
            except ValueError as error:
                raise SandboxValidationError(str(error)) from error
            service.resolve_approval(session_id, owner_id, approval_id, decision)
        except SandboxError as error:
            raise _http_error(error) from error
        return {"approvalId": approval_id, "decision": decision}

    @app.post("/web/sandbox/sessions/{session_id}/terminal")
    async def _launch_sandbox_terminal(
        session_id: str, request: Request
    ) -> JSONResponse:
        try:
            url, shell_session_id, token = await service.launch_terminal(
                session_id, owner_resolver(request)
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return _launch_response(
            request,
            session_id,
            token,
            {"url": url, "shellSessionId": shell_session_id},
        )

    @app.post("/web/sandbox/sessions/{session_id}/browser")
    async def _launch_sandbox_browser(
        session_id: str, request: Request
    ) -> JSONResponse:
        try:
            url, token = service.launch_browser(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return _launch_response(request, session_id, token, {"url": url})

    @app.post("/web/sandbox/sessions/{session_id}/files")
    async def _upload_sandbox_file(
        session_id: str,
        request: Request,
        file: Annotated[UploadFile, File()],
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        content = bytearray()
        try:
            while chunk := await file.read(1024 * 1024):
                content.extend(chunk)
                if len(content) > SANDBOX_UPLOAD_MAX_BYTES:
                    limit_mb = SANDBOX_UPLOAD_MAX_BYTES // (1024 * 1024)
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件不能超过 {limit_mb} MB。",
                    )
            path = await service.upload_file(
                session_id,
                owner_id,
                file.filename or "attachment",
                file.content_type or "application/octet-stream",
                bytes(content),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        finally:
            await file.close()
        return {
            "id": path,
            "path": path,
            "name": path.rsplit("/", 1)[-1],
            "mimeType": file.content_type or "application/octet-stream",
            "sizeBytes": len(content),
        }

    @app.post("/web/sandbox/sessions/{session_id}/messages")
    async def _send_sandbox_message(
        session_id: str, request: Request
    ) -> StreamingResponse:
        try:
            data = await _request_object(request, maximum=128 * 1024)
            prompt = data.get("message")
            if not isinstance(prompt, str) or not prompt.strip():
                raise SandboxValidationError("message must not be empty")
            if len(prompt) > 100_000:
                raise SandboxValidationError("message is too large")
            raw_skill_ids = data.get("skillIds", [])
            if (
                not isinstance(raw_skill_ids, list)
                or len(raw_skill_ids) > 20
                or any(
                    not isinstance(skill_id, str) or not skill_id or len(skill_id) > 500
                    for skill_id in raw_skill_ids
                )
            ):
                raise SandboxValidationError("skillIds 格式无效。")
            skill_ids = tuple(dict.fromkeys(raw_skill_ids))
        except SandboxError as error:
            raise _http_error(error) from error
        owner_id = owner_resolver(request)
        try:
            service.require_owned(session_id, owner_id)
        except SandboxError as error:
            raise _http_error(error) from error

        async def _stream() -> AsyncIterator[str]:
            try:
                async for event in service.stream_message(
                    session_id, owner_id, prompt.strip(), skill_ids
                ):
                    if event.kind == "text":
                        payload = {"text": event.text}
                        yield f"event: delta\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        continue
                    if event.approval is not None:
                        yield (
                            "event: approval\n"
                            f"data: {json.dumps(event.approval, ensure_ascii=False)}\n\n"
                        )
                        continue
                    if event.approval_resolved_id:
                        payload = {"approvalId": event.approval_resolved_id}
                        yield (
                            "event: approval_resolved\n"
                            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        )
                        continue
                    if event.kind == "usage" and event.usage is not None:
                        payload = {
                            "turnId": event.turn_id,
                            "usage": event.usage.public_dict(),
                            **(
                                {"threadTotal": event.thread_total.public_dict()}
                                if event.thread_total is not None
                                else {}
                            ),
                            **(
                                {"modelContextWindow": (event.model_context_window)}
                                if event.model_context_window is not None
                                else {}
                            ),
                        }
                        yield (
                            "event: usage\n"
                            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        )
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
                        "Failed to disconnect cancelled Sandbox Session %s",
                        session_id,
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
    async def _disconnect_sandbox_session(
        session_id: str, request: Request
    ) -> dict[str, bool]:
        try:
            await service.close(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {"disconnected": True}

    mount_sandbox_proxy_routes(app, service.resolve_proxy_target)

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
