# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Public response models for the Studio model catalog."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class ModelOption(ApiModel):
    id: str
    name: str
    display_name: str
    vendor_name: str
    activation_state: str
    lifecycle_status: str
    available: bool
    api_key_allowed: bool | None = None


class ModelApiKeyModelAccess(ApiModel):
    effect: Literal["allow", "deny"]
    all_models: bool
    model_ids: list[str]


class ModelApiKeyOption(ApiModel):
    id: str
    name: str
    status: str | None = None
    allow_all: bool | None = None
    model_access: ModelApiKeyModelAccess | None = Field(default=None, exclude=True)


class ModelApiKeysResponse(ApiModel):
    provider: Literal["volcengine", "byteplus"]
    keys: list[ModelApiKeyOption]
    default_key_id: str | None = None


class ModelApiKeyValueResponse(ApiModel):
    value: str


ModelPermissionState = Literal[
    "Available", "Shutdown", "VideoGeneration", "Unsupported", "NotActivated", "Unknown"
]


class ModelApiKeyModelPermission(ApiModel):
    name: str
    state: ModelPermissionState
    model_id: str | None = None


class ModelOptionsResponse(ApiModel):
    provider: Literal["volcengine", "byteplus"]
    selected_api_key_id: str | None = None
    models: list[ModelOption]
    api_key_model_permissions: list[ModelApiKeyModelPermission] | None = None
    model_permission_catalog: dict[str, ModelApiKeyModelPermission] = Field(
        default_factory=dict, exclude=True
    )


__all__ = [
    "ModelApiKeyOption",
    "ModelApiKeyValueResponse",
    "ModelApiKeysResponse",
    "ModelOption",
    "ModelOptionsResponse",
]
