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

"""Outbound Studio BFF client for the Runtime reverse-tool channel."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from frontend.server.studio_tools.registry import (
    StudioToolCatalogSnapshot,
    StudioToolExecutionContext,
    StudioToolExecutionError,
)
from veadk.integrations.agentkit.studio_channel.protocol import (
    CAPABILITIES_SUFFIX,
    DEFAULT_CHANNEL_PATH,
    HTTP_MESSAGE_SUFFIX,
    HTTP_RUN_SUFFIX,
    PROTOCOL_VERSION,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

MAX_TOOL_RESULT_BYTES = 128 * 1024
TOOL_RESULT_PREVIEW_BYTES = 64 * 1024


class StudioChannelError(RuntimeError):
    """A connection or protocol failure safe to surface to Studio."""


def _bounded_tool_result(content: Any) -> Any:
    encoded = json.dumps(content, ensure_ascii=False).encode("utf-8")
    if len(encoded) <= MAX_TOOL_RESULT_BYTES:
        return content
    preview = encoded[:TOOL_RESULT_PREVIEW_BYTES].decode("utf-8", errors="replace")
    result: dict[str, Any] = {
        "truncated": True,
        "original_size_bytes": len(encoded),
        "preview": preview,
    }
    if isinstance(content, dict):
        for key in ("ok", "error", "executed_by", "bff_process_id"):
            if key in content:
                result[key] = content[key]
    return result


async def runtime_supports_bff_tools(
    *,
    endpoint: str,
    authorization: str,
) -> bool:
    """Return whether the deployed Agent explicitly accepts BFF tools."""

    headers = {"Authorization": authorization} if authorization else {}
    url = _http_channel_url(endpoint, CAPABILITIES_SUFFIX)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5)) as client:
            response = await client.get(url, headers=headers)
    except (httpx.ConnectError, httpx.TimeoutException) as error:
        raise StudioChannelError(
            "Unable to query the Runtime BFF-tool capability."
        ) from error
    if response.status_code == 404:
        return False
    if response.status_code >= 400:
        raise StudioChannelError(
            "Runtime rejected the BFF-tool capability query "
            f"(HTTP {response.status_code})."
        )
    try:
        capability = response.json()
    except ValueError as error:
        raise StudioChannelError(
            "Runtime returned an invalid BFF-tool capability response."
        ) from error
    if not isinstance(capability, dict) or not isinstance(
        capability.get("enabled"), bool
    ):
        raise StudioChannelError(
            "Runtime returned an invalid BFF-tool capability response."
        )
    if not capability["enabled"]:
        return False
    if capability.get("protocol") != PROTOCOL_VERSION:
        raise StudioChannelError(
            "Runtime advertises an incompatible BFF-tool protocol."
        )
    transports = capability.get("transports")
    if not isinstance(transports, list) or not {
        "websocket",
        "http-sse",
    }.intersection(transports):
        raise StudioChannelError(
            "Runtime enabled BFF tools without a supported transport."
        )
    return True


def _websocket_url(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        raise StudioChannelError("Runtime endpoint is not a valid HTTP(S) URL.")
    scheme = "wss" if parsed.scheme in {"https", "wss"} else "ws"
    base_path = parsed.path.rstrip("/")
    path = f"{base_path}{DEFAULT_CHANNEL_PATH}"
    return urlunsplit((scheme, parsed.netloc, path, parsed.query, ""))


def _http_channel_url(endpoint: str, suffix: str) -> str:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise StudioChannelError("Runtime endpoint is not a valid HTTP(S) URL.")
    base_path = parsed.path.rstrip("/")
    path = f"{base_path}{DEFAULT_CHANNEL_PATH}{suffix}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def _scope_id(runtime_id: str, payload: dict[str, Any]) -> str:
    scope = {
        "runtime_id": runtime_id,
        "app_name": str(payload.get("app_name") or ""),
        "user_id": str(payload.get("user_id") or ""),
        "session_id": str(payload.get("session_id") or ""),
    }
    encoded = json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()
    return "scope_" + hashlib.sha256(encoded).hexdigest()


class StudioToolRun:
    """One Agent run multiplexed with its BFF tool calls over one channel."""

    def __init__(
        self,
        *,
        receive_message: Callable[[], Coroutine[Any, Any, dict[str, Any]]],
        send_message: Callable[[dict[str, Any]], Awaitable[None]],
        close_transport: Callable[[], Awaitable[None]],
        catalog: StudioToolCatalogSnapshot,
        scope_id: str,
        catalog_revision: str,
        run_id: str,
        execution_context: StudioToolExecutionContext,
    ) -> None:
        self._receive_message = receive_message
        self._send_message = send_message
        self._close_transport = close_transport
        self.catalog = catalog
        self.scope_id = scope_id
        self.catalog_revision = catalog_revision
        self.run_id = run_id
        self.execution_context = execution_context
        self._send_lock = asyncio.Lock()
        self._tool_tasks: dict[str, asyncio.Task[None]] = {}
        self._completed = False
        self._fatal_error: BaseException | None = None
        self._fatal_event = asyncio.Event()

    async def _send(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._send_message(message)

    def _tool_task_done(self, request_id: str, task: asyncio.Task[None]) -> None:
        self._tool_tasks.pop(request_id, None)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self._fatal_error = error
            self._fatal_event.set()

    async def _receive_or_raise(self) -> dict[str, Any]:
        receive_task = asyncio.create_task(self._receive_message())
        fatal_task = asyncio.create_task(self._fatal_event.wait())
        done, pending = await asyncio.wait(
            {receive_task, fatal_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        if fatal_task in done and self._fatal_error is not None:
            if not receive_task.done():
                await asyncio.gather(receive_task, return_exceptions=True)
            raise self._fatal_error
        await asyncio.gather(fatal_task, return_exceptions=True)
        return receive_task.result()

    async def _execute_tool(self, message: dict[str, Any]) -> None:
        request_id = str(message.get("request_id") or "")
        status = "success"
        content: Any = None
        error: str | None = None
        try:
            if (
                message.get("run_id") != self.run_id
                or message.get("scope_id") != self.scope_id
                or message.get("catalog_revision") != self.catalog_revision
            ):
                raise StudioToolExecutionError("Studio tool call context mismatch.")
            arguments = message.get("arguments")
            if not isinstance(arguments, dict):
                raise StudioToolExecutionError(
                    "Studio tool arguments must be an object."
                )
            content = await self.catalog.execute(
                name=str(message.get("tool_name") or ""),
                executor_revision=str(message.get("executor_revision") or ""),
                arguments=arguments,
                context=self.execution_context,
            )
            content = _bounded_tool_result(content)
        except StudioToolExecutionError as exc:
            status = "denied"
            error = str(exc)
        except Exception:  # noqa: BLE001 - executor safety boundary
            status = "error"
            error = "Studio BFF tool execution failed."
            logger.exception(
                "Studio tool execution failed tool=%s run_id=%s",
                message.get("tool_name"),
                self.run_id,
            )
        await self._send(
            {
                "type": "tool.result",
                "request_id": request_id,
                "run_id": self.run_id,
                "scope_id": self.scope_id,
                "catalog_revision": self.catalog_revision,
                "status": status,
                "content": content,
                "error": error,
            }
        )

    async def stream(self) -> AsyncIterator[bytes]:
        try:
            while True:
                message = await self._receive_or_raise()
                if not isinstance(message, dict):
                    raise StudioChannelError(
                        "Runtime sent a non-object channel message."
                    )
                message_type = message.get("type")
                if message_type == "tool.call":
                    request_id = str(message.get("request_id") or "")
                    if not request_id or request_id in self._tool_tasks:
                        raise StudioChannelError(
                            "Runtime sent an invalid or duplicate tool request_id."
                        )
                    task = asyncio.create_task(self._execute_tool(message))
                    self._tool_tasks[request_id] = task
                    task.add_done_callback(
                        lambda completed, key=request_id: self._tool_task_done(
                            key, completed
                        )
                    )
                elif message_type == "tool.cancel":
                    if message.get("run_id") != self.run_id:
                        raise StudioChannelError(
                            "Runtime sent a tool.cancel for the wrong run."
                        )
                    request_id = str(message.get("request_id") or "")
                    task = self._tool_tasks.get(request_id)
                    if task is not None:
                        task.cancel()
                elif message_type == "run.event":
                    if message.get("run_id") != self.run_id:
                        raise StudioChannelError(
                            "Runtime sent a run.event for the wrong run."
                        )
                    event = message.get("event")
                    if not isinstance(event, dict):
                        raise StudioChannelError("Runtime sent an invalid run.event.")
                    yield (
                        "data: "
                        + json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                        + "\n\n"
                    ).encode("utf-8")
                elif message_type == "run.completed":
                    if message.get("run_id") != self.run_id:
                        raise StudioChannelError(
                            "Runtime completed the wrong Studio-channel run."
                        )
                    self._completed = True
                    if message.get("status") == "error":
                        raise StudioChannelError("Runtime Studio-channel run failed.")
                    return
                elif message_type == "channel.error":
                    raise StudioChannelError(
                        str(message.get("error") or "Runtime Studio channel failed.")
                    )
                elif message_type == "ping":
                    await self._send({"type": "pong"})
        finally:
            if not self._completed:
                try:
                    await self._send({"type": "run.cancel", "run_id": self.run_id})
                except Exception:  # noqa: BLE001 - best-effort cancellation
                    pass
            tool_tasks = list(self._tool_tasks.values())
            for task in tool_tasks:
                task.cancel()
            if tool_tasks:
                await asyncio.gather(*tool_tasks, return_exceptions=True)
            await self._close_transport()


async def _receive_expected_message(
    receive_message: Callable[[], Coroutine[Any, Any, dict[str, Any]]],
    expected_type: str,
) -> dict[str, Any]:
    message = await asyncio.wait_for(receive_message(), timeout=15)
    if not isinstance(message, dict) or message.get("type") != expected_type:
        detail = (
            message.get("error") if isinstance(message, dict) else "invalid message"
        )
        raise StudioChannelError(
            f"Expected {expected_type} from Runtime Studio channel: {detail}"
        )
    return message


def _invalid_status_code(error: InvalidStatus) -> int | None:
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


async def _open_http_studio_tool_run(
    *,
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    catalog: StudioToolCatalogSnapshot,
    scope_id: str,
    revision: str,
    run_id: str,
    studio_instance_id: str,
    execution_context: StudioToolExecutionContext,
) -> StudioToolRun:
    channel_id = uuid4().hex
    request_id = uuid4().hex
    run_url = _http_channel_url(endpoint, HTTP_RUN_SUFFIX)
    message_suffix = HTTP_MESSAGE_SUFFIX.format(channel_id=channel_id)
    message_url = _http_channel_url(endpoint, message_suffix)
    client = httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(None, connect=10),
    )
    response: httpx.Response | None = None
    try:
        request = client.build_request(
            "POST",
            run_url,
            json={
                "protocol": PROTOCOL_VERSION,
                "channel_id": channel_id,
                "studio_instance_id": studio_instance_id,
                "scope_id": scope_id,
                "catalog_revision": revision,
                "tools": catalog.manifests(),
                "request_id": request_id,
                "run_id": run_id,
                "payload": payload,
            },
        )
        response = await client.send(request, stream=True)
        if response.status_code >= 400:
            raw_detail = (await response.aread()).decode("utf-8", errors="replace")
            raise StudioChannelError(
                "Runtime rejected the Studio HTTP fallback "
                f"(HTTP {response.status_code}): {raw_detail[:500]}"
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
                    raise StudioChannelError(
                        "Runtime sent invalid SSE data on the Studio channel."
                    ) from error
                if not isinstance(message, dict):
                    raise StudioChannelError(
                        "Runtime sent a non-object channel message."
                    )
                return message
            raise StudioChannelError("Runtime closed the Studio HTTP channel early.")

        async def send_message(message: dict[str, Any]) -> None:
            result = await client.post(message_url, json=message, timeout=15)
            if result.status_code >= 400:
                detail = result.text[:500]
                if result.status_code == 404:
                    detail = (
                        "the result POST reached a different Runtime instance; "
                        "configure this Runtime with exactly one instance"
                    )
                raise StudioChannelError(
                    "Runtime rejected a Studio tool result "
                    f"(HTTP {result.status_code}): {detail}"
                )

        async def close_transport() -> None:
            assert response is not None
            await response.aclose()
            await client.aclose()

        ready = await _receive_expected_message(receive_message, "channel.ready")
        if ready.get("protocol") != PROTOCOL_VERSION:
            raise StudioChannelError("Runtime acknowledged an incompatible protocol.")
        catalog_ack = await _receive_expected_message(receive_message, "catalog.ack")
        if (
            catalog_ack.get("scope_id") != scope_id
            or catalog_ack.get("revision") != revision
        ):
            raise StudioChannelError("Runtime acknowledged the wrong catalog revision.")
        started = await _receive_expected_message(receive_message, "run.started")
        if started.get("run_id") != run_id:
            raise StudioChannelError("Runtime started the wrong Studio-channel run.")
        logger.info(
            "Studio tool channel using HTTP fallback endpoint_host=%s",
            urlsplit(endpoint).netloc,
        )
        return StudioToolRun(
            receive_message=receive_message,
            send_message=send_message,
            close_transport=close_transport,
            catalog=catalog,
            scope_id=scope_id,
            catalog_revision=revision,
            run_id=run_id,
            execution_context=execution_context,
        )
    except Exception:
        if response is not None:
            await response.aclose()
        await client.aclose()
        raise


async def open_studio_tool_run(
    *,
    endpoint: str,
    authorization: str,
    runtime_id: str,
    payload: dict[str, Any],
    catalog: StudioToolCatalogSnapshot,
) -> StudioToolRun:
    """Connect, publish the current catalog, and start one same-socket run."""

    if not catalog.enabled:
        raise StudioChannelError("Studio tool catalog is empty.")
    headers: dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    channel_token = os.getenv("VEADK_STUDIO_CHANNEL_TOKEN", "").strip()
    if channel_token:
        headers["X-VeADK-Studio-Channel-Token"] = channel_token

    studio_instance_id = os.getenv("VEADK_STUDIO_INSTANCE_ID", "").strip()
    if not studio_instance_id:
        studio_instance_id = f"studio-{os.getpid()}"
    scope_id = _scope_id(runtime_id, payload)
    revision = catalog.revision
    run_id = str(payload.get("invocation_id") or uuid4())
    execution_context = StudioToolExecutionContext(
        runtime_id=runtime_id,
        app_name=str(payload.get("app_name") or ""),
        user_id=str(payload.get("user_id") or ""),
        session_id=str(payload.get("session_id") or ""),
        run_id=run_id,
        scope_id=scope_id,
        catalog_revision=revision,
    )
    try:
        websocket = await connect(
            _websocket_url(endpoint),
            additional_headers=headers,
            max_size=2 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=10,
        )
    except InvalidStatus as error:
        status_code = _invalid_status_code(error)
        if status_code not in {200, 404, 405, 426, 501}:
            raise
        logger.warning(
            "Runtime gateway did not upgrade the Studio WebSocket (HTTP %s); "
            "falling back to streaming HTTP",
            status_code,
        )
        return await _open_http_studio_tool_run(
            endpoint=endpoint,
            headers=headers,
            payload=payload,
            catalog=catalog,
            scope_id=scope_id,
            revision=revision,
            run_id=run_id,
            studio_instance_id=studio_instance_id,
            execution_context=execution_context,
        )
    try:

        async def receive_message() -> dict[str, Any]:
            raw = await websocket.recv()
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise StudioChannelError("Runtime sent a non-object channel message.")
            return message

        async def send_message(message: dict[str, Any]) -> None:
            await websocket.send(json.dumps(message, ensure_ascii=False))

        await websocket.send(
            json.dumps(
                {
                    "type": "channel.hello",
                    "protocol": PROTOCOL_VERSION,
                    "studio_instance_id": studio_instance_id,
                }
            )
        )
        ready = await _receive_expected_message(receive_message, "channel.ready")
        if ready.get("protocol") != PROTOCOL_VERSION:
            raise StudioChannelError("Runtime acknowledged an incompatible protocol.")

        await websocket.send(
            json.dumps(
                {
                    "type": "catalog.replace",
                    "scope_id": scope_id,
                    "revision": revision,
                    "tools": catalog.manifests(),
                },
                ensure_ascii=False,
            )
        )
        catalog_ack = await _receive_expected_message(receive_message, "catalog.ack")
        if (
            catalog_ack.get("scope_id") != scope_id
            or catalog_ack.get("revision") != revision
        ):
            raise StudioChannelError("Runtime acknowledged the wrong catalog revision.")

        await websocket.send(
            json.dumps(
                {
                    "type": "run.start",
                    "request_id": uuid4().hex,
                    "run_id": run_id,
                    "scope_id": scope_id,
                    "catalog_revision": revision,
                    "payload": payload,
                },
                ensure_ascii=False,
            )
        )
        started = await _receive_expected_message(receive_message, "run.started")
        if started.get("run_id") != run_id:
            raise StudioChannelError("Runtime started the wrong Studio-channel run.")
        return StudioToolRun(
            receive_message=receive_message,
            send_message=send_message,
            close_transport=websocket.close,
            catalog=catalog,
            scope_id=scope_id,
            catalog_revision=revision,
            run_id=run_id,
            execution_context=execution_context,
        )
    except Exception:
        await websocket.close()
        raise
