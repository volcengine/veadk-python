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

import hashlib
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from frontend.server.knowledge.gateways import _document
from frontend.server.knowledge.models import CreateDocumentBody, UpdateDocumentBody
from frontend.server.knowledge.routes import mount_knowledge_routes
from frontend.server.knowledge.service import (
    KnowledgeAccessError,
    KnowledgeIdentity,
    KnowledgeRecord,
    KnowledgeService,
    ProviderConnection,
    StoredKnowledgeUpload,
    encode_owned_description,
)
from frontend.server.knowledge.uploads import (
    TosKnowledgeUploadStore,
    validate_knowledge_upload,
    validate_knowledge_upload_content,
)
from frontend.server.knowledge.web_import import (
    WebImportFetchError,
    WebImportResult,
)
from frontend.server.storage import StudioProvider

SIGNING_KEY = b"knowledge-upload-test-signing-key"


@pytest.mark.parametrize(
    ("file_name", "mime_type", "expected_type"),
    [
        ("photo.png", "image/png", "png"),
        ("photo.jpg", "image/jpeg", "jpg"),
        ("photo.jpeg", "image/jpeg", "jpeg"),
        ("guide.pdf", "application/pdf", "pdf"),
        (
            "slides.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "pptx",
        ),
        (
            "guide.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        ),
        ("table.xlsx", "application/octet-stream", "xlsx"),
        ("notes.txt", "text/plain", "txt"),
    ],
)
def test_validate_knowledge_upload_accepts_supported_media_and_documents(
    file_name: str,
    mime_type: str,
    expected_type: str,
) -> None:
    result = validate_knowledge_upload(file_name, mime_type)

    assert result.file_name == file_name
    assert result.document_type == expected_type


@pytest.mark.parametrize(
    ("file_name", "mime_type", "status_code"),
    [
        ("../secret.pdf", "application/pdf", 400),
        ("folder\\secret.pdf", "application/pdf", 400),
        ("payload.exe", "application/octet-stream", 415),
        ("image.png", "text/html", 415),
        ("clip.mp4", "video/mp4", 415),
        ("voice.wav", "audio/wav", 415),
        ("legacy.doc", "application/msword", 415),
        ("legacy.xls", "application/vnd.ms-excel", 415),
        ("legacy.ppt", "application/vnd.ms-powerpoint", 415),
        ("animation.gif", "image/gif", 415),
        ("photo.webp", "image/webp", 415),
    ],
)
def test_validate_knowledge_upload_rejects_unsafe_names_and_types(
    file_name: str,
    mime_type: str,
    status_code: int,
) -> None:
    with pytest.raises(KnowledgeAccessError) as captured:
        validate_knowledge_upload(file_name, mime_type)

    assert captured.value.status_code == status_code


def _validated(file_name: str, mime_type: str):
    return validate_knowledge_upload(file_name, mime_type)


@pytest.mark.parametrize(
    ("file_name", "mime_type", "content"),
    [
        ("photo.png", "image/png", b"\x89PNG\r\n\x1a\ncontent"),
        ("photo.jpg", "image/jpeg", b"\xff\xd8\xff\xe0content"),
        ("guide.pdf", "application/pdf", b"%PDF-1.7\ncontent"),
        ("notes.txt", "text/plain", "安全的 UTF-8 文本\n".encode()),
        ("notes.txt", "application/octet-stream", b"\xef\xbb\xbfUTF-8 BOM\n"),
    ],
)
def test_validate_knowledge_upload_content_accepts_matching_bytes(
    tmp_path: Path,
    file_name: str,
    mime_type: str,
    content: bytes,
) -> None:
    source = tmp_path / file_name
    source.write_bytes(content)

    validate_knowledge_upload_content(source, _validated(file_name, mime_type))


@pytest.mark.parametrize(
    ("file_name", "mime_type", "content"),
    [
        ("photo.png", "image/png", b"not-a-png"),
        ("photo.jpg", "image/jpeg", b"not-a-jpeg"),
        ("guide.pdf", "application/pdf", b"not-a-pdf"),
        ("notes.txt", "text/plain", b"binary\x00content"),
        ("notes.txt", "text/plain", b"invalid-utf8-\xff"),
    ],
)
def test_validate_knowledge_upload_content_rejects_spoofed_or_binary_files(
    tmp_path: Path,
    file_name: str,
    mime_type: str,
    content: bytes,
) -> None:
    source = tmp_path / file_name
    source.write_bytes(content)

    with pytest.raises(KnowledgeAccessError) as captured:
        validate_knowledge_upload_content(source, _validated(file_name, mime_type))

    assert captured.value.status_code == 415


@pytest.mark.parametrize(
    ("file_name", "mime_type", "required_path"),
    [
        (
            "guide.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "word/document.xml",
        ),
        (
            "slides.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "ppt/presentation.xml",
        ),
        (
            "table.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xl/workbook.xml",
        ),
    ],
)
def test_validate_knowledge_upload_content_accepts_expected_ooxml_structure(
    tmp_path: Path,
    file_name: str,
    mime_type: str,
    required_path: str,
) -> None:
    source = tmp_path / file_name
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(required_path, "<document />")

    validate_knowledge_upload_content(source, _validated(file_name, mime_type))


def test_validate_knowledge_upload_content_rejects_wrong_ooxml_family(
    tmp_path: Path,
) -> None:
    source = tmp_path / "spoofed.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")

    with pytest.raises(KnowledgeAccessError) as captured:
        validate_knowledge_upload_content(
            source,
            _validated(
                source.name,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        )

    assert captured.value.status_code == 415


class _FakeTosClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}
        self.uploads: list[dict[str, object]] = []
        self.deleted: list[dict[str, object]] = []
        self.created_buckets: list[str] = []
        self.create_bucket_error: Exception | None = None
        self.objects: dict[tuple[str, str], bytes] = {}

    def create_bucket(self, *, bucket: str) -> None:
        self.created_buckets.append(bucket)
        if self.create_bucket_error is not None:
            raise self.create_bucket_error

    def put_object_from_file(self, **kwargs: object) -> None:
        self.uploads.append(kwargs)

    def put_object(self, **kwargs: object) -> None:
        content = kwargs["content"]
        assert isinstance(content, bytes)
        self.objects[(str(kwargs["bucket"]), str(kwargs["key"]))] = content

    def get_object(self, **kwargs: object) -> list[bytes]:
        return [self.objects[(str(kwargs["bucket"]), str(kwargs["key"]))]]

    def delete_object(self, **kwargs: object) -> None:
        self.deleted.append(kwargs)


