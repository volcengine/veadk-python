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

"""FastAPI transport for the Studio knowledge library."""

from __future__ import annotations

import json
import logging
import re
import tempfile
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool

from .models import (
    CreateDocumentBody,
    CreateKnowledgeBaseBody,
    KnowledgeItemResponse,
    KnowledgeListResponse,
    UpdateDocumentBody,
    UpdateKnowledgeBaseBody,
)
from .service import KnowledgeAccessError, KnowledgeIdentity, KnowledgeService
from .uploads import validate_knowledge_upload
from .web_import import (
    WebImportContentError,
    WebImporter,
    WebImportFetchError,
    WebImportResult,
    WebImportSecurityError,
    WebImportTooLargeError,
)

logger = logging.getLogger(__name__)


class WebImportClient(Protocol):
    async def import_url(self, url: str) -> WebImportResult: ...


_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "accesskey",
    "accesskeyid",
    "ak",
    "apikey",
    "authorization",
    "authkey",
    "clientsecret",
    "cookie",
    "credential",
    "credentials",
    "password",
    "secretaccesskey",
    "secretkey",
    "sessiontoken",
    "setcookie",
    "sig",
    "signature",
    "sk",
    "token",
}
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(access[_-]?key(?:[_-]?id)?|secret(?:[_-]?(?:access)?[_-]?key)?|"
    r"session[_-]?token|security[_-]?token|client[_-]?secret|api[_-]?key|"
    r"authorization|cookie|[a-z0-9_-]*(?:password|secret|token|signature)|"
    r"sig|ak|sk)"
    r"\b\s*[\"']?\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;}&]+)"
)
_BEARER_SECRET = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_COOKIE_HEADER = re.compile(r"(?im)\b(?:set-)?cookie\s*:\s*[^\r\n]*")
_REQUEST_ID = re.compile(r"(?i)\b(?:request|trace)[_-]?id\s*[:=]\s*([A-Za-z0-9._:-]+)")


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _is_sensitive_key(value: object) -> bool:
    normalized = _normalized_key(value)
    return normalized in _SENSITIVE_KEYS or normalized.endswith(
        (
            "accesskey",
            "apikey",
            "authorization",
            "cookie",
            "password",
            "secret",
            "signature",
            "token",
        )
    )


def _sanitize_text(value: object) -> str:
    text = str(value or "")[:8192]
    text = _COOKIE_HEADER.sub("Cookie: [REDACTED]", text)
    text = _BEARER_SECRET.sub("Bearer [REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}={_REDACTED}",
        text,
    )


def _safe_diagnostic_value(value: Any, *, key: object = "", depth: int = 0) -> Any:
    if _is_sensitive_key(key):
        return _REDACTED
    if depth > 4:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Enum):
        return _sanitize_text(value.value)
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, Mapping):
        return {
            str(item_key): _safe_diagnostic_value(
                item,
                key=item_key,
                depth=depth + 1,
            )
            for item_key, item in list(value.items())[:50]
            if not str(item_key).startswith("_")
        }
    if isinstance(value, (list, tuple)):
        return [_safe_diagnostic_value(item, depth=depth + 1) for item in value[:20]]
    return f"<{type(value).__name__}>"


def _error_chain(error: Exception) -> list[Exception]:
    chain: list[Exception] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while isinstance(current, Exception) and id(current) not in seen and len(chain) < 6:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return chain


def _error_attribute(chain: list[Exception], *names: str) -> Any:
    for error in chain:
        for name in names:
            value = getattr(error, name, None)
            if value not in (None, ""):
                return value
    return None


def _error_status(chain: list[Exception]) -> int:
    value = _error_attribute(
        chain,
        "status_code",
        "status",
        "http_status",
        "http_status_code",
    )
    values = [value]
    values.extend(
        getattr(getattr(error, "response", None), "status_code", None)
        for error in chain
    )
    for candidate in values:
        try:
            status_code = int(candidate)
        except (TypeError, ValueError):
            continue
        if 400 <= status_code <= 599:
            return status_code
    return 502


