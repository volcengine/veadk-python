# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""AgentKit and provider SDK adapters for Studio knowledge resources."""

from __future__ import annotations

import json
import mimetypes
import re
from collections.abc import Callable
from pathlib import PurePosixPath
from threading import RLock
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from .models import CreateDocumentBody, CreateKnowledgeBaseBody
from .regions import provider_data_region
from .service import (
    KnowledgeAccessError,
    KnowledgeRecord,
    ProviderConnection,
    ProvisionedKnowledgeBase,
)

CredentialsResolver = Callable[[], tuple[str, str, str | None]]
KnowledgeClientFactory = Callable[[str], Any]
_VIKING_SDK_LOCK = RLock()
_SUPPORTED_CONNECTION_AUTH_TYPES = {
    "aksk",
    "sts",
    "temporaryaksk",
    "temporarycredentials",
}
PROVIDER_ASSOCIATION_INVALID = "KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID"
DOCUMENT_NOT_FOUND = "KNOWLEDGE_DOCUMENT_NOT_FOUND"
DOCUMENT_FORMAT_UNSUPPORTED = "KNOWLEDGE_DOCUMENT_FORMAT_UNSUPPORTED"
DOCUMENT_TOO_LARGE = "KNOWLEDGE_DOCUMENT_TOO_LARGE"
DOCUMENT_URL_INVALID = "KNOWLEDGE_DOCUMENT_URL_INVALID"
_COLLECTION_NOT_FOUND_CODE = 1000005
_DOCUMENT_NOT_FOUND_CODES = {1000011, 1001001}


