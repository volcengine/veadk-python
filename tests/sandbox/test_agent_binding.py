"""Agent-native sandbox integration: real MCP transport, offline model/control plane."""

import asyncio
from collections import defaultdict
from contextlib import aclosing

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner as ADKRunner
from google.adk.sessions import DatabaseSessionService
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types
from pydantic import Field

from tests.sandbox.test_manager import FakeClient
from veadk import Agent, Runner
from veadk.sandbox import SandboxManager, SessionKey


@pytest_asyncio.fixture
async def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    calls, closed = [], []
    original_close = McpToolset.close

    async def close(self):
        await original_close(self)
        closed.append(self)

    monkeypatch.setattr(McpToolset, "close", close)

    async def mcp(request):
        if request.method != "POST":
            return web.Response(status=405)
        msg = await request.json()
        if "id" not in msg:
            return web.Response(status=202)
        method = msg["method"]
        if method == "initialize":
            result = {
                "protocolVersion": msg["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "sandbox", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "read_marker",
                        "description": "Read this sandbox marker",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            }
        elif method == "tools/call":
            assert msg["params"]["name"] == "read_marker"
            marker = request.query["route"]
            calls.append(marker)
            result = {"content": [{"type": "text", "text": marker}], "isError": False}
        else:
            raise AssertionError(method)
        return web.json_response({"jsonrpc": "2.0", "id": msg["id"], "result": result})

    app = web.Application()
    app.router.add_route("*", "/mcp", mcp)
    async with TestServer(app) as server:

        class Client(FakeClient):
            def create_session(self, request):
                value = super().create_session(request)
                value.endpoint = str(server.make_url(f"/?route={value.session_id}-v1"))
                return value

            def resume_session(self, request):
                response = super().resume_session(request)
                self.sessions[request.session_id].endpoint = str(
                    server.make_url(f"/?route={request.session_id}-v2")
                )
                return response

        client = Client()
        manager = SandboxManager(
            tool_id="test-tool",
            state_dir=tmp_path / "bindings",
            client=client,
            poll_interval=0.01,
            ready_timeout=3,
        )
        async with DatabaseSessionService(
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}"
        ) as service:
            yield manager, client, service, calls, closed


class Model(BaseLlm):
    counts: dict = Field(default_factory=lambda: defaultdict(list))
    arrivals: set = Field(default_factory=set)
    gate: asyncio.Event = Field(default_factory=asyncio.Event)
    concurrent: bool = False
    mode: str = "normal"

    async def generate_content_async(self, llm_request, stream=False):
        label = llm_request.contents[0].parts[0].text
        self.counts[label].append(len(llm_request.contents))
        assert set(llm_request.tools_dict) == {"read_marker"}
        if self.mode == "error":
            raise RuntimeError("offline model failure")
        if self.mode == "block":
            self.gate.set()
            await asyncio.Event().wait()
        if self.concurrent:
            self.arrivals.add(label)
            if len(self.arrivals) == 2:
                self.gate.set()
            await asyncio.wait_for(self.gate.wait(), 5)
        last = llm_request.contents[-1].parts
        if any(p.function_response for p in last):
            part = types.Part(text=str(last))
        else:
            part = types.Part(
                function_call=types.FunctionCall(name="read_marker", args={})
            )
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.fixture(params=[Runner, ADKRunner], ids=["veadk", "native_adk"])
def runner_type(request):
    return request.param


async def invoke(runner, *, messages, user_id, session_id):
    if isinstance(runner, Runner):
        return await runner.run(
            messages=messages, user_id=user_id, session_id=session_id
        )
    output = ""
    async with aclosing(
        runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=messages)]),
        )
    ) as stream:
        async for event in stream:
            for part in event.content.parts if event.content else []:
                if part.text and not part.thought:
                    output = part.text
    return output


def make_runner(manager, service, model, runner_type, **kwargs):
    agent = Agent(
        name="shared_agent",
        tools=[],
        sandbox=manager,
        model_api_key="offline-placeholder",
        **kwargs,
    )
    agent.model = model
    return agent, runner_type(
        agent=agent,
        app_name="shared_app",
        session_service=service,
        auto_create_session=True,
    )


