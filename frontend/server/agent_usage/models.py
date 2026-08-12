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

"""Validated contracts for Studio agent usage statistics."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentUsageEvent(BaseModel):
    """One successful Studio invocation persisted as an immutable object."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    invocation_id: str = Field(alias="invocationId", min_length=1, max_length=512)
    runtime_id: str = Field(alias="runtimeId", min_length=1, max_length=512)
    app_name: str = Field(alias="appName", min_length=1, max_length=512)
    user_id: str = Field(alias="userId", min_length=1, max_length=1024)
    display_name: str = Field(default="", alias="displayName", max_length=1024)
    used_at: datetime = Field(alias="usedAt")


class AgentUsageUser(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    user_id: str = Field(alias="userId")
    display_name: str = Field(alias="displayName")
    invocation_count: int = Field(alias="invocationCount", ge=1)
    last_used_at: datetime = Field(alias="lastUsedAt")


class AgentUsageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    runtime_id: str = Field(alias="runtimeId")
    app_name: str = Field(alias="appName")
    total_invocations: int = Field(alias="totalInvocations", ge=0)
    total_users: int = Field(alias="totalUsers", ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(alias="pageSize", ge=1)
    total_pages: int = Field(alias="totalPages", ge=0)
    users: list[AgentUsageUser]
