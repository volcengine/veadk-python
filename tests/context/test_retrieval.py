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

"""Original-text reference authorization, integrity and per-invocation limits."""

import copy
from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions import Session
from google.adk.tools.function_tool import FunctionTool
from google.genai import types

from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import ContextScope, current_scope
from veadk.context.tool_results import READ_CONTEXT_TOOL, compact_tool_results


def source():
    def fetch() -> str:
        """Fetch the report."""
        return ""

    result = types.Part.from_function_response(
        name="fetch",
        response={
            "result": "x" * 10000 + "INV-418 = 187.25 CNY" + "y" * 10000,
        },
    )
    result.function_response.id = "fetch-call"
    event = Event(
        id="source-event",
        author="agent",
        content=types.Content(role="user", parts=[result]),
    )
    session = Session(id="session", app_name="app", user_id="user", events=[event])
    scope = ContextScope(session=session, agent_name="agent", branch="")
    request = LlmRequest(
        contents=[copy.deepcopy(event.content)],
        tools_dict={"fetch": FunctionTool(fetch)},
    )
    config = ContextCompressionConfig(max_retrieval_calls=2)
    refs = compact_tool_results(request, scope, config)
    return request, scope, config, next(iter(refs))


async def read(request, scope, handle, **kwargs):
    token = current_scope.set(scope)
    try:
        return await request.tools_dict[READ_CONTEXT_TOOL].func(
            handle,
            SimpleNamespace(session=scope.session, agent_name=scope.agent_name),
            **kwargs,
        )
    finally:
        current_scope.reset(token)


@pytest.mark.asyncio
async def test_empty_content_events_do_not_break_original_lookup():
    request, scope, config, _ = source()
    original = copy.deepcopy(scope.session.events[0].content)
    scope.session.events.append(
        Event(author="agent", content=types.Content(role="model"))
    )
    request.contents = [original]
    refs = compact_tool_results(request, scope, config)
    handle = next(iter(refs))
    result = await read(request, scope, handle, query="INV-418")
    assert "INV-418 = 187.25 CNY" in result["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dimension", ["app_name", "user_id", "id", "agent_name", "branch"]
)
async def test_reference_cannot_cross_scope(dimension):
    request, scope, _, handle = source()
    foreign = ContextScope(
        session=scope.session.model_copy(deep=True),
        agent_name=scope.agent_name,
        branch=scope.branch,
    )
    setattr(
        foreign if dimension in {"agent_name", "branch"} else foreign.session,
        dimension,
        "foreign",
    )
    result = await read(request, foreign, handle, query="INV-418")
    assert result == {"error": "context_reference_not_available"}


@pytest.mark.asyncio
async def test_reader_finds_middle_fact_without_knowing_offset_and_preserves_original():
    request, scope, config, handle = source()
    original = scope.session.model_dump()
    result = await read(request, scope, handle, query="INV-418")
    assert "INV-418 = 187.25 CNY" in result["text"]
    assert len(result["text"].encode()) <= config.retrieval_max_bytes
    assert result["offset"] > 0
    assert scope.session.model_dump() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["deleted", "modified"])
async def test_source_removed_or_changed_is_unavailable(change):
    request, scope, _, handle = source()
    if change == "deleted":
        scope.session.events.clear()
    else:
        scope.session.events[0].content.parts[0].function_response.response[
            "result"
        ] = "replaced"
    assert await read(request, scope, handle) == {"error": "context_reference_expired"}


@pytest.mark.asyncio
async def test_retrieval_limit_survives_new_reader_instances():
    request, scope, config, handle = source()
    for _ in range(2):
        fresh = LlmRequest(
            contents=[copy.deepcopy(scope.session.events[0].content)],
            tools_dict={
                "fetch": request.tools_dict["fetch"],
            },
        )
        compact_tool_results(fresh, scope, config)
        assert "text" in await read(fresh, scope, handle)
    exhausted = await read(request, scope, handle)
    assert exhausted["error"] == "context_retrieval_budget_exhausted"
    assert exhausted["remaining_calls"] == 0 and exhausted["complete"] is False
    assert "text" not in exhausted and scope.retrieval_calls == 2
