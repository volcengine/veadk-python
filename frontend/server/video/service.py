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

"""Business rules and orchestration for Studio video creation."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from veadk.utils.logger import get_logger

from .client import ArkPromptClient, ArkServiceError, ArkVideoClient
from .models import (
    PromptEnhanceRequest,
    PromptEnhanceResponse,
    ResolvedVideoTaskMode,
    VideoAssetResponse,
    VideoAssetRole,
    VideoCapabilities,
    VideoProviderConfig,
    VideoTaskCreateRequest,
    VideoTaskRecord,
    VideoTaskResponse,
)
from .storage import LazyVideoAssetRepository, StoredVideoAsset

logger = get_logger(__name__)

_REDACTED = "[REDACTED]"
_SENSITIVE_ERROR_KEYS = {
    "access_key",
    "access_token",
    "apikey",
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "id_token",
    "password",
    "refresh_token",
    "secret_key",
    "session_token",
    "set_cookie",
    "signature",
    "token",
}
_BEARER_SECRET = re.compile(r"(?i)\bBearer\s+[^\s,;\"']+")
_JWT_SECRET = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|"
    r"session[_-]?token|refresh[_-]?token|access[_-]?token|password|signature)"
    r"\s*[:=]\s*[^\s,;]+"
)
_SIGNED_URL_QUERY = re.compile(r"(https?://[^\s?\"'<>]+)\?[^\s\"'<>]+")


def _provider_error_text(result: dict[str, Any]) -> str:
    """Preserve the provider error payload while removing credential material."""

    error = result.get("error")
    if error in (None, "", {}, []):
        return "视频生成失败，请调整提示词或素材后重试。"
    safe_error = _redact_provider_error(error)
    if isinstance(safe_error, str):
        return safe_error
    return json.dumps(safe_error, ensure_ascii=False, indent=2)


def _redact_provider_error(value: Any, *, key: str = "") -> Any:
    normalized_key = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    if normalized_key in _SENSITIVE_ERROR_KEYS or normalized_key.endswith(
        ("_api_key", "_password", "_secret", "_signature", "_token")
    ):
        return _REDACTED
    if isinstance(value, dict):
        return {
            str(child_key): _redact_provider_error(child_value, key=str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_provider_error(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_provider_error(item) for item in value]
    if not isinstance(value, str):
        return value
    redacted = _BEARER_SECRET.sub("Bearer [REDACTED]", value)
    redacted = _JWT_SECRET.sub(_REDACTED, redacted)
    redacted = _SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}={_REDACTED}",
        redacted,
    )
    return _SIGNED_URL_QUERY.sub(r"\1?[REDACTED]", redacted)


class VideoTaskNotFound(RuntimeError):
    pass


class VideoTaskAccessDenied(RuntimeError):
    pass


class VideoInputError(RuntimeError):
    pass


class VideoService:
    def __init__(
        self,
        *,
        config: VideoProviderConfig,
        prompt_client: ArkPromptClient,
        video_client: ArkVideoClient,
        assets: LazyVideoAssetRepository,
        max_asset_bytes: int,
    ) -> None:
        self.config = config
        self.prompt_client = prompt_client
        self.video_client = video_client
        self.assets = assets
        self.max_asset_bytes = max_asset_bytes
        self._tasks: dict[str, VideoTaskRecord] = {}
        self._task_lock = asyncio.Lock()

    def capabilities(self) -> VideoCapabilities:
        return VideoCapabilities(
            provider=self.config.provider,
            generation_model=self.config.generation_model,
            enhancer_model=self.config.enhancer_model,
            asset_storage_available=self.assets.configured,
            asset_storage_unavailable_reason=self.assets.unavailable_reason,
            max_asset_bytes=self.max_asset_bytes,
            supported_modes=[
                "text_to_video",
                "reference_to_video",
                "video_editing",
                "video_extension",
                "first_last_frame",
            ],
        )

    async def upload_asset(
        self,
        *,
        owner_id: str,
        role: VideoAssetRole,
        file_name: str,
        declared_mime_type: str,
        source: Path,
    ) -> VideoAssetResponse:
        repository = await self.assets.get()
        return await repository.save(
            owner_id=owner_id,
            role=role,
            file_name=file_name,
            declared_mime_type=declared_mime_type,
            source=source,
        )

    async def enhance_prompt(
        self,
        owner_id: str,
        request: PromptEnhanceRequest,
    ) -> PromptEnhanceResponse:
        from .prompts import (
            PromptValidationError,
            apply_parameter_policy,
            build_enhancement_input,
            build_enhancement_messages,
            parse_enhancement_output,
        )

        assets = await self._load_assets(owner_id, request.asset_ids)
        roles = [asset.role for asset in assets]
        input_data = build_enhancement_input(
            request.prompt.strip(),
            selected_task_mode=request.task_mode,
            has_video="reference_video" in roles,
            has_image="reference_image" in roles,
            has_first_frame="first_frame" in roles,
            has_last_frame="last_frame" in roles,
            video_count=roles.count("reference_video"),
            image_count=roles.count("reference_image"),
            selected_ratio=request.ratio,
            selected_resolution=request.resolution,
            selected_duration=request.duration_seconds,
        )
        try:
            raw_output = await self.prompt_client.enhance(
                build_enhancement_messages(input_data)
            )
            enhanced = parse_enhancement_output(
                raw_output,
                selected_task_mode=request.task_mode,
            )
            task_mode = enhanced["task_type"]
            prompt = enhanced["enhanced_prompt"]
            self._validate_asset_mapping(enhanced["asset_mapping"], assets)
            self._validate_assets(task_mode, assets)
            policy = apply_parameter_policy(
                task_mode,
                ratio=request.ratio,
                resolution=request.resolution,
                duration=request.duration_seconds,
            )
        except PromptValidationError as error:
            logger.warning("Prompt enhancer contract validation failed: %s", error)
            raise ArkServiceError(
                "提示词增强结果不符合视频任务约束，请重试。"
            ) from error
        return PromptEnhanceResponse(
            resolved_task_mode=task_mode,
            enhanced_prompt=prompt,
            enhancer_model=self.config.enhancer_model,
            ratio=str(policy["ratio"]),
            resolution=str(policy["resolution"]),
            duration_seconds=int(policy["duration"]),
        )

    async def create_task(
        self,
        owner_id: str,
        request: VideoTaskCreateRequest,
    ) -> VideoTaskResponse:
        assets = await self._load_assets(owner_id, request.asset_ids)
        self._validate_assets(request.resolved_task_mode, assets)
        from .prompts import apply_parameter_policy

        # Locked modes may round-trip their resolved sentinel values from the
        # enhancement response. Convert those to harmless user-control defaults,
        # then recompute the canonical policy server-side instead of trusting the
        # browser to submit the final Seedance parameters.
        selected_ratio = "16:9" if request.ratio == "adaptive" else request.ratio
        selected_duration = (
            8 if request.duration_seconds == -1 else request.duration_seconds
        )
        try:
            policy = apply_parameter_policy(
                request.resolved_task_mode,
                ratio=selected_ratio,
                resolution=request.resolution,
                duration=selected_duration,
            )
        except ValueError as error:
            raise VideoInputError(str(error)) from error
        content: list[dict[str, Any]] = [
            {"type": "text", "text": request.enhanced_prompt.strip()}
        ]
        repository = await self.assets.get() if assets else None
        for asset in assets:
            assert repository is not None
            url = await repository.signed_url(owner_id, asset.record.ref.media_id)
            content.append(self._asset_content(asset.role, url))
        body = {
            "model": self.config.generation_model,
            "content": content,
            "ratio": policy["ratio"],
            "resolution": policy["resolution"],
            "duration": policy["duration"],
            "output_format": policy["output_format"],
            "generate_audio": policy["generate_audio"],
        }
        result = await self.video_client.create_task(body)
        task_id = str(result["id"])
        record = VideoTaskRecord(
            task_id=task_id,
            owner_id=owner_id,
            task_mode=request.resolved_task_mode,
            generation_model=self.config.generation_model,
            enhanced_prompt=request.enhanced_prompt.strip(),
            output_format=policy["output_format"],
            status="queued",
        )
        async with self._task_lock:
            self._tasks[task_id] = record
        return self._task_response(record)

    async def get_task(self, owner_id: str, task_id: str) -> VideoTaskResponse:
        record = await self._owned_task(owner_id, task_id)
        result = await self.video_client.get_task(task_id)
        raw_status = str(result.get("status") or "").lower()
        if raw_status in {"queued", "pending", "created"}:
            record.status = "queued"
        elif raw_status in {"running", "processing"}:
            record.status = "running"
        elif raw_status in {"succeeded", "success", "completed"}:
            record.status = "succeeded"
            content = result.get("content")
            video_url = content.get("video_url") if isinstance(content, dict) else None
            if not isinstance(video_url, str) or not video_url.startswith("https://"):
                raise ArkServiceError("视频任务已完成，但没有返回有效的下载地址。")
            record.video_url = video_url
            record.error = None
        elif raw_status in {"failed", "error", "cancelled", "canceled"}:
            record.status = "failed"
            record.video_url = None
            record.error = _provider_error_text(result)
        elif raw_status == "expired":
            record.status = "failed"
            record.video_url = None
            record.error = "视频任务已过期，请重新发起生成。"
        else:
            raise ArkServiceError("视频生成服务返回了未知的任务状态。")
        return self._task_response(record)

    async def open_download(self, owner_id: str, task_id: str):
        record = await self._owned_task(owner_id, task_id)
        if record.status != "succeeded" or not record.video_url:
            raise VideoInputError("视频尚未生成完成。")
        response = await self.video_client.open_download(record.video_url)
        return response, record.output_format

    async def _owned_task(self, owner_id: str, task_id: str) -> VideoTaskRecord:
        async with self._task_lock:
            record = self._tasks.get(task_id)
        if record is None:
            raise VideoTaskNotFound("视频任务不存在或已过期。")
        if record.owner_id != owner_id:
            raise VideoTaskAccessDenied("无权访问该视频任务。")
        return record

    async def _load_assets(
        self, owner_id: str, asset_ids: list[str]
    ) -> list[StoredVideoAsset]:
        if not asset_ids:
            return []
        if len(set(asset_ids)) != len(asset_ids):
            raise VideoInputError("视频素材不能重复。")
        repository = await self.assets.get()
        return [await repository.get(owner_id, asset_id) for asset_id in asset_ids]

    @staticmethod
    def _validate_assets(
        task_mode: ResolvedVideoTaskMode,
        assets: list[StoredVideoAsset],
    ) -> None:
        counts = Counter(asset.role for asset in assets)
        allowed_roles = {
            "text_to_video": set(),
            "reference_to_video": {"reference_image", "reference_video"},
            "video_editing": {"reference_image", "reference_video"},
            "video_extension": {"reference_image", "reference_video"},
            "first_last_frame": {"first_frame", "last_frame"},
        }[task_mode]
        unexpected = set(counts) - allowed_roles
        if unexpected:
            raise VideoInputError(
                f"该任务模式不支持素材角色：{', '.join(sorted(unexpected))}。"
            )
        if any(count > 1 for count in counts.values()):
            raise VideoInputError("每个素材位置最多上传一个文件。")
        if task_mode == "text_to_video" and assets:
            raise VideoInputError("文生视频模式不接受参考素材。")
        if task_mode == "reference_to_video" and not assets:
            raise VideoInputError("参考素材生视频至少需要一个参考素材。")
        if task_mode in {"video_editing", "video_extension"} and (
            counts["reference_video"] != 1
        ):
            raise VideoInputError("该任务模式需要且只能上传一个参考视频。")
        if task_mode == "first_last_frame" and counts["first_frame"] != 1:
            raise VideoInputError("首尾帧生成需要且只能上传一张首帧图片。")

    @staticmethod
    def _validate_asset_mapping(
        model_assets: list[dict[str, Any]],
        assets: list[StoredVideoAsset],
    ) -> None:
        expected = Counter(asset.role for asset in assets)
        actual = Counter(str(asset.get("role") or "") for asset in model_assets)
        if actual != expected:
            raise ArkServiceError("提示词增强结果与已上传素材不一致，请重试。")

    @staticmethod
    def _asset_content(role: VideoAssetRole, url: str) -> dict[str, Any]:
        if role == "reference_video":
            return {
                "type": "video_url",
                "video_url": {"url": url},
                "role": role,
            }
        return {
            "type": "image_url",
            "image_url": {"url": url},
            "role": role,
        }

    @staticmethod
    def _task_response(record: VideoTaskRecord) -> VideoTaskResponse:
        return VideoTaskResponse(
            task_id=record.task_id,
            status=record.status,
            task_mode=record.task_mode,
            generation_model=record.generation_model,
            enhanced_prompt=record.enhanced_prompt,
            output_format=record.output_format,
            video_url=record.video_url,
            error=record.error,
        )


__all__ = [
    "VideoInputError",
    "VideoService",
    "VideoTaskAccessDenied",
    "VideoTaskNotFound",
]
