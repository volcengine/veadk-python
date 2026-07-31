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

"""Hermes and OpenClaw iframe Sessions for Studio."""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse

from veadk.cli.agentkit_session_metadata import SESSION_DISPLAY_NAME_MAX_LENGTH
from veadk.cli.frontend_sandbox import (
    STUDIO_SANDBOX_TTL_SECONDS,
    SandboxCloudGateway,
    SandboxCloudSession,
    SandboxConfigurationError,
    SandboxError,
    SandboxProvisioningError,
    SandboxSessionNotFoundError,
    SandboxValidationError,
)

EmbeddedAgentKind = Literal["openclaw", "hermes"]
EmbeddedAgentSurface = Literal["webui", "terminal"]

_MAX_ACTIVE_SESSIONS = 20
_MAX_REQUEST_BYTES = 16 * 1024 * 1024
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
_MAX_WEBSOCKET_MESSAGE_BYTES = 8 * 1024 * 1024
_PROXY_TIMEOUT_SECONDS = 60
_FAILED_STATUSES = frozenset(
    {"error", "failed", "createfailed", "stopped", "deleting", "deleted"}
)
_TEXT_TYPES = (
    "text/",
    "application/javascript",
    "application/json",
    "application/manifest+json",
    "application/xml",
    "image/svg+xml",
)
_GATEWAY_QUERY_KEYS = frozenset({"authorization", "faasinstancename"})
_STUDIO_COOKIE_PREFIX = "veadk_"
_PROXY_SECRET_ENV = "VEADK_EMBEDDED_PROXY_SECRET"
_PROXY_CAPABILITY_VERSION = 1
_OPENCLAW_QR_COMMAND = "openclaw qr --json --no-ascii --url wss://localhost"
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class EmbeddedAgentDefinition:
    """Server-side configuration for one preset AgentKit environment."""

    kind: EmbeddedAgentKind
    label: str
    tool_type: str
    tool_env: str
    webui_path: str


DEFINITIONS: dict[EmbeddedAgentKind, EmbeddedAgentDefinition] = {
    "openclaw": EmbeddedAgentDefinition(
        kind="openclaw",
        label="OpenClaw",
        tool_type="ArkClawEnv",
        tool_env="SANDBOX_OPENCLAW_TOOL",
        webui_path="/openclaw",
    ),
    "hermes": EmbeddedAgentDefinition(
        kind="hermes",
        label="Hermes",
        tool_type="HermesEnv",
        tool_env="SANDBOX_HERMES_TOOL",
        webui_path="/hermes",
    ),
}


@dataclass
class EmbeddedAgentSession:
    """Private server-side state backing one pair of Studio iframes."""

    kind: EmbeddedAgentKind
    owner_id: str
    cloud: SandboxCloudSession
    webui_target: str
    terminal_target: str
    openclaw_bootstrap_token: str
    proxy_token: str
    expires_at: float


@dataclass(frozen=True)
class _ProxyCapability:
    """Authenticated iframe routing claims shared by every Studio instance."""

    session_id: str
    kind: EmbeddedAgentKind
    owner_id: str
    expires_at: float


def _definition(kind: str) -> EmbeddedAgentDefinition:
    if kind not in {"openclaw", "hermes"}:
        raise SandboxValidationError("不支持的智能体类型。")
    return DEFINITIONS[cast(EmbeddedAgentKind, kind)]


def _proxy_cookie_name(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:20]
    return f"veadk_embedded_{digest}"


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _proxy_prefix(
    session_id: str,
    kind: EmbeddedAgentKind,
    surface: EmbeddedAgentSurface,
) -> str:
    return f"/web/embedded/{quote(session_id, safe='')}/{kind}/{surface}"


