"""Tool argument contracts through the real ADK execution boundary."""

import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from google.adk.tools import FunctionTool, AgentTool
from google.adk.agents import LlmAgent
from veadk import Agent

from tests.routing.test_turn_contract import Judge, RecordingLlm, routed, setup, turn
from veadk.routing.context import RouteSelection, TurnContext, _TURN
from veadk.routing.tool_arguments import validate_tool_arguments


class ToolCaller(RecordingLlm):
    arguments: list[dict]

    async def generate_content_async(self, llm_request, stream=False):
        self.calls.append(copy.deepcopy(llm_request.contents))
        index = len(self.calls) - 1
        part = (
            types.Part(
                function_call=types.FunctionCall(
                    name="multiply", id=f"call-{index}", args=self.arguments[index]
                )
            )
            if index < len(self.arguments)
            else types.Part(text="complete")
        )
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        [{"quantity": "7", "price": "19"}],
        [{"quantity": "7.5", "price": 19}, {"quantity": 7, "price": 19}],
        [{"quantity": True, "price": 19}, {"quantity": 7, "price": 19}],
        [{"quantity": 7}, {"quantity": 7, "price": 19}],
    ],
)
async def test_invalid_arguments_corrected_without_switching_or_side_effect(
    monkeypatch, arguments
):
    effects = []

    def multiply(quantity: int, price: int) -> dict:
        effects.append((quantity, price))
        return {"total": quantity * price}

    cheap = ToolCaller(model="cheap", arguments=arguments)
    strong, judge = RecordingLlm(model="strong"), Judge()
    root = routed(monkeypatch, judge, strong, cheap, tools=[multiply])
    runner, session = await setup(root)
    try:
        events = await turn(runner, session, "Calculate the total")
        assert effects == [(7, 19)]
        assert all(type(value) is int for value in effects[0])
        assert len(judge.calls) == 1 and not strong.calls
        results = [
            p.function_response.response
            for e in events
            if e.content
            for p in e.content.parts or []
            if p.function_response
        ]
        assert results[-1] == {"total": 133}
        if len(arguments) > 1:
            assert results[0]["error"] == "invalid_tool_arguments"
            assert results[0]["retryable"] is True
    finally:
        await runner.close()


def binding(invocation="root-turn"):
    return TurnContext(
        RouteSelection("simple", "test", invocation), None, None, "target"
    )


def declared(schema=None, *, genai=None):
    declaration = types.FunctionDeclaration(
        name="tool", parameters_json_schema=schema, parameters=genai
    )
    return SimpleNamespace(_get_declaration=lambda: declaration)


@pytest.mark.asyncio
async def test_guard_opt_out_and_absent_declarations():
    args = {"count": "3"}
    assert await validate_tool_arguments(object(), args, object()) is None
    assert args == {"count": "3"}
    token = _TURN.set(binding())
    try:
        assert await validate_tool_arguments(declared(), args, object()) is None
        assert (
            await validate_tool_arguments(
                SimpleNamespace(_get_declaration=lambda: None), args, object()
            )
            is None
        )
    finally:
        _TURN.reset(token)


@pytest.mark.asyncio
async def test_shadow_does_not_change_tool_arguments_or_execute_validation():
    context = binding()
    context = replace(context, selection=replace(context.selection, shadow=True))
    token = _TURN.set(context)
    args = {"count": "7"}
    try:
        assert await validate_tool_arguments(object(), args, object()) is None
        assert args == {"count": "7"}
        assert not context.tool_argument_errors
    finally:
        _TURN.reset(token)


@pytest.mark.asyncio
async def test_nested_schema_references_arrays_and_nullable():
    schema = {
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {"$ref": "#/$defs/Item"}},
            "note": {"type": ["string", "null"]},
        },
        "$defs": {
            "Item": {"type": "object", "properties": {"count": {"type": "integer"}}}
        },
    }
    args = {"items": [{"count": "17"}], "note": None}
    token = _TURN.set(binding())
    try:
        assert (
            await validate_tool_arguments(
                declared(schema), args, SimpleNamespace(state={})
            )
            is None
        )
        assert args == {"items": [{"count": 17}], "note": None}
        args = {"note": None}
        genai = types.Schema(
            type="OBJECT",
            properties={"note": types.Schema(type="STRING", nullable=True)},
        )
        assert (
            await validate_tool_arguments(
                declared(genai=genai), args, SimpleNamespace(state={})
            )
            is None
        )
    finally:
        _TURN.reset(token)


@pytest.mark.asyncio
async def test_schema_constants_are_data_not_rewritten_schema():
    tool = declared(
        {
            "type": "object",
            "properties": {
                "value": {
                    "const": {"type": "INTEGER", "$ref": "https://example.test/data"}
                }
            },
        }
    )
    args = {"value": {"type": "INTEGER", "$ref": "https://example.test/data"}}
    token = _TURN.set(binding())
    try:
        assert (
            await validate_tool_arguments(tool, args, SimpleNamespace(state={})) is None
        )
        assert args["value"]["type"] == "INTEGER"
    finally:
        _TURN.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid", ["7.0", "01", "+7", "1e3", True, 1.2, None, "9" * 130]
)
async def test_ambiguous_or_lossy_coercion_is_rejected_without_argument_leak(invalid):
    tool = declared({"type": "object", "properties": {"count": {"type": "integer"}}})
    token = _TURN.set(binding())
    try:
        args = {"count": invalid}
        result = await validate_tool_arguments(tool, args, SimpleNamespace(state={}))
        assert result["error"] == "invalid_tool_arguments"
        assert result["issues"] == [
            {"schema_path": ["properties", "count", "type"], "rule": "type"}
        ]
        assert args == {"count": invalid}
    finally:
        _TURN.reset(token)


