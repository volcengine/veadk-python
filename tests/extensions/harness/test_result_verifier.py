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

from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
    FinalResponseVerifierConfig,
)
from veadk.extensions.harness.schemas import ToolReceipt


def test_verifier_fails_completion_claim_without_receipt():
    verifier = FinalResponseVerifier()

    report = verifier.verify_text("Done, I created the report.")

    assert report.status == "fail"
    assert report.unsupported_claims


def test_verifier_does_not_match_completion_markers_inside_words_or_negations():
    verifier = FinalResponseVerifier()

    assert verifier.verify_text("The report is still undone.").status == "pass"
    assert verifier.verify_text("报告尚未完成。").status == "pass"


def test_verifier_matches_mixed_ascii_and_cjk_completion_markers():
    verifier = FinalResponseVerifier(
        FinalResponseVerifierConfig(completion_markers=["done", "完成"])
    )

    assert verifier.verify_text("Done，报告已完成。").status == "fail"
    assert verifier.verify_text("The work is undone，报告尚未完成。").status == "pass"


def test_verifier_allows_completion_claim_with_success_receipt():
    verifier = FinalResponseVerifier()

    report = verifier.verify_text(
        "Done, I created the report.",
        receipts=[
            ToolReceipt(name="write_file", status="success", summary="report.md saved")
        ],
    )

    assert report.status == "pass"
    assert report.supported_claims


def test_verifier_block_intervention():
    verifier = FinalResponseVerifier(FinalResponseVerifierConfig(mode="block"))

    report = verifier.verify_text("The file was saved successfully.")
    intervention = verifier.decide(report)

    assert intervention.action == "block"


def test_verifier_ignores_html_like_code_blocks_for_truncation():
    verifier = FinalResponseVerifier()
    html_snippet = "```html\n<div>\n" + ("x" * 1500) + "\n```"

    report = verifier.verify_text(html_snippet)

    assert report.status == "pass"


def test_verifier_ignores_unclosed_script_inside_code_block():
    verifier = FinalResponseVerifier()
    html_snippet = "```html\n<html><body><script>\n" + ("x" * 1500) + "\n```"

    report = verifier.verify_text(html_snippet)

    assert report.status == "pass"


def test_verifier_does_not_treat_inline_html_tags_as_truncated_document():
    verifier = FinalResponseVerifier()
    text = "Use `<span>`, `<a>`, and `<input>` in examples. " + "<div" + ("x" * 1500)

    report = verifier.verify_text(text)

    assert report.status == "pass"


def test_verifier_flags_actual_truncated_html():
    verifier = FinalResponseVerifier()
    html = "<html><body><div><p>" + ("x" * 1500)

    report = verifier.verify_text(html)

    assert report.status == "fail"
    assert "response looks like truncated html" in report.reasons


def test_repair_candidates_respects_configured_limit():
    verifier = FinalResponseVerifier(
        FinalResponseVerifierConfig(max_repair_candidates=1)
    )

    assert verifier._repair_candidates('prefix {"a": 1,}') == ['prefix {"a": 1,}']


def test_try_repair_json_text_respects_candidate_limit():
    value = '{"message": “hello”}'

    limited = FinalResponseVerifier(
        FinalResponseVerifierConfig(max_repair_candidates=1)
    )
    unrestricted = FinalResponseVerifier()

    assert limited.try_repair_json_text(value) == value
    assert unrestricted.try_repair_json_text(value) == '{"message":"hello"}'
