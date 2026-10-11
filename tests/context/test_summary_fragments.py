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

"""Regressions: validate substance across all historical fragments."""

import json

import pytest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from veadk.context.budget import ContextBudgetError
from veadk.context.config import ContextCompressionConfig
from veadk.context.summary import HistorySummary, summarize_history


def summary(**values):
    return HistorySummary(
        goal="Continue calibration task",
        active_constraints=[],
        decisions=[],
        completed_work=[],
        pending_work=[],
        evidence=[],
        uncertainties=[],
    ).model_copy(update=values)


class FragmentModel:
    model = "offline-fragment-model"

    def __init__(self, outputs):
        self.outputs = outputs
        self.requests = []

    async def generate_content_async(self, request, stream=False):
        self.requests.append(request)
        value = self.outputs[len(self.requests) - 1]
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text=value.model_dump_json())]
            )
        )


def history():
    return [
        item
        for i in range(8)
        for item in [
            types.Content(role="user", parts=[types.Part(text=f"Record {i}")]),
            types.Content(
                role="model", parts=[types.Part(text="archive " + "x" * 1200)]
            ),
        ]
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sparse",
    [
        summary(
            uncertainties=["No task-relevant measurement is present in this fragment."]
        ),
        summary(
            evidence=["  "],
            uncertainties=["Only unrelated archival material is available."],
        ),
    ],
)
@pytest.mark.parametrize("batch", [True, False])
@pytest.mark.parametrize("sparse_first", [False, True])
async def test_sparse_fragment_does_not_discard_evidence_from_other_fragment(
    sparse, batch, sparse_first
):
    fact = "Calibration offset 0.004 mm"
    parts = (
        [sparse, summary(evidence=[fact])]
        if sparse_first
        else [summary(evidence=[fact]), sparse]
    )
    model = FragmentModel(parts + [summary(evidence=[fact])])
    config = ContextCompressionConfig(
        context_window=9000,
        summary_max_tokens=512,
        safety_margin=256,
        protected_context=(fact,),
    )
    value = json.loads(
        await summarize_history(
            history(),
            model,
            config,
            accept_candidate=(lambda _: True) if batch else None,
        )
    )
    assert len(model.requests) == (2 if batch else 3)
    if batch:
        assert value["chronological_summaries"][int(sparse_first)]["evidence"] == [fact]
        assert not any(
            item.strip()
            for item in value["chronological_summaries"][int(not sparse_first)][
                "evidence"
            ]
        )
    else:
        assert value["evidence"] == [fact]


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [True, False])
async def test_entirely_sparse_history_is_rejected_before_merge_can_invent_facts(batch):
    model = FragmentModel(
        [
            summary(uncertainties=["No task facts found"]),
            summary(uncertainties=["No additional relevant facts"]),
            summary(evidence=["invented"]),
        ]
    )
    config = ContextCompressionConfig(
        context_window=9000, summary_max_tokens=512, safety_margin=256
    )
    with pytest.raises(ContextBudgetError, match="summary_empty"):
        await summarize_history(
            history(),
            model,
            config,
            accept_candidate=(lambda _: True) if batch else None,
        )
    assert len(model.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        summary(),
        summary(uncertainties=["  "]),
        summary(goal=" ", uncertainties=["No facts"]),
    ],
)
async def test_goal_only_partial_is_still_rejected(invalid):
    model = FragmentModel([summary(evidence=["Offset 0.004 mm"]), invalid])
    with pytest.raises(ContextBudgetError, match="summary_empty"):
        await summarize_history(
            history(),
            model,
            ContextCompressionConfig(
                context_window=9000, summary_max_tokens=512, safety_margin=256
            ),
            accept_candidate=lambda _: True,
        )
    assert len(model.requests) == 2