def _error_code(chain: list[Exception]) -> str:
    value = _error_attribute(chain, "error_code", "code", "errorCode")
    if isinstance(value, Enum):
        value = value.value
    return (
        _sanitize_text(value) if value not in (None, "") else "KNOWLEDGE_UPSTREAM_ERROR"
    )


def _error_request_id(chain: list[Exception]) -> str:
    value = _error_attribute(
        chain,
        "request_id",
        "requestId",
        "requestid",
        "trace_id",
        "traceId",
    )
    if value not in (None, ""):
        return _sanitize_text(value)
    for error in chain:
        headers = getattr(getattr(error, "response", None), "headers", None)
        if not isinstance(headers, Mapping):
            continue
        for name in ("x-request-id", "x-tt-logid", "x-trace-id"):
            if headers.get(name):
                return _sanitize_text(headers[name])
    for error in chain:
        match = _REQUEST_ID.search(str(error))
        if match is not None:
            return _sanitize_text(match.group(1))
    return ""


def _error_diagnostics(chain: list[Exception]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for error in chain:
        fields_source = {
            name: getattr(error, name)
            for name in (
                "status_code",
                "status",
                "http_status",
                "http_status_code",
                "error_code",
                "errorCode",
                "code",
                "request_id",
                "requestId",
                "trace_id",
                "traceId",
                "message",
                "hint",
                "detail",
                "details",
                "reason",
                "region",
                "provider",
                "operation",
            )
            if getattr(error, name, None) not in (None, "")
        }
        try:
            fields_source.update(
                {
                    str(key): value
                    for key, value in list(vars(error).items())[:50]
                    if not str(key).startswith("_")
                }
            )
        except TypeError:
            pass
        response = getattr(error, "response", None)
        response_status = getattr(response, "status_code", None)
        if response_status is not None:
            fields_source["responseStatus"] = response_status
        response_headers = getattr(response, "headers", None)
        if isinstance(response_headers, Mapping):
            selected_headers = {
                str(key): value
                for key, value in response_headers.items()
                if str(key).casefold()
                in {
                    "content-type",
                    "retry-after",
                    "x-request-id",
                    "x-trace-id",
                    "x-tt-logid",
                }
            }
            if selected_headers:
                fields_source["responseHeaders"] = selected_headers
        fields = {
            str(key): _safe_diagnostic_value(value, key=key)
            for key, value in fields_source.items()
        }
        entry: dict[str, Any] = {"exceptionType": type(error).__name__}
        if fields:
            entry["fields"] = fields
        entries.append(entry)
    return {"errors": entries}


def _error_detail(error: Exception) -> tuple[int, dict[str, Any]]:
    chain = _error_chain(error)
    status_code = _error_status(chain)
    message = _sanitize_text(str(chain[0])) or type(chain[0]).__name__
    detail: dict[str, Any] = {
        "status": status_code,
        "errorCode": _error_code(chain),
        "message": message,
        "requestId": _error_request_id(chain),
        "diagnostics": _error_diagnostics(chain),
    }
    if len(chain) > 1:
        upstream_message = _sanitize_text(str(chain[-1]))
        if upstream_message and upstream_message != message:
            detail["upstreamMessage"] = upstream_message
        upstream_code = _error_code(chain[1:])
        if (
            upstream_code != "KNOWLEDGE_UPSTREAM_ERROR"
            and upstream_code != detail["errorCode"]
        ):
            detail["upstreamErrorCode"] = upstream_code
        upstream_status = _error_status(chain[1:])
        if upstream_status != 502 and upstream_status != status_code:
            detail["upstreamStatus"] = upstream_status
    return status_code, detail


def _safe_source_url(value: str) -> str:
    """Keep a useful source URL without persisting credentials or fragments."""
    parsed = urlsplit(value)
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not _is_sensitive_key(key)
        ],
        doseq=True,
    )
    hostname = parsed.hostname or ""
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit(
        (
            parsed.scheme,
            f"{display_host}{port}",
            parsed.path,
            query,
            "",
        )
    )