class _TosBucketError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@pytest.mark.parametrize(
    ("provider", "regions", "provider_tag"),
    [
        ("volcengine", ("cn-beijing", "cn-shanghai"), "ve"),
        ("byteplus", ("ap-southeast-1", "ap-southeast-2"), "bp"),
    ],
)
def test_generated_bucket_name_is_provider_and_region_scoped(
    provider: StudioProvider,
    regions: tuple[str, str],
    provider_tag: str,
) -> None:
    store = TosKnowledgeUploadStore(
        provider=provider,
        resolve_credentials=lambda: ("ak", "sk", None),
        source={"VEADK_STUDIO_ACCOUNT_ID": "3001037806"},
    )

    targets = [store._target(region) for region in regions]

    assert [target.bucket for target in targets] == [
        (
            "agentkit-platform-3001037806-bp-cn-hongkong"
            if provider == "byteplus" and region == "ap-southeast-1"
            else f"agentkit-platform-3001037806-{provider_tag}-{region}"
        )
        for region in regions
    ]
    assert targets[0].bucket != targets[1].bucket


@pytest.mark.parametrize(
    ("provider", "region", "account_region", "provider_tag"),
    [
        ("volcengine", "cn-beijing", "cn-beijing", "ve"),
        ("byteplus", "ap-southeast-1", "ap-southeast-1", "bp"),
    ],
)
def test_generated_bucket_resolves_account_id_with_runtime_credentials(
    monkeypatch: pytest.MonkeyPatch,
    provider: StudioProvider,
    region: str,
    account_region: str,
    provider_tag: str,
) -> None:
    captured: dict[str, object] = {}
    calls = 0

    def _resolve_account_id(**kwargs: object) -> str:
        nonlocal calls
        calls += 1
        captured.update(kwargs)
        return "3001037806"

    monkeypatch.setattr(
        "frontend.server.storage.provisioning.resolve_studio_account_id_for_deploy",
        _resolve_account_id,
    )
    store = TosKnowledgeUploadStore(
        provider=provider,
        resolve_credentials=lambda: ("role-ak", "role-sk", "role-token"),
        source={},
    )

    target = store._target(region)
    repeated_target = store._target(region)

    expected_data_region = "cn-hongkong" if provider == "byteplus" else region
    assert target.bucket == (
        f"agentkit-platform-3001037806-{provider_tag}-{expected_data_region}"
    )
    assert captured == {
        "access_key": "role-ak",
        "secret_key": "role-sk",
        "session_token": "role-token",
        "region": account_region,
        "provider": provider,
    }
    assert repeated_target == target
    assert calls == 1