def _viking_host(provider: str, region: str) -> str:
    return (
        f"api-knowledgebase.mlp.{region}.bytepluses.com"
        if provider == "byteplus"
        else f"api-knowledgebase.mlp.{region}.volces.com"
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _size_bytes(value: Any, metadata: dict[str, Any]) -> int:
    raw_data = getattr(value, "raw_data", None)
    raw = raw_data if isinstance(raw_data, dict) else {}
    candidates = (
        raw.get("size_bytes"),
        raw.get("sizeBytes"),
        raw.get("file_size"),
        raw.get("fileSize"),
        raw.get("content_length"),
        raw.get("contentLength"),
        raw.get("size"),
        metadata.get("size_bytes"),
        metadata.get("sizeBytes"),
        metadata.get("file_size"),
        metadata.get("fileSize"),
        metadata.get("_veadk_file_size_bytes"),
    )
    for candidate in candidates:
        if not isinstance(candidate, (str, int, float)):
            continue
        try:
            size = int(candidate)
        except (TypeError, ValueError):
            continue
        if size >= 0:
            return size
    return 0


def _provider_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate Studio metadata into Viking's documented field envelope."""
    fields: list[dict[str, Any]] = []
    for field_name, value in metadata.items():
        if isinstance(value, bool):
            field_type = "bool"
            field_value: Any = value
        elif isinstance(value, int):
            field_type = "int64"
            field_value = value
        elif isinstance(value, float):
            field_type = "float32"
            field_value = value
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            field_type = "list<string>"
            field_value = value
        elif isinstance(value, list) and all(
            isinstance(item, int) and not isinstance(item, bool) for item in value
        ):
            field_type = "list<int64>"
            field_value = value
        else:
            field_type = "string"
            field_value = (
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            )
        fields.append(
            {
                "field_name": field_name,
                "field_type": field_type,
                "field_value": field_value,
            }
        )
    return fields


def _record(value: Any, *, fallback_region: str) -> KnowledgeRecord:
    return KnowledgeRecord(
        id=_text(getattr(value, "knowledge_id", "")),
        name=_text(getattr(value, "name", "")),
        description=str(getattr(value, "description", "") or ""),
        provider_type=_text(getattr(value, "provider_type", "")),
        provider_knowledge_id=_text(getattr(value, "provider_knowledge_id", "")),
        project_name=_text(getattr(value, "project_name", "")),
        region=_text(getattr(value, "region", "")) or fallback_region,
        status=_text(getattr(value, "status", "")),
        created_at=_text(getattr(value, "create_time", "")),
        updated_at=_text(getattr(value, "last_update_time", "")),
    )


def _is_not_found(error: Exception) -> bool:
    values = (
        getattr(error, "error_code", ""),
        getattr(error, "code", ""),
        error,
    )
    return any(
        "notfound" in re.sub(r"[^a-z0-9]", "", str(value).casefold())
        for value in values
    )


def _provider_error_code(error: Exception) -> int | None:
    for value in (
        getattr(error, "code", None),
        getattr(error, "error_code", None),
        str(error),
    ):
        match = re.search(r"(?<!\d)(100\d{4})(?!\d)", str(value or ""))
        if match is not None:
            return int(match.group(1))
    return None


def _provider_association_error() -> KnowledgeAccessError:
    return KnowledgeAccessError(
        "底层 Provider 知识库已不存在，此 AgentKit 关联已失效。"
        "您可以删除这个失效关联后重新创建。",
        status_code=409,
        error_code=PROVIDER_ASSOCIATION_INVALID,
    )


def _document_submission_error(error: Exception) -> KnowledgeAccessError | None:
    message = str(getattr(error, "message", "") or error).casefold()
    unsupported = any(
        marker in message
        for marker in (
            "not support",
            "not supported",
            "unsupported",
            "invalid doc type",
            "invalid doc_type",
            "invalid document type",
            "invalid file type",
        )
    )
    if unsupported:
        return KnowledgeAccessError(
            "Provider 暂不支持此文件格式或导入方式，请改用受支持的数据后重试。",
            status_code=422,
            error_code=DOCUMENT_FORMAT_UNSUPPORTED,
        )
    if "too large" in message or (
        any(marker in message for marker in ("exceed", "exceeds", "exceeded"))
        and any(subject in message for subject in ("file size", "size limit"))
    ):
        return KnowledgeAccessError(
            "文件超过 Provider 支持的大小，请压缩或拆分后重试。",
            status_code=413,
            error_code=DOCUMENT_TOO_LARGE,
        )
    if any(
        marker in message
        for marker in (
            "invalid url",
            "invalid uri",
            "url is invalid",
            "unsupported url",
        )
    ):
        return KnowledgeAccessError(
            "Provider 无法读取此网页地址，请确认地址可公开访问后重试。",
            status_code=422,
            error_code=DOCUMENT_URL_INVALID,
        )
    return None


def _provider_call(
    call: Callable[[], Any],
    *,
    document_submission: bool = False,
) -> Any:
    try:
        return call()
    except Exception as error:
        code = _provider_error_code(error)
        if code == _COLLECTION_NOT_FOUND_CODE:
            raise _provider_association_error() from error
        if code in _DOCUMENT_NOT_FOUND_CODES:
            raise KnowledgeAccessError(
                "知识内容不存在或已被删除。",
                status_code=404,
                error_code=DOCUMENT_NOT_FOUND,
            ) from error
        if document_submission:
            actionable = _document_submission_error(error)
            if actionable is not None:
                raise actionable from error
        raise


def _provider_list_docs(collection: Any, **kwargs: Any) -> list[Any]:
    """Treat BytePlus' omitted doc_list on an empty collection as an empty page."""
    try:
        return collection.list_docs(**kwargs)
    except KeyError as error:
        if error.args == ("doc_list",):
            return []
        raise


def _credential_value(payload: dict[str, Any], aliases: set[str]) -> str:
    pending: list[tuple[dict[str, Any], int]] = [(payload, 0)]
    while pending:
        current, depth = pending.pop()
        for key, value in current.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).casefold())
            if normalized in aliases and isinstance(value, str) and value.strip():
                return value.strip()
            if depth < 2 and isinstance(value, dict):
                pending.append((value, depth + 1))
    return ""


