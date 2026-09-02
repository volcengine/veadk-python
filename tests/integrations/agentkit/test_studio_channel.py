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
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.adk.tools.tool_context import ToolContext

from veadk.integrations.agentkit.studio_channel import (
    PROTOCOL_VERSION,
    StudioExternalToolset,
    StudioRemoteTool,
    StudioToolManifest,
    bind_studio_tools,
    catalog_revision,
    mount_studio_channel_routes,
)
from veadk.integrations.agentkit.studio_channel.routes import _StudioChannelConnection


def _manifest(name: str = "studio_multiply") -> dict[str, Any]:
    return {
        "name": name,
        "description": "Multiply two integers in the Studio BFF.",
        "input_schema": {
            "type": "object",
            "properties": {
                "left": {"type": "integer"},
                "right": {"type": "integer"},
            },
            "required": ["left", "right"],
            "additionalProperties": False,
        },
        "executor_revision": "demo-v1",
        "timeout_ms": 30000,
        "idempotent": True,
        "risk_level": "low",
    }


def test_catalog_revision_is_stable_across_tool_order() -> None:
    first = _manifest("studio_first")
    second = _manifest("studio_second")

    assert catalog_revision([first, second]) == catalog_revision([second, first])


def test_runtime_rejects_an_invalid_json_schema() -> None:
    manifest = _manifest()
    manifest["input_schema"]["properties"]["left"]["type"] = "not-a-json-type"

    with pytest.raises(ValueError, match="input_schema is invalid"):
        StudioToolManifest.model_validate(manifest)


def test_manifest_accepts_a_fifteen_minute_tool_timeout() -> None:
    manifest = _manifest()
    manifest["timeout_ms"] = 15 * 60 * 1000

    validated = StudioToolManifest.model_validate(manifest)

    assert validated.timeout_ms == 15 * 60 * 1000


def test_manifest_rejects_a_tool_timeout_over_thirty_minutes() -> None:
    manifest = _manifest()
    manifest["timeout_ms"] = 30 * 60 * 1000 + 1

    with pytest.raises(ValueError, match="less than or equal to 1800000"):
        StudioToolManifest.model_validate(manifest)


