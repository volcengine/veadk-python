# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Protocol and semantic-projection contracts, using a captured provider payload."""

import asyncio
import copy
import json

import pytest
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions import Session
from google.genai import types
from litellm import ModelResponse

from veadk.context.history import eligible_prefix_end
from veadk.context.runtime import ContextScope, current_scope
from veadk.models.retrying_lite_llm import RetryingLiteLlm

SUMMARY = {
    "goal": "Reconcile invoice INV-418 without paying it",
    "active_constraints": ["Never submit payment", "Currency is CNY"],
    "decisions": ["Use the corrected total 187.25 CNY"],
    "completed_work": ["Compared both line items"],
    "pending_work": ["Explain the discrepancy"],
    "evidence": ["INV-418 total=187.25 CNY"],
    "uncertainties": [],
    "schema_version": 1,
}


class SummaryClient(LiteLLMClient):
    def __init__(self, summary=None):
        self.requests = []
        self.summary = summary if summary is not None else json.dumps(SUMMARY)

    async def acompletion(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        text = (
            self.summary
            if kwargs.get("response_format")
            else "INV-418: 187.25 CNY; no payment submitted."
        )
        return ModelResponse(
            model="openai/context-test",
            choices=[{"message": {"role": "assistant", "content": text}}],
        )


def content(role, text):
    return types.Content(role=role, parts=[types.Part(text=text)])


def history_request():
    contents = []
    for i in range(8):
        contents.extend(
            [
                content("user", f"Invoice INV-418, step {i}. Never submit payment."),
                content("model", "Historical explanation. " * 35 + "Total 187.25 CNY."),
            ]
        )
    contents.append(content("user", "Explain the discrepancy; do not pay."))
    return LlmRequest(
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction="Follow the user's authorization limits."
        ),
    )


