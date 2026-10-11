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

"""Offline contracts for the synthetic live evaluator, not model quality claims."""

import json
import time
from types import SimpleNamespace

import pytest

from evaluations.context_compression.corpus import (
    build_material,
    cases,
    dataset_hash,
    grade,
    select_cases,
)
from evaluations.context_compression.run import isolated_environment, validate_target
from evaluations.context_compression.worker import aggregate, run_case


def test_summary_diagnostics_report_only_allowlisted_structure_not_response_data():
    from evaluations.context_compression.worker import summary_diagnostics

    value = {
        "goal": None,
        "active_constraints": [],
        "decisions": [],
        "completed_work": [],
        "pending_work": [],
        "evidence": [],
        "uncertainties": [],
        "synthetic-private-field": "synthetic-private-value",
    }
    diagnostics = summary_diagnostics(json.dumps(value), "stop")
    assert diagnostics["schema_valid"] is False
    assert diagnostics["error_types"] == ["extra_forbidden", "string_type"]
    assert diagnostics["fields"] == ["goal", "unknown_field"]
    assert diagnostics["finish_reason"] == "stop"
    assert "synthetic-private" not in json.dumps(diagnostics)


def test_summary_diagnostics_identify_json_wrapper_without_relaxing_validation():
    from evaluations.context_compression.worker import summary_diagnostics

    diagnostics = summary_diagnostics('```json\n{"private": "value"}\n```', "length")
    assert diagnostics["schema_valid"] is False
    assert diagnostics["error_types"] == ["json_invalid"]
    assert diagnostics["fenced"] is True
    assert diagnostics["finish_reason"] == "length"
    assert "private" not in json.dumps(diagnostics)
    assert (
        summary_diagnostics(None, "arbitrary-response-data")["finish_reason"] == "other"
    )


def test_exact_fact_diagnostics_decode_json_values_without_retaining_them():
    from evaluations.context_compression.worker import exact_fact_presence

    fact = 'keep "quoted"\nline'
    payload = [{"content": json.dumps({"evidence": [fact]})}]
    result = exact_fact_presence(payload, (fact, "missing", "evidence"))
    assert result == [True, False, False]
    assert exact_fact_presence(None, (fact,)) == [False]
    assert exact_fact_presence({"evidence": ["keep quoted line"]}, (fact,)) == [False]
    assert fact not in json.dumps(result)


def test_exact_fact_diagnostics_bound_nested_json_and_never_mutate_input():
    from evaluations.context_compression.worker import exact_fact_presence

    value = {"field": "synthetic-private-value"}
    for _ in range(30):
        value = {"nested": value}
    before = json.dumps(value)
    result = exact_fact_presence(value, ("synthetic-private-value",))
    assert result == [False]
    assert json.dumps(value) == before
    assert "synthetic-private" not in json.dumps(result)


@pytest.mark.asyncio
async def test_fact_observer_does_not_send_expected_answers_to_transport(monkeypatch):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    from evaluations.context_compression.worker import MeasuredClient
    from veadk.context.config import ContextCompressionConfig

    expected = "synthetic-oracle-only"
    sent = []

    async def transport(self, **kwargs):
        sent.append(kwargs)
        return ModelResponse(
            model=kwargs["model"],
            choices=[{"message": {"role": "assistant", "content": expected}}],
        )

    monkeypatch.setattr(LiteLLMClient, "acompletion", transport)
    client = MeasuredClient(
        ContextCompressionConfig(context_window=40000, output_reserve=2000),
        {"calls": 1, "deadline": time.monotonic() + 30},
    )
    client.expected_facts = (expected,)
    messages = [{"role": "user", "content": "synthetic request"}]
    response = await client.acompletion("synthetic-model", messages)
    assert sent == [{"model": "synthetic-model", "messages": messages, "tools": None}]
    assert client.calls[0]["exact_fact_presence"] == {
        "input": [False],
        "output": [True],
    }
    assert response.choices[0].message.content == expected
    assert expected not in json.dumps(client.calls)


def test_corpus_is_deterministic_diverse_and_keeps_expected_answers_separate():
    dataset = cases()
    assert len(dataset) == 96
    assert len({case.id for case in dataset}) == 96
    assert len({case.category for case in dataset}) == 8
    assert dataset_hash(dataset) == dataset_hash(cases())
    assert dataset_hash(dataset) != dataset_hash(cases(variants=5))
    for case in dataset:
        counts = {"load_record": 1} if case.tool_document is not None else {}
        if case.category == "tool_chain":
            counts.update(lookup_rate=1, calculate_total=1)
        assert grade(case, json.dumps(case.expected), counts)["task_success"]
        assert not grade(case, "{}", counts)["task_success"]


def test_case_filter_preserves_order_and_rejects_unknown_cases():
    dataset = cases(1)
    identifiers = [dataset[3].id, dataset[0].id]
    selected = select_cases(1, ("short", "pressure", "overflow"), identifiers)
    assert selected == [dataset[0], dataset[3]]
    with pytest.raises(ValueError, match="unknown_evaluation_case"):
        select_cases(1, ("short",), ["missing-case"])


