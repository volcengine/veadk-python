"""Failure, replay and lifetime contracts at the real ADK boundary."""

import asyncio
import copy
from types import SimpleNamespace

import httpx
import pytest
from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent
from google.adk.events import Event
from google.adk.tools import AgentTool
from google.genai import types
from pydantic import BaseModel
from volcenginesdkarkruntime._exceptions import ArkBadRequestError

from tests.routing.test_turn_contract import (
    Judge,
    RecordingArk,
    RecordingLlm,
    routed,
    setup,
    turn,
)
from veadk.routing.context import get_turn_context
from veadk.routing.execution import _RECORD, _REQUEST, _select, _portable_contents


class ExpiringArk(RecordingArk):
    async def generate_content_via_responses(self, responses_args, stream=False):
        if responses_args.get("previous_response_id"):
            self.calls.append(copy.deepcopy(responses_args))
            raise ArkBadRequestError(
                "expired",
                response=httpx.Response(
                    400, request=httpx.Request("POST", "https://example.test/responses")
                ),
                body={"code": "InvalidParameter.PreviousResponseNotFound"},
                request_id="test-request",
            )
        async for response in super().generate_content_via_responses(
            responses_args, stream
        ):
            yield response


@pytest.mark.asyncio
async def test_expired_responses_id_retries_same_model_with_full_history(monkeypatch):
    cheap = ExpiringArk(model="openai/cheap")
    strong = RecordingLlm(model="strong")
    judge = Judge()
    root = routed(monkeypatch, judge, strong, cheap)
    runner, session = await setup(root)
    try:
        await turn(runner, session, "ORCHID")
        await turn(runner, session, "MAPLE")
        assert len(cheap.calls) == 3
        assert cheap.calls[1]["previous_response_id"]
        assert not cheap.calls[2].get("previous_response_id")
        assert "ORCHID" in str(cheap.calls[2]["input"])
        assert "MAPLE" in str(cheap.calls[2]["input"])
        assert not strong.calls
        assert len(judge.calls) == 2
    finally:
        await runner.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["instruction", "history"])
async def test_changed_effective_request_rebuilds_responses_chain(monkeypatch, change):
    cheap = RecordingArk(model="openai/cheap")
    calls = 0

    async def callback(callback_context, llm_request):
        nonlocal calls
        calls += 1
        if calls == 2 and change == "history":
            llm_request.contents[0] = types.Content(
                role="user", parts=[types.Part(text="REVISED")]
            )
        llm_request.model = "callback-must-not-switch-model"

    root = routed(
        monkeypatch,
        Judge(),
        RecordingLlm(model="strong"),
        cheap,
        instruction="Remember codes",
        before_model_callback=callback,
    )
    runner, session = await setup(root)
    try:
        await turn(runner, session, "ORCHID")
        if change == "instruction":
            root.instruction = "Remember codes and reply briefly"
        await turn(runner, session, "MAPLE")
        assert not cheap.calls[1].get("previous_response_id")
        assert cheap.calls[1]["model"] == "cheap"
        assert calls == 2
        if change == "history":
            assert "REVISED" in str(cheap.calls[1]["input"])
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_resume_reuses_persisted_selection_and_rejects_configuration_change(
    monkeypatch,
):
    judge = Judge()
    cheap = RecordingLlm(model="cheap")
    root = routed(monkeypatch, judge, RecordingLlm(model="strong"), cheap)
    runner, session = await setup(root)
    try:
        await turn(runner, session, "ORCHID")
        saved = await runner.session_service.get_session(
            app_name=session.app_name, user_id=session.user_id, session_id=session.id
        )
        record = saved.state[_RECORD]
        ctx = SimpleNamespace(session=saved, invocation_id=record["invocation_id"])
        binding = await _select(root, ctx, root.model)
        assert binding.model is cheap
        assert len(judge.calls) == 1
        cheap.model = "changed"
        with pytest.raises(ValueError, match="configuration changed"):
            await _select(root, ctx, root.model)
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_cancellation_closes_classifier_and_clears_turn_scope(monkeypatch):
    started = asyncio.Event()
    closed = []

    class WaitingJudge(Judge):
        async def judge(self, **kwargs):
            started.set()
            await asyncio.Event().wait()

        async def aclose(self):
            closed.append(True)

    root = routed(
        monkeypatch,
        WaitingJudge(),
        RecordingLlm(model="strong"),
        RecordingLlm(model="cheap"),
    )
    runner, session = await setup(root)
    try:
        task = asyncio.create_task(turn(runner, session, "ORCHID"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert root.model.active_runs == 0
        assert closed == [True]
        assert get_turn_context() is None and _REQUEST.get() is None
        assert not root.model.store._inflight
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_late_capability_growth_fails_without_switching(monkeypatch):
    async def enlarge(callback_context, llm_request):
        llm_request.contents.append(
            types.Content(role="user", parts=[types.Part(text="X" * 33000)])
        )

    cheap, strong = RecordingLlm(model="cheap"), RecordingLlm(model="strong")
    judge = Judge()
    root = routed(monkeypatch, judge, strong, cheap, before_model_callback=enlarge)
    runner, session = await setup(root)
    try:
        with pytest.raises(ValueError, match="context_too_large"):
            await turn(runner, session, "small query")
        assert len(judge.calls) == 1
        assert not cheap.calls and not strong.calls
        assert get_turn_context() is None
    finally:
        await runner.close()


def test_foreign_reasoning_removed_without_losing_tool_pair_or_mutating_session():
    items = [
        types.Content(
            role="model",
            parts=[
                types.Part(
                    text="opaque reasoning",
                    thought=True,
                    thought_signature=b"signature",
                ),
                types.Part(
                    function_call=types.FunctionCall(
                        name="lookup", id="call-1", args={}
                    ),
                    thought=True,
                    thought_signature=b"tool-signature",
                ),
                types.Part(text="business answer"),
            ],
        ),
        types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name="lookup", id="call-1", response={"result": "ORCHID"}
                    )
                )
            ],
        ),
    ]
    event = Event(
        author="root",
        content=items[0],
        custom_metadata={"veadk_query_routing": {"target": "a"}},
    )
    ctx = SimpleNamespace(session=SimpleNamespace(events=[event]))
    same = _portable_contents(ctx, items, "a")
    foreign = _portable_contents(ctx, items, "b")
    assert same[0].parts[0].thought_signature == b"signature"
    assert "opaque reasoning" not in str(foreign)
    assert (
        foreign[0].parts[0].function_call.id
        == foreign[1].parts[0].function_response.id
        == "call-1"
    )
    assert all(p.thought_signature is None for c in foreign for p in c.parts)
    assert "business answer" in str(foreign) and "ORCHID" in str(foreign)
    assert items[0].parts[0].thought_signature == b"signature"


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow_type", [SequentialAgent, ParallelAgent])
async def test_agent_tool_workflow_inherits_root_model(monkeypatch, workflow_type):
    from tests.routing.test_turn_contract import DelegatingLlm

    judge = Judge()
    unused, cheap = RecordingLlm(model="unused"), DelegatingLlm(model="cheap")
    workflow = workflow_type(
        name="workflow",
        sub_agents=[
            LlmAgent(name="first", model=unused),
            LlmAgent(name="second", model=unused),
        ],
    )
    root = routed(monkeypatch, judge, unused, cheap, tools=[AgentTool(workflow)])
    runner, session = await setup(root)
    try:
        await turn(runner, session, "ORCHID")
        assert len(cheap.calls) == 4
        assert len(judge.calls) == 1 and not unused.calls
        assert len(set(cheap.scopes)) == 1
    finally:
        await runner.close()


