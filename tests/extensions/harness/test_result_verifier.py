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
