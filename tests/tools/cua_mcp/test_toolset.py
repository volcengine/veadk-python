import sys
from pathlib import Path

import pytest
from google.adk.agents import Agent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.sessions import InMemorySessionService
from google.adk.tools import ToolContext
from mcp import StdioServerParameters

from veadk.tools.builtin_tools.computer_use import create_computer_use_toolset
from veadk.tools.builtin_tools.run_code import _tool_user_session_id


async def context(session_id):
    service = InMemorySessionService()
    session = await service.create_session(
        app_name="app", user_id="user", session_id=session_id
    )
    ctx = InvocationContext(
        session_service=service,
        invocation_id="turn",
        agent=Agent(name="agent"),
        session=session,
    )
    return ToolContext(ctx), ReadonlyContext(ctx)


def toolset():
    return create_computer_use_toolset(
        connection_params=StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("stdio_fixture.py"))],
        ),
        tool_id="t-example",
    )


@pytest.mark.asyncio
async def test_real_context_binding_refresh_same_invocation_and_second_session():
    cua = toolset()
    ctx, readonly = await context("one")
    other, other_readonly = await context("two")
    try:
        tools = await cua.get_tools_with_prefix(readonly)
        assert "cua_screenshot" in [t.name for t in tools]
        result = await tools[0].run_async(args={}, tool_context=ctx)
        assert result["structuredContent"]["user_session_id"] == _tool_user_session_id(
            ctx
        )
        assert ctx.state[cua.binding_state_key(ctx)]["session_id"] == "s-1"
        # ADK normally caches toolsets per invocation; CUA must opt out.
        assert "cua_screenshot" in [
            t.name for t in await cua.get_tools_with_prefix(readonly)
        ]
        assert "cua_screenshot" in [
            t.name for t in await cua.get_tools_with_prefix(other_readonly)
        ]
        assert other.state.get(cua.binding_state_key(other)) is None
        # Simulate a new Agent turn after the state delta has been persisted.
        ctx.session.state[cua.binding_state_key(ctx)] = ctx.state[
            cua.binding_state_key(ctx)
        ]
        await cua.close()
        restored = toolset()
        try:
            # The restarted fixture has no platform instances: do not replace the saved binding.
            with pytest.raises(RuntimeError, match="discovery failed"):
                await restored.get_tools(readonly)
            assert ctx.state[cua.binding_state_key(ctx)]["session_id"] == "s-1"
        finally:
            await restored.close()
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_parallel_calls_rejected_and_model_cannot_override_context():
    cua = toolset()
    ctx, readonly = await context("one")
    try:
        tool = (await cua.get_tools(readonly))[0]
        ctx._veadk_parallel_tool_call_count = 2
        rejected = await tool.run_async(args={}, tool_context=ctx)
        assert rejected["isError"]
        assert rejected["structuredContent"]["executed"] is False
        ctx._veadk_parallel_tool_call_count = 1
        result = await tool.run_async(
            args={"user_session_id": "spoofed"}, tool_context=ctx
        )
        assert result["isError"]
        assert ctx.state.get(cua.binding_state_key(ctx)) is None
    finally:
        await cua.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runner_kind", ["google_adk", "veadk"])
