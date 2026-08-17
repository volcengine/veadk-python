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

"""Authorization and orchestration for AgentKit knowledge resources."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Protocol
from urllib.parse import urlsplit

from .models import (
    CreateDocumentBody,
    CreateKnowledgeBaseBody,
    UpdateDocumentBody,
    UpdateKnowledgeBaseBody,
)

_LEGACY_METADATA_PATTERN = re.compile(
    r"(?:\n\n)?\[veadk-meta:(?P<version>v[12]):(?P<payload>[A-Za-z0-9_-]+)\]\s*$"
)
_COMPACT_METADATA_PATTERN = re.compile(
    r"(?:\s)?veadkmeta_v3_"
    r"(?P<owner>[A-Za-z0-9_-]+|0)\."
    r"(?P<provider_name>[A-Za-z0-9_]+|0)\."
    r"(?P<flags>[0-9]+)\."
    r"(?P<signature>[A-Za-z0-9_-]+)$"
)
_PROVIDER_BINDING_LOCK = RLock()
_DOCUMENT_CLEANUP_PAGE_SIZE = 100
logger = logging.getLogger(__name__)


class KnowledgeAccessError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class KnowledgeProvisionError(RuntimeError):
    def __init__(self, failures: list[dict[str, str]]) -> None:
        self.status_code = 502
        self.error_code = "KNOWLEDGE_PROVISION_FAILED"
        self.failures = failures
        super().__init__(
            "所有可用地域都无法创建知识库："
            + "；".join(
                f"{failure['region']}: {failure['message']}" for failure in failures
            )
        )


class KnowledgeRollbackError(KnowledgeAccessError):
    def __init__(
        self,
        message: str,
        *,
        operation: str,
        operation_error: Exception,
        cleanup_errors: list[Exception],
        resource: str = "",
    ) -> None:
        super().__init__(
            message,
            status_code=502,
            error_code="KNOWLEDGE_ROLLBACK_FAILED",
        )
        self.operation = operation
        self.operation_error = str(operation_error)
        self.cleanup_errors = [str(error) for error in cleanup_errors]
        self.resource = resource


@dataclass(frozen=True, slots=True)
class KnowledgeIdentity:
    owner_id: str
    owner_label: str
    is_admin: bool = False
    can_bind_provider: bool = False


@dataclass(frozen=True, slots=True)
class KnowledgeRecord:
    id: str
    name: str
    description: str
    provider_type: str
    provider_knowledge_id: str
    project_name: str
    region: str
    status: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class ProviderConnection:
    provider_type: str
    provider_knowledge_id: str
    base_url: str = ""
    region: str = ""
    auth_type: str = ""
    auth_key: str = field(default="", repr=False)
    extra_config: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    id: str
    name: str
    description: str
    provider_type: str
    provider_knowledge_id: str
    project_name: str
    region: str
    status: str
    created_at: str
    updated_at: str
    owner_id: str
    owner_label: str
    can_manage: bool


@dataclass(frozen=True, slots=True)
class KnowledgeList:
    items: list[KnowledgeItem]
    next_token: str = ""


@dataclass(frozen=True, slots=True)
class ProvisionedKnowledgeBase:
    provider_knowledge_id: str
    name: str


class AgentKitKnowledgeGateway(Protocol):
    def list(
        self,
        *,
        region: str,
        project_name: str | None,
        next_token: str | None,
        max_results: int,
    ) -> tuple[list[KnowledgeRecord], str]: ...

    def get(self, knowledge_id: str, *, region: str) -> KnowledgeRecord: ...

    def add(
        self,
        body: CreateKnowledgeBaseBody,
        *,
        description: str,
        provider_knowledge_id: str,
        project_name: str,
        region: str,
    ) -> str: ...

    def update_description(
        self,
        knowledge_id: str,
        *,
        description: str,
        region: str,
    ) -> None: ...

    def delete(self, knowledge_id: str, *, region: str) -> None: ...

    def connection(
        self,
        knowledge_id: str,
        *,
        region: str,
    ) -> ProviderConnection: ...


class DocumentGateway(Protocol):
    def list(
        self,
        *,
        offset: int,
        limit: int,
        document_type: str | None,
    ) -> tuple[list[dict[str, Any]], bool]: ...

    def get(self, document_id: str) -> dict[str, Any]: ...

    def preview(
        self,
        document_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], bool]: ...

    def create(self, body: CreateDocumentBody) -> dict[str, Any]: ...

    def update_metadata(
        self,
        document_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]: ...

    def delete(self, document_id: str) -> None: ...


class DocumentGatewayFactory(Protocol):
    def __call__(
        self,
        record: KnowledgeRecord,
        connection: ProviderConnection,
        /,
    ) -> DocumentGateway: ...


class KnowledgeBaseProvisioner(Protocol):
    def create(
        self,
        *,
        name: str,
        description: str,
        project_name: str,
        region: str,
    ) -> ProvisionedKnowledgeBase: ...

    def delete(
        self,
        *,
        name: str,
        provider_knowledge_id: str,
        project_name: str,
        region: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class StoredKnowledgeUpload:
    tos_path: str
    bucket: str
    key: str
    region: str


class KnowledgeUploadStore(Protocol):
    max_file_bytes: int

    def put(
        self,
        *,
        source: Path,
        owner_id: str,
        knowledge_id: str,
        region: str,
        file_name: str,
        mime_type: str,
    ) -> StoredKnowledgeUpload: ...

    def delete(self, upload: StoredKnowledgeUpload) -> None: ...

    def read_managed(
        self,
        *,
        tos_path: str,
        owner_id: str,
        knowledge_id: str,
        region: str,
    ) -> bytes | None: ...

    def put_metadata(
        self,
        upload: StoredKnowledgeUpload,
        metadata: dict[str, Any],
    ) -> None: ...

    def get_metadata_managed(
        self,
        *,
        tos_path: str,
        owner_id: str,
        knowledge_id: str,
        region: str,
    ) -> dict[str, Any]: ...

    def put_metadata_managed(
        self,
        *,
        tos_path: str,
        owner_id: str,
        knowledge_id: str,
        region: str,
        metadata: dict[str, Any],
    ) -> bool: ...

    def delete_managed(
        self,
        *,
        tos_path: str,
        owner_id: str,
        knowledge_id: str,
        region: str,
    ) -> bool: ...


def _visible_description(description: str) -> str:
    value = description or ""
    match = _COMPACT_METADATA_PATTERN.search(value) or _LEGACY_METADATA_PATTERN.search(
        value
    )
    return (description[: match.start()] if match else description or "").strip()


def _metadata_signature(metadata: dict[str, str], signing_key: bytes) -> str:
    payload = json.dumps(
        metadata,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return (
        base64.urlsafe_b64encode(
            hmac.new(signing_key, payload, hashlib.sha256).digest()
        )
        .decode("ascii")
        .rstrip("=")
    )


def _compact_encode(value: str) -> str:
    if not value:
        return "0"
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _compact_decode(value: str) -> str:
    if value == "0":
        return ""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode("utf-8")


def _compact_signature(metadata: dict[str, str], signing_key: bytes) -> str:
    payload = json.dumps(
        metadata,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hmac.new(signing_key, payload, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def encode_owned_description(
    description: str,
    identity: KnowledgeIdentity,
    *,
    signing_key: bytes,
    knowledge_id: str,
    provider_type: str,
    provider_knowledge_id: str,
    project_name: str,
    region: str,
    provider_managed: bool = False,
    provider_name: str = "",
) -> str:
    metadata = {
        "veadk:author": identity.owner_id,
        "veadk:knowledge-id": knowledge_id,
        "veadk:managed": "true",
        "veadk:owner": identity.owner_id,
        "veadk:project": project_name,
        "veadk:provider-id": provider_knowledge_id,
        "veadk:provider-type": provider_type,
        "veadk:region": region,
    }
    if provider_managed:
        metadata["veadk:provider-managed"] = "true"
    if provider_name:
        metadata["veadk:provider-name"] = provider_name
    flags = 1 | (2 if provider_managed else 0)
    signature = _compact_signature(metadata, signing_key)
    encoded = ".".join(
        (
            _compact_encode(identity.owner_id),
            provider_name or "0",
            str(flags),
            signature,
        )
    )
    visible = _visible_description(description)
    separator = " " if visible else ""
    result = f"{visible}{separator}veadkmeta_v3_{encoded}"
    if len(result) > 200:
        raise KnowledgeAccessError(
            "知识库描述和用户标识合计超过 AgentKit 的 200 字符限制。",
            status_code=422,
            error_code="KNOWLEDGE_DESCRIPTION_TOO_LONG",
        )
    return result


def decode_owned_description(
    description: str,
    *,
    signing_key: bytes | None = None,
    knowledge_id: str = "",
    provider_type: str = "",
    provider_knowledge_id: str = "",
    project_name: str = "",
    region: str = "",
) -> tuple[str, dict[str, str]]:
    compact_match = _COMPACT_METADATA_PATTERN.search(description or "")
    if compact_match is not None:
        visible = description[: compact_match.start()].strip()
        try:
            flags = int(compact_match.group("flags"))
            metadata = {
                "veadk:author": _compact_decode(compact_match.group("owner")),
                "veadk:knowledge-id": knowledge_id,
                "veadk:managed": "true",
                "veadk:owner": _compact_decode(compact_match.group("owner")),
                "veadk:project": project_name,
                "veadk:provider-id": provider_knowledge_id,
                "veadk:provider-type": provider_type,
                "veadk:region": region,
            }
            provider_name = compact_match.group("provider_name")
        except (ValueError, UnicodeDecodeError):
            return visible, {}
        if flags & 2:
            metadata["veadk:provider-managed"] = "true"
        if provider_name != "0":
            metadata["veadk:provider-name"] = provider_name
        signature = compact_match.group("signature")
        if (
            signing_key is None
            or not (flags & 1)
            or not metadata["veadk:owner"]
            or not hmac.compare_digest(
                signature,
                _compact_signature(metadata, signing_key),
            )
        ):
            return visible, {}
        return visible, metadata

    match = _LEGACY_METADATA_PATTERN.search(description or "")
    if match is None:
        return (description or "").strip(), {}
    visible = description[: match.start()].strip()
    payload = match.group("payload")
    try:
        padding = "=" * (-len(payload) % 4)
        decoded = json.loads(
            base64.urlsafe_b64decode(payload + padding).decode("utf-8")
        )
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return visible, {}
    if not isinstance(decoded, dict):
        return visible, {}
    metadata = {
        str(key): str(value)
        for key, value in decoded.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    signature = metadata.pop("veadk:signature", "")
    expected_binding = {
        "veadk:knowledge-id": knowledge_id,
        "veadk:project": project_name,
        "veadk:provider-id": provider_knowledge_id,
        "veadk:provider-type": provider_type,
        "veadk:region": region,
    }
    if (
        match.group("version") != "v2"
        or signing_key is None
        or not signature
        or any(metadata.get(key) != value for key, value in expected_binding.items())
        or not hmac.compare_digest(
            signature, _metadata_signature(metadata, signing_key)
        )
    ):
        return visible, {}
    return visible, metadata


class KnowledgeService:
    def __init__(
        self,
        agentkit: AgentKitKnowledgeGateway,
        document_gateway_factory: DocumentGatewayFactory,
        *,
        signing_key: bytes | str,
        upload_store: KnowledgeUploadStore | None = None,
        provisioner: KnowledgeBaseProvisioner | None = None,
    ) -> None:
        normalized_key = (
            signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key
        )
        if not normalized_key:
            raise ValueError("Knowledge metadata signing key must not be empty")
        self._agentkit = agentkit
        self._document_gateway_factory = document_gateway_factory
        self._signing_key = normalized_key
        self._upload_store = upload_store
        self._provisioner = provisioner

    @property
    def max_upload_bytes(self) -> int:
        return (
            self._upload_store.max_file_bytes if self._upload_store is not None else 0
        )

    def list(
        self,
        *,
        identity: KnowledgeIdentity,
        region: str,
        project_name: str | None,
        next_token: str | None,
        page_size: int,
    ) -> KnowledgeList:
        items: list[KnowledgeItem] = []
        token = next_token
        for _ in range(100):
            remaining = page_size - len(items)
            if remaining <= 0:
                break
            records, following = self._agentkit.list(
                region=region,
                project_name=project_name,
                next_token=token,
                max_results=remaining,
            )
            for record in records:
                item = self._to_item(record, identity)
                if identity.is_admin or item.owner_id == identity.owner_id:
                    items.append(item)
            token = following or None
            if not token:
                break
        return KnowledgeList(items=items, next_token=token or "")

    def create(
        self,
        body: CreateKnowledgeBaseBody,
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> KnowledgeItem:
        if not identity.can_bind_provider:
            raise KnowledgeAccessError(
                "只有管理员或开发者可以创建知识库。",
                status_code=403,
            )
        if self._provisioner is None:
            raise KnowledgeAccessError(
                "知识库创建服务尚未配置。",
                status_code=503,
            )
        project_name = "default"
        with _PROVIDER_BINDING_LOCK:
            provisioned = self._provisioner.create(
                name=body.name,
                description=_visible_description(body.description),
                project_name=project_name,
                region=region,
            )
            knowledge_id = ""
            try:
                knowledge_id = self._agentkit.add(
                    body,
                    description=_visible_description(body.description),
                    provider_knowledge_id=provisioned.provider_knowledge_id,
                    project_name=project_name,
                    region=region,
                )
                record = self._agentkit.get(knowledge_id, region=region)
                description = self._encode_record_description(
                    body.description,
                    identity,
                    record,
                    provider_managed=True,
                    provider_name=(
                        provisioned.name if provisioned.name != body.name else ""
                    ),
                )
                self._agentkit.update_description(
                    knowledge_id,
                    description=description,
                    region=region,
                )
            except Exception as operation_error:
                cleanup_errors: list[Exception] = []
                if knowledge_id:
                    try:
                        self._agentkit.delete(knowledge_id, region=region)
                    except Exception as cleanup_error:
                        cleanup_errors.append(cleanup_error)
                try:
                    self._provisioner.delete(
                        name=provisioned.name,
                        provider_knowledge_id=provisioned.provider_knowledge_id,
                        project_name=project_name,
                        region=region,
                    )
                except Exception as cleanup_error:
                    cleanup_errors.append(cleanup_error)
                if cleanup_errors:
                    raise KnowledgeRollbackError(
                        "知识库创建失败，并且部分已创建资源未能清理。",
                        operation="create_knowledge_base",
                        operation_error=operation_error,
                        cleanup_errors=cleanup_errors,
                        resource=provisioned.provider_knowledge_id,
                    ) from cleanup_errors[0]
                raise
        return self.get(knowledge_id, identity=identity, region=region)

    def create_first_available(
        self,
        body: CreateKnowledgeBaseBody,
        *,
        identity: KnowledgeIdentity,
        regions: tuple[str, ...],
    ) -> KnowledgeItem:
        """Provision in the first provider region that accepts the request."""
        candidates = tuple(
            dict.fromkeys(region.strip() for region in regions if region.strip())
        )
        if not candidates:
            raise KnowledgeAccessError("当前云环境没有可用地域。", status_code=409)
        last_error: Exception | None = None
        failures: list[dict[str, str]] = []
        for region in candidates:
            try:
                return self.create(body, identity=identity, region=region)
            except KnowledgeAccessError as error:
                if isinstance(error, KnowledgeRollbackError):
                    raise
                # Permission and duplicate-binding failures are independent of
                # region and must not be obscured by a retry elsewhere.
                if error.status_code in {403, 409}:
                    raise
                last_error = error
                failures.append(
                    {
                        "region": region,
                        "message": str(error),
                        "errorCode": str(getattr(error, "error_code", "")),
                        "requestId": str(getattr(error, "request_id", "")),
                    }
                )
            except Exception as error:
                last_error = error
                failures.append(
                    {
                        "region": region,
                        "message": str(error),
                        "errorCode": str(
                            getattr(error, "error_code", "")
                            or getattr(error, "code", "")
                        ),
                        "requestId": str(getattr(error, "request_id", "")),
                    }
                )
                logger.info(
                    "Knowledge binding failed in region=%s error_type=%s; trying next region",
                    region,
                    type(error).__name__,
                )
        assert last_error is not None
        raise KnowledgeProvisionError(failures) from last_error

    def get(
        self,
        knowledge_id: str,
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> KnowledgeItem:
        return self._to_authorized_item(
            self._agentkit.get(knowledge_id, region=region),
            identity,
        )

    def update(
        self,
        knowledge_id: str,
        body: UpdateKnowledgeBaseBody,
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> KnowledgeItem:
        record = self._authorized_record(knowledge_id, identity, region)
        _, metadata = self._verified_record_description(record)
        if metadata:
            owner = KnowledgeIdentity(
                owner_id=metadata["veadk:owner"],
                owner_label=(
                    identity.owner_label
                    if metadata["veadk:owner"] == identity.owner_id
                    else metadata.get("veadk:author", "")
                ),
            )
            description = self._encode_record_description(
                body.description,
                owner,
                record,
                provider_managed=metadata.get("veadk:provider-managed") == "true",
                provider_name=metadata.get("veadk:provider-name", ""),
            )
        else:
            # Administrators may edit unmanaged AgentKit entries, but editing
            # must never silently claim ownership on their behalf.
            description = _visible_description(body.description)
        self._agentkit.update_description(
            knowledge_id,
            description=description,
            region=region,
        )
        return self.get(knowledge_id, identity=identity, region=region)

    def delete(
        self,
        knowledge_id: str,
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> None:
        record = self._authorized_record(knowledge_id, identity, region)
        _, metadata = self._verified_record_description(record)
        if metadata.get("veadk:provider-managed") == "true":
            if self._provisioner is None:
                raise KnowledgeAccessError(
                    "知识库删除服务尚未配置。",
                    status_code=503,
                )
            self._delete_all_documents(
                record,
                identity=identity,
                region=region,
            )
            logger.info(
                "Deleting Studio-managed knowledge provider knowledge_id=%s "
                "provider_id=%s region=%s",
                record.id,
                record.provider_knowledge_id,
                record.region or region,
            )
            self._provisioner.delete(
                name=metadata.get("veadk:provider-name") or record.name,
                provider_knowledge_id=record.provider_knowledge_id,
                project_name=record.project_name or "default",
                region=record.region or region,
            )
            logger.info(
                "Deleted Studio-managed knowledge provider knowledge_id=%s "
                "provider_id=%s region=%s",
                record.id,
                record.provider_knowledge_id,
                record.region or region,
            )
        self._agentkit.delete(knowledge_id, region=region)

    def list_documents(
        self,
        knowledge_id: str,
        *,
        identity: KnowledgeIdentity,
        region: str,
        offset: int,
        limit: int,
        document_type: str | None,
    ) -> tuple[list[dict[str, Any]], bool]:
        record, gateway = self._document_context(knowledge_id, identity, region)
        documents, has_more = gateway.list(
            offset=offset,
            limit=limit,
            document_type=document_type,
        )
        owner_id = self._to_item(record, identity).owner_id
        return (
            [
                self._with_stored_metadata(
                    document,
                    owner_id=owner_id,
                    knowledge_id=knowledge_id,
                    region=region,
                )
                for document in documents
            ],
            has_more,
        )

    def get_document(
        self,
        knowledge_id: str,
        document_id: str,
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> dict[str, Any]:
        record, gateway = self._document_context(knowledge_id, identity, region)
        return self._with_stored_metadata(
            gateway.get(document_id),
            owner_id=self._to_item(record, identity).owner_id,
            knowledge_id=knowledge_id,
            region=region,
        )

    def preview_document(
        self,
        knowledge_id: str,
        document_id: str,
        *,
        identity: KnowledgeIdentity,
        region: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        record, gateway = self._document_context(knowledge_id, identity, region)
        document = self._with_stored_metadata(
            gateway.get(document_id),
            owner_id=self._to_item(record, identity).owner_id,
            knowledge_id=knowledge_id,
            region=region,
        )
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        source_markdown = ""
        content_format = str(metadata.get("_veadk_content_format") or "")
        tos_path = str(document.get("tosPath") or "").strip()
        if content_format == "markdown" and tos_path and self._upload_store is not None:
            source = self._upload_store.read_managed(
                tos_path=tos_path,
                owner_id=self._to_item(record, identity).owner_id,
                knowledge_id=knowledge_id,
                region=region,
            )
            if source is not None:
                try:
                    source_markdown = source.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise KnowledgeAccessError(
                        "网页 Markdown 原文已损坏。",
                        status_code=502,
                    ) from error
        if source_markdown:
            chunks, has_more = [], False
        else:
            chunks, has_more = gateway.preview(
                document_id,
                offset=offset,
                limit=limit,
            )
        return {
            "document": document,
            "chunks": chunks,
            "offset": offset,
            "limit": limit,
            "hasMore": has_more,
            "sourceMarkdown": source_markdown,
        }

    def create_document(
        self,
        knowledge_id: str,
        body: CreateDocumentBody,
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> dict[str, Any]:
        return self._documents(knowledge_id, identity, region).create(body)

    def authorize_document_operation(
        self,
        knowledge_id: str,
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> None:
        """Authorize a provider document operation before external I/O."""
        self._documents(knowledge_id, identity, region)

    def upload_document(
        self,
        knowledge_id: str,
        *,
        identity: KnowledgeIdentity,
        region: str,
        source: Path,
        file_name: str,
        mime_type: str,
        name: str | None,
        document_type: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        # Resolve ownership and the AgentKit provider connection before any
        # bytes are sent to persistent storage.
        gateway = self._documents(knowledge_id, identity, region)
        if self._upload_store is None:
            raise KnowledgeAccessError(
                "知识库文件存储尚未配置。",
                status_code=503,
            )
        provider_metadata = {
            **metadata,
            "_veadk_file_size_bytes": source.stat().st_size,
        }
        upload = self._upload_store.put(
            source=source,
            owner_id=identity.owner_id,
            knowledge_id=knowledge_id,
            region=region,
            file_name=file_name,
            mime_type=mime_type,
        )
        try:
            put_metadata = getattr(self._upload_store, "put_metadata", None)
            if callable(put_metadata):
                put_metadata(upload, provider_metadata)
            result = gateway.create(
                CreateDocumentBody(
                    source_type="tos",
                    name=name or file_name,
                    document_type=document_type,
                    tos_path=upload.tos_path,
                    metadata=provider_metadata,
                )
            )
            return self._merge_document_metadata(result, provider_metadata)
        except Exception as operation_error:
            try:
                self._upload_store.delete(upload)
            except Exception as cleanup_error:
                raise KnowledgeRollbackError(
                    "数据写入失败，并且上传文件未能完全清理。",
                    operation="create_document",
                    operation_error=operation_error,
                    cleanup_errors=[cleanup_error],
                    resource=upload.tos_path,
                ) from cleanup_error
            raise

    def update_document(
        self,
        knowledge_id: str,
        document_id: str,
        body: UpdateDocumentBody,
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> dict[str, Any]:
        record, gateway = self._document_context(knowledge_id, identity, region)
        document = gateway.get(document_id)
        owner_id = self._to_item(record, identity).owner_id
        tos_path = str(document.get("tosPath") or "").strip()
        stored_metadata: dict[str, Any] = {}
        if self._upload_store is not None and tos_path:
            stored_metadata = self._upload_store.get_metadata_managed(
                tos_path=tos_path,
                owner_id=owner_id,
                knowledge_id=knowledge_id,
                region=region,
            )
        metadata = {
            **body.metadata,
            **{
                key: value
                for key, value in stored_metadata.items()
                if key.startswith("_veadk_")
            },
        }
        updated = gateway.update_metadata(document_id, metadata)
        if self._upload_store is not None and tos_path:
            self._upload_store.put_metadata_managed(
                tos_path=tos_path,
                owner_id=owner_id,
                knowledge_id=knowledge_id,
                region=region,
                metadata=metadata,
            )
        return self._merge_document_metadata(
            updated,
            metadata,
        )

    def delete_document(
        self,
        knowledge_id: str,
        document_id: str,
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> None:
        record, gateway = self._document_context(knowledge_id, identity, region)
        document = gateway.get(document_id)
        self._delete_document_from_context(
            record,
            gateway,
            document,
            identity=identity,
            region=region,
        )

    def _delete_all_documents(
        self,
        record: KnowledgeRecord,
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> None:
        connection = self._agentkit.connection(record.id, region=region)
        gateway = self._document_gateway_factory(record, connection)
        documents: list[dict[str, Any]] = []
        offset = 0
        while True:
            page, has_more = gateway.list(
                offset=offset,
                limit=_DOCUMENT_CLEANUP_PAGE_SIZE,
                document_type=None,
            )
            documents.extend(page)
            if not has_more:
                break
            if not page:
                raise KnowledgeAccessError(
                    "Provider 返回了无效的知识分页，知识库尚未删除，请重试。",
                    status_code=502,
                    error_code="KNOWLEDGE_DOCUMENT_PAGE_INVALID",
                )
            offset += len(page)
        for document in documents:
            document_id = str(document.get("id") or "").strip()
            if not document_id:
                raise KnowledgeAccessError(
                    "Provider 返回了缺少 ID 的数据，知识库尚未删除，请重试。",
                    status_code=502,
                    error_code="KNOWLEDGE_DOCUMENT_ID_INVALID",
                )
            self._delete_document_from_context(
                record,
                gateway,
                document,
                identity=identity,
                region=region,
            )

    def _delete_document_from_context(
        self,
        record: KnowledgeRecord,
        gateway: DocumentGateway,
        document: dict[str, Any],
        *,
        identity: KnowledgeIdentity,
        region: str,
    ) -> None:
        document_id = str(document.get("id") or "").strip()
        tos_path = str(document.get("tosPath") or "").strip()
        metadata = document.get("metadata")
        is_studio_managed = isinstance(metadata, dict) and any(
            str(key).startswith("_veadk_") for key in metadata
        )
        if self._upload_store is None and tos_path and is_studio_managed:
            raise KnowledgeAccessError(
                "知识库文件存储尚未配置，数据尚未删除，请联系管理员。",
                status_code=503,
                error_code="KNOWLEDGE_STORAGE_UNAVAILABLE",
            )
        if self._upload_store is not None and tos_path:
            owner_id = self._to_item(record, identity).owner_id
            deleted = self._upload_store.delete_managed(
                tos_path=tos_path,
                owner_id=owner_id,
                knowledge_id=record.id,
                region=region,
            )
            if not deleted and is_studio_managed:
                raise KnowledgeAccessError(
                    "无法验证此数据的 Studio 存储归属，数据尚未删除，请重试或联系管理员。",
                    status_code=409,
                    error_code="KNOWLEDGE_DOCUMENT_STORAGE_INVALID",
                )
        gateway.delete(document_id)

    def _documents(
        self,
        knowledge_id: str,
        identity: KnowledgeIdentity,
        region: str,
    ) -> DocumentGateway:
        return self._document_context(knowledge_id, identity, region)[1]

    @staticmethod
    def _merge_document_metadata(
        document: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        document_metadata = document.get("metadata")
        if not isinstance(document_metadata, dict):
            document_metadata = {}
        merged_metadata = {
            **document_metadata,
            **metadata,
        }
        source_url = str(merged_metadata.get("_veadk_source_url") or "").strip()
        content_format = str(merged_metadata.get("_veadk_content_format") or "").strip()
        source_title = str(merged_metadata.get("_veadk_source_title") or "").strip()
        if content_format == "markdown" and not source_title and source_url:
            source_title = urlsplit(source_url).hostname or "网页"
        return {
            **document,
            "name": (
                source_title
                if content_format == "markdown" and source_title
                else str(document.get("name") or "")
            ),
            "metadata": merged_metadata,
            "url": source_url or str(document.get("url") or ""),
            "sizeBytes": int(
                merged_metadata.get("_veadk_file_size_bytes")
                or document.get("sizeBytes")
                or 0
            ),
        }

    def _with_stored_metadata(
        self,
        document: dict[str, Any],
        *,
        owner_id: str,
        knowledge_id: str,
        region: str,
    ) -> dict[str, Any]:
        if self._upload_store is None:
            return document
        tos_path = str(document.get("tosPath") or "").strip()
        if not tos_path:
            return document
        metadata = self._upload_store.get_metadata_managed(
            tos_path=tos_path,
            owner_id=owner_id,
            knowledge_id=knowledge_id,
            region=region,
        )
        return self._merge_document_metadata(document, metadata)

    def _document_context(
        self,
        knowledge_id: str,
        identity: KnowledgeIdentity,
        region: str,
    ) -> tuple[KnowledgeRecord, DocumentGateway]:
        record = self._authorized_record(knowledge_id, identity, region)
        # This call is deliberately required for every provider operation. It
        # keeps provider selection and endpoint data sourced from AgentKit.
        connection = self._agentkit.connection(knowledge_id, region=region)
        return record, self._document_gateway_factory(record, connection)

    def _authorized_record(
        self,
        knowledge_id: str,
        identity: KnowledgeIdentity,
        region: str,
    ) -> KnowledgeRecord:
        record = self._agentkit.get(knowledge_id, region=region)
        self._to_authorized_item(record, identity)
        return record

    def _to_authorized_item(
        self,
        record: KnowledgeRecord,
        identity: KnowledgeIdentity,
    ) -> KnowledgeItem:
        item = self._to_item(record, identity)
        if not identity.is_admin and item.owner_id != identity.owner_id:
            raise KnowledgeAccessError("无权访问此知识库。", status_code=403)
        return item

    def _encode_record_description(
        self,
        description: str,
        identity: KnowledgeIdentity,
        record: KnowledgeRecord,
        *,
        provider_managed: bool = False,
        provider_name: str = "",
    ) -> str:
        return encode_owned_description(
            description,
            identity,
            signing_key=self._signing_key,
            knowledge_id=record.id,
            provider_type=record.provider_type,
            provider_knowledge_id=record.provider_knowledge_id,
            project_name=record.project_name,
            region=record.region,
            provider_managed=provider_managed,
            provider_name=provider_name,
        )

    def _decode_record_description(
        self,
        record: KnowledgeRecord,
    ) -> tuple[str, dict[str, str]]:
        return decode_owned_description(
            record.description,
            signing_key=self._signing_key,
            knowledge_id=record.id,
            provider_type=record.provider_type,
            provider_knowledge_id=record.provider_knowledge_id,
            project_name=record.project_name,
            region=record.region,
        )

    def _verified_record_description(
        self,
        record: KnowledgeRecord,
    ) -> tuple[str, dict[str, str]]:
        description, metadata = self._decode_record_description(record)
        has_envelope = "veadkmeta_v" in record.description or "[veadk-meta:" in (
            record.description
        )
        if has_envelope and not metadata:
            raise KnowledgeAccessError(
                "知识库所有权元数据校验失败，已拒绝修改或删除。请联系管理员检查 Studio 签名配置。",
                status_code=409,
                error_code="KNOWLEDGE_METADATA_SIGNATURE_INVALID",
            )
        return description, metadata

    def _to_item(
        self,
        record: KnowledgeRecord,
        identity: KnowledgeIdentity,
    ) -> KnowledgeItem:
        description, metadata = self._decode_record_description(record)
        owner_id = metadata.get("veadk:owner", "")
        owner_label = (
            identity.owner_label
            if owner_id == identity.owner_id
            else metadata.get("veadk:author", "") or owner_id
        )
        return KnowledgeItem(
            id=record.id,
            name=record.name,
            description=description,
            provider_type=record.provider_type,
            provider_knowledge_id=record.provider_knowledge_id,
            project_name=record.project_name,
            region=record.region,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
            owner_id=owner_id,
            owner_label=owner_label,
            can_manage=identity.is_admin or owner_id == identity.owner_id,
        )


__all__ = [
    "AgentKitKnowledgeGateway",
    "DocumentGateway",
    "KnowledgeAccessError",
    "KnowledgeBaseProvisioner",
    "KnowledgeIdentity",
    "KnowledgeItem",
    "KnowledgeList",
    "KnowledgeProvisionError",
    "KnowledgeRecord",
    "KnowledgeService",
    "KnowledgeUploadStore",
    "ProviderConnection",
    "ProvisionedKnowledgeBase",
    "StoredKnowledgeUpload",
    "decode_owned_description",
    "encode_owned_description",
]