def _connection_credentials(
    connection: ProviderConnection,
    fallback: CredentialsResolver,
) -> tuple[str, str, str | None]:
    auth_type = re.sub(r"[^a-z0-9]", "", connection.auth_type.casefold())
    # AgentKit also uses ExtraConfig for non-secret provider settings. It is
    # not an authentication contract unless AuthType or AuthKey says so.
    if not connection.auth_key and auth_type in {"", "aksk"}:
        return fallback()
    auth_payloads = [
        value for value in (connection.auth_key, connection.extra_config) if value
    ]
    if auth_type and auth_type not in _SUPPORTED_CONNECTION_AUTH_TYPES:
        raise KnowledgeAccessError(
            "AgentKit 返回了当前不支持的 Provider 连接认证方式。",
            status_code=409,
        )

    combined: dict[str, Any] = {}
    for raw in auth_payloads:
        if len(raw) > 65_536:
            raise KnowledgeAccessError("Provider 连接认证信息无效。", status_code=409)
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise KnowledgeAccessError(
                "Provider 连接认证信息无法安全解析。",
                status_code=409,
            ) from error
        if not isinstance(decoded, dict):
            raise KnowledgeAccessError("Provider 连接认证信息无效。", status_code=409)
        combined.update(decoded)

    access_key = _credential_value(
        combined,
        {"ak", "accesskey", "accesskeyid"},
    )
    secret_key = _credential_value(
        combined,
        {"sk", "secretkey", "secretaccesskey"},
    )
    session_token = _credential_value(
        combined,
        {"sessiontoken", "securitytoken", "ststoken"},
    )
    if not access_key or not secret_key:
        raise KnowledgeAccessError(
            "Provider 连接未提供完整的临时 AK/SK。",
            status_code=409,
        )
    if (
        auth_type in {"sts", "temporaryaksk", "temporarycredentials"}
        and not session_token
    ):
        raise KnowledgeAccessError(
            "Provider 临时连接缺少 STS Token。",
            status_code=409,
        )
    return access_key, secret_key, session_token or None


class SdkAgentKitKnowledgeGateway:
    """Typed adapter around ``AgentkitKnowledgeClient``."""

    def __init__(self, client_factory: KnowledgeClientFactory) -> None:
        self._client_factory = client_factory

    def list(
        self,
        *,
        region: str,
        project_name: str | None,
        next_token: str | None,
        max_results: int,
    ) -> tuple[list[KnowledgeRecord], str]:
        from agentkit.sdk.knowledge import types

        response = self._client_factory(region).list_knowledge_bases(
            types.ListKnowledgeBasesRequest(
                ProjectName=project_name,
                NextToken=next_token,
                MaxResults=max_results,
            )
        )
        return (
            [
                _record(item, fallback_region=region)
                for item in (response.knowledge_bases or [])
                if _text(getattr(item, "knowledge_id", ""))
            ],
            _text(getattr(response, "next_token", "")),
        )

    def get(self, knowledge_id: str, *, region: str) -> KnowledgeRecord:
        from agentkit.sdk.knowledge import types

        try:
            response = self._client_factory(region).get_knowledge_base(
                types.GetKnowledgeBaseRequest(KnowledgeId=knowledge_id)
            )
        except Exception as error:
            if _is_not_found(error):
                raise KnowledgeAccessError(
                    "知识库不存在。",
                    status_code=404,
                ) from error
            raise
        record = _record(response, fallback_region=region)
        if not record.id:
            raise KnowledgeAccessError("知识库不存在。", status_code=404)
        return record

    def add(
        self,
        body: CreateKnowledgeBaseBody,
        *,
        description: str,
        provider_knowledge_id: str,
        project_name: str,
        region: str,
    ) -> str:
        from agentkit.sdk.knowledge import types

        response = self._client_factory(region).add_knowledge_base(
            types.AddKnowledgeBaseRequest(
                ProjectName=project_name,
                KnowledgeBases=[
                    types.KnowledgeBasesItemForAddKnowledgeBase(
                        Name=body.name,
                        Description=description,
                        ProviderType="VIKINGDB_KNOWLEDGE",
                        ProviderKnowledgeId=provider_knowledge_id,
                    )
                ],
            )
        )
        results = list(response.knowledge_bases or [])
        knowledge_id = _text(getattr(results[0], "knowledge_id", "")) if results else ""
        if not knowledge_id:
            message = _text(getattr(results[0], "message", "")) if results else ""
            raise RuntimeError(message or "AgentKit did not return a knowledge ID")
        return knowledge_id

    def update_description(
        self,
        knowledge_id: str,
        *,
        description: str,
        region: str,
    ) -> None:
        from agentkit.sdk.knowledge import types

        self._client_factory(region).update_knowledge_base(
            types.UpdateKnowledgeBaseRequest(
                KnowledgeId=knowledge_id,
                Description=description,
            )
        )

    def delete(self, knowledge_id: str, *, region: str) -> None:
        from agentkit.sdk.knowledge import types

        self._client_factory(region).delete_knowledge_base(
            types.DeleteKnowledgeBaseRequest(KnowledgeId=knowledge_id)
        )

    def connection(
        self,
        knowledge_id: str,
        *,
        region: str,
    ) -> ProviderConnection:
        from agentkit.sdk.knowledge import types

        response = self._client_factory(region).get_knowledge_connection_info(
            types.GetKnowledgeConnectionInfoRequest(KnowledgeId=knowledge_id)
        )
        infos = list(response.connection_infos or [])
        # Prefer a ready public connection. AgentKit remains authoritative for
        # the provider type, endpoint, region and temporary auth metadata.
        info = next(
            (
                item
                for item in infos
                if _text(getattr(item, "status", "")).casefold()
                in {"", "ready", "available", "active"}
                and _text(getattr(item, "addr_type", "")).casefold()
                in {"", "public", "internet"}
            ),
            infos[0] if infos else None,
        )
        if info is None:
            raise KnowledgeAccessError(
                "知识库暂无可用的 Provider 连接。",
                status_code=409,
            )
        return ProviderConnection(
            provider_type=_text(getattr(response, "provider_type", "")),
            provider_knowledge_id=_text(getattr(response, "provider_knowledge_id", "")),
            base_url=_text(getattr(info, "base_url", "")),
            region=_text(getattr(info, "region", "")) or region,
            auth_type=_text(getattr(info, "auth_type", "")),
            auth_key=_text(getattr(info, "auth_key", "")),
            extra_config=str(getattr(info, "extra_config", "") or ""),
        )


