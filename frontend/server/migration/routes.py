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

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from frontend.server.source_projects import (
    SOURCE_PROJECT_EXCEPTIONS,
    SourceProjectService,
)

from .models import (
    ConfirmMigrationBody,
    CreateMigrationTaskBody,
    SubmitAnalysisAnswersBody,
)
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
    project_service: SourceProjectService | None = None,
) -> None:
    persistence_results: dict[tuple[str, str], dict[str, object]] = {}
    persistence_tasks: dict[tuple[str, str], asyncio.Task[dict[str, object]]] = {}
    watchers: dict[tuple[str, str], asyncio.Task[None]] = {}

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

    async def ensure_persisted(
        task_id: str,
        owner_id: str,
        *,
        wait: bool = True,
    ) -> dict[str, object]:
        key = (owner_id, task_id)
        cached = persistence_results.get(key)
        if cached is not None and cached.get("state") == "saved":
            return cached
        if project_service is None:
            result: dict[str, object] = {
                "state": "unavailable",
                "message": "项目存储尚未配置，迁移产物只在当前环境中保留。",
            }
            persistence_results[key] = result
            return result
        configured_project_service = project_service
        running = persistence_tasks.get(key)
        if running is not None:
            if wait:
                return await running
            return {
                "state": "saving",
                "message": "正在保存源码版本。",
            }

        async def persist() -> dict[str, object]:
            try:
                bundle = await run_in_threadpool(
                    service.persistence_bundle,
                    task_id,
                    owner_id,
                )
                project, version = await configured_project_service.persist_migration(
                    owner_id=owner_id,
                    task_id=bundle.task_id,
                    project_name=bundle.project_name,
                    artifact=bundle.artifact,
                    result=bundle.result,
                    result_bytes=bundle.result_bytes,
                    environment_defaults=bundle.environment_defaults,
                )
                result: dict[str, object] = {
                    "state": "saved",
                    "projectId": project.project_id,
                    "versionId": version.version_id,
                    "message": "源码已保存到已迁移项目。",
                }
            except (MigrationError, *SOURCE_PROJECT_EXCEPTIONS) as error:
                logger.warning(
                    "Could not persist migration source task_id=%s error_type=%s",
                    task_id,
                    type(error).__name__,
                )
                result = {
                    "state": "failed",
                    "message": "源码暂未保存，可刷新任务重试。",
                    "retryable": True,
                }
            except Exception:
                logger.exception(
                    "Unexpected migration persistence failure task_id=%s",
                    task_id,
                )
                result = {
                    "state": "failed",
                    "message": "源码暂未保存，可刷新任务重试。",
                    "retryable": True,
                }
            persistence_results[key] = result
            return result

        running = asyncio.create_task(persist())
        persistence_tasks[key] = running
        if not wait:

            def cleanup(completed: asyncio.Task[dict[str, object]]) -> None:
                if persistence_tasks.get(key) is completed:
                    persistence_tasks.pop(key, None)

            running.add_done_callback(cleanup)
            return {
                "state": "saving",
                "message": "正在保存源码版本。",
            }
        try:
            return await running
        finally:
            persistence_tasks.pop(key, None)

    async def with_persistence(
        task: dict[str, object],
        owner_id: str,
    ) -> dict[str, object]:
        task_id = str(task.get("id") or "")
        if task.get("state") not in {
            "succeeded",
            "succeeded_with_warnings",
            "partial",
        }:
            cached = persistence_results.get((owner_id, task_id))
            return {**task, "persistence": cached} if cached is not None else task
        return {
            **task,
            "persistence": await ensure_persisted(
                task_id,
                owner_id,
                wait=False,
            ),
        }

    def start_watcher(task_id: str, owner_id: str) -> None:
        key = (owner_id, task_id)
        current = watchers.get(key)
        if current is not None and not current.done():
            return

        async def watch() -> None:
            try:
                while True:
                    await asyncio.sleep(3)
                    try:
                        task = await run_in_threadpool(
                            service.get_task,
                            task_id,
                            owner_id,
                        )
                    except MigrationError as error:
                        if error.retryable:
                            continue
                        return
                    state = task.get("state")
                    if state in {
                        "succeeded",
                        "succeeded_with_warnings",
                        "partial",
                    }:
                        await ensure_persisted(task_id, owner_id)
                        return
                    if state in {"failed", "cancelled", "expired"}:
                        return
            finally:
                watchers.pop(key, None)

        watchers[key] = asyncio.create_task(watch())

    @app.get("/web/agent-migrations/capabilities")
    async def capabilities(request: Request) -> dict[str, object]:
        owner_resolver(request)
        return await invoke("capabilities", service.capabilities)

    @app.get("/web/agent-migrations/tasks")
    async def list_tasks(request: Request) -> dict[str, list[dict[str, object]]]:
        owner_id = owner_resolver(request)
        payload = await invoke(
            "list_tasks",
            lambda: service.list_tasks(owner_id),
        )
        items = payload.get("items") if isinstance(payload, dict) else None
        if isinstance(items, list):
            payload = {
                **payload,
                "items": await asyncio.gather(
                    *(
                        with_persistence(item, owner_id)
                        for item in items
                        if isinstance(item, dict)
                    )
                ),
            }
        return payload

    @app.post("/web/agent-migrations/tasks")
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

    @app.put("/web/agent-migrations/tasks/{task_id}/source")
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

    @app.get("/web/agent-migrations/tasks/{task_id}")
    async def get_task(
        task_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        task = await invoke(
            "get_task",
            lambda: service.get_task(task_id, owner_id),
            task_id=task_id,
        )
        return await with_persistence(task, owner_id)

    @app.post("/web/agent-migrations/tasks/{task_id}/answers")
    async def submit_answers(
        task_id: str,
        body: SubmitAnalysisAnswersBody,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        return await invoke(
            "submit_answers",
            lambda: service.submit_answers(task_id, owner_id, body),
            task_id=task_id,
        )

    @app.post("/web/agent-migrations/tasks/{task_id}/confirm")
    async def confirm(
        task_id: str,
        body: ConfirmMigrationBody,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        task = await invoke(
            "confirm",
            lambda: service.confirm(task_id, owner_id, body),
            task_id=task_id,
        )
        start_watcher(task_id, owner_id)
        return await with_persistence(task, owner_id)

    @app.post("/web/agent-migrations/tasks/{task_id}/stop")
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

    @app.get("/web/agent-migrations/tasks/{task_id}/activity")
    async def activity(
        task_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        return await invoke(
            "activity",
            lambda: service.activity(task_id, owner_id),
            task_id=task_id,
        )

    @app.get("/web/agent-migrations/tasks/{task_id}/artifact")
    async def artifact(
        task_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        artifact_payload = await invoke(
            "artifact",
            lambda: service.artifact(task_id, owner_id),
            task_id=task_id,
        )
        await ensure_persisted(task_id, owner_id, wait=False)
        return artifact_payload

    @app.get("/web/agent-migrations/tasks/{task_id}/download")
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

    @app.get("/web/agent-migrations/tasks/{task_id}/artifact/file")
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

    @app.delete("/web/agent-migrations/tasks/{task_id}")
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
