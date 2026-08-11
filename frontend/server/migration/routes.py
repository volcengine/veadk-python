# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""FastAPI boundary for Studio project migration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .models import ConfirmMigrationBody, CreateMigrationTaskBody
from .service import (
    MIGRATION_UPLOAD_MAX_BYTES,
    MigrationError,
    MigrationService,
)

logger = logging.getLogger(__name__)
_ZIP_CONTENT_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}


def mount_migration_routes(
    app: Any,
    service: MigrationService,
    *,
    owner_resolver: Callable[[Request], str],
    creator_resolver: Callable[[Request], str],
) -> None:
    async def invoke(
        operation: str,
        call: Callable[[], Any],
        *,
        task_id: str = "",
    ) -> Any:
        try:
            return await run_in_threadpool(call)
        except MigrationError as error:
            logger.warning(
                "Studio migration request failed operation=%s task_id=%s "
                "code=%s retryable=%s",
                operation,
                task_id or "none",
                error.code,
                str(error.retryable).lower(),
            )
            raise HTTPException(
                status_code=error.status_code,
                detail=error.detail(),
            ) from error
        except Exception as error:
            logger.exception(
                "Studio migration internal failure operation=%s task_id=%s "
                "error_type=%s",
                operation,
                task_id or "none",
                type(error).__name__,
            )
            internal = MigrationError(
                "MIGRATION_INTERNAL",
                "迁移服务异常，请刷新状态后重试。",
                status_code=500,
                retryable=False,
            )
            raise HTTPException(
                status_code=internal.status_code,
                detail=internal.detail(),
            ) from error

    @app.get("/web/migrations/capabilities")
    async def capabilities(request: Request) -> dict[str, object]:
        owner_resolver(request)
        return await invoke("capabilities", service.capabilities)

    @app.get("/web/migrations/tasks")
    async def list_tasks(request: Request) -> dict[str, list[dict[str, object]]]:
        owner_id = owner_resolver(request)
        return await invoke(
            "list_tasks",
            lambda: service.list_tasks(owner_id),
        )

    @app.post("/web/migrations/tasks")
    async def create_task(
        body: CreateMigrationTaskBody,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        creator_name = creator_resolver(request)
        return await invoke(
            "create_task",
            lambda: service.create_task(body, owner_id, creator_name),
        )

    @app.put("/web/migrations/tasks/{task_id}/source")
    async def upload_source(
        task_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        content_type = (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        )
        if content_type not in _ZIP_CONTENT_TYPES:
            error = MigrationError(
                "MIGRATION_SOURCE_CONTENT_TYPE_INVALID",
                "请选择 ZIP 格式的本地项目文件。",
                status_code=415,
            )
            raise HTTPException(error.status_code, detail=error.detail())
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                declared_bytes = int(declared)
                if declared_bytes < 0:
                    raise ValueError("negative content length")
            except ValueError as error:
                invalid = MigrationError(
                    "MIGRATION_SOURCE_LENGTH_INVALID",
                    "项目 ZIP 大小格式无效。",
                    status_code=400,
                )
                raise HTTPException(
                    invalid.status_code,
                    detail=invalid.detail(),
                ) from error
            if declared_bytes > MIGRATION_UPLOAD_MAX_BYTES:
                too_large = MigrationError(
                    "MIGRATION_SOURCE_TOO_LARGE",
                    "项目 ZIP 不能超过 50 MiB。",
                    status_code=413,
                )
                raise HTTPException(
                    too_large.status_code,
                    detail=too_large.detail(),
                )
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > MIGRATION_UPLOAD_MAX_BYTES:
                too_large = MigrationError(
                    "MIGRATION_SOURCE_TOO_LARGE",
                    "项目 ZIP 不能超过 50 MiB。",
                    status_code=413,
                )
                raise HTTPException(
                    too_large.status_code,
                    detail=too_large.detail(),
                )
            content.extend(chunk)
        return await invoke(
            "upload_source",
            lambda: service.upload_source(task_id, owner_id, bytes(content)),
            task_id=task_id,
        )

    @app.get("/web/migrations/tasks/{task_id}")
    async def get_task(
        task_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        return await invoke(
            "get_task",
            lambda: service.get_task(task_id, owner_id),
            task_id=task_id,
        )

    @app.post("/web/migrations/tasks/{task_id}/confirm")
    async def confirm(
        task_id: str,
        body: ConfirmMigrationBody,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        return await invoke(
            "confirm",
            lambda: service.confirm(task_id, owner_id, body),
            task_id=task_id,
        )

    @app.post("/web/migrations/tasks/{task_id}/stop")
    async def stop(
        task_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        return await invoke(
            "stop",
            lambda: service.stop(task_id, owner_id),
            task_id=task_id,
        )

    @app.get("/web/migrations/tasks/{task_id}/artifact")
    async def artifact(
        task_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        return await invoke(
            "artifact",
            lambda: service.artifact(task_id, owner_id),
            task_id=task_id,
        )

    @app.get("/web/migrations/tasks/{task_id}/download")
    async def download(
        task_id: str,
        request: Request,
    ) -> Response:
        owner_id = owner_resolver(request)
        content, filename = await invoke(
            "download",
            lambda: service.download(task_id, owner_id),
            task_id=task_id,
        )
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/web/migrations/tasks/{task_id}/artifact/file")
    async def preview_file(
        task_id: str,
        request: Request,
        path: str = Query(min_length=1, max_length=4096),
    ) -> Response:
        owner_id = owner_resolver(request)
        content, media_type = await invoke(
            "preview_file",
            lambda: service.preview_file(task_id, owner_id, path),
            task_id=task_id,
        )
        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "no-store"},
        )

    @app.delete("/web/migrations/tasks/{task_id}")
    async def delete(
        task_id: str,
        request: Request,
    ) -> dict[str, bool]:
        owner_id = owner_resolver(request)
        await invoke(
            "delete",
            lambda: service.delete(task_id, owner_id),
            task_id=task_id,
        )
        return {"deleted": True}


__all__ = ["mount_migration_routes"]