class VikingKnowledgeBaseProvisioner:
    """Create and remove Studio-owned Viking knowledge bases."""

    def __init__(
        self,
        *,
        provider: str,
        resolve_credentials: CredentialsResolver,
    ) -> None:
        if provider not in {"volcengine", "byteplus"}:
            raise ValueError(f"Unsupported provider: {provider}")
        self._provider = provider
        self._resolve_credentials = resolve_credentials

    def _client(self, region: str) -> Any:
        from volcengine.viking_knowledgebase import VikingKnowledgeBaseService

        access_key, secret_key, session_token = self._resolve_credentials()
        provider_region = provider_data_region(self._provider, region)
        host = _viking_host(self._provider, provider_region)
        return VikingKnowledgeBaseService(
            host=host,
            region=provider_region,
            ak=access_key,
            sk=secret_key,
            sts_token=session_token or "",
            scheme="https",
        )

    def create(
        self,
        *,
        name: str,
        description: str,
        project_name: str,
        region: str,
    ) -> ProvisionedKnowledgeBase:
        provider_name = name
        with _VIKING_SDK_LOCK:
            collection = self._client(region).create_collection(
                provider_name,
                version=4,
                description=description,
                project=project_name,
            )
        provider_knowledge_id = _text(getattr(collection, "resource_id", ""))
        if not provider_knowledge_id:
            raise RuntimeError("Viking did not return a knowledge resource ID")
        return ProvisionedKnowledgeBase(
            provider_knowledge_id=provider_knowledge_id,
            name=provider_name,
        )

    def delete(
        self,
        *,
        name: str,
        provider_knowledge_id: str,
        project_name: str,
        region: str,
    ) -> None:
        try:
            with _VIKING_SDK_LOCK:
                self._client(region).drop_collection(
                    name,
                    project=project_name,
                    resource_id=provider_knowledge_id or None,
                )
        except Exception as error:
            if _provider_error_code(error) == _COLLECTION_NOT_FOUND_CODE:
                return
            raise


