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

"""Thin FastAPI management routes for Studio cronjobs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Query, Request, Response, status

from .repository import CronjobConflict, CronjobNotFound
from .schemas import (
    CreateCronjobRequest,
    Cronjob,
    CronjobIdentity,
    CronjobListResponse,
    CronjobRun,
    CronjobRunListResponse,
    UpdateCronjobRequest,
)
from .service import (
    CronjobAccessDenied,
    CronjobRunQueueUnavailable,
    CronjobService,
)

IdentityResolver = Callable[[Request], CronjobIdentity]
RuntimeAuthorizer = Callable[[Request, str, str], Any]


def mount_routes(
    app: Any,
    service: CronjobService,
    identity_resolver: IdentityResolver,
    authorize_runtime: RuntimeAuthorizer | None = None,
) -> None:
    @app.get("/web/cronjobs", response_model=CronjobListResponse)
    async def list_cronjobs(
        request: Request,
        owner_id: str | None = Query(default=None, alias="ownerId", max_length=1024),
    ) -> CronjobListResponse:
        return await _invoke(
            lambda: service.list(
                identity_resolver(request),
                owner_id=owner_id,
            ),
            list_response=True,
        )

    @app.post(
        "/web/cronjobs",
        response_model=Cronjob,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_cronjob(
        body: CreateCronjobRequest,
        request: Request,
        owner_id: str | None = Query(default=None, alias="ownerId", max_length=1024),
    ) -> Cronjob:
        if authorize_runtime is not None:
            authorize_runtime(request, body.runtime_id, body.region)
        return await _invoke(
            lambda: service.create(identity_resolver(request), body, owner_id=owner_id)
        )

    @app.get("/web/cronjobs/{job_id}", response_model=Cronjob)
    async def get_cronjob(
        job_id: str,
        request: Request,
        owner_id: str | None = Query(default=None, alias="ownerId", max_length=1024),
    ) -> Cronjob:
        return await _invoke(
            lambda: service.get(identity_resolver(request), job_id, owner_id=owner_id)
        )

    @app.patch("/web/cronjobs/{job_id}", response_model=Cronjob)
    @app.post("/web/cronjobs/{job_id}/update", response_model=Cronjob)
    async def update_cronjob(
        job_id: str,
        body: UpdateCronjobRequest,
        request: Request,
        owner_id: str | None = Query(default=None, alias="ownerId", max_length=1024),
    ) -> Cronjob:
        identity = identity_resolver(request)
        if authorize_runtime is not None and (
            body.runtime_id is not None or body.region is not None
        ):
            current = await _invoke(
                lambda: service.get(identity, job_id, owner_id=owner_id)
            )
            authorize_runtime(
                request,
                body.runtime_id or current.runtime_id,
                body.region or current.region,
            )
        return await _invoke(
            lambda: service.update(identity, job_id, body, owner_id=owner_id)
        )

    @app.delete(
        "/web/cronjobs/{job_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    async def delete_cronjob(
        job_id: str,
        request: Request,
        owner_id: str | None = Query(default=None, alias="ownerId", max_length=1024),
    ) -> Response:
        await _invoke(
            lambda: service.delete(
                identity_resolver(request), job_id, owner_id=owner_id
            )
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/web/cronjobs/{job_id}/enable", response_model=Cronjob)
    async def enable_cronjob(
        job_id: str,
        request: Request,
        owner_id: str | None = Query(default=None, alias="ownerId", max_length=1024),
    ) -> Cronjob:
        return await _invoke(
            lambda: service.enable(
                identity_resolver(request), job_id, owner_id=owner_id
            )
        )

    @app.post("/web/cronjobs/{job_id}/disable", response_model=Cronjob)
    async def disable_cronjob(
        job_id: str,
        request: Request,
        owner_id: str | None = Query(default=None, alias="ownerId", max_length=1024),
    ) -> Cronjob:
        return await _invoke(
            lambda: service.disable(
                identity_resolver(request), job_id, owner_id=owner_id
            )
        )

    @app.post(
        "/web/cronjobs/{job_id}/run",
        response_model=CronjobRun,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def run_cronjob(
        job_id: str,
        request: Request,
        owner_id: str | None = Query(default=None, alias="ownerId", max_length=1024),
    ) -> CronjobRun:
        return await _invoke(
            lambda: service.request_run(
                identity_resolver(request), job_id, owner_id=owner_id
            )
        )

    @app.get(
        "/web/cronjobs/{job_id}/runs",
        response_model=CronjobRunListResponse,
    )
    async def list_cronjob_runs(
        job_id: str,
        request: Request,
        owner_id: str | None = Query(default=None, alias="ownerId", max_length=1024),
    ) -> CronjobRunListResponse:
        return await _invoke(
            lambda: service.list_runs(
                identity_resolver(request), job_id, owner_id=owner_id
            ),
            list_response=True,
        )

    @app.post(
        "/web/cronjobs/{job_id}/runs/{run_id}/cancel",
        response_model=CronjobRun,
    )
    async def cancel_cronjob_run(
        job_id: str,
        run_id: str,
        request: Request,
        owner_id: str | None = Query(default=None, alias="ownerId", max_length=1024),
    ) -> CronjobRun:
        return await _invoke(
            lambda: service.cancel(
                identity_resolver(request),
                job_id,
                run_id,
                owner_id=owner_id,
            )
        )


async def _invoke(call: Callable[[], Any], *, list_response: bool = False) -> Any:
    try:
        result = await call()
    except Exception as error:
        _raise_api_error(error)
        raise
    if list_response:
        return {"items": result}
    return result


def _raise_api_error(error: Exception) -> None:
    if isinstance(error, CronjobAccessDenied):
        raise HTTPException(status_code=403, detail=str(error)) from error
    if isinstance(error, CronjobNotFound):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, CronjobConflict):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, CronjobRunQueueUnavailable):
        raise HTTPException(status_code=503, detail=str(error)) from error
    raise HTTPException(
        status_code=502,
        detail="定时任务服务暂时不可用，请稍后重试。",
    ) from error


__all__ = ["IdentityResolver", "RuntimeAuthorizer", "mount_routes"]
