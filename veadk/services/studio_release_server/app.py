"""FastAPI transport for authenticated Studio release jobs."""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status

from veadk.services.studio_release_server.builder import (
    StudioReleaseBuilder,
)
from veadk.services.studio_release_server.models import (
    ReleaseRequest,
    ReleaseServerSettings,
    ReleaseStatus,
)
from veadk.services.studio_release_server.service import (
    ReleaseConflictError,
    ReleaseNotFoundError,
    ReleaseService,
)
from veadk.services.studio_release_server.tos_store import TosJobStore


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
        app.state.release_service = service or ReleaseService(
            settings=resolved_settings,
            store=TosJobStore(resolved_settings),
            builder=StudioReleaseBuilder(resolved_settings),
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

    @app.post(
        "/release",
        response_model=ReleaseStatus,
        response_model_by_alias=True,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_api_key)],
    )
    def release(request: Request, payload: ReleaseRequest) -> ReleaseStatus:
        try:
            return request.app.state.release_service.submit(payload)
        except ReleaseConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

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
