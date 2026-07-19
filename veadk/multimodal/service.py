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
"""Validation and lifecycle operations for multimodal media."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
from pathlib import Path
import uuid

import filetype

from .models import MediaRecord
from .models import MediaRef
from .storage import MediaStorage

SUPPORTED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
        "text/markdown",
        "text/plain",
        "video/mp4",
        "video/quicktime",
        "video/webm",
    }
)

_EXTENSION_MIME_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}


class MediaService:
    """Validate files and coordinate a configured storage backend."""

    def __init__(
        self, storage: MediaStorage, max_file_bytes: int | None = None
    ) -> None:
        self.storage = storage
        self.max_file_bytes = max_file_bytes or int(
            os.getenv("VEADK_MEDIA_MAX_FILE_BYTES", str(20 * 1024 * 1024))
        )

    async def save_file(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        file_name: str,
        declared_mime_type: str,
        source: Path,
        origin: str = "user",
    ) -> MediaRecord:
        """Validate and persist one uploaded file."""
        size_bytes = source.stat().st_size
        self._validate_size(size_bytes)
        mime_type = await asyncio.to_thread(
            self._detect_mime_type, source, file_name, declared_mime_type
        )
        sha256 = await asyncio.to_thread(self._sha256_file, source)
        record = MediaRecord.create(
            ref=MediaRef(app_name, user_id, session_id, uuid.uuid4().hex),
            file_name=Path(file_name).name or "attachment",
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            origin=origin,
        )
        await self.storage.save_file(record, source)
        return record

    async def save_bytes(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        file_name: str,
        mime_type: str,
        data: bytes,
        origin: str,
    ) -> MediaRecord:
        """Persist model-produced bytes."""
        normalized_mime = mime_type.split(";", 1)[0].strip().lower()
        if normalized_mime not in SUPPORTED_MIME_TYPES:
            raise ValueError(f"Unsupported media type: {normalized_mime}")
        self._validate_size(len(data))
        record = MediaRecord.create(
            ref=MediaRef(app_name, user_id, session_id, uuid.uuid4().hex),
            file_name=Path(file_name).name or "model-output",
            mime_type=normalized_mime,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            origin=origin,
        )
        await self.storage.save_bytes(record, data)
        return record

    async def get_record(self, ref: MediaRef) -> MediaRecord:
        """Load metadata or fail when the media object does not exist."""
        record = await self.storage.get_record(ref)
        if record is None:
            raise FileNotFoundError(ref.uri)
        return record

    def _validate_size(self, size_bytes: int) -> None:
        if size_bytes <= 0:
            raise ValueError("Uploaded file is empty.")
        if size_bytes > self.max_file_bytes:
            limit_mb = self.max_file_bytes // (1024 * 1024)
            raise ValueError(f"File exceeds the {limit_mb} MB upload limit.")

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _detect_mime_type(path: Path, file_name: str, declared: str) -> str:
        extension = Path(file_name).suffix.lower()
        declared = declared.split(";", 1)[0].strip().lower()
        detected = filetype.guess(str(path))
        if detected is not None:
            mime_type = detected.mime
        elif extension in _EXTENSION_MIME_TYPES:
            mime_type = _EXTENSION_MIME_TYPES[extension]
        else:
            guessed, _ = mimetypes.guess_type(file_name)
            mime_type = declared or guessed or "application/octet-stream"
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise ValueError(f"Unsupported media type: {mime_type}")
        return mime_type


def media_kind(mime_type: str) -> str:
    """Return the frontend media category for a MIME type."""
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type == "text/markdown":
        return "markdown"
    return "text"