def _valid_target(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SandboxProvisioningError("AgentKit Session 未返回有效的访问地址。")
    return value


def _target_from_endpoint(endpoint: str, path: str) -> str:
    parsed = urlsplit(_valid_target(endpoint))
    endpoint_path = parsed.path.rstrip("/")
    requested_path = f"/{path.lstrip('/')}"
    if endpoint_path == requested_path or endpoint_path.startswith(
        f"{requested_path}/"
    ):
        target_path = endpoint_path
    else:
        target_path = f"{endpoint_path}{requested_path}"
    return urlunsplit((parsed.scheme, parsed.netloc, target_path, parsed.query, ""))


def _target_from_session_meta(endpoint: str, value: str) -> str:
    if not value:
        return ""
    parsed_value = urlsplit(value)
    if parsed_value.scheme and parsed_value.scheme not in {"http", "https"}:
        raise SandboxProvisioningError("AgentKit Session 返回了无效的页面地址。")
    target = urlsplit(_target_from_endpoint(endpoint, parsed_value.path))
    query = dict(parse_qsl(parsed_value.query, keep_blank_values=True))
    query.update(parse_qsl(target.query, keep_blank_values=True))
    return urlunsplit((target.scheme, target.netloc, target.path, urlencode(query), ""))


def _terminal_target(cloud: SandboxCloudSession) -> str:
    candidates = [
        _target_from_session_meta(cloud.endpoint, value)
        for value in (cloud.webshell_url, cloud.vnc_url)
        if value
    ]
    for candidate in candidates:
        if "terminal" in urlsplit(candidate).path.lower():
            return candidate
    if candidates:
        return candidates[0]
    return _target_from_endpoint(cloud.endpoint, "/terminal")


async def _resolve_terminal_target(cloud: SandboxCloudSession) -> str:
    """Create a native shell session and keep its ID with Endpoint auth."""
    candidate = _terminal_target(cloud)
    if dict(parse_qsl(urlsplit(candidate).query, keep_blank_values=True)).get(
        "session_id"
    ):
        return candidate

    terminal_url_endpoint = _target_from_endpoint(
        cloud.endpoint,
        "/v1/shell/terminal-url",
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                terminal_url_endpoint,
                headers={"accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        value = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(value, str) or not value:
            raise ValueError("missing terminal URL")
        terminal = urlsplit(value)
        if terminal.path.rstrip("/") != "/terminal":
            raise ValueError("unexpected terminal path")
        shell_session_id = (
            dict(parse_qsl(terminal.query, keep_blank_values=True))
            .get("session_id", "")
            .strip()
        )
        if not shell_session_id:
            raise ValueError("missing shell session ID")
    except (httpx.HTTPError, TypeError, ValueError) as error:
        raise SandboxProvisioningError("无法创建 Terminal 会话。") from error

    target = urlsplit(_target_from_endpoint(cloud.endpoint, terminal.path))
    query = {"session_id": shell_session_id}
    query.update(parse_qsl(target.query, keep_blank_values=True))
    return urlunsplit((target.scheme, target.netloc, target.path, urlencode(query), ""))


def _first_json_object(value: str) -> dict[str, object]:
    clean = _ANSI_ESCAPE_RE.sub("", value)
    decoder = json.JSONDecoder()
    for index, character in enumerate(clean):
        if character != "{":
            continue
        try:
            decoded, _end = decoder.raw_decode(clean[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return cast(dict[str, object], decoded)
    raise ValueError("missing JSON object")


async def _resolve_openclaw_bootstrap_token(cloud: SandboxCloudSession) -> str:
    """Read the Session's Control UI bootstrap token through the data plane."""
    shell_endpoint = _target_from_endpoint(cloud.endpoint, "/v1/shell/exec")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                shell_endpoint,
                json={"command": _OPENCLAW_QR_COMMAND},
                headers={"accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or data.get("exit_code") not in {0, "0"}:
            raise ValueError("OpenClaw QR command failed")
        output = data.get("output")
        if not isinstance(output, str):
            raise TypeError("OpenClaw QR output is missing")
        setup_code = _first_json_object(output).get("setupCode")
        if not isinstance(setup_code, str) or not setup_code:
            raise ValueError("OpenClaw setup code is missing")
        setup = json.loads(_base64url_decode(setup_code))
        token = setup.get("bootstrapToken") if isinstance(setup, dict) else None
        if (
            not isinstance(token, str)
            or not token.strip()
            or len(token) > 4_096
            or "\r" in token
            or "\n" in token
        ):
            raise ValueError("OpenClaw bootstrap token is invalid")
        return token.strip()
    except (
        binascii.Error,
        httpx.HTTPError,
        json.JSONDecodeError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        raise SandboxProvisioningError("无法初始化 OpenClaw 页面鉴权。") from error


def _epoch(value: str, fallback: float) -> float:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return fallback


class EmbeddedAgentService:
    """List and connect persistent preset AgentKit Sessions."""

    def __init__(
        self,
        gateway: SandboxCloudGateway,
        *,
        ready_timeout_seconds: float = 300,
        poll_interval_seconds: float = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        endpoint_probe: Callable[[str], Awaitable[int]] | None = None,
        terminal_target_resolver: Callable[[SandboxCloudSession], Awaitable[str]]
        | None = None,
        openclaw_bootstrap_resolver: Callable[[SandboxCloudSession], Awaitable[str]]
        | None = None,
        openclaw_gateway_token_factory: Callable[[], str] | None = None,
        session_env_resolver: Callable[[], dict[str, str]] | None = None,
        capability_secret: str | None = None,
    ) -> None:
        self._gateway = gateway
        self._ready_timeout_seconds = ready_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._sleep = sleep
        self._endpoint_probe = endpoint_probe or self._probe_endpoint
        self._terminal_target_resolver = (
            terminal_target_resolver or _resolve_terminal_target
        )
        self._openclaw_bootstrap_resolver = (
            openclaw_bootstrap_resolver or _resolve_openclaw_bootstrap_token
        )
        self._openclaw_gateway_token_factory = openclaw_gateway_token_factory or (
            lambda: secrets.token_urlsafe(32)
        )
        self._session_env_resolver = session_env_resolver
        resolved_secret = (
            capability_secret
            or os.getenv(_PROXY_SECRET_ENV)
            or secrets.token_urlsafe(32)
        )
        self._capability_secret = resolved_secret.encode("utf-8")
        self._session_envs: dict[str, str] | None = None
        self._session_env_lock = asyncio.Lock()
        self._sessions: dict[tuple[str, str], EmbeddedAgentSession] = {}
        self._lock = asyncio.Lock()

    def capabilities(self, kind: str) -> dict[str, object]:
        definition = _definition(kind)
        enabled = bool(os.getenv(definition.tool_env, "").strip())
        return {
            "kind": definition.kind,
            "label": definition.label,
            "enabled": enabled,
            "reason": ("" if enabled else f"管理员尚未配置 {definition.tool_env}。"),
        }

    @staticmethod
    def _tool_id(definition: EmbeddedAgentDefinition) -> str:
        tool_id = os.getenv(definition.tool_env, "").strip()
        if not tool_id:
            raise SandboxConfigurationError(f"管理员尚未配置 {definition.tool_env}。")
        return tool_id

    @staticmethod
    async def _probe_endpoint(target: str) -> int:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(target)
            return response.status_code

    async def _creation_envs(self) -> dict[str, str]:
        if self._session_env_resolver is None:
            return {}
        if self._session_envs is not None:
            return dict(self._session_envs)
        async with self._session_env_lock:
            if self._session_envs is None:
                try:
                    resolved = await asyncio.to_thread(self._session_env_resolver)
                except Exception as error:
                    raise SandboxConfigurationError(
                        "无法为嵌入式智能体解析模型配置。"
                    ) from error
                self._session_envs = {
                    str(key): str(value)
                    for key, value in resolved.items()
                    if key and value
                }
        return dict(self._session_envs)

    async def list(self, kind: str) -> list[SandboxCloudSession]:
        definition = _definition(kind)
        sessions = await self._gateway.list_sessions(self._tool_id(definition))
        return [
            session
            for session in sessions
            if not session.tool_type or session.tool_type == definition.tool_type
        ]

    async def start(
        self,
        kind: str,
        owner_id: str,
        display_name: object = "",
    ) -> EmbeddedAgentSession:
        definition = _definition(kind)
        if not isinstance(display_name, str):
            raise SandboxValidationError("智能体名称必须是文本。")
        display_name = display_name.strip()
        if len(display_name) > SESSION_DISPLAY_NAME_MAX_LENGTH:
            raise SandboxValidationError(
                f"智能体名称不能超过 {SESSION_DISPLAY_NAME_MAX_LENGTH} 个字符。"
            )
        display_name = display_name or f"{definition.label} 智能体"
        tool_id = self._tool_id(definition)
        await self._discard_expired()
        async with self._lock:
            active = sum(
                session.owner_id == owner_id for session in self._sessions.values()
            )
            if active >= _MAX_ACTIVE_SESSIONS:
                raise SandboxProvisioningError("当前智能体连接数量已达上限。")

        creation_envs = await self._creation_envs()
        if definition.kind == "openclaw":
            creation_envs.setdefault(
                "OPENCLAW_GATEWAY_TOKEN",
                self._openclaw_gateway_token_factory(),
            )
        cloud = await self._gateway.create_session(
            tool_id,
            display_name=display_name,
            envs=creation_envs,
        )
        try:
            cloud = await self._wait_until_ready(definition, cloud)
            return await self._register(
                definition,
                cloud,
                owner_id,
                require_openclaw_bootstrap=True,
            )
        except BaseException:
            with contextlib.suppress(SandboxError):
                await self._gateway.delete_session(cloud)
            raise

    async def connect(
        self,
        kind: str,
        session_id: str,
        owner_id: str,
    ) -> EmbeddedAgentSession:
        definition = _definition(kind)
        cloud = await self._gateway.get_session(
            self._tool_id(definition),
            session_id,
        )
        cloud = await self._wait_until_ready(definition, cloud)
        return await self._register(definition, cloud, owner_id)

    async def _register(
        self,
        definition: EmbeddedAgentDefinition,
        cloud: SandboxCloudSession,
        owner_id: str,
        *,
        proxy_token: str | None = None,
        capability_expires_at: float | None = None,
        issue_openclaw_bootstrap: bool = True,
        require_openclaw_bootstrap: bool = False,
    ) -> EmbeddedAgentSession:
        expires_at_epoch = capability_expires_at or _epoch(
            cloud.expire_at,
            time.time() + STUDIO_SANDBOX_TTL_SECONDS,
        )
        if expires_at_epoch <= time.time():
            raise SandboxSessionNotFoundError("智能体连接已过期。")
        token = proxy_token or self._sign_capability(
            session_id=cloud.instance_id,
            kind=definition.kind,
            owner_id=owner_id,
            expires_at=expires_at_epoch,
        )
        terminal_target = await self._terminal_target_resolver(cloud)
        openclaw_bootstrap_token = ""
        if definition.kind == "openclaw" and issue_openclaw_bootstrap:
            try:
                openclaw_bootstrap_token = await self._openclaw_bootstrap_resolver(
                    cloud
                )
            except SandboxProvisioningError:
                if require_openclaw_bootstrap:
                    raise
        session = EmbeddedAgentSession(
            kind=definition.kind,
            owner_id=owner_id,
            cloud=cloud,
            webui_target=_target_from_endpoint(cloud.endpoint, definition.webui_path),
            terminal_target=terminal_target,
            openclaw_bootstrap_token=openclaw_bootstrap_token,
            proxy_token=token,
            expires_at=(time.monotonic() + max(0.0, expires_at_epoch - time.time())),
        )
        async with self._lock:
            self._sessions[(cloud.instance_id, owner_id)] = session
        return session

    def _sign_capability(
        self,
        *,
        session_id: str,
        kind: EmbeddedAgentKind,
        owner_id: str,
        expires_at: float,
    ) -> str:
        payload = json.dumps(
            {
                "exp": int(expires_at),
                "kind": kind,
                "owner": owner_id,
                "sid": session_id,
                "v": _PROXY_CAPABILITY_VERSION,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encoded_payload = _base64url_encode(payload)
        signature = hmac.new(
            self._capability_secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{encoded_payload}.{_base64url_encode(signature)}"

    def _verify_capability(
        self,
        *,
        token: str,
        session_id: str,
        kind: EmbeddedAgentKind,
        owner_id: str | None,
    ) -> _ProxyCapability:
        if not token:
            raise PermissionError("missing iframe capability")
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            supplied_signature = _base64url_decode(encoded_signature)
            expected_signature = hmac.new(
                self._capability_secret,
                encoded_payload.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise ValueError("signature mismatch")
            payload = json.loads(_base64url_decode(encoded_payload))
            capability = _ProxyCapability(
                session_id=str(payload["sid"]),
                kind=_definition(str(payload["kind"])).kind,
                owner_id=str(payload["owner"]),
                expires_at=float(payload["exp"]),
            )
            if int(payload["v"]) != _PROXY_CAPABILITY_VERSION:
                raise ValueError("unsupported capability version")
        except (
            binascii.Error,
            KeyError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
        ) as error:
            raise PermissionError("invalid iframe capability") from error
        if capability.session_id != session_id or capability.kind != kind:
            raise PermissionError("invalid iframe capability")
        if owner_id is not None and capability.owner_id != owner_id:
            raise SandboxSessionNotFoundError("智能体连接不存在。")
        if capability.expires_at <= time.time():
            raise SandboxSessionNotFoundError("智能体连接已过期。")
        return capability

    async def _wait_until_ready(
        self,
        definition: EmbeddedAgentDefinition,
        cloud: SandboxCloudSession,
    ) -> SandboxCloudSession:
        deadline = time.monotonic() + self._ready_timeout_seconds
        current = cloud
        while True:
            try:
                current = await self._gateway.get_session(
                    current.tool_id, current.instance_id
                )
            except SandboxSessionNotFoundError:
                if time.monotonic() >= deadline:
                    raise SandboxProvisioningError(
                        f"等待 {definition.label} Session 就绪超时。"
                    ) from None
                await self._sleep(self._poll_interval_seconds)
                continue
            status = current.status.lower()
            if status == "ready" and current.endpoint:
                if current.tool_type and current.tool_type != definition.tool_type:
                    raise SandboxProvisioningError(
                        f"AgentKit Session ToolType 为 {current.tool_type}，"
                        f"预期为 {definition.tool_type}。"
                    )
                targets = (
                    _target_from_endpoint(current.endpoint, definition.webui_path),
                    _terminal_target(current),
                )
                statuses: tuple[int, int] | None = None
                try:
                    statuses = cast(
                        tuple[int, int],
                        tuple(
                            await asyncio.gather(
                                *(self._endpoint_probe(target) for target in targets)
                            )
                        ),
                    )
                except httpx.HTTPError:
                    pass
                if statuses and all(200 <= value < 400 for value in statuses):
                    return current
            if status in _FAILED_STATUSES:
                raise SandboxProvisioningError(
                    f"{definition.label} Session 启动失败（{current.status}）。"
                )
            if time.monotonic() >= deadline:
                raise SandboxProvisioningError(
                    f"等待 {definition.label} Session 就绪超时。"
                )
            await self._sleep(self._poll_interval_seconds)

    async def disconnect(
        self,
        kind: str,
        session_id: str,
        owner_id: str,
        token: str,
    ) -> None:
        definition = _definition(kind)
        capability = self._verify_capability(
            token=token,
            session_id=session_id,
            kind=definition.kind,
            owner_id=owner_id,
        )
        async with self._lock:
            self._sessions.pop((session_id, capability.owner_id), None)

    async def delete(
        self,
        kind: str,
        session_id: str,
    ) -> None:
        definition = _definition(kind)
        cloud = await self._gateway.get_session(
            self._tool_id(definition),
            session_id,
        )
        if cloud.tool_type and cloud.tool_type != definition.tool_type:
            raise SandboxSessionNotFoundError("智能体 Session 不存在。")
        async with self._lock:
            for key in tuple(self._sessions):
                if key[0] == session_id:
                    self._sessions.pop(key, None)
        await self._gateway.delete_session(cloud)

    async def resolve(
        self,
        kind: str,
        session_id: str,
        owner_id: str | None,
        token: str,
        surface: str,
    ) -> str:
        definition = _definition(kind)
        if surface not in {"webui", "terminal"}:
            raise SandboxSessionNotFoundError("智能体页面不存在。")
        capability = self._verify_capability(
            token=token,
            session_id=session_id,
            kind=definition.kind,
            owner_id=owner_id,
        )
        session = self._sessions.get((session_id, capability.owner_id))
        if session is None:
            cloud = await self._gateway.get_session(
                self._tool_id(definition),
                session_id,
            )
            if cloud.status.lower() != "ready" or not cloud.endpoint:
                raise SandboxSessionNotFoundError("智能体 Session 尚未就绪。")
            if cloud.tool_type and cloud.tool_type != definition.tool_type:
                raise SandboxSessionNotFoundError("智能体 Session 不存在。")
            session = await self._register(
                definition,
                cloud,
                capability.owner_id,
                proxy_token=token,
                capability_expires_at=capability.expires_at,
                issue_openclaw_bootstrap=False,
            )
        if time.monotonic() >= session.expires_at:
            raise SandboxSessionNotFoundError("智能体连接已过期。")
        return session.webui_target if surface == "webui" else session.terminal_target

    async def _discard_expired(self) -> None:
        now = time.monotonic()
        async with self._lock:
            expired = [
                (key, session)
                for key, session in self._sessions.items()
                if now >= session.expires_at
            ]
            for key, _session in expired:
                self._sessions.pop(key, None)

    async def close_all(self) -> None:
        async with self._lock:
            self._sessions.clear()


def _public_session(session: EmbeddedAgentSession) -> dict[str, object]:
    now = time.time()
    created_at = _epoch(session.cloud.created_at, now)
    expires_at = _epoch(
        session.cloud.expire_at,
        created_at + STUDIO_SANDBOX_TTL_SECONDS,
    )
    session_id = session.cloud.instance_id
    webui_url = f"{_proxy_prefix(session_id, session.kind, 'webui')}/"
    terminal_url = f"{_proxy_prefix(session_id, session.kind, 'terminal')}/"
    webui_query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(
                urlsplit(session.webui_target).query,
                keep_blank_values=True,
            )
            if key.lower() in {"session", "session_id"}
        ]
    )
    terminal_query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(
                urlsplit(session.terminal_target).query,
                keep_blank_values=True,
            )
            if key.lower() == "session_id"
        ]
    )
    webui_fragment = (
        f"#token={quote(session.openclaw_bootstrap_token, safe='')}"
        if session.openclaw_bootstrap_token
        else ""
    )
    return {
        "kind": session.kind,
        "status": "ready",
        "sessionId": session_id,
        "sandboxId": session_id,
        "webuiUrl": (
            f"{webui_url}{'?' + webui_query if webui_query else ''}{webui_fragment}"
        ),
        "terminalUrl": (
            f"{terminal_url}{'?' + terminal_query if terminal_query else ''}"
        ),
        "createdAt": created_at,
        "expiresAt": expires_at,
        "ttlSeconds": STUDIO_SANDBOX_TTL_SECONDS,
    }


def _public_cloud_session(
    kind: EmbeddedAgentKind,
    session: SandboxCloudSession,
) -> dict[str, str]:
    return {
        "kind": kind,
        "sessionId": session.instance_id,
        "userSessionId": session.user_session_id,
        "displayName": session.display_name,
        "status": session.status,
        "createdAt": session.created_at,
        "expireAt": session.expire_at,
    }


def _http_error(error: SandboxError) -> HTTPException:
    status_code = 502
    if isinstance(error, SandboxConfigurationError):
        status_code = 503
    elif isinstance(error, SandboxValidationError):
        status_code = 422
    elif isinstance(error, SandboxSessionNotFoundError):
        status_code = 404
    return HTTPException(
        status_code=status_code,
        detail={
            "code": error.code,
            "message": str(error),
            "retryable": error.retryable,
        },
    )


def _secure_cookie(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    return request.url.scheme == "https" or forwarded.split(",", 1)[0] == "https"


def _trusted_websocket_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    parsed = urlsplit(origin)
    return parsed.scheme in {
        "http",
        "https",
    } and parsed.netloc == websocket.headers.get("host")


def _upstream_url(
    target: str,
    asset_path: str,
    query: str,
    *,
    trailing_slash: bool = False,
) -> str:
    parsed = urlsplit(target)
    base_path = parsed.path.rstrip("/")
    if asset_path.startswith("__root__/"):
        path = f"/{asset_path.removeprefix('__root__/')}"
    elif asset_path:
        path = f"{base_path}/{asset_path}"
    else:
        path = f"{base_path}/" if base_path and trailing_slash else base_path or "/"
    incoming = {
        key: value
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key.lower() not in _GATEWAY_QUERY_KEYS
    }
    protected = dict(parse_qsl(parsed.query, keep_blank_values=True))
    incoming.update(protected)
    return urlunsplit((parsed.scheme, parsed.netloc, path, urlencode(incoming), ""))


def _public_query(query: str, target: str) -> str:
    protected_keys = _GATEWAY_QUERY_KEYS | {
        key.lower()
        for key, _value in parse_qsl(urlsplit(target).query, keep_blank_values=True)
    }
    return urlencode(
        [
            (key, value)
            for key, value in parse_qsl(query, keep_blank_values=True)
            if key.lower() not in protected_keys
        ]
    )


def _rewrite_text(
    text: str,
    *,
    target: str,
    prefix: str,
    root_relative_assets: bool = False,
) -> str:
    target_parts = urlsplit(target)
    upstream_path = target_parts.path.rstrip("/")
    upstream_origin = f"{target_parts.scheme}://{target_parts.netloc}"

    def _absolute_url(match: re.Match[str]) -> str:
        parsed = urlsplit(match.group(0))
        if upstream_path and parsed.path.startswith(upstream_path):
            path = f"{prefix}{parsed.path[len(upstream_path) :]}"
        else:
            path = f"{prefix}/__root__{parsed.path}"
        query = _public_query(parsed.query, target)
        return (
            f"{path}{'?' + query if query else ''}"
            f"{'#' + parsed.fragment if parsed.fragment else ''}"
        )

    text = re.sub(
        rf"{re.escape(upstream_origin)}[^\s\"'`<>()]*",
        _absolute_url,
        text,
    )
    if upstream_path:
        for quote_char in ('"', "'", "`"):
            text = text.replace(
                f"{quote_char}{upstream_path}",
                f"{quote_char}{prefix}",
            )
    proxy_path = re.escape(prefix.lstrip("/"))
    for attribute in ("src", "href", "action"):
        text = re.sub(
            rf"({attribute}\s*=\s*[\"'])/(?!/|{proxy_path}(?:/|$))",
            rf"\1{prefix}/__root__/",
            text,
            flags=re.IGNORECASE,
        )
    text = re.sub(
        rf"url\(\s*([\"']?)/(?!/|{proxy_path}(?:/|$))",
        rf"url(\1{prefix}/__root__/",
        text,
        flags=re.IGNORECASE,
    )
    for key, value in parse_qsl(target_parts.query, keep_blank_values=True):
        if value and key.lower() in _GATEWAY_QUERY_KEYS:
            text = text.replace(value, "")
    if root_relative_assets:
        public_root = f"{prefix}/__root__"

        def _relative_attribute(match: re.Match[str]) -> str:
            before, quote_char, value = match.groups()
            if (
                not value
                or value.startswith(("/", "//", "#"))
                or urlsplit(value).scheme
            ):
                return match.group(0)
            normalized = value.removeprefix("./")
            return f"{before}{quote_char}{public_root}/{normalized}{quote_char}"

        for attribute in ("src", "href", "action"):
            text = re.sub(
                rf"({attribute}\s*=\s*)([\"'])([^\"']+)\2",
                _relative_attribute,
                text,
                flags=re.IGNORECASE,
            )
        text = text.replace(
            "const baseUrl = window.location.origin + basePath;",
            f"const baseUrl = window.location.origin + '{public_root}';",
        )
        text = text.replace(
            "new URL('.', window.location.href)",
            "new URL(document.baseURI)",
        )
    return text


def _proxy_headers(content_type: str) -> dict[str, str]:
    return {
        "cache-control": "no-store",
        "content-type": content_type,
        "cross-origin-resource-policy": "same-origin",
        "referrer-policy": "same-origin",
        "x-content-type-options": "nosniff",
        "x-frame-options": "SAMEORIGIN",
    }


def _upstream_cookie_header(value: str) -> str:
    """Keep runtime cookies while withholding Studio identity capabilities."""
    cookies = []
    for part in value.split(";"):
        cookie = part.strip()
        name, separator, _value = cookie.partition("=")
        if (
            separator
            and name.strip()
            and not name.strip().lower().startswith(_STUDIO_COOKIE_PREFIX)
        ):
            cookies.append(cookie)
    return "; ".join(cookies)


def _local_set_cookie(value: str, prefix: str, *, secure: bool) -> str:
    """Scope an upstream runtime cookie to its same-origin iframe proxy."""
    value = re.sub(r";\s*Domain=[^;]*", "", value, flags=re.IGNORECASE)
    if not secure:
        value = re.sub(r";\s*Secure(?=;|$)", "", value, flags=re.IGNORECASE)
    if re.search(r";\s*Path=", value, flags=re.IGNORECASE):
        return re.sub(
            r";\s*Path=[^;]*",
            f"; Path={prefix}",
            value,
            count=1,
            flags=re.IGNORECASE,
        )
    return f"{value}; Path={prefix}"


def _append_upstream_cookies(
    response: Response,
    headers: httpx.Headers,
    prefix: str,
    *,
    secure: bool,
) -> None:
    for value in headers.get_list("set-cookie"):
        cookie = _local_set_cookie(value, prefix, secure=secure)
        response.raw_headers.append((b"set-cookie", cookie.encode("latin-1")))


async def _proxy_http(
    request: Request,
    *,
    target: str,
    prefix: str,
    asset_path: str,
    root_relative_assets: bool = False,
) -> Response:
    body = await request.body()
    if len(body) > _MAX_REQUEST_BYTES:
        return JSONResponse({"detail": "请求内容过大。"}, status_code=413)
    headers = {
        name: request.headers[name]
        for name in (
            "accept",
            "accept-language",
            "authorization",
            "content-type",
            "if-none-match",
            "if-modified-since",
            "range",
            "user-agent",
            "x-hermes-session-token",
        )
        if name in request.headers
    }
    upstream_cookie = _upstream_cookie_header(request.headers.get("cookie", ""))
    if upstream_cookie:
        headers["cookie"] = upstream_cookie
    headers.update(
        {
            "x-forwarded-host": request.headers.get("host", ""),
            "x-forwarded-prefix": prefix,
        }
    )
    target_parts = urlsplit(target)
    upstream_origin = f"{target_parts.scheme}://{target_parts.netloc}"
    headers["origin"] = upstream_origin
    headers["referer"] = target
    client = httpx.AsyncClient(
        timeout=_PROXY_TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    try:
        upstream = await client.send(
            client.build_request(
                request.method,
                _upstream_url(
                    target,
                    asset_path,
                    request.url.query,
                    trailing_slash=request.url.path.endswith("/"),
                ),
                content=body or None,
                headers=headers,
            ),
            stream=True,
        )
    except httpx.HTTPError:
        await client.aclose()
        return JSONResponse(
            {"detail": "无法连接智能体页面。"},
            status_code=502,
            headers={"cache-control": "no-store"},
        )
    content_type = upstream.headers.get("content-type", "application/octet-stream")
    response_headers = _proxy_headers(content_type)
    if content_type.lower().startswith("text/event-stream"):

        async def _event_stream() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream.aiter_bytes():
                    if len(chunk) > _MAX_RESPONSE_BYTES:
                        return
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        response = StreamingResponse(
            _event_stream(),
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=None,
        )
        _append_upstream_cookies(
            response,
            upstream.headers,
            prefix,
            secure=_secure_cookie(request),
        )
        return response
    try:
        content = await upstream.aread()
    finally:
        await upstream.aclose()
        await client.aclose()
    if len(content) > _MAX_RESPONSE_BYTES:
        return JSONResponse(
            {"detail": "智能体页面响应过大。"},
            status_code=502,
            headers={"cache-control": "no-store"},
        )
    if any(content_type.lower().startswith(value) for value in _TEXT_TYPES):
        try:
            content = _rewrite_text(
                content.decode(upstream.encoding or "utf-8"),
                target=target,
                prefix=prefix,
                root_relative_assets=root_relative_assets,
            ).encode("utf-8")
        except (LookupError, UnicodeDecodeError):
            pass
    location = upstream.headers.get("location", "")
    if location:
        resolved = urlsplit(urljoin(target, location))
        target_parts = urlsplit(target)
        if resolved.netloc == target_parts.netloc:
            target_root = target_parts.path.rstrip("/")
            suffix = resolved.path
            if target_root and suffix.startswith(target_root):
                suffix = suffix[len(target_root) :]
            else:
                suffix = f"/__root__{suffix}"
            public_query = _public_query(resolved.query, target)
            response_headers["location"] = (
                f"{prefix}{suffix or '/'}{'?' + public_query if public_query else ''}"
            )
    response = Response(
        content=content if request.method != "HEAD" else b"",
        status_code=upstream.status_code,
        headers=response_headers,
    )
    _append_upstream_cookies(
        response,
        upstream.headers,
        prefix,
        secure=_secure_cookie(request),
    )
    return response


async def _relay_websocket(
    websocket: WebSocket,
    upstream_url: str,
    cookie: str = "",
    user_agent: str = "",
) -> None:
    import websockets
    from websockets.exceptions import ConnectionClosed

    requested_protocols = [
        value.strip()
        for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if value.strip()
    ]
    await websocket.accept(
        subprotocol=requested_protocols[0] if requested_protocols else None
    )
    try:
        parsed_upstream = urlsplit(upstream_url)
        upstream_origin = (
            f"{'https' if parsed_upstream.scheme == 'wss' else 'http'}"
            f"://{parsed_upstream.netloc}"
        )
        additional_headers = {}
        if cookie:
            additional_headers["cookie"] = cookie
        if user_agent:
            additional_headers["user-agent"] = user_agent
        upstream = await websockets.connect(
            upstream_url,
            origin=cast(Any, upstream_origin),
            subprotocols=cast(Any, requested_protocols or None),
            additional_headers=additional_headers or None,
            open_timeout=_PROXY_TIMEOUT_SECONDS,
            close_timeout=5,
            max_size=_MAX_WEBSOCKET_MESSAGE_BYTES,
        )
    except Exception:  # noqa: BLE001 - WebSocket transport boundary
        with contextlib.suppress(RuntimeError):
            await websocket.close(code=1011, reason="sandbox websocket unavailable")
        return

    def _safe_close_code(value: object) -> int:
        try:
            code = int(value)
        except (TypeError, ValueError):
            return 1011
        if code < 1000 or code >= 5000 or code in {1005, 1006, 1015}:
            return 1011
        return code

    def _safe_close_reason(value: object) -> str:
        reason = str(value or "")
        for key, secret in parse_qsl(
            urlsplit(upstream_url).query,
            keep_blank_values=True,
        ):
            if secret and key.lower() in _GATEWAY_QUERY_KEYS:
                reason = reason.replace(secret, "***")
        return reason.encode("utf-8")[:120].decode("utf-8", errors="ignore")

    def _connection_close(error: ConnectionClosed) -> tuple[int, str]:
        frame = error.rcvd or error.sent
        return (
            _safe_close_code(frame.code if frame is not None else 1011),
            _safe_close_reason(frame.reason if frame is not None else ""),
        )

    async def _browser_to_upstream() -> tuple[str, int, str]:
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return (
                        "browser",
                        _safe_close_code(message.get("code", 1000)),
                        "",
                    )
                value = message.get("bytes")
                if value is None:
                    value = message.get("text")
                if value is not None:
                    await upstream.send(value)
        except WebSocketDisconnect as error:
            return ("browser", _safe_close_code(error.code), "")
        except RuntimeError:
            return ("browser", 1000, "")
        except ConnectionClosed as error:
            code, reason = _connection_close(error)
            return (
                "upstream",
                code,
                reason,
            )

    async def _upstream_to_browser() -> tuple[str, int, str]:
        try:
            async for value in upstream:
                if isinstance(value, bytes):
                    await websocket.send_bytes(value)
                else:
                    await websocket.send_text(value)
        except ConnectionClosed as error:
            code, reason = _connection_close(error)
            return (
                "upstream",
                code,
                reason,
            )
        except (WebSocketDisconnect, RuntimeError):
            return ("browser", 1000, "")
        return (
            "upstream",
            _safe_close_code(upstream.close_code or 1000),
            _safe_close_reason(upstream.close_reason),
        )

    tasks = {
        asyncio.create_task(_browser_to_upstream()),
        asyncio.create_task(_upstream_to_browser()),
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        closures = [task.result() for task in done]
        closure = next(
            (value for value in closures if value[0] == "upstream"),
            closures[0],
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        source, code, reason = closure
        if source == "upstream":
            with contextlib.suppress(RuntimeError):
                await websocket.close(code=code, reason=reason)
        else:
            await upstream.close(code=code)
    finally:
        await upstream.close()


def mount_embedded_agent_routes(
    app: Any,
    service: EmbeddedAgentService,
    owner_resolver: Callable[[Any], str],
    proxy_owner_resolver: Callable[[Any], str | None] | None = None,
) -> None:
    """Mount Session lifecycle and same-origin iframe proxy routes."""
    resolve_proxy_owner = proxy_owner_resolver or owner_resolver

    def _session_response(
        session: EmbeddedAgentSession,
        request: Request,
    ) -> Response:
        response = JSONResponse(_public_session(session))
        response.headers["cache-control"] = "no-store"
        response.set_cookie(
            _proxy_cookie_name(session.cloud.instance_id),
            session.proxy_token,
            max_age=STUDIO_SANDBOX_TTL_SECONDS,
            httponly=True,
            secure=_secure_cookie(request),
            samesite="strict",
            path=f"/web/embedded/{quote(session.cloud.instance_id, safe='')}",
        )
        return response

    @app.get("/web/{kind}/capabilities")
    async def _capabilities(kind: str, request: Request) -> dict[str, object]:
        owner_resolver(request)
        try:
            return service.capabilities(kind)
        except SandboxError as error:
            raise _http_error(error) from error

    @app.post("/web/{kind}/sessions")
    async def _start(kind: str, request: Request) -> Response:
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
            session = await service.start(
                kind,
                owner_id,
                data.get("displayName", ""),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return _session_response(session, request)

    @app.get("/web/{kind}/sessions")
    async def _list(kind: str, request: Request) -> Response:
        owner_resolver(request)
        try:
            definition = _definition(kind)
            sessions = await service.list(kind)
        except SandboxError as error:
            raise _http_error(error) from error
        response = JSONResponse(
            {
                "sessions": [
                    _public_cloud_session(definition.kind, session)
                    for session in sessions
                ]
            }
        )
        response.headers["cache-control"] = "no-store"
        return response

    @app.post("/web/{kind}/sessions/{session_id}/connect")
    async def _connect(
        kind: str,
        session_id: str,
        request: Request,
    ) -> Response:
        owner_id = owner_resolver(request)
        try:
            session = await service.connect(kind, session_id, owner_id)
        except SandboxError as error:
            raise _http_error(error) from error
        return _session_response(session, request)

    @app.post("/web/embedded/{session_id}/{kind}/disconnect")
    async def _disconnect(
        kind: str,
        session_id: str,
        request: Request,
    ) -> Response:
        owner_id = owner_resolver(request)
        try:
            await service.disconnect(
                kind,
                session_id,
                owner_id,
                request.cookies.get(_proxy_cookie_name(session_id), ""),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        response = Response(status_code=204)
        response.delete_cookie(
            _proxy_cookie_name(session_id),
            path=f"/web/embedded/{quote(session_id, safe='')}",
        )
        return response

    @app.delete("/web/{kind}/sessions/{session_id}")
    async def _delete(kind: str, session_id: str, request: Request) -> Response:
        owner_resolver(request)
        try:
            await service.delete(kind, session_id)
        except SandboxError as error:
            raise _http_error(error) from error
        response = Response(status_code=204)
        response.delete_cookie(
            _proxy_cookie_name(session_id),
            path=f"/web/embedded/{quote(session_id, safe='')}",
        )
        return response

    @app.api_route(
        "/web/embedded/{session_id}/{kind}/{surface}/{asset_path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def _http_proxy(
        session_id: str,
        kind: str,
        surface: str,
        asset_path: str,
        request: Request,
    ) -> Response:
        try:
            owner_id = resolve_proxy_owner(request)
            token = request.cookies.get(_proxy_cookie_name(session_id), "")
            target = await service.resolve(kind, session_id, owner_id, token, surface)
        except PermissionError:
            return JSONResponse({"detail": "智能体页面授权已失效。"}, status_code=403)
        except SandboxError as error:
            return JSONResponse({"detail": str(error)}, status_code=404)
        typed_kind = _definition(kind).kind
        typed_surface: EmbeddedAgentSurface = (
            "webui" if surface == "webui" else "terminal"
        )
        return await _proxy_http(
            request,
            target=target,
            prefix=_proxy_prefix(session_id, typed_kind, typed_surface),
            asset_path=asset_path,
            root_relative_assets=typed_surface == "terminal",
        )

    @app.websocket("/web/embedded/{session_id}/{kind}/{surface}/{asset_path:path}")
    async def _websocket_proxy(
        session_id: str,
        kind: str,
        surface: str,
        asset_path: str,
        websocket: WebSocket,
    ) -> None:
        if not _trusted_websocket_origin(websocket):
            await websocket.close(code=1008, reason="untrusted origin")
            return
        try:
            owner_id = resolve_proxy_owner(websocket)
            token = websocket.cookies.get(_proxy_cookie_name(session_id), "")
            target = await service.resolve(kind, session_id, owner_id, token, surface)
        except (HTTPException, PermissionError, SandboxError):
            await websocket.close(code=1008, reason="invalid capability")
            return
        upstream = _upstream_url(
            target,
            asset_path,
            websocket.url.query,
            trailing_slash=websocket.url.path.endswith("/"),
        )
        parsed = urlsplit(upstream)
        upstream = urlunsplit(
            (
                "wss" if parsed.scheme == "https" else "ws",
                parsed.netloc,
                parsed.path,
                parsed.query,
                "",
            )
        )
        await _relay_websocket(
            websocket,
            upstream,
            _upstream_cookie_header(websocket.headers.get("cookie", "")),
            websocket.headers.get("user-agent", ""),
        )

    app.router.on_shutdown.append(service.close_all)


__all__ = [
    "DEFINITIONS",
    "EmbeddedAgentService",
    "mount_embedded_agent_routes",
]
