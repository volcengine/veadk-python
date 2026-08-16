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

"""Private TOS uploads used by AgentKit knowledge documents."""

from __future__ import annotations

import codecs
import hashlib
import json
import os
import re
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from urllib.parse import quote, unquote, urlparse
from uuid import uuid4

from frontend.server.storage import (
    STUDIO_STORAGE_ROOT_PREFIX,
    StudioProvider,
    StudioStorageConfig,
)
from frontend.server.storage.tos import create_tos_client_factory

from .regions import provider_data_region
from .service import KnowledgeAccessError, StoredKnowledgeUpload

CredentialResolver = Callable[[], tuple[str, str, str | None]]

DEFAULT_MAX_UPLOAD_BYTES = 200 * 1024 * 1024
_DEFAULT_PREFIX = f"{STUDIO_STORAGE_ROOT_PREFIX}/knowledge"
_GENERIC_MIME_TYPES = {"", "application/octet-stream"}
_MAX_METADATA_BYTES = 64 * 1024
_GENERATED_BUCKET_PROVIDER_TAG = {
    "volcengine": "ve",
    "byteplus": "bp",
}
_SUPPORTED_FILE_MIME_TYPES: dict[str, frozenset[str]] = {
    ".docx": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
        }
    ),
    ".jpeg": frozenset({"image/jpeg"}),
    ".jpg": frozenset({"image/jpeg"}),
    ".pdf": frozenset({"application/pdf"}),
    ".png": frozenset({"image/png"}),
    ".pptx": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/zip",
        }
    ),
    ".txt": frozenset({"text/plain"}),
    ".xlsx": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/zip",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class ValidatedKnowledgeUpload:
    file_name: str
    suffix: str
    mime_type: str
    document_type: str


def validate_knowledge_upload(
    file_name: str,
    declared_mime_type: str,
) -> ValidatedKnowledgeUpload:
    """Validate the browser-controlled filename and MIME declaration."""
    candidate = file_name.strip()
    if (
        not candidate
        or len(candidate) > 255
        or candidate in {".", ".."}
        or "/" in candidate
        or "\\" in candidate
        or "\x00" in candidate
        or any(ord(char) < 32 for char in candidate)
    ):
        raise KnowledgeAccessError("文件名无效，请重新选择文件。", status_code=400)
    suffix = Path(candidate).suffix.casefold()
    allowed_mime_types = _SUPPORTED_FILE_MIME_TYPES.get(suffix)
    if allowed_mime_types is None:
        raise KnowledgeAccessError(
            "暂不支持此文件格式。请上传 PNG、JPG、PDF、PPTX、DOCX、XLSX 或 TXT 文件。",
            status_code=415,
        )
    mime_type = declared_mime_type.split(";", 1)[0].strip().casefold()
    if mime_type not in _GENERIC_MIME_TYPES and mime_type not in allowed_mime_types:
        raise KnowledgeAccessError(
            "文件格式与文件类型不一致，请检查后重新上传。",
            status_code=415,
        )
    return ValidatedKnowledgeUpload(
        file_name=candidate,
        suffix=suffix,
        mime_type=mime_type or "application/octet-stream",
        document_type=suffix.removeprefix("."),
    )


_OOXML_REQUIRED_PREFIX = {
    ".docx": "word/",
    ".pptx": "ppt/",
    ".xlsx": "xl/",
}
_TEXT_ALLOWED_CONTROLS = {"\t", "\n", "\r", "\f"}


def _is_safe_utf8_text(source: Path) -> bool:
    decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")
    try:
        with source.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                text = decoder.decode(chunk)
                if any(
                    (ord(char) < 32 or 0x7F <= ord(char) <= 0x9F)
                    and char not in _TEXT_ALLOWED_CONTROLS
                    for char in text
                ):
                    return False
            tail = decoder.decode(b"", final=True)
    except (OSError, UnicodeDecodeError):
        return False
    return not any(
        (ord(char) < 32 or 0x7F <= ord(char) <= 0x9F)
        and char not in _TEXT_ALLOWED_CONTROLS
        for char in tail
    )


def _is_expected_ooxml(source: Path, suffix: str) -> bool:
    required_prefix = _OOXML_REQUIRED_PREFIX[suffix]
    try:
        with zipfile.ZipFile(source) as archive:
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False
    return "[Content_Types].xml" in names and any(
        name.startswith(required_prefix) for name in names
    )


