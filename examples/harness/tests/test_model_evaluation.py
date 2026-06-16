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

from evaluation.run_model_eval import (
    _model_metrics,
    load_model_env,
    parse_env_file,
    render_model_markdown,
)


def test_model_env_loader_redacts_and_loads_only_model_keys(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "MODEL_AGENT_API_KEY=example-test-key",
                "MODEL_AGENT_NAME=test-model",
                "MODEL_AGENT_API_BASE=https://example.com/api",
                "DATABASE_POSTGRESQL_PASSWORD=unused-placeholder",
            ]
        ),
        encoding="utf-8",
    )
    for key in ("MODEL_AGENT_API_KEY", "MODEL_AGENT_NAME", "MODEL_AGENT_API_BASE"):
        monkeypatch.delenv(key, raising=False)

    result = load_model_env(env_file)

    assert result.missing_required_keys == []
    assert result.model_name == "test-model"
    assert set(result.loaded_keys) == {
        "MODEL_AGENT_API_KEY",
        "MODEL_AGENT_NAME",
        "MODEL_AGENT_API_BASE",
    }
    assert "DATABASE_POSTGRESQL_PASSWORD" not in result.loaded_keys


def test_parse_env_file_handles_quotes_and_export(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "export MODEL_AGENT_NAME=\"quoted-model\"\nMODEL_AGENT_API_BASE='https://example.com'\n",
        encoding="utf-8",
    )

    values = parse_env_file(env_file)

    assert values["MODEL_AGENT_NAME"] == "quoted-model"
    assert values["MODEL_AGENT_API_BASE"] == "https://example.com"


def test_model_metrics_show_false_accept_reduction():
    rows = [
        {
            "id": "unsupported",
            "scenario_name": "Unsupported source claim",
            "harness_capability": "ResultVerifier unsupported-answer block",
            "scenario_type": "unsupported_without_evidence",
            "prompt": "source required",
            "evidence_required": True,
            "expected_trusted": False,
            "baseline": {
                "answer": "unsupported answer",
                "trusted_by_runtime": True,
                "posthoc_verifier_done": False,
                "posthoc_missing_requirements": ["missing evidence"],
            },
            "harness": {
                "answer": "cannot verify",
                "trusted_by_runtime": False,
                "verifier_done": False,
                "missing_requirements": ["missing evidence"],
                "receipt_count": 0,
                "receipt_tools": [],
            },
        },
        {
            "id": "answerable",
            "scenario_name": "Answerable with tool evidence",
            "harness_capability": "Tool receipt + source verification",
            "scenario_type": "answerable_with_tools",
            "prompt": "source required",
            "evidence_required": True,
            "expected_trusted": True,
            "baseline": {
                "answer": "verified answer",
                "trusted_by_runtime": True,
                "posthoc_verifier_done": False,
                "posthoc_missing_requirements": [],
            },
            "harness": {
                "answer": "verified answer",
                "trusted_by_runtime": True,
                "verifier_done": True,
                "missing_requirements": [],
                "receipt_count": 1,
                "receipt_tools": ["lookup"],
            },
        },
    ]

    metrics = _model_metrics(rows)

    assert metrics["baseline_trust_decision_accuracy"] == 0.5
    assert metrics["harness_trust_decision_accuracy"] == 1.0
    assert metrics["trust_decision_accuracy_gain_pp"] == 50.0
    assert metrics["baseline_unsupported_false_accept_rate"] == 1.0
    assert metrics["harness_unsupported_false_accept_rate"] == 0.0
    assert metrics["unsupported_false_accept_reduction_pp"] == 100.0
    assert metrics["harness_answerable_receipt_coverage_rate"] == 1.0
    assert metrics["harness_answerable_verified_pass_rate"] == 1.0
    assert metrics["harness_unsupported_block_rate"] == 1.0


def test_model_report_is_grouped_by_scenario():
    report = {
        "generated_at": "2026-06-11T00:00:00+00:00",
        "env": {
            "env_file": "<process-env>",
            "loaded_keys": [],
            "model_name": "test-model",
            "api_base": "https://example.com",
            "api_key": "<redacted>",
        },
        "method": {
            "baseline": "normal veADK Agent; every non-empty answer is trusted",
            "harness": "veADK Agent with ContextEngine and ResultVerifier",
            "case_count": 1,
        },
        "metrics": {
            "case_count": 1,
            "answerable_case_count": 0,
            "unsupported_case_count": 1,
            "baseline_trust_decision_accuracy": 0.0,
            "harness_trust_decision_accuracy": 1.0,
            "trust_decision_accuracy_gain_pp": 100.0,
            "baseline_unsupported_false_accept_rate": 1.0,
            "harness_unsupported_false_accept_rate": 0.0,
            "unsupported_false_accept_reduction_pp": 100.0,
            "harness_answerable_verified_pass_rate": 0.0,
            "harness_answerable_receipt_coverage_rate": 0.0,
            "harness_unsupported_block_rate": 1.0,
            "harness_trusted_answer_verification_rate": 0.0,
        },
        "cases": [
            {
                "id": "production-no-evidence-source-claim",
                "scenario_name": "No-evidence hallucination suppression",
                "harness_capability": "ResultVerifier unsupported-answer block",
                "scenario_type": "unsupported_without_evidence",
                "prompt": "source required",
                "evidence_required": True,
                "expected_trusted": False,
                "baseline": {
                    "answer": "unsupported answer",
                    "trusted_by_runtime": True,
                    "posthoc_verifier_done": False,
                    "posthoc_missing_requirements": ["missing evidence"],
                },
                "harness": {
                    "answer": "cannot verify",
                    "trusted_by_runtime": False,
                    "verifier_done": False,
                    "missing_requirements": ["missing evidence"],
                    "receipt_count": 0,
                    "receipt_tools": [],
                },
            }
        ],
    }

    markdown = render_model_markdown(report)

    assert "| Scenario | Harness capability |" in markdown
    assert markdown.index("Scenario") < markdown.index("Case Detail")
    assert "No-evidence hallucination suppression" in markdown
    assert "trust decision corrected" in markdown
