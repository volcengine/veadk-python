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

"""Deterministic module-level evals for Harness effects."""

from __future__ import annotations

from pydantic import Field

from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    ToolResultCompactor,
    ToolResultCompactorConfig,
)
from veadk.extensions.harness.schemas import (
    ToolReceipt,
    CompressionRequest,
    ConversationMessage,
    HarnessBaseModel,
)


class HarnessEvalSummary(HarnessBaseModel):
    """Human-readable deterministic eval metrics."""

    scenario: str
    baseline_chars: int
    enhanced_chars: int
    char_saving_ratio: float
    baseline_false_accept: bool
    enhanced_false_accept: bool
    notes: list[str] = Field(default_factory=list)


def run_deterministic_eval() -> list[HarnessEvalSummary]:
    """Run small synthetic checks that demonstrate module effects."""

    compactor = ToolResultCompactor(
        ToolResultCompactorConfig(max_context_chars=1200, min_candidate_chars=200)
    )
    large_tool_output = "metric,value\n" + "\n".join(
        f"item_{index},{index}" for index in range(500)
    )
    messages = [
        ConversationMessage(role="user", content="Summarize the latest metrics."),
        ConversationMessage(role="tool", content=large_tool_output),
        ConversationMessage(role="assistant", content="I will summarize the data."),
        ConversationMessage(role="tool", content="latest status: complete"),
    ]
    compressed = compactor.compress_messages(
        CompressionRequest(messages=messages, max_context_chars=1200)
    )
    baseline_chars = sum(len(message.content) for message in messages)
    enhanced_chars = sum(len(message.content) for message in compressed.messages)

    verifier = FinalResponseVerifier()
    unsupported = verifier.verify_text("Done, I created the report.")
    supported = verifier.verify_text(
        "Done, I created the report.",
        receipts=[
            ToolReceipt(
                name="write_report",
                status="success",
                summary="report.md saved",
            )
        ],
    )
    return [
        HarnessEvalSummary(
            scenario="Large historical tool result",
            baseline_chars=baseline_chars,
            enhanced_chars=enhanced_chars,
            char_saving_ratio=(
                1 - enhanced_chars / baseline_chars if baseline_chars else 0.0
            ),
            baseline_false_accept=False,
            enhanced_false_accept=False,
            notes=["old large tool output is summarized while latest feedback is kept"],
        ),
        HarnessEvalSummary(
            scenario="Unsupported completion claim",
            baseline_chars=len("Done, I created the report."),
            enhanced_chars=len("Done, I created the report."),
            char_saving_ratio=0.0,
            baseline_false_accept=True,
            enhanced_false_accept=unsupported.status != "fail",
            notes=[f"supported receipt status: {supported.status}"],
        ),
    ]