@pytest.mark.asyncio
async def test_same_agent_concurrent_sessions_and_resume(environment, runner_type):
    manager, client, service, calls, closed = environment
    model = Model(model="offline", concurrent=True)
    observed = []

    async def callback(callback_context, llm_request):
        observed.append(callback_context.session.id)
        assert set(llm_request.tools_dict) == {"read_marker"}

    agent, runner = make_runner(
        manager, service, model, runner_type, before_model_callback=callback
    )
    original_tools = agent.tools
    try:
        outputs = await asyncio.gather(
            *(
                invoke(runner, messages=label, user_id="user", session_id=label)
                for label in ("A", "B")
            )
        )
        keys = [SessionKey("shared_app", "user", label) for label in ("A", "B")]
        ids = [(await manager.status(key))["session_id"] for key in keys]
        assert ids[0] != ids[1]
        for index, output in enumerate(outputs):
            assert ids[index] + "-v1" in output
            assert ids[1 - index] not in output
        await manager.pause(keys[0])
        output = await invoke(
            runner, messages="continue", user_id="user", session_id="A"
        )
        assert ids[0] + "-v2" in output
        assert (await manager.status(keys[0]))["session_id"] == ids[0]
        assert model.counts["A"] == [1, 3, 5, 7]
        assert model.counts["B"] == [1, 3]
        assert len(closed) == 3 and len(set(map(id, closed))) == 3
        assert agent.tools is original_tools and not agent.tools
        assert agent.before_model_callback is callback
        assert runner.agent is agent
        assert sorted(calls) == sorted([ids[0] + "-v1", ids[1] + "-v1", ids[0] + "-v2"])
        assert client.calls.count("create") == 2
        assert sorted(observed) == ["A"] * 4 + ["B"] * 2
        for key in keys:
            await manager.delete(key)
    finally:
        await runner.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["error", "block", "early_close", "tool_error", "discovery_error"]
)
async def test_failure_cancel_and_stream_close_release_connection_and_lock(
    environment, mode, monkeypatch, runner_type
):
    manager, client, service, _calls, closed = environment
    model = Model(model="offline", mode=mode)
    _agent, runner = make_runner(manager, service, model, runner_type)
    key = SessionKey("shared_app", "user", "failure")
    try:
        if mode in {"tool_error", "discovery_error"}:
            from google.adk.tools.mcp_tool.mcp_tool import McpTool

            async def fail(*args, **kwargs):
                raise RuntimeError("offline tool failure")

            target, method = (
                (McpToolset, "get_tools")
                if mode == "discovery_error"
                else (McpTool, "run_async")
            )
            with monkeypatch.context() as patcher:
                patcher.setattr(target, method, fail)
                with pytest.raises(Exception, match="offline tool failure"):
                    await invoke(
                        runner,
                        messages="tool fail",
                        user_id=key.user_id,
                        session_id=key.session_id,
                    )
        elif mode == "error":
            with pytest.raises(RuntimeError, match="offline model failure"):
                await invoke(
                    runner,
                    messages="fail",
                    user_id=key.user_id,
                    session_id=key.session_id,
                )
        elif mode == "block":
            task = asyncio.create_task(
                invoke(
                    runner,
                    messages="block",
                    user_id=key.user_id,
                    session_id=key.session_id,
                )
            )
            await asyncio.wait_for(model.gate.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            async with aclosing(
                runner.run_async(
                    user_id=key.user_id,
                    session_id=key.session_id,
                    new_message=types.Content(
                        role="user", parts=[types.Part(text="stop")]
                    ),
                )
            ) as stream:
                await anext(stream)
        assert len(closed) == 1
        await asyncio.wait_for(manager.pause(key), 2)
        assert client.calls[-1] == "pause"
        await manager.delete(key)
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_missing_chat_does_not_create_sandbox_and_live_is_rejected(
    environment, runner_type
):
    manager, client, service, _calls, _closed = environment
    agent = Agent(name="empty", sandbox=manager, model_api_key="offline-placeholder")
    runner = runner_type(agent=agent, app_name="shared_app", session_service=service)
    try:
        with pytest.raises(ValueError, match="Session not found"):
            await invoke(
                runner, messages="missing", user_id="user", session_id="missing"
            )
        await service.create_session(
            app_name="shared_app", user_id="user", session_id="live"
        )
        with pytest.raises(NotImplementedError, match="run_live"):
            async with aclosing(
                runner.run_live(
                    user_id="user",
                    session_id="live",
                    live_request_queue=LiveRequestQueue(),
                )
            ) as stream:
                await anext(stream)
        assert client.calls == []
    finally:
        await runner.close()


def test_configured_local_tools_are_rejected(tmp_path):
    def local_tool() -> str:
        return "local"

    manager = SandboxManager(
        tool_id="test-tool", state_dir=tmp_path, client=FakeClient()
    )
    with pytest.raises(ValueError, match="empty tools"):
        Agent(
            name="mixed",
            tools=[local_tool],
            sandbox=manager,
            model_api_key="offline-placeholder",
        )


@pytest.mark.asyncio
async def test_clone_revalidates_configuration_without_serializing_manager(tmp_path):
    from types import SimpleNamespace

    manager = SandboxManager(
        tool_id="test-tool", state_dir=tmp_path, client=FakeClient()
    )
    agent = Agent(name="original", sandbox=manager, model_api_key="offline-placeholder")
    assert "sandbox" not in agent.model_dump()
    assert "SandboxManager" not in repr(agent)
    clone = agent.clone(update={"name": "clone"})
    assert clone.sandbox is manager
    clone.runtime = "codex"
    with pytest.raises(ValueError, match="ADK"):
        await anext(clone._run_async_impl(SimpleNamespace()))
    assert manager.client.calls == []


@pytest.mark.asyncio
async def test_before_agent_short_circuit_allocates_no_sandbox(
    environment, runner_type
):
    manager, client, service, _calls, closed = environment

    async def short_circuit(callback_context):
        return types.Content(role="model", parts=[types.Part(text="CACHED_REPLY")])

    agent, runner = make_runner(
        manager,
        service,
        Model(model="offline"),
        runner_type,
        before_agent_callback=short_circuit,
    )
    try:
        assert (
            await invoke(runner, messages="cached", user_id="user", session_id="cached")
            == "CACHED_REPLY"
        )
        assert client.calls == [] and closed == []
        assert agent.before_agent_callback is short_circuit
    finally:
        await runner.close()