def validate_knowledge_upload_content(
    source: Path,
    validated: ValidatedKnowledgeUpload,
) -> None:
    """Reject files whose bytes do not match the validated extension."""
    try:
        with source.open("rb") as stream:
            head = stream.read(1024)
    except OSError as error:
        raise KnowledgeAccessError(
            "无法读取上传文件，请重新选择文件。",
            status_code=400,
        ) from error

    suffix = validated.suffix
    matches = (
        head.startswith(b"\x89PNG\r\n\x1a\n")
        if suffix == ".png"
        else head.startswith(b"\xff\xd8\xff")
        if suffix in {".jpg", ".jpeg"}
        else head.lstrip(b"\xef\xbb\xbf\x00\t\r\n ").startswith(b"%PDF-")
        if suffix == ".pdf"
        else _is_expected_ooxml(source, suffix)
        if suffix in _OOXML_REQUIRED_PREFIX
        else _is_safe_utf8_text(source)
        if suffix == ".txt"
        else False
    )
    if not matches:
        raise KnowledgeAccessError(
            "文件内容与扩展名不一致，或文件已损坏。",
            status_code=415,
        )


@dataclass(frozen=True, slots=True)
class _UploadTarget:
    bucket: str
    region: str
    endpoint: str
    prefix: str
    mode: Literal["configured", "generated"]


def _parse_tos_path(value: str) -> tuple[str, str] | None:
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.casefold().startswith("tos://"):
        parsed = urlparse(candidate)
        if (
            parsed.scheme.casefold() != "tos"
            or not parsed.netloc
            or not parsed.path
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or parsed.hostname != parsed.netloc
        ):
            return None
        return parsed.netloc, parsed.path.lstrip("/")
    if candidate.startswith("/") or "\\" in candidate or "://" in candidate:
        return None
    bucket, separator, key = candidate.partition("/")
    if (
        not separator
        or not key
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]*[a-z0-9]", bucket)
    ):
        return None
    return bucket, key


def _metadata_key(target: _UploadTarget, bucket: str, key: str) -> str:
    digest = hashlib.sha256(f"{bucket}/{key}".encode()).hexdigest()
    return f"{target.prefix.strip('/')}/metadata/{digest}.json"


