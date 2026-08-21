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

"""Runtime dispatcher and reverse-RPC control plane for Studio BFF routes."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from veadk.integrations.agentkit.studio_routes.protocol import (
    MAX_ROUTE_REQUEST_BODY_BYTES,
    MAX_ROUTE_RESPONSE_BODY_BYTES,
    ROUTE_CAPABILITIES_PATH,
    ROUTE_CHANNEL_PATH,
    ROUTE_HTTP_CHANNEL_PATH,
    ROUTE_HTTP_MESSAGE_PATH,
    ROUTE_PROTOCOL_VERSION,
    RouteCatalogSnapshot,
    StudioRouteManifest,
    match_route_path,
    validate_route_catalog,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

RouteChannelSender = Callable[[dict[str, Any]], Awaitable[None]]


class _RouteCallFailure(RuntimeError):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


@dataclass
class _PendingRouteCall:
    future: asyncio.Future[dict[str, Any]]
    catalog_revision: str


@dataclass(frozen=True)
class _MatchedRoute:
    manifest: StudioRouteManifest
    path_params: dict[str, str]


class StudioRouteHost:
    """Own the effective route catalog and its currently connected provider."""

    def __init__(self, *, native_route_keys: set[tuple[str, str]]) -> None:
        self.native_route_keys = native_route_keys
        self.catalog: RouteCatalogSnapshot | None = None
        self.provider: _StudioRouteConnection | None = None
        self._route_by_key: dict[tuple[str, str], StudioRouteManifest] = {}
        self._template_routes: tuple[StudioRouteManifest, ...] = ()
        self._catalog_lock = asyncio.Lock()

    async def install_catalog(
        self,
        connection: _StudioRouteConnection,
        snapshot: RouteCatalogSnapshot,
    ) -> None:
        route_by_key = {(route.method, route.path): route for route in snapshot.routes}
        template_routes = tuple(route for route in snapshot.routes if "{" in route.path)
        async with self._catalog_lock:
            self.catalog = snapshot
            self.provider = connection
            self._route_by_key = route_by_key
            self._template_routes = template_routes

    async def provider_disconnected(self, connection: _StudioRouteConnection) -> None:
        async with self._catalog_lock:
            if self.provider is connection:
                self.provider = None

    def route_for(self, method: str, path: str) -> _MatchedRoute | None:
        exact = self._route_by_key.get((method.upper(), path))
        if exact is not None:
            return _MatchedRoute(manifest=exact, path_params={})
        for route in self._template_routes:
            if route.method != method.upper():
                continue
            path_params = match_route_path(route.path, path)
            if path_params is not None:
                return _MatchedRoute(manifest=route, path_params=path_params)
        return None

    def methods_for(self, path: str) -> set[str]:
        methods = {
            method for method, route_path in self._route_by_key if route_path == path
        }
        methods.update(
            route.method
            for route in self._template_routes
            if match_route_path(route.path, path) is not None
        )
        return methods

    async def execute(
        self,
        *,
        route: StudioRouteManifest,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        provider = self.provider
        catalog = self.catalog
        if provider is None or catalog is None:
            raise _RouteCallFailure(503, "studio_route_provider_offline")
        return await provider.call_route(
            manifest=route,
            catalog_revision=catalog.revision,
            request_payload=request_payload,
        )


class StudioDynamicRouteMiddleware:
    """Intercept validated Studio routes while leaving other ASGI scopes intact."""

    def __init__(self, app: ASGIApp, *, host: StudioRouteHost) -> None:
        self.app = app
        self.host = host

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method") or "GET").upper()
        path = str(scope.get("path") or "/")
        matched_route = self.host.route_for(method, path)
        if matched_route is None:
            allowed = self.host.methods_for(path)
            if allowed:
                await JSONResponse(
                    {"detail": "studio_route_method_not_allowed"},
                    status_code=405,
                    headers={"Allow": ", ".join(sorted(allowed))},
                )(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        try:
            request_payload = await _read_request(scope, receive)
            request_payload["path_params"] = matched_route.path_params
            route_response = await self.host.execute(
                route=matched_route.manifest,
                request_payload=request_payload,
            )
            response = _response_from_route_result(route_response)
        except _RouteCallFailure as error:
            response = JSONResponse(
                {"detail": error.code},
                status_code=error.status_code,
            )
        await response(scope, receive, send)


async def _read_request(scope: Scope, receive: Receive) -> dict[str, Any]:
    body = bytearray()
    more_body = True
    while more_body:
        message = await receive()
        if message["type"] == "http.disconnect":
            raise _RouteCallFailure(499, "studio_route_client_disconnected")
        if message["type"] != "http.request":
            continue
        body.extend(message.get("body", b""))
        if len(body) > MAX_ROUTE_REQUEST_BODY_BYTES:
            raise _RouteCallFailure(413, "studio_route_request_too_large")
        more_body = bool(message.get("more_body", False))

    headers: dict[str, str] = {}
    allowed_headers = {"accept", "content-type", "x-request-id"}
    for raw_name, raw_value in scope.get("headers", []):
        name = raw_name.decode("latin-1").lower()
        if name in allowed_headers:
            headers[name] = raw_value.decode("latin-1")
    return {
        "method": str(scope.get("method") or "GET").upper(),
        "path": str(scope.get("path") or "/"),
        "query_string": bytes(scope.get("query_string") or b"").decode("latin-1"),
        "headers": headers,
        "body": bytes(body).decode("utf-8", errors="replace") if body else None,
    }


def _response_from_route_result(payload: dict[str, Any]) -> Response:
    status = payload.get("status", 200)
    if not isinstance(status, int) or not 200 <= status <= 599:
        raise _RouteCallFailure(502, "studio_route_invalid_response")
    raw_headers = payload.get("headers") or {}
    if not isinstance(raw_headers, dict):
        raise _RouteCallFailure(502, "studio_route_invalid_response")
    headers = {
        str(name).lower(): str(value)
        for name, value in raw_headers.items()
        if str(name).lower() in {"content-type", "cache-control", "x-request-id"}
    }
    body = payload.get("body")
    if isinstance(body, str):
        encoded = body.encode("utf-8")
        if len(encoded) > MAX_ROUTE_RESPONSE_BODY_BYTES:
            raise _RouteCallFailure(502, "studio_route_response_too_large")
        return Response(
            content=encoded,
            status_code=status,
            headers=headers,
            media_type=None if "content-type" in headers else "text/plain",
        )
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(encoded) > MAX_ROUTE_RESPONSE_BODY_BYTES:
        raise _RouteCallFailure(502, "studio_route_response_too_large")
    headers.pop("content-type", None)
    return Response(
        content=encoded,
        status_code=status,
        headers=headers,
        media_type="application/json",
    )


class _StudioRouteConnection:
    def __init__(self, *, sender: RouteChannelSender, host: StudioRouteHost) -> None:
        self._sender = sender
        self.host = host
        self.connection_id = uuid4().hex
        self.pending_calls: dict[str, _PendingRouteCall] = {}
        self._send_lock = asyncio.Lock()
        self._closed = False

    async def send(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._sender(message)

    async def call_route(
        self,
        *,
        manifest: StudioRouteManifest,
        catalog_revision: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self._closed:
            raise _RouteCallFailure(503, "studio_route_provider_offline")
        request_id = uuid4().hex
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self.pending_calls[request_id] = _PendingRouteCall(
            future=future,
            catalog_revision=catalog_revision,
        )
        try:
            await self.send(
                {
                    "type": "route.call",
                    "request_id": request_id,
                    "route_id": manifest.id,
                    "catalog_revision": catalog_revision,
                    "request": request_payload,
                    "deadline_ms": manifest.timeout_ms,
                }
            )
            try:
                result = await asyncio.wait_for(
                    future,
                    timeout=manifest.timeout_ms / 1000,
                )
            except TimeoutError as error:
                await self.send(
                    {
                        "type": "route.cancel",
                        "request_id": request_id,
                        "reason": "timeout",
                    }
                )
                raise _RouteCallFailure(504, "studio_route_timeout") from error
        finally:
            self.pending_calls.pop(request_id, None)

        message_type = result.get("type")
        if message_type == "route.result" and isinstance(result.get("response"), dict):
            return result["response"]
        if message_type == "route.disconnected":
            raise _RouteCallFailure(503, "studio_route_provider_offline")
        raise _RouteCallFailure(502, "studio_route_execution_error")

    async def _replace_catalog(self, message: dict[str, Any]) -> None:
        revision = str(message.get("revision") or "")
        try:
            snapshot = validate_route_catalog(
                revision=revision,
                raw_routes=message.get("routes"),
                native_route_keys=self.host.native_route_keys,
            )
        except (TypeError, ValueError, ValidationError) as error:
            await self.send(
                {
                    "type": "route.catalog.nack",
                    "revision": revision,
                    "error": str(error),
                }
            )
            return
        await self.host.install_catalog(self, snapshot)
        await self.send(
            {
                "type": "route.catalog.ack",
                "revision": revision,
                "active_routes": len(snapshot.routes),
            }
        )

    async def _resolve_result(self, message: dict[str, Any]) -> None:
        request_id = str(message.get("request_id") or "")
        pending = self.pending_calls.get(request_id)
        if pending is None or pending.future.done():
            return
        if message.get("catalog_revision") != pending.catalog_revision:
            pending.future.set_result(
                {
                    "type": "route.error",
                    "code": "route_result_context_mismatch",
                }
            )
            return
        pending.future.set_result(message)

    async def handle_message(self, message: object) -> None:
        if not isinstance(message, dict):
            await self.send(
                {"type": "channel.error", "error": "channel message must be an object"}
            )
            return
        message_type = message.get("type")
        if message_type == "route.catalog.replace":
            await self._replace_catalog(message)
        elif message_type in {"route.result", "route.error"}:
            await self._resolve_result(message)
        elif message_type == "ping":
            await self.send({"type": "pong"})
        elif message_type != "pong":
            await self.send(
                {
                    "type": "channel.error",
                    "error": f"unsupported message type: {message_type}",
                }
            )

    async def receive_loop(self, websocket: WebSocket) -> None:
        while True:
            await self.handle_message(await websocket.receive_json())

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self.host.provider_disconnected(self)
        for pending in self.pending_calls.values():
            if not pending.future.done():
                pending.future.set_result({"type": "route.disconnected"})
        self.pending_calls.clear()


def _native_route_keys(app: FastAPI) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for route in app.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not isinstance(path, str) or not methods:
            continue
        for method in methods:
            keys.add((str(method).upper(), path))
    return keys


def mount_studio_route_host(*, app: FastAPI, enabled: bool = False) -> StudioRouteHost:
    """Mount the Runtime half of Studio's persistent reverse-route channel."""

    host = StudioRouteHost(native_route_keys=_native_route_keys(app))
    setattr(app.state, "studio_route_host", host)
    setattr(app.state, "studio_route_host_enabled", enabled)

    def _promote_endpoints(*endpoints: Callable[..., Any]) -> None:
        for endpoint in reversed(endpoints):
            route = next(
                item
                for item in app.router.routes
                if getattr(item, "endpoint", None) is endpoint
            )
            app.router.routes.remove(route)
            app.router.routes.insert(0, route)

    @app.get(ROUTE_CAPABILITIES_PATH)
    async def studio_route_capabilities() -> dict[str, Any]:
        return {
            "enabled": enabled,
            "protocol": ROUTE_PROTOCOL_VERSION,
            "transports": ["websocket", "http-sse"] if enabled else [],
            "route_modes": ["exact", "segment-template"] if enabled else [],
        }

    _promote_endpoints(studio_route_capabilities)
    if not enabled:
        return host

    # Keep the dynamic dispatcher inside AgentKit's existing authentication and
    # identity middleware. ``add_middleware`` inserts at the outer edge, so move
    # the newly added item to the inner edge before the stack is first built.
    app.add_middleware(StudioDynamicRouteMiddleware, host=host)
    route_dispatcher_middleware = app.user_middleware.pop(0)
    app.user_middleware.append(route_dispatcher_middleware)
    http_connections: dict[str, _StudioRouteConnection] = {}
    http_connections_lock = asyncio.Lock()

    @app.websocket(ROUTE_CHANNEL_PATH)
    async def studio_route_channel(websocket: WebSocket) -> None:
        await websocket.accept()
        connection: _StudioRouteConnection | None = None
        try:
            hello = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            if not isinstance(hello, dict) or hello.get("type") != "channel.hello":
                await websocket.close(code=4400, reason="channel.hello required")
                return
            if hello.get("protocol") != ROUTE_PROTOCOL_VERSION:
                await websocket.close(code=4400, reason="unsupported protocol")
                return
            connection = _StudioRouteConnection(sender=websocket.send_json, host=host)
            await connection.send(
                {
                    "type": "channel.ready",
                    "protocol": ROUTE_PROTOCOL_VERSION,
                    "connection_id": connection.connection_id,
                    "instance_id": f"runtime-{os.getpid()}",
                    "transport": "websocket",
                }
            )
            await connection.receive_loop(websocket)
        except (WebSocketDisconnect, RuntimeError):
            pass
        except TimeoutError:
            await websocket.close(code=4408, reason="channel.hello timeout")
        finally:
            if connection is not None:
                await connection.close()

    @app.post(ROUTE_HTTP_CHANNEL_PATH)
    async def studio_route_http_channel(request: Request) -> StreamingResponse:
        try:
            body = await request.json()
        except ValueError as error:
            raise HTTPException(status_code=400, detail="invalid JSON body") from error
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        if body.get("protocol") != ROUTE_PROTOCOL_VERSION:
            raise HTTPException(status_code=400, detail="unsupported protocol")
        channel_id = str(body.get("channel_id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", channel_id):
            raise HTTPException(status_code=400, detail="invalid channel_id")

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=256)

        async def send_message(message: dict[str, Any]) -> None:
            await queue.put(message)

        connection = _StudioRouteConnection(sender=send_message, host=host)
        async with http_connections_lock:
            if channel_id in http_connections:
                raise HTTPException(status_code=409, detail="channel_id is active")
            http_connections[channel_id] = connection
        await connection.send(
            {
                "type": "channel.ready",
                "protocol": ROUTE_PROTOCOL_VERSION,
                "connection_id": connection.connection_id,
                "instance_id": f"runtime-{os.getpid()}",
                "transport": "http-sse",
            }
        )
        await connection.handle_message(
            {
                "type": "route.catalog.replace",
                "revision": body.get("catalog_revision"),
                "routes": body.get("routes"),
            }
        )

        async def event_stream():
            try:
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield b": keepalive\n\n"
                        continue
                    if message is None:
                        return
                    yield (
                        "data: "
                        + json.dumps(message, ensure_ascii=False, separators=(",", ":"))
                        + "\n\n"
                    ).encode("utf-8")
            finally:
                async with http_connections_lock:
                    if http_connections.get(channel_id) is connection:
                        http_connections.pop(channel_id, None)
                await connection.close()

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post(ROUTE_HTTP_MESSAGE_PATH)
    async def studio_route_http_message(
        channel_id: str,
        request: Request,
    ) -> dict[str, bool]:
        async with http_connections_lock:
            connection = http_connections.get(channel_id)
        if connection is None:
            raise HTTPException(
                status_code=404,
                detail="Studio route channel is not on this Runtime instance",
            )
        try:
            message = await request.json()
        except ValueError as error:
            raise HTTPException(status_code=400, detail="invalid JSON body") from error
        if not isinstance(message, dict) or message.get("type") not in {
            "route.result",
            "route.error",
            "pong",
        }:
            raise HTTPException(status_code=400, detail="unsupported channel message")
        await connection.handle_message(message)
        return {"accepted": True}

    _promote_endpoints(
        studio_route_channel,
        studio_route_http_channel,
        studio_route_http_message,
    )
    return host