def test_generated_bucket_preserves_account_resolution_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from frontend.server.storage.provisioning import StudioStorageProvisioningError

    def _resolve_account_id(**_: object) -> str:
        raise StudioStorageProvisioningError("无法获取当前云账号 ID：STS denied")

    monkeypatch.setattr(
        "frontend.server.storage.provisioning.resolve_studio_account_id_for_deploy",
        _resolve_account_id,
    )
    store = TosKnowledgeUploadStore(
        provider="volcengine",
        resolve_credentials=lambda: ("role-ak", "role-sk", "role-token"),
        source={},
    )

    with pytest.raises(KnowledgeAccessError) as captured:
        store._target("cn-beijing")

    assert captured.value.status_code == 503
    assert str(captured.value) == "无法获取当前云账号 ID：STS denied"


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_generated_bucket_owned_by_current_account_allows_upload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: StudioProvider,
) -> None:
    import tos

    fake_client = _FakeTosClient()
    fake_client.create_bucket_error = _TosBucketError("BucketAlreadyOwnedByYou")
    monkeypatch.setattr(tos, "TosClientV2", lambda **kwargs: fake_client)
    region = "cn-beijing" if provider == "volcengine" else "ap-southeast-1"
    store = TosKnowledgeUploadStore(
        provider=provider,
        resolve_credentials=lambda: ("ak", "sk", None),
        source={"VEADK_STUDIO_ACCOUNT_ID": "3001037806"},
    )
    source = tmp_path / "guide.pdf"
    source.write_bytes(b"%PDF-test")

    result = store.put(
        source=source,
        owner_id="alice",
        knowledge_id="kb-1",
        region=region,
        file_name="guide.pdf",
        mime_type="application/pdf",
    )

    assert fake_client.created_buckets == [result.bucket]
    assert len(fake_client.uploads) == 1


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_generated_bucket_owned_by_another_account_fails_before_upload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: StudioProvider,
) -> None:
    import tos

    fake_client = _FakeTosClient()
    fake_client.create_bucket_error = _TosBucketError("BucketAlreadyExists")
    monkeypatch.setattr(tos, "TosClientV2", lambda **kwargs: fake_client)
    region = "cn-beijing" if provider == "volcengine" else "ap-southeast-1"
    store = TosKnowledgeUploadStore(
        provider=provider,
        resolve_credentials=lambda: ("ak", "sk", None),
        source={"VEADK_STUDIO_ACCOUNT_ID": "3001037806"},
    )
    source = tmp_path / "guide.pdf"
    source.write_bytes(b"%PDF-test")

    with pytest.raises(KnowledgeAccessError) as captured:
        store.put(
            source=source,
            owner_id="alice",
            knowledge_id="kb-1",
            region=region,
            file_name="guide.pdf",
            mime_type="application/pdf",
        )

    assert captured.value.status_code == 503
    assert "已被其他账号占用" in str(captured.value)
    assert fake_client.uploads == []


def test_tos_upload_uses_byteplus_endpoint_and_user_scoped_random_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = _FakeTosClient()

    import tos

    def make_client(**kwargs: object) -> _FakeTosClient:
        fake_client.kwargs = kwargs
        return fake_client

    monkeypatch.setattr(tos, "TosClientV2", make_client)
    store = TosKnowledgeUploadStore(
        provider="byteplus",
        resolve_credentials=lambda: ("ak", "sk", "token"),
        source={
            "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
            "VEADK_STUDIO_TOS_REGION": "cn-hongkong",
        },
    )
    source = tmp_path / "upload.pdf"
    source.write_bytes(b"%PDF-test")

    result = store.put(
        source=source,
        owner_id="alice@example.com",
        knowledge_id="kb/support",
        region="ap-southeast-1",
        file_name="report.pdf",
        mime_type="application/pdf",
    )

    assert fake_client.kwargs == {
        "ak": "ak",
        "sk": "sk",
        "security_token": "token",
        "endpoint": "tos-cn-hongkong.bytepluses.com",
        "region": "cn-hongkong",
    }
    key = str(fake_client.uploads[0]["key"])
    assert key.startswith(
        "veadk-studio/v1/knowledge/users/alice%40example.com/kb%2Fsupport/"
    )
    random_segment, file_name = key.rsplit("/", 2)[-2:]
    assert len(random_segment) == 32
    assert all(char in "0123456789abcdef" for char in random_segment)
    assert file_name == "report.pdf"
    assert result.tos_path == f"studio-bucket/{key}"

    metadata = {
        "_veadk_source_url": "https://example.com/article?id=42",
        "_veadk_content_format": "markdown",
    }
    store.put_metadata(result, metadata)

    assert (
        store.get_metadata_managed(
            tos_path=result.tos_path,
            owner_id="alice@example.com",
            knowledge_id="kb/support",
            region="ap-southeast-1",
        )
        == metadata
    )
    assert (
        store.get_metadata_managed(
            tos_path=result.tos_path,
            owner_id="another-user",
            knowledge_id="kb/support",
            region="ap-southeast-1",
        )
        == {}
    )

    updated_metadata = {
        **metadata,
        "reviewed": True,
    }
    assert (
        store.put_metadata_managed(
            tos_path=result.tos_path,
            owner_id="alice@example.com",
            knowledge_id="kb/support",
            region="ap-southeast-1",
            metadata=updated_metadata,
        )
        is True
    )
    assert (
        store.get_metadata_managed(
            tos_path=result.tos_path,
            owner_id="alice@example.com",
            knowledge_id="kb/support",
            region="ap-southeast-1",
        )
        == updated_metadata
    )


