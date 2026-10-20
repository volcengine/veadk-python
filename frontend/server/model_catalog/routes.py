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

"""FastAPI composition and transport for the Studio model catalog."""

from __future__ import annotations

import os
from collections.abc import Callable
from threading import Lock
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response

from veadk.cli.studio_model_catalog import (
    provider_allows_studio_development_model,
)

from .models import (
    ModelApiKeysResponse,
    ModelApiKeyValueResponse,
    ModelOptionsResponse,
)
from .errors import model_catalog_error_response
from .protocol import (
    CredentialResolver,
    ModelCatalogError,
    Provider,
    SignedRequest,
)

if TYPE_CHECKING:
    from .service import ModelCatalogService

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
    if provider not in {"volcengine", "byteplus"}:
        raise ValueError(f"Unsupported model catalog provider: {provider}")
    return _LazyModelCatalogService(
        provider=provider,
        resolve_credentials=resolve_credentials,
        http_client=http_client,
        token_loader=token_loader,
        signed_request=signed_request,
    )  # type: ignore[return-value]


class _LazyModelCatalogService:
    """Keep provider clients and request signing off Studio startup."""

    def __init__(
        self,
        *,
        provider: Provider,
        resolve_credentials: CredentialResolver,
        http_client: httpx.AsyncClient | None,
        token_loader: Callable[..., str] | None,
        signed_request: SignedRequest | None,
    ) -> None:
        self._provider: Provider = provider
        self._resolve_credentials = resolve_credentials
        self._http_client = http_client
        self._token_loader = token_loader
        self._signed_request = signed_request
        self._service: Any | None = None
        self._lock = Lock()

    def _resolve(self) -> ModelCatalogService:
        if self._service is not None:
            return self._service
        with self._lock:
            if self._service is None:
                self._service = _build_model_catalog_service(
                    provider=self._provider,
                    resolve_credentials=self._resolve_credentials,
                    http_client=self._http_client,
                    token_loader=self._token_loader,
                    signed_request=self._signed_request,
                )
        return self._service

    async def list_api_keys(
        self, *, force_refresh: bool = False
    ) -> ModelApiKeysResponse:
        return await self._resolve().list_api_keys(force_refresh=force_refresh)

    async def resolve_raw_key(self, key_id: str) -> str:
        return await self._resolve().resolve_raw_key(key_id)

    async def list_options(
        self,
        *,
        api_key_id: str | None = None,
        force_refresh: bool = False,
    ) -> ModelOptionsResponse:
        return await self._resolve().list_options(
            api_key_id=api_key_id,
            force_refresh=force_refresh,
        )


def _build_model_catalog_service(
    *,
    provider: Provider,
    resolve_credentials: CredentialResolver,
    http_client: httpx.AsyncClient | None,
    token_loader: Callable[..., str] | None,
    signed_request: SignedRequest | None,
) -> ModelCatalogService:
    from frontend.server.video.client import (
        ArkHttpClient,
        ArkTokenCache,
        ArkTokenProvider,
    )

    from .client import (
        PROVIDER_CONFIGS,
        ModelApiKeyClient,
        ModelCatalogClient,
    )
    from .service import ModelApiKeyService, ModelCatalogService

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
        response: Response,
        refresh: bool = Query(default=False),
    ) -> ModelApiKeysResponse | Response:
        authorize(request)
        response.headers.update(_NO_STORE_HEADERS)
        try:
            return await service.list_api_keys(force_refresh=refresh)
        except ModelCatalogError as error:
            return model_catalog_error_response(error)

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
    ) -> ModelApiKeyValueResponse | Response:
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
            return model_catalog_error_response(error)
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
        scope: Literal["development"] | None = Query(default=None),
    ) -> ModelOptionsResponse | Response:
        authorize(request)
        try:
            if api_key_id is None and not refresh:
                response = await service.list_options()
            else:
                response = await service.list_options(
                    api_key_id=api_key_id,
                    force_refresh=refresh,
                )
            if scope != "development":
                return response
            return response.model_copy(
                update={
                    "models": [
                        model
                        for model in response.models
                        if provider_allows_studio_development_model(
                            response.provider, model.id
                        )
                    ]
                }
            )
        except ModelCatalogError as error:
            return model_catalog_error_response(error)


__all__ = ["build_model_catalog_service", "mount_model_catalog_routes"]
