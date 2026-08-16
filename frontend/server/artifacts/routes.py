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

"""FastAPI routes for a user's durable artifact library."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from veadk.utils.logger import get_logger

from .models import ArtifactMetadataPatch, ArtifactSyncRequest
from .repository import ArtifactNotFound
from .service import ArtifactIngestError, ArtifactService, ArtifactStorageUnavailable

logger = get_logger(__name__)


def mount_routes(
    app: Any,
    service: ArtifactService,
    identity_resolver: Callable[[Request], str],
) -> None:
    @app.get("/web/artifacts")
    async def list_artifacts(request: Request) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            items = await service.list(owner_id)
        except Exception as error:
            _raise_api_error(error, "读取产物库")
            raise
        return {
            "items": [item.model_dump(mode="json", by_alias=True) for item in items]
        }

    @app.post("/web/artifacts/sync")
    async def sync_artifacts(
        body: ArtifactSyncRequest,
        request: Request,
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            items = await service.sync(owner_id, body.candidates)
        except Exception as error:
            _raise_api_error(error, "同步产物")
            raise
        return {
            "items": [item.model_dump(mode="json", by_alias=True) for item in items]
        }

    @app.patch("/web/artifacts/{artifact_id}")
    async def update_artifact(
        artifact_id: str,
        body: ArtifactMetadataPatch,
        request: Request,
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            item = await service.update(owner_id, artifact_id, body)
        except Exception as error:
            _raise_api_error(error, "更新产物")
            raise
        return item.model_dump(mode="json", by_alias=True)

    @app.delete("/web/artifacts/{artifact_id}", status_code=204)
    @app.post("/web/artifacts/{artifact_id}/delete", status_code=204)
    async def delete_artifact(artifact_id: str, request: Request) -> None:
        owner_id = identity_resolver(request)
        try:
            await service.delete(owner_id, artifact_id)
        except Exception as error:
            _raise_api_error(error, "删除产物")
            raise

    @app.get("/web/artifacts/{artifact_id}/content")
    async def artifact_content(
        artifact_id: str,
        request: Request,
        download: bool = Query(default=False),
    ) -> StreamingResponse:
        owner_id = identity_resolver(request)
        try:
            record, response = await service.open_content(owner_id, artifact_id)
        except Exception as error:
            _raise_api_error(error, "读取产物内容")
            raise
        disposition = "attachment" if download else "inline"
        headers = {
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{quote(record.name, safe='')}"
            ),
            "Cache-Control": "private, max-age=300",
        }
        if record.size_bytes:
            headers["Content-Length"] = str(record.size_bytes)
        return StreamingResponse(
            _response_chunks(response),
            media_type=record.mime_type,
            headers=headers,
            background=BackgroundTask(_close_response, response),
        )


def _response_chunks(response: Any) -> Iterator[bytes]:
    read = getattr(response, "read", None)
    if callable(read):
        try:
            while True:
                chunk = read(64 * 1024)
                if not chunk:
                    break
                yield _response_bytes(chunk)
            return
        except TypeError:
            content = read()
            if content:
                yield _response_bytes(content)
            return
    for chunk in response:
        if chunk:
            yield _response_bytes(chunk)


def _response_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    raise TypeError("Artifact content stream returned non-bytes data.")


def _close_response(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _raise_api_error(error: Exception, action: str) -> None:
    if isinstance(error, ArtifactNotFound):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, ArtifactStorageUnavailable):
        raise HTTPException(status_code=503, detail=str(error)) from error
    if isinstance(error, ArtifactIngestError):
        raise HTTPException(status_code=400, detail=str(error)) from error
    if isinstance(error, httpx.HTTPStatusError):
        raise HTTPException(
            status_code=502,
            detail="生成服务暂时无法提供产物内容，请稍后重试。",
        ) from error
    logger.exception("Failed to %s", action)
    raise HTTPException(
        status_code=502,
        detail=f"{action}失败，请稍后重试。",
    ) from error


__all__ = ["mount_routes"]
