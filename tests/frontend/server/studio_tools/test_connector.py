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

from __future__ import annotations

import asyncio
import base64
import json
import socket
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from typing import cast

import pytest
import uvicorn
from fastapi import FastAPI
from google.adk.tools.tool_context import ToolContext
from websockets.exceptions import InvalidStatus

import frontend.server.studio_tools.connector as connector
from frontend.server.studio_tools.registry import StudioTool, StudioToolRegistry
from veadk.integrations.agentkit.studio_channel import (
    StudioExternalToolset,
    mount_studio_channel_routes,
)


class _FakeWebSocket:
    def __init__(self, *, mismatched_tool_context: bool = False) -> None:
        self.incoming: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self.mismatched_tool_context = mismatched_tool_context
        payload = (
            base64.urlsafe_b64encode(
                json.dumps({"x-faas-instance-name": "instance-websocket"}).encode()
            )
            .decode()
            .rstrip("=")
        )
        self.response = SimpleNamespace(
            headers={
                "x-session-id": f"v1.{payload}.signature",
                "x-faas-request-id": "request-websocket",
            }
        )

    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        self.sent.append(message)
        if message["type"] == "channel.hello":
            await self.incoming.put(
                json.dumps(
                    {
                        "type": "channel.ready",
                        "protocol": "studio-tool-channel/1",
                        "connection_id": "connection-1",
                    }
                )
            )
        elif message["type"] == "catalog.replace":
            await self.incoming.put(
                json.dumps(
                    {
                        "type": "catalog.ack",
                        "scope_id": message["scope_id"],
                        "revision": message["revision"],
                    }
                )
            )
        elif message["type"] == "run.start":
            await self.incoming.put(
                json.dumps(
                    {
                        "type": "run.started",
                        "request_id": message["request_id"],
                        "run_id": message["run_id"],
                    }
                )
            )
            await self.incoming.put(
                json.dumps(
                    {
                        "type": "tool.call",
                        "request_id": "call-1",
                        "run_id": message["run_id"],
                        "scope_id": (
                            "wrong-scope"
                            if self.mismatched_tool_context
                            else message["scope_id"]
                        ),
                        "catalog_revision": message["catalog_revision"],
                        "tool_name": "studio_multiply",
                        "executor_revision": "v1",
                        "arguments": {"left": 6, "right": 7},
                    }
                )
            )
        elif message["type"] == "tool.result":
            await self.incoming.put(
                json.dumps(
                    {
                        "type": "run.event",
                        "run_id": message["run_id"],
                        "event": {
                            "id": "event-1",
                            "author": "agent",
                            "tool_result": message["content"],
                        },
                    }
                )
            )
            await self.incoming.put(
                json.dumps(
                    {
                        "type": "run.completed",
                        "run_id": message["run_id"],
                        "status": "success",
                    }
                )
            )

    async def recv(self) -> str:
        return await self.incoming.get()

    async def close(self) -> None:
        self.closed = True


def _registry() -> StudioToolRegistry:
    registry = StudioToolRegistry()
    registry.register(
        StudioTool(
            name="studio_multiply",
            description="Multiply two integers in Studio.",
            input_schema={
                "type": "object",
                "properties": {
                    "left": {"type": "integer"},
                    "right": {"type": "integer"},
                },
                "required": ["left", "right"],
                "additionalProperties": False,
            },
            executor=lambda args: {"product": args["left"] * args["right"]},
            executor_revision="v1",
        )
    )
    return registry


def test_large_tool_results_are_bounded_before_crossing_the_channel() -> None:
    content = {
        "ok": True,
        "executed_by": "studio-bff",
        "data": "x" * connector.MAX_TOOL_RESULT_BYTES,
    }

    result = connector._bounded_tool_result(content)

    assert result["ok"] is True
    assert result["executed_by"] == "studio-bff"
    assert result["truncated"] is True
    assert result["original_size_bytes"] > connector.MAX_TOOL_RESULT_BYTES
    assert len(result["preview"].encode("utf-8")) <= connector.TOOL_RESULT_PREVIEW_BYTES


@pytest.mark.asyncio
async def test_connector_reads_agent_bff_tool_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, dict[str, str]]] = []

    class _Response:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "enabled": True,
                "protocol": "studio-tool-channel/1",
                "transports": ["websocket", "http-sse"],
            }

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: Any) -> None:
            del args

        async def get(self, url: str, *, headers: dict[str, str]) -> _Response:
            requests.append((url, headers))
            return _Response()

    monkeypatch.setattr(connector.httpx, "AsyncClient", _Client)

    assert await connector.runtime_supports_bff_tools(
        endpoint="https://runtime.example/base?gateway=value",
        authorization="Bearer runtime-key",
    )
    assert requests == [
        (
            "https://runtime.example/base/harness/studio-channel/v1/capabilities"
            "?gateway=value",
            {"Authorization": "Bearer runtime-key"},
        )
    ]