@pytest.mark.asyncio
async def test_budget_shared_by_nested_tasks_persisted_for_resume_and_reset_next_turn():
    tool = declared({"type": "object", "required": ["count"]})
    state = {}
    token = _TURN.set(binding())
    try:
        await validate_tool_arguments(tool, {}, SimpleNamespace(state=state))
        await validate_tool_arguments(tool, {}, SimpleNamespace(state={}))
        with pytest.raises(ValueError, match="budget exhausted"):
            await validate_tool_arguments(tool, {}, SimpleNamespace(state=state))
    finally:
        _TURN.reset(token)
    token = _TURN.set(binding())
    try:
        with pytest.raises(ValueError, match="budget exhausted"):
            await validate_tool_arguments(tool, {}, SimpleNamespace(state=state))
    finally:
        _TURN.reset(token)
    token = _TURN.set(binding("next-turn"))
    try:
        result = await validate_tool_arguments(tool, {}, SimpleNamespace(state=state))
        assert result["corrections_remaining"] == 1
    finally:
        _TURN.reset(token)


@pytest.mark.asyncio
async def test_remote_schema_reference_does_not_trigger_network():
    token = _TURN.set(binding())
    try:
        with pytest.raises(ValueError, match="local references"):
            await validate_tool_arguments(
                declared({"$ref": "https://example.test/schema"}),
                {},
                SimpleNamespace(state={}),
            )
    finally:
        _TURN.reset(token)


@pytest.mark.asyncio
async def test_invalid_arguments_have_bounded_correction_budget(monkeypatch):
    effects = []

    def multiply(quantity: int, price: int) -> dict:
        effects.append(True)
        return {"total": quantity * price}

    cheap = ToolCaller(
        model="cheap", arguments=[{"quantity": "invalid", "price": 19}] * 4
    )
    root = routed(
        monkeypatch, Judge(), RecordingLlm(model="strong"), cheap, tools=[multiply]
    )
    runner, session = await setup(root)
    try:
        with pytest.raises(
            ValueError, match="tool argument correction budget exhausted"
        ):
            await turn(runner, session, "Calculate")
        assert not effects
        assert len(cheap.calls) == 3
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_opt_out_retains_original_tool_behavior():
    def multiply(quantity: int, price: int) -> dict:
        return {"total": quantity * price}

    agent = Agent(
        name="plain",
        model=ToolCaller(model="test", arguments=[{"quantity": "7", "price": "19"}]),
        model_api_key="test-only",
        query_routing=False,
        tools=[multiply],
    )
    runner, session = await setup(agent)
    try:
        with pytest.raises(TypeError):
            await turn(runner, session, "Calculate")
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_user_callback_and_confirmation_are_preserved(monkeypatch):
    effects = []
    callbacks = []

    def multiply(quantity: int, price: int) -> dict:
        effects.append(True)
        return {"total": quantity * price}

    def before_tool(tool, args, tool_context):
        callbacks.append(dict(args))
        args["quantity"] = "7"

    tool = FunctionTool(multiply, require_confirmation=True)
    root = routed(
        monkeypatch,
        Judge(),
        RecordingLlm(model="strong"),
        ToolCaller(model="cheap", arguments=[{"quantity": "bad", "price": "19"}]),
        tools=[tool],
        before_tool_callback=before_tool,
    )
    runner, session = await setup(root)
    try:
        events = await turn(runner, session, "Calculate")
        assert callbacks == [{"quantity": "bad", "price": "19"}]
        assert not effects
        assert any(e.actions.requested_tool_confirmations for e in events)
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_native_agent_tool_inherits_generic_argument_validation(monkeypatch):
    from tests.routing.test_turn_contract import DelegatingLlm

    effects = []

    def multiply(quantity: int, price: int) -> dict:
        effects.append((quantity, price))
        return {"total": quantity * price}

    class NestedCaller(DelegatingLlm):
        async def generate_content_async(self, llm_request, stream=False):
            if "multiply" in llm_request.tools_dict:
                self.calls.append(copy.deepcopy(llm_request.contents))
                has_result = any(
                    p.function_response
                    for c in llm_request.contents
                    for p in c.parts or []
                )
                part = (
                    types.Part(text="done")
                    if has_result
                    else types.Part(
                        function_call=types.FunctionCall(
                            name="multiply",
                            id="nested",
                            args={"quantity": "7", "price": "19"},
                        )
                    )
                )
                yield LlmResponse(content=types.Content(role="model", parts=[part]))
            else:
                async for response in super().generate_content_async(
                    llm_request, stream
                ):
                    yield response

    child = LlmAgent(name="child", model=RecordingLlm(model="unused"), tools=[multiply])
    cheap = NestedCaller(model="cheap")
    root = routed(
        monkeypatch,
        Judge(),
        RecordingLlm(model="strong"),
        cheap,
        tools=[AgentTool(child)],
    )
    runner, session = await setup(root)
    try:
        await turn(runner, session, "Calculate")
        assert effects == [(7, 19)]
        assert not child.model.calls
    finally:
        await runner.close()
