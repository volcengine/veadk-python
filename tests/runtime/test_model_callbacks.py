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

from types import SimpleNamespace

import pytest
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.adk.tools.base_tool import BaseTool
from google.genai import types

from veadk.runtime.codex.translate import build_prompt_from_llm_request
from veadk.runtime.model_callbacks import (
    build_runtime_llm_request,
    final_events_to_llm_response,
    llm_response_to_event,
    run_after_model_callbacks,
    run_before_model_callbacks,
    run_on_model_error_callbacks,
)
from veadk.runtime.output_state import maybe_save_output_to_state
from veadk.runtime.piagent.translate import (
    build_prompt_from_llm_request as build_pi_prompt_from_llm_request,
)


def _content(text: str, *, role: str = "user") -> types.Content:
    return types.Content(role=role, parts=[types.Part(text=text)])


def _event(author: str, text: str) -> Event:
    return Event(
        invocation_id="inv-history",
        author=author,
        content=_content(text, role="user" if author == "user" else "model"),
    )


def _ctx(
    agent: LlmAgent, *events: Event, user_text: str = "hello"
) -> InvocationContext:
    return InvocationContext(
        session_service=InMemorySessionService(),
        invocation_id="inv-1",
        agent=agent,
        user_content=_content(user_text),
        session=Session(
            id="session-1",
            appName="app",
            userId="user",
            state={},
            events=list(events),
        ),
    )


class _BeforePlugin(BasePlugin):
    def __init__(self, calls: list[str], response: LlmResponse | None = None) -> None:
        super().__init__(name="before")
        self.calls = calls
        self.response = response

    async def before_model_callback(self, *, callback_context, llm_request):
        self.calls.append("plugin-before")
        return self.response


class _ErrorPlugin(BasePlugin):
    def __init__(self, response: LlmResponse) -> None:
        super().__init__(name="error")
        self.response = response

    async def on_model_error_callback(self, *, callback_context, llm_request, error):
        return self.response


class _LongRunningTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="slow",
            description="Slow tool.",
            is_long_running=True,
        )


@pytest.mark.asyncio
async def test_before_model_callback_mutates_request_consumed_by_prompts() -> None:
    def before_model_callback(callback_context, llm_request):
        llm_request.contents[-1].parts[0].text = "mutated request"

    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        instruction="Answer briefly.",
        before_model_callback=before_model_callback,
    )
    ctx = _ctx(agent, _event("user", "history"), user_text="original request")
    runtime_call = await build_runtime_llm_request(
        agent,
        ctx,
        model="model-a",
        tools_dict={},
    )

    response = await run_before_model_callbacks(
        agent,
        ctx,
        runtime_call.llm_request,
        runtime_call.model_response_event,
    )

    assert response is None
    codex_prompt = build_prompt_from_llm_request(runtime_call.llm_request)
    pi_prompt = build_pi_prompt_from_llm_request(runtime_call.llm_request)
    assert "mutated request" in codex_prompt
    assert "mutated request" in pi_prompt
    assert "original request" not in codex_prompt
    assert "original request" not in pi_prompt


@pytest.mark.asyncio
async def test_before_model_short_circuit_preserves_callback_actions() -> None:
    def before_model_callback(callback_context, llm_request):
        callback_context.state["guard"] = "hit"
        return LlmResponse(content=_content("blocked", role="model"))

    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        before_model_callback=before_model_callback,
    )
    ctx = _ctx(agent)
    runtime_call = await build_runtime_llm_request(
        agent,
        ctx,
        model="model-a",
        tools_dict={},
    )

    response = await run_before_model_callbacks(
        agent,
        ctx,
        runtime_call.llm_request,
        runtime_call.model_response_event,
    )
    event = llm_response_to_event(
        runtime_call.llm_request,
        response,
        runtime_call.model_response_event,
    )

    assert event.author == "agent"
    assert event.is_final_response()
    assert event.content.parts[0].text == "blocked"
    assert event.actions.state_delta == {"guard": "hit"}


@pytest.mark.asyncio
async def test_plugin_before_model_short_circuits_agent_callbacks() -> None:
    calls: list[str] = []

    def before_model_callback(callback_context, llm_request):
        calls.append("agent-before")

    plugin_response = LlmResponse(content=_content("plugin", role="model"))
    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        before_model_callback=before_model_callback,
    )
    ctx = _ctx(agent)
    ctx.plugin_manager.register_plugin(_BeforePlugin(calls, plugin_response))
    runtime_call = await build_runtime_llm_request(
        agent,
        ctx,
        model="model-a",
        tools_dict={},
    )

    response = await run_before_model_callbacks(
        agent,
        ctx,
        runtime_call.llm_request,
        runtime_call.model_response_event,
    )

    assert response is plugin_response
    assert calls == ["plugin-before"]


@pytest.mark.asyncio
async def test_after_model_replacement_is_final_and_saved_to_output_key() -> None:
    def after_model_callback(callback_context, llm_response):
        return LlmResponse(content=_content("after text", role="model"))

    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        after_model_callback=after_model_callback,
    )
    ctx = _ctx(agent)
    runtime_call = await build_runtime_llm_request(
        agent,
        ctx,
        model="model-a",
        tools_dict={},
    )
    response = final_events_to_llm_response(
        [
            Event(
                invocation_id="inv-1",
                author="agent",
                content=_content("runtime text", role="model"),
            )
        ]
    )

    response = await run_after_model_callbacks(
        agent,
        ctx,
        response,
        runtime_call.model_response_event,
    )
    event = llm_response_to_event(
        runtime_call.llm_request,
        response,
        runtime_call.model_response_event,
    )
    maybe_save_output_to_state(
        SimpleNamespace(name="agent", output_key="answer", output_schema=None),
        event,
    )

    assert event.is_final_response()
    assert event.content.parts[0].text == "after text"
    assert event.actions.state_delta["answer"] == "after text"


@pytest.mark.asyncio
async def test_on_model_error_plugin_returns_fallback_response() -> None:
    agent = LlmAgent(name="agent", model="gemini-2.5-flash")
    ctx = _ctx(agent)
    fallback = LlmResponse(content=_content("fallback", role="model"))
    ctx.plugin_manager.register_plugin(_ErrorPlugin(fallback))
    runtime_call = await build_runtime_llm_request(
        agent,
        ctx,
        model="model-a",
        tools_dict={},
    )

    response = await run_on_model_error_callbacks(
        agent,
        ctx,
        RuntimeError("backend down"),
        runtime_call.llm_request,
        runtime_call.model_response_event,
    )

    assert response is fallback


def test_llm_response_to_event_populates_function_call_ids_and_long_running() -> None:
    tool = _LongRunningTool()
    llm_request = SimpleNamespace(tools_dict={"slow": tool})
    llm_response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name="slow", args={}))],
        )
    )
    model_response_event = Event(invocation_id="inv-1", author="agent")

    event = llm_response_to_event(llm_request, llm_response, model_response_event)

    call = event.get_function_calls()[0]
    assert call.id.startswith("adk-")
    assert event.long_running_tool_ids == {call.id}