@pytest.mark.parametrize("file_name", ["../secret.pdf", "folder\\secret.pdf"])
def test_tos_store_rejects_unsafe_file_name_even_without_route_validation(
    tmp_path: Path,
    file_name: str,
) -> None:
    store = TosKnowledgeUploadStore(
        provider="volcengine",
        resolve_credentials=lambda: ("ak", "sk", None),
        source={
            "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
            "VEADK_STUDIO_TOS_REGION": "cn-beijing",
        },
    )
    source = tmp_path / "upload.pdf"
    source.write_bytes(b"%PDF-test")

    with pytest.raises(KnowledgeAccessError) as captured:
        store.put(
            source=source,
            owner_id="alice",
            knowledge_id="kb-1",
            region="cn-beijing",
            file_name=file_name,
            mime_type="application/pdf",
        )

    assert captured.value.status_code == 400


def test_tos_upload_uses_region_scoped_bucket_when_studio_bucket_mismatches() -> None:
    store = TosKnowledgeUploadStore(
        provider="volcengine",
        resolve_credentials=lambda: ("ak", "sk", None),
        source={
            "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
            "VEADK_STUDIO_TOS_REGION": "cn-beijing",
            "VEADK_STUDIO_ACCOUNT_ID": "3001037806",
        },
    )

    target = store._target("cn-shanghai")

    assert target.mode == "generated"
    assert target.bucket == "agentkit-platform-3001037806-ve-cn-shanghai"


def test_tos_upload_prefers_explicit_knowledge_storage() -> None:
    store = TosKnowledgeUploadStore(
        provider="byteplus",
        resolve_credentials=lambda: ("ak", "sk", None),
        source={
            "VEADK_STUDIO_TOS_BUCKET": "studio-control-plane",
            "VEADK_STUDIO_TOS_REGION": "ap-southeast-1",
            "VEADK_KNOWLEDGE_TOS_BUCKET": "knowledge-data-plane",
            "VEADK_KNOWLEDGE_TOS_REGION": "cn-hongkong",
        },
    )

    target = store._target("ap-southeast-1")

    assert target.mode == "configured"
    assert target.bucket == "knowledge-data-plane"
    assert target.region == "cn-hongkong"


def test_tos_store_only_deletes_objects_in_the_owned_knowledge_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeTosClient()
    import tos

    monkeypatch.setattr(tos, "TosClientV2", lambda **kwargs: fake_client)
    store = TosKnowledgeUploadStore(
        provider="volcengine",
        resolve_credentials=lambda: ("ak", "sk", None),
        source={
            "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
            "VEADK_STUDIO_TOS_REGION": "cn-beijing",
        },
    )
    owned_path = (
        "tos://studio-bucket/veadk-studio/v1/knowledge/users/"
        "alice%40example.com/kb%2Fsupport/0123456789abcdef/source.pdf"
    )
    owned_key = owned_path.removeprefix("tos://studio-bucket/")
    metadata_key = (
        "veadk-studio/v1/knowledge/metadata/"
        f"{hashlib.sha256(f'studio-bucket/{owned_key}'.encode()).hexdigest()}.json"
    )

    for path in (owned_path.removeprefix("tos://"), owned_path):
        assert (
            store.delete_managed(
                tos_path=path,
                owner_id="alice@example.com",
                knowledge_id="kb/support",
                region="cn-beijing",
            )
            is True
        )
    for path in (
        (
            "other-bucket/veadk-studio/v1/knowledge/users/"
            "alice%40example.com/kb%2Fsupport/0123456789abcdef/source.pdf"
        ),
        (
            "tos://other-bucket/veadk-studio/v1/knowledge/users/"
            "alice%40example.com/kb%2Fsupport/0123456789abcdef/source.pdf"
        ),
        "studio-bucket/external/source.pdf",
        "tos://studio-bucket/external/source.pdf",
    ):
        assert (
            store.delete_managed(
                tos_path=path,
                owner_id="alice@example.com",
                knowledge_id="kb/support",
                region="cn-beijing",
            )
            is False
        )
    assert fake_client.deleted == [
        {
            "bucket": "studio-bucket",
            "key": metadata_key,
        },
        {
            "bucket": "studio-bucket",
            "key": "veadk-studio/v1/knowledge/users/"
            "alice%40example.com/kb%2Fsupport/0123456789abcdef/source.pdf",
        },
        {
            "bucket": "studio-bucket",
            "key": metadata_key,
        },
        {
            "bucket": "studio-bucket",
            "key": "veadk-studio/v1/knowledge/users/"
            "alice%40example.com/kb%2Fsupport/0123456789abcdef/source.pdf",
        },
    ]