@pytest.mark.asyncio
async def test_connector_treats_missing_capability_as_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        status_code = 404

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: Any) -> None:
            del args

        async def get(self, url: str, *, headers: dict[str, str]) -> _Response:
            del url, headers
            return _Response()

    monkeypatch.setattr(connector.httpx, "AsyncClient", _Client)

    assert not await connector.runtime_supports_bff_tools(
        endpoint="https://runtime.example",
        authorization="",
    )


@pytest.mark.asyncio
async def test_connector_runs_and_executes_tool_over_one_websocket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    websocket = _FakeWebSocket()
    connect_calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
        connect_calls.append((url, kwargs))
        return websocket

    monkeypatch.setattr(connector, "connect", fake_connect)
    run = await connector.open_studio_tool_run(
        endpoint="https://runtime.example/base?gateway=value",
        authorization="Bearer runtime-key",
        runtime_id="runtime-1",
        payload={
            "app_name": "agent",
            "user_id": "user-1",
            "session_id": "session-1",
            "new_message": {"role": "user", "parts": [{"text": "6 * 7"}]},
        },
        catalog=_registry().snapshot(),
    )

    chunks = [chunk async for chunk in run.stream()]

    assert run.execution_context.runtime_id == "runtime-1"
    assert run.execution_context.app_name == "agent"
    assert run.execution_context.user_id == "user-1"
    assert run.execution_context.session_id == "session-1"
    assert run.execution_context.run_id == run.run_id
    assert run.execution_context.scope_id == run.scope_id
    assert run.execution_context.catalog_revision == run.catalog_revision
    assert run.runtime_context.instance_name == "instance-websocket"
    assert run.runtime_context.request_id == "request-websocket"
    assert connect_calls[0][0] == (
        "wss://runtime.example/base/harness/studio-channel/v1?gateway=value"
    )
    assert connect_calls[0][1]["additional_headers"] == {
        "Authorization": "Bearer runtime-key",
    }
    tool_result = next(item for item in websocket.sent if item["type"] == "tool.result")
    assert tool_result["status"] == "success"
    assert tool_result["content"] == {"product": 42}
    assert json.loads(chunks[0].removeprefix(b"data: ").strip()) == {
        "id": "event-1",
        "author": "agent",
        "tool_result": {"product": 42},
    }
    assert websocket.closed


@pytest.mark.asyncio
async def test_connector_does_not_execute_a_cross_scope_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    websocket = _FakeWebSocket(mismatched_tool_context=True)

    async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
        del url, kwargs
        return websocket

    monkeypatch.setattr(connector, "connect", fake_connect)
    run = await connector.open_studio_tool_run(
        endpoint="https://runtime.example",
        authorization="Bearer runtime-key",
        runtime_id="runtime-1",
        payload={
            "app_name": "agent",
            "user_id": "user-1",
            "session_id": "session-1",
            "new_message": {"role": "user", "parts": [{"text": "6 * 7"}]},
        },
        catalog=_registry().snapshot(),
    )

    chunks = [chunk async for chunk in run.stream()]

    tool_result = next(item for item in websocket.sent if item["type"] == "tool.result")
    assert tool_result["status"] == "denied"
    assert tool_result["content"] is None
    assert tool_result["error"] == "Studio tool call context mismatch."
    assert json.loads(chunks[0].removeprefix(b"data: ").strip())["tool_result"] is None


@pytest.mark.asyncio
async def test_connector_falls_back_to_http_and_completes_a_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()

    async def run_handler(
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        assert payload["session_id"] == "session-1"
        tools = await StudioExternalToolset().get_tools()
        result = await tools[0].run_async(
            args={"left": 6, "right": 7},
            tool_context=cast(ToolContext, None),
        )
        yield {"id": "event-http", "tool_result": result}

    mount_studio_channel_routes(app=app, run_handler=run_handler)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    while not server.started:
        await asyncio.sleep(0.01)

    async def reject_websocket(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise InvalidStatus(SimpleNamespace(status_code=200))  # type: ignore[arg-type]

    monkeypatch.setattr(connector, "connect", reject_websocket)
    try:
        run = await connector.open_studio_tool_run(
            endpoint=f"http://127.0.0.1:{port}",
            authorization="",
            runtime_id="runtime-1",
            payload={
                "app_name": "agent",
                "user_id": "user-1",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "6 * 7"}]},
            },
            catalog=_registry().snapshot(),
        )
        chunks = [chunk async for chunk in run.stream()]
    finally:
        server.should_exit = True
        await server_task

    event = json.loads(chunks[0].removeprefix(b"data: ").strip())
    assert event == {"id": "event-http", "tool_result": {"product": 42}}
