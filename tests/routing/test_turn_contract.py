"""Contracts across real ADK turns; only provider IO is substituted."""

import copy
import asyncio
from types import SimpleNamespace

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.agents import LlmAgent
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import AgentTool
from google.genai import types
from pydantic import Field

from veadk import Agent
from veadk.models.ark_llm import ArkLlm, request_reorganization_by_ark
from veadk.routing import factory
from veadk.routing.context import get_turn_context


class Judge:
    def __init__(self, values=(0.01,)):
        self.values = iter(values)
        self.calls = []

    async def judge(self, *, state, questions):
        self.calls.append(state)
        value = next(self.values, 0.01)
        return SimpleNamespace(
            answers={key: {"type": "noul", "noul": value} for key in questions},
            raw={"usage": {"input_tokens": 10}},
        )

    async def aclose(self):
        pass


class RecordingLlm(BaseLlm):
    calls: list = Field(default_factory=list)
    failure: bool = False

    async def generate_content_async(self, llm_request, stream=False):
        self.calls.append(copy.deepcopy(llm_request.contents))
        if self.failure:
            raise RuntimeError("provider failed")
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=self.model)])
        )


class RecordingArk(ArkLlm):
    calls: list = Field(default_factory=list)

    async def generate_content_via_responses(self, responses_args, stream=False):
        payload = request_reorganization_by_ark(
            copy.deepcopy(responses_args), self.enable_responses_cache
        )
        self.calls.append(payload)
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=self.model)]),
            interaction_id=f"{self.model}-{len(self.calls)}",
        )


async def turn(runner, session, text):
    return [
        event
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=text)]),
        )
    ]


async def setup(agent):
    service = InMemorySessionService()
    runner = Runner(app_name="routing_contract", agent=agent, session_service=service)
    session = await service.create_session(app_name="routing_contract", user_id="user")
    return runner, session


def routed(monkeypatch, judge, strong, cheap, **kwargs):
    monkeypatch.setattr(factory, "DecisionClient", lambda **_: judge)
    monkeypatch.setattr(factory, "_build_model", lambda *args, **kw: cheap)
    return Agent(
        name="root",
        model=strong,
        model_api_key="test-only",
        model_api_base="https://ark.cn-beijing.volces.com/api/v3",
        query_routing={
            "mode": "enforce",
            "simple_models": [{"name": cheap.model, "supports_tools": True}],
        },
        **kwargs,
    )


@pytest.mark.asyncio
async def test_next_turn_redecides_and_retains_same_session_history(monkeypatch):
    judge = Judge((0.9, 0.01))
    strong, cheap = RecordingLlm(model="strong"), RecordingLlm(model="cheap")
    agent = routed(monkeypatch, judge, strong, cheap)
    runner, session = await setup(agent)
    try:
        await turn(runner, session, "Remember project ORCHID")
        await turn(runner, session, "Continue with the project")
        assert len(judge.calls) == 2
        assert len(strong.calls) == len(cheap.calls) == 1
        assert "ORCHID" in str(cheap.calls[0])
        assert agent.canonical_model is strong
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_selected_model_failure_never_changes_model(monkeypatch):
    strong, cheap = (
        RecordingLlm(model="strong"),
        RecordingLlm(model="cheap", failure=True),
    )
    agent = routed(monkeypatch, Judge(), strong, cheap)
    runner, session = await setup(agent)
    try:
        with pytest.raises(RuntimeError, match="provider failed"):
            await turn(runner, session, "hello")
        assert not strong.calls
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_responses_reuse_and_model_switch_rebuild_history(monkeypatch):
    judge = Judge((0.01, 0.01, 0.9, 0.01))
    strong, cheap = (
        RecordingArk(model="openai/strong"),
        RecordingArk(model="openai/cheap"),
    )
    agent = routed(monkeypatch, judge, strong, cheap, enable_responses=True)
    runner, session = await setup(agent)
    try:
        for text in ("ORCHID", "continue", "new requirement MAPLE", "recall both"):
            await turn(runner, session, text)
        assert len(judge.calls) == 4
        assert cheap.calls[0].get("previous_response_id") is None
        assert cheap.calls[1]["previous_response_id"] == "openai/cheap-1"
        assert strong.calls[0].get("previous_response_id") is None
        assert cheap.calls[2].get("previous_response_id") is None
        assert "ORCHID" in str(cheap.calls[2]["input"])
        assert "MAPLE" in str(cheap.calls[2]["input"])
    finally:
        await runner.close()