def test_tos_store_legacy_cleanup_accepts_one_encoded_owner_segment_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeTosClient()
    import tos

    monkeypatch.setattr(tos, "TosClientV2", lambda **kwargs: fake_client)
    store = TosKnowledgeUploadStore(
        provider="volcengine",
        resolve_credentials=lambda: ("ak", "sk", None),
        source={
            "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
            "VEADK_STUDIO_TOS_REGION": "cn-beijing",
        },
    )
    valid_key = (
        "veadk-studio/v1/knowledge/users/legacy%40owner/kb-legacy/"
        "0123456789abcdef/source.pdf"
    )

    assert (
        store.delete_managed(
            tos_path=f"studio-bucket/{valid_key}",
            owner_id="",
            knowledge_id="kb-legacy",
            region="cn-beijing",
        )
        is True
    )
    for forged_path in (
        f"other-bucket/{valid_key}",
        "studio-bucket/external/users/legacy%40owner/kb-legacy/file.pdf",
        (
            "studio-bucket/veadk-studio/v1/knowledge/users/legacy%40owner/"
            "kb-other/file.pdf"
        ),
        (
            "studio-bucket/veadk-studio/v1/knowledge/users/legacy/extra/"
            "kb-legacy/file.pdf"
        ),
        ("studio-bucket/veadk-studio/v1/knowledge/users/legacy%ZZ/kb-legacy/file.pdf"),
    ):
        assert (
            store.delete_managed(
                tos_path=forged_path,
                owner_id="",
                knowledge_id="kb-legacy",
                region="cn-beijing",
            )
            is False
        )

    assert fake_client.deleted == [
        {
            "bucket": "studio-bucket",
            "key": (
                "veadk-studio/v1/knowledge/metadata/"
                f"{hashlib.sha256(f'studio-bucket/{valid_key}'.encode()).hexdigest()}.json"
            ),
        },
        {"bucket": "studio-bucket", "key": valid_key},
    ]


class _AgentKitGateway:
    def __init__(self, record: KnowledgeRecord) -> None:
        self.record = record
        self.connection_calls = 0

    def list(self, **kwargs):
        del kwargs
        return [self.record], ""

    def get(self, knowledge_id: str, *, region: str) -> KnowledgeRecord:
        del region
        if knowledge_id != self.record.id:
            raise KnowledgeAccessError("missing", status_code=404)
        return self.record

    def add(
        self,
        body,
        *,
        description: str,
        region: str,
        provider_knowledge_id: str = "",
        project_name: str = "",
    ) -> str:
        del body, description, region, provider_knowledge_id, project_name
        return self.record.id

    def update_description(
        self,
        knowledge_id: str,
        *,
        description: str,
        region: str,
    ) -> None:
        del knowledge_id, region
        self.record = replace(self.record, description=description)

    def delete(self, knowledge_id: str, *, region: str) -> None:
        del knowledge_id, region

    def connection(self, knowledge_id: str, *, region: str) -> ProviderConnection:
        del knowledge_id
        self.connection_calls += 1
        return ProviderConnection(
            provider_type="VIKINGDB_KNOWLEDGE",
            provider_knowledge_id=self.record.provider_knowledge_id,
            region=region,
        )


class _DocumentGateway:
    def __init__(self) -> None:
        self.created: list[CreateDocumentBody] = []
        self.failure: Exception | None = None
        self.deleted: list[str] = []

    def list(self, **kwargs):
        del kwargs
        return [], False

    def get(self, document_id: str):
        return {"id": document_id, "tosPath": "tos://bucket/object.pdf"}

    def preview(self, document_id: str, *, offset: int, limit: int):
        del document_id, offset, limit
        return [], False

    def create(self, body: CreateDocumentBody):
        if self.failure is not None:
            raise self.failure
        self.created.append(body)
        return {"id": "doc-1", "tosPath": body.tos_path}

    def update_metadata(self, document_id: str, metadata):
        return {"id": document_id, "metadata": metadata}

    def delete(self, document_id: str) -> None:
        self.deleted.append(document_id)


