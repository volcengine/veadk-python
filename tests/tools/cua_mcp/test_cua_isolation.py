import ast
from pathlib import Path

import pytest
from google.adk.models import LlmRequest
from google.genai import types

from veadk.models.ark_llm import _get_responses_inputs
from test_toolset import context, toolset


@pytest.mark.parametrize(
    "name",
    [
        "cua_screenshot",
        "cua_actions_batch",
        "cua_click",
        "cua_typing",
        "cua_node_invoke",
    ],
)
def test_every_cua_image_reaches_unmodified_ark_without_editing_event(name):
    from veadk.tools.computer_use.media import lift_screenshots

    original = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    name=name,
                    id="call",
                    response={"done": True},
                    parts=[
                        types.FunctionResponsePart(
                            inline_data=types.FunctionResponseBlob(
                                mime_type="image/png", data=b"png-fixture"
                            )
                        )
                    ],
                )
            )
        ],
    )
    request = LlmRequest(contents=[original])
    lift_screenshots(request)
    lift_screenshots(request)
    inputs = _get_responses_inputs(request)[1]
    assert (
        sum(
            p.get("type") == "input_image" for i in inputs for p in i.get("content", [])
        )
        == 1
    )
    assert original.parts[0].function_response.parts
    assert not request.contents[0].parts[0].function_response.parts


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_id", [None, "resp-existing"])
async def test_toolset_preserves_request_context_without_rebuilding_history(
    monkeypatch, previous_id
):
    from google.adk.flows.llm_flows.contents import request_processor
    from veadk.models.ark_llm import ArkLlm

    def reject_history_rebuild(*args, **kwargs):
        raise AssertionError("CUA must not rerun ADK's history processor")

    monkeypatch.setattr(request_processor, "run_async", reject_history_rebuild)
    cua = toolset()
    ctx, _ = await context("request-only")
    ctx._invocation_context.agent.model = ArkLlm(model="openai/offline")
    request = LlmRequest(
        previous_interaction_id=previous_id,
        contents=[
            types.Content(
                role="user", parts=[types.Part(text="request-only instruction")]
            )
        ],
    )
    before = request.model_dump()
    try:
        await cua.process_llm_request(tool_context=ctx, llm_request=request)
        assert request.model_dump() == before
    finally:
        await cua.close()


def test_generic_model_source_has_no_cua_branch():
    path = Path(__file__).resolve().parents[3] / "veadk/models/ark_llm.py"
    source = path.read_text()
    assert "_veadk_cua" not in source
    assert "_cua_responses" not in source
    ast.parse(source)


@pytest.mark.asyncio
async def test_toolset_does_not_replace_model_or_require_binding():
    cua = toolset()
    ctx, _ = await context("one")
    agent = ctx._invocation_context.agent
    model = agent.model
    request = LlmRequest(contents=[])
    try:
        await cua.process_llm_request(tool_context=ctx, llm_request=request)
        assert agent.model is model
        assert not hasattr(request, "_veadk_cua_context")
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_fixed_catalog_rejects_filter_change_without_model_call():
    cua = toolset()
    ctx, readonly = await context("one")
    try:
        await cua.get_tools(readonly)
        cua.tool_filter = ["cua_screenshot"]
        with pytest.raises(RuntimeError, match="catalog.*changed"):
            await cua.get_tools(readonly)
    finally:
        await cua.close()


@pytest.mark.asyncio
async def test_legacy_mcp_discovery_contract_fails_before_model():
    from unittest.mock import AsyncMock
    from mcp import types as mcp_types

    cua = toolset()
    _, readonly = await context("legacy")
    session = AsyncMock()
    session.list_tools.return_value = mcp_types.ListToolsResult(
        tools=[], _meta={"veadk/cua": {"discovery_mode": "lazy-v1"}}
    )
    cua._manager.create_session = AsyncMock(return_value=session)
    try:
        with pytest.raises(RuntimeError, match="discovery failed"):
            await cua.get_tools(readonly)
    finally:
        await cua.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["none", "template", "schema"])
async def test_catalog_is_checked_after_child_restart_and_new_invocation(change):
    from unittest.mock import AsyncMock
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.agents.readonly_context import ReadonlyContext

    cua = toolset()
    ctx, readonly = await context("restart_catalog")
    invocation = ctx._invocation_context
    try:
        original = await cua.get_tools(readonly)
        saved = await invocation.session_service.get_session(
            app_name="app", user_id="user", session_id="restart_catalog"
        )
        assert any(key.startswith("veadk_cua_catalog_") for key in saved.state)
        assert ctx.state.get(cua.binding_state_key(ctx)) is None
    finally:
        await cua.close()

    restored = toolset()
    new_context = ReadonlyContext(
        InvocationContext(
            session_service=invocation.session_service,
            invocation_id="next-turn",
            agent=invocation.agent,
            session=saved,
        )
    )
    try:
        if change != "none":
            session = await restored._manager.create_session()
            from mcp import types as mcp_types

            result = await session.list_tools(
                params=mcp_types.PaginatedRequestParams(
                    _meta=restored._metadata(new_context)
                )
            )
            if change == "template":
                result.tools = [t for t in result.tools if t.name == "ensure_sandbox"]
            else:
                result.tools[1].inputSchema["description"] = "changed schema"
            session.list_tools = AsyncMock(return_value=result)
            with pytest.raises(RuntimeError, match="catalog.*changed"):
                await restored.get_tools(new_context)
        else:
            tools = await restored.get_tools(new_context)
            assert [t.name for t in tools] == [t.name for t in original]
    finally:
        await restored.close()
