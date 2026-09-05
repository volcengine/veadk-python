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

"""FastAPI transport for Studio environment management and image builds."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Query, Request

from veadk.utils.logger import get_logger

from .models import (
    EnvironmentInput,
    EnvironmentPatch,
    EnvironmentShareCodesRequest,
    RepositoryInspectRequest,
)
from .repository import (
    EnvironmentConflict,
    EnvironmentNotFound,
    EnvironmentStorageUnavailable,
)
from .resources import EnvironmentResourceError
from .service import EnvironmentService

logger = get_logger(__name__)


def mount_environment_routes(
    app: Any,
    service: EnvironmentService,
    identity_resolver: Callable[[Request], str],
) -> None:
    @app.post("/web/v3/environment-repositories/inspect")
    @app.post("/web/environment-repositories/inspect")
    async def inspect_environment_repository(
        body: RepositoryInspectRequest,
        request: Request,
    ) -> dict[str, Any]:
        _ = identity_resolver(request)
        try:
            inspection = await service.inspect_repository(body.repository_url, body.ref)
            return _public(inspection)
        except Exception as error:
            _raise_api_error(error, "探查 Git 仓库")
            raise

    @app.get("/web/v3/environments")
    @app.get("/web/environments")
    async def list_environments(request: Request) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            records = await service.list(owner_id)
        except Exception as error:
            _raise_api_error(error, "读取环境列表")
            raise
        return {"items": [_public(record) for record in records]}

    @app.post("/web/v3/environments", status_code=201)
    @app.post("/web/environments", status_code=201)
    async def create_environment(
        body: EnvironmentInput,
        request: Request,
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(await service.create(owner_id, body))
        except Exception as error:
            _raise_api_error(error, "创建环境")
            raise

    @app.get("/web/v3/environments/{environment_id}")
    @app.get("/web/environments/{environment_id}")
    async def get_environment(
        environment_id: str,
        request: Request,
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(await service.get(owner_id, environment_id))
        except Exception as error:
            _raise_api_error(error, "读取环境")
            raise

    @app.post("/web/v3/environments/{environment_id}/share-code")
    @app.post("/web/environments/{environment_id}/share-code")
    async def export_environment_share_code(
        environment_id: str,
        request: Request,
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(await service.export_share_code(owner_id, environment_id))
        except Exception as error:
            _raise_api_error(error, "导出环境分享码")
            raise

    @app.post("/web/v3/environment-share-codes/inspect")
    @app.post("/web/environment-share-codes/inspect")
    async def inspect_environment_share_codes(
        body: EnvironmentShareCodesRequest,
        request: Request,
    ) -> dict[str, Any]:
        _ = identity_resolver(request)
        try:
            return _public(await service.inspect_share_codes(body.share_codes))
        except Exception as error:
            _raise_api_error(error, "解析环境分享码")
            raise

    @app.post("/web/v3/environment-share-codes/import")
    @app.post("/web/environment-share-codes/import")
    async def import_environment_share_codes(
        body: EnvironmentShareCodesRequest,
        request: Request,
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(await service.import_share_codes(owner_id, body.share_codes))
        except Exception as error:
            _raise_api_error(error, "导入环境分享码")
            raise

    @app.patch("/web/v3/environments/{environment_id}")
    @app.patch("/web/environments/{environment_id}")
    async def update_environment(
        environment_id: str,
        body: EnvironmentPatch,
        request: Request,
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(await service.update(owner_id, environment_id, body))
        except Exception as error:
            _raise_api_error(error, "更新环境")
            raise

    @app.delete("/web/v3/environments/{environment_id}", status_code=204)
    @app.post("/web/v3/environments/{environment_id}/delete", status_code=204)
    @app.delete("/web/environments/{environment_id}", status_code=204)
    @app.post("/web/environments/{environment_id}/delete", status_code=204)
    async def delete_environment(environment_id: str, request: Request) -> None:
        owner_id = identity_resolver(request)
        try:
            await service.delete(owner_id, environment_id)
        except Exception as error:
            _raise_api_error(error, "删除环境")
            raise

    @app.post("/web/v3/environments/{environment_id}/build", status_code=202)
    @app.post("/web/environments/{environment_id}/build", status_code=202)
    async def build_environment(
        environment_id: str,
        request: Request,
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(await service.start_build(owner_id, environment_id))
        except Exception as error:
            _raise_api_error(error, "启动环境镜像构建")
            raise

    @app.get("/web/v3/environments/{environment_id}/builds/{version_id}")
    @app.get("/web/environments/{environment_id}/builds/{version_id}")
    async def get_environment_build(
        environment_id: str,
        version_id: str,
        request: Request,
        include_logs: bool = Query(default=False, alias="includeLogs"),
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(
                await service.get_build(
                    owner_id,
                    environment_id,
                    version_id,
                    include_logs=include_logs,
                )
            )
        except Exception as error:
            _raise_api_error(error, "读取环境镜像构建状态")
            raise

    @app.get("/web/v3/environments/{environment_id}/builds/{version_id}/manifest")
    @app.get("/web/environments/{environment_id}/builds/{version_id}/manifest")
    async def get_environment_manifest(
        environment_id: str,
        version_id: str,
        request: Request,
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            manifest = await service.get_manifest(owner_id, environment_id, version_id)
            if not request.url.path.startswith("/web/v3/"):
                manifest = manifest.model_copy(
                    update={"api_version": "agentkit.studio/v1alpha1"}
                )
            return _public(manifest)
        except Exception as error:
            _raise_api_error(error, "读取环境 Manifest")
            raise

    @app.get("/web/v3/environment-resources")
    @app.get("/web/environment-resources")
    async def environment_resources(request: Request) -> dict[str, Any]:
        _ = identity_resolver(request)
        try:
            return _public(service.resource_info())
        except Exception as error:
            _raise_api_error(error, "读取环境构建资源")
            raise


def _public(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json", by_alias=True, exclude={"owner_id"})


def _raise_api_error(error: Exception, action: str) -> None:
    if isinstance(error, EnvironmentNotFound):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, EnvironmentConflict):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, (ValueError, TypeError)):
        raise HTTPException(status_code=400, detail=str(error)) from error
    if isinstance(error, EnvironmentStorageUnavailable):
        raise HTTPException(status_code=503, detail=str(error)) from error
    if isinstance(error, EnvironmentResourceError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    logger.exception("Failed to %s", action)
    raise HTTPException(
        status_code=502,
        detail=f"{action}失败，请稍后重试。",
    ) from error


__all__ = ["mount_environment_routes"]
