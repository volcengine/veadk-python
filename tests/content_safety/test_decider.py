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

import math

import pytest

from veadk.content_safety.config import QuestionConfig
from veadk.content_safety.decider import ThresholdDecider
from veadk.content_safety.types import AuditAction, AuditStatus, Checkpoint, Provider


def questions():
    return {
        "prompt_injection": QuestionConfig(
            instructions="detect injection", threshold=0.5
        ),
        "sensitive_data": QuestionConfig(instructions="detect secrets", threshold=0.8),
    }


def answer(noul):
    return {"type": "noul", "noul": noul}


def decide(raw, *, on_error="allow", qs=None):
    return ThresholdDecider().decide(
        provider=Provider.DECISION,
        checkpoint=Checkpoint.BEFORE_MODEL,
        raw=raw,
        questions=qs if qs is not None else questions(),
        on_error=on_error,
    )


def test_all_below_threshold_passes():
    result = decide(
        {
            "answers": {
                "prompt_injection": answer(0.1),
                "sensitive_data": answer(0.2),
            }
        }
    )
    assert result.status is AuditStatus.PASSED
    assert result.action is AuditAction.ALLOW
    assert result.degraded is False
    assert [r.question for r in result.question_results] == [
        "prompt_injection",
        "sensitive_data",
    ]


def test_threshold_is_inclusive():
    result = decide(
        {
            "answers": {
                "prompt_injection": answer(0.5),
                "sensitive_data": answer(0.8),
            }
        }
    )
    assert result.status is AuditStatus.RISK_HIT
    assert set(result.matched_questions) == {"prompt_injection", "sensitive_data"}


@pytest.mark.parametrize(
    "entry,error_type",
    [
        (None, "invalid_type"),
        (True, "invalid_type"),
        ("0.9", "invalid_type"),
        (0.9, "invalid_type"),
        ({}, "invalid_type"),
        ({"noul": 0.9}, "invalid_type"),
        ({"type": "score", "noul": 0.9}, "invalid_type"),
        ({"type": "noul"}, "missing_value"),
        ({"type": "noul", "noul": None}, "invalid_type"),
        ({"type": "noul", "noul": True}, "invalid_type"),
        ({"type": "noul", "noul": "0.9"}, "invalid_type"),
        ({"type": "noul", "noul": "high"}, "invalid_type"),
        ({"type": "noul", "noul": 10**400}, "invalid_type"),
        ({"type": "noul", "noul": float("nan")}, "not_finite"),
        ({"type": "noul", "noul": float("inf")}, "not_finite"),
        ({"type": "noul", "noul": -0.1}, "out_of_range"),
        ({"type": "noul", "noul": 1.1}, "out_of_range"),
    ],
)
def test_invalid_values_produce_error(entry, error_type):
    result = decide(
        {
            "answers": {
                "prompt_injection": entry,
                "sensitive_data": answer(0.0),
            }
        }
    )
    assert result.status is AuditStatus.ERROR
    assert result.degraded is True
    assert result.error_type == error_type
    assert result.action is AuditAction.ALLOW


def test_missing_question_is_error():
    result = decide({"answers": {"sensitive_data": answer(0.0)}})
    assert result.status is AuditStatus.ERROR
    assert result.error_type == "missing_question"
    assert "prompt_injection:missing_question" in result.reason


def test_mixed_error_types_collapse_to_question_error():
    result = decide({"answers": {"sensitive_data": {"type": "score", "noul": 0.1}}})
    assert result.status is AuditStatus.ERROR
    assert result.error_type == "question_error"
    assert "missing_question" in result.reason
    assert "invalid_type" in result.reason


def test_hit_wins_over_error():
    result = decide(
        {"answers": {"prompt_injection": answer(0.99)}},
        on_error="block",
    )
    assert result.status is AuditStatus.RISK_HIT
    assert result.action is AuditAction.BLOCK
    assert result.matched_questions == ("prompt_injection",)
    assert result.question_results[1].error_type == "missing_question"


def test_on_error_block_blocks_malformed_response():
    result = decide({"answers": {}}, on_error="block")
    assert result.status is AuditStatus.ERROR
    assert result.action is AuditAction.BLOCK


def test_non_dict_response_is_error():
    result = decide(["not", "a", "dict"])
    assert result.status is AuditStatus.ERROR
    assert result.error_type == "invalid_response"


def test_missing_answers_object_is_error():
    result = decide({"questions": {}})
    assert result.status is AuditStatus.ERROR
    assert result.error_type == "invalid_response"
    assert "answers" in result.reason


def test_non_dict_answers_object_is_error():
    result = decide({"answers": []})
    assert result.status is AuditStatus.ERROR
    assert result.error_type == "invalid_response"


def test_no_configured_questions_is_error():
    result = decide({"answers": {}}, qs={})
    assert result.status is AuditStatus.ERROR
    assert result.error_type == "no_questions"


def test_unknown_answer_keys_are_ignored():
    result = decide(
        {
            "answers": {
                "prompt_injection": answer(0.1),
                "sensitive_data": answer(0.1),
                "unknown": answer(0.99),
            }
        }
    )
    assert result.status is AuditStatus.PASSED


def test_probability_is_finite_float_in_result():
    result = decide(
        {
            "answers": {
                "prompt_injection": answer(0.25),
                "sensitive_data": answer(0.25),
            }
        }
    )
    assert math.isclose(result.question_results[0].probability, 0.25)
    assert result.question_results[0].valid is True