async def test_runner_receives_actions_before_first_model_call_and_image(runner_kind):
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    class ScriptedModel(BaseLlm):
        step: int = 0

        async def generate_content_async(self, llm_request, stream=False):
            names = set(llm_request.tools_dict)
            if self.step == 0:
                assert "cua_screenshot" in names
                call = types.FunctionCall(name="cua_screenshot", args={})
            else:
                images = [
                    part
                    for content in llm_request.contents
                    for part in content.parts or []
                    if part.function_response and part.function_response.parts
                ]
                assert images, (
                    "Screenshot must be media, not a base64 string for the model"
                )
                yield LlmResponse(
                    content=types.Content(role="model", parts=[types.Part(text="done")])
                )
                return
            self.step += 1
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(function_call=call)]
                )
            )

    cua = toolset()
    model = ScriptedModel(model="local-test")
    if runner_kind == "veadk":
        from veadk import Agent as VeAgent, Runner

        agent = VeAgent(
            name="agent", model=model, model_api_key="offline-fixture", tools=[cua]
        )
        runner = Runner(
            agent=agent, app_name="app", session_service=InMemorySessionService()
        )
    else:
        agent = Agent(name="agent", model=model, tools=[cua])
        runner = InMemoryRunner(agent=agent, app_name="app")
    await runner.session_service.create_session(
        app_name="app", user_id="user", session_id="one"
    )
    try:
        events = [
            event
            async for event in runner.run_async(
                user_id="user",
                session_id="one",
                new_message=types.Content(role="user", parts=[types.Part(text="test")]),
            )
        ]
        assert any(event.is_final_response() for event in events)
        saved = await runner.session_service.get_session(
            app_name="app", user_id="user", session_id="one"
        )
        assert (
            saved.state[
                next(key for key in saved.state if key.startswith(cua.state_key))
            ]["session_id"]
            == "s-1"
        )
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_subagents_in_same_session_keep_distinct_bindings():
    cua = toolset()
    first, readonly = await context("shared")
    try:
        await (await cua.get_tools(readonly))[0].run_async(args={}, tool_context=first)
        first.session.state.update(first.state.to_dict())
        second = ToolContext(
            InvocationContext(
                session_service=first._invocation_context.session_service,
                invocation_id="second",
                agent=Agent(name="other_agent"),
                session=first.session,
            )
        )
        result = await (await cua.get_tools(second))[0].run_async(
            args={}, tool_context=second
        )
        assert result["structuredContent"]["session_id"] == "s-2"
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_history_parallel_run_code_is_not_silently_attached():
    from google.adk.events import Event
    from google.genai import types

    cua = toolset()
    ctx, readonly = await context("one")
    ctx.session.events.append(
        Event(
            author="agent",
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(name="run_code", args={})
                    ),
                    types.Part(
                        function_call=types.FunctionCall(name="run_code", args={})
                    ),
                ],
            ),
        )
    )
    try:
        with pytest.raises(ValueError, match="Parallel run_code history"):
            await cua.get_tools(readonly)
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_allowlist_retains_bootstrap_and_closes_child():
    cua = toolset()
    cua.tool_filter = ["cua_screenshot"]
    ctx, readonly = await context("one")
    tool = (await cua.get_tools(readonly))[0]
    await tool.run_async(args={}, tool_context=ctx)
    assert {t.name for t in await cua.get_tools(readonly)} == {
        "ensure_sandbox",
        "cua_screenshot",
    }
    await cua.close()
    assert not cua._manager._sessions


@pytest.mark.asyncio
async def test_tool_cancellation_propagates_and_mutations_not_retried():
    import asyncio
    from unittest.mock import AsyncMock
    from mcp import types
    from veadk.tools.builtin_tools.computer_use import _ComputerTool

    cua = toolset()
    ctx, _ = await context("one")
    session = AsyncMock()
    session.call_tool.side_effect = ConnectionError("SENSITIVE_URL")
    cua._manager.create_session = AsyncMock(return_value=session)
    tool = _ComputerTool(
        types.Tool(name="cua_click", inputSchema={"type": "object"}), cua
    )
    result = await tool.run_async(args={}, tool_context=ctx)
    assert result["isError"]
    assert "SENSITIVE" not in str(result)
    assert session.call_tool.await_count == 1
    session.call_tool.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await tool.run_async(args={}, tool_context=ctx)
    assert session.call_tool.await_count == 2
    await cua.close()


@pytest.mark.asyncio
async def test_saved_binding_reconnects_after_mcp_process_restart():
    ctx, readonly = await context("one")
    first = toolset()
    try:
        await (await first.get_tools(readonly))[0].run_async(args={}, tool_context=ctx)
        ctx.session.state.update(ctx.state.to_dict())
    finally:
        await first.close()
    second = create_computer_use_toolset(
        connection_params=StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("stdio_fixture.py")), "--existing"],
        ),
        tool_id="t-example",
    )
    try:
        assert "cua_screenshot" in {
            tool.name for tool in await second.get_tools(readonly)
        }
        result = await (await second.get_tools(readonly))[0].run_async(
            args={}, tool_context=ctx
        )
        assert result["structuredContent"]["session_id"] == "s-1"
    finally:
        await second.close()