@pytest.mark.parametrize(
    "category", ["exact_amount", "code_contract", "negation", "correction"]
)
def test_grader_rejects_one_wrong_fact_even_when_other_facts_are_correct(category):
    case = next(case for case in cases() if case.category == category)
    changed = dict(case.expected)
    changed[next(iter(changed))] = "incorrect synthetic value"
    assert not grade(case, json.dumps(changed), {})["task_success"]


def test_unauthorized_action_and_replayed_tool_cannot_pass_on_final_answer_alone():
    case = next(case for case in cases() if case.category == "tool_injection")
    answer = json.dumps(case.expected)
    assert not grade(case, answer, {"load_record": 1, "submit_payment": 1})[
        "task_success"
    ]
    assert not grade(case, answer, {"load_record": 2})["task_success"]


def test_tool_facts_are_in_middle_and_conversation_facts_are_outside_recent_turns():
    for case in cases(variants=1, tiers=("pressure",)):
        turns, document = build_material(case, 40000)
        if case.tool_document is not None:
            assert case.tool_document in document
            assert case.tool_document not in document[:8000]
            assert case.tool_document not in document[-8000:]
        else:
            assert case.facts[0] in turns[0]
            assert all(case.facts[0] not in turn for turn in turns[-2:])
            if len(case.facts) > 1:
                assert case.facts[1] in turns[4]


@pytest.mark.parametrize(
    "base",
    [
        "https://api.openai.com/api/v3",
        "http://ark.cn-beijing.volces.com/api/v3",
        "https://ark.cn-beijing.volces.com.evil.invalid/api/v3",
        "https://ark.cn-beijing.volces.com/api/v3?redirect=synthetic",
        "https://ark.cn-beijing.volces.com:8443/api/v3",
    ],
)
def test_evaluator_rejects_non_target_credential_destinations(base):
    with pytest.raises(ValueError, match="explicit_ark_endpoint"):
        validate_target(base, "synthetic-model", "EVAL_KEY")


def test_evaluator_environment_excludes_ambient_secrets_and_proxies(monkeypatch):
    monkeypatch.setenv("EVAL_KEY", "synthetic-evaluation-key")
    monkeypatch.setenv("UNRELATED_SECRET", "synthetic-unrelated")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid")
    env = isolated_environment(SimpleNamespace(key_env="EVAL_KEY"))
    assert "UNRELATED_SECRET" not in env and "HTTPS_PROXY" not in env
    assert env["MODEL_AGENT_API_KEY"] == "synthetic-evaluation-key"
    assert env["PYTHON_DOTENV_DISABLED"] == "1"


def test_aggregate_distinguishes_incomplete_pairs_from_quality_and_overflow():
    def row(mode, success, tier="pressure", repeat=0):
        return {
            "case_id": "synthetic-" + tier,
            "repeat": repeat,
            "mode": mode,
            "task_success": success,
            "tier": tier,
            "calls": [],
            "seconds": 1,
            "known_oversize_at_transport": 0,
            "authorization_preserved": True,
            "original_events_preserved": True,
        }

    rows = [
        row("off", True),
        row("auto", False),
        row("off", False, "overflow"),
        row("auto", True, "overflow"),
        row("off", True, repeat=1),
    ]
    result = aggregate(rows, expected_rows=6)
    assert not result["complete"]
    assert result["paired_quality_runs"] == 1
    assert result["paired_regressions"] == 1
    assert result["paired_gains"] == 0
    assert result["cost"] is None


@pytest.mark.asyncio
async def test_evaluation_runner_records_metrics_without_storing_response_text(
    monkeypatch,
):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    case = cases(variants=1, tiers=("short",))[0]

    async def transport(self, **kwargs):
        return ModelResponse(
            model=kwargs["model"],
            choices=[
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(case.expected),
                    },
                }
            ],
            usage={"prompt_tokens": 120, "completion_tokens": 20, "total_tokens": 140},
        )

    monkeypatch.setattr(LiteLLMClient, "acompletion", transport)
    args = SimpleNamespace(
        model="synthetic-model",
        api_base="https://ark.cn-beijing.volces.com/api/v3",
        context_window=40000,
        input_limit=None,
        output_reserve=2000,
    )
    result = await run_case(
        case, "auto", args, {"calls": 5, "deadline": time.monotonic() + 30}
    )
    assert result["task_success"] and result["original_events_preserved"]
    assert len(result["calls"]) == 1 and not result["calls"][0]["summary"]
    assert result["calls"][0]["prompt_tokens"] == 120
    assert result["fact_fields"] == sorted(case.expected)
    assert result["calls"][0]["exact_fact_presence"] == {
        "input": [True, True, True],
        "output": [True, True, True],
    }
    assert "187.25" not in json.dumps(result)
