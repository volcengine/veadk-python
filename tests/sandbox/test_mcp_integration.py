"""Real local MCP transport and VeADK/SQLite; offline model and control plane."""

import json
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from pydantic import Field

from examples.sandbox_mcp.main import create_runner, run_turn
from tests.sandbox.test_manager import FakeClient
from veadk.sandbox import SandboxManager, SessionKey


class OfflineModel(BaseLlm):
    content_counts: list[int] = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream=False):
        self.content_counts.append(len(llm_request.contents))
        last_parts = llm_request.contents[-1].parts
        if any(part.function_response for part in last_parts):
            assert "LOCAL_MCP_OK" in str(last_parts)
            part = types.Part(text="LOCAL_MCP_OK")
        else:
            part = types.Part(
                function_call=types.FunctionCall(name="read_marker", args={})
            )
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.mark.asyncio
async def test_standard_mcp_reconnect_preserves_physical_session_and_chat(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    from veadk import Agent

    routes = []

    async def mcp(request):
        if request.method != "POST":
            return web.Response(status=405)
        message = await request.json()
        if "id" not in message:
            return web.Response(status=202)
        method = message["method"]
        if method == "initialize":
            result = {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-sandbox", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "read_marker",
                        "description": "Read the marker from the sandbox.",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            }
        elif method == "tools/call":
            assert message["params"]["name"] == "read_marker"
            routes.append(request.query["route"])
            result = {
                "content": [{"type": "text", "text": "LOCAL_MCP_OK"}],
                "isError": False,
            }
        else:
            raise AssertionError(method)
        return web.json_response(
            {"jsonrpc": "2.0", "id": message["id"], "result": result}
        )

    app = web.Application()
    app.router.add_route("*", "/mcp", mcp)
    async with TestServer(app) as server:

        class LocalClient(FakeClient):
            def create_session(self, request):
                value = super().create_session(request)
                value.endpoint = str(server.make_url("/?route=1"))
                return value

            def resume_session(self, request):
                response = super().resume_session(request)
                self.sessions[request.session_id].endpoint = str(
                    server.make_url("/?route=2")
                )
                return response

        client = LocalClient()
        model = OfflineModel(model="offline")
        key = SessionKey("mcp_test", "user", "chat")
        db_url = f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}"

        def offline_agent(**kwargs):
            agent = Agent(**kwargs, model_api_key="offline-placeholder")
            agent.model = model
            return agent

        manager = SandboxManager(
            tool_id="test-tool", state_dir=tmp_path / "bindings", client=client
        )
        async with DatabaseSessionService(db_url=db_url) as service:
            with patch("veadk.Agent", side_effect=offline_agent):
                runner = create_runner(
                    manager=manager, session_service=service, app_name=key.app_name
                )
            try:
                for index in range(2):
                    output = await run_turn(
                        runner=runner, prompt="Read the sandbox marker.", key=key
                    )
                    assert "LOCAL_MCP_OK" in output
                    assert (await manager.status(key))["session_id"] == "sandbox-1"
                    session = await service.get_session(
                        app_name=key.app_name,
                        user_id=key.user_id,
                        session_id=key.session_id,
                    )
                    responses = [
                        r
                        for event in session.events
                        for r in event.get_function_responses()
                    ]
                    assert len(responses) == index + 1
                    assert "LOCAL_MCP_OK" in json.dumps(responses[-1].model_dump())
                    if index == 0:
                        await manager.pause(key)
            finally:
                await runner.close()
        async with DatabaseSessionService(db_url=db_url) as reopened:
            session = await reopened.get_session(
                app_name=key.app_name, user_id=key.user_id, session_id=key.session_id
            )
            assert (
                len(
                    [
                        r
                        for event in session.events
                        for r in event.get_function_responses()
                    ]
                )
                == 2
            )
        await manager.delete(key)

    assert routes == ["1", "2"]
    assert model.content_counts == [1, 3, 5, 7]
    assert client.calls == ["create", "pause", "resume", "delete"]
