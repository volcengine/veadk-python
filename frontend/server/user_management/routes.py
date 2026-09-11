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

"""Authenticated administration routes and request-scoped permission resolution."""

import asyncio
from collections.abc import Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware

from .errors import UserManagementError
from .policy import StudioPrincipal, StudioRole
from .service import UserManagementService


class RoleChange(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    role: StudioRole
    expected_role: StudioRole = Field(alias="expectedRole")


def error_response(error: UserManagementError) -> JSONResponse:
    return JSONResponse(
        {"detail": error.code, "code": error.code},
        status_code=error.status,
        headers={"Cache-Control": "no-store"},
    )


def _url_origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        port = parsed.port
        return (
            parsed.scheme,
            parsed.hostname,
            port if port is not None else (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


class IdentityRoleMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        service: UserManagementService,
        principal: Callable[[Request], StudioPrincipal | None],
    ):
        super().__init__(app)
        self.service = service
        self.principal = principal

    async def dispatch(self, request: Request, call_next):
        # OAuth stays outside this middleware and establishes the trusted identity first
        public = request.url.path in {
            "/",
            "/index.html",
            "/favicon.ico",
            "/web/auth-config",
            "/web/ui-config",
            "/web/site-logo",
        }
        if not public and not request.url.path.startswith(
            ("/assets/", "/oauth2/", "/skillhub/")
        ):
            principal = self.principal(request)
            if principal is not None:
                try:
                    request.state.studio_identity_principal = await asyncio.to_thread(
                        self.service.principal_for, principal
                    )
                except UserManagementError as error:
                    return error_response(error)
        response = await call_next(request)
        if request.url.path == "/web/access" or request.url.path.startswith(
            "/web/users"
        ):
            response.headers["Cache-Control"] = "no-store"
        return response


def mount_user_management(
    app: FastAPI,
    service: UserManagementService,
    principal: Callable[[Request], StudioPrincipal | None],
    *,
    public_url: str | None = None,
) -> None:
    # The configured callback URL remains public even when a gateway rewrites
    # the request scheme or host. Forwarded headers are not a trust source
    configured_origin = _url_origin(public_url) if public_url else None
    if public_url and configured_origin is None:
        raise ValueError("Studio public URL must be an absolute HTTP(S) URL")
    app.add_middleware(IdentityRoleMiddleware, service=service, principal=principal)

    @app.get("/web/users")
    async def list_users(
        request: Request,
        page: int = Query(1, ge=1),
        pageSize: int = Query(20, ge=1, le=100),
        query: str = Query("", max_length=200),
        role: StudioRole | None = None,
    ):
        try:
            return await asyncio.to_thread(
                service.list_users, principal(request), page, pageSize, query, role
            )
        except UserManagementError as error:
            return error_response(error)

    @app.patch("/web/users/{user_uid}/role")
    async def change_role(user_uid: str, body: RoleChange, request: Request):
        # Browser mutations must originate from this Studio, not another site
        origin = request.headers.get("origin")
        request_origin = _url_origin(origin) if origin else None
        expected_origin = configured_origin or _url_origin(str(request.url))
        if request.headers.get("sec-fetch-site") == "cross-site" or (
            origin and (request_origin is None or request_origin != expected_origin)
        ):
            return error_response(UserManagementError(403, "cross_origin_request"))
        try:
            return await asyncio.to_thread(
                service.change_role,
                principal(request),
                user_uid,
                body.role,
                body.expected_role,
            )
        except UserManagementError as error:
            return error_response(error)