def _web_import_access_error(error: Exception) -> KnowledgeAccessError:
    if isinstance(error, WebImportSecurityError):
        return KnowledgeAccessError(
            "网页地址不安全或无法公开访问，请检查地址后重试。",
            status_code=422,
            error_code="KNOWLEDGE_WEB_URL_UNSAFE",
        )
    if isinstance(error, WebImportTooLargeError):
        return KnowledgeAccessError(
            "网页内容超过导入限制，请缩小内容范围后重试。",
            status_code=413,
            error_code="KNOWLEDGE_WEB_CONTENT_TOO_LARGE",
        )
    if isinstance(error, WebImportContentError):
        return KnowledgeAccessError(
            "网页没有可导入的正文内容，请确认地址指向公开的 HTML 页面。",
            status_code=422,
            error_code="KNOWLEDGE_WEB_CONTENT_INVALID",
        )
    if isinstance(error, WebImportFetchError):
        return KnowledgeAccessError(
            "网页暂时无法获取，请确认地址可公开访问后重试。",
            status_code=502,
            error_code="KNOWLEDGE_WEB_FETCH_FAILED",
        )
    return KnowledgeAccessError(
        "网页导入失败，请稍后重试。",
        status_code=502,
        error_code="KNOWLEDGE_WEB_IMPORT_FAILED",
    )


