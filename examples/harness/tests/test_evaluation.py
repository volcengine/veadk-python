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

from evaluation.run_eval import run_evaluation


def test_offline_eval_proves_harness_metric_lift(tmp_path):
    report = run_evaluation(tmp_path)
    verifier = report["result_verifier"]
    context = report["context_engine"]

    assert verifier["harness"]["accuracy"] > verifier["baseline"]["accuracy"]
    assert verifier["baseline"]["unsafe_false_accept_rate"] == 1.0
    assert verifier["harness"]["unsafe_false_accept_rate"] == 0.0
    assert verifier["harness"]["unsafe_recall"] == 1.0

    assert context["harness"]["quality_score"] > context["baseline"]["quality_score"]
    assert context["harness"]["anchor_contract_rate"] == 1.0
    assert context["harness"]["control_pollution_rate"] == 0.0
    assert context["harness"]["budget_compliance_rate"] == 1.0

    assert (tmp_path / "harness_eval_report.json").exists()
    assert (tmp_path / "harness_eval_report.md").exists()
    markdown = (tmp_path / "harness_eval_report.md").read_text(encoding="utf-8")
    assert "| Scenario | Harness module |" in markdown
    assert "RAG memory freshness" in markdown
    assert markdown.index("Scenario Lift") < markdown.index("ResultVerifier Cases")
