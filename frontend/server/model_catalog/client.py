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

"""Provider-aware clients for ModelArk catalog inputs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from frontend.server.video.client import ArkHttpClient, ArkServiceError
from veadk.utils.volcengine_sign import volcengine_signed_request
from veadk.utils.logger import get_logger

from .errors import cloud_payload, cloud_request_error, cloud_response_error
from .protocol import (
    CloudCredentials,
    CredentialResolver,
    ModelCatalogError,
    Provider,
    SignedRequest,
)

_PAGE_SIZE = 100
_MAX_PAGES = 100
logger = get_logger(__name__)


@dataclass(frozen=True)
class ModelCatalogProviderConfig:
    provider: Provider
    region: str
    openapi_host: str
    api_base: str


PROVIDER_CONFIGS: dict[Provider, ModelCatalogProviderConfig] = {
    "volcengine": ModelCatalogProviderConfig(
        provider="volcengine",
        region="cn-beijing",
        openapi_host="open.volcengineapi.com",
        api_base="https://ark.cn-beijing.volces.com/api/v3",
    ),
    "byteplus": ModelCatalogProviderConfig(
        provider="byteplus",
        region="ap-southeast-1",
        openapi_host="open.byteplusapi.com",
        api_base="https://ark.ap-southeast.bytepluses.com/api/v3",
    ),
}


class ModelCatalogClient:
    """Fetch activation metadata and exact data-plane model versions."""

    def __init__(
        self,
        *,
        config: ModelCatalogProviderConfig,
        resolve_credentials: CredentialResolver,
        ark_http_client: ArkHttpClient,
        signed_request: SignedRequest = volcengine_signed_request,
    ) -> None:
        self._config = config
        self._resolve_credentials = resolve_credentials
        self._ark = ark_http_client
        self._signed_request = signed_request

    async def list_activations(self) -> list[dict[str, Any]]:
        try:
            credentials = self._resolve_credentials()
        except Exception as error:
            raise ModelCatalogError(
                "云账号凭据不可用，请检查 Studio 的云账号配置后重试。",
                status_code=503,
            ) from error

        items: list[dict[str, Any]] = []
        for page_number in range(1, _MAX_PAGES + 1):
            payload = await self._activation_page(
                credentials=credentials,
                page_number=page_number,
            )
            result = payload.get("Result")
            if not isinstance(result, dict):
                raise ModelCatalogError("模型开通状态服务返回了无法解析的结果。")
            page_items = result.get("Items") or []
            if not isinstance(page_items, list) or not all(
                isinstance(item, dict) for item in page_items
            ):
                raise ModelCatalogError("模型开通状态服务返回了无法解析的结果。")
            items.extend(page_items)
            total_count = _safe_int(result.get("TotalCount"), len(items))
            if not page_items or len(items) >= total_count:
                return items
        raise ModelCatalogError("模型开通状态列表分页异常，请稍后重试。")

    async def list_models(self, *, api_key: str | None = None) -> list[dict[str, Any]]:
        try:
            if api_key is None:
                response = await self._ark.request("GET", "/models")
            else:
                response = await self._ark.http_client.request(
                    "GET",
                    f"{self._config.api_base}/models",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                if response.status_code >= 400:
                    raise cloud_response_error(
                        response, action="ListModels", secrets=(api_key,)
                    )
        except ModelCatalogError:
            raise
        except ArkServiceError as error:
            raise cloud_request_error(
                error, action="ListModels", secrets=(api_key,)
            ) from error
        except Exception as error:
            raise cloud_request_error(
                error, action="ListModels", secrets=(api_key,)
            ) from error
        payload = cloud_payload(response, action="ListModels", secrets=(api_key,))
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or not all(
            isinstance(item, dict) for item in data
        ):
            raise ModelCatalogError("模型服务返回了无法解析的结果，请稍后重试。")
        return data

    async def _activation_page(
        self,
        *,
        credentials: CloudCredentials,
        page_number: int,
    ) -> dict[str, Any]:
        logger.info(
            f"Studio cloud request action=ListModelActivations provider={self._config.provider} page={page_number}"
        )
        access_key, secret_key, session_token = credentials
        try:
            payload = await asyncio.to_thread(
                self._signed_request,
                request_body={
                    "PageNumber": page_number,
                    "PageSize": _PAGE_SIZE,
                    "WithPrice": False,
                    "WithFreeUsage": False,
                    "Filter": {"FoundationModelDomain": "LLM"},
                },
                ak=access_key,
                sk=secret_key,
                service="ark",
                region=self._config.region,
                host=self._config.openapi_host,
                path="/",
                header={"X-Security-Token": session_token or ""},
                query={
                    "Action": "ListModelActivations",
                    "Version": "2024-01-01",
                },
                response_type="response",
            )
        except Exception as error:
            raise cloud_request_error(
                error, action="ListModelActivations", secrets=credentials
            ) from error
        payload = cloud_payload(
            payload, action="ListModelActivations", secrets=credentials
        )
        if not isinstance(payload, dict):
            raise ModelCatalogError("模型开通状态服务返回了无法解析的结果。")
        return payload


class ModelApiKeyClient:
    """List Ark API keys and resolve one raw value without exposing it publicly."""

    def __init__(
        self,
        *,
        config: ModelCatalogProviderConfig,
        resolve_credentials: CredentialResolver,
        signed_request: SignedRequest = volcengine_signed_request,
    ) -> None:
        self._config = config
        self._resolve_credentials = resolve_credentials
        self._signed_request = signed_request

    async def list_keys(self) -> list[dict[str, Any]]:
        credentials = self._credentials()
        keys: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for page_number in range(1, _MAX_PAGES + 1):
            payload = await self._request(
                credentials=credentials,
                action="ListApiKeys",
                request_body={
                    "ProjectName": "default",
                    "PageNumber": page_number,
                    "PageSize": _PAGE_SIZE,
                },
            )
            result = payload.get("Result")
            if not isinstance(result, dict):
                raise ModelCatalogError("API Key 服务返回了无法解析的结果。")
            items = result.get("Items") or []
            if not isinstance(items, list) or not all(
                isinstance(item, dict) for item in items
            ):
                raise ModelCatalogError("API Key 服务返回了无法解析的结果。")
            new_count = 0
            for item in items:
                key_id = str(item.get("Id") or "").strip()
                name = str(item.get("Name") or "").strip()
                if key_id and key_id not in seen_ids:
                    seen_ids.add(key_id)
                    access_control = item.get("AccessControlInfo")
                    allow_all = (
                        access_control.get("AllowAll")
                        if isinstance(access_control, dict)
                        else None
                    )
                    access_rules = (
                        access_control.get("AccessRules")
                        if isinstance(access_control, dict)
                        else None
                    )
                    model_rule = (
                        access_rules.get("model")
                        if isinstance(access_rules, dict)
                        else None
                    )
                    model_access = None
                    if (
                        isinstance(model_rule, dict)
                        and model_rule.get("Effect") in {"allow", "deny"}
                        and isinstance(model_rule.get("EffectToAll"), bool)
                    ):
                        model_access = {
                            "effect": model_rule["Effect"],
                            "all_models": model_rule["EffectToAll"],
                            "model_ids": [
                                value
                                for value in (model_rule.get("Ids") or [])
                                if isinstance(value, str)
                            ],
                        }
                    keys.append(
                        {
                            "id": key_id,
                            "name": name,
                            "status": str(item.get("Status") or "").strip() or None,
                            "allow_all": allow_all
                            if isinstance(allow_all, bool)
                            else None,
                            "model_access": model_access,
                        }
                    )
                    new_count += 1
            total_count = _safe_int(result.get("TotalCount"), -1)
            if (total_count >= 0 and len(keys) >= total_count) or (
                not items and total_count < 0
            ):
                return sorted(keys, key=lambda key: (key["name"].casefold(), key["id"]))
            if new_count == 0:
                raise ModelCatalogError("API Key 列表分页异常，请稍后重试。")
        raise ModelCatalogError("API Key 列表分页异常，请稍后重试。")

    async def get_raw_key(self, key_id: str) -> str:
        payload = await self._request(
            credentials=self._credentials(),
            action="GetRawApiKey",
            request_body={
                "Id": _control_plane_key_id(key_id),
                "ProjectName": "default",
            },
        )
        result = payload.get("Result")
        api_key = result.get("ApiKey") if isinstance(result, dict) else None
        if not isinstance(api_key, str) or not api_key.strip():
            raise ModelCatalogError(
                "无法读取所选 API Key，请确认它仍然存在后重试。",
                status_code=404,
            )
        return api_key.strip()

    def _credentials(self) -> CloudCredentials:
        try:
            return self._resolve_credentials()
        except Exception as error:
            raise ModelCatalogError(
                "云账号凭据不可用，请检查 Studio 的云账号配置后重试。",
                status_code=503,
            ) from error

    async def _request(
        self,
        *,
        credentials: CloudCredentials,
        action: str,
        request_body: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        access_key, secret_key, session_token = credentials
        try:
            payload = await asyncio.to_thread(
                self._signed_request,
                request_body=request_body,
                ak=access_key,
                sk=secret_key,
                service="ark",
                region=self._config.region,
                host=self._config.openapi_host,
                path="/",
                header={"X-Security-Token": session_token or ""},
                query={
                    "Action": action,
                    "Version": "2024-01-01",
                    **(query or {}),
                },
                response_type="response",
            )
        except Exception as error:
            raise cloud_request_error(
                error, action=action, secrets=credentials
            ) from error
        payload = cloud_payload(payload, action=action, secrets=credentials)
        if not isinstance(payload, dict):
            raise ModelCatalogError("API Key 服务返回了无法解析的结果。")
        return payload


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _control_plane_key_id(value: str) -> int | str:
    """Preserve Ark's numeric ID type while accepting legacy string IDs."""
    return int(value) if value.isdigit() else value


__all__ = [
    "PROVIDER_CONFIGS",
    "CredentialResolver",
    "ModelApiKeyClient",
    "ModelCatalogClient",
    "ModelCatalogError",
    "ModelCatalogProviderConfig",
    "Provider",
]
