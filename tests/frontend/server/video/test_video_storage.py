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

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from frontend.server.video.storage import (
    VideoAssetRepository,
    VideoAssetStorageUnavailable,
)
from veadk.multimodal.models import MediaRecord, MediaRef
from veadk.multimodal.service import MediaService


class MemoryMediaStorage:
    def __init__(self) -> None:
        self.records: dict[MediaRef, MediaRecord] = {}

    async def save_file(self, record: MediaRecord, source: Path) -> None:
        assert source.read_bytes()
        self.records[record.ref] = record

    async def save_bytes(self, record: MediaRecord, data: bytes) -> None:
        assert data
        self.records[record.ref] = record

    async def get_record(self, ref: MediaRef) -> MediaRecord | None:
        return self.records.get(ref)

    async def read_bytes(self, ref: MediaRef) -> bytes:
        raise NotImplementedError

    def local_path(self, ref: MediaRef) -> Path | None:
        return None

    async def signed_url(self, ref: MediaRef) -> str:
        return f"https://assets.example/{ref.media_id}"

    async def delete(self, ref: MediaRef) -> None:
        self.records.pop(ref, None)

    async def delete_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        raise NotImplementedError


class FailingMediaStorage(MemoryMediaStorage):
    async def save_file(self, record: MediaRecord, source: Path) -> None:
        raise TimeoutError("TOS request timed out")


@pytest.mark.asyncio
async def test_video_asset_metadata_can_be_restored_by_another_repository_instance(
    tmp_path: Path,
) -> None:
    storage = MemoryMediaStorage()
    media_service = MediaService(storage, max_file_bytes=1024 * 1024)
    source = tmp_path / "frame.png"
    source.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    )

    first_repository = VideoAssetRepository(media_service)
    saved = await first_repository.save(
        owner_id="alice",
        role="first_frame",
        file_name="frame.png",
        declared_mime_type="image/png",
        source=source,
    )

    restored = await VideoAssetRepository(media_service).get("alice", saved.asset_id)

    assert restored.owner_id == "alice"
    assert restored.role == "first_frame"
    assert restored.record.ref == MediaRef(
        app_name="video",
        user_id="alice",
        session_id="first_frame",
        media_id=saved.asset_id,
    )


@pytest.mark.asyncio
async def test_video_asset_upload_converts_storage_failure_to_recoverable_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "frame.png"
    source.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    )
    repository = VideoAssetRepository(
        MediaService(FailingMediaStorage(), max_file_bytes=1024 * 1024)
    )

    with pytest.raises(
        VideoAssetStorageUnavailable,
        match="请稍后重试或联系管理员检查 TOS 配置",
    ):
        await repository.save(
            owner_id="alice",
            role="reference_image",
            file_name="frame.png",
            declared_mime_type="image/png",
            source=source,
        )


@pytest.mark.asyncio
async def test_reference_video_below_seedance_pixel_minimum_is_rejected_before_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "reference.mp4"
    source.write_bytes(b"video-bytes")
    storage = MemoryMediaStorage()
    repository = VideoAssetRepository(MediaService(storage, max_file_bytes=1024 * 1024))

    def probe(*args, **kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps({"streams": [{"width": 640, "height": 360}]}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", probe)

    with pytest.raises(ValueError, match="至少包含 409600 个像素"):
        await repository.save(
            owner_id="alice",
            role="reference_video",
            file_name="reference.mp4",
            declared_mime_type="video/mp4",
            source=source,
        )

    assert storage.records == {}
