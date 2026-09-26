"""Budget-pressure regressions using synthetic evidence and the real manager."""

import copy
import math
from types import SimpleNamespace

import pytest
from google.genai import types
from test_recoverable_context import mcp_source, read

from veadk.context.budget import ContextBudgetError, count_input, request_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.manager import prepare_context
from veadk.context.runtime import current_scope
from veadk.context.tool_results import READ_CONTEXT_TOOL


def example(cap):
    text = "".join(
        f"Record {i}: warehouse {i * 17}, audited balance {i * 23} units.\n"
        for i in range(240 if cap == 16000 else 430)
    )
    request, scope = mcp_source(text)
    request.contents.insert(
        0,
        types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id="fetch-1", name="fetch", args={}
                    )
                )
            ],
        ),
    )
    request.contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text="What is the audited balance for record 113?")],
        )
    )
    request.model = "deepseek-v4-1-flash-260910"
    request.config.max_output_tokens = 1024
    base = ContextCompressionConfig(context_window=256000, tool_result_max_bytes=cap)
    before = count_input(request_payload(request), base)
    policy = base.model_copy(update={"input_limit": math.ceil(before / 0.97)})
    assert 10000 < len(text.encode()) < cap
    return text, request, scope, policy, before


@pytest.mark.asyncio
@pytest.mark.parametrize("cap", [16000, 32000])
async def test_below_configured_cap_still_fits_pressure_and_original_is_readable(cap):
    text, request, scope, policy, before = example(cap)
    original = copy.deepcopy(scope.session.events)
    token = current_scope.set(scope)
    try:
        await prepare_context(request, SimpleNamespace(model=request.model), policy, {})
    finally:
        current_scope.reset(token)
    after = count_input(request_payload(request), policy)
    assert after < before
    assert after <= policy.input_limit - min(1024, policy.input_limit // 20)
    assert READ_CONTEXT_TOOL in request.tools_dict
    import re

    ref = re.search(
        r"ctx_[a-f0-9]{24}", "".join(c.model_dump_json() for c in request.contents)
    )[0]
    result = await read(request, scope, ref, query="Record 113:")
    assert result["text"] == text[result["offset"] : result["end"]]
    assert "audited balance 2599 units" in result["text"]
    assert scope.session.events == original


@pytest.mark.asyncio
async def test_pressure_does_not_override_explicit_protected_evidence():
    text, request, scope, policy, _ = example(32000)
    policy = policy.model_copy(update={"protected_context": ("Record 113:",)})
    original = copy.deepcopy(scope.session.events)
    token = current_scope.set(scope)
    try:
        with pytest.raises(ContextBudgetError):
            await prepare_context(
                request, SimpleNamespace(model=request.model), policy, {}
            )
    finally:
        current_scope.reset(token)
    assert (
        request.contents[1].parts[0].function_response.response["content"][0]["text"]
        == text
    )
    assert scope.session.events == original


@pytest.mark.asyncio
async def test_sufficient_budget_does_not_project_short_tool_result():
    _, request, scope, policy, _ = example(32000)
    policy = policy.model_copy(update={"input_limit": 200000})
    original = copy.deepcopy(request.contents)
    token = current_scope.set(scope)
    try:
        await prepare_context(request, SimpleNamespace(model=request.model), policy, {})
    finally:
        current_scope.reset(token)
    assert request.contents == original
    assert READ_CONTEXT_TOOL not in request.tools_dict
