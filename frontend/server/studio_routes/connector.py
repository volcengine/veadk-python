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

"""Persistent outbound Studio BFF client for Runtime dynamic HTTP routes."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from frontend.server.studio_routes.registry import (
    StudioRouteExecutionError,
    StudioRouteRegistry,
)
from veadk.integrations.agentkit.studio_routes.protocol import (
    ROUTE_CAPABILITIES_PATH,
    ROUTE_CHANNEL_PATH,
    ROUTE_HTTP_CHANNEL_PATH,
    ROUTE_HTTP_MESSAGE_PATH,
    ROUTE_PROTOCOL_VERSION,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class StudioRouteChannelError(RuntimeError):
    """A safe reverse-route connection or protocol failure."""


def _endpoint_url(endpoint: str, path: str, *, websocket: bool = False) -> str:
    parsed = urlsplit(endpoint)
    allowed_schemes = {"http", "https", "ws", "wss"} if websocket else {"http", "https"}
    if parsed.scheme not in allowed_schemes or not parsed.netloc:
        raise StudioRouteChannelError("Runtime endpoint is not a valid HTTP(S) URL.")
    if websocket:
        scheme = "wss" if parsed.scheme in {"https", "wss"} else "ws"
    else:
        scheme = parsed.scheme
    base_path = parsed.path.rstrip("/")
    return urlunsplit((scheme, parsed.netloc, f"{base_path}{path}", parsed.query, ""))


def _headers(authorization: str) -> dict[str, str]:
    headers = {"Authorization": authorization} if authorization else {}
    channel_token = os.getenv("VEADK_STUDIO_CHANNEL_TOKEN", "").strip()
    if channel_token:
        headers["X-VeADK-Studio-Channel-Token"] = channel_token
    return headers


async def runtime_supports_bff_routes(
    *,
    endpoint: str,
    authorization: str,
) -> bool:
    """Return whether this Runtime explicitly enables Studio dynamic routes."""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5)) as client:
            response = await client.get(
                _endpoint_url(endpoint, ROUTE_CAPABILITIES_PATH),
                headers=_headers(authorization),
            )
    except (httpx.ConnectError, httpx.TimeoutException) as error:
        raise StudioRouteChannelError(
            "Unable to query the Runtime BFF-route capability."
        ) from error
    if response.status_code == 404:
        return False
    if response.status_code >= 400:
        raise StudioRouteChannelError(
            "Runtime rejected the BFF-route capability query "
            f"(HTTP {response.status_code})."
        )
    try:
        capability = response.json()
    except ValueError as error:
        raise StudioRouteChannelError(
            "Runtime returned an invalid BFF-route capability response."
        ) from error
    if not isinstance(capability, dict) or not isinstance(
        capability.get("enabled"), bool
    ):
        raise StudioRouteChannelError(
            "Runtime returned an invalid BFF-route capability response."
        )
    if not capability["enabled"]:
        return False
    if capability.get("protocol") != ROUTE_PROTOCOL_VERSION:
        raise StudioRouteChannelError(
            "Runtime advertises an incompatible BFF-route protocol."
        )
    transports = capability.get("transports")
    if not isinstance(transports, list) or not {
        "websocket",
        "http-sse",
    }.intersection(transports):
        raise StudioRouteChannelError(
            "Runtime enabled BFF routes without a supported transport."
        )
    route_modes = capability.get("route_modes")
    if not isinstance(route_modes, list) or not {
        "exact",
        "segment-template",
    }.issubset(set(route_modes)):
        raise StudioRouteChannelError(
            "Runtime enabled BFF routes without the required route modes."
        )
    return True


async def _receive_expected_message(
    receive_message: Callable[[], Awaitable[dict[str, Any]]],
    expected_type: str,
) -> dict[str, Any]:
    message = await asyncio.wait_for(receive_message(), timeout=15)
    if not isinstance(message, dict) or message.get("type") != expected_type:
        detail = (
            message.get("error") if isinstance(message, dict) else "invalid message"
        )
        raise StudioRouteChannelError(
            f"Expected {expected_type} from Runtime route channel: {detail}"
        )
    return message


class _RouteCallExecutor:
    def __init__(
        self,
        *,
        registry: StudioRouteRegistry,
        send_message: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.registry = registry
        self._send_message = send_message
        self._send_lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def send(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._send_message(message)

    async def _execute_route(self, message: dict[str, Any]) -> None:
        request_id = str(message.get("request_id") or "")
        revision = str(message.get("catalog_revision") or "")
        try:
            if revision != self.registry.revision:
                raise StudioRouteExecutionError("Studio route catalog mismatch.")
            request = message.get("request")
            if not isinstance(request, dict):
                raise StudioRouteExecutionError(
                    "Studio route request must be an object."
                )
            route_id = str(message.get("route_id") or "")
            manifest = next(
                (item for item in self.registry.manifests() if item["id"] == route_id),
                None,
            )
            if manifest is None:
                raise StudioRouteExecutionError(
                    f"Studio route handler is unavailable: {route_id}"
                )
            response = await self.registry.execute(
                route_id=route_id,
                handler_revision=str(manifest["handler_revision"]),
                request=request,
            )
            serializable_response = {
                "status": response.status,
                "headers": response.headers,
                "body": response.body,
            }
            json.dumps(serializable_response, ensure_ascii=False)
        except StudioRouteExecutionError as error:
            await self.send(
                {
                    "type": "route.error",
                    "request_id": request_id,
                    "catalog_revision": revision,
                    "code": "handler_unavailable",
                    "message": str(error),
                }
            )
            return
        except Exception:  # noqa: BLE001 - local handler safety boundary
            logger.exception(
                "Studio route execution failed route_id=%s request_id=%s",
                message.get("route_id"),
                request_id,
            )
            await self.send(
                {
                    "type": "route.error",
                    "request_id": request_id,
                    "catalog_revision": revision,
                    "code": "handler_failed",
                    "message": "Studio BFF route execution failed.",
                }
            )
            return
        await self.send(
            {
                "type": "route.result",
                "request_id": request_id,
                "catalog_revision": revision,
                "response": serializable_response,
            }
        )

    def _task_done(self, request_id: str, task: asyncio.Task[None]) -> None:
        self._tasks.pop(request_id, None)
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "Studio route result delivery failed request_id=%s error=%s",
                request_id,
                task.exception(),
            )

    async def handle(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "route.call":
            request_id = str(message.get("request_id") or "")
            if not request_id or request_id in self._tasks:
                raise StudioRouteChannelError(
                    "Runtime sent an invalid or duplicate route request_id."
                )
            task = asyncio.create_task(self._execute_route(message))
            self._tasks[request_id] = task
            task.add_done_callback(
                lambda completed, key=request_id: self._task_done(key, completed)
            )
        elif message_type == "route.cancel":
            request_id = str(message.get("request_id") or "")
            task = self._tasks.get(request_id)
            if task is not None:
                task.cancel()
        elif message_type == "ping":
            await self.send({"type": "pong"})
        elif message_type == "channel.error":
            raise StudioRouteChannelError(
                str(message.get("error") or "Runtime route channel failed.")
            )
        else:
            raise StudioRouteChannelError(
                f"Runtime sent an unsupported route-channel message: {message_type}"
            )

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


def _invalid_status_code(error: InvalidStatus) -> int | None:
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


async def _serve_websocket(
    *,
    endpoint: str,
    headers: dict[str, str],
    registry: StudioRouteRegistry,
    studio_instance_id: str,
    on_ready: Callable[[], None],
) -> None:
    websocket = await connect(
        _endpoint_url(endpoint, ROUTE_CHANNEL_PATH, websocket=True),
        additional_headers=headers,
        max_size=2 * 1024 * 1024,
        ping_interval=20,
        ping_timeout=20,
        open_timeout=10,
    )
    executor: _RouteCallExecutor | None = None
    try:

        async def receive_message() -> dict[str, Any]:
            raw = await websocket.recv()
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise StudioRouteChannelError(
                    "Runtime sent a non-object route-channel message."
                )
            return message

        async def send_message(message: dict[str, Any]) -> None:
            await websocket.send(json.dumps(message, ensure_ascii=False))

        executor = _RouteCallExecutor(registry=registry, send_message=send_message)
        await send_message(
            {
                "type": "channel.hello",
                "protocol": ROUTE_PROTOCOL_VERSION,
                "studio_instance_id": studio_instance_id,
                "provider_id": "local-studio-bff",
            }
        )
        ready = await _receive_expected_message(receive_message, "channel.ready")
        if ready.get("protocol") != ROUTE_PROTOCOL_VERSION:
            raise StudioRouteChannelError(
                "Runtime acknowledged an incompatible BFF-route protocol."
            )
        await send_message(
            {
                "type": "route.catalog.replace",
                "revision": registry.revision,
                "routes": registry.manifests(),
            }
        )
        ack = await _receive_expected_message(receive_message, "route.catalog.ack")
        if ack.get("revision") != registry.revision:
            raise StudioRouteChannelError(
                "Runtime acknowledged the wrong BFF-route catalog revision."
            )
        on_ready()
        while True:
            await executor.handle(await receive_message())
    finally:
        if executor is not None:
            await executor.close()
        await websocket.close()


async def _serve_http_sse(
    *,
    endpoint: str,
    headers: dict[str, str],
    registry: StudioRouteRegistry,
    studio_instance_id: str,
    on_ready: Callable[[], None],
) -> None:
    channel_id = uuid4().hex
    message_path = ROUTE_HTTP_MESSAGE_PATH.format(channel_id=channel_id)
    client = httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(None, connect=10),
    )
    response: httpx.Response | None = None
    executor: _RouteCallExecutor | None = None
    try:
        request = client.build_request(
            "POST",
            _endpoint_url(endpoint, ROUTE_HTTP_CHANNEL_PATH),
            json={
                "protocol": ROUTE_PROTOCOL_VERSION,
                "channel_id": channel_id,
                "studio_instance_id": studio_instance_id,
                "catalog_revision": registry.revision,
                "routes": registry.manifests(),
            },
        )
        response = await client.send(request, stream=True)
        if response.status_code >= 400:
            detail = (await response.aread()).decode("utf-8", errors="replace")
            raise StudioRouteChannelError(
                "Runtime rejected the Studio route HTTP fallback "
                f"(HTTP {response.status_code}): {detail[:500]}"
            )
        lines = response.aiter_lines()

        async def receive_message() -> dict[str, Any]:
            async for line in lines:
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as error:
                    raise StudioRouteChannelError(
                        "Runtime sent invalid SSE data on the route channel."
                    ) from error
                if not isinstance(message, dict):
                    raise StudioRouteChannelError(
                        "Runtime sent a non-object route-channel message."
                    )
                return message
            raise StudioRouteChannelError("Runtime closed the route HTTP channel.")

        async def send_message(message: dict[str, Any]) -> None:
            result = await client.post(
                _endpoint_url(endpoint, message_path),
                json=message,
                timeout=15,
            )
            if result.status_code >= 400:
                detail = result.text[:500]
                if result.status_code == 404:
                    detail = (
                        "the result POST reached a different Runtime instance; "
                        "configure this demo Runtime with exactly one instance"
                    )
                raise StudioRouteChannelError(
                    "Runtime rejected a Studio route result "
                    f"(HTTP {result.status_code}): {detail}"
                )

        executor = _RouteCallExecutor(registry=registry, send_message=send_message)
        ready = await _receive_expected_message(receive_message, "channel.ready")
        if ready.get("protocol") != ROUTE_PROTOCOL_VERSION:
            raise StudioRouteChannelError(
                "Runtime acknowledged an incompatible BFF-route protocol."
            )
        ack = await _receive_expected_message(receive_message, "route.catalog.ack")
        if ack.get("revision") != registry.revision:
            raise StudioRouteChannelError(
                "Runtime acknowledged the wrong BFF-route catalog revision."
            )
        logger.info(
            "Studio route channel using HTTP fallback endpoint_host=%s",
            urlsplit(endpoint).netloc,
        )
        on_ready()
        while True:
            await executor.handle(await receive_message())
    finally:
        if executor is not None:
            await executor.close()
        if response is not None:
            await response.aclose()
        await client.aclose()


async def serve_studio_route_channel(
    *,
    endpoint: str,
    authorization: str,
    registry: StudioRouteRegistry,
    on_ready: Callable[[], None],
) -> None:
    """Serve one persistent route channel until disconnected or cancelled."""

    if not registry.enabled:
        raise StudioRouteChannelError("Studio route registry is empty.")
    studio_instance_id = os.getenv("VEADK_STUDIO_INSTANCE_ID", "").strip()
    if not studio_instance_id:
        studio_instance_id = f"studio-{os.getpid()}"
    headers = _headers(authorization)
    try:
        await _serve_websocket(
            endpoint=endpoint,
            headers=headers,
            registry=registry,
            studio_instance_id=studio_instance_id,
            on_ready=on_ready,
        )
    except InvalidStatus as error:
        status_code = _invalid_status_code(error)
        if status_code not in {200, 404, 405, 426, 501}:
            raise
        logger.warning(
            "Runtime gateway did not upgrade the Studio route WebSocket "
            "(HTTP %s); falling back to streaming HTTP",
            status_code,
        )
        await _serve_http_sse(
            endpoint=endpoint,
            headers=headers,
            registry=registry,
            studio_instance_id=studio_instance_id,
            on_ready=on_ready,
        )


@dataclass
class _ManagedChannel:
    endpoint: str
    authorization: str
    connected: asyncio.Event
    task: asyncio.Task[None]


class StudioRouteChannelManager:
    """Keep one persistent BFF route provider connection per Runtime."""

    def __init__(self, registry: StudioRouteRegistry) -> None:
        self.registry = registry
        self._channels: dict[str, _ManagedChannel] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def ensure_connected(
        self,
        *,
        runtime_id: str,
        endpoint: str,
        authorization: str,
    ) -> bool:
        if self._closed:
            raise StudioRouteChannelError("Studio route channel manager is closed.")
        if not self.registry.enabled:
            return False
        if not await runtime_supports_bff_routes(
            endpoint=endpoint,
            authorization=authorization,
        ):
            return False
        async with self._lock:
            managed = self._channels.get(runtime_id)
            if managed is not None and (
                managed.endpoint != endpoint
                or managed.authorization != authorization
                or managed.task.done()
            ):
                managed.task.cancel()
                await asyncio.gather(managed.task, return_exceptions=True)
                self._channels.pop(runtime_id, None)
                managed = None
            if managed is None:
                connected = asyncio.Event()
                task = asyncio.create_task(
                    self._maintain(
                        runtime_id=runtime_id,
                        endpoint=endpoint,
                        authorization=authorization,
                        connected=connected,
                    )
                )
                managed = _ManagedChannel(
                    endpoint=endpoint,
                    authorization=authorization,
                    connected=connected,
                    task=task,
                )
                self._channels[runtime_id] = managed
        try:
            await asyncio.wait_for(managed.connected.wait(), timeout=20)
        except TimeoutError as error:
            raise StudioRouteChannelError(
                "Timed out while connecting the Runtime BFF-route channel."
            ) from error
        return True

    async def _maintain(
        self,
        *,
        runtime_id: str,
        endpoint: str,
        authorization: str,
        connected: asyncio.Event,
    ) -> None:
        retry_delay = 1.0
        while True:
            try:
                await serve_studio_route_channel(
                    endpoint=endpoint,
                    authorization=authorization,
                    registry=self.registry,
                    on_ready=connected.set,
                )
                raise StudioRouteChannelError("Runtime route channel closed.")
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - reconnect boundary
                connected.clear()
                logger.warning(
                    "Studio route channel disconnected runtime_id=%s "
                    "endpoint_host=%s retry_in=%.1fs error=%s",
                    runtime_id,
                    urlsplit(endpoint).netloc,
                    retry_delay,
                    error,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 10.0)

    def connected(self, runtime_id: str) -> bool:
        managed = self._channels.get(runtime_id)
        return bool(managed and managed.connected.is_set() and not managed.task.done())

    async def close(self) -> None:
        self._closed = True
        tasks = [managed.task for managed in self._channels.values()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._channels.clear()