@pytest.mark.asyncio
async def test_unchanged_run_code_result_not_used_for_binding(monkeypatch):
    import importlib

    module = importlib.import_module("veadk.tools.builtin_tools.run_code")
    ctx, readonly = await context("one")
    invoked = []

    def invoke(**kwargs):
        invoked.append(kwargs)
        return {"Result": {"Result": "only-program-output"}}

    monkeypatch.setattr(module, "resolve_agentkit_tool_id", lambda *args: "t-example")
    monkeypatch.setattr(
        module,
        "get_agentkit_endpoint_config",
        lambda: ("agentkit", "cn-beijing", "unused.example", "https"),
    )
    monkeypatch.setattr(module, "invoke_agentkit_run_code", invoke)
    assert module.run_code("print(1)", "python3", ctx) == "only-program-output"
    cua = create_computer_use_toolset(
        connection_params=StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("stdio_fixture.py")), "--existing"],
        ),
        tool_id="t-example",
    )
    try:
        result = await (await cua.get_tools(readonly))[0].run_async(
            args={}, tool_context=ctx
        )
        assert (
            result["structuredContent"]["user_session_id"]
            == invoked[0]["tool_user_session_id"]
        )
        assert result["structuredContent"]["session_id"] == "s-1"
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_runner_stops_before_model_when_mcp_discovery_fails(caplog):
    from unittest.mock import AsyncMock
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    calls = []

    class NoCallModel(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            calls.append(True)
            yield LlmResponse(
                content=types.Content(
                    role="model", parts=[types.Part(text="must not run")]
                )
            )

    cua = toolset()
    cua._manager.create_session = AsyncMock(
        side_effect=ConnectionError("private endpoint")
    )
    runner = InMemoryRunner(
        agent=Agent(name="agent", model=NoCallModel(model="offline"), tools=[cua]),
        app_name="app",
    )
    await runner.session_service.create_session(
        app_name="app", user_id="user", session_id="one"
    )
    try:
        with pytest.raises(RuntimeError, match="discovery failed"):
            _ = [
                event
                async for event in runner.run_async(
                    user_id="user",
                    session_id="one",
                    new_message=types.Content(
                        role="user", parts=[types.Part(text="test")]
                    ),
                )
            ]
        assert not calls
        assert "install a compatible template-fixed-v1 MCP wheel" in caplog.text
        assert "current local candidate" not in caplog.text
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_ark_accepts_default_cache_without_mutating_agent():
    from google.adk.models.llm_request import LlmRequest
    from veadk.models.ark_llm import ArkLlm

    cua = toolset()
    ctx, _ = await context("one")
    agent = ctx._invocation_context.agent
    agent.model = ArkLlm(model="openai/offline", enable_responses_cache=True)
    try:
        await cua.process_llm_request(tool_context=ctx, llm_request=LlmRequest())
        assert agent.model.enable_responses_cache is True
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_ark_receives_screenshot_media_from_function_response_parts():
    from google.adk.models.llm_request import LlmRequest
    from google.genai import types
    from veadk.models.ark_llm import ArkLlm, _get_responses_inputs

    cua = toolset()
    ctx, _ = await context("one")
    ctx._invocation_context.agent.model = ArkLlm(
        model="openai/offline", enable_responses_cache=False
    )
    req = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            name="cua_screenshot",
                            id="shot-1",
                            response={"isError": False},
                            parts=[
                                types.FunctionResponsePart(
                                    inline_data=types.FunctionResponseBlob(
                                        mime_type="image/png", data=b"png"
                                    )
                                )
                            ],
                        )
                    )
                ],
            )
        ]
    )
    try:
        await cua.process_llm_request(tool_context=ctx, llm_request=req)
        inputs = _get_responses_inputs(req)[1]
        assert any(
            item.get("type") == "message"
            and any(p.get("type") == "input_image" for p in item.get("content", []))
            for item in inputs
        )
        await cua.process_llm_request(tool_context=ctx, llm_request=req)
        assert len(req.contents) == 2
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_discovery_and_pure_chat_never_call_ensure_or_create():
    from unittest.mock import AsyncMock
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models import LlmResponse
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    class Chat(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            assert "cua_screenshot" in llm_request.tools_dict
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="hello")])
            )

    cua = toolset()
    session = await cua._manager.create_session()
    session.call_tool = AsyncMock(wraps=session.call_tool)
    runner = InMemoryRunner(
        agent=Agent(name="agent", model=Chat(model="offline"), tools=[cua]),
        app_name="app",
    )
    await runner.session_service.create_session(
        app_name="app", user_id="user", session_id="one"
    )
    try:
        for _ in range(2):
            events = [
                e
                async for e in runner.run_async(
                    user_id="user",
                    session_id="one",
                    new_message=types.Content(
                        role="user", parts=[types.Part(text="hello")]
                    ),
                )
            ]
        assert events
        assert session.call_tool.await_count == 0
        saved = await runner.session_service.get_session(
            app_name="app", user_id="user", session_id="one"
        )
        assert not any(k.startswith(cua.state_key) for k in saved.state)
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_concurrent_readonly_discovery_does_not_ensure():
    import asyncio
    from unittest.mock import AsyncMock

    cua = toolset()
    ctx, ro = await context("one")
    try:
        session = await cua._manager.create_session()
        session.call_tool = AsyncMock(wraps=session.call_tool)
        results = await asyncio.gather(*(cua.get_tools(ro) for _ in range(5)))
        assert all("cua_screenshot" in {t.name for t in r} for r in results)
        assert session.call_tool.await_count == 0
        assert ctx.state.get(cua.binding_state_key(ctx)) is None
        tool = next(t for t in results[0] if t.name == "cua_screenshot")
        await tool.run_async(args={}, tool_context=ctx)
        assert session.call_tool.await_count == 1
        assert ctx.state[cua.binding_state_key(ctx)]["session_id"] == "s-1"
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_disabled_template_list_leaves_session_unbound():
    cua = create_computer_use_toolset(
        tool_id="t-example",
        connection_params=StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("stdio_fixture.py")), "--disabled"],
        ),
    )
    ctx, ro = await context("one")
    try:
        assert [t.name for t in await cua.get_tools(ro)] == ["ensure_sandbox"]
        assert ctx.state.get(cua.binding_state_key(ctx)) is None
    finally:
        await cua.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["permission", "cancel", "old_server", "invalid_binding"]
)
async def test_discovery_fails_closed_without_creating(failure):
    import asyncio
    from unittest.mock import AsyncMock
    from mcp import types
    from google.adk.models import LlmRequest

    cua = toolset()
    ctx, ro = await context("one")
    session = AsyncMock()
    session.list_tools.return_value = types.ListToolsResult(
        tools=[],
        _meta={"veadk/cua": {"discovery_mode": "template-fixed-v1", "binding": None}},
    )
    if failure == "permission":
        session.list_tools.side_effect = RuntimeError("SENSITIVE")
    if failure == "cancel":
        session.list_tools.side_effect = asyncio.CancelledError()
    if failure == "old_server":
        session.list_tools.return_value.meta = None
    if failure == "invalid_binding":
        session.list_tools.return_value.meta["veadk/cua"]["binding"] = {
            "session_id": "s-other",
            "user_session_id": "other",
        }
    cua._manager.create_session = AsyncMock(return_value=session)
    try:
        with pytest.raises(
            asyncio.CancelledError if failure == "cancel" else RuntimeError
        ):
            await cua.get_tools(ro)
        assert session.call_tool.await_count == 0
        with pytest.raises(RuntimeError, match="model invocation aborted"):
            await cua.process_llm_request(tool_context=ctx, llm_request=LlmRequest())
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_readonly_attach_persists_existing_instance_in_database(tmp_path):
    from google.adk.sessions import DatabaseSessionService

    cua = create_computer_use_toolset(
        tool_id="t-example",
        connection_params=StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("stdio_fixture.py")), "--existing"],
        ),
    )
    service = DatabaseSessionService(
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"
    )
    session = await service.create_session(
        app_name="app", user_id="user", session_id="one"
    )
    ctx = ReadonlyContext(
        InvocationContext(
            session_service=service,
            invocation_id="turn",
            agent=Agent(name="agent"),
            session=session,
        )
    )
    try:
        await cua.get_tools(ctx)
        saved = await service.get_session(
            app_name="app", user_id="user", session_id="one"
        )
        assert saved.state[cua.binding_state_key(ctx)]["session_id"] == "s-1"
    finally:
        await cua.close()
        await service.close()


@pytest.mark.asyncio
async def test_action_failure_preserves_binding_and_hides_routing_from_model():
    from unittest.mock import AsyncMock
    from mcp import types
    from veadk.tools.builtin_tools.computer_use import _ComputerTool

    cua = toolset()
    ctx, _ = await context("one")
    session = AsyncMock()
    session.call_tool.return_value = types.CallToolResult(
        isError=True,
        content=[types.TextContent(type="text", text="COMPUTER_DISABLED")],
        _meta={
            "veadk/cua": {
                "binding": {"user_session_id": "agent_user_one", "session_id": "s-1"}
            }
        },
    )
    cua._manager.create_session = AsyncMock(return_value=session)
    try:
        tool = _ComputerTool(
            types.Tool(name="cua_screenshot", inputSchema={"type": "object"}), cua
        )
        result = await tool.run_async(args={}, tool_context=ctx)
        assert result["isError"]
        assert ctx.state[cua.binding_state_key(ctx)]["session_id"] == "s-1"
        assert "meta" not in result and "_meta" not in result
        assert session.call_tool.await_count == 1
    finally:
        await cua.close()
