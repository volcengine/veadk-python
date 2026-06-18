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
from pathlib import Path

from veadk.extensions.harness.adk import build_harness_plugins
from veadk.extensions.harness.eval import run_deterministic_eval
from veadk.extensions.harness.modules.invocation_context import (
    HarnessInvocationContextBuilder,
)
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    ToolResultCompactor,
    ToolResultCompactorConfig,
)
from veadk.extensions.harness.schemas import (
    CompressionRequest,
    ConversationMessage,
    HarnessInvocationRef,
    TaskContract,
)

GOLDEN_DIR = Path(__file__).parent / "golden"


def _load_case(filename: str) -> dict[str, object]:
    return json.loads((GOLDEN_DIR / filename).read_text().splitlines()[0])


def test_context_engine_golden_case():
    case = _load_case("context_engine_cases.jsonl")
    input_data = case["input"]
    expected = case["expected"]
    assert isinstance(input_data, dict)
    assert isinstance(expected, dict)
    context = HarnessInvocationRef(
        session_id="s1",
        invocation_id="r1",
        task=TaskContract(goal=str(input_data["goal"])),
    )

    bundle = HarnessInvocationContextBuilder().prepare_context(
        context,
        user_input=str(input_data["user_input"]),
    )

    for text in expected["contains"]:
        assert text in bundle.header


def test_compactor_golden_case():
    case = _load_case("compressor_cases.jsonl")
    input_data = case["input"]
    expected = case["expected"]
    assert isinstance(input_data, dict)
    assert isinstance(expected, dict)
    old_tool_chars = int(input_data["old_tool_chars"])
    latest_tool = str(input_data["latest_tool"])
    messages = [
        ConversationMessage(role="user", content="Summarize."),
        ConversationMessage(role="tool", content="x" * old_tool_chars),
        ConversationMessage(role="assistant", content="I will inspect the data."),
        ConversationMessage(role="tool", content=latest_tool),
    ]
    compactor = ToolResultCompactor(
        ToolResultCompactorConfig(max_context_chars=1000, min_candidate_chars=200)
    )

    result = compactor.compress_messages(
        CompressionRequest(messages=messages, max_context_chars=1000)
    )
    before = sum(len(message.content) for message in messages)
    after = sum(len(message.content) for message in result.messages)

    assert 1 - after / before >= expected["min_saving_ratio"]
    assert result.messages[-1].content == latest_tool


def test_verifier_golden_case():
    case = _load_case("verifier_cases.jsonl")
    input_data = case["input"]
    expected = case["expected"]
    assert isinstance(input_data, dict)
    assert isinstance(expected, dict)

    report = FinalResponseVerifier().verify_text(str(input_data["answer"]))

    assert report.status == expected["status"]


def test_plugin_lifecycle_golden_case():
    case = _load_case("plugin_lifecycle_cases.jsonl")
    input_data = case["input"]
    expected = case["expected"]
    assert isinstance(input_data, dict)
    assert isinstance(expected, dict)

    plugins = build_harness_plugins(components=str(input_data["components"]))

    assert [plugin.name for plugin in plugins] == expected["plugins"]


def test_deterministic_eval_reports_effect_direction():
    results = run_deterministic_eval()

    assert results[0].char_saving_ratio > 0
    assert results[1].baseline_false_accept is True
    assert results[1].enhanced_false_accept is False
