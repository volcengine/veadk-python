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

from veadk.extensions.harness import (
    ContextEngine,
    HarnessInvocationContextConfig,
    HarnessInvocationContextBuilder,
    HarnessInvocationRef,
    TaskContract,
)
from veadk.extensions.harness.schemas import ToolReceipt, ConversationMessage


def test_invocation_context_builder_builds_task_anchor_and_receipts():
    builder = HarnessInvocationContextBuilder()
    context = HarnessInvocationRef(
        session_id="s1",
        invocation_id="r1",
        profile="research",
        task=TaskContract(goal="Create a chart", acceptance_criteria=["save a PNG"]),
    )
    bundle = builder.prepare_context(
        context,
        user_input="Create a chart from this CSV file.",
        history=[ConversationMessage(role="user", content="Use the latest CSV.")],
        receipts=[
            ToolReceipt(name="read_csv", status="success", summary="10 rows loaded")
        ],
        has_tools=True,
    )

    assert bundle.injected is True
    assert "task_goal: Create a chart" in bundle.header
    assert "read_csv [success]" in bundle.header
    assert "[Harness Tool Protocol]" in bundle.header
    assert "valid JSON object arguments" in bundle.header


def test_invocation_context_defaults_match_runtime_budget():
    config = HarnessInvocationContextConfig()

    assert config.max_history_messages == 12
    assert config.max_context_chars == 24000
    assert config.max_receipts == 8
    assert config.receipt_summary_chars == 500


def test_invocation_context_receipts_are_bounded_and_recent():
    builder = HarnessInvocationContextBuilder()
    context = HarnessInvocationRef(session_id="s1", invocation_id="r1")
    receipts = [
        ToolReceipt(
            name=f"tool_{index}",
            status="success",
            summary=f"summary {index} " + ("x" * 800),
        )
        for index in range(10)
    ]

    bundle = builder.prepare_context(
        context,
        user_input="Summarize tool evidence.",
        receipts=receipts,
    )

    assert "tool_0 [success]" not in bundle.header
    assert "tool_1 [success]" not in bundle.header
    assert "tool_2 [success]" in bundle.header
    assert "tool_9 [success]" in bundle.header
    assert "x" * 700 not in bundle.header


def test_invocation_context_builder_injects_after_system_messages():
    builder = HarnessInvocationContextBuilder()
    context = HarnessInvocationRef(session_id="s1", invocation_id="r1")
    messages = [
        ConversationMessage(role="system", content="base system"),
        ConversationMessage(role="user", content="hello"),
    ]

    enhanced, bundle = builder.enhance_messages(messages, context, user_input="hello")

    assert bundle.injected is True
    assert enhanced[0].content == "base system"
    assert enhanced[1].name == "veadk_harness_context"


def test_context_engine_alias_remains_available():
    assert ContextEngine is HarnessInvocationContextBuilder
