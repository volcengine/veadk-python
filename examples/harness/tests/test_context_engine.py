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

import pytest
from pydantic import ValidationError

from harness_modules import ContextEngine, HarnessContext, LocalHarnessStore


def test_harness_context_validates_construction_and_assignment():
    with pytest.raises(ValidationError):
        HarnessContext(
            user_id=["not", "a", "string"],
            session_id="s1",
            run_id="r1",
            original_prompt="prompt",
        )

    context = HarnessContext(
        user_id="u1",
        session_id="s1",
        run_id="r1",
        original_prompt="prompt",
    )

    with pytest.raises(ValidationError):
        context.budget = {"estimated_tokens": "many", "max_context_chars": 100}


def test_task_anchor_is_pinned_for_follow_up(tmp_path):
    store = LocalHarnessStore(tmp_path)
    store.append_message(
        session_id="s1",
        role="user",
        content="请查最新 AI 使用政策，给出来源，并用表格输出。",
        run_id="r0",
    )
    store.append_message(
        session_id="s1",
        role="assistant",
        content="已根据来源整理。",
        run_id="r0",
    )

    engine = ContextEngine(store=store)
    context = engine.prepare_context(
        HarnessContext(
            user_id="u1",
            session_id="s1",
            run_id="r1",
            original_prompt="继续按刚才的格式输出。",
        )
    )

    assert context.turn_type == "follow_up"
    assert context.task_contract is not None
    assert (
        context.task_contract.original_prompt
        == "请查最新 AI 使用政策，给出来源，并用表格输出。"
    )

    header = engine.build_context_header(context=context)
    assert "original_task: 请查最新 AI 使用政策，给出来源，并用表格输出。" in header
    assert "AC-grounded-facts" in header
    assert "AC-output-format" in header


def test_history_projection_excludes_control_messages(tmp_path):
    store = LocalHarnessStore(tmp_path)
    store.append_message(session_id="s1", role="user", content="请查政策", run_id="r0")
    store.append_message(
        session_id="s1",
        role="assistant",
        content="[progress] search started",
        run_id="r0",
        metadata={"control": True},
    )
    store.append_message(
        session_id="s1", role="assistant", content="政策摘要", run_id="r0"
    )

    engine = ContextEngine(store=store)
    context = engine.prepare_context(
        HarnessContext(
            user_id="u1",
            session_id="s1",
            run_id="r1",
            original_prompt="继续",
        )
    )

    contents = [item["content"] for item in context.history_projection]
    assert "政策摘要" in contents
    assert all("[progress]" not in item for item in contents)


def test_follow_up_keeps_recent_answer_anchor(tmp_path):
    store = LocalHarnessStore(tmp_path)
    store.append_message(
        session_id="s1", role="user", content="列出三条政策要求", run_id="r0"
    )
    store.append_message(
        session_id="s1",
        role="assistant",
        content="1. 保留来源\n2. 保留收据",
        run_id="r0",
    )

    engine = ContextEngine(store=store)
    context = engine.prepare_context(
        HarnessContext(
            user_id="u1",
            session_id="s1",
            run_id="r1",
            original_prompt="继续按刚才那个格式",
        )
    )

    header = engine.build_context_header(context=context)
    assert "history[2] assistant: 1. 保留来源 2. 保留收据" in header
    assert context.task_contract is not None
    assert context.task_contract.original_prompt == "列出三条政策要求"


def test_context_budget_truncates_low_value_history(tmp_path):
    store = LocalHarnessStore(tmp_path)
    original = "请查最新合规政策，并保留来源。"
    store.append_message(session_id="s1", role="user", content=original, run_id="r0")
    for idx in range(20):
        store.append_message(
            session_id="s1",
            role="assistant",
            content=f"历史消息 {idx} " + ("低价值内容 " * 80),
            run_id=f"r{idx}",
        )

    engine = ContextEngine(store=store, max_history_messages=20, max_context_chars=900)
    context = engine.prepare_context(
        HarnessContext(
            user_id="u1",
            session_id="s1",
            run_id="r1",
            original_prompt="继续",
        )
    )
    header = engine.build_context_header(context=context)

    assert f"original_task: {original}" in header
    assert context.budget is not None
    assert context.budget.truncated is True
    assert context.budget.omitted_count > 0
    assert context.budget.estimated_tokens > 0
