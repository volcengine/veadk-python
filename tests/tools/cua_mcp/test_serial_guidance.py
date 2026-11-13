"""Multi-call turns are rejected as recoverable CUA results, never dispatched."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from google.adk.events import Event
from google.genai import types
from test_toolset import context, toolset


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_visible", [True, False])
@pytest.mark.parametrize("source", ["counter", "event", "mixed_run_code"])
async def test_multi_call_rejection_is_actionable_without_dispatch(
    batch_visible, source
):
    cua = toolset()
    if not batch_visible:
        cua.tool_filter = ["cua_click"]
    ctx, readonly = await context("reject")
    try:
        tools = await cua.get_tools(readonly)
        session = await cua._manager.create_session()
        session.call_tool = AsyncMock(wraps=session.call_tool)
        if source == "counter":
            ctx._veadk_parallel_tool_call_count = 2
        else:
            ctx.session.events.append(
                Event(
                    author="agent",
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="run_code"
                                    if source == "mixed_run_code" and i == 1
                                    else "cua_click",
                                    args={},
                                    id=str(i),
                                )
                            )
                            for i in range(2)
                        ],
                    ),
                )
            )
        click = next(t for t in tools if t.name == "cua_click")
        result = await click.run_async(args={}, tool_context=ctx)
        assert result["isError"] is True
        assert result["structuredContent"]["code"] == "CUA_MULTIPLE_TOOL_CALLS_REJECTED"
        assert result["structuredContent"]["executed"] is False
        message = result["content"][0]["text"]
        assert ("cua_actions_batch" in message) is batch_visible
        assert "one tool call" in message
        if batch_visible:
            assert "action_type" in message and "run_code" in message
        assert session.call_tool.await_count == 0
        assert ctx.state.get(cua.binding_state_key(ctx)) is None
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_real_runner_recovers_from_multi_call_to_one_batch():
    from google.adk.agents import Agent
    from google.adk.models import LlmResponse
    from google.adk.models.base_llm import BaseLlm
    from google.adk.runners import InMemoryRunner

    class Model(BaseLlm):
        step: int = 0

        async def generate_content_async(self, request, stream=False):
            if self.step == 0:
                parts = [
                    types.Part(
                        function_call=types.FunctionCall(
                            id=f"bad-{i}", name="cua_click", args={}
                        )
                    )
                    for i in range(2)
                ]
            elif self.step == 1:
                responses = [
                    p.function_response
                    for c in request.contents
                    for p in c.parts or []
                    if p.function_response
                ]
                assert len(responses) == 2
                assert all(r.response["isError"] for r in responses)
                assert all("cua_actions_batch" in str(r.response) for r in responses)
                parts = [
                    types.Part(
                        function_call=types.FunctionCall(
                            id="batch",
                            name="cua_actions_batch",
                            args={
                                "actions": [
                                    {"action_type": "CLICK"},
                                    {"action_type": "TYPING", "text": "fixture"},
                                ]
                            },
                        )
                    )
                ]
            else:
                response = [
                    p.function_response
                    for c in request.contents
                    for p in c.parts or []
                    if p.function_response
                ][-1]
                assert (
                    response.name == "cua_actions_batch"
                    and not response.response.get("isError")
                )
                assert response.response["structuredContent"]["data"]["performed"] == [
                    "CLICK",
                    "TYPING",
                ]
                parts = [types.Part(text="done")]
            self.step += 1
            yield LlmResponse(content=types.Content(role="model", parts=parts))

    cua = toolset()
    model = Model(model="local-scripted")
    runner = InMemoryRunner(
        agent=Agent(name="agent", model=model, tools=[cua]), app_name="app"
    )
    await runner.session_service.create_session(
        app_name="app", user_id="user", session_id="recovery"
    )
    try:
        session = await cua._manager.create_session()
        session.call_tool = AsyncMock(wraps=session.call_tool)
        events = [
            event
            async for event in runner.run_async(
                user_id="user",
                session_id="recovery",
                new_message=types.Content(role="user", parts=[types.Part(text="test")]),
            )
        ]
        assert model.step == 3
        assert any(e.is_final_response() for e in events)
        assert session.call_tool.await_count == 1
        assert session.call_tool.call_args.args[0] == "cua_actions_batch"
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_disabled_template_never_recommends_batch():
    import sys
    from mcp import StdioServerParameters
    from veadk.tools.builtin_tools.computer_use import create_computer_use_toolset

    cua = create_computer_use_toolset(
        tool_id="t-example",
        connection_params=StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("stdio_fixture.py")), "--disabled"],
        ),
    )
    ctx, readonly = await context("off")
    try:
        tools = await cua.get_tools(readonly)
        assert [t.name for t in tools] == ["ensure_sandbox"]
        ctx._veadk_parallel_tool_call_count = 2
        result = await tools[0].run_async(args={}, tool_context=ctx)
        assert result["isError"] and "cua_actions_batch" not in str(result)
        assert ctx.state.get(cua.binding_state_key(ctx)) is None
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_mcp_descriptions_reach_model_declarations():
    cua = toolset()
    _, readonly = await context("schema")
    try:
        tools = await cua.get_tools(readonly)
        assert len(tools) == 55
        for tool in tools:
            declaration = tool._get_declaration().model_dump(
                mode="json", exclude_none=True
            )
            assert len(declaration["description"]) >= 80
            schema = declaration.get("parameters_json_schema") or declaration.get(
                "parameters"
            )
            assert schema and schema.get("description")
            for name, field in schema.get("properties", {}).items():
                assert field.get("description"), (tool.name, name)
        batch = next(t for t in tools if t.name == "cua_actions_batch")
        assert (
            "one tool call" in batch.description and "no rollback" in batch.description
        )
    finally:
        await cua.close()
