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

"""Artifact ingestion, ownership, and metadata orchestration."""

from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import os
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .models import (
    ArtifactIngestCandidate,
    ArtifactLibraryItem,
    ArtifactMetadataPatch,
    ArtifactRecord,
    ArtifactType,
)
from .repository import ArtifactNotFound, TosArtifactRepository

_DEFAULT_MAX_BYTES = 512 * 1024 * 1024
_DEFAULT_SOURCE_SUFFIXES = (
    ".volces.com",
    ".volccdn.com",
    ".byteplus.com",
    ".bytepluses.com",
)


class ArtifactStorageUnavailable(RuntimeError):
    pass


class ArtifactIngestError(ValueError):
    pass


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_name(value: str, mime_type: str) -> str:
    name = Path(value.replace("\\", "/")).name.strip().strip(".")
    if not name:
        name = "artifact"
    if len(name) > 480:
        name = name[:480]
    if "." not in name:
        extension = mimetypes.guess_extension(mime_type) or ""
        if extension == ".jpe":
            extension = ".jpg"
        name += extension
    return name


def _artifact_type(mime_type: str) -> ArtifactType:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    raise ArtifactIngestError("产物同步仅支持图片和视频。")


class ArtifactService:
    def __init__(
        self,
        repository: TosArtifactRepository | None,
        *,
        unavailable_reason: str = "",
        max_file_bytes: int | None = None,
        source_host_suffixes: tuple[str, ...] | None = None,
    ) -> None:
        self._repository = repository
        self._unavailable_reason = unavailable_reason
        self._max_file_bytes = max_file_bytes or int(
            os.getenv("VEADK_ARTIFACT_MAX_FILE_BYTES", str(_DEFAULT_MAX_BYTES))
        )
        configured_hosts = tuple(
            item.strip().lower()
            for item in os.getenv("VEADK_ARTIFACT_SOURCE_HOSTS", "").split(",")
            if item.strip()
        )
        self._source_host_suffixes = (
            source_host_suffixes or configured_hosts or _DEFAULT_SOURCE_SUFFIXES
        )

    @property
    def available(self) -> bool:
        return self._repository is not None

    async def list(self, owner_id: str) -> list[ArtifactLibraryItem]:
        repository = self._require_repository()
        records = await repository.list(owner_id)
        return [await self._item(record) for record in records]

    async def get(self, owner_id: str, artifact_id: str) -> ArtifactRecord:
        return await self._require_repository().get(owner_id, artifact_id)

    async def sync(
        self,
        owner_id: str,
        candidates: list[ArtifactIngestCandidate],
    ) -> list[ArtifactLibraryItem]:
        repository = self._require_repository()
        for candidate in candidates:
            artifact_id, source_hash = self._identity(owner_id, candidate)
            try:
                await repository.get(owner_id, artifact_id)
                continue
            except ArtifactNotFound:
                pass

            self._validate_source_url(str(candidate.source_url))
            with tempfile.TemporaryDirectory(prefix="veadk-artifact-") as temp_dir:
                target = Path(temp_dir) / "content"
                mime_type, size_bytes = await self._download(
                    str(candidate.source_url),
                    candidate.mime_type,
                    target,
                )
                artifact_type = _artifact_type(mime_type)
                content_name = _safe_name(candidate.name, mime_type)
                now = datetime.now(timezone.utc)
                record = ArtifactRecord(
                    id=artifact_id,
                    ownerId=owner_id,
                    appName=candidate.app_name,
                    agentId=candidate.agent_id,
                    agentName=candidate.agent_name,
                    sessionId=candidate.session_id,
                    sessionTitle=candidate.session_title,
                    sessionUpdatedAt=_utc(candidate.session_updated_at),
                    name=content_name,
                    contentName=content_name,
                    contentKey=repository.content_key(
                        owner_id, artifact_id, content_name
                    ),
                    type=artifact_type,
                    mimeType=mime_type,
                    sizeBytes=size_bytes,
                    version=1,
                    createdAt=_utc(candidate.created_at),
                    updatedAt=now,
                    sourceUrlHash=source_hash,
                    origin=candidate.origin,
                )
                await repository.create(record, target)
        return await self.list(owner_id)

    async def update(
        self,
        owner_id: str,
        artifact_id: str,
        patch: ArtifactMetadataPatch,
    ) -> ArtifactLibraryItem:
        repository = self._require_repository()
        record = await repository.get(owner_id, artifact_id)
        update = patch.model_dump(exclude_none=True)
        if "name" in update:
            update["name"] = _safe_name(str(update["name"]), record.mime_type)
        updated = record.model_copy(
            update={**update, "updated_at": datetime.now(timezone.utc)}
        )
        await repository.update(updated)
        return await self._item(updated)

    async def delete(self, owner_id: str, artifact_id: str) -> None:
        await self._require_repository().delete(owner_id, artifact_id)

    async def open_content(self, owner_id: str, artifact_id: str):
        return await self._require_repository().open_content(owner_id, artifact_id)

    async def _item(self, record: ArtifactRecord) -> ArtifactLibraryItem:
        repository = self._require_repository()
        signed_url = await repository.signed_url(record)
        preview_mode = (
            "image"
            if record.type == "image"
            else "video"
            if record.type == "video"
            else "unavailable"
        )
        return ArtifactLibraryItem(
            id=record.id,
            appName=record.app_name,
            agentId=record.agent_id,
            sessionId=record.session_id,
            sessionTitle=record.session_title,
            agentName=record.agent_name,
            sessionUpdatedAt=record.session_updated_at,
            name=record.name,
            version=record.version,
            type=record.type,
            createdAt=record.created_at,
            updatedAt=record.updated_at,
            description=record.description,
            tags=record.tags,
            mimeType=record.mime_type,
            sizeBytes=record.size_bytes,
            canManage=True,
            thumbnailUrl=signed_url if record.type == "image" else "",
            contentUrl=signed_url,
            origin=record.origin,
            preview={
                "filename": record.content_name,
                "version": record.version,
                "mode": preview_mode,
            },
        )

    def _require_repository(self) -> TosArtifactRepository:
        if self._repository is None:
            raise ArtifactStorageUnavailable(self._unavailable_reason)
        return self._repository

    @staticmethod
    def _identity(
        owner_id: str,
        candidate: ArtifactIngestCandidate,
    ) -> tuple[str, str]:
        source = str(candidate.source_url)
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        stable = (
            f"{owner_id}\0{candidate.session_id}\0{candidate.origin.event_id}\0"
            f"{candidate.origin.invocation_id}\0{candidate.origin.tool_name}\0"
            f"{candidate.origin.provider_task_id}\0{candidate.name}\0{source_hash}"
        )
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:40], source_hash

    def _validate_source_url(self, source_url: str) -> None:
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username:
            raise ArtifactIngestError("产物来源必须是安全的 HTTPS 地址。")
        host = parsed.hostname.lower().rstrip(".")
        if not any(
            host == suffix.removeprefix(".") or host.endswith(suffix)
            for suffix in self._source_host_suffixes
        ):
            raise ArtifactIngestError("产物来源不是受信任的生成服务地址。")
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            }
        except OSError as error:
            raise ArtifactIngestError("无法解析产物来源地址。") from error
        if not addresses or any(
            not ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise ArtifactIngestError("产物来源地址不可访问。")

    async def _download(
        self,
        source_url: str,
        declared_mime_type: str,
        target: Path,
    ) -> tuple[str, int]:
        timeout = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)
        async with (
            httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client,
            client.stream("GET", source_url) as response,
        ):
            response.raise_for_status()
            content_length = int(response.headers.get("content-length") or 0)
            if content_length > self._max_file_bytes:
                raise ArtifactIngestError("生成产物超过可保存的大小限制。")
            header_mime = response.headers.get("content-type", "").split(";", 1)[0]
            mime_type = (header_mime or declared_mime_type).strip().lower()
            if mime_type == "application/octet-stream":
                mime_type = declared_mime_type.strip().lower()
            if not mime_type:
                mime_type = mimetypes.guess_type(urlparse(source_url).path)[0] or ""
            _artifact_type(mime_type)
            size_bytes = 0
            with target.open("wb") as output:
                async for chunk in response.aiter_bytes():
                    size_bytes += len(chunk)
                    if size_bytes > self._max_file_bytes:
                        raise ArtifactIngestError("生成产物超过可保存的大小限制。")
                    output.write(chunk)
        if size_bytes == 0:
            raise ArtifactIngestError("生成服务返回了空产物。")
        return mime_type, size_bytes


__all__ = [
    "ArtifactIngestError",
    "ArtifactService",
    "ArtifactStorageUnavailable",
]