def test_custom_native_subclass_rejected_instead_of_losing_its_behavior(monkeypatch):
    class Custom(LlmAgent):
        pass

    with pytest.raises(ValueError, match="custom ADK agents"):
        routed(
            monkeypatch,
            Judge(),
            RecordingLlm(model="strong"),
            RecordingLlm(model="cheap"),
            sub_agents=[Custom(name="custom", model="unused")],
        )


@pytest.mark.asyncio
async def test_output_schema_and_tool_description_are_classified(monkeypatch):
    class Output(BaseModel):
        code: str

    def lookup_project(code: str) -> str:
        """Look up archived project codes."""
        return code

    cheap, strong = RecordingLlm(model="cheap"), RecordingLlm(model="strong")
    judge = Judge()
    root = routed(
        monkeypatch,
        judge,
        strong,
        cheap,
        tools=[lookup_project],
        global_instruction="Archive policy applies",
    )
    runner, session = await setup(root)
    try:
        await turn(runner, session, "ORCHID")
        assert "archived project" in str(judge.calls)
        assert "Archive policy" in str(judge.calls)
        root.output_schema = Output
        await turn(runner, session, "format code")
        assert len(judge.calls) == 1
        assert len(strong.calls) == 1
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_callback_cannot_mutate_bound_model_configuration(monkeypatch):
    cheap = RecordingLlm(model="cheap")

    async def mutate(callback_context, llm_request):
        cheap.model = "other"

    root = routed(
        monkeypatch,
        Judge(),
        RecordingLlm(model="strong"),
        cheap,
        before_model_callback=mutate,
    )
    runner, session = await setup(root)
    try:
        with pytest.raises(ValueError, match="configuration changed during the turn"):
            await turn(runner, session, "hello")
        assert not cheap.calls
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_unresolved_dynamic_tools_choose_strong(monkeypatch):
    from google.adk.tools.base_toolset import BaseToolset

    class Toolset(BaseToolset):
        async def get_tools(self, readonly_context=None):
            return []

        async def close(self):
            pass

    judge = Judge()
    strong, cheap = RecordingLlm(model="strong"), RecordingLlm(model="cheap")
    root = routed(monkeypatch, judge, strong, cheap, tools=[Toolset()])
    runner, session = await setup(root)
    try:
        await turn(runner, session, "hello")
        assert len(strong.calls) == 1 and not cheap.calls
        assert not judge.calls
    finally:
        await runner.close()
