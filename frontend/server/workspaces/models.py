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

"""Validated contracts for Studio workspaces."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkspaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    environment_ids: list[str] = Field(
        default_factory=list, alias="environmentIds", max_length=100
    )

    @model_validator(mode="after")
    def normalize(self) -> WorkspaceInput:
        self.name = self.name.strip()
        self.description = self.description.strip()
        if not self.name:
            raise ValueError("工作区名称不能为空。")
        self.environment_ids = list(
            dict.fromkeys(item.strip() for item in self.environment_ids if item.strip())
        )
        return self


class WorkspacePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    environment_ids: list[str] | None = Field(
        default=None, alias="environmentIds", max_length=100
    )

    @model_validator(mode="after")
    def normalize(self) -> WorkspacePatch:
        if not self.model_fields_set:
            raise ValueError("至少需要更新一个工作区字段。")
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("工作区名称不能为空。")
        if self.description is not None:
            self.description = self.description.strip()
        if self.environment_ids is not None:
            self.environment_ids = list(
                dict.fromkeys(
                    item.strip() for item in self.environment_ids if item.strip()
                )
            )
        return self


class WorkspaceRecord(WorkspaceInput):
    id: str = Field(min_length=32, max_length=32)
    owner_id: str = Field(alias="ownerId", min_length=1, max_length=1024)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


__all__ = ["WorkspaceInput", "WorkspacePatch", "WorkspaceRecord"]