def mount_knowledge_routes(
    app: FastAPI,
    *,
    service: KnowledgeService,
    identity_resolver: Callable[[Request], KnowledgeIdentity],
    region_resolver: Callable[[str | None], str],
    region_candidates_resolver: Callable[[], tuple[str, ...]] | None = None,
    create_region_candidates_resolver: Callable[[], tuple[str, ...]] | None = None,
    web_importer: WebImportClient | None = None,
) -> None:
    importer: WebImportClient = web_importer or WebImporter()

    async def invoke(call: Callable[[], Any]) -> Any:
        try:
            return await run_in_threadpool(call)
        except KnowledgeAccessError as error:
            status_code, detail = _error_detail(error)
            raise HTTPException(
                status_code=status_code,
                detail=detail,
            ) from error
        except HTTPException:
            raise
        except Exception as error:
            logger.error(
                "Studio knowledge request failed error_type=%s",
                type(error).__name__,
            )
            status_code, detail = _error_detail(error)
            raise HTTPException(
                status_code=status_code,
                detail=detail,
            ) from error

    @app.get(
        "/web/knowledge-bases",
        response_model=KnowledgeListResponse,
        response_model_by_alias=True,
    )
    async def list_knowledge_bases(
        request: Request,
        region: str = "",
        project_name: str = Query(default="", alias="projectName"),
        next_token: str = Query(default="", alias="nextToken"),
        page_size: int = Query(default=30, alias="pageSize", ge=1, le=100),
    ) -> Any:
        identity = identity_resolver(request)
        return await invoke(
            lambda: service.list(
                identity=identity,
                region=region_resolver(region),
                project_name=project_name.strip() or None,
                next_token=next_token.strip() or None,
                page_size=page_size,
            )
        )

    @app.post(
        "/web/knowledge-bases",
        status_code=status.HTTP_201_CREATED,
        response_model=KnowledgeItemResponse,
        response_model_by_alias=True,
    )
    async def create_knowledge_base(
        body: CreateKnowledgeBaseBody,
        request: Request,
    ) -> Any:
        identity = identity_resolver(request)
        regions = (
            (region_resolver(body.region),)
            if body.region
            else (
                create_region_candidates_resolver()
                if create_region_candidates_resolver is not None
                else region_candidates_resolver()
                if region_candidates_resolver is not None
                else (region_resolver(None),)
            )
        )
        return await invoke(
            lambda: service.create_first_available(
                body,
                identity=identity,
                regions=regions,
            )
        )

    @app.get(
        "/web/knowledge-bases/{knowledge_id}",
        response_model=KnowledgeItemResponse,
        response_model_by_alias=True,
    )
    async def get_knowledge_base(
        knowledge_id: str,
        request: Request,
        region: str = "",
    ) -> Any:
        identity = identity_resolver(request)
        return await invoke(
            lambda: service.get(
                knowledge_id,
                identity=identity,
                region=region_resolver(region),
            )
        )

    @app.patch(
        "/web/knowledge-bases/{knowledge_id}",
        response_model=KnowledgeItemResponse,
        response_model_by_alias=True,
    )
    async def update_knowledge_base(
        knowledge_id: str,
        body: UpdateKnowledgeBaseBody,
        request: Request,
        region: str = "",
    ) -> Any:
        identity = identity_resolver(request)
        return await invoke(
            lambda: service.update(
                knowledge_id,
                body,
                identity=identity,
                region=region_resolver(region),
            )
        )

    @app.delete(
        "/web/knowledge-bases/{knowledge_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_knowledge_base(
        knowledge_id: str,
        request: Request,
        region: str = "",
    ) -> Response:
        identity = identity_resolver(request)
        await invoke(
            lambda: service.delete(
                knowledge_id,
                identity=identity,
                region=region_resolver(region),
            )
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/web/knowledge-bases/{knowledge_id}/documents")
    async def list_documents(
        knowledge_id: str,
        request: Request,
        region: str = "",
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        document_type: str = Query(default="", alias="documentType"),
    ) -> dict[str, Any]:
        identity = identity_resolver(request)
        items, has_more = await invoke(
            lambda: service.list_documents(
                knowledge_id,
                identity=identity,
                region=region_resolver(region),
                offset=offset,
                limit=limit,
                document_type=document_type.strip() or None,
            )
        )
        return {
            "items": items,
            "offset": offset,
            "limit": limit,
            "hasMore": has_more,
        }

    @app.post(
        "/web/knowledge-bases/{knowledge_id}/documents",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_document(
        knowledge_id: str,
        body: CreateDocumentBody,
        request: Request,
        region: str = "",
    ) -> Any:
        identity = identity_resolver(request)
        resolved_region = region_resolver(region)
        if body.source_type == "url":
            await invoke(
                lambda: service.authorize_document_operation(
                    knowledge_id,
                    identity=identity,
                    region=resolved_region,
                )
            )
            try:
                imported = await importer.import_url(body.url or "")
            except Exception as error:  # noqa: BLE001
                try:
                    raise _web_import_access_error(error) from error
                except KnowledgeAccessError as access_error:
                    status_code, detail = _error_detail(access_error)
                    raise HTTPException(
                        status_code=status_code,
                        detail=detail,
                    ) from access_error

            safe_url = _safe_source_url(imported.final_url)
            resolved_name = (
                (body.name or "").strip()
                or imported.title.strip()
                or (urlsplit(safe_url).hostname or "网页")
            )[:256]
            metadata = {
                **body.metadata,
                "_veadk_source_url": safe_url,
                "_veadk_source_title": imported.title.strip()[:512],
                "_veadk_content_format": "markdown",
                "_veadk_fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    delete=False,
                    suffix=".md",
                ) as temp:
                    temp_path = Path(temp.name)
                    temp.write(imported.markdown)
                result = await invoke(
                    lambda: service.upload_document(
                        knowledge_id,
                        identity=identity,
                        region=resolved_region,
                        source=temp_path,
                        file_name=f"web-{uuid4().hex}.txt",
                        mime_type="text/plain",
                        name=resolved_name,
                        document_type="txt",
                        metadata=metadata,
                    )
                )
                return {**result, "url": safe_url}
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
        return await invoke(
            lambda: service.create_document(
                knowledge_id,
                body,
                identity=identity,
                region=resolved_region,
            )
        )

    @app.post(
        "/web/knowledge-bases/{knowledge_id}/documents/upload",
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_document(
        knowledge_id: str,
        request: Request,
        file: Annotated[UploadFile, File()],
        name: Annotated[str, Form()] = "",
        document_type: Annotated[str, Form(alias="documentType")] = "",
        metadata: Annotated[str, Form()] = "{}",
        region: str = "",
    ) -> Any:
        identity = identity_resolver(request)
        try:
            validated = validate_knowledge_upload(
                file.filename or "",
                file.content_type or "",
            )
        except KnowledgeAccessError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail=str(error),
            ) from error
        resolved_name = name.strip() or validated.file_name
        if len(resolved_name) > 256:
            raise HTTPException(status_code=400, detail="知识名称不能超过 256 个字符。")
        resolved_document_type = document_type.strip() or validated.document_type
        if len(resolved_document_type) > 64:
            raise HTTPException(status_code=400, detail="知识类型不能超过 64 个字符。")
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError as error:
            raise HTTPException(
                status_code=400,
                detail="知识元数据不是有效的 JSON。",
            ) from error
        if not isinstance(parsed_metadata, dict):
            raise HTTPException(status_code=400, detail="知识元数据必须是 JSON 对象。")
        if not all(isinstance(key, str) for key in parsed_metadata):
            raise HTTPException(
                status_code=400,
                detail="知识元数据字段名必须是字符串。",
            )
        if len(metadata.encode("utf-8")) > 32 * 1024:
            raise HTTPException(status_code=413, detail="知识元数据不能超过 32 KB。")
        if service.max_upload_bytes <= 0:
            raise HTTPException(status_code=503, detail="知识库文件存储尚未配置。")

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=validated.suffix,
            ) as temp:
                temp_path = Path(temp.name)
                size_bytes = 0
                while chunk := await file.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > service.max_upload_bytes:
                        limit_mb = service.max_upload_bytes // (1024 * 1024)
                        raise HTTPException(
                            status_code=413,
                            detail=f"文件超过 {limit_mb} MB 上传限制。",
                        )
                    temp.write(chunk)
            if size_bytes == 0:
                raise HTTPException(status_code=400, detail="不能上传空文件。")
            resolved_region = region_resolver(region)
            return await invoke(
                lambda: service.upload_document(
                    knowledge_id,
                    identity=identity,
                    region=resolved_region,
                    source=temp_path,
                    file_name=validated.file_name,
                    mime_type=validated.mime_type,
                    name=resolved_name,
                    document_type=resolved_document_type,
                    metadata=parsed_metadata,
                )
            )
        finally:
            await file.close()
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    @app.get("/web/knowledge-bases/{knowledge_id}/documents/{document_id}")
    async def get_document(
        knowledge_id: str,
        document_id: str,
        request: Request,
        region: str = "",
    ) -> Any:
        identity = identity_resolver(request)
        return await invoke(
            lambda: service.get_document(
                knowledge_id,
                document_id,
                identity=identity,
                region=region_resolver(region),
            )
        )

    @app.get("/web/knowledge-bases/{knowledge_id}/documents/{document_id}/preview")
    async def preview_document(
        knowledge_id: str,
        document_id: str,
        request: Request,
        region: str = "",
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        identity = identity_resolver(request)
        return await invoke(
            lambda: service.preview_document(
                knowledge_id,
                document_id,
                identity=identity,
                region=region_resolver(region),
                offset=offset,
                limit=limit,
            )
        )

    @app.patch("/web/knowledge-bases/{knowledge_id}/documents/{document_id}")
    async def update_document(
        knowledge_id: str,
        document_id: str,
        body: UpdateDocumentBody,
        request: Request,
        region: str = "",
    ) -> Any:
        identity = identity_resolver(request)
        return await invoke(
            lambda: service.update_document(
                knowledge_id,
                document_id,
                body,
                identity=identity,
                region=region_resolver(region),
            )
        )

    @app.delete(
        "/web/knowledge-bases/{knowledge_id}/documents/{document_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_document(
        knowledge_id: str,
        document_id: str,
        request: Request,
        region: str = "",
    ) -> Response:
        identity = identity_resolver(request)
        await invoke(
            lambda: service.delete_document(
                knowledge_id,
                document_id,
                identity=identity,
                region=region_resolver(region),
            )
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["mount_knowledge_routes"]
