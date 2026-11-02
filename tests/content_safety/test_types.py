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

from veadk.content_safety.types import (
    AuditAction,
    AuditResult,
    AuditStatus,
    Checkpoint,
    Provider,
    QuestionResult,
)


def test_question_result_to_dict():
    item = QuestionResult(
        question="q", threshold=0.5, probability=0.9, valid=True, hit=True
    )
    assert item.to_dict() == {
        "question": "q",
        "threshold": 0.5,
        "probability": 0.9,
        "valid": True,
        "hit": True,
        "error_type": None,
    }


def test_audit_result_to_dict_is_json_ready():
    item = QuestionResult(question="q", threshold=0.5, probability=0.1, valid=True)
    result = AuditResult.allow(
        provider=Provider.DECISION,
        checkpoint=Checkpoint.BEFORE_MODEL,
        question_results=(item,),
        reason="ok",
    )
    data = result.to_dict()
    assert data["provider"] == "decision"
    assert data["checkpoint"] == "before_model"
    assert data["status"] == "passed"
    assert data["action"] == "allow"
    assert data["question_results"][0]["question"] == "q"


def test_block_constructor_sets_terminal_fields():
    result = AuditResult.block(
        provider=Provider.DECISION,
        checkpoint=Checkpoint.AFTER_TOOL,
        matched_questions=("a",),
        reason="hit",
    )
    assert result.status is AuditStatus.RISK_HIT
    assert result.action is AuditAction.BLOCK
    assert result.degraded is False
    assert result.matched_questions == ("a",)


def test_error_constructor_follows_on_error():
    allow = AuditResult.error(
        provider=Provider.DECISION,
        checkpoint=Checkpoint.BEFORE_MODEL,
        on_error="allow",
        error_type="timeout",
    )
    block = AuditResult.error(
        provider=Provider.DECISION,
        checkpoint=Checkpoint.BEFORE_MODEL,
        on_error="block",
        error_type="timeout",
    )
    assert allow.action is AuditAction.ALLOW
    assert allow.status is AuditStatus.ERROR
    assert allow.degraded is True
    assert block.action is AuditAction.BLOCK


def test_skipped_and_disabled_constructors():
    skipped = AuditResult.skipped(
        provider=Provider.DECISION,
        checkpoint=Checkpoint.BEFORE_MODEL,
        reason="empty",
    )
    disabled = AuditResult.disabled(
        provider=Provider.NONE,
        checkpoint=Checkpoint.AFTER_MODEL,
        reason="off",
    )
    assert skipped.status is AuditStatus.SKIPPED
    assert skipped.action is AuditAction.ALLOW
    assert disabled.status is AuditStatus.DISABLED
    assert disabled.action is AuditAction.ALLOW
