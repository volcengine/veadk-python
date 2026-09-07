# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from frontend.server.migration.evaluation.contracts import (
    EvaluationContractError,
    normalize_dataset,
)
from frontend.server.migration.evaluation.dimensions import (
    EVALUATION_DIMENSION_IDS,
    STANDARD_DIMENSION_IDS,
)
from frontend.server.migration.evaluation.models import (
    EVALUATION_DATASET_MAX_BYTES,
    EvaluationDatasetBody,
    MigrationEvaluationConfig,
)


def _dataset(**case: object) -> EvaluationDatasetBody:
    return EvaluationDatasetBody.model_validate(
        {
            "cases": [
                {
                    "caseId": "case-1",
                    "userInput": "北京今天的天气怎么样？",
                    **case,
                }
            ]
        }
    )


def test_dimension_registry_and_presets_are_stable() -> None:
    assert EVALUATION_DIMENSION_IDS == (
        "semantic_fidelity",
        "output_contract",
        "workflow_tool_fidelity",
        "context_memory_fidelity",
        "boundary_error_fidelity",
        "safety_refusal_fidelity",
    )
    assert MigrationEvaluationConfig(enabled=False).dimensions == []
    assert (
        tuple(MigrationEvaluationConfig(enabled=True).dimensions)
        == STANDARD_DIMENSION_IDS
    )
    custom = MigrationEvaluationConfig(
        enabled=True,
        preset="custom",
        dimensions=["safety_refusal_fidelity", "semantic_fidelity"],
    )
    assert custom.dimensions == ["semantic_fidelity", "safety_refusal_fidelity"]


def test_custom_dimensions_require_at_least_one_and_reject_duplicates() -> None:
    with pytest.raises(ValidationError, match="至少选择一个"):
        MigrationEvaluationConfig(enabled=True, preset="custom")
    with pytest.raises(ValidationError, match="不能重复"):
        MigrationEvaluationConfig(
            enabled=True,
            preset="custom",
            dimensions=["semantic_fidelity", "semantic_fidelity"],
        )


def test_dataset_canonicalizes_simple_input_without_expected_tools() -> None:
    body = _dataset(
        expectedOutcome="应返回天气和温度",
        criteria=["使用中文", "使用中文"],
        priorMessages=[
            {"role": "user", "content": "我准备去北京"},
            {"role": "assistant", "content": "好的，什么时候出发？"},
        ],
    )

    normalized = normalize_dataset(body)
    case = json.loads(normalized.content)

    assert case == {
        "case_id": "case-1",
        "criteria": ["使用中文"],
        "messages": [
            {"role": "user", "content": "我准备去北京"},
            {"role": "assistant", "content": "好的，什么时候出发？"},
            {"role": "user", "content": "北京今天的天气怎么样？"},
        ],
        "reference_output": "应返回天气和温度",
    }
    assert len(normalized.sha256) == 64
    assert normalized.version_id == normalized.sha256[:32]
    assert normalized.case_count == 1
    with pytest.raises(ValidationError, match="Extra inputs"):
        _dataset(expectedTools=["weather"])


@pytest.mark.parametrize(
    ("case", "match"),
    [
        ({"userInput": " "}, "用户会怎么问"),
        ({"priorMessages": [{"role": "tool", "content": "x"}]}, "user|assistant"),
        ({"expectedOutcome": "中" * (16 * 1024 // 3 + 1)}, "16 KiB"),
        ({"criteria": ["x"] * 21}, "20"),
        ({"criteria": ["中" * (2 * 1024 // 3 + 1)]}, "2 KiB"),
    ],
)
def test_case_boundaries_are_enforced(case: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _dataset(**case)


def test_message_limit_and_utf8_byte_limit_are_enforced() -> None:
    messages = [
        {"role": "assistant" if index % 2 else "user", "content": str(index)}
        for index in range(20)
    ]
    with pytest.raises(ValidationError, match="19 items"):
        _dataset(priorMessages=messages)
    with pytest.raises(ValidationError, match="32 KiB"):
        _dataset(userInput="中" * (32 * 1024 // 3 + 1))


def test_dataset_requires_one_to_one_hundred_unique_cases() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        EvaluationDatasetBody(cases=[])
    cases = [{"caseId": f"case-{index}", "userInput": "hello"} for index in range(101)]
    with pytest.raises(ValidationError, match="100 items"):
        EvaluationDatasetBody.model_validate({"cases": cases})
    with pytest.raises(ValidationError, match="不能重复"):
        EvaluationDatasetBody.model_validate(
            {
                "cases": [
                    {"caseId": "same", "userInput": "one"},
                    {"caseId": "same", "userInput": "two"},
                ]
            }
        )


def test_normalized_jsonl_limit_is_checked_after_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _dataset()
    monkeypatch.setattr(
        "frontend.server.migration.evaluation.contracts.EVALUATION_DATASET_MAX_BYTES",
        len(normalize_dataset(body).content) - 1,
    )
    with pytest.raises(EvaluationContractError, match="10 MiB"):
        normalize_dataset(body)


def test_limit_constant_is_exactly_ten_mib() -> None:
    assert EVALUATION_DATASET_MAX_BYTES == 10 * 1024 * 1024
