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

from __future__ import annotations

import asyncio
import importlib
import json

import pytest
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.long_running_tool import LongRunningFunctionTool
from google.genai import types

from veadk.runtime.model_callbacks import build_runtime_llm_request


def _content(text):
    return types.Content(role="user", parts=[types.Part(text=text)])


def _response():
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id="call-external",
                    name="external_job",
                    response={"value": "finished-value"},
                )
            )
        ],
    )


def _ctx(agent, events=()):
    return InvocationContext(
        session_service=InMemorySessionService(),
        invocation_id="inv-current",
        agent=agent,
        user_content=_content("start the job"),
        session=Session(
            id="session", app_name="app", user_id="user", events=list(events)
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("trailing_metadata", [False, True])
async def test_resume_uses_tool_result_once_without_replaying_original_request(
    trailing_metadata,
):
    agent = LlmAgent(name="agent", model="model")
    events = [
        Event(
            author="user",
            invocation_id="inv-current",
            content=_content("start the job"),
        ),
        Event(author="user", invocation_id="inv-current", content=_response()),
    ]
    if trailing_metadata:
        events.append(Event(author="agent", invocation_id="inv-current"))
    request = (
        await build_runtime_llm_request(
            agent, _ctx(agent, events), model="model", tools_dict={}
        )
    ).llm_request
    assert request.contents[-1] == _response()
    assert sum(c == _response() for c in request.contents) == 1
    assert sum(c == _content("start the job") for c in request.contents) == 1


@pytest.mark.asyncio
async def test_previous_invocation_result_does_not_replace_new_user_input():
    agent = LlmAgent(name="agent", model="model")
    result = Event(author="user", invocation_id="inv-old", content=_response())
    request = (
        await build_runtime_llm_request(
            agent, _ctx(agent, [result]), model="model", tools_dict={}
        )
    ).llm_request
    assert request.contents == [_response(), _content("start the job")]


@pytest.mark.parametrize("runtime", ["codex", "piagent"])
@pytest.mark.parametrize("include_history", [False, True])
def test_tool_result_survives_prompt_translation(runtime, include_history):
    module = importlib.import_module(f"veadk.runtime.{runtime}.translate")
    contents = (
        [_content("start the job"), _response()] if include_history else [_response()]
    )
    options = {"include_history": include_history} if runtime == "codex" else {}
    prompt = module.build_prompt_from_llm_request(
        LlmRequest(contents=contents), **options
    )
    assert "finished-value" in prompt
    assert "call-external" in prompt
    assert "not a new user request" in prompt
    if runtime == "codex":
        prompt = module.build_prompt(
            _ctx(LlmAgent(name="agent", model="model"), []).model_copy(
                update={"user_content": _response()}
            )
        )
        assert "finished-value" in prompt


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("callback_text", [False, True])
def test_codex_resume_includes_every_result_from_the_current_batch(
    reverse, callback_text
):
    from veadk.runtime.codex.translate import build_prompt_from_llm_request

    first, second = _response(), _response()
    first.parts[0].function_response.id = "call-first"
    first.parts[0].function_response.response = {"value": "callback-updated"}
    second.parts[0].function_response.id = "call-second"
    results = [first, second]
    if reverse:
        results.reverse()
    if callback_text:
        results[-1].parts.append(types.Part(text="callback continuation note"))
    request = LlmRequest(contents=[_content("start the job"), *results])
    before = request.model_dump()

    prompt = build_prompt_from_llm_request(request, include_history=False)

    records = json.loads(prompt.split("\n")[1])
    assert [
        record["id"] for record in records if record["type"] == "function_response"
    ] == [result.parts[0].function_response.id for result in results]
    assert ("callback continuation note" in prompt) == callback_text
    assert "callback-updated" in prompt
    assert "start the job" not in prompt
    assert request.model_dump() == before


@pytest.mark.parametrize("boundary", ["text", "model_text", "reasoning", "call"])
def test_codex_resume_does_not_merge_results_across_a_turn_boundary(boundary):
    from veadk.runtime.codex.translate import build_prompt_from_llm_request

    earlier, current = _response(), _response()
    earlier.parts[0].function_response.response = {"value": "previous-batch"}
    if boundary == "text":
        separator = _content("do it again")
    elif boundary == "model_text":
        separator = types.Content(role="model", parts=[types.Part(text="done")])
    elif boundary == "reasoning":
        separator = types.Content(
            role="model", parts=[types.Part(text="next step", thought=True)]
        )
    else:
        separator = types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id="call-external", name="external_job"
                    )
                )
            ],
        )
    prompt = build_prompt_from_llm_request(
        LlmRequest(contents=[earlier, separator, current]), include_history=False
    )
    records = json.loads(prompt.split("\n")[1])
    assert len(records) == 1
    assert "finished-value" in prompt
    assert "previous-batch" not in prompt


def test_codex_new_user_turn_does_not_repeat_prior_tool_results():
    from veadk.runtime.codex.translate import build_prompt_from_llm_request

    prompt = build_prompt_from_llm_request(
        LlmRequest(contents=[_response(), _response(), _content("next request")]),
        include_history=False,
    )
    assert prompt == "next request"


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime", ["codex", "piagent"])
@pytest.mark.parametrize("kind", ["long_running", "deferred", "normal"])
@pytest.mark.parametrize("initial_result", [None, {"job_id": "job-1"}])
async def test_pending_notification_follows_initial_execution_and_events(
    runtime, kind, initial_result
):
    order = []

    async def external_job() -> dict:
        """Start an external job."""
        await asyncio.sleep(0)
        order.append("executed")
        return initial_result

    tool = (
        LongRunningFunctionTool(external_job)
        if kind == "long_running"
        else FunctionTool(external_job)
    )
    if kind == "deferred":
        tool._defers_response = True

    async def emit(event):
        order.append("call" if event.get_function_calls() else "response")

    async def pending():
        order.append("pending")

    module = importlib.import_module(f"veadk.runtime.{runtime}.tools_bridge")
    agent = LlmAgent(name="agent", model="model", tools=[tool])
    bundle = await module.build_executable_tools(
        agent, _ctx(agent), event_sink=emit, on_tool_pending=pending
    )
    await bundle.executors["external_job"]({}, "call-external")
    assert order == ["call", "executed"] + (
        ["pending"] if kind != "normal" and initial_result is None else ["response"]
    )
