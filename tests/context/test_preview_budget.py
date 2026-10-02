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

"""Unused request space must not hide already ranked, authorized evidence."""

import copy
from types import SimpleNamespace

import pytest
from google.genai import types

from veadk.context.budget import count_input, request_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.manager import prepare_context
from veadk.context.runtime import current_scope
from veadk.context.tool_results import READ_CONTEXT_TOOL
from test_recoverable_context import mcp_source


FIRST = "Delivery location: East warehouse."
SECOND = "Backup delivery location: South warehouse."


def block(label, unit, size):
    value = label + "\n"
    index = 0
    while len(value.encode()) < size:
        value += f"{label[:8]} record {index}: {unit} {index * 17}; "
        index += 1
    return value


def fixture(unit, *, first_size=4200):
    first = block(FIRST, unit, first_size)
    second = block(SECOND, unit, 2600)
    text = first + "\n\n" + second + "\n\n" + block("Archived context", unit, 26000)
    request, scope = mcp_source(text)
    request.model = "deepseek-v4-1-flash-260910"
    request.config.max_output_tokens = 1024
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
            parts=[
                types.Part(text="Give the delivery location and its backup location.")
            ],
        )
    )
    spans = [(0, len(first)), (len(first) + 2, len(first) + 2 + len(second))]

    class RankedEvidence:
        calls = 0

        async def rank(self, identity, reference, original, query):
            self.calls += 1
            assert original == text
            return spans

    scope.evidence_retriever = RankedEvidence()
    return request, scope, ContextCompressionConfig(input_limit=20000)


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["delivery", "运输记录"])
@pytest.mark.parametrize("first_size", [4200, 7000])
async def test_preview_budget_uses_target_space_for_already_ranked_evidence(
    unit, first_size
):
    request, scope, policy = fixture(unit, first_size=first_size)
    events = copy.deepcopy(scope.session.events)
    protected = copy.deepcopy([request.contents[0], request.contents[-1]])
    token = current_scope.set(scope)
    try:
        await prepare_context(request, SimpleNamespace(model=request.model), policy, {})
    finally:
        current_scope.reset(token)
    preview = (
        request.contents[1].parts[0].function_response.response["content"][0]["text"]
    )
    assert FIRST in preview
    assert SECOND in preview
    assert (
        count_input(request_payload(request), policy)
        <= policy.input_limit * policy.target_ratio
    )
    assert scope.session.events == events
    assert [request.contents[0], request.contents[-1]] == protected
    assert READ_CONTEXT_TOOL in request.tools_dict and "ctx_" in preview
    assert scope.evidence_retriever.calls == 1


@pytest.mark.asyncio
async def test_preview_budget_honors_smaller_target_and_preserves_source():
    request, scope, policy = fixture("delivery")
    policy = policy.model_copy(update={"target_ratio": 0.4})
    original = copy.deepcopy(scope.session.events)
    token = current_scope.set(scope)
    try:
        await prepare_context(request, SimpleNamespace(model=request.model), policy, {})
    finally:
        current_scope.reset(token)
    assert (
        count_input(request_payload(request), policy)
        <= policy.input_limit * policy.target_ratio
    )
    assert scope.session.events == original
    assert scope.evidence_retriever.calls == 1


@pytest.mark.asyncio
async def test_preview_budget_counts_escaped_json_and_keeps_selected_source(
    monkeypatch,
):
    from veadk.context import tool_results
    from veadk.context.retrieval import _matches

    request, scope, policy = fixture('"\\' * 16)
    original = copy.deepcopy(scope.session.events)
    selected = []
    extend = tool_results.extend_prepared_preview

    def tracked(scope, source, text, query, previous_maximum, maximum):
        from veadk.context.retrieval import _key

        ranked = scope.evidence_rankings[_key(scope, source, query)]
        previous = _matches(text, ranked, previous_maximum, preview=True)
        value = extend(scope, source, text, query, previous_maximum, maximum)
        if value is not None:
            for match in previous:
                assert match["text"] in value
            selected.append(value)
        return value

    monkeypatch.setattr(tool_results, "extend_prepared_preview", tracked)
    token = current_scope.set(scope)
    try:
        await prepare_context(request, SimpleNamespace(model=request.model), policy, {})
    finally:
        current_scope.reset(token)
    assert selected
    assert (
        count_input(request_payload(request), policy)
        <= policy.input_limit * policy.target_ratio
    )
    assert scope.session.events == original
    assert scope.evidence_retriever.calls == 1