class VikingDocumentGateway:
    def __init__(
        self,
        collection_factory: Callable[[], Any],
        *,
        project_name: str,
        resource_id: str | None,
    ) -> None:
        self._collection_factory = collection_factory
        self._project_name = project_name or "default"
        self._resource_id = resource_id

    def _collection(self) -> Any:
        try:
            return self._collection_factory()
        except Exception as error:
            if _provider_error_code(error) == _COLLECTION_NOT_FOUND_CODE:
                raise _provider_association_error() from error
            raise

    def list(
        self,
        *,
        offset: int,
        limit: int,
        document_type: str | None,
    ) -> tuple[list[dict[str, Any]], bool]:
        with _VIKING_SDK_LOCK:
            docs = _provider_call(
                lambda: _provider_list_docs(
                    self._collection(),
                    offset=offset,
                    limit=limit + 1,
                    doc_type=document_type,
                    project=self._project_name,
                )
            )
        return [_document(item) for item in docs[:limit]], len(docs) > limit

    def get(self, document_id: str) -> dict[str, Any]:
        with _VIKING_SDK_LOCK:
            return _document(
                _provider_call(
                    lambda: self._collection().get_doc(
                        document_id,
                        project=self._project_name,
                        resource_id=self._resource_id,
                    )
                )
            )

    def preview(
        self,
        document_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        with _VIKING_SDK_LOCK:
            points = _provider_call(
                lambda: self._collection().list_points(
                    offset=offset,
                    limit=limit + 1,
                    doc_ids=[document_id],
                    get_attachment_link=True,
                    project=self._project_name,
                    resource_id=self._resource_id,
                )
            )
        return [_preview_chunk(item) for item in points[:limit]], len(points) > limit

    def create(self, body: CreateDocumentBody) -> dict[str, Any]:
        document_id = f"studio-{uuid4().hex}" if body.source_type == "url" else ""
        document_type = (body.document_type or "").strip() or (
            "html" if body.source_type == "url" else None
        )
        with _VIKING_SDK_LOCK:
            before_ids: set[str] = set()
            if body.source_type == "tos":
                before_ids = {
                    _text(getattr(item, "doc_id", ""))
                    for item in _provider_call(
                        lambda: _provider_list_docs(
                            self._collection(),
                            offset=0,
                            limit=100,
                            project=self._project_name,
                        )
                    )
                }
            _provider_call(
                lambda: self._collection().add_doc(
                    body.source_type,
                    doc_id=document_id or None,
                    doc_name=body.name,
                    doc_type=document_type,
                    url=body.url,
                    tos_path=body.tos_path,
                    meta=_provider_metadata(body.metadata) or None,
                    project=self._project_name,
                    resource_id=self._resource_id,
                ),
                document_submission=True,
            )
            if body.source_type == "tos":
                submitted = _provider_call(
                    lambda: _provider_list_docs(
                        self._collection(),
                        offset=0,
                        limit=100,
                        project=self._project_name,
                    )
                )
                match = next(
                    (
                        item
                        for item in submitted
                        if _text(getattr(item, "doc_id", "")) not in before_ids
                        and _text(getattr(item, "tos_path", ""))
                        == (body.tos_path or "").strip()
                    ),
                    None,
                )
                if match is not None:
                    return _document(match)
                return {
                    "id": "",
                    "name": body.name or "",
                    "type": body.document_type or "",
                    "url": "",
                    "tosPath": body.tos_path or "",
                    "metadata": body.metadata,
                    "status": "submitted",
                    "createdAt": "",
                    "updatedAt": "",
                }
        return {
            "id": document_id,
            "name": body.name or "",
            "type": document_type or "",
            "url": body.url or "",
            "tosPath": body.tos_path or "",
            "metadata": body.metadata,
            "status": "submitted",
        }

    def update_metadata(
        self,
        document_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        with _VIKING_SDK_LOCK:
            _provider_call(
                lambda: self._collection().update_meta(
                    document_id,
                    _provider_metadata(metadata),
                    project=self._project_name,
                    resource_id=self._resource_id,
                )
            )
        return self.get(document_id)

    def delete(self, document_id: str) -> None:
        with _VIKING_SDK_LOCK:
            _provider_call(
                lambda: self._collection().delete_doc(
                    document_id,
                    project=self._project_name,
                    resource_id=self._resource_id,
                )
            )


def build_viking_document_gateway_factory(
    *,
    provider: str,
    resolve_credentials: CredentialsResolver,
) -> Callable[[KnowledgeRecord, ProviderConnection], VikingDocumentGateway]:
    if provider not in {"volcengine", "byteplus"}:
        raise ValueError(f"Unsupported provider: {provider}")

    def build(
        record: KnowledgeRecord,
        connection: ProviderConnection,
    ) -> VikingDocumentGateway:
        if connection.provider_type != "VIKINGDB_KNOWLEDGE":
            raise KnowledgeAccessError(
                "当前知识库 Provider 暂不支持文档管理。",
                status_code=409,
            )
        from volcengine.viking_knowledgebase import VikingKnowledgeBaseService

        parsed = urlparse(connection.base_url)
        if parsed.netloc and parsed.path not in {"", "/"}:
            raise KnowledgeAccessError(
                "AgentKit 返回的 Provider 连接包含当前 SDK 不支持的路径。",
                status_code=409,
            )
        region = connection.region or record.region
        default_host = _viking_host(provider, region)
        host = parsed.netloc or parsed.path.split("/", 1)[0] or default_host
        scheme = parsed.scheme or "https"
        access_key, secret_key, session_token = _connection_credentials(
            connection,
            resolve_credentials,
        )
        provider_id = connection.provider_knowledge_id or record.provider_knowledge_id
        resource_id = provider_id if provider_id.startswith("kb-") else None
        collection_name = (
            provider_id
            if provider_id and not provider_id.startswith("kb-")
            else record.name
        )

        def collection_factory() -> Any:
            # The upstream Viking SDK is process-global. Reconfigure and invoke
            # it while holding ``_VIKING_SDK_LOCK`` in the gateway methods.
            client = VikingKnowledgeBaseService(
                host=host,
                region=region,
                ak=access_key,
                sk=secret_key,
                sts_token=session_token or "",
                scheme=scheme,
            )
            return client.get_collection(
                collection_name,
                project=record.project_name or "default",
                resource_id=resource_id,
            )

        return VikingDocumentGateway(
            collection_factory,
            project_name=record.project_name,
            resource_id=resource_id,
        )

    return build


def _document(value: Any) -> dict[str, Any]:
    metadata = {
        _text(getattr(item, "field_name", "")): getattr(item, "field_val", None)
        for item in (getattr(value, "fields", None) or [])
        if _text(getattr(item, "field_name", ""))
    }
    return {
        "id": _text(getattr(value, "doc_id", "")),
        "name": _text(getattr(value, "doc_name", "")),
        "type": _text(getattr(value, "doc_type", "")),
        "status": _text(getattr(value, "status", "")),
        "url": _text(metadata.get("_veadk_source_url"))
        or _text(getattr(value, "url", "")),
        "tosPath": _text(getattr(value, "tos_path", "")),
        "sizeBytes": _size_bytes(value, metadata),
        "metadata": metadata,
        "createdAt": _text(getattr(value, "create_time", "")),
        "updatedAt": _text(getattr(value, "update_time", "")),
    }


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item, depth=depth + 1) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, depth=depth + 1) for item in value]
    raw_data = getattr(value, "raw_data", None)
    if isinstance(raw_data, (dict, list, tuple)):
        return _json_safe(raw_data, depth=depth + 1)
    return str(value)


