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

"""Source attribution must be usable within an admitted evidence block."""

import copy
import re

import pytest

from veadk.context import history_evidence
from veadk.context.budget import count_input, request_payload
from test_source_context import (
    DATE_A,
    DATE_B,
    FACT_A,
    FACT_B,
    binding,
    fixture,
    prepared,
)
from test_hybrid_history import Ranker, scope_for
from test_long_history_evidence import policy
from test_compression import content


def block(text, index):
    return next(
        value
        for value in re.split(r"(?=\[message \d+,)", text)
        if value.startswith(f"[message {index},")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fact,date,index", [(FACT_A, DATE_A, 25), (FACT_B, DATE_B, 79)]
)
async def test_actual_admitted_block_contains_its_verbatim_source_context(
    fact, date, index
):
    values, scope = fixture(fact, date)
    original = [e.model_dump(mode="json") for e in scope.session.events]
    request, client = await prepared(values, scope)
    evidence = block(request.contents[0].parts[0].text, index)
    # The old view only names a distant message number in this block. It
    # contains the date elsewhere, which does not satisfy this association.
    assert fact in evidence and date in evidence
    assert (DATE_B if date == DATE_A else DATE_A) not in evidence
    assert not client.requests
    assert [e.model_dump(mode="json") for e in scope.session.events] == original


@pytest.mark.asyncio
async def test_conflicting_claim_and_explicit_date_are_not_rewritten():
    first = "今天完成签收。Earlier I said the delivery was still pending."
    second = "The inspection occurred on 2027-06-03, before this record was written."
    values, _ = fixture()
    values[25] = content("user", first)
    values[79] = content("user", second)

    class Both(Ranker):
        async def rank(self, identity, reference, text, query):
            return [(text.index(v), text.index(v) + len(v)) for v in [first, second]]

    scope = scope_for(values, Both(first))
    for owner, context in [(25, 10), (79, 60)]:
        scope.session.events[owner].custom_metadata = {
            "veadk:source_context:v1": binding(scope, owner, [context])
        }
    request, _ = await prepared(values, scope)
    text = request.contents[0].parts[0].text
    assert first in block(text, 25) and DATE_A in block(text, 25)
    assert second in block(text, 79) and DATE_B in block(text, 79)
    assert "2027-06-03" in text


@pytest.mark.asyncio
async def test_budget_limited_attribution_cannot_displace_original_evidence(
    monkeypatch,
):
    values, scope = fixture()
    with monkeypatch.context() as patch:
        patch.setattr(history_evidence, "_contextualize", lambda *a, **kw: None)
        baseline, _ = await prepared(values, scope)
    baseline_text = baseline.contents[0].parts[0].text
    ceiling = count_input(request_payload(baseline), policy())
    candidate = baseline.model_copy(deep=True)
    history = values[:-1]
    regions = [
        tuple(map(int, match))
        for match in re.findall(
            r"\[message (\d+), role \w+, part (\d+), characters (\d+):(\d+)",
            baseline_text,
        )
    ]
    reference = re.search(r"Source: ([^\]]+)\]", baseline_text).group(1)
    # Use the fully admitted message itself, with insufficient room for even
    # one full context copy. Existing body, schemas and data must stay exact.
    history_evidence._contextualize(
        candidate,
        history,
        regions,
        [(25, 0, 0, len(FACT_A))],
        reference,
        {25: (10,), 79: (60,)},
        policy(),
        ceiling,
    )
    assert candidate.model_dump() == baseline.model_dump()
    assert candidate.contents[0].parts[0].text == baseline_text
    assert count_input(request_payload(candidate), policy()) == ceiling


@pytest.mark.asyncio
async def test_inline_context_does_not_create_new_instructions_or_tools():
    values, scope = fixture()
    before = copy.deepcopy(values[-1])
    request, _ = await prepared(values, scope)
    assert request.contents[-1] == before
    assert all(item.role != "system" for item in request.contents)
    assert set(request.tools_dict) <= {"veadk_read_context"}
    assert count_input(request_payload(request), policy()) <= 12000