class TosKnowledgeUploadStore:
    """Upload source files to account-owned TOS for Viking ingestion."""

    def __init__(
        self,
        *,
        provider: StudioProvider,
        resolve_credentials: CredentialResolver,
        source: Mapping[str, str] | None = None,
    ) -> None:
        self._provider: StudioProvider = provider
        self._resolve_credentials = resolve_credentials
        self._environment = source
        environment = source if source is not None else os.environ
        try:
            self.max_file_bytes = int(
                environment.get(
                    "VEADK_KNOWLEDGE_MAX_FILE_BYTES",
                    str(DEFAULT_MAX_UPLOAD_BYTES),
                )
            )
        except ValueError as error:
            raise ValueError(
                "VEADK_KNOWLEDGE_MAX_FILE_BYTES must be an integer"
            ) from error
        if self.max_file_bytes <= 0:
            raise ValueError("VEADK_KNOWLEDGE_MAX_FILE_BYTES must be positive")
        self._prepared_targets: set[tuple[str, str]] = set()
        self._lock = RLock()

    def put(
        self,
        *,
        source: Path,
        owner_id: str,
        knowledge_id: str,
        region: str,
        file_name: str,
        mime_type: str,
    ) -> StoredKnowledgeUpload:
        validated = validate_knowledge_upload(file_name, mime_type)
        validate_knowledge_upload_content(source, validated)
        target = self._target(region)
        client = self._client(target)
        self._prepare_target(client, target)
        owner_segment = quote(owner_id, safe="")[:512]
        knowledge_segment = quote(knowledge_id, safe="")[:512]
        key = "/".join(
            (
                target.prefix.strip("/"),
                "users",
                owner_segment,
                knowledge_segment,
                uuid4().hex,
                validated.file_name,
            )
        )
        try:
            client.put_object_from_file(
                bucket=target.bucket,
                key=key,
                file_path=str(source),
                content_type=validated.mime_type,
            )
        except Exception as error:
            raise KnowledgeAccessError(
                "文件上传到知识库存储失败，请稍后重试。",
                status_code=502,
            ) from error
        return StoredKnowledgeUpload(
            tos_path=f"{target.bucket}/{key}",
            bucket=target.bucket,
            key=key,
            region=target.region,
        )

    def delete(self, upload: StoredKnowledgeUpload) -> None:
        target = self._target(upload.region)
        client = self._client(target)
        client.delete_object(bucket=upload.bucket, key=upload.key)
        client.delete_object(
            bucket=upload.bucket,
            key=_metadata_key(target, upload.bucket, upload.key),
        )

    def put_metadata(
        self,
        upload: StoredKnowledgeUpload,
        metadata: dict[str, Any],
    ) -> None:
        target = self._target(upload.region)
        self._put_metadata(target, upload.bucket, upload.key, metadata)

    def _put_metadata(
        self,
        target: _UploadTarget,
        bucket: str,
        key: str,
        metadata: dict[str, Any],
    ) -> None:
        content = json.dumps(
            metadata,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(content) > _MAX_METADATA_BYTES:
            raise KnowledgeAccessError("知识元数据不能超过 64 KB。", status_code=413)
        self._client(target).put_object(
            bucket=bucket,
            key=_metadata_key(target, bucket, key),
            content=content,
            content_type="application/json",
        )

    def put_metadata_managed(
        self,
        *,
        tos_path: str,
        owner_id: str,
        knowledge_id: str,
        region: str,
        metadata: dict[str, Any],
    ) -> bool:
        resolved = self._managed_key(
            tos_path=tos_path,
            owner_id=owner_id,
            knowledge_id=knowledge_id,
            region=region,
        )
        if resolved is None:
            return False
        target, bucket, key = resolved
        self._put_metadata(target, bucket, key, metadata)
        return True

    def get_metadata_managed(
        self,
        *,
        tos_path: str,
        owner_id: str,
        knowledge_id: str,
        region: str,
    ) -> dict[str, Any]:
        resolved = self._managed_key(
            tos_path=tos_path,
            owner_id=owner_id,
            knowledge_id=knowledge_id,
            region=region,
        )
        if resolved is None:
            return {}
        target, bucket, key = resolved
        client = self._client(target)
        try:
            response = client.get_object(
                bucket=bucket,
                key=_metadata_key(target, bucket, key),
            )
        except Exception as error:
            if int(getattr(error, "status_code", 0) or 0) == 404:
                return {}
            raise
        content = response.read() if hasattr(response, "read") else b"".join(response)
        if len(content) > _MAX_METADATA_BYTES:
            raise KnowledgeAccessError("知识元数据超过 64 KB。", status_code=502)
        try:
            value = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise KnowledgeAccessError("知识元数据已损坏。", status_code=502) from error
        if not isinstance(value, dict) or not all(
            isinstance(key, str) for key in value
        ):
            raise KnowledgeAccessError("知识元数据格式无效。", status_code=502)
        return value

    def delete_managed(
        self,
        *,
        tos_path: str,
        owner_id: str,
        knowledge_id: str,
        region: str,
    ) -> bool:
        """Delete a source object only when it belongs to this Studio scope."""
        resolved = self._managed_key(
            tos_path=tos_path,
            owner_id=owner_id,
            knowledge_id=knowledge_id,
            region=region,
        )
        if resolved is None:
            return False
        target, bucket, key = resolved
        client = self._client(target)
        client.delete_object(bucket=bucket, key=key)
        client.delete_object(
            bucket=bucket,
            key=_metadata_key(target, bucket, key),
        )
        return True

    def _managed_key(
        self,
        *,
        tos_path: str,
        owner_id: str,
        knowledge_id: str,
        region: str,
    ) -> tuple[_UploadTarget, str, str] | None:
        resolved = _parse_tos_path(tos_path)
        if resolved is None:
            return None
        bucket, key = resolved
        target = self._target(region)
        if bucket != target.bucket:
            return None
        users_prefix = f"{target.prefix.strip('/')}/users/"
        knowledge_segment = quote(knowledge_id, safe="")[:512]
        if owner_id:
            expected_prefix = (
                f"{users_prefix}{quote(owner_id, safe='')[:512]}/{knowledge_segment}/"
            )
            if not key.startswith(expected_prefix) or key == expected_prefix:
                return None
        else:
            if not key.startswith(users_prefix):
                return None
            owner_segment, separator, scoped_key = key[len(users_prefix) :].partition(
                "/"
            )
            try:
                decoded_owner = unquote(owner_segment, errors="strict")
            except UnicodeDecodeError:
                return None
            expected_knowledge_prefix = f"{knowledge_segment}/"
            if (
                not separator
                or not decoded_owner
                or owner_segment in {".", ".."}
                or quote(decoded_owner, safe="") != owner_segment
                or not scoped_key.startswith(expected_knowledge_prefix)
                or scoped_key == expected_knowledge_prefix
            ):
                return None
        return target, bucket, key

    def _target(self, region: str) -> _UploadTarget:
        normalized_region = provider_data_region(self._provider, region.strip())
        if not normalized_region:
            raise KnowledgeAccessError(
                "知识库地域为空，无法上传文件。", status_code=409
            )
        environment = self._environment if self._environment is not None else os.environ
        knowledge_storage_keys = {
            "VEADK_STUDIO_TOS_BUCKET": "VEADK_KNOWLEDGE_TOS_BUCKET",
            "VEADK_STUDIO_TOS_REGION": "VEADK_KNOWLEDGE_TOS_REGION",
        }
        knowledge_storage_requested = any(
            str(environment.get(key) or "").strip()
            for key in knowledge_storage_keys.values()
        )
        if knowledge_storage_requested:
            knowledge_environment = dict(environment)
            for target_key, source_key in knowledge_storage_keys.items():
                knowledge_environment[target_key] = str(
                    environment.get(source_key) or ""
                ).strip()
            configured = StudioStorageConfig.from_env(
                self._provider,
                knowledge_environment,
            )
            if not configured.configured:
                raise KnowledgeAccessError(
                    "知识库存储配置不完整，请同时配置 Bucket 和地域。",
                    status_code=503,
                )
            if configured.region != normalized_region:
                raise KnowledgeAccessError(
                    "知识库存储地域与知识库地域不一致，请联系管理员调整配置。",
                    status_code=409,
                )
        else:
            configured = StudioStorageConfig.from_env(self._provider, environment)
        prefix = (
            str(environment.get("VEADK_KNOWLEDGE_TOS_PREFIX") or "").strip("/")
            or _DEFAULT_PREFIX
        )
        if configured.configured and configured.region == normalized_region:
            return _UploadTarget(
                bucket=configured.bucket,
                region=configured.region,
                endpoint=configured.endpoint,
                prefix=prefix,
                mode="configured",
            )

        from agentkit.toolkit.volcengine.services.tos_service import TOSService

        base_bucket = str(TOSService.generate_bucket_name() or "").strip().casefold()
        region_segment = "-".join(
            part
            for part in re.split(r"[^a-z0-9]+", normalized_region.casefold())
            if part
        )
        suffix = f"-{_GENERATED_BUCKET_PROVIDER_TAG[self._provider]}-{region_segment}"
        bucket = f"{base_bucket[: 63 - len(suffix)].rstrip('-')}{suffix}"
        if len(bucket) < 3 or not re.fullmatch(r"[a-z0-9][a-z0-9-]*[a-z0-9]", bucket):
            raise KnowledgeAccessError(
                "无法生成有效的知识库存储桶名称，请配置 Studio TOS 存储。",
                status_code=503,
            )
        domain = "bytepluses.com" if self._provider == "byteplus" else "volces.com"
        return _UploadTarget(
            bucket=bucket,
            region=normalized_region,
            endpoint=f"tos-{normalized_region}.{domain}",
            prefix=prefix,
            mode="generated",
        )

    def _client(self, target: _UploadTarget) -> Any:
        config = StudioStorageConfig(
            provider=self._provider,
            bucket=target.bucket,
            region=target.region,
            endpoint=target.endpoint,
        )
        return create_tos_client_factory(config, self._resolve_credentials)()

    def _prepare_target(self, client: Any, target: _UploadTarget) -> None:
        cache_key = (target.bucket, target.region)
        with self._lock:
            if cache_key in self._prepared_targets:
                return
            if target.mode == "generated":
                try:
                    client.create_bucket(bucket=target.bucket)
                except Exception as error:
                    status_code = getattr(error, "status_code", None)
                    code = str(getattr(error, "code", "") or "")
                    if status_code == 409 and code == "BucketAlreadyOwnedByYou":
                        pass
                    elif status_code == 409 and code == "BucketAlreadyExists":
                        raise KnowledgeAccessError(
                            "自动生成的知识库存储桶名称已被其他账号占用，"
                            "请配置 Studio TOS 存储后重试。",
                            status_code=503,
                        ) from error
                    else:
                        raise KnowledgeAccessError(
                            "无法准备知识库文件存储，请联系管理员检查 TOS 权限。",
                            status_code=503,
                        ) from error
            self._prepared_targets.add(cache_key)


__all__ = [
    "DEFAULT_MAX_UPLOAD_BYTES",
    "TosKnowledgeUploadStore",
    "ValidatedKnowledgeUpload",
    "validate_knowledge_upload",
]
