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

"""Optional surrounding text must not displace distinct ranked evidence."""

import copy

import pytest
from google.genai import types

from veadk.context import retrieval, tool_results
from veadk.context.config import ContextCompressionConfig
from test_recoverable_context import mcp_source


def evidence_case(language):
    first = "Primary station: East." if language == "en" else "主站位置：东区。"
    second = (
        "Backup station: South. " * 9 if language == "en" else "备用站位置：南区。" * 8
    )
    prefix, suffix = "surrounding " * 20, " context" * 10
    line = prefix + first + suffix
    text = (
        line
        + "\n"
        + "archived unrelated material " * 90
        + "\n"
        + second
        + "\n"
        + "archive " * 1000
    )
    spans = [
        (len(prefix), len(prefix) + len(first)),
        (text.index(second), text.index(second) + len(second)),
    ]

    def rendered(ranges):
        return retrieval._preview(
            [{"offset": a, "end": b, "text": text[a:b]} for a, b in ranges]
        )

    # Both direct hits fit; the optional first-line expansion also fits alone,
    # but keeping that expansion excludes the second distinct direct hit.
    maximum = max(
        len(rendered(spans).encode()), len(rendered([(0, len(line))]).encode())
    )
    assert len(rendered([(0, len(line)), spans[1]]).encode()) > maximum
    return text, spans, maximum, first, second


@pytest.mark.parametrize("language", ["en", "zh"])
def test_evidence_before_expansion_at_actual_budget_selection(language):
    text, spans, maximum, first, second = evidence_case(language)
    matches = retrieval._matches(text, spans, maximum, preview=True)
    value = retrieval._preview(matches)
    assert first in value and second in value
    assert len(value.encode()) <= maximum
    assert all(m["text"] == text[m["offset"] : m["end"]] for m in matches)


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "zh"])
async def test_evidence_before_expansion_in_authorized_mcp_projection(language):
    text, spans, maximum, first, second = evidence_case(language)
    request, scope = mcp_source(text)
    request.contents.append(
        types.Content(
            role="user", parts=[types.Part(text="List both station locations.")]
        )
    )
    original = copy.deepcopy(scope.session.events)

    class Ranker:
        async def rank(self, identity, reference, source, query):
            assert source == text
            return spans

    scope.evidence_retriever = Ranker()
    scope.projection_bytes = maximum
    config = ContextCompressionConfig(tool_result_max_bytes=16000)
    await retrieval.prepare_previews(request, scope, config)
    refs = tool_results.compact_tool_results(request, scope, config)
    value = (
        request.contents[0].parts[0].function_response.response["content"][0]["text"]
    )
    assert first in value and second in value
    assert refs and tool_results.READ_CONTEXT_TOOL in request.tools_dict
    assert scope.session.events == original
    from veadk.context.references import resolve

    assert all(resolve(scope, descriptor) == text for descriptor in refs.values())
