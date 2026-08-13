# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""FastAPI composition and transport for the Studio model catalog."""

from __future__ import annotations

import os
from collections.abc import Callable

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response

from frontend.server.video.client import (
    ArkHttpClient,
    ArkTokenCache,
    ArkTokenProvider,
)

from .client import (
    PROVIDER_CONFIGS,
    CredentialResolver,
    ModelApiKeyClient,
    ModelCatalogClient,
    ModelCatalogError,
    Provider,
    SignedRequest,
)
from .models import (
    ModelApiKeysResponse,
    ModelApiKeyValueResponse,
    ModelOptionsResponse,
)
from .service import ModelApiKeyService, ModelCatalogService

_NO_STORE_HEADERS = {"Cache-Control": "no-store"}
_RAW_KEY_UPSTREAM_ERROR = "无法读取所选 API Key，请检查云账号权限后重试。"


def build_model_catalog_service(
    *,
    provider: Provider,
    resolve_credentials: CredentialResolver,
    http_client: httpx.AsyncClient | None = None,
    token_loader: Callable[..., str] | None = None,
    signed_request: SignedRequest | None = None,
) -> ModelCatalogService:
    if provider not in PROVIDER_CONFIGS:
        raise ValueError(f"Unsupported model catalog provider: {provider}")
    config = PROVIDER_CONFIGS[provider]
    token_cache = (
        ArkTokenCache(
            provider=provider,
            region=config.region,
            resolve_credentials=resolve_credentials,
            api_key_name=os.getenv("MODEL_AGENT_API_KEY_NAME") or None,
        )
        if token_loader is None
        else ArkTokenCache(
            provider=provider,
            region=config.region,
            resolve_credentials=resolve_credentials,
            api_key_name=os.getenv("MODEL_AGENT_API_KEY_NAME") or None,
            token_loader=token_loader,
        )
    )
    transport = ArkHttpClient(
        provider=provider,
        api_base=config.api_base,
        token_provider=ArkTokenProvider(
            token_cache,
            os.getenv("MODEL_AGENT_API_KEY", ""),
        ),
        http_client=http_client,
    )
    client = (
        ModelCatalogClient(
            config=config,
            resolve_credentials=resolve_credentials,
            ark_http_client=transport,
        )
        if signed_request is None
        else ModelCatalogClient(
            config=config,
            resolve_credentials=resolve_credentials,
            ark_http_client=transport,
            signed_request=signed_request,
        )
    )
    api_key_client = (
        ModelApiKeyClient(
            config=config,
            resolve_credentials=resolve_credentials,
        )
        if signed_request is None
        else ModelApiKeyClient(
            config=config,
            resolve_credentials=resolve_credentials,
            signed_request=signed_request,
        )
    )
    return ModelCatalogService(
        provider=provider,
        client=client,
        api_keys=ModelApiKeyService(
            provider=provider,
            client=api_key_client,
            default_key_name=os.getenv("MODEL_AGENT_API_KEY_NAME") or None,
        ),
    )


def mount_model_catalog_routes(
    app: FastAPI,
    *,
    service: ModelCatalogService,
    authorize: Callable[[Request], object],
) -> None:
    @app.get(
        "/web/model-api-keys",
        response_model=ModelApiKeysResponse,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    async def model_api_keys(
        request: Request,
        refresh: bool = Query(default=False),
    ) -> ModelApiKeysResponse:
        authorize(request)
        try:
            return await service.list_api_keys(force_refresh=refresh)
        except ModelCatalogError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail=str(error),
            ) from error

    @app.post(
        "/web/model-api-keys/{api_key_id}/value",
        response_model=ModelApiKeyValueResponse,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    async def model_api_key_value(
        api_key_id: str,
        request: Request,
        response: Response,
    ) -> ModelApiKeyValueResponse:
        try:
            authorize(request)
        except HTTPException as error:
            raise HTTPException(
                status_code=error.status_code,
                detail=error.detail,
                headers={**(error.headers or {}), **_NO_STORE_HEADERS},
            ) from None
        response.headers.update(_NO_STORE_HEADERS)
        try:
            value = await service.resolve_raw_key(api_key_id)
        except ModelCatalogError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail=str(error),
                headers=_NO_STORE_HEADERS,
            ) from None
        except Exception:  # noqa: BLE001 - never expose unexpected upstream details
            raise HTTPException(
                status_code=502,
                detail=_RAW_KEY_UPSTREAM_ERROR,
                headers=_NO_STORE_HEADERS,
            ) from None
        return ModelApiKeyValueResponse(value=value)

    @app.get(
        "/web/model-options",
        response_model=ModelOptionsResponse,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    async def model_options(
        request: Request,
        api_key_id: str | None = Query(default=None, alias="apiKeyId"),
        refresh: bool = Query(default=False),
    ) -> ModelOptionsResponse:
        authorize(request)
        try:
            if api_key_id is None and not refresh:
                return await service.list_options()
            return await service.list_options(
                api_key_id=api_key_id,
                force_refresh=refresh,
            )
        except ModelCatalogError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail=str(error),
            ) from error


__all__ = ["build_model_catalog_service", "mount_model_catalog_routes"]
