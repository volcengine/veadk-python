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

"""Catalog joining rules and short-lived cache."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from typing import Any

from veadk.utils.logger import get_logger

from .client import ModelApiKeyClient, ModelCatalogClient, ModelCatalogError, Provider
from .models import (
    ModelApiKeyOption,
    ModelApiKeysResponse,
    ModelOption,
    ModelOptionsResponse,
)

logger = get_logger(__name__)

_CACHE_TTL_SECONDS = 300.0
_SUPPORTED_DOMAINS = {"LLM", "VLM"}
_SUPPORTED_TASK_TYPES = {"TextGeneration", "LLM Agent", "VLM Agent"}


class ModelCatalogService:
    def __init__(
        self,
        *,
        provider: Provider,
        client: ModelCatalogClient,
        api_keys: ModelApiKeyService | None = None,
        ttl_seconds: float = _CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provider: Provider = provider
        self._client = client
        self._api_keys = api_keys
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._cached: dict[str, tuple[ModelOptionsResponse, float]] = {}
        self._lock = asyncio.Lock()

    async def list_api_keys(
        self, *, force_refresh: bool = False
    ) -> ModelApiKeysResponse:
        if self._api_keys is None:
            return ModelApiKeysResponse(provider=self._provider, keys=[])
        return await self._api_keys.list_keys(force_refresh=force_refresh)

    async def resolve_raw_key(
        self,
        key_id: str,
        *,
        force_refresh: bool = False,
    ) -> str:
        if self._api_keys is None:
            raise ModelCatalogError(
                "当前环境未配置 Ark API Key 服务。",
                status_code=404,
            )
        return await self._api_keys.resolve_raw_key(
            key_id,
            force_refresh=force_refresh,
        )

    async def list_options(
        self,
        *,
        api_key_id: str | None = None,
        force_refresh: bool = False,
    ) -> ModelOptionsResponse:
        selected_key_id = api_key_id
        api_key: str | None = None
        if self._api_keys is not None:
            key_catalog = await self._api_keys.list_keys(force_refresh=force_refresh)
            selected_key_id = selected_key_id or key_catalog.default_key_id
            if selected_key_id is None:
                raise ModelCatalogError(
                    "当前账号暂无可用的 Ark API Key，请先在控制台创建。",
                    status_code=404,
                )
            api_key = await self._api_keys.resolve_raw_key(
                selected_key_id,
                force_refresh=force_refresh,
                known_keys=key_catalog,
            )
        cache_key = selected_key_id or "__legacy_default__"
        now = self._clock()
        cached = self._cached.get(cache_key)
        if not force_refresh and cached is not None and now < cached[1]:
            return cached[0]
        async with self._lock:
            now = self._clock()
            cached = self._cached.get(cache_key)
            if not force_refresh and cached is not None and now < cached[1]:
                return cached[0]
            try:
                list_models = (
                    self._client.list_models()
                    if api_key is None
                    else self._client.list_models(api_key=api_key)
                )
                activations, models = await asyncio.gather(
                    self._client.list_activations(),
                    list_models,
                )
                refreshed = ModelOptionsResponse(
                    provider=self._provider,
                    selected_api_key_id=selected_key_id,
                    models=join_model_options(activations, models),
                )
            except ModelCatalogError:
                if cached is None:
                    raise
                logger.warning(
                    "Refreshing the Studio model catalog failed; serving cached data."
                )
                self._cached[cache_key] = (
                    cached[0],
                    self._clock() + self._ttl_seconds,
                )
                return cached[0]
            self._cached[cache_key] = (
                refreshed,
                self._clock() + self._ttl_seconds,
            )
            return refreshed


class ModelApiKeyService:
    """Cache safe key metadata and raw values separately."""

    def __init__(
        self,
        *,
        provider: Provider,
        client: ModelApiKeyClient,
        default_key_name: str | None = None,
        ttl_seconds: float = _CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provider: Provider = provider
        self._client = client
        self._default_key_name = (default_key_name or "").strip()
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._cached_keys: ModelApiKeysResponse | None = None
        self._keys_expire_at = 0.0
        self._raw_keys: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    async def list_keys(self, *, force_refresh: bool = False) -> ModelApiKeysResponse:
        now = self._clock()
        if (
            not force_refresh
            and self._cached_keys is not None
            and now < self._keys_expire_at
        ):
            return self._cached_keys
        async with self._lock:
            now = self._clock()
            if (
                not force_refresh
                and self._cached_keys is not None
                and now < self._keys_expire_at
            ):
                return self._cached_keys
            raw_items = await self._client.list_keys()
            keys = [ModelApiKeyOption(**item) for item in raw_items]
            default_key_id = next(
                (
                    item.id
                    for item in keys
                    if self._default_key_name and item.name == self._default_key_name
                ),
                keys[0].id if keys else None,
            )
            response = ModelApiKeysResponse(
                provider=self._provider,
                keys=keys,
                default_key_id=default_key_id,
            )
            self._cached_keys = response
            self._keys_expire_at = self._clock() + self._ttl_seconds
            return response

    async def resolve_raw_key(
        self,
        key_id: str,
        *,
        force_refresh: bool = False,
        known_keys: ModelApiKeysResponse | None = None,
    ) -> str:
        catalog = known_keys or await self.list_keys(force_refresh=force_refresh)
        if not any(item.id == key_id for item in catalog.keys):
            raise ModelCatalogError(
                "所选 API Key 不存在或已被删除，请刷新后重新选择。",
                status_code=404,
            )
        now = self._clock()
        cached = self._raw_keys.get(key_id)
        if not force_refresh and cached is not None and now < cached[1]:
            return cached[0]
        raw_key = await self._client.get_raw_key(key_id)
        self._raw_keys[key_id] = (
            raw_key,
            self._clock() + self._ttl_seconds,
        )
        return raw_key


def join_model_options(
    activations: list[dict[str, Any]],
    models: list[dict[str, Any]],
) -> list[ModelOption]:
    """Join exact model versions to account activation metadata by model name."""
    activation_by_name = {
        _text(item, "FoundationModelName"): item
        for item in activations
        if _text(item, "FoundationModelName")
    }
    options: list[ModelOption] = []
    for model in models:
        if not _supports_agent(model):
            continue
        lifecycle = _text(model, "status") or "Running"
        if lifecycle == "Shutdown":
            continue
        name = _text(model, "name")
        model_id = _text(model, "id")
        activation = activation_by_name.get(name)
        if not name or not model_id:
            continue
        activation_state = (
            _text(activation, "State") if activation is not None else ""
        ) or "Unavailable"
        display_name = (
            _text(activation, "DisplayName") if activation is not None else ""
        ) or name
        vendor_name = _text(activation, "VendorName") if activation is not None else ""
        options.append(
            ModelOption(
                id=model_id,
                name=name,
                display_name=display_name,
                vendor_name=vendor_name,
                activation_state=activation_state,
                lifecycle_status=lifecycle,
                available=(activation_state == "Available"),
            )
        )
    return sorted(
        options,
        key=lambda item: (
            not item.available,
            item.display_name.casefold(),
            item.id.casefold(),
        ),
    )


def _supports_agent(model: Mapping[str, Any]) -> bool:
    domain = _text(model, "domain").upper()
    if domain not in _SUPPORTED_DOMAINS:
        return False
    raw_task_types = model.get("task_type")
    if not isinstance(raw_task_types, list) or not raw_task_types:
        # A few third-party LLM entries omit task_type while remaining compatible
        # with ModelArk's OpenAI-compatible text API.
        return domain == "LLM"
    task_types = {str(value).strip() for value in raw_task_types}
    return bool(task_types & _SUPPORTED_TASK_TYPES)


def _text(item: Mapping[str, Any], key: str) -> str:
    return str(item.get(key) or "").strip()


__all__ = ["ModelApiKeyService", "ModelCatalogService", "join_model_options"]
