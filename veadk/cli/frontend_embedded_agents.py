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

"""Disposable Hermes and OpenClaw iframe Sessions for Studio."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import re
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, cast
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse

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
    proxy_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    expires_at: float = field(
        default_factory=lambda: time.monotonic() + STUDIO_SANDBOX_TTL_SECONDS
    )


def _definition(kind: str) -> EmbeddedAgentDefinition:
    if kind not in {"openclaw", "hermes"}:
        raise SandboxValidationError("不支持的智能体类型。")
    return DEFINITIONS[cast(EmbeddedAgentKind, kind)]


def _proxy_cookie_name(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:20]
    return f"veadk_embedded_{digest}"


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
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def _target_from_session_meta(endpoint: str, value: str) -> str:
    if not value:
        return ""
    parsed_value = urlsplit(value)
    if parsed_value.scheme:
        return _valid_target(value)
    parsed_endpoint = urlsplit(_valid_target(endpoint))
    resolved = urlsplit(urljoin(endpoint, value))
    query = resolved.query or parsed_endpoint.query
    return _valid_target(
        urlunsplit((resolved.scheme, resolved.netloc, resolved.path, query, ""))
    )


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


def _epoch(value: str, fallback: float) -> float:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return fallback


class EmbeddedAgentService:
    """Create, own, and destroy disposable preset AgentKit Sessions."""

    def __init__(
        self,
        gateway: SandboxCloudGateway,
        *,
        ready_timeout_seconds: float = 300,
        poll_interval_seconds: float = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._gateway = gateway
        self._ready_timeout_seconds = ready_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._sleep = sleep
        self._sessions: dict[str, EmbeddedAgentSession] = {}
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

    async def start(self, kind: str, owner_id: str) -> EmbeddedAgentSession:
        definition = _definition(kind)
        tool_id = self._tool_id(definition)
        await self._discard_expired()
        async with self._lock:
            active = sum(
                session.owner_id == owner_id for session in self._sessions.values()
            )
            if active >= _MAX_ACTIVE_SESSIONS:
                raise SandboxProvisioningError("当前临时智能体 Session 数量已达上限。")

        cloud = await self._gateway.create_session(
            tool_id,
            display_name=f"{definition.label} iframe",
        )
        try:
            cloud = await self._wait_until_ready(definition, cloud)
            session = EmbeddedAgentSession(
                kind=definition.kind,
                owner_id=owner_id,
                cloud=cloud,
                webui_target=_target_from_endpoint(
                    cloud.endpoint, definition.webui_path
                ),
                terminal_target=_terminal_target(cloud),
            )
            async with self._lock:
                self._sessions[cloud.instance_id] = session
            return session
        except BaseException:
            with contextlib.suppress(SandboxError):
                await self._gateway.delete_session(cloud)
            raise

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

    async def close(
        self,
        kind: str,
        session_id: str,
        owner_id: str,
    ) -> None:
        definition = _definition(kind)
        async with self._lock:
            session = self._sessions.get(session_id)
            if (
                session is None
                or session.kind != definition.kind
                or session.owner_id != owner_id
            ):
                raise SandboxSessionNotFoundError("临时智能体 Session 不存在。")
            self._sessions.pop(session_id, None)
        await self._gateway.delete_session(session.cloud)

    def resolve(
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
        session = self._sessions.get(session_id)
        if (
            session is None
            or session.kind != definition.kind
            or (owner_id is not None and session.owner_id != owner_id)
        ):
            raise SandboxSessionNotFoundError("临时智能体 Session 不存在。")
        if time.monotonic() >= session.expires_at:
            raise SandboxSessionNotFoundError("临时智能体 Session 已过期。")
        if not token or not secrets.compare_digest(session.proxy_token, token):
            raise PermissionError("invalid iframe capability")
        return session.webui_target if surface == "webui" else session.terminal_target

    async def _discard_expired(self) -> None:
        now = time.monotonic()
        async with self._lock:
            expired = [
                session
                for session in self._sessions.values()
                if now >= session.expires_at
            ]
            for session in expired:
                self._sessions.pop(session.cloud.instance_id, None)
        if expired:
            await asyncio.gather(
                *(self._gateway.delete_session(session.cloud) for session in expired),
                return_exceptions=True,
            )

    async def close_all(self) -> None:
        async with self._lock:
            sessions = tuple(self._sessions.values())
            self._sessions.clear()
        if sessions:
            await asyncio.gather(
                *(self._gateway.delete_session(session.cloud) for session in sessions),
                return_exceptions=True,
            )


def _public_session(session: EmbeddedAgentSession) -> dict[str, object]:
    now = time.time()
    created_at = _epoch(session.cloud.created_at, now)
    expires_at = _epoch(
        session.cloud.expire_at,
        created_at + STUDIO_SANDBOX_TTL_SECONDS,
    )
    session_id = session.cloud.instance_id
    return {
        "kind": session.kind,
        "status": "ready",
        "sessionId": session_id,
        "sandboxId": session_id,
        "webuiUrl": f"{_proxy_prefix(session_id, session.kind, 'webui')}/",
        "terminalUrl": f"{_proxy_prefix(session_id, session.kind, 'terminal')}/",
        "createdAt": created_at,
        "expiresAt": expires_at,
        "ttlSeconds": STUDIO_SANDBOX_TTL_SECONDS,
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


def _upstream_url(target: str, asset_path: str, query: str) -> str:
    parsed = urlsplit(target)
    base_path = parsed.path.rstrip("/")
    if asset_path.startswith("__root__/"):
        path = f"/{asset_path.removeprefix('__root__/')}"
    elif asset_path:
        path = f"{base_path}/{asset_path}"
    else:
        path = base_path or "/"
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


async def _proxy_http(
    request: Request,
    *,
    target: str,
    prefix: str,
    asset_path: str,
) -> Response:
    body = await request.body()
    if len(body) > _MAX_REQUEST_BYTES:
        return JSONResponse({"detail": "请求内容过大。"}, status_code=413)
    headers = {
        name: request.headers[name]
        for name in (
            "accept",
            "accept-language",
            "content-type",
            "if-none-match",
            "if-modified-since",
            "user-agent",
        )
        if name in request.headers
    }
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
                    request.url.query if asset_path else "",
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

        return StreamingResponse(
            _event_stream(),
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=None,
        )
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
    return Response(
        content=content if request.method != "HEAD" else b"",
        status_code=upstream.status_code,
        headers=response_headers,
    )


async def _relay_websocket(
    websocket: WebSocket,
    upstream_url: str,
) -> None:
    import websockets

    try:
        parsed_upstream = urlsplit(upstream_url)
        upstream_origin = (
            f"{'https' if parsed_upstream.scheme == 'wss' else 'http'}"
            f"://{parsed_upstream.netloc}"
        )
        requested_protocols = [
            value.strip()
            for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
            if value.strip()
        ]
        upstream = await websockets.connect(
            upstream_url,
            origin=cast(Any, upstream_origin),
            subprotocols=cast(Any, requested_protocols or None),
            open_timeout=_PROXY_TIMEOUT_SECONDS,
            close_timeout=5,
            max_size=_MAX_WEBSOCKET_MESSAGE_BYTES,
        )
    except Exception:  # noqa: BLE001 - WebSocket transport boundary
        await websocket.close(code=1011, reason="agent connection failed")
        return
    await websocket.accept(subprotocol=upstream.subprotocol)

    async def _browser_to_upstream() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            value = message.get("bytes")
            if value is None:
                value = message.get("text")
            if value is not None:
                await upstream.send(value)

    async def _upstream_to_browser() -> None:
        async for value in upstream:
            if isinstance(value, bytes):
                await websocket.send_bytes(value)
            else:
                await websocket.send_text(value)

    tasks = {
        asyncio.create_task(_browser_to_upstream()),
        asyncio.create_task(_upstream_to_browser()),
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            with contextlib.suppress(
                WebSocketDisconnect, RuntimeError, ConnectionError
            ):
                task.result()
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    finally:
        await upstream.close()
        with contextlib.suppress(RuntimeError):
            await websocket.close()


def mount_embedded_agent_routes(
    app: Any,
    service: EmbeddedAgentService,
    owner_resolver: Callable[[Any], str],
    proxy_owner_resolver: Callable[[Any], str | None] | None = None,
) -> None:
    """Mount Session lifecycle and same-origin iframe proxy routes."""
    resolve_proxy_owner = proxy_owner_resolver or owner_resolver

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
            session = await service.start(kind, owner_id)
        except SandboxError as error:
            raise _http_error(error) from error
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

    @app.delete("/web/{kind}/sessions/{session_id}")
    async def _close(kind: str, session_id: str, request: Request) -> Response:
        owner_id = owner_resolver(request)
        try:
            await service.close(kind, session_id, owner_id)
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
            target = service.resolve(kind, session_id, owner_id, token, surface)
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
            target = service.resolve(kind, session_id, owner_id, token, surface)
        except (HTTPException, PermissionError, SandboxError):
            await websocket.close(code=1008, reason="invalid capability")
            return
        upstream = _upstream_url(target, asset_path, websocket.url.query)
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
        await _relay_websocket(websocket, upstream)

    app.router.on_shutdown.append(service.close_all)


__all__ = [
    "DEFINITIONS",
    "EmbeddedAgentService",
    "mount_embedded_agent_routes",
]
