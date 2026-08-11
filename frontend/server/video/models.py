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

"""Request, response, and internal models for Studio video creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SEEDANCE_MIN_DURATION_SECONDS = 4
SEEDANCE_MAX_DURATION_SECONDS = 30
SEEDANCE_EDITING_DURATION = -1

VideoTaskMode = Literal[
    "auto",
    "text_to_video",
    "reference_to_video",
    "video_editing",
    "video_extension",
    "first_last_frame",
]
ResolvedVideoTaskMode = Literal[
    "text_to_video",
    "reference_to_video",
    "video_editing",
    "video_extension",
    "first_last_frame",
]
VideoAssetRole = Literal[
    "reference_image",
    "reference_video",
    "first_frame",
    "last_frame",
]
VideoTaskStatus = Literal["queued", "running", "succeeded", "failed"]
VideoOutputFormat = Literal["mp4", "mov"]


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class VideoCapabilities(ApiModel):
    provider: Literal["volcengine", "byteplus"]
    generation_model: str
    enhancer_model: str
    asset_storage_available: bool
    asset_storage_unavailable_reason: str
    max_asset_bytes: int
    supported_modes: list[ResolvedVideoTaskMode]


class VideoAssetResponse(ApiModel):
    asset_id: str
    role: VideoAssetRole
    file_name: str
    mime_type: str
    size_bytes: int
    preview_url: str


class PromptEnhanceRequest(ApiModel):
    prompt: str = Field(min_length=1, max_length=12_000)
    task_mode: VideoTaskMode = "auto"
    asset_ids: list[str] = Field(default_factory=list, max_length=8)
    ratio: str = Field(default="16:9", min_length=3, max_length=16)
    resolution: str = Field(default="720p", min_length=3, max_length=16)
    duration_seconds: int = Field(
        default=8,
        ge=SEEDANCE_MIN_DURATION_SECONDS,
        le=SEEDANCE_MAX_DURATION_SECONDS,
    )


class PromptEnhanceResponse(ApiModel):
    resolved_task_mode: ResolvedVideoTaskMode
    enhanced_prompt: str
    enhancer_model: str
    ratio: str
    resolution: str
    duration_seconds: int


class VideoTaskCreateRequest(ApiModel):
    enhanced_prompt: str = Field(min_length=1, max_length=24_000)
    resolved_task_mode: ResolvedVideoTaskMode
    asset_ids: list[str] = Field(default_factory=list, max_length=8)
    ratio: str = Field(default="16:9", min_length=3, max_length=16)
    resolution: str = Field(default="720p", min_length=3, max_length=16)
    duration_seconds: int = Field(
        default=8,
        ge=SEEDANCE_EDITING_DURATION,
        le=SEEDANCE_MAX_DURATION_SECONDS,
    )

    @model_validator(mode="after")
    def validate_duration_seconds(self) -> VideoTaskCreateRequest:
        duration = self.duration_seconds
        if duration == SEEDANCE_EDITING_DURATION:
            if self.resolved_task_mode != "video_editing":
                raise ValueError("durationSeconds=-1 is only valid for video editing")
            return self
        if duration < SEEDANCE_MIN_DURATION_SECONDS:
            raise ValueError("durationSeconds must be between 4 and 30")
        return self


class VideoTaskResponse(ApiModel):
    task_id: str
    status: VideoTaskStatus
    task_mode: ResolvedVideoTaskMode
    generation_model: str
    enhanced_prompt: str
    output_format: VideoOutputFormat
    video_url: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class VideoProviderConfig:
    provider: Literal["volcengine", "byteplus"]
    region: str
    api_base: str
    generation_model: str
    enhancer_model: str


@dataclass
class VideoTaskRecord:
    task_id: str
    owner_id: str
    task_mode: ResolvedVideoTaskMode
    generation_model: str
    enhanced_prompt: str
    output_format: VideoOutputFormat
    status: VideoTaskStatus = "queued"
    video_url: str | None = None
    error: str | None = None
