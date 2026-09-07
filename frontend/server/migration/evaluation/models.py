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

"""User-facing contracts for migration-effect evaluation."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .dimensions import (
    EVALUATION_DIMENSION_IDS,
    STANDARD_DIMENSION_IDS,
    EvaluationDimensionId,
)

EVALUATION_DATASET_MAX_BYTES = 10 * 1024 * 1024
EVALUATION_CASES_MAX = 100
EVALUATION_MESSAGES_MAX = 20
EVALUATION_MESSAGE_TEXT_MAX_BYTES = 32 * 1024
EVALUATION_REFERENCE_MAX_BYTES = 16 * 1024
EVALUATION_CRITERIA_MAX = 20
EVALUATION_CRITERION_MAX_BYTES = 2 * 1024
EVALUATION_OUTPUT_MAX_BYTES = 64 * 1024

_CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


class MigrationEvaluationConfig(BaseModel):
    enabled: bool = False
    preset: Literal["standard", "custom"] = "standard"
    dimensions: list[EvaluationDimensionId] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def normalize(self) -> MigrationEvaluationConfig:
        if not self.enabled:
            self.preset = "standard"
            self.dimensions = []
            return self
        if self.preset == "standard":
            if self.dimensions and tuple(self.dimensions) != STANDARD_DIMENSION_IDS:
                raise ValueError("标准评测维度不可修改；请切换到自定义评测")
            self.dimensions = list(STANDARD_DIMENSION_IDS)
            return self
        if not self.dimensions:
            raise ValueError("自定义评测至少选择一个维度")
        if len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("评测维度不能重复")
        selected = set(self.dimensions)
        self.dimensions = [
            dimension for dimension in EVALUATION_DIMENSION_IDS if dimension in selected
        ]
        return self


class EvaluationMessageBody(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def normalize(self) -> EvaluationMessageBody:
        self.content = self.content.strip()
        if not self.content:
            raise ValueError("历史对话内容不能为空")
        return self


class EvaluationCaseBody(BaseModel):
    case_id: str = Field(alias="caseId", min_length=1, max_length=64)
    user_input: str = Field(alias="userInput", min_length=1)
    expected_outcome: str | None = Field(default=None, alias="expectedOutcome")
    criteria: list[str] = Field(default_factory=list)
    prior_messages: list[EvaluationMessageBody] = Field(
        default_factory=list,
        alias="priorMessages",
        max_length=EVALUATION_MESSAGES_MAX - 1,
    )

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def normalize(self) -> EvaluationCaseBody:
        self.case_id = self.case_id.strip()
        self.user_input = self.user_input.strip()
        self.expected_outcome = (self.expected_outcome or "").strip() or None
        if not _CASE_ID_RE.fullmatch(self.case_id):
            raise ValueError("评测用例 ID 格式无效")
        if not self.user_input:
            raise ValueError("请填写用户会怎么问")
        messages = [
            *self.prior_messages,
            EvaluationMessageBody(role="user", content=self.user_input),
        ]
        if len(messages) > EVALUATION_MESSAGES_MAX:
            raise ValueError("单个用例最多包含 20 条对话")
        if (
            sum(_utf8_size(item.content) for item in messages)
            > EVALUATION_MESSAGE_TEXT_MAX_BYTES
        ):
            raise ValueError("单个用例的对话文本不能超过 32 KiB")
        if (
            self.expected_outcome is not None
            and _utf8_size(self.expected_outcome) > EVALUATION_REFERENCE_MAX_BYTES
        ):
            raise ValueError("期望结果不能超过 16 KiB")
        if len(self.criteria) > EVALUATION_CRITERIA_MAX:
            raise ValueError("单个用例最多包含 20 条评测标准")
        normalized_criteria: list[str] = []
        seen: set[str] = set()
        for criterion in self.criteria:
            normalized = criterion.strip()
            if not normalized:
                raise ValueError("评测标准不能为空")
            if _utf8_size(normalized) > EVALUATION_CRITERION_MAX_BYTES:
                raise ValueError("单条评测标准不能超过 2 KiB")
            if normalized not in seen:
                seen.add(normalized)
                normalized_criteria.append(normalized)
        self.criteria = normalized_criteria
        return self

    def canonical(self) -> dict[str, object]:
        messages = [item.model_dump(mode="json") for item in self.prior_messages]
        messages.append({"role": "user", "content": self.user_input})
        return {
            "case_id": self.case_id,
            "messages": messages,
            "reference_output": self.expected_outcome,
            "criteria": self.criteria,
        }


class EvaluationDatasetBody(BaseModel):
    cases: list[EvaluationCaseBody] = Field(
        min_length=1,
        max_length=EVALUATION_CASES_MAX,
    )

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def validate_unique_ids(self) -> EvaluationDatasetBody:
        identifiers = [item.case_id for item in self.cases]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("评测用例 ID 不能重复")
        return self


class ResumeEvaluationBody(BaseModel):
    environment: dict[str, str] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def validate_environment(self) -> ResumeEvaluationBody:
        normalized: dict[str, str] = {}
        for key, value in self.environment.items():
            name = key.strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError("环境变量名称格式无效")
            if not isinstance(value, str) or not value or "\x00" in value:
                raise ValueError("环境变量值不能为空或包含 NUL")
            if _utf8_size(value) > 64 * 1024:
                raise ValueError("单个环境变量值不能超过 64 KiB")
            normalized[name] = value
        self.environment = normalized
        return self


__all__ = [
    "EVALUATION_CASES_MAX",
    "EVALUATION_CRITERIA_MAX",
    "EVALUATION_CRITERION_MAX_BYTES",
    "EVALUATION_DATASET_MAX_BYTES",
    "EVALUATION_MESSAGES_MAX",
    "EVALUATION_MESSAGE_TEXT_MAX_BYTES",
    "EVALUATION_OUTPUT_MAX_BYTES",
    "EVALUATION_REFERENCE_MAX_BYTES",
    "EvaluationCaseBody",
    "EvaluationDatasetBody",
    "EvaluationMessageBody",
    "MigrationEvaluationConfig",
    "ResumeEvaluationBody",
]
