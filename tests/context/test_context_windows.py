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

"""A relevant fragment must not drop an affordable same-paragraph condition.

The old SDK returns the fragment but omits the referent/condition. These tests
exercise real preview/search selection and authorized SDK reader output, not
the contents of a fabricated model answer. All records are synthetic.
"""

import copy

import pytest

from veadk.context import retrieval


def ranked(text, needle):
    start = text.index(needle)
    return [(start, start + len(needle))]


def selected(text, spans, budget=1000, preview=True):
    return retrieval._matches(text, spans, budget, preview=preview)


@pytest.mark.parametrize("preview", [True, False])
@pytest.mark.parametrize(
    "prefix,hit,condition",
    [
        (
            "For the northern service plan, ",
            "the warranty remains active",
            "; except after a transfer.",
        ),
        ("北区服务方案：", "保修仍然有效", "；但转让之后失效。"),
        ("🙂 Owner A: ", "access is allowed", " only until the end of June. 🗓"),
    ],
)
def test_referent_and_condition_reach_actual_selection(preview, prefix, hit, condition):
    paragraph = prefix + hit + condition
    text = "Unrelated record.\n" + paragraph + "\nDifferent record."
    matches = selected(text, ranked(text, hit), preview=preview)
    assert len(matches) == 1
    assert matches[0]["text"] == paragraph
    assert text[matches[0]["offset"] : matches[0]["end"]] == paragraph
    assert "Unrelated record" not in matches[0]["text"]


@pytest.mark.parametrize("preview", [True, False])
def test_overlapping_ranked_hits_share_one_complete_original_paragraph(preview):
    paragraph = (
        "Owner Delta holds the license. The permission expires after relocation."
    )
    text = "Other.\n" + paragraph + "\nLast."
    spans = ranked(text, "holds the license") + ranked(text, "license. The permission")
    matches = selected(text, spans, preview=preview)
    assert len(matches) == 1 and matches[0]["text"] == paragraph
    assert selected(text, spans * 2, preview=preview) == matches


@pytest.mark.parametrize("preview", [True, False])
def test_unaffordable_context_falls_back_to_exact_ranked_span(preview):
    text = "Earlier.\n" + "bound " * 45 + "specific fact" + " limit" * 35 + "\nLater."
    spans = ranked(text, "specific fact")
    a, b = spans[0]
    expected = [{"offset": a, "end": b, "text": text[a:b]}]
    budget = (
        len(retrieval._preview(expected).encode())
        if preview
        else len(text[a:b].encode())
    )
    assert selected(text, spans, budget, preview) == expected
    assert selected(text, spans, 1, preview) == []


@pytest.mark.parametrize("prefix", ["x" * 513, "汉" * 180, "🙂" * 140])
def test_context_allowance_is_bounded_in_bytes(prefix):
    text = prefix + "bounded hit" + "tail" * 140
    spans = ranked(text, "bounded hit")
    matches = selected(text, spans, 20000)
    assert matches == [
        {"offset": spans[0][0], "end": spans[0][1], "text": "bounded hit"}
    ]


def test_no_boundary_in_large_source_does_not_include_unranked_surroundings():
    text = "x" * 800000 + "needle" + "y" * 800000
    matches = selected(text, ranked(text, "needle"), 20000)
    assert matches == [{"offset": 800000, "end": 800006, "text": "needle"}]


def test_two_disjoint_paragraphs_retain_original_order_and_utf8_budget():
    first = "Zebra account: quota 7; ends tomorrow."
    last = "Alpha account: 配额 9；下周结束。"
    text = first + "\n" + "unrelated " * 90 + "\n" + last
    spans = ranked(text, "配额 9") + ranked(text, "quota 7")
    matches = selected(text, spans, 500)
    assert [m["text"] for m in matches] == [first, last]
    assert len(retrieval._preview(matches).encode()) <= 500


@pytest.mark.parametrize("preview", [True, False])
def test_exact_line_boundaries_and_crlf_are_preserved(preview):
    text = "first\r\nwhole line\r\nlast"
    span = ranked(text, "whole line\r\n")
    matches = selected(text, span, preview=preview)
    assert matches == [
        {"offset": span[0][0], "end": span[0][1], "text": "whole line\r\n"}
    ]


@pytest.mark.asyncio
async def test_authorized_reader_retains_condition_and_original_session():
    from veadk.context.config import ContextCompressionConfig
    from veadk.context.tool_results import compact_tool_results
    from test_recoverable_context import mcp_source, read

    paragraph = "For the northern service plan, the warranty remains active; except after a transfer."
    text = "x" * 18000 + "\n" + paragraph + "\n" + "z" * 18000
    request, scope = mcp_source(text)
    before = copy.deepcopy(scope.session.events)

    class Ranker:
        async def rank(self, identity, reference, original, query):
            assert original == text
            return ranked(original, "the warranty remains active")

    scope.evidence_retriever = Ranker()
    refs = compact_tool_results(
        request, scope, ContextCompressionConfig(max_retrieval_calls=2)
    )
    ref = next(iter(refs))
    response = await read(request, scope, ref, operation="search", query="warranty")
    assert response["found"] and len(response["matches"]) == 1
    assert response["matches"][0]["text"] == paragraph
    assert scope.session.events == before
    exact = await read(request, scope, ref, operation="read", query="warranty")
    assert exact["text"] == text[exact["offset"] : exact["end"]]
