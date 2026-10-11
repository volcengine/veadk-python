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

"""Admission regressions at the final transport boundary (no network)."""

import pytest
from google.adk.models.lite_llm import LiteLLMClient

from veadk.context.budget import ContextBudgetError, check_payload
from veadk.context.client import BudgetedLiteLLMClient
from veadk.context.config import ContextCompressionConfig


class FailingClient(LiteLLMClient):
    def __init__(self):
        self.requests = []

    async def acompletion(self, **kwargs):
        self.requests.append(kwargs)
        raise RuntimeError("synthetic provider failure")


@pytest.mark.asyncio
async def test_smaller_fallback_cannot_inherit_primary_window(monkeypatch):
    monkeypatch.setattr(
        "veadk.context.budget.model_limits",
        lambda model: (
            {
                "max_input_tokens": 2000,
                "max_output_tokens": 500,
            }
            if model == "small"
            else {}
        ),
    )
    delegate = FailingClient()
    client = BudgetedLiteLLMClient(
        delegate,
        ContextCompressionConfig(
            context_window=20000,
            output_reserve=500,
            safety_margin=100,
        ),
    )
    with pytest.raises(ContextBudgetError, match="input_too_large"):
        await client.acompletion(
            model="primary",
            messages=[
                {
                    "role": "user",
                    "content": "x" * 5000,
                }
            ],
            fallbacks=["small"],
        )
    assert [request["model"] for request in delegate.requests] == ["primary"]


@pytest.mark.asyncio
async def test_unknown_fallback_cannot_claim_primary_capacity():
    delegate = FailingClient()
    client = BudgetedLiteLLMClient(
        delegate,
        ContextCompressionConfig(
            context_window=20000,
            output_reserve=500,
        ),
    )
    with pytest.raises(ContextBudgetError, match="fallback_capacity_required"):
        await client.acompletion(
            model="unknown-primary",
            messages=[
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
            fallbacks=["unknown-fallback"],
        )
    assert len(delegate.requests) == 1


@pytest.mark.parametrize(
    "override",
    [
        {"max_tokens": 100000},
        {"previous_response_id": "hidden-history"},
        {"messages": [{"role": "user", "content": "replacement"}]},
        {"model": "another-model"},
        {"context_management": {"type": "compact"}},
    ],
)
def test_extra_body_cannot_override_accounted_inputs_or_capacity(override):
    with pytest.raises(ContextBudgetError, match="reserved_payload_override"):
        check_payload(
            {
                "model": "synthetic-model",
                "messages": [],
                "extra_body": override,
            },
            ContextCompressionConfig(context_window=4000, output_reserve=500),
        )


def test_conflicting_output_limits_are_rejected_instead_of_undercounted():
    with pytest.raises(ContextBudgetError, match="conflicting_output_limits"):
        check_payload(
            {
                "model": "synthetic-model",
                "messages": [],
                "max_tokens": 3000,
                "max_completion_tokens": 200,
            },
            ContextCompressionConfig(context_window=4000, output_reserve=500),
        )


def test_output_limit_cannot_exceed_the_selected_models_answer_capacity(monkeypatch):
    monkeypatch.setattr(
        "veadk.context.budget.model_limits",
        lambda _: {
            "context_window": 10000,
            "max_input_tokens": 8000,
            "max_output_tokens": 500,
        },
    )
    with pytest.raises(ContextBudgetError, match="output_limit_exceeds_model_capacity"):
        check_payload(
            {"model": "smaller", "messages": [], "max_tokens": 1000},
            ContextCompressionConfig(),
        )


def test_remote_file_content_requires_explicit_media_budget():
    with pytest.raises(ContextBudgetError, match="media_budget_required"):
        check_payload(
            {
                "model": "synthetic-model",
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_file", "file_id": "synthetic-file"},
                        ],
                    }
                ],
            },
            ContextCompressionConfig(context_window=4000, output_reserve=500),
        )
