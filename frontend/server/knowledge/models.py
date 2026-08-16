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

"""HTTP models for the Studio AgentKit knowledge library."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        # Ownership is resolved from the authenticated request. Silently discard
        # legacy client owner fields instead of ever treating them as authority.
        extra="ignore",
    )


class CreateKnowledgeBaseBody(ApiModel):
    name: str = Field(
        min_length=1,
        max_length=48,
        pattern=r"^[A-Za-z][A-Za-z0-9_]*$",
    )
    description: str = Field(default="", max_length=80)
    region: str | None = Field(default=None, max_length=64)


class UpdateKnowledgeBaseBody(ApiModel):
    description: str = Field(max_length=80)


class CreateDocumentBody(ApiModel):
    source_type: Literal["url", "tos"]
    name: str | None = Field(default=None, max_length=256)
    document_type: str | None = Field(default=None, max_length=64)
    url: str | None = Field(default=None, max_length=4_096)
    tos_path: str | None = Field(default=None, max_length=4_096)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source(self) -> CreateDocumentBody:
        if self.source_type == "url" and not (self.url or "").strip():
            raise ValueError("url is required when sourceType is url")
        if self.source_type == "tos" and not (self.tos_path or "").strip():
            raise ValueError("tosPath is required when sourceType is tos")
        return self


class UpdateDocumentBody(ApiModel):
    metadata: dict[str, Any]


class KnowledgeItemResponse(ApiModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: str
    name: str
    description: str
    provider_type: str
    provider_knowledge_id: str
    project_name: str
    region: str
    status: str
    created_at: str
    updated_at: str
    owner_id: str
    owner_label: str
    can_manage: bool


class KnowledgeListResponse(ApiModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    items: list[KnowledgeItemResponse]
    next_token: str = ""


__all__ = [
    "CreateDocumentBody",
    "CreateKnowledgeBaseBody",
    "KnowledgeItemResponse",
    "KnowledgeListResponse",
    "UpdateDocumentBody",
    "UpdateKnowledgeBaseBody",
]
