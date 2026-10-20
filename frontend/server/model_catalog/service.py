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

"""Catalog joining rules and short-lived cache."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from typing import Any

from veadk.utils.logger import get_logger

from .client import ModelApiKeyClient, ModelCatalogClient
from .models import (
    ModelApiKeyModelPermission,
    ModelApiKeyOption,
    ModelApiKeysResponse,
    ModelOption,
    ModelOptionsResponse,
    ModelPermissionState,
)
from .protocol import ModelCatalogError, Provider

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
        self._pending_options: dict[
            tuple[str | None, bool], asyncio.Task[ModelOptionsResponse]
        ] = {}

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
        request_key = (api_key_id, force_refresh)
        pending = self._pending_options.get(request_key)
        if pending is None:
            pending = asyncio.create_task(
                self._list_options(api_key_id=api_key_id, force_refresh=force_refresh)
            )
            self._pending_options[request_key] = pending

            def finished(task: asyncio.Task[ModelOptionsResponse]) -> None:
                if self._pending_options.get(request_key) is task:
                    del self._pending_options[request_key]

            pending.add_done_callback(finished)
        # One browser cancelling its request must not cancel other callers.
        return await asyncio.shield(pending)

    async def _list_options(
        self,
        *,
        api_key_id: str | None = None,
        force_refresh: bool = False,
    ) -> ModelOptionsResponse:
        selected_key_id = api_key_id
        selected_key: ModelApiKeyOption | None = None
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
            selected_key = next(
                key for key in key_catalog.keys if key.id == selected_key_id
            )
        cache_key = selected_key_id or "__legacy_default__"
        now = self._clock()
        cached = self._cached.get(cache_key)
        if not force_refresh and cached is not None and now < cached[1]:
            return apply_api_key_permissions(cached[0], selected_key)
        async with self._lock:
            now = self._clock()
            cached = self._cached.get(cache_key)
            if not force_refresh and cached is not None and now < cached[1]:
                return apply_api_key_permissions(cached[0], selected_key)
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
                    model_permission_catalog=build_model_permission_catalog(
                        activations, models
                    ),
                )
            except ModelCatalogError:
                if cached is None or force_refresh:
                    raise
                logger.warning(
                    "Refreshing the Studio model catalog failed; serving cached data."
                )
                self._cached[cache_key] = (
                    cached[0],
                    self._clock() + self._ttl_seconds,
                )
                return apply_api_key_permissions(cached[0], selected_key)
            self._cached[cache_key] = (
                refreshed,
                self._clock() + self._ttl_seconds,
            )
            return apply_api_key_permissions(refreshed, selected_key)


class ModelApiKeyService:
    """Read key metadata live; cache raw values only on the server."""

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
        self._raw_keys: dict[str, tuple[str, float]] = {}
        self._pending_keys: asyncio.Task[ModelApiKeysResponse] | None = None

    async def list_keys(self, *, force_refresh: bool = False) -> ModelApiKeysResponse:
        """Share overlapping reads only; subsequent reads still fetch live data."""
        pending = self._pending_keys
        if pending is None:
            pending = asyncio.create_task(self._read_keys())
            self._pending_keys = pending

            def finished(task: asyncio.Task[ModelApiKeysResponse]) -> None:
                if self._pending_keys is task:
                    self._pending_keys = None

            pending.add_done_callback(finished)
        return await asyncio.shield(pending)

    async def _read_keys(self) -> ModelApiKeysResponse:
        raw_items = await self._client.list_keys()
        keys = [ModelApiKeyOption(**item) for item in raw_items]
        selectable = [item for item in keys if item.status != "Restricted"]
        default_key_id = next(
            (
                item.id
                for item in selectable
                if self._default_key_name and item.name == self._default_key_name
            ),
            selectable[0].id if selectable else None,
        )
        return ModelApiKeysResponse(
            provider=self._provider,
            keys=keys,
            default_key_id=default_key_id,
        )

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
        if any(
            item.id == key_id and item.status == "Restricted" for item in catalog.keys
        ):
            raise ModelCatalogError(
                "所选 API Key 已禁用，请在控制台启用或选择其他 API Key",
                status_code=400,
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


def apply_api_key_permissions(
    response: ModelOptionsResponse,
    key: ModelApiKeyOption | None,
) -> ModelOptionsResponse:
    if key is None or key.allow_all is None:
        return response
    permissions = None
    rule = key.model_access
    if not key.allow_all and rule and rule.effect == "allow" and not rule.all_models:
        permissions = [
            response.model_permission_catalog.get(
                name, ModelApiKeyModelPermission(name=name, state="Unknown")
            )
            for name in dict.fromkeys(rule.model_ids)
        ]
    models = []
    for model in response.models:
        allowed = key.allow_all
        if not allowed and key.model_access is not None:
            rule = key.model_access
            matches = rule.all_models or bool(
                {model.name, model.id}.intersection(rule.model_ids)
            )
            allowed = matches if rule.effect == "allow" else not matches
        models.append(
            model.model_copy(
                update={
                    "api_key_allowed": allowed,
                    "available": model.available and allowed,
                }
            )
        )
    return response.model_copy(
        update={
            "api_key_model_permissions": permissions,
            "models": sorted(
                models,
                key=lambda model: (
                    model.api_key_allowed is False,
                    not model.available,
                    model.display_name.casefold(),
                    model.id,
                ),
            ),
        }
    )


def build_model_permission_catalog(
    activations: list[dict[str, Any]], models: list[dict[str, Any]]
) -> dict[str, ModelApiKeyModelPermission]:
    """Explain every explicitly granted model, including non-agent and retired models."""
    activated = {
        _text(item, "FoundationModelName")
        for item in activations
        if _text(item, "State") == "Available"
    }
    catalog: dict[str, ModelApiKeyModelPermission] = {}
    priority = {
        "Available": 0,
        "NotActivated": 1,
        "VideoGeneration": 2,
        "Unsupported": 3,
        "Shutdown": 4,
    }
    for model in models:
        name = _text(model, "name")
        state: ModelPermissionState
        if _text(model, "status") == "Shutdown":
            state = "Shutdown"
        elif _text(model, "domain") == "VideoGeneration":
            state = "VideoGeneration"
        elif not _supports_agent(model):
            state = "Unsupported"
        else:
            state = "Available" if name in activated else "NotActivated"
        for identifier in {name, _text(model, "id")} - {""}:
            current = catalog.get(identifier)
            if current is None or priority[state] < priority[current.state]:
                catalog[identifier] = ModelApiKeyModelPermission(
                    name=identifier, state=state, model_id=_text(model, "id") or None
                )
    return catalog


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
