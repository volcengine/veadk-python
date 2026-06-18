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

import json

from veadk.extensions.harness.modules.tool_result_compactor import (
    ToolResultCompactor,
    ToolResultCompactorConfig,
)
from veadk.extensions.harness.schemas import CompressionRequest, ConversationMessage


def test_tool_result_compactor_compacts_large_tool_result():
    compactor = ToolResultCompactor(
        ToolResultCompactorConfig(max_tool_result_chars=200, summary_chars=80)
    )

    compressed, report = compactor.compress_tool_result({"rows": "x" * 1000})

    assert report.changed is True
    assert compressed["harness_compressed"] is True
    assert report.compressed_chars < report.original_chars


def test_builtin_provider_preserves_metric_rows_and_drops_noise():
    compactor = ToolResultCompactor(ToolResultCompactorConfig())
    payload = {
        "metric_rows": [
            {"kind": "metric", "model": "T4", "accuracy": 82, "rank": 2},
            {"kind": "metric", "model": "T5", "accuracy": 88, "rank": 1},
        ],
        "debug_rows": [
            {"kind": "debug", "row": index, "trace": "x" * 80} for index in range(200)
        ],
    }

    compressed, report = compactor.compress_tool_result(payload)

    assert compressed["provider"] == "builtin"
    assert report.provider == "builtin"
    assert report.compression_ratio < 0.1
    assert "model=T5" in str(compressed["summary"])
    assert "debug_rows" not in str(compressed["summary"])


def test_builtin_provider_reads_run_code_result_string():
    compactor = ToolResultCompactor(ToolResultCompactorConfig())
    payload = {
        "result": (
            '[{"kind":"metric","model":"T5","accuracy":88},'
            '{"kind":"debug","payload":"' + ("x" * 12000) + '"}]'
        )
    }

    compressed, report = compactor.compress_tool_result(payload)

    assert compressed["provider"] == "builtin"
    assert report.provider == "builtin"
    assert "model=T5" in str(compressed["summary"])
    assert "payload" not in str(compressed["summary"])


def test_builtin_provider_ignores_debug_rows_with_metric_shaped_fields():
    compactor = ToolResultCompactor(ToolResultCompactorConfig())
    rows = [
        {"kind": "metric", "model": "T5", "accuracy": 88, "rank": 0},
        {
            "kind": "debug",
            "model": "noise-1",
            "accuracy": 0,
            "payload": "x" * 12000,
        },
    ]

    compressed, report = compactor.compress_tool_result({"result": json.dumps(rows)})

    assert report.changed is True
    assert "model=T5" in str(compressed["summary"])
    assert "noise-1" not in str(compressed["summary"])
    assert "payload" not in str(compressed["summary"])


def test_policy_preserves_recent_tool_feedback():
    compactor = ToolResultCompactor(
        ToolResultCompactorConfig(
            max_context_chars=500,
            min_candidate_chars=100,
            protect_recent_messages=1,
        )
    )
    messages = [
        ConversationMessage(role="user", content="summarize"),
        ConversationMessage(role="tool", content="a" * 1000),
        ConversationMessage(role="tool", content="b" * 1000),
    ]

    result = compactor.compress_messages(
        CompressionRequest(messages=messages, max_context_chars=500)
    )

    assert result.report.changed is True
    assert result.messages[-1].content == "b" * 1000
    assert result.report.policy["candidate_count"] == 1