class _UploadStore:
    max_file_bytes = 12

    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []
        self.contents: list[bytes] = []
        self.deleted: list[StoredKnowledgeUpload] = []
        self.managed_deletes: list[dict[str, object]] = []
        self.cleanup_failure: Exception | None = None
        self.metadata: dict[str, dict[str, object]] = {}

    def put(self, **kwargs) -> StoredKnowledgeUpload:
        self.puts.append(kwargs)
        self.contents.append(Path(kwargs["source"]).read_bytes())
        return StoredKnowledgeUpload(
            tos_path="tos://bucket/object.pdf",
            bucket="bucket",
            key="object.pdf",
            region="cn-beijing",
        )

    def delete(self, upload: StoredKnowledgeUpload) -> None:
        self.deleted.append(upload)
        self.metadata.pop(upload.tos_path, None)

    def put_metadata(
        self,
        upload: StoredKnowledgeUpload,
        metadata: dict[str, object],
    ) -> None:
        self.metadata[upload.tos_path] = metadata

    def get_metadata_managed(self, **kwargs) -> dict[str, object]:
        return self.metadata.get(str(kwargs["tos_path"]), {})

    def put_metadata_managed(self, **kwargs) -> bool:
        self.metadata[str(kwargs["tos_path"])] = dict(kwargs["metadata"])
        return True

    def delete_managed(self, **kwargs) -> bool:
        self.managed_deletes.append(kwargs)
        if self.cleanup_failure is not None:
            raise self.cleanup_failure
        return True


def _knowledge_service() -> tuple[KnowledgeService, _DocumentGateway, _UploadStore]:
    identity = KnowledgeIdentity("user-1", "Alice")
    record = KnowledgeRecord(
        id="kb-1",
        name="support",
        description=encode_owned_description(
            "Support",
            identity,
            signing_key=SIGNING_KEY,
            knowledge_id="kb-1",
            provider_type="VIKINGDB_KNOWLEDGE",
            provider_knowledge_id="provider-1",
            project_name="default",
            region="cn-beijing",
        ),
        provider_type="VIKINGDB_KNOWLEDGE",
        provider_knowledge_id="provider-1",
        project_name="default",
        region="cn-beijing",
    )
    documents = _DocumentGateway()
    uploads = _UploadStore()
    service = KnowledgeService(
        _AgentKitGateway(record),
        lambda record, connection: documents,
        signing_key=SIGNING_KEY,
        upload_store=uploads,
    )
    return service, documents, uploads


def test_upload_route_authorizes_then_adds_tos_document() -> None:
    service, documents, uploads = _knowledge_service()
    app = FastAPI()

    def identity(request: Request) -> KnowledgeIdentity:
        return KnowledgeIdentity(request.headers.get("x-owner", "user-1"), "User")

    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=identity,
        region_resolver=lambda value: value or "cn-beijing",
    )
    client = TestClient(app)

    response = client.post(
        "/web/knowledge-bases/kb-1/documents/upload",
        headers={"x-owner": "user-1"},
        files={"file": ("guide.pdf", b"%PDF-test", "application/pdf")},
        data={"metadata": '{"team":"support"}'},
    )

    assert response.status_code == 201
    assert len(uploads.puts) == 1
    assert documents.created[0].source_type == "tos"
    assert documents.created[0].tos_path == "tos://bucket/object.pdf"
    assert documents.created[0].metadata == {
        "team": "support",
        "_veadk_file_size_bytes": 9,
    }


