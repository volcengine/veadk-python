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

"""Shared source context must remain usable when the evidence budget is full."""

import re

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from veadk.context.history_evidence import _contextualize, _render
from veadk.context.budget import count_input, request_payload
from test_compression import content
from test_long_history_evidence import policy


def fixture():
    values, links = [], {}
    for date in ["Conversation recorded on 2028-03-11.", "记录日期 2028-05-19。"]:
        source = len(values)
        values.append(content("user", date))
        for i in range(36):
            index = len(values)
            values.append(
                content("user" if i % 2 else "model", f"陈述 {i}: yesterday / 昨天。")
            )
            links[index] = (source,)
    values.append(content("user", "This unrelated statement has no declared date."))
    regions = [(i, 0, 0, len(v.parts[0].text)) for i, v in enumerate(values)]
    return values, regions, links


def ranges(text):
    return re.findall(
        r"\[message (\d+), role \w+, part (\d+), characters (\d+):(\d+)", text
    )


def test_full_budget_contextualization_groups_without_dropping_any_evidence():
    values, regions, links = fixture()
    original = [v.model_dump() for v in values]
    baseline = _render(values, regions, "source:test", links)
    request = LlmRequest(
        contents=[content("user", baseline), content("user", "Compare dates.")],
        config=types.GenerateContentConfig(
            system_instruction="Use evidence carefully."
        ),
    )
    before = request.model_dump()
    ceiling = count_input(request_payload(request), policy())
    _contextualize(
        request, values, regions, regions, "source:test", links, policy(), ceiling
    )
    result = request.contents[0].parts[0].text
    assert "[Source group:" in result
    assert (
        result != baseline
        and count_input(request_payload(request), policy()) <= ceiling
    )
    assert ranges(result) == ranges(baseline)
    for value in values:
        assert value.parts[0].text in result
    assert request.model_dump(exclude={"contents"}) == {
        k: v for k, v in before.items() if k != "contents"
    }
    assert request.contents[-1].model_dump() == before["contents"][-1]
    assert [v.model_dump() for v in values] == original


def test_groups_do_not_leak_dates_across_sources_or_unbound_messages():
    values, regions, links = fixture()
    result = _render(values, regions, "source:test", links, grouped_context=True)
    groups = re.findall(r"\[Source group:.*?\[End source group\.\]", result, re.S)
    assert len(groups) == 2
    for group, source, forbidden in zip(groups, [0, 37], [37, 0]):
        assert values[source].parts[0].text in group
        assert values[forbidden].parts[0].text not in group
        assert len(ranges(group)) == 37
    assert result.index(values[-1].parts[0].text) > result.rindex("[End source group.]")
    assert ranges(result) == ranges(_render(values, regions, "source:test", links))


def test_nonadjacent_context_keeps_intervening_unbound_evidence_in_place():
    values = [
        content("user", "Document heading; record date is not event date."),
        content("model", "Unbound original statement."),
        content("user", "Today approved; earlier plan was rejected."),
    ]
    regions = [(i, 0, 0, len(v.parts[0].text)) for i, v in enumerate(values)]
    result = _render(values, regions, "source:test", {2: (0,)}, grouped_context=True)
    assert ranges(result) == ranges(_render(values, regions, "source:test", {2: (0,)}))
    group = result.split("[Source group:", 1)[1]
    assert values[0].parts[0].text in group and values[2].parts[0].text in group
    assert values[1].parts[0].text not in group


def test_empty_source_record_cannot_relabel_preceding_unbound_evidence():
    values = [
        content("user", ""),
        content("user", "Keep this original evidence."),
        content("model", "Linked statement with empty context."),
    ]
    regions = [
        (i, 0, 0, len(v.parts[0].text)) for i, v in enumerate(values) if v.parts[0].text
    ]
    result = _render(values, regions, "source:test", {2: (0,)}, grouped_context=True)
    assert ranges(result) == ranges(_render(values, regions, "source:test", {2: (0,)}))
    assert values[1].parts[0].text in result and values[2].parts[0].text in result
    assert result.index(values[1].parts[0].text) < result.index("[Source group:")
    assert values[1].parts[0].text not in result.split("[Source group:", 1)[1]


@pytest.mark.parametrize("targets", [(0, 1), (1, 0)])
def test_multiple_source_records_keep_roles_parts_and_original_order(targets):
    values = [
        content("user", "Source date."),
        content("model", "Document title."),
        content("user", "Fact."),
    ]
    values[0].parts.append(types.Part(text="Additional original source context."))
    regions = [
        (i, p, 0, len(part.text))
        for i, v in enumerate(values)
        for p, part in enumerate(v.parts)
    ]
    result = _render(values, regions, "source:test", {2: targets}, grouped_context=True)
    assert ranges(result) == ranges(
        _render(values, regions, "source:test", {2: targets})
    )
    for text in [
        "Source date.",
        "Document title.",
        "Additional original source context.",
    ]:
        assert result.count(text) == 1
    assert "role model" in result and "part 1" in result