def model_for(client, **overrides):
    return RetryingLiteLlm(
        model="openai/context-test",
        llm_client=client,
        context_compression={
            "context_window": 20000,
            "output_reserve": 2000,
            "safety_margin": 256,
            "trigger_ratio": 0.4,
            "summary_trigger_ratio": 0.4,
            "target_ratio": 0.3,
            **overrides,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("ratio", "expected_calls"), [(0.86, 1), (0.97, 2)])
async def test_default_history_summary_waits_until_near_hard_budget(
    ratio, expected_calls
):
    import math

    from veadk.context.budget import count_input, request_payload, resolve_budget
    from veadk.context.config import ContextCompressionConfig

    request = history_request()
    original = request.model_dump()
    count = count_input(request_payload(request), ContextCompressionConfig())
    config = ContextCompressionConfig(
        context_window=math.ceil(count / ratio) + 2000 + 256,
        output_reserve=2000,
        safety_margin=256,
    )
    budget = resolve_budget("openai/context-test", config)
    assert 0.8 < count / budget.available < 1
    client = SummaryClient()
    model = RetryingLiteLlm(
        model="openai/context-test", llm_client=client, context_compression=config
    )
    _ = [item async for item in model.generate_content_async(request)]
    assert len(client.requests) == expected_calls
    assert request.model_dump() == original
    if expected_calls == 1:
        assert [
            message["content"] for message in client.requests[0]["messages"][1:]
        ] == [item.parts[0].text for item in request.contents]
        assert not client.requests[0].get("response_format")


@pytest.mark.asyncio
async def test_summary_is_installed_in_actual_payload_with_recent_turns_intact():
    client = SummaryClient()
    request = history_request()
    original = request.model_dump()
    _ = [item async for item in model_for(client).generate_content_async(request)]
    assert len(client.requests) == 2
    summary_call, final = client.requests
    assert summary_call["tools"] is None
    assert summary_call["num_retries"] == 0
    messages = final["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == original["config"]["system_instruction"]
    assert "Summary of earlier conversation" in messages[1]["content"]
    assert "187.25 CNY" in messages[1]["content"]
    assert "Never submit payment" in messages[1]["content"]
    assert [m["content"] for m in messages[-3:]] == [
        c.parts[0].text for c in request.contents[-3:]
    ]
    assert len(json.dumps(messages)) < len(json.dumps(original["contents"]))
    assert request.model_dump() == original


@pytest.mark.asyncio
async def test_session_cache_requires_matching_source_and_avoids_resummarizing():
    client = SummaryClient()
    model = model_for(client)
    request = history_request()
    session = Session(id="session", app_name="app", user_id="user")
    scope = ContextScope(session=session, agent_name="agent", branch="")
    token = current_scope.set(scope)
    try:
        _ = [item async for item in model.generate_content_async(request)]
        assert len(scope.pending_state) == 1
        session.state.update(scope.pending_state)
        scope.pending_state.clear()
        _ = [item async for item in model.generate_content_async(request)]
        assert len(client.requests) == 3
        request.contents[0].parts[0].text = "Changed original task: invoice INV-999"
        _ = [item async for item in model.generate_content_async(request)]
        assert len(client.requests) == 5
    finally:
        current_scope.reset(token)


@pytest.mark.asyncio
async def test_invalid_summary_can_only_fall_back_when_original_fits():
    client = SummaryClient(summary="not valid JSON")
    request = history_request()
    _ = [item async for item in model_for(client).generate_content_async(request)]
    assert len(client.requests) == 2
    assert len(client.requests[-1]["messages"]) == len(request.contents) + 1


@pytest.mark.asyncio
async def test_ark_summary_uses_bounded_reasoning_without_changing_main_request():
    client = SummaryClient()
    llm = RetryingLiteLlm(
        model="openai/doubao-seed-2-1-pro-260628",
        llm_client=client,
        extra_body={"thinking": {"type": "enabled"}},
        context_compression={
            "context_window": 20000,
            "output_reserve": 2000,
            "trigger_ratio": 0.4,
            "summary_trigger_ratio": 0.4,
            "target_ratio": 0.3,
        },
    )
    _ = [item async for item in llm.generate_content_async(history_request())]
    assert len(client.requests) == 2
    assert client.requests[0]["extra_body"]["thinking"] == {"type": "disabled"}
    assert client.requests[1]["extra_body"]["thinking"] == {"type": "enabled"}


def test_parallel_tool_transaction_is_never_split():
    call_a = types.Part.from_function_call(name="a", args={})
    call_a.function_call.id = "a1"
    call_b = types.Part.from_function_call(name="b", args={})
    call_b.function_call.id = "b1"
    result_a = types.Part.from_function_response(name="a", response={"result": 1})
    result_a.function_response.id = "a1"
    result_b = types.Part.from_function_response(name="b", response={"result": 2})
    result_b.function_response.id = "b1"
    contents = [
        content("user", "work"),
        types.Content(role="model", parts=[call_a, call_b]),
        types.Content(role="user", parts=[result_a]),
        content("user", "interruption"),
    ]
    assert eligible_prefix_end(contents, 1) == 0
    contents.extend(
        [
            types.Content(role="user", parts=[result_b]),
            content("model", "done"),
            content("user", "next"),
        ]
    )
    assert eligible_prefix_end(contents, 1) == 6


@pytest.mark.asyncio
async def test_concurrent_scopes_keep_summary_state_separate():
    model = model_for(SummaryClient())
    barrier = asyncio.Event()
    scopes = []

    async def run(branch):
        scope = ContextScope(
            session=Session(id="shared", app_name="app", user_id="user"),
            agent_name="agent",
            branch=branch,
        )
        token = current_scope.set(scope)
        scopes.append(scope)
        try:
            if len(scopes) == 2:
                barrier.set()
            await barrier.wait()
            _ = [item async for item in model.generate_content_async(history_request())]
            assert current_scope.get() is scope
            assert scope.summary_calls == 1
            assert len(scope.pending_state) == 1
        finally:
            current_scope.reset(token)

    await asyncio.gather(run("left"), run("right"))
    assert set(scopes[0].pending_state).isdisjoint(scopes[1].pending_state)
    assert current_scope.get() is None


@pytest.mark.asyncio
async def test_rolling_summary_rebuilds_from_original_at_depth_limit():
    client = SummaryClient()
    model = model_for(client, max_summary_depth=2)
    original = history_request()
    scope = ContextScope(
        session=Session(id="s", app_name="a", user_id="u"),
        agent_name="agent",
        branch="",
    )
    token = current_scope.set(scope)
    try:
        depths = []
        for round_number in range(3):
            # Each user invocation gets a fresh call allowance; only Session
            # cache state survives into the next invocation in the real Runner.
            scope.summary_calls = 0
            snapshot = original.model_dump()
            _ = [item async for item in model.generate_content_async(original)]
            assert original.model_dump() == snapshot
            record = next(iter(scope.pending_state.values()))
            depths.append(record["depth"])
            scope.session.state.update(scope.pending_state)
            scope.pending_state.clear()
            original.contents += [
                content("model", "new evidence " * 800),
                content("user", f"Continue {round_number}, never pay"),
            ]
        assert depths == [1, 2, 1]
        summaries = [r for r in client.requests if r.get("response_format")]
        assert "Summary of earlier conversation" in json.dumps(summaries[1]["messages"])
        assert "Summary of earlier conversation" not in json.dumps(
            summaries[2]["messages"]
        )
        assert "Invoice INV-418, step 0" in json.dumps(summaries[2]["messages"])
    finally:
        current_scope.reset(token)