def test_upload_route_blocks_cross_owner_before_persistent_upload() -> None:
    service, _, uploads = _knowledge_service()
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity("user-2", "Mallory"),
        region_resolver=lambda value: value or "cn-beijing",
    )

    response = TestClient(app).post(
        "/web/knowledge-bases/kb-1/documents/upload",
        files={"file": ("guide.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 403
    assert uploads.puts == []


def test_upload_route_enforces_streamed_size_limit() -> None:
    service, _, uploads = _knowledge_service()
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity("user-1", "Alice"),
        region_resolver=lambda value: value or "cn-beijing",
    )

    response = TestClient(app).post(
        "/web/knowledge-bases/kb-1/documents/upload",
        files={"file": ("guide.pdf", b"%PDF-too-large", "application/pdf")},
    )

    assert response.status_code == 413
    assert uploads.puts == []


def test_agentkit_failure_removes_new_tos_object(tmp_path: Path) -> None:
    service, documents, uploads = _knowledge_service()
    documents.failure = RuntimeError("provider failed")
    source = tmp_path / "guide.pdf"
    source.write_bytes(b"%PDF-test")

    with pytest.raises(RuntimeError, match="provider failed"):
        service.upload_document(
            "kb-1",
            identity=KnowledgeIdentity("user-1", "Alice"),
            region="cn-beijing",
            source=source,
            file_name="guide.pdf",
            mime_type="application/pdf",
            name="guide.pdf",
            document_type="pdf",
            metadata={},
        )

    assert uploads.deleted == [
        StoredKnowledgeUpload(
            tos_path="tos://bucket/object.pdf",
            bucket="bucket",
            key="object.pdf",
            region="cn-beijing",
        )
    ]


def test_update_document_keeps_internal_metadata_and_updates_sidecar() -> None:
    service, _documents, uploads = _knowledge_service()
    uploads.metadata["tos://bucket/object.pdf"] = {
        "team": "support",
        "_veadk_source_url": "https://example.com/guide",
        "_veadk_file_size_bytes": 42,
    }

    updated = service.update_document(
        "kb-1",
        "doc-1",
        UpdateDocumentBody(metadata={"team": "platform", "reviewed": True}),
        identity=KnowledgeIdentity("user-1", "Alice"),
        region="cn-beijing",
    )

    assert updated["metadata"] == {
        "team": "platform",
        "reviewed": True,
        "_veadk_source_url": "https://example.com/guide",
        "_veadk_file_size_bytes": 42,
    }
    assert updated["url"] == "https://example.com/guide"
    assert updated["sizeBytes"] == 42
    assert uploads.metadata["tos://bucket/object.pdf"] == updated["metadata"]


def test_delete_document_removes_managed_source_before_provider_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, documents, uploads = _knowledge_service()
    events: list[str] = []
    original_delete_managed = uploads.delete_managed
    original_delete_document = documents.delete
    monkeypatch.setattr(
        uploads,
        "delete_managed",
        lambda **kwargs: (
            events.append("storage"),
            original_delete_managed(**kwargs),
        )[1],
    )
    monkeypatch.setattr(
        documents,
        "delete",
        lambda document_id: (
            events.append("provider"),
            original_delete_document(document_id),
        )[1],
    )

    service.delete_document(
        "kb-1",
        "doc-1",
        identity=KnowledgeIdentity("user-1", "Alice"),
        region="cn-beijing",
    )

    assert documents.deleted == ["doc-1"]
    assert events == ["storage", "provider"]
    assert uploads.managed_deletes == [
        {
            "tos_path": "tos://bucket/object.pdf",
            "owner_id": "user-1",
            "knowledge_id": "kb-1",
            "region": "cn-beijing",
        }
    ]


def test_admin_delete_on_legacy_association_requests_owner_agnostic_cleanup() -> None:
    record = KnowledgeRecord(
        id="kb-legacy",
        name="legacy",
        description="Legacy association without owner metadata",
        provider_type="VIKINGDB_KNOWLEDGE",
        provider_knowledge_id="provider-legacy",
        project_name="default",
        region="cn-beijing",
    )
    documents = _DocumentGateway()
    uploads = _UploadStore()
    service = KnowledgeService(
        _AgentKitGateway(record),
        lambda record, connection: documents,
        signing_key=SIGNING_KEY,
        upload_store=uploads,
    )

    service.delete_document(
        "kb-legacy",
        "doc-1",
        identity=KnowledgeIdentity("admin-1", "Admin", is_admin=True),
        region="cn-beijing",
    )

    assert documents.deleted == ["doc-1"]
    assert uploads.managed_deletes == [
        {
            "tos_path": "tos://bucket/object.pdf",
            "owner_id": "",
            "knowledge_id": "kb-legacy",
            "region": "cn-beijing",
        }
    ]


def test_source_cleanup_failure_is_returned_before_provider_deletion() -> None:
    service, documents, uploads = _knowledge_service()
    uploads.cleanup_failure = RuntimeError("TOS unavailable")

    with pytest.raises(RuntimeError, match="TOS unavailable"):
        service.delete_document(
            "kb-1",
            "doc-1",
            identity=KnowledgeIdentity("user-1", "Alice"),
            region="cn-beijing",
        )

    assert documents.deleted == []


def test_delete_route_returns_source_cleanup_error_details() -> None:
    service, documents, uploads = _knowledge_service()
    uploads.cleanup_failure = RuntimeError("TOS unavailable")
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity("user-1", "Alice"),
        region_resolver=lambda value: value or "cn-beijing",
    )

    response = TestClient(app).delete(
        "/web/knowledge-bases/kb-1/documents/doc-1",
        params={"region": "cn-beijing"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "status": 502,
        "errorCode": "KNOWLEDGE_UPSTREAM_ERROR",
        "message": "TOS unavailable",
        "requestId": "",
        "diagnostics": {
            "errors": [{"exceptionType": "RuntimeError"}],
        },
    }
    assert documents.deleted == []


class _WebImporter:
    def __init__(
        self,
        result: WebImportResult | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.result = result or WebImportResult(
            markdown="# Imported",
            title="Imported page",
            final_url="https://example.com/article",
        )
        self.failure = failure
        self.urls: list[str] = []

    async def import_url(self, url: str) -> WebImportResult:
        self.urls.append(url)
        if self.failure is not None:
            raise self.failure
        return self.result


def _web_import_client(
    service: KnowledgeService,
    importer: _WebImporter,
    *,
    owner_id: str = "user-1",
) -> TestClient:
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity(owner_id, "User"),
        region_resolver=lambda value: value or "cn-beijing",
        web_importer=importer,
    )
    return TestClient(app)


def test_web_import_authorizes_then_uploads_markdown_through_tos() -> None:
    service, documents, uploads = _knowledge_service()
    uploads.max_file_bytes = 1024
    importer = _WebImporter(
        WebImportResult(
            markdown="# Service guide\n\nImported body.",
            title="Service guide",
            final_url=(
                "https://example.com/guide?id=42&token=secret-value"
                "&X-Amz-Signature=signed-secret#section"
            ),
        )
    )

    response = _web_import_client(service, importer).post(
        "/web/knowledge-bases/kb-1/documents",
        json={
            "sourceType": "url",
            "url": "https://example.com/guide?id=42&token=secret-value",
            "metadata": {"team": "support", "_veadk_source_title": "spoofed"},
        },
    )

    assert response.status_code == 201
    assert importer.urls == ["https://example.com/guide?id=42&token=secret-value"]
    assert uploads.contents == [b"# Service guide\n\nImported body."]
    uploaded_source = uploads.puts[0]["source"]
    assert isinstance(uploaded_source, Path)
    assert not uploaded_source.exists()
    assert uploads.puts[0]["mime_type"] == "text/plain"
    assert str(uploads.puts[0]["file_name"]).endswith(".txt")
    created = documents.created[0]
    assert created.source_type == "tos"
    assert created.document_type == "txt"
    assert created.name == "Service guide"
    assert created.metadata["team"] == "support"
    assert created.metadata["_veadk_source_url"] == ("https://example.com/guide?id=42")
    assert created.metadata["_veadk_source_title"] == "Service guide"
    assert created.metadata["_veadk_content_format"] == "markdown"
    assert created.metadata["_veadk_fetched_at"]
    assert response.json()["url"] == "https://example.com/guide?id=42"
    assert "secret-value" not in response.text
    assert "signed-secret" not in response.text


def test_viking_document_restores_sanitized_web_source_url_from_metadata() -> None:
    item = SimpleNamespace(
        doc_id="doc-web",
        doc_name="Imported page",
        doc_type="txt",
        status="ready",
        url="https://tos.example.com/generated-source.txt?signature=temporary",
        tos_path="tos://bucket/web-source.txt",
        fields=[
            SimpleNamespace(
                field_name="_veadk_source_url",
                field_val="https://example.com/guide?id=42",
            )
        ],
        create_time="",
        update_time="",
    )

    result = _document(item)

    assert result["url"] == "https://example.com/guide?id=42"


def test_web_import_blocks_cross_owner_before_fetch_or_upload() -> None:
    service, documents, uploads = _knowledge_service()
    importer = _WebImporter()

    response = _web_import_client(
        service,
        importer,
        owner_id="user-2",
    ).post(
        "/web/knowledge-bases/kb-1/documents",
        json={"sourceType": "url", "url": "https://example.com/private"},
    )

    assert response.status_code == 403
    assert importer.urls == []
    assert uploads.puts == []
    assert documents.created == []


def test_web_import_provider_failure_rolls_back_tos_object() -> None:
    service, documents, uploads = _knowledge_service()
    uploads.max_file_bytes = 1024
    documents.failure = RuntimeError("provider failed")

    response = _web_import_client(service, _WebImporter()).post(
        "/web/knowledge-bases/kb-1/documents",
        json={"sourceType": "url", "url": "https://example.com/article"},
    )

    assert response.status_code == 502
    assert len(uploads.puts) == 1
    assert len(uploads.deleted) == 1
    uploaded_source = uploads.puts[0]["source"]
    assert isinstance(uploaded_source, Path)
    assert not uploaded_source.exists()
    detail = response.json()["detail"]
    assert detail["status"] == 502
    assert detail["errorCode"] == "KNOWLEDGE_UPSTREAM_ERROR"


def test_web_import_failure_is_structured_and_does_not_leak_credentials() -> None:
    service, documents, uploads = _knowledge_service()
    importer = _WebImporter(
        failure=WebImportFetchError(
            "request failed token=secret-value Authorization: Bearer top-secret"
        )
    )

    response = _web_import_client(service, importer).post(
        "/web/knowledge-bases/kb-1/documents",
        json={
            "sourceType": "url",
            "url": "https://example.com/article?token=secret-value",
        },
    )

    assert response.status_code == 502
    assert uploads.puts == []
    assert documents.created == []
    detail = response.json()["detail"]
    assert detail["status"] == 502
    assert detail["errorCode"] == "KNOWLEDGE_WEB_FETCH_FAILED"
    assert detail["requestId"] == ""
    assert "diagnostics" in detail
    assert "secret-value" not in response.text
    assert "top-secret" not in response.text
