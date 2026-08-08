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

"""Validated contracts for Studio Skill management."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field, model_validator


@dataclass(frozen=True)
class SkillIdentity:
    """Trusted identity used for filtering, never as an ownership boundary."""

    author: str
    is_admin: bool = False


class CreateSkillSpaceBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    region: str = Field(min_length=1, max_length=64)
    project_name: str | None = Field(default=None, alias="projectName", max_length=256)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def normalize(self) -> CreateSkillSpaceBody:
        self.name = self.name.strip()
        self.description = (self.description or "").strip() or None
        self.region = self.region.strip()
        self.project_name = (self.project_name or "").strip() or None
        if not self.name:
            raise ValueError("Skill 空间名称不能为空")
        return self


class UpdateSkillSpaceBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    region: str = Field(min_length=1, max_length=64)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def normalize(self) -> UpdateSkillSpaceBody:
        self.name = self.name.strip()
        self.description = (self.description or "").strip() or None
        self.region = self.region.strip()
        if not self.name:
            raise ValueError("Skill 空间名称不能为空")
        return self


class UploadSkillQuery(BaseModel):
    region: str = Field(min_length=1, max_length=64)
    project_name: str | None = Field(default=None, alias="projectName", max_length=256)

    model_config = {"populate_by_name": True, "extra": "forbid"}
