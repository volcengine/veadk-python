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
"""Tests for durable multimodal storage backends."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Any

import pytest

from veadk.multimodal.models import MediaRecord
from veadk.multimodal.models import MediaRef
from veadk.multimodal.service import MediaService
from veadk.multimodal import storage as storage_module
from veadk.multimodal.storage import LocalMediaStorage
from veadk.multimodal.storage import TosMediaStorage
from veadk.multimodal.storage import create_media_storage


def _record(ref: MediaRef, *, size_bytes: int = 5) -> MediaRecord:
    return MediaRecord.create(
        ref=ref,
        file_name="hello.txt",
        mime_type="text/plain",
        size_bytes=size_bytes,
        sha256="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        origin="user",
    )


def test_media_uri_round_trip() -> None:
    ref = MediaRef("demo app", "user@example.com", "session/1", "abc123")

    assert MediaRef.from_uri(ref.uri) == ref
    assert MediaRef.from_uri("https://example.com/file.png") is None


def test_local_storage_defaults_to_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = tmp_path / "veadk-media"
    monkeypatch.delenv("VEADK_MEDIA_STORAGE", raising=False)
    monkeypatch.delenv("VEADK_MEDIA_LOCAL_DIR", raising=False)
    monkeypatch.setattr(storage_module, "_DEFAULT_LOCAL_MEDIA_DIR", expected)

    storage = create_media_storage()

    assert isinstance(storage, LocalMediaStorage)
    assert storage.root_dir == expected.resolve()


@pytest.mark.asyncio
async def test_local_storage_persists_and_deletes_session(tmp_path: Path) -> None:
    storage = LocalMediaStorage(tmp_path)
    ref = MediaRef("demo", "user", "session", "media-id")
    record = _record(ref)

    await storage.save_bytes(record, b"hello")

    assert await storage.get_record(ref) == record
    assert await storage.read_bytes(ref) == b"hello"
    local_path = storage.local_path(ref)
    assert local_path is not None
    assert local_path.read_bytes() == b"hello"

    await storage.delete_session("demo", "user", "session")
    assert await storage.get_record(ref) is None


@pytest.mark.asyncio
async def test_tos_storage_isolates_users_by_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeTosClient.objects = {}
    fake_tos = SimpleNamespace(
        TosClientV2=_FakeTosClient,
        HttpMethodType=SimpleNamespace(Http_Method_Get="GET"),
        exceptions=SimpleNamespace(TosServerError=_FakeTosServerError),
    )
    monkeypatch.setitem(sys.modules, "tos", fake_tos)
    storage = TosMediaStorage(
        bucket="bucket",
        region="cn-beijing",
        endpoint="tos.example",
        access_key="ak",
        secret_key="sk",
    )
    alice_ref = MediaRef("demo/app", "alice@example.com", "session/1", "shared-id")
    bob_ref = MediaRef("demo/app", "bob@example.com", "session/1", "shared-id")
    alice_record = _record(alice_ref)
    bob_record = _record(bob_ref)

    await storage.save_bytes(alice_record, b"alice")
    await storage.save_bytes(bob_record, b"bob")

    assert any(
        key.startswith("veadk-media/users/alice%40example.com/")
        for key in _FakeTosClient.objects
    )
    assert any(
        key.startswith("veadk-media/users/bob%40example.com/")
        for key in _FakeTosClient.objects
    )
    assert await storage.read_bytes(alice_ref) == b"alice"
    assert await storage.read_bytes(bob_ref) == b"bob"

    await storage.delete_session("demo/app", "alice@example.com", "session/1")

    assert await storage.get_record(alice_ref) is None
    assert await storage.get_record(bob_ref) == bob_record


@pytest.mark.asyncio
async def test_media_service_detects_markdown(tmp_path: Path) -> None:
    path = tmp_path / "guide.md"
    path.write_text("# Guide", encoding="utf-8")
    service = MediaService(LocalMediaStorage(tmp_path / "storage"))

    record = await service.save_file(
        app_name="demo",
        user_id="user",
        session_id="session",
        file_name="guide.md",
        declared_mime_type="",
        source=path,
    )

    assert record.mime_type == "text/markdown"
    assert await service.storage.read_bytes(record.ref) == b"# Guide"


@pytest.mark.asyncio
async def test_media_service_rejects_unsupported_file(tmp_path: Path) -> None:
    path = tmp_path / "archive.zip"
    path.write_bytes(b"PK\x03\x04not-a-supported-upload")
    service = MediaService(LocalMediaStorage(tmp_path / "storage"))

    with pytest.raises(ValueError, match="Unsupported media type"):
        await service.save_file(
            app_name="demo",
            user_id="user",
            session_id="session",
            file_name=path.name,
            declared_mime_type="application/zip",
            source=path,
        )


class _FakeTosServerError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeTosClient:
    objects: dict[str, bytes] = {}

    def __init__(self, **_: object) -> None:
        self.objects = self.__class__.objects

    def put_object(self, *, key: str, content: Any, **_: object) -> None:
        data = content.read() if hasattr(content, "read") else content
        self.objects[key] = bytes(data)

    def get_object(self, *, key: str, **_: object) -> SimpleNamespace:
        if key not in self.objects:
            raise _FakeTosServerError(404)
        return SimpleNamespace(read=lambda: self.objects[key])

    def pre_signed_url(self, _: object, *, key: str, **__: object) -> SimpleNamespace:
        return SimpleNamespace(signed_url=f"https://tos.example/{key}?signed=1")

    def delete_object(self, *, key: str, **_: object) -> None:
        self.objects.pop(key, None)

    def list_objects_type2(self, *, prefix: str, **_: object) -> SimpleNamespace:
        contents = [
            SimpleNamespace(key=key) for key in self.objects if key.startswith(prefix)
        ]
        return SimpleNamespace(
            contents=contents,
            is_truncated=False,
            next_continuation_token=None,
        )


@pytest.mark.asyncio
async def test_tos_storage_persists_signs_and_deletes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeTosClient.objects = {}
    fake_tos = SimpleNamespace(
        TosClientV2=_FakeTosClient,
        HttpMethodType=SimpleNamespace(Http_Method_Get="GET"),
        exceptions=SimpleNamespace(TosServerError=_FakeTosServerError),
    )
    monkeypatch.setitem(sys.modules, "tos", fake_tos)
    storage = TosMediaStorage(
        bucket="bucket",
        region="cn-beijing",
        endpoint="tos.example",
        access_key="ak",
        secret_key="sk",
    )
    ref = MediaRef("demo", "user", "session", "media-id")
    record = _record(ref)

    await storage.save_bytes(record, b"hello")

    object_prefix = "veadk-media/users/user/apps/demo/sessions/session/media/media-id"
    assert set(_FakeTosClient.objects) == {
        f"{object_prefix}/content",
        f"{object_prefix}/metadata.json",
    }
    assert await storage.get_record(ref) == record
    assert await storage.read_bytes(ref) == b"hello"
    signed_url = await storage.signed_url(ref)
    assert signed_url is not None
    assert signed_url.startswith("https://tos.example/")

    await storage.delete(ref)
    assert await storage.get_record(ref) is None

    await storage.save_bytes(record, b"hello")
    await storage.delete_session("demo", "user", "session")
    assert await storage.get_record(ref) is None
