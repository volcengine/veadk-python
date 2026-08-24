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

"""Thin FastAPI routes for Studio Skill management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .archive import SkillArchiveError
from .models import CreateSkillSpaceBody, SkillIdentity, UpdateSkillSpaceBody
from .repository import SkillRepositoryError
from .service import SkillService

_MAX_ARCHIVE_BYTES = 20 * 1024 * 1024


def _convert_error(error: Exception) -> HTTPException:
    if isinstance(error, HTTPException):
        return error
    if isinstance(error, (SkillArchiveError, SkillRepositoryError)):
        return HTTPException(
            status_code=error.status_code,
            detail=error.detail(),
        )
    error_type = f"{type(error).__module__}.{type(error).__qualname__}"
    raw_message = str(error).strip() or repr(error)
    return HTTPException(
        status_code=502,
        detail={
            "code": "SKILL_SERVICE_UNAVAILABLE",
            "message": "暂时无法访问 AgentKit Skills。",
            "retryable": True,
            "originalError": {
                "type": error_type,
                "message": raw_message,
                "repr": repr(error),
            },
        },
    )


def mount_skill_routes(
    app: Any,
    service: SkillService,
    identity_resolver: Callable[[Request], SkillIdentity],
) -> None:
    async def invoke(call: Callable[[], Any]) -> Any:
        try:
            return await run_in_threadpool(call)
        except Exception as error:
            raise _convert_error(error) from error

    async def read_archive(request: Request) -> bytes:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in {
            "application/zip",
            "application/x-zip-compressed",
            "application/octet-stream",
        }:
            raise HTTPException(
                status_code=415,
                detail={
                    "code": "SKILL_CONTENT_TYPE_INVALID",
                    "message": "请选择 ZIP 格式的 Skill 文件。",
                    "retryable": False,
                },
            )
        declared = request.headers.get("content-length")
        if declared:
            try:
                if int(declared) > _MAX_ARCHIVE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "SKILL_ARCHIVE_TOO_LARGE",
                            "message": "Skill ZIP 不能超过 20 MiB。",
                            "retryable": False,
                        },
                    )
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "SKILL_CONTENT_LENGTH_INVALID",
                        "message": "上传文件大小格式无效。",
                        "retryable": False,
                    },
                ) from error
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > _MAX_ARCHIVE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "SKILL_ARCHIVE_TOO_LARGE",
                        "message": "Skill ZIP 不能超过 20 MiB。",
                        "retryable": False,
                    },
                )
            content.extend(chunk)
        return bytes(content)

    @app.post("/web/skill-management/validate")
    async def validate_archive(request: Request) -> dict[str, object]:
        identity = identity_resolver(request)
        content = await read_archive(request)
        return await invoke(lambda: service.validate_archive(identity, content))

    @app.get("/web/skill-management/spaces")
    async def list_spaces(
        request: Request,
        region: str = Query(min_length=1, max_length=64),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        project: str | None = Query(default=None, max_length=256),
    ) -> dict[str, object]:
        identity = identity_resolver(request)
        return await invoke(
            lambda: service.list_spaces(
                identity,
                region=region,
                page=page,
                page_size=page_size,
                project_name=(project or "").strip() or None,
            )
        )

    @app.post("/web/skill-management/spaces")
    async def create_space(
        body: CreateSkillSpaceBody,
        request: Request,
    ) -> dict[str, object]:
        identity = identity_resolver(request)
        return await invoke(lambda: service.create_space(identity, body))

    @app.put("/web/skill-management/spaces/{space_id}")
    async def update_space(
        space_id: str,
        body: UpdateSkillSpaceBody,
        request: Request,
    ) -> dict[str, object]:
        identity = identity_resolver(request)
        return await invoke(lambda: service.update_space(identity, space_id, body))

    @app.delete("/web/skill-management/spaces/{space_id}")
    async def delete_space(
        space_id: str,
        request: Request,
        region: str = Query(min_length=1, max_length=64),
    ) -> dict[str, bool]:
        identity = identity_resolver(request)
        await invoke(
            lambda: service.delete_space(
                identity,
                region=region,
                space_id=space_id,
            )
        )
        return {"deleted": True}

    @app.post("/web/skill-management/spaces/{space_id}/skills")
    async def upload_skill(
        space_id: str,
        request: Request,
        region: str = Query(min_length=1, max_length=64),
        project: str | None = Query(default=None, max_length=256),
    ) -> dict[str, object]:
        identity = identity_resolver(request)
        content = await read_archive(request)
        return await invoke(
            lambda: service.upload_skill(
                identity,
                region=region,
                project_name=(project or "").strip() or None,
                space_id=space_id,
                content=content,
            )
        )

    @app.delete("/web/skill-management/spaces/{space_id}/skills/{skill_id}")
    async def delete_skill(
        space_id: str,
        skill_id: str,
        request: Request,
        region: str = Query(min_length=1, max_length=64),
    ) -> dict[str, bool]:
        del space_id
        identity = identity_resolver(request)
        await invoke(
            lambda: service.delete_skill(
                identity,
                region=region,
                skill_id=skill_id,
            )
        )
        return {"deleted": True}

    @app.get("/web/skill-management/spaces/{space_id}/skills/{skill_id}/files")
    async def skill_files(
        space_id: str,
        skill_id: str,
        request: Request,
        region: str = Query(min_length=1, max_length=64),
        version: str | None = Query(default=None, max_length=128),
        skill_space_name: str | None = Query(default=None, max_length=256),
        skill_name: str | None = Query(default=None, max_length=256),
    ) -> dict[str, object]:
        identity = identity_resolver(request)
        return await invoke(
            lambda: service.skill_files(
                identity,
                region=region,
                space_id=space_id,
                skill_id=skill_id,
                version=(version or "").strip() or None,
                skill_space_name=(skill_space_name or "").strip() or None,
                skill_name=(skill_name or "").strip() or None,
            )
        )

    @app.get("/web/skill-management/spaces/{space_id}/skills/{skill_id}/archive")
    async def skill_archive(
        space_id: str,
        skill_id: str,
        request: Request,
        region: str = Query(min_length=1, max_length=64),
        version: str | None = Query(default=None, max_length=128),
        skill_space_name: str | None = Query(default=None, max_length=256),
        skill_name: str | None = Query(default=None, max_length=256),
    ) -> Response:
        identity = identity_resolver(request)
        content, filename = await invoke(
            lambda: service.skill_archive(
                identity,
                region=region,
                space_id=space_id,
                skill_id=skill_id,
                version=(version or "").strip() or None,
                skill_space_name=(skill_space_name or "").strip() or None,
                skill_name=(skill_name or "").strip() or None,
            )
        )
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


__all__ = ["mount_skill_routes"]
