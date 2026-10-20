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

"""FastAPI transport for Studio workspace management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request

from veadk.utils.logger import get_logger

from .models import WorkspaceInput, WorkspacePatch
from .repository import (
    WorkspaceConflict,
    WorkspaceNotFound,
    WorkspaceStorageUnavailable,
)
from .service import WorkspaceService

logger = get_logger(__name__)


def mount_workspace_routes(
    app: Any,
    service: WorkspaceService,
    identity_resolver: Callable[[Request], str],
) -> None:
    @app.get("/web/workspaces")
    async def list_workspaces(request: Request) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            records = await service.list(owner_id)
        except Exception as error:
            _raise_api_error(error, "读取工作区列表")
            raise
        return {"items": [_public(record) for record in records]}

    @app.post("/web/workspaces", status_code=201)
    async def create_workspace(
        body: WorkspaceInput, request: Request
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(await service.create(owner_id, body))
        except Exception as error:
            _raise_api_error(error, "创建工作区")
            raise

    @app.get("/web/workspaces/{workspace_id}")
    async def get_workspace(workspace_id: str, request: Request) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(await service.get(owner_id, workspace_id))
        except Exception as error:
            _raise_api_error(error, "读取工作区")
            raise

    @app.patch("/web/workspaces/{workspace_id}")
    async def update_workspace(
        workspace_id: str, body: WorkspacePatch, request: Request
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(await service.update(owner_id, workspace_id, body))
        except Exception as error:
            _raise_api_error(error, "更新工作区")
            raise

    @app.delete("/web/workspaces/{workspace_id}", status_code=204)
    async def delete_workspace(workspace_id: str, request: Request) -> None:
        owner_id = identity_resolver(request)
        try:
            await service.delete(owner_id, workspace_id)
        except Exception as error:
            _raise_api_error(error, "删除工作区")
            raise

    @app.put("/web/workspaces/{workspace_id}/environments/{environment_id}")
    async def add_workspace_environment(
        workspace_id: str, environment_id: str, request: Request
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(
                await service.add_environment(owner_id, workspace_id, environment_id)
            )
        except Exception as error:
            _raise_api_error(error, "添加工作区环境")
            raise

    @app.delete("/web/workspaces/{workspace_id}/environments/{environment_id}")
    async def remove_workspace_environment(
        workspace_id: str, environment_id: str, request: Request
    ) -> dict[str, Any]:
        owner_id = identity_resolver(request)
        try:
            return _public(
                await service.remove_environment(owner_id, workspace_id, environment_id)
            )
        except Exception as error:
            _raise_api_error(error, "移除工作区环境")
            raise


def _public(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json", by_alias=True, exclude={"owner_id"})


def _raise_api_error(error: Exception, action: str) -> None:
    if isinstance(error, WorkspaceNotFound):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, WorkspaceConflict):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, (ValueError, TypeError)):
        raise HTTPException(status_code=400, detail=str(error)) from error
    if isinstance(error, WorkspaceStorageUnavailable):
        raise HTTPException(status_code=503, detail=str(error)) from error
    logger.exception("Failed to %s", action)
    raise HTTPException(
        status_code=502, detail=f"{action}失败，请稍后重试。"
    ) from error


__all__ = ["mount_workspace_routes"]
