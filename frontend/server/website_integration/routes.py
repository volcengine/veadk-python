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

"""FastAPI routes for website integration management and embedded chat."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .models import (
    BootstrapSessionBody,
    CreateWebsiteIntegrationBody,
    RunWebsiteChatBody,
    WebsiteIntegration,
)
from .service import (
    WebsiteIntegrationService,
    WebsiteIntegrationStorageError,
    origin_matches_domain,
)

OwnerResolver = Callable[[Request], str]
RuntimeAuthorizer = Callable[[Request, str, str], Any]
RuntimeInvoker = Callable[[WebsiteIntegration, dict[str, Any]], Awaitable[Response]]

_EMBED_PATHS = frozenset({"/embed/session", "/embed/run_sse"})
_ORIGINAL_ORIGIN_STATE_KEY = "website_integration_origin"


class _WebsiteIntegrationOriginMiddleware:
    """Let embed routes apply their own token-bound Origin policy.

    Google ADK installs an application-wide browser Origin guard.  The guard is
    correct for Studio's own APIs, but it would reject every customer website
    before the embed routes can validate the generated token and configured
    domain.  Preserve the browser Origin in request state and hide it only from
    inner middleware for these two public embed endpoints.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") not in _EMBED_PATHS:
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers", []))
        origin = next(
            (
                value.decode("latin-1")
                for key, value in headers
                if key.lower() == b"origin"
            ),
            "",
        )
        if not origin:
            await self.app(scope, receive, send)
            return

        state = dict(scope.get("state") or {})
        state[_ORIGINAL_ORIGIN_STATE_KEY] = origin
        child_scope = {
            **scope,
            "headers": [
                (key, value) for key, value in headers if key.lower() != b"origin"
            ],
            "state": state,
        }
        await self.app(child_scope, receive, send)


def _request_origin(request: Request) -> str:
    return str(
        getattr(request.state, _ORIGINAL_ORIGIN_STATE_KEY, "")
        or request.headers.get("origin", "")
    )


def _cors_headers(origin: str) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
        "Access-Control-Max-Age": "600",
        "Vary": "Origin",
    }


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def mount_routes(
    app: Any,
    service: WebsiteIntegrationService,
    *,
    owner_id: OwnerResolver,
    authorize_runtime: RuntimeAuthorizer,
    invoke_runtime: RuntimeInvoker,
) -> None:
    app.add_middleware(_WebsiteIntegrationOriginMiddleware)

    @app.get("/web/website-integrations")
    async def list_website_integrations(request: Request) -> dict[str, Any]:
        try:
            integrations = await run_in_threadpool(
                service.list,
                owner_id(request),
            )
        except WebsiteIntegrationStorageError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return {"integrations": [item.public_dict() for item in integrations]}

    @app.post(
        "/web/website-integrations",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_website_integration(
        request: Request,
        body: CreateWebsiteIntegrationBody,
    ) -> dict[str, object]:
        authorize_runtime(request, body.runtime_id, body.region)
        try:
            integration = await run_in_threadpool(
                service.create,
                owner_id(request),
                body,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except WebsiteIntegrationStorageError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return integration.public_dict()

    @app.delete(
        "/web/website-integrations/{integration_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_website_integration(
        integration_id: str, request: Request
    ) -> Response:
        try:
            deleted = await run_in_threadpool(
                service.delete,
                owner_id(request),
                integration_id,
            )
        except WebsiteIntegrationStorageError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if not deleted:
            raise HTTPException(status_code=404, detail="Integration not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.options("/embed/session")
    async def website_integration_preflight(request: Request) -> Response:
        origin = _request_origin(request)
        if not origin:
            raise HTTPException(status_code=403, detail="Origin is required")
        return Response(status_code=204, headers=_cors_headers(origin))

    @app.post("/embed/session")
    async def create_website_integration_session(
        request: Request,
        body: BootstrapSessionBody,
    ) -> Response:
        origin = _request_origin(request)
        try:
            session = await run_in_threadpool(service.bootstrap, body.token, origin)
        except WebsiteIntegrationStorageError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if session is None:
            raise HTTPException(status_code=403, detail="Token or Origin is invalid")
        return JSONResponse(
            {
                "sessionToken": session.token,
                "expiresAt": session.expires_at.isoformat(),
            },
            headers=_cors_headers(origin),
        )

    @app.options("/embed/run_sse")
    async def website_integration_chat_preflight(request: Request) -> Response:
        origin = _request_origin(request)
        if not origin:
            raise HTTPException(status_code=403, detail="Origin is required")
        return Response(status_code=204, headers=_cors_headers(origin))

    @app.post("/embed/run_sse")
    async def run_website_integration_chat(
        request: Request,
        body: RunWebsiteChatBody,
    ) -> Response:
        try:
            integration = await run_in_threadpool(
                service.integration_for_session,
                _bearer_token(request),
            )
        except WebsiteIntegrationStorageError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if integration is None:
            raise HTTPException(status_code=401, detail="Session is invalid")
        origin = _request_origin(request)
        if not origin_matches_domain(origin, integration.domain):
            raise HTTPException(status_code=403, detail="Origin is invalid")
        message = body.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        payload = {
            "app_name": integration.app_name,
            "user_id": body.user_id,
            "session_id": body.session_id,
            "new_message": {"role": "user", "parts": [{"text": message}]},
            "streaming": True,
        }
        response = await invoke_runtime(integration, payload)
        response.headers.update(_cors_headers(origin))
        return response
