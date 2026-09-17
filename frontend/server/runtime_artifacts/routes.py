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

"""Authenticated list and content endpoints for Runtime session artifacts"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from .service import RuntimeArtifactAccess, RuntimeArtifactError, RuntimeArtifactService

AccessResolver = Callable[
    [Request, str, str, str, str],
    RuntimeArtifactAccess | Awaitable[RuntimeArtifactAccess],
]

_CONTENT_CSP = (
    "sandbox; default-src 'none'; script-src 'none'; "
    "img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; media-src 'self'; frame-ancestors 'self'; "
    "base-uri 'none'; form-action 'none'"
)


def mount_routes(
    app: FastAPI,
    service: RuntimeArtifactService,
    access_resolver: AccessResolver,
) -> None:
    async def resolve(
        request: Request, runtime_id: str, region: str, app_name: str, session_id: str
    ) -> RuntimeArtifactAccess:
        access = access_resolver(request, runtime_id, region, app_name, session_id)
        if inspect.isawaitable(access):
            access = await access
        return access

    @app.get("/web/runtime-artifacts/{runtime_id}/sessions/{session_id}")
    async def list_artifacts(
        runtime_id: str,
        session_id: str,
        request: Request,
        region: str = Query(
            ..., min_length=1, max_length=64, pattern=r"^[a-z]{2}(?:-[a-z0-9]+){1,3}$"
        ),
        appName: str = Query(..., min_length=1, max_length=256),
        limit: int = Query(default=200, ge=1, le=500),
        cursor: str = Query(default="", max_length=4096),
    ) -> dict[str, Any]:
        access = await resolve(request, runtime_id, region, appName, session_id)
        try:
            return await service.list(access, session_id, limit=limit, cursor=cursor)
        except RuntimeArtifactError as error:
            raise HTTPException(error.status_code, detail=str(error)) from error

    @app.get(
        "/web/runtime-artifacts/{runtime_id}/sessions/{session_id}/content/{path:path}"
    )
    async def artifact_content(
        runtime_id: str,
        session_id: str,
        path: str,
        request: Request,
        region: str = Query(
            ..., min_length=1, max_length=64, pattern=r"^[a-z]{2}(?:-[a-z0-9]+){1,3}$"
        ),
        appName: str = Query(..., min_length=1, max_length=256),
        download: bool = Query(default=False),
    ) -> StreamingResponse:
        access_started = perf_counter()
        access = await resolve(request, runtime_id, region, appName, session_id)
        access_ms = (perf_counter() - access_started) * 1000
        storage_started = perf_counter()
        try:
            content = await service.open_content(
                access,
                session_id,
                path,
                download=download,
                range_header=request.headers.get("range"),
            )
        except RuntimeArtifactError as error:
            raise HTTPException(error.status_code, detail=str(error)) from error
        storage_ms = (perf_counter() - storage_started) * 1000
        disposition = "attachment" if download else "inline"
        headers = {
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(content.name, safe='')}",
            "Content-Length": str(content.size),
            "Cache-Control": "private, no-store",
            "Accept-Ranges": "bytes",
            "Content-Security-Policy": _CONTENT_CSP,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Server-Timing": f"access;dur={access_ms:.1f}, storage_open;dur={storage_ms:.1f}",
        }
        if content.byte_range:
            start, end = content.byte_range
            headers["Content-Range"] = f"bytes {start}-{end}/{content.total_size}"
        return StreamingResponse(
            content.chunks(),
            status_code=206 if content.byte_range else 200,
            media_type=content.mime_type,
            headers=headers,
            background=BackgroundTask(content.close),
        )