def test_independent_model_endpoint_and_protocol(monkeypatch):
    monkeypatch.setattr(factory, "DecisionClient", lambda **_: Judge())
    agent = Agent(
        name="root",
        model_name="strong",
        model_api_key="root-only",
        model_api_base="https://ark.cn-beijing.volces.com/api/v3",
        query_routing={
            "simple_models": [
                {
                    "name": "cheap",
                    "api_base": "https://other.example/v1",
                    "api_key": "other-only",
                    "provider": "openai",
                    "api": "chat_completions",
                }
            ],
        },
    )
    runtime = agent.model.registry.runtimes[0]
    assert runtime.llm._additional_args["api_base"] == "https://other.example/v1"
    assert runtime.llm._additional_args["api_key"] == "other-only"


class DelegatingLlm(RecordingLlm):
    scopes: list = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream=False):
        self.calls.append(copy.deepcopy(llm_request.contents))
        self.scopes.append(get_turn_context().selection.invocation_id)
        # Each nested Agent sees only its own task/tool history.
        has_result = any(
            p.function_response for c in llm_request.contents for p in c.parts or []
        )
        tools = llm_request.tools_dict
        if tools and not has_result:
            name = next(iter(tools))
            part = types.Part(
                function_call=types.FunctionCall(
                    name=name, args={"request": "nested task"}
                )
            )
        else:
            part = types.Part(text="done")
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
async def test_two_nested_agent_tools_inherit_one_decision_and_keep_context_isolation(
    monkeypatch, native
):
    judge = Judge()
    cheap = DelegatingLlm(model="cheap")
    unused = RecordingLlm(model="unused")
    cls = LlmAgent if native else Agent
    kwargs = {} if native else {"model_api_key": "test-only", "query_routing": False}
    leaf = cls(name="leaf", model=unused, **kwargs)
    child = cls(name="child", model=unused, tools=[AgentTool(leaf)], **kwargs)
    agent = routed(monkeypatch, judge, unused, cheap, tools=[AgentTool(child)])
    runner, session = await setup(agent)
    try:
        await turn(runner, session, "ROOT_PRIVATE_CONTEXT")
        assert len(judge.calls) == 1
        assert len(cheap.calls) == 5
        assert len(set(cheap.scopes)) == 1
        assert not unused.calls
        assert "ROOT_PRIVATE_CONTEXT" not in str(cheap.calls[1])
        assert "ROOT_PRIVATE_CONTEXT" not in str(cheap.calls[2])
        assert get_turn_context() is None
        assert leaf.canonical_model is unused
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_concurrent_sessions_keep_distinct_fixed_models(monkeypatch):
    judge = Judge((0.01, 0.9))
    strong, cheap = RecordingLlm(model="strong"), RecordingLlm(model="cheap")
    agent = routed(monkeypatch, judge, strong, cheap)
    runner, first = await setup(agent)
    second = await runner.session_service.create_session(
        app_name="routing_contract", user_id="user"
    )
    try:
        await asyncio.gather(
            turn(runner, first, "FIRST"), turn(runner, second, "SECOND")
        )
        assert len(judge.calls) == 2
        assert len(strong.calls) == len(cheap.calls) == 1
        assert "FIRST" in str(cheap.calls[0])
        assert "SECOND" in str(strong.calls[0])
        assert get_turn_context() is None
    finally:
        await runner.close()


class TransferringLlm(RecordingLlm):
    async def generate_content_async(self, llm_request, stream=False):
        self.calls.append(copy.deepcopy(llm_request.contents))
        if len(self.calls) == 1:
            part = types.Part(
                function_call=types.FunctionCall(
                    name="transfer_to_agent", args={"agent_name": "child"}
                )
            )
        else:
            part = types.Part(text=self.model)
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.mark.asyncio
async def test_native_transfer_and_next_turn_share_root_routing(monkeypatch):
    judge = Judge((0.01, 0.9))
    unused = RecordingLlm(model="unused")
    cheap, strong = TransferringLlm(model="cheap"), RecordingLlm(model="strong")
    child = LlmAgent(name="child", model=unused)
    root = routed(monkeypatch, judge, strong, cheap, sub_agents=[child])
    runner, session = await setup(root)
    try:
        await turn(runner, session, "Transfer task ORCHID")
        await turn(runner, session, "Continue ORCHID")
        assert len(judge.calls) == 2
        assert len(cheap.calls) == 2
        assert len(strong.calls) == 1
        assert not unused.calls
        assert child.canonical_model is unused
        assert "ORCHID" in str(strong.calls)
    finally:
        await runner.close()
