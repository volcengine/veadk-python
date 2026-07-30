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

"""FastAPI transport for authenticated Studio release jobs."""

from __future__ import annotations

import hmac
import json
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from frontend.service.studio_release_server.builder import (
    StudioReleaseBuilder,
)
from frontend.service.studio_release_server.models import (
    ReleaseRequest,
    ReleaseServerSettings,
    ReleaseStatus,
    SourceUpload,
    SourceUploadRequest,
)
from frontend.service.studio_release_server.service import (
    ReleaseConflictError,
    ReleaseNotFoundError,
    ReleaseService,
)
from frontend.service.studio_release_server.tos_store import (
    TosDependencyStore,
    TosJobStore,
    TosSourceStore,
)


def create_app(
    *,
    settings: ReleaseServerSettings | None = None,
    service: ReleaseService | None = None,
) -> FastAPI:
    """Create the release API with injectable dependencies for tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings = settings or ReleaseServerSettings.from_env()
        app.state.settings = resolved_settings
        if service is not None:
            app.state.release_service = service
        else:
            source_store = TosSourceStore(resolved_settings)
            app.state.release_service = ReleaseService(
                settings=resolved_settings,
                store=TosJobStore(resolved_settings),
                builder=StudioReleaseBuilder(
                    resolved_settings,
                    source_store=source_store,
                    dependency_store=TosDependencyStore(resolved_settings),
                ),
                source_store=source_store,
            )
        yield

    app = FastAPI(
        title="VeADK Studio Release Server",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    def require_api_key(
        request: Request,
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ) -> None:
        expected = request.app.state.settings.api_key
        if not x_api_key or not hmac.compare_digest(x_api_key, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid API key",
            )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", dependencies=[Depends(require_api_key)])
    def readyz() -> dict[str, str]:
        """Confirm that the active revision loaded the expected API key."""
        return {"status": "ready"}

    @app.post(
        "/source-upload",
        response_model=SourceUpload,
        response_model_by_alias=True,
        dependencies=[Depends(require_api_key)],
    )
    def source_upload(
        request: Request,
        payload: SourceUploadRequest,
    ) -> SourceUpload:
        try:
            return request.app.state.release_service.prepare_source_upload(
                payload.request_id
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post(
        "/release",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_api_key)],
    )
    def release(request: Request, payload: ReleaseRequest) -> StreamingResponse:
        try:
            release_service = request.app.state.release_service
            release_service.submit(payload)
        except ReleaseConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        def events() -> Iterator[str]:
            last_event = ""
            while True:
                current = release_service.get(payload.request_id)
                data = json.dumps(current.public_dict(), ensure_ascii=False)
                if data != last_event:
                    yield f"data: {data}\n\n"
                    last_event = data
                if current.state in {"succeeded", "failed"}:
                    return
                yield ": keepalive\n\n"
                time.sleep(1)

        return StreamingResponse(
            events(),
            status_code=status.HTTP_202_ACCEPTED,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get(
        "/status/{job_id}",
        response_model=ReleaseStatus,
        response_model_by_alias=True,
        dependencies=[Depends(require_api_key)],
    )
    def release_status(request: Request, job_id: str) -> ReleaseStatus:
        try:
            return request.app.state.release_service.get(job_id)
        except ReleaseNotFoundError as error:
            raise HTTPException(status_code=404, detail="release not found") from error

    return app


app = create_app()

__all__ = ["app", "create_app"]
