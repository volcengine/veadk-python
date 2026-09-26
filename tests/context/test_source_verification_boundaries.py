"""Caller ownership, invocation isolation and admission for read-first trials."""

import asyncio
import copy
from types import SimpleNamespace

import pytest
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions import Session
from google.genai import types

from veadk.context.budget import ContextBudgetError
from veadk.context.client import BudgetedLiteLLMClient
from veadk.context.config import ContextCompressionConfig
from veadk.context.manager import prepare_context
from veadk.context.runtime import ContextScope, current_scope, is_summary
from veadk.context.source_verification import source_verification_choice


def policy(**changes):
    return ContextCompressionConfig(
        context_window=32000, output_reserve=1024, verify_sources=True, **changes
    )


def source_scope(name="s"):
    return ContextScope(
        session=Session(id=name, app_name="a", user_id="u"),
        agent_name="agent",
        branch="",
        lossy_references={"ctx_local"},
        source_verification_allowed=True,
    )


def payload():
    return {
        "model": "openai/deepseek-v4-1-flash-260910",
        "api_base": "https://ark.cn-beijing.volces.com/api/v3",
        "extra_body": {"thinking": {"type": "disabled"}},
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "Check source."}],
        "response_format": None,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "veadk_read_context",
                    "parameters": {"type": "object"},
                },
            }
        ],
    }


@pytest.mark.parametrize(
    "where,update",
    [
        ("payload", {"tool_choice": "none"}),
        ("payload", {"tool_choice": "auto"}),
        ("payload", {"tool_choice": None}),
        ("payload", {"function_call": {"name": "business_tool"}}),
        ("extra", {"tool_choice": "none"}),
        ("payload", {"response_format": {"type": "json_object"}}),
        ("extra", {"response_format": {"type": "json_object"}}),
        ("payload", {"stream": True}),
        ("payload", {"model": "openai/unknown"}),
        ("payload", {"api_base": "https://unrelated.invalid"}),
        ("payload", {"api_base": None}),
        ("extra", {"thinking": {"type": "enabled"}}),
        ("payload", {"tools": []}),
    ],
)
def test_explicit_settings_and_unvalidated_routes_are_untouched(where, update):
    args = payload()
    (args if where == "payload" else args["extra_body"]).update(update)
    before = copy.deepcopy(args)
    scope = source_scope()
    token = current_scope.set(scope)
    try:
        assert source_verification_choice(args, policy()) is None
        assert args == before and not scope.source_verification_attempted
    finally:
        current_scope.reset(token)


@pytest.mark.parametrize(
    "case",
    [
        "default",
        "off",
        "summary",
        "no_scope",
        "no_loss",
        "restored",
        "read",
        "attempted",
        "native_choice",
    ],
)
def test_verification_is_limited_to_first_lossy_opt_in_request(case):
    config, scope = policy(), source_scope()
    if case == "default":
        config = ContextCompressionConfig(context_window=32000)
    elif case == "off":
        config = policy(mode="off")
    elif case == "no_scope":
        scope = None
    elif case == "no_loss":
        scope.lossy_references.clear()
    elif case == "restored":
        scope.restored_references.update(scope.lossy_references)
    elif case == "read":
        scope.retrieval_calls = 1
    elif case == "attempted":
        scope.source_verification_attempted = True
    elif case == "native_choice":
        scope.source_verification_allowed = False
    token = current_scope.set(scope)
    summary = is_summary.set(case == "summary")
    try:
        assert source_verification_choice(payload(), config) is None
    finally:
        is_summary.reset(summary)
        current_scope.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        types.GenerateContentConfig(
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="NONE")
            )
        ),
        types.GenerateContentConfig(response_mime_type="application/json"),
        types.GenerateContentConfig(response_schema={"type": "object"}),
    ],
)
async def test_native_caller_contract_is_respected_before_conversion(config):
    scope = source_scope()
    token = current_scope.set(scope)
    request = LlmRequest(
        model="openai/deepseek-v4-1-flash-260910", config=config, contents=[]
    )
    before = config.model_dump()
    try:
        await prepare_context(
            request, SimpleNamespace(model=request.model), policy(), {}
        )
        assert not scope.source_verification_allowed
        assert not scope.lossy_references
        assert request.config.model_dump() == before
    finally:
        current_scope.reset(token)


class Recorder(LiteLLMClient):
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def acompletion(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        await asyncio.sleep(0)
        if self.fail:
            raise RuntimeError("synthetic failure")
        return "synthetic response"


@pytest.mark.asyncio
async def test_shared_client_has_one_attempt_per_isolated_invocation():
    delegate = Recorder()
    client = BudgetedLiteLLMClient(delegate, policy())

    async def invoke(name):
        scope = source_scope(name)
        token = current_scope.set(scope)
        try:
            for _ in range(2):
                args = payload()
                args["messages"][0]["content"] = name
                before = copy.deepcopy(args)
                await client.acompletion(**args)
                assert args == before
        finally:
            current_scope.reset(token)

    await asyncio.gather(invoke("first"), invoke("second"))
    for name in ("first", "second"):
        calls = [c for c in delegate.calls if c["messages"][0]["content"] == name]
        assert len(calls) == 2
        assert calls[0]["tool_choice"] == {
            "type": "function",
            "function": {"name": "veadk_read_context"},
        }
        assert "tool_choice" not in calls[1]


@pytest.mark.asyncio
async def test_provider_failure_does_not_force_a_retry_loop():
    delegate = Recorder(fail=True)
    client = BudgetedLiteLLMClient(delegate, policy())
    scope = source_scope()
    token = current_scope.set(scope)
    try:
        for _ in range(2):
            with pytest.raises(RuntimeError, match="synthetic failure"):
                await client.acompletion(**payload())
        assert "tool_choice" in delegate.calls[0]
        assert "tool_choice" not in delegate.calls[1]
    finally:
        current_scope.reset(token)


@pytest.mark.asyncio
async def test_oversize_admission_precedes_attempt_consumption():
    delegate = Recorder()
    client = BudgetedLiteLLMClient(delegate, policy())
    scope = source_scope()
    token = current_scope.set(scope)
    try:
        args = payload()
        args["messages"][0]["content"] *= 10000
        with pytest.raises(ContextBudgetError, match="input_too_large"):
            await client.acompletion(**args)
        assert not delegate.calls and not scope.source_verification_attempted
    finally:
        current_scope.reset(token)