def test_remote_tool_exposes_manifest_schema_and_dispatches() -> None:
    calls: list[dict[str, Any]] = []

    class Dispatcher:
        async def call_tool(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return {"product": 42}

    tool = StudioRemoteTool(
        manifest=StudioToolManifest.model_validate(_manifest()),
        dispatcher=Dispatcher(),
        run_id="run-1",
        scope_id="scope-1",
        catalog_revision="revision-1",
    )

    declaration = tool._get_declaration()
    assert declaration.name == "studio_multiply"
    assert declaration.parameters_json_schema == _manifest()["input_schema"]

    result = asyncio.run(
        tool.run_async(
            args={"left": 6, "right": 7},
            tool_context=cast(
                ToolContext,
                SimpleNamespace(function_call_id="adk-function-call-1"),
            ),
        )
    )
    assert result == {"product": 42}
    assert calls[0]["run_id"] == "run-1"
    assert calls[0]["arguments"] == {"left": 6, "right": 7}
    assert calls[0]["function_call_id"] == "adk-function-call-1"


@pytest.mark.asyncio
async def test_channel_preserves_bounded_content_for_failed_tool_result() -> None:
    sent: list[dict[str, Any]] = []
    connection: _StudioChannelConnection

    async def sender(message: dict[str, Any]) -> None:
        sent.append(message)
        if message["type"] != "tool.call":
            return
        await connection._resolve_tool_result(
            {
                "type": "tool.result",
                "request_id": message["request_id"],
                "run_id": message["run_id"],
                "scope_id": message["scope_id"],
                "catalog_revision": message["catalog_revision"],
                "status": "error",
                "error": "Codex Sandbox 连接中断",
                "content": {
                    "ok": False,
                    "codex_activity": {"events": [{"status": "failed"}]},
                },
            }
        )

    async def run_handler(
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        del payload
        if False:
            yield {}

    connection = _StudioChannelConnection(
        sender=sender,
        run_handler=run_handler,
        reserved_tool_names=set(),
    )
    result = await connection.call_tool(
        run_id="run-1",
        scope_id="scope-1",
        catalog_revision="revision-1",
        manifest=StudioToolManifest.model_validate(_manifest()),
        arguments={"left": 6, "right": 7},
    )

    assert sent[0]["type"] == "tool.call"
    assert result == {
        "ok": False,
        "codex_activity": {"events": [{"status": "failed"}]},
        "status": "error",
        "error": "Codex Sandbox 连接中断",
    }


@pytest.mark.asyncio
async def test_external_toolset_isolates_concurrent_run_catalogs() -> None:
    toolset = StudioExternalToolset()

    def remote_tool(name: str) -> StudioRemoteTool:
        return StudioRemoteTool(
            manifest=StudioToolManifest.model_validate(_manifest(name)),
            dispatcher=cast(Any, object()),
            run_id=f"run-{name}",
            scope_id=f"scope-{name}",
            catalog_revision=f"revision-{name}",
        )

    async def selected_name(name: str) -> list[str]:
        with bind_studio_tools([remote_tool(name)]):
            await asyncio.sleep(0)
            return [tool.name for tool in await toolset.get_tools()]

    first, second = await asyncio.gather(
        selected_name("studio_first"),
        selected_name("studio_second"),
    )

    assert first == ["studio_first"]
    assert second == ["studio_second"]
    assert await toolset.get_tools() == []


def test_websocket_runs_and_calls_bff_tool_on_the_same_connection() -> None:
    app = FastAPI()
    toolset = StudioExternalToolset()

    async def run_handler(
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        assert payload["session_id"] == "session-1"
        tools = await toolset.get_tools()
        result = await tools[0].run_async(
            args={"left": 6, "right": 7},
            tool_context=cast(ToolContext, None),
        )
        yield {"id": "event-1", "author": "agent", "tool_result": result}

    mount_studio_channel_routes(app=app, run_handler=run_handler)
    tools = [_manifest()]
    revision = catalog_revision(tools)

    with TestClient(app).websocket_connect("/harness/studio-channel/v1") as websocket:
        websocket.send_json(
            {
                "type": "channel.hello",
                "protocol": PROTOCOL_VERSION,
                "studio_instance_id": "studio-1",
            }
        )
        assert websocket.receive_json()["type"] == "channel.ready"

        websocket.send_json(
            {
                "type": "catalog.replace",
                "scope_id": "scope-1",
                "revision": revision,
                "tools": tools,
            }
        )
        assert websocket.receive_json() == {
            "type": "catalog.ack",
            "scope_id": "scope-1",
            "revision": revision,
        }

        websocket.send_json(
            {
                "type": "run.start",
                "request_id": "request-1",
                "run_id": "run-1",
                "scope_id": "scope-1",
                "catalog_revision": revision,
                "payload": {"session_id": "session-1"},
            }
        )
        assert websocket.receive_json() == {
            "type": "run.started",
            "request_id": "request-1",
            "run_id": "run-1",
        }

        tool_call = websocket.receive_json()
        assert tool_call["type"] == "tool.call"
        assert tool_call["run_id"] == "run-1"
        assert tool_call["tool_name"] == "studio_multiply"
        assert tool_call["arguments"] == {"left": 6, "right": 7}
        assert tool_call["function_call_id"] == ""

        websocket.send_json(
            {
                "type": "tool.result",
                "request_id": tool_call["request_id"],
                "run_id": "run-1",
                "scope_id": "scope-1",
                "catalog_revision": revision,
                "status": "success",
                "content": {"product": 42, "executed_by": "studio-bff"},
            }
        )
        run_event = websocket.receive_json()
        assert run_event == {
            "type": "run.event",
            "run_id": "run-1",
            "event": {
                "id": "event-1",
                "author": "agent",
                "tool_result": {"product": 42, "executed_by": "studio-bff"},
            },
        }
        assert websocket.receive_json() == {
            "type": "run.completed",
            "run_id": "run-1",
            "status": "success",
        }


def test_catalog_rejects_agent_tool_name_conflicts() -> None:
    app = FastAPI()

    async def run_handler(
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        del payload
        if False:
            yield {}

    mount_studio_channel_routes(
        app=app,
        run_handler=run_handler,
        reserved_tool_names={"studio_multiply"},
    )
    tools = [_manifest()]

    with TestClient(app).websocket_connect("/harness/studio-channel/v1") as websocket:
        websocket.send_json({"type": "channel.hello", "protocol": PROTOCOL_VERSION})
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "catalog.replace",
                "scope_id": "scope-1",
                "revision": catalog_revision(tools),
                "tools": tools,
            }
        )
        rejection = websocket.receive_json()

    assert rejection["type"] == "catalog.reject"
    assert "conflict" in rejection["error"]


def test_channel_routes_are_promoted_above_an_existing_catchall() -> None:
    app = FastAPI()

    @app.post("/{path:path}")
    async def catchall(path: str) -> dict[str, str]:
        return {"caught": path}

    async def run_handler(
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        del payload
        if False:
            yield {}

    mount_studio_channel_routes(app=app, run_handler=run_handler)
    response = TestClient(app).post(
        "/harness/studio-channel/v1/http-runs",
        json={"protocol": "invalid-on-purpose"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "unsupported protocol"}


def test_channel_capability_can_be_advertised_without_enabling_rpc_routes() -> None:
    app = FastAPI()

    async def run_handler(
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        del payload
        if False:
            yield {}

    mount_studio_channel_routes(
        app=app,
        run_handler=run_handler,
        enabled=False,
    )
    client = TestClient(app)

    assert client.get("/harness/studio-channel/v1/capabilities").json() == {
        "enabled": False,
        "protocol": PROTOCOL_VERSION,
        "transports": [],
    }
    assert (
        client.post(
            "/harness/studio-channel/v1/http-runs",
            json={"protocol": PROTOCOL_VERSION},
        ).status_code
        == 404
    )


def test_channel_capability_advertises_supported_transports_when_enabled() -> None:
    app = FastAPI()

    async def run_handler(
        payload: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        del payload
        if False:
            yield {}

    mount_studio_channel_routes(app=app, run_handler=run_handler, enabled=True)

    assert TestClient(app).get("/harness/studio-channel/v1/capabilities").json() == {
        "enabled": True,
        "protocol": PROTOCOL_VERSION,
        "transports": ["websocket", "http-sse"],
    }
