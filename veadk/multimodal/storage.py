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
"""Storage backends for durable multimodal media."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Protocol
from urllib.parse import quote

from .models import MediaRecord
from .models import MediaRef

_DEFAULT_LOCAL_MEDIA_DIR = Path("/tmp/veadk-media")


class MediaStorage(Protocol):
    """Persistence contract shared by local filesystem and TOS backends."""

    async def save_file(self, record: MediaRecord, source: Path) -> None:
        """Store one file and its metadata."""
        ...

    async def save_bytes(self, record: MediaRecord, data: bytes) -> None:
        """Store in-memory bytes and their metadata."""
        ...

    async def get_record(self, ref: MediaRef) -> MediaRecord | None:
        """Load metadata for one object."""
        ...

    async def read_bytes(self, ref: MediaRef) -> bytes:
        """Load all bytes for model input."""
        ...

    def local_path(self, ref: MediaRef) -> Path | None:
        """Return a local delivery path when the backend has one."""
        ...

    async def signed_url(self, ref: MediaRef) -> str | None:
        """Return a short-lived delivery URL when supported."""
        ...

    async def delete(self, ref: MediaRef) -> None:
        """Delete one object and its metadata."""
        ...

    async def delete_session(
        self, app_name: str, user_id: str, session_id: str
    ) -> None:
        """Delete every object belonging to a session."""
        ...


def _scope_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _scope_prefix(ref: MediaRef) -> str:
    return "/".join(
        (
            "apps",
            _scope_token(ref.app_name),
            "users",
            _scope_token(ref.user_id),
            "sessions",
            _scope_token(ref.session_id),
            "media",
            ref.media_id,
        )
    )


def _session_prefix(app_name: str, user_id: str, session_id: str) -> str:
    return "/".join(
        (
            "apps",
            _scope_token(app_name),
            "users",
            _scope_token(user_id),
            "sessions",
            _scope_token(session_id),
            "media",
        )
    )


def _tos_scope_prefix(ref: MediaRef) -> str:
    """Return a readable, user-first TOS key prefix."""
    return "/".join(
        (
            "users",
            quote(ref.user_id, safe=""),
            "apps",
            quote(ref.app_name, safe=""),
            "sessions",
            quote(ref.session_id, safe=""),
            "media",
            quote(ref.media_id, safe=""),
        )
    )


def _tos_session_prefix(app_name: str, user_id: str, session_id: str) -> str:
    """Return one user's exact TOS session prefix."""
    return "/".join(
        (
            "users",
            quote(user_id, safe=""),
            "apps",
            quote(app_name, safe=""),
            "sessions",
            quote(session_id, safe=""),
            "media",
            "",
        )
    )


