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

"""Runtime endpoints for Studio-owned tools and reverse Agent runs."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from veadk.integrations.agentkit.studio_channel.protocol import (
    CAPABILITIES_SUFFIX,
    DEFAULT_CHANNEL_PATH,
    HTTP_MESSAGE_SUFFIX,
    HTTP_RUN_SUFFIX,
    PROTOCOL_VERSION,
    CatalogSnapshot,
    StudioToolManifest,
    validate_catalog,
)
from veadk.integrations.agentkit.studio_channel.tool import (
    StudioRemoteTool,
    bind_studio_tools,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

StudioChannelRunHandler = Callable[[dict[str, Any]], AsyncIterator[dict[str, Any]]]
StudioChannelSender = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class _PendingToolCall:
    future: asyncio.Future[dict[str, Any]]
    run_id: str
    scope_id: str
    catalog_revision: str


class _StudioChannelConnection:
    def __init__(
        self,
        *,
        sender: StudioChannelSender,
        run_handler: StudioChannelRunHandler,
        reserved_tool_names: set[str],
    ) -> None:
        self._sender = sender
        self.run_handler = run_handler
        self.reserved_tool_names = reserved_tool_names
        self.connection_id = uuid4().hex
        self.catalogs: dict[str, CatalogSnapshot] = {}
        self.pending_calls: dict[str, _PendingToolCall] = {}
        self.run_tasks: dict[str, asyncio.Task[None]] = {}
        self._send_lock = asyncio.Lock()

    async def send(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._sender(message)

    async def call_tool(
        self,
        *,
        run_id: str,
        scope_id: str,
        catalog_revision: str,
        manifest: StudioToolManifest,
        arguments: dict[str, Any],
    ) -> Any:
        request_id = uuid4().hex
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self.pending_calls[request_id] = _PendingToolCall(
            future=future,
            run_id=run_id,
            scope_id=scope_id,
            catalog_revision=catalog_revision,
        )
        await self.send(
            {
                "type": "tool.call",
                "request_id": request_id,
                "run_id": run_id,
                "scope_id": scope_id,
                "catalog_revision": catalog_revision,
                "tool_name": manifest.name,
                "executor_revision": manifest.executor_revision,
                "arguments": arguments,
                "deadline_ms": manifest.timeout_ms,
            }
        )
        try:
            result = await asyncio.wait_for(
                future,
                timeout=manifest.timeout_ms / 1000,
            )
        except TimeoutError:
            await self.send(
                {
                    "type": "tool.cancel",
                    "request_id": request_id,
                    "run_id": run_id,
                }
            )
            return {"status": "timeout", "error": "Studio tool timed out."}
        finally:
            self.pending_calls.pop(request_id, None)

        if result.get("status") == "success":
            return result.get("content")
        return {
            "status": result.get("status", "error"),
            "error": result.get("error") or "Studio tool execution failed.",
        }

    async def _replace_catalog(self, message: dict[str, Any]) -> None:
        scope_id = str(message.get("scope_id") or "")
        revision = str(message.get("revision") or "")
        try:
            snapshot = validate_catalog(
                scope_id=scope_id,
                revision=revision,
                raw_tools=message.get("tools"),
                reserved_tool_names=self.reserved_tool_names,
            )
        except (TypeError, ValueError, ValidationError) as error:
            await self.send(
                {
                    "type": "catalog.reject",
                    "scope_id": scope_id,
                    "revision": revision,
                    "error": str(error),
                }
            )
            return
        self.catalogs[scope_id] = snapshot
        await self.send(
            {
                "type": "catalog.ack",
                "scope_id": scope_id,
                "revision": revision,
            }
        )

    async def _start_run(self, message: dict[str, Any]) -> None:
        run_id = str(message.get("run_id") or "")
        scope_id = str(message.get("scope_id") or "")
        revision = str(message.get("catalog_revision") or "")
        payload = message.get("payload")
        snapshot = self.catalogs.get(scope_id)
        if not run_id or not isinstance(payload, dict):
            await self._send_error("run.start requires run_id and object payload")
            return
        if run_id in self.run_tasks:
            await self._send_error("run_id is already active", run_id=run_id)
            return
        if snapshot is None or snapshot.revision != revision:
            await self._send_error(
                "run.start references an unacknowledged catalog revision",
                run_id=run_id,
            )
            return
        tools = [
            StudioRemoteTool(
                manifest=manifest,
                dispatcher=self,
                run_id=run_id,
                scope_id=scope_id,
                catalog_revision=revision,
            )
            for manifest in snapshot.tools
        ]
        task = asyncio.create_task(
            self._execute_run(
                run_id=run_id,
                request_id=str(message.get("request_id") or ""),
                payload=payload,
                tools=tools,
            )
        )
        self.run_tasks[run_id] = task

    async def _execute_run(
        self,
        *,
        run_id: str,
        request_id: str,
        payload: dict[str, Any],
        tools: list[StudioRemoteTool],
    ) -> None:
        await self.send(
            {"type": "run.started", "request_id": request_id, "run_id": run_id}
        )
        status = "success"
        try:
            with bind_studio_tools(tools):
                async for event in self.run_handler(payload):
                    await self.send(
                        {"type": "run.event", "run_id": run_id, "event": event}
                    )
        except asyncio.CancelledError:
            status = "cancelled"
        except Exception as error:  # noqa: BLE001 - runtime boundary
            status = "error"
            logger.exception("Studio channel run failed run_id=%s", run_id)
            await self.send(
                {
                    "type": "run.event",
                    "run_id": run_id,
                    "event": {"error": str(error)},
                }
            )
        finally:
            await self.send(
                {"type": "run.completed", "run_id": run_id, "status": status}
            )
            self.run_tasks.pop(run_id, None)

    async def _resolve_tool_result(self, message: dict[str, Any]) -> None:
        request_id = str(message.get("request_id") or "")
        pending = self.pending_calls.get(request_id)
        if pending is None or pending.future.done():
            return
        if (
            message.get("run_id") != pending.run_id
            or message.get("scope_id") != pending.scope_id
            or message.get("catalog_revision") != pending.catalog_revision
        ):
            pending.future.set_result(
                {"status": "error", "error": "Studio tool result context mismatch."}
            )
            return
        pending.future.set_result(message)

    async def _cancel_run(self, message: dict[str, Any]) -> None:
        run_id = str(message.get("run_id") or "")
        task = self.run_tasks.get(run_id)
        if task is not None:
            task.cancel()

    async def _send_error(self, error: str, *, run_id: str = "") -> None:
        message = {"type": "channel.error", "error": error}
        if run_id:
            message["run_id"] = run_id
        await self.send(message)

    async def handle_message(self, message: object) -> None:
        if not isinstance(message, dict):
            await self._send_error("channel messages must be JSON objects")
            return
        message_type = message.get("type")
        if message_type == "catalog.replace":
            await self._replace_catalog(message)
        elif message_type == "run.start":
            await self._start_run(message)
        elif message_type == "run.cancel":
            await self._cancel_run(message)
        elif message_type == "tool.result":
            await self._resolve_tool_result(message)
        elif message_type == "ping":
            await self.send({"type": "pong"})
        else:
            await self._send_error(f"unsupported message type: {message_type}")

    async def receive_loop(self, websocket: WebSocket) -> None:
        while True:
            await self.handle_message(await websocket.receive_json())

    async def close(self) -> None:
        tasks = list(self.run_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for pending in self.pending_calls.values():
            if not pending.future.done():
                pending.future.set_result(
                    {
                        "status": "channel_disconnected",
                        "error": "Studio tool channel disconnected.",
                    }
                )
        self.pending_calls.clear()


def mount_studio_channel_routes(
    *,
    app: FastAPI,
    run_handler: StudioChannelRunHandler,
    reserved_tool_names: set[str] | None = None,
    path: str = DEFAULT_CHANNEL_PATH,
    enabled: bool = True,
) -> None:
    """Advertise BFF-tool support and mount RPC routes when explicitly enabled."""

    def _promote_endpoints(*endpoints: Callable[..., Any]) -> None:
        # AgentKit's generated app contains broad fallback routes before
        # integration routes. Starlette matches in declaration order.
        for endpoint in reversed(endpoints):
            route = next(
                item
                for item in app.router.routes
                if getattr(item, "endpoint", None) is endpoint
            )
            app.router.routes.remove(route)
            app.router.routes.insert(0, route)

    @app.get(f"{path}{CAPABILITIES_SUFFIX}")
    async def studio_tool_channel_capabilities() -> dict[str, Any]:
        return {
            "enabled": enabled,
            "protocol": PROTOCOL_VERSION,
            "transports": ["websocket", "http-sse"] if enabled else [],
        }

    _promote_endpoints(studio_tool_channel_capabilities)
    setattr(app.state, "_veadk_studio_channel_enabled", enabled)
    if not enabled:
        return

    reserved = set(reserved_tool_names or ())
    http_connections: dict[str, _StudioChannelConnection] = {}
    http_connections_lock = asyncio.Lock()

    def _has_valid_token(headers: Any) -> bool:
        required_token = os.getenv("VEADK_STUDIO_CHANNEL_TOKEN", "").strip()
        presented_token = headers.get("x-veadk-studio-channel-token", "")
        return not required_token or hmac.compare_digest(
            required_token, presented_token
        )

    @app.websocket(path)
    async def studio_tool_channel(websocket: WebSocket) -> None:
        if not _has_valid_token(websocket.headers):
            await websocket.close(code=4403, reason="invalid Studio channel token")
            return

        await websocket.accept()
        connection: _StudioChannelConnection | None = None
        try:
            hello = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            if not isinstance(hello, dict) or hello.get("type") != "channel.hello":
                await websocket.close(code=4400, reason="channel.hello required")
                return
            if hello.get("protocol") != PROTOCOL_VERSION:
                await websocket.close(code=4400, reason="unsupported protocol")
                return
            connection = _StudioChannelConnection(
                sender=websocket.send_json,
                run_handler=run_handler,
                reserved_tool_names=reserved,
            )
            await connection.send(
                {
                    "type": "channel.ready",
                    "protocol": PROTOCOL_VERSION,
                    "connection_id": connection.connection_id,
                    "limits": {"max_tools": 64, "max_concurrent_runs": 8},
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

    @app.post(f"{path}{HTTP_RUN_SUFFIX}")
    async def studio_tool_http_run(request: Request) -> StreamingResponse:
        """Open an SSE downlink when an API gateway cannot proxy WebSockets."""

        if not _has_valid_token(request.headers):
            raise HTTPException(status_code=403, detail="invalid Studio channel token")
        try:
            body = await request.json()
        except ValueError as error:
            raise HTTPException(status_code=400, detail="invalid JSON body") from error
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        if body.get("protocol") != PROTOCOL_VERSION:
            raise HTTPException(status_code=400, detail="unsupported protocol")

        channel_id = str(body.get("channel_id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", channel_id):
            raise HTTPException(status_code=400, detail="invalid channel_id")
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=256)

        async def send_message(message: dict[str, Any]) -> None:
            await queue.put(message)

        connection = _StudioChannelConnection(
            sender=send_message,
            run_handler=run_handler,
            reserved_tool_names=reserved,
        )
        async with http_connections_lock:
            if channel_id in http_connections:
                raise HTTPException(status_code=409, detail="channel_id is active")
            http_connections[channel_id] = connection

        await connection.send(
            {
                "type": "channel.ready",
                "protocol": PROTOCOL_VERSION,
                "connection_id": connection.connection_id,
                "transport": "http-sse",
                "limits": {"max_tools": 64, "max_concurrent_runs": 1},
            }
        )
        await connection.handle_message(
            {
                "type": "catalog.replace",
                "scope_id": body.get("scope_id"),
                "revision": body.get("catalog_revision"),
                "tools": body.get("tools"),
            }
        )
        scope_id = str(body.get("scope_id") or "")
        revision = str(body.get("catalog_revision") or "")
        if connection.catalogs.get(scope_id) is None:
            await queue.put(None)
        else:
            await connection.handle_message(
                {
                    "type": "run.start",
                    "request_id": body.get("request_id"),
                    "run_id": body.get("run_id"),
                    "scope_id": scope_id,
                    "catalog_revision": revision,
                    "payload": body.get("payload"),
                }
            )
            if str(body.get("run_id") or "") not in connection.run_tasks:
                await queue.put(None)

        async def event_stream() -> AsyncIterator[bytes]:
            try:
                while True:
                    message = await queue.get()
                    if message is None:
                        return
                    yield (
                        "data: "
                        + json.dumps(
                            message,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n\n"
                    ).encode("utf-8")
                    if message.get("type") == "run.completed":
                        return
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

    @app.post(f"{path}{HTTP_MESSAGE_SUFFIX}")
    async def studio_tool_http_message(
        channel_id: str, request: Request
    ) -> dict[str, bool]:
        """Accept tool results and cancellation for one HTTP fallback run."""

        if not _has_valid_token(request.headers):
            raise HTTPException(status_code=403, detail="invalid Studio channel token")
        async with http_connections_lock:
            connection = http_connections.get(channel_id)
        if connection is None:
            raise HTTPException(
                status_code=404,
                detail="Studio HTTP channel is not on this Runtime instance",
            )
        try:
            message = await request.json()
        except ValueError as error:
            raise HTTPException(status_code=400, detail="invalid JSON body") from error
        if not isinstance(message, dict) or message.get("type") not in {
            "tool.result",
            "run.cancel",
            "pong",
        }:
            raise HTTPException(status_code=400, detail="unsupported channel message")
        if message.get("type") != "pong":
            await connection.handle_message(message)
        return {"accepted": True}

    _promote_endpoints(
        studio_tool_channel,
        studio_tool_http_run,
        studio_tool_http_message,
    )

    setattr(app.state, "_veadk_studio_channel_mounted", True)
