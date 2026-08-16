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

"""TOS repository for immutable artifact content and mutable metadata."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX

from .models import ArtifactRecord

_MAX_METADATA_BYTES = 64 * 1024


class ArtifactNotFound(LookupError):
    pass


class ArtifactConflict(RuntimeError):
    pass


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    return value if isinstance(value, int) else None


class TosArtifactRepository:
    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        root_prefix: str = STUDIO_STORAGE_ROOT_PREFIX,
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS artifact storage requires a bucket.")
        self._bucket = bucket
        self._client_factory = client_factory
        self._root_prefix = root_prefix.strip("/")

    async def list(self, owner_id: str) -> list[ArtifactRecord]:
        return await asyncio.to_thread(self._list, owner_id)

    async def get(self, owner_id: str, artifact_id: str) -> ArtifactRecord:
        return await asyncio.to_thread(self._get, owner_id, artifact_id)

    async def create(self, record: ArtifactRecord, source: Path) -> ArtifactRecord:
        return await asyncio.to_thread(self._create, record, source)

    async def update(self, record: ArtifactRecord) -> ArtifactRecord:
        await asyncio.to_thread(
            self._put_metadata, self._client_factory(), record, False
        )
        return record

    async def delete(self, owner_id: str, artifact_id: str) -> None:
        await asyncio.to_thread(self._delete, owner_id, artifact_id)

    async def open_content(
        self, owner_id: str, artifact_id: str
    ) -> tuple[ArtifactRecord, Any]:
        return await asyncio.to_thread(self._open_content, owner_id, artifact_id)

    async def signed_url(self, record: ArtifactRecord, *, expires: int = 900) -> str:
        return await asyncio.to_thread(self._signed_url, record, expires)

    def _list(self, owner_id: str) -> list[ArtifactRecord]:
        client = self._client_factory()
        prefix = f"{self._owner_prefix(owner_id)}/"
        continuation_token = ""
        keys: list[str] = []
        while True:
            output = client.list_objects_type2(
                bucket=self._bucket,
                prefix=prefix,
                continuation_token=continuation_token,
                max_keys=1000,
            )
            keys.extend(
                str(item.key)
                for item in (getattr(output, "contents", None) or [])
                if str(getattr(item, "key", "")).endswith("/metadata.json")
            )
            if not getattr(output, "is_truncated", False):
                break
            continuation_token = str(
                getattr(output, "next_continuation_token", "") or ""
            )
            if not continuation_token:
                raise RuntimeError(
                    "TOS truncated an artifact listing without a continuation token."
                )
        records = [self._record_from_key(client, key) for key in keys]
        return sorted(
            (record for record in records if record.owner_id == owner_id),
            key=lambda record: (record.created_at, record.id),
            reverse=True,
        )

    def _get(self, owner_id: str, artifact_id: str) -> ArtifactRecord:
        client = self._client_factory()
        key = self._metadata_key(owner_id, artifact_id)
        try:
            record = self._record_from_key(client, key)
        except Exception as error:
            if _status_code(error) == 404:
                raise ArtifactNotFound("产物不存在或已被删除。") from error
            raise
        if record.owner_id != owner_id or record.id != artifact_id:
            raise ArtifactNotFound("产物不存在或已被删除。")
        return record

    def _create(self, record: ArtifactRecord, source: Path) -> ArtifactRecord:
        client = self._client_factory()
        try:
            with source.open("rb") as content:
                client.put_object(
                    bucket=self._bucket,
                    key=record.content_key,
                    content=content,
                    content_length=record.size_bytes,
                    content_type=record.mime_type,
                    forbid_overwrite=True,
                )
        except Exception as error:
            if _status_code(error) not in {409, 412}:
                raise
            existing = self._get(record.owner_id, record.id)
            if existing.source_url_hash != record.source_url_hash:
                raise ArtifactConflict(
                    "Artifact id already contains different content."
                )
            return existing

        try:
            self._put_metadata(client, record, True)
        except Exception:
            client.delete_object(bucket=self._bucket, key=record.content_key)
            raise
        return record

    def _put_metadata(
        self,
        client: Any,
        record: ArtifactRecord,
        forbid_overwrite: bool,
    ) -> None:
        content = record.model_dump_json(by_alias=True).encode("utf-8")
        if len(content) > _MAX_METADATA_BYTES:
            raise ValueError("Artifact metadata is too large.")
        client.put_object(
            bucket=self._bucket,
            key=self._metadata_key(record.owner_id, record.id),
            content=content,
            content_length=len(content),
            content_type="application/json",
            forbid_overwrite=forbid_overwrite,
        )

    def _delete(self, owner_id: str, artifact_id: str) -> None:
        record = self._get(owner_id, artifact_id)
        client = self._client_factory()
        client.delete_object(bucket=self._bucket, key=record.content_key)
        client.delete_object(
            bucket=self._bucket,
            key=self._metadata_key(owner_id, artifact_id),
        )

    def _open_content(
        self, owner_id: str, artifact_id: str
    ) -> tuple[ArtifactRecord, Any]:
        record = self._get(owner_id, artifact_id)
        response = self._client_factory().get_object(
            bucket=self._bucket,
            key=record.content_key,
        )
        return record, response

    def _signed_url(self, record: ArtifactRecord, expires: int) -> str:
        import tos

        output = self._client_factory().pre_signed_url(
            tos.HttpMethodType.Http_Method_Get,
            bucket=self._bucket,
            key=record.content_key,
            expires=expires,
        )
        return str(output.signed_url)

    def _record_from_key(self, client: Any, key: str) -> ArtifactRecord:
        response = client.get_object(bucket=self._bucket, key=key)
        if hasattr(response, "read"):
            content = response.read(_MAX_METADATA_BYTES + 1)
        else:
            content = b"".join(response)
        if not isinstance(content, bytes) or len(content) > _MAX_METADATA_BYTES:
            raise ValueError("Artifact metadata is invalid or too large.")
        return ArtifactRecord.model_validate_json(content)

    def content_key(self, owner_id: str, artifact_id: str, name: str) -> str:
        return (
            f"{self._artifact_prefix(owner_id, artifact_id)}/content/"
            f"{quote(name, safe='')}"
        )

    def _metadata_key(self, owner_id: str, artifact_id: str) -> str:
        return f"{self._artifact_prefix(owner_id, artifact_id)}/metadata.json"

    def _artifact_prefix(self, owner_id: str, artifact_id: str) -> str:
        if not artifact_id or "/" in artifact_id:
            raise ValueError("Invalid artifact id.")
        return f"{self._owner_prefix(owner_id)}/{quote(artifact_id, safe='')}"

    def _owner_prefix(self, owner_id: str) -> str:
        if not owner_id:
            raise ValueError("Artifact owner id is required.")
        return f"{self._root_prefix}/users/{quote(owner_id, safe='')}/artifacts"


__all__ = [
    "ArtifactConflict",
    "ArtifactNotFound",
    "TosArtifactRepository",
]
