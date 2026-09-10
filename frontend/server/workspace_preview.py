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

"""Authenticated routes for projects in a personal persistent Sandbox."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import PurePosixPath

from urllib.parse import parse_qs, quote, urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from veadk.cli.frontend_sandbox import (
    SandboxCloudGateway,
    SandboxCloudSession,
    SandboxError,
)


def _validate_folder(folder: str) -> None:
    path = PurePosixPath(folder)
    if not path.is_absolute() or ".." in path.parts or "\x00" in folder:
        raise ValueError("Invalid Sandbox workspace folder")


def aio_url(endpoint: str, *, folder: str | None = None, local: bool = False) -> str:
    """Preserve the session routing and authorization query on the AIO root."""
    parts = urlsplit(endpoint)
    local_host = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    valid_scheme = parts.scheme == "https" or (
        local and local_host and parts.scheme == "http"
    )
    if (
        not valid_scheme
        or not parts.hostname
        or parts.username
        or parts.password
        or (local and not local_host)
    ):
        raise ValueError("Invalid Sandbox endpoint")
    query = parts.query
    if folder is not None:
        _validate_folder(folder)
        if "folder" not in parse_qs(query, keep_blank_values=True):
            # Leave signed and provider-specific parameters byte-for-byte intact.
            query += ("&" if query else "") + "folder=" + quote(folder, safe="/")
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/") + "/", query, "")
    )


def _expired(session: SandboxCloudSession) -> bool:
    if session.status.lower() in {"expired", "deleted", "failed", "error"}:
        return True
    if not session.expire_at:
        return False
    try:
        expiry = datetime.fromisoformat(session.expire_at.replace("Z", "+00:00"))
        return expiry.replace(tzinfo=expiry.tzinfo or timezone.utc) <= datetime.now(
            timezone.utc
        )
    except ValueError:
        return True


def editor_url(endpoint: str, name: str) -> str:
    """Open the editor directly while preserving cloud routing credentials."""
    parts = urlsplit(aio_url(endpoint))
    path = parts.path.rstrip("/")
    if not path.endswith("/code-server"):
        path += "/code-server"
    return (
        aio_url(
            urlunsplit((parts.scheme, parts.netloc, path, parts.query, "")),
            folder="/home/gem/Projects/" + name,
        )
        + "&studio-resource-version=3"
    )


class ProjectInput(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def project_summary(session: SandboxCloudSession) -> dict[str, str]:
    return {
        "sessionId": session.instance_id,
        "name": session.display_name,
        "status": "expired" if _expired(session) else session.status.lower(),
        "expireAt": session.expire_at,
        "region": session.region,
    }


def project_response(session: SandboxCloudSession, name: str) -> JSONResponse:
    return JSONResponse(
        {
            **project_summary(session),
            "name": name,
            "url": editor_url(session.endpoint, name),
        },
        headers={
            "Cache-Control": "private, no-store",
            "Referrer-Policy": "no-referrer",
        },
    )


def mount_workspace_preview_routes(
    app: FastAPI,
    gateway: SandboxCloudGateway,
    owner_resolver: Callable[[Request], str],
    creator_resolver: Callable[[Request], str],
) -> None:
    tool_id = (os.getenv("STUDIO_WORKSPACE_TOOL_ID") or "").strip()
    from frontend.server.workspace_projects import PersistentWorkspaceProjects
    from frontend.server.sandbox_remote import SandboxRemoteError

    projects = PersistentWorkspaceProjects(gateway, tool_id)

    def require_tool() -> None:
        nonlocal tool_id
        tool_id = (os.getenv("STUDIO_WORKSPACE_TOOL_ID") or "").strip()
        projects.tool_id = tool_id
        if not tool_id:
            raise HTTPException(503, "请先配置工作区 Sandbox 镜像")

    @app.get("/web/workspace-preview/state")
    async def workspace_state(request: Request) -> JSONResponse:
        owner = owner_resolver(request)
        require_tool()
        try:
            return JSONResponse(
                await projects.state(owner),
                headers={"Cache-Control": "private, no-store"},
            )
        except (SandboxError, TimeoutError, ValueError) as error:
            raise HTTPException(502, "暂时无法确认工作区状态，请重试") from error

    @app.get("/web/workspace-preview/projects")
    async def list_projects(request: Request) -> JSONResponse:
        owner = owner_resolver(request)
        require_tool()
        try:
            cloud, names = await projects.list(owner, creator_resolver(request))
            details = await projects.describe(cloud, names)
            return JSONResponse(
                {
                    "projects": [
                        {**project_summary(cloud), **detail} for detail in details
                    ]
                },
                headers={"Cache-Control": "private, no-store"},
            )
        except (SandboxError, SandboxRemoteError, TimeoutError, ValueError) as error:
            raise HTTPException(502, "恢复工作区或读取项目列表失败，请重试") from error

    @app.post("/web/workspace-preview/projects")
    async def create_project(request: Request, body: ProjectInput) -> JSONResponse:
        owner = owner_resolver(request)
        require_tool()
        try:
            cloud = await projects.create(owner, creator_resolver(request), body.name)
            return project_response(cloud, body.name)
        except (SandboxError, SandboxRemoteError, TimeoutError, ValueError) as error:
            raise HTTPException(502, "项目初始化失败，请确认镜像可用后重试") from error

    @app.post("/web/workspace-preview/projects/{project_name}/open")
    async def open_project(request: Request, project_name: str) -> JSONResponse:
        owner = owner_resolver(request)
        require_tool()
        try:
            cloud = await projects.open(owner, creator_resolver(request), project_name)
            return project_response(cloud, project_name)
        except (SandboxError, SandboxRemoteError, TimeoutError, ValueError) as error:
            raise HTTPException(502, "恢复工作区或打开项目失败，请重试") from error