class LocalMediaStorage:
    """Store media beneath a private local directory."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _object_dir(self, ref: MediaRef) -> Path:
        return self.root_dir.joinpath(*_scope_prefix(ref).split("/"))

    def _content_path(self, ref: MediaRef) -> Path:
        return self._object_dir(ref) / "content"

    def _metadata_path(self, ref: MediaRef) -> Path:
        return self._object_dir(ref) / "metadata.json"

    async def save_file(self, record: MediaRecord, source: Path) -> None:
        await asyncio.to_thread(self._save_file, record, source)

    def _save_file(self, record: MediaRecord, source: Path) -> None:
        object_dir = self._object_dir(record.ref)
        object_dir.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(source, self._content_path(record.ref))
        self._metadata_path(record.ref).write_text(
            json.dumps(record.to_dict(), ensure_ascii=False), encoding="utf-8"
        )

    async def save_bytes(self, record: MediaRecord, data: bytes) -> None:
        await asyncio.to_thread(self._save_bytes, record, data)

    def _save_bytes(self, record: MediaRecord, data: bytes) -> None:
        object_dir = self._object_dir(record.ref)
        object_dir.mkdir(parents=True, exist_ok=False)
        self._content_path(record.ref).write_bytes(data)
        self._metadata_path(record.ref).write_text(
            json.dumps(record.to_dict(), ensure_ascii=False), encoding="utf-8"
        )

    async def get_record(self, ref: MediaRef) -> MediaRecord | None:
        metadata_path = self._metadata_path(ref)
        if not metadata_path.is_file():
            return None
        raw = await asyncio.to_thread(metadata_path.read_text, encoding="utf-8")
        return MediaRecord.from_dict(json.loads(raw))

    async def read_bytes(self, ref: MediaRef) -> bytes:
        content_path = self._content_path(ref)
        if not content_path.is_file():
            raise FileNotFoundError(ref.uri)
        return await asyncio.to_thread(content_path.read_bytes)

    def local_path(self, ref: MediaRef) -> Path | None:
        path = self._content_path(ref)
        return path if path.is_file() else None

    async def signed_url(self, ref: MediaRef) -> str | None:
        del ref
        return None

    async def delete(self, ref: MediaRef) -> None:
        await asyncio.to_thread(shutil.rmtree, self._object_dir(ref), True)

    async def delete_session(
        self, app_name: str, user_id: str, session_id: str
    ) -> None:
        path = self.root_dir.joinpath(
            *_session_prefix(app_name, user_id, session_id).split("/")[:-1]
        )
        await asyncio.to_thread(shutil.rmtree, path, True)


class TosMediaStorage:
    """Store private media objects in Volcengine TOS."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint: str,
        access_key: str,
        secret_key: str,
        session_token: str = "",
        key_prefix: str = "veadk-media",
    ) -> None:
        if not bucket or not access_key or not secret_key:
            raise ValueError(
                "TOS media storage requires bucket, access key, and secret key."
            )
        import tos

        self._tos = tos
        self._bucket = bucket
        self._key_prefix = key_prefix.strip("/")
        self._client = tos.TosClientV2(
            ak=access_key,
            sk=secret_key,
            security_token=session_token,
            endpoint=endpoint,
            region=region,
        )

    def _key(self, ref: MediaRef, name: str) -> str:
        prefix = _tos_scope_prefix(ref)
        return f"{self._key_prefix}/{prefix}/{name}"

    def _session_key_prefix(self, app_name: str, user_id: str, session_id: str) -> str:
        prefix = _tos_session_prefix(app_name, user_id, session_id)
        return f"{self._key_prefix}/{prefix}"

    async def save_file(self, record: MediaRecord, source: Path) -> None:
        await asyncio.to_thread(self._save_file, record, source)

    def _save_file(self, record: MediaRecord, source: Path) -> None:
        with source.open("rb") as content:
            self._client.put_object(
                bucket=self._bucket,
                key=self._key(record.ref, "content"),
                content=content,
                content_length=record.size_bytes,
                content_type=record.mime_type,
            )
        self._put_metadata(record)

    async def save_bytes(self, record: MediaRecord, data: bytes) -> None:
        await asyncio.to_thread(self._save_bytes, record, data)

    def _save_bytes(self, record: MediaRecord, data: bytes) -> None:
        self._client.put_object(
            bucket=self._bucket,
            key=self._key(record.ref, "content"),
            content=data,
            content_length=len(data),
            content_type=record.mime_type,
        )
        self._put_metadata(record)

    def _put_metadata(self, record: MediaRecord) -> None:
        data = json.dumps(record.to_dict(), ensure_ascii=False).encode("utf-8")
        self._client.put_object(
            bucket=self._bucket,
            key=self._key(record.ref, "metadata.json"),
            content=data,
            content_length=len(data),
            content_type="application/json",
        )

    async def get_record(self, ref: MediaRef) -> MediaRecord | None:
        try:
            data = await asyncio.to_thread(
                self._get_object, self._key(ref, "metadata.json")
            )
        except self._tos.exceptions.TosServerError as error:
            if error.status_code == 404:
                return None
            raise
        return MediaRecord.from_dict(json.loads(data.decode("utf-8")))

    def _get_object(self, key: str) -> bytes:
        output = self._client.get_object(bucket=self._bucket, key=key)
        data = output.read()
        if not isinstance(data, bytes):
            raise TypeError(f"TOS returned non-bytes content for {key}.")
        return data

    async def read_bytes(self, ref: MediaRef) -> bytes:
        return await asyncio.to_thread(self._get_object, self._key(ref, "content"))

    def local_path(self, ref: MediaRef) -> Path | None:
        del ref
        return None

    async def signed_url(self, ref: MediaRef) -> str | None:
        return await asyncio.to_thread(self._signed_url, ref)

    def _signed_url(self, ref: MediaRef) -> str:
        output = self._client.pre_signed_url(
            self._tos.HttpMethodType.Http_Method_Get,
            bucket=self._bucket,
            key=self._key(ref, "content"),
            expires=900,
        )
        return output.signed_url

    async def delete(self, ref: MediaRef) -> None:
        await asyncio.gather(
            asyncio.to_thread(
                self._client.delete_object,
                bucket=self._bucket,
                key=self._key(ref, "content"),
            ),
            asyncio.to_thread(
                self._client.delete_object,
                bucket=self._bucket,
                key=self._key(ref, "metadata.json"),
            ),
        )

    async def delete_session(
        self, app_name: str, user_id: str, session_id: str
    ) -> None:
        prefix = self._session_key_prefix(app_name, user_id, session_id)
        await asyncio.to_thread(self._delete_prefix, prefix)

    def _delete_prefix(self, prefix: str) -> None:
        continuation_token = ""
        while True:
            output = self._client.list_objects_type2(
                bucket=self._bucket,
                prefix=prefix,
                continuation_token=continuation_token,
                max_keys=1000,
            )
            for item in output.contents or []:
                self._client.delete_object(bucket=self._bucket, key=item.key)
            if not output.is_truncated:
                return
            continuation_token = output.next_continuation_token
            if not continuation_token:
                raise RuntimeError(
                    "TOS truncated a listing without a continuation token."
                )


def create_media_storage(*, local_root: str | Path | None = None) -> MediaStorage:
    """Create the configured media backend; local filesystem is the default."""
    backend = os.getenv("VEADK_MEDIA_STORAGE", "local").strip().lower()
    if backend == "local":
        root = (
            local_root or os.getenv("VEADK_MEDIA_LOCAL_DIR") or _DEFAULT_LOCAL_MEDIA_DIR
        )
        return LocalMediaStorage(root)
    if backend != "tos":
        raise ValueError(f"Unsupported VEADK_MEDIA_STORAGE value: {backend}")

    provider = os.getenv("CLOUD_PROVIDER", "").lower()
    default_region = "ap-southeast-1" if provider == "byteplus" else "cn-beijing"
    region = os.getenv("DATABASE_TOS_REGION") or os.getenv("REGION") or default_region
    domain = "bytepluses.com" if provider == "byteplus" else "volces.com"
    endpoint = os.getenv("DATABASE_TOS_ENDPOINT") or f"tos-{region}.{domain}"
    return TosMediaStorage(
        bucket=os.getenv("DATABASE_TOS_BUCKET", ""),
        region=region,
        endpoint=endpoint,
        access_key=os.getenv("VOLCENGINE_ACCESS_KEY", ""),
        secret_key=os.getenv("VOLCENGINE_SECRET_KEY", ""),
        session_token=os.getenv("VOLCENGINE_SESSION_TOKEN", ""),
        key_prefix=os.getenv("VEADK_MEDIA_TOS_PREFIX", "veadk-media"),
    )