def _attachment_value(value: Any, aliases: set[str]) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith(("http://", "https://")) and "url" in aliases:
            return candidate
        try:
            decoded = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""
        return _attachment_value(decoded, aliases)
    if isinstance(value, dict):
        normalized = {
            re.sub(r"[^a-z0-9]", "", str(key).casefold()): item
            for key, item in value.items()
        }
        for alias in aliases:
            candidate = normalized.get(alias)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for item in value.values():
            candidate = _attachment_value(item, aliases)
            if candidate:
                return candidate
    elif isinstance(value, (list, tuple)):
        for item in value:
            candidate = _attachment_value(item, aliases)
            if candidate:
                return candidate
    return ""


def _attachment_type(attachment: Any, url: str) -> str:
    explicit = _attachment_value(
        attachment,
        {
            "attachmenttype",
            "contenttype",
            "filetype",
            "format",
            "mimetype",
            "type",
        },
    )
    if explicit:
        return explicit.casefold()
    suffix = PurePosixPath(urlparse(url).path).suffix.casefold()
    if suffix:
        return (mimetypes.types_map.get(suffix) or suffix.removeprefix(".")).casefold()
    return ""


def _preview_chunk(value: Any) -> dict[str, Any]:
    attachment = _json_safe(getattr(value, "chunk_attachment", None))
    attachment_url = _attachment_value(
        attachment,
        {
            "attachmenturl",
            "downloadurl",
            "link",
            "signedurl",
            "sourceurl",
            "url",
        },
    )
    return {
        "id": _text(getattr(value, "point_id", ""))
        or _text(getattr(value, "chunk_id", "")),
        "title": _text(getattr(value, "chunk_title", "")),
        "content": str(getattr(value, "content", "") or ""),
        "attachmentUrl": attachment_url,
        "attachmentType": _attachment_type(attachment, attachment_url),
        "attachment": attachment,
        "tableFields": _json_safe(getattr(value, "table_chunk_fields", None)),
    }


__all__ = [
    "DOCUMENT_FORMAT_UNSUPPORTED",
    "DOCUMENT_NOT_FOUND",
    "DOCUMENT_TOO_LARGE",
    "DOCUMENT_URL_INVALID",
    "PROVIDER_ASSOCIATION_INVALID",
    "SdkAgentKitKnowledgeGateway",
    "VikingDocumentGateway",
    "VikingKnowledgeBaseProvisioner",
    "build_viking_document_gateway_factory",
]
