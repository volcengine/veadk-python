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

"""Protected source strings must be recognized before JSON escaping."""

import copy

import pytest
from google.adk.events import Event
from google.genai import types
from test_recoverable_context import mcp_source, read
from veadk.context.config import ContextCompressionConfig
from veadk.context.tool_results import (
    READ_CONTEXT_TOOL,
    compact_read_results,
    compact_tool_results,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "protected",
    [
        "Approval pending.\nNext line",
        'Amount "7319" pending',
        "Literal \\path pending",
        "Value \x01 pending",
    ],
)
async def test_escaped_protected_search_text_is_never_rewritten(protected):
    text = (protected + " ordinary archive evidence.\n") * 3000
    request, scope = mcp_source(text)
    policy = ContextCompressionConfig()
    refs = compact_tool_results(request, scope, policy)
    ref = next(iter(refs))
    for i in range(2):
        value = await read(request, scope, ref, operation="search", query="pending")
        assert any(protected in m["text"] for m in value["matches"])
        content = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name=READ_CONTEXT_TOOL, id=f"read-{i}", response=value
                    )
                )
            ],
        )
        scope.session.events.append(
            Event(id=f"event-{i}", author="agent", content=copy.deepcopy(content))
        )
        request.contents.append(content)
    originals = copy.deepcopy(scope.session.events)
    before = copy.deepcopy(request.contents[-2])
    compact_read_results(
        request.contents,
        scope,
        refs,
        policy.model_copy(update={"protected_context": (protected,)}),
    )
    assert request.contents[-2] == before
    assert scope.session.events == originals
