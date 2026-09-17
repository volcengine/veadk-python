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

"""Read the mount fields missing from older AgentKit SDK response models"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .service import RuntimeArtifactError


class _MountPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bucket_name: str = Field(default="", alias="BucketName")
    bucket_path: str = Field(default="/", alias="BucketPath")
    local_mount_path: str = Field(default="", alias="LocalMountPath")


class _TosMountConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enable_tos: bool = Field(default=False, alias="EnableTos")
    mount_points: list[_MountPoint] = Field(default_factory=list, alias="MountPoints")


class _RuntimeTag(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(alias="Key")
    value: str = Field(default="", alias="Value")


class _RuntimeMountResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Intentionally excludes credentials, authorizers and environment variables
    tos_mount_config: _TosMountConfig | None = Field(
        default=None, alias="TosMountConfig"
    )
    tags: list[_RuntimeTag] | None = Field(default=None, alias="Tags", exclude=True)


def read_runtime_artifact_detail(
    client: Any,
    runtime_id: str,
    *,
    authorize_tags: Callable[[dict[str, str]], None] | None = None,
) -> dict[str, Any]:
    from agentkit.sdk.runtime.types import GetRuntimeRequest

    try:
        response = client._invoke_api(
            api_action="GetRuntime",
            request=GetRuntimeRequest.model_validate({"RuntimeId": runtime_id}),
            response_type=_RuntimeMountResponse,
        )
    except ValidationError:
        # Validation errors can echo the invalid input, including mount credentials
        raise RuntimeArtifactError(
            "Runtime 产物挂载配置无效，请检查挂载设置", 502
        ) from None
    if authorize_tags is not None:
        authorize_tags({tag.key: tag.value for tag in response.tags or []})
    return response.model_dump(by_alias=True)
