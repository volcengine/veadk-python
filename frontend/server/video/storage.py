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

"""Private, provider-accessible storage for video reference assets."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from frontend.server.storage import (
    STUDIO_STORAGE_ROOT_PREFIX,
    STUDIO_STORAGE_UNAVAILABLE_REASON,
    StudioStorageConfig,
    StudioTosMediaStorage,
)
from frontend.server.storage.tos import create_tos_client_factory
from veadk.multimodal.models import MediaRecord, MediaRef
from veadk.multimodal.service import MediaService

from .models import VideoAssetResponse, VideoAssetRole

CredentialResolver = Callable[[], tuple[str, str, str | None]]

_MIN_REFERENCE_VIDEO_PIXELS = 409_600


class VideoAssetError(RuntimeError):
    pass


class VideoAssetStorageUnavailable(VideoAssetError):
    pass


class VideoAssetNotFound(VideoAssetError):
    pass


@dataclass(frozen=True)
class StoredVideoAsset:
    owner_id: str
    role: VideoAssetRole
    record: MediaRecord


class VideoAssetRepository:
    """Keep ownership metadata while bytes remain in private TOS storage."""

    def __init__(self, media_service: MediaService) -> None:
        self._media_service = media_service

    @property
    def max_file_bytes(self) -> int:
        return self._media_service.max_file_bytes

    async def save(
        self,
        *,
        owner_id: str,
        role: VideoAssetRole,
        file_name: str,
        declared_mime_type: str,
        source: Path,
    ) -> VideoAssetResponse:
        if role == "reference_video":
            width, height = await asyncio.to_thread(
                _probe_video_dimensions,
                source,
            )
            if width * height < _MIN_REFERENCE_VIDEO_PIXELS:
                raise ValueError(
                    f"参考视频分辨率过低（{width}×{height}）。"
                    "Seedance 2.5 要求参考视频至少包含 409600 个像素，"
                    "例如 854×480。"
                )
        try:
            record = await self._media_service.save_file(
                app_name="video",
                user_id=owner_id,
                session_id=role,
                file_name=file_name,
                declared_mime_type=declared_mime_type,
                source=source,
            )
        except ValueError:
            raise
        except Exception as error:
            raise VideoAssetStorageUnavailable(
                "参考素材上传失败，请稍后重试或联系管理员检查 TOS 配置。"
            ) from error
        try:
            self._validate_role_mime(role, record.mime_type)
            preview_url = await self._media_service.storage.signed_url(record.ref)
            if not preview_url or not preview_url.startswith("https://"):
                raise VideoAssetStorageUnavailable(
                    "视频素材存储未提供可供生成模型访问的安全地址。"
                )
        except Exception:
            await self._media_service.storage.delete(record.ref)
            raise
        return VideoAssetResponse(
            asset_id=record.ref.media_id,
            role=role,
            file_name=record.file_name,
            mime_type=record.mime_type,
            size_bytes=record.size_bytes,
            preview_url=preview_url,
        )

    async def get(self, owner_id: str, asset_id: str) -> StoredVideoAsset:
        for role in (
            "reference_image",
            "reference_video",
            "first_frame",
            "last_frame",
        ):
            ref = MediaRef(
                app_name="video",
                user_id=owner_id,
                session_id=role,
                media_id=asset_id,
            )
            record = await self._media_service.storage.get_record(ref)
            if record is not None:
                return StoredVideoAsset(owner_id, role, record)
        raise VideoAssetNotFound("视频素材不存在或已过期。")

    async def signed_url(self, owner_id: str, asset_id: str) -> str:
        asset = await self.get(owner_id, asset_id)
        url = await self._media_service.storage.signed_url(asset.record.ref)
        if not url or not url.startswith("https://"):
            raise VideoAssetStorageUnavailable(
                "视频素材存储未提供可供生成模型访问的安全地址。"
            )
        return url

    @staticmethod
    def _validate_role_mime(role: VideoAssetRole, mime_type: str) -> None:
        expected_prefix = "video/" if role == "reference_video" else "image/"
        if not mime_type.startswith(expected_prefix):
            expected = "视频" if expected_prefix == "video/" else "图片"
            raise ValueError(f"该素材位置只支持{expected}文件。")


def _probe_video_dimensions(source: Path) -> tuple[int, int]:
    """Read the first video stream dimensions without decoding the upload."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(source),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as error:
        raise VideoAssetStorageUnavailable(
            "当前环境无法校验参考视频规格，请联系管理员安装 ffprobe。"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise ValueError("参考视频解析超时，请压缩视频后重试。") from error

    if result.returncode != 0:
        raise ValueError("无法读取参考视频分辨率，请上传有效的 MP4、MOV 或 WebM 视频。")
    try:
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(
            "无法读取参考视频分辨率，请上传包含画面的视频文件。"
        ) from error
    if width <= 0 or height <= 0:
        raise ValueError("无法读取参考视频分辨率，请上传包含画面的视频文件。")
    return width, height


class LazyVideoAssetRepository:
    """Delay TOS credential resolution until a user actually uploads a file."""

    def __init__(self, factory: Callable[[], VideoAssetRepository] | None) -> None:
        self._factory = factory
        self._repository: VideoAssetRepository | None = None
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return self._factory is not None

    @property
    def unavailable_reason(self) -> str:
        return "" if self.configured else STUDIO_STORAGE_UNAVAILABLE_REASON

    async def get(self) -> VideoAssetRepository:
        if self._factory is None:
            raise VideoAssetStorageUnavailable(STUDIO_STORAGE_UNAVAILABLE_REASON)
        if self._repository is not None:
            return self._repository
        async with self._lock:
            if self._repository is None:
                try:
                    self._repository = self._factory()
                except Exception as error:
                    raise VideoAssetStorageUnavailable(
                        "参考素材存储暂不可用，请联系管理员检查 TOS 配置。"
                    ) from error
            return self._repository


def video_asset_repository_factory(
    *,
    provider: Literal["volcengine", "byteplus"],
    resolve_credentials: CredentialResolver,
) -> tuple[Callable[[], VideoAssetRepository] | None, int]:
    """Build a lazy TOS repository factory, or safely disable asset upload."""
    max_bytes = int(os.getenv("VEADK_VIDEO_MAX_FILE_BYTES", str(100 * 1024 * 1024)))
    config = StudioStorageConfig.from_env(provider)
    if not config.configured:
        return None, max_bytes

    client_factory = create_tos_client_factory(config, resolve_credentials)

    def factory() -> VideoAssetRepository:
        storage = StudioTosMediaStorage(
            bucket=config.bucket,
            region=config.region,
            endpoint=config.endpoint,
            access_key="",
            secret_key="",
            key_prefix=STUDIO_STORAGE_ROOT_PREFIX,
            client=client_factory(),
            signed_url_endpoint=config.endpoint,
        )
        return VideoAssetRepository(MediaService(storage, max_file_bytes=max_bytes))

    return factory, max_bytes


__all__ = [
    "LazyVideoAssetRepository",
    "StoredVideoAsset",
    "VideoAssetNotFound",
    "VideoAssetRepository",
    "VideoAssetStorageUnavailable",
    "video_asset_repository_factory",
]
