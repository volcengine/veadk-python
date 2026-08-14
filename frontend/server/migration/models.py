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

"""Validated request contracts for Studio project migration."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MigrationFramework = Literal[
    "langchain",
    "langgraph",
    "adk",
    "strands",
    "agentcore",
    "dify",
    "any",
]

MIGRATION_FRAMEWORKS: tuple[MigrationFramework, ...] = (
    "langchain",
    "langgraph",
    "adk",
    "strands",
    "agentcore",
    "dify",
    "any",
)
STRUCTURED_MIGRATION_FRAMEWORKS: frozenset[str] = frozenset(
    {"langchain", "langgraph", "adk", "strands", "agentcore"}
)
_SOURCE_FILE_NAME_RE = re.compile(r"^[^/\\\x00-\x1f]{1,255}\.zip$", re.IGNORECASE)
_APP_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_TASK_ID_RE = re.compile(r"^migration-v1-[0-9a-f]{32}$")
STRUCTURED_ENTRY_PATTERN = (
    r"^[A-Za-z0-9_./-]+\.(?:py|json)(?::[A-Za-z_][A-Za-z0-9_]*)?$"
)
_ENTRY_RE = re.compile(STRUCTURED_ENTRY_PATTERN)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def is_valid_structured_entry(value: object) -> bool:
    if not isinstance(value, str) or not _ENTRY_RE.fullmatch(value):
        return False
    path_value = value.split(":", 1)[0]
    path = PurePosixPath(path_value)
    return (
        not path.is_absolute()
        and "." not in path.parts
        and ".." not in path.parts
        and path.as_posix() == path_value
    )


class CreateMigrationTaskBody(BaseModel):
    task_id: str | None = Field(default=None, alias="taskId", max_length=45)
    source_file_name: str = Field(alias="sourceFileName", min_length=1, max_length=255)
    instruction: str = Field(default="", max_length=20_000)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def normalize(self) -> CreateMigrationTaskBody:
        self.task_id = (self.task_id or "").strip() or None
        self.source_file_name = self.source_file_name.strip()
        self.instruction = self.instruction.strip()
        if self.task_id is not None and not _TASK_ID_RE.fullmatch(self.task_id):
            raise ValueError("迁移会话 ID 无效")
        if not _SOURCE_FILE_NAME_RE.fullmatch(self.source_file_name):
            raise ValueError("请选择名称有效的 ZIP 文件")
        return self


class ConfirmMigrationBody(BaseModel):
    framework: MigrationFramework
    entry: str | None = Field(default=None, max_length=512)
    app_name: str = Field(alias="appName", min_length=1, max_length=63)
    instruction: str = Field(default="", max_length=20_000)
    analysis_attempt: int = Field(alias="analysisAttempt", ge=1)
    analysis_sha256: str = Field(alias="analysisSha256", min_length=64, max_length=64)
    input_sha256: str = Field(alias="inputSha256", min_length=64, max_length=64)
    boundary_confirmed: bool = Field(alias="boundaryConfirmed")

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def normalize(self) -> ConfirmMigrationBody:
        self.entry = (self.entry or "").strip() or None
        self.app_name = self.app_name.strip()
        self.instruction = self.instruction.strip()
        self.analysis_sha256 = self.analysis_sha256.strip()
        self.input_sha256 = self.input_sha256.strip()
        if not _SHA256_RE.fullmatch(self.analysis_sha256) or not _SHA256_RE.fullmatch(
            self.input_sha256
        ):
            raise ValueError("迁移确认引用无效")
        if self.boundary_confirmed is not True:
            raise ValueError("请先确认迁移边界")
        if not _APP_NAME_RE.fullmatch(self.app_name):
            raise ValueError(
                "Agent 名称必须为 1-63 位，只能包含小写字母、数字和连字符，"
                "且必须以字母或数字开头和结尾"
            )
        if self.framework in STRUCTURED_MIGRATION_FRAMEWORKS:
            if not is_valid_structured_entry(self.entry):
                raise ValueError("Structured 迁移必须确认有效的项目入口")
        elif self.entry is not None:
            raise ValueError("Dify/Any 迁移不接受 Structured 项目入口")
        return self


class SubmitAnalysisAnswersBody(BaseModel):
    analysis_attempt: int = Field(alias="analysisAttempt", ge=1)
    analysis_sha256: str = Field(alias="analysisSha256", min_length=64, max_length=64)
    input_sha256: str = Field(alias="inputSha256", min_length=64, max_length=64)
    answers: dict[str, str]

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def normalize(self) -> SubmitAnalysisAnswersBody:
        self.analysis_sha256 = self.analysis_sha256.strip()
        self.input_sha256 = self.input_sha256.strip()
        if not _SHA256_RE.fullmatch(self.analysis_sha256) or not _SHA256_RE.fullmatch(
            self.input_sha256
        ):
            raise ValueError("分析结果引用无效")
        if len(self.answers) > 50:
            raise ValueError("待确认问题不能超过 50 个")
        normalized_answers: dict[str, str] = {}
        for key, value in self.answers.items():
            normalized_key = key.strip()
            normalized_value = value.strip()
            if not normalized_key or len(normalized_key) > 128:
                raise ValueError("待确认问题 ID 无效")
            if len(normalized_value) > 4_000:
                raise ValueError("单个确认答案不能超过 4000 个字符")
            normalized_answers[normalized_key] = normalized_value
        self.answers = normalized_answers
        return self


__all__ = [
    "MIGRATION_FRAMEWORKS",
    "STRUCTURED_ENTRY_PATTERN",
    "STRUCTURED_MIGRATION_FRAMEWORKS",
    "ConfirmMigrationBody",
    "CreateMigrationTaskBody",
    "MigrationFramework",
    "SubmitAnalysisAnswersBody",
    "is_valid_structured_entry",
]
