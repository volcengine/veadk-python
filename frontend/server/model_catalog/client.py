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

"""Provider-aware clients for ModelArk catalog inputs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from frontend.server.video.client import ArkHttpClient, ArkServiceError
from veadk.utils.volcengine_sign import volcengine_signed_request

CloudCredentials = tuple[str, str, str | None]
CredentialResolver = Callable[[], CloudCredentials]
Provider = Literal["volcengine", "byteplus"]

_PAGE_SIZE = 100
_MAX_PAGES = 100


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


class ModelCatalogError(RuntimeError):
    """A sanitized, retryable failure safe to return to a Studio client."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


SignedRequest = Callable[..., Any]


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
                    raise ModelCatalogError(
                        "模型服务鉴权失败，请检查所选 API Key 后重试。",
                        status_code=502,
                    )
        except ModelCatalogError:
            raise
        except ArkServiceError as error:
            raise ModelCatalogError(
                str(error),
                status_code=error.status_code,
            ) from error
        except Exception as error:
            raise ModelCatalogError(
                "模型服务凭据不可用，请检查 Studio 的模型凭据后重试。",
                status_code=503,
            ) from error
        try:
            payload = response.json()
        except ValueError as error:
            raise ModelCatalogError(
                "模型服务返回了无法解析的结果，请稍后重试。"
            ) from error
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
            )
        except Exception as error:
            raise ModelCatalogError(
                "无法获取模型开通状态，请检查云账号权限后重试。"
            ) from error
        if not isinstance(payload, dict):
            raise ModelCatalogError("模型开通状态服务返回了无法解析的结果。")
        metadata = payload.get("ResponseMetadata")
        upstream_error = metadata.get("Error") if isinstance(metadata, dict) else None
        if upstream_error:
            raise ModelCatalogError(
                "获取模型开通状态失败，请检查 ark:ListModelActivations 权限后重试。"
            )
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

    async def list_keys(self) -> list[dict[str, str]]:
        credentials = self._credentials()
        keys: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        scanned = 0
        for page_number in range(1, _MAX_PAGES + 1):
            payload = await self._request(
                credentials=credentials,
                action="ListApiKeys",
                request_body={
                    "ProjectName": "default",
                    "Filter": {"AllowAll": True},
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
                if key_id and name and key_id not in seen_ids:
                    seen_ids.add(key_id)
                    keys.append({"id": key_id, "name": name})
                    new_count += 1
            scanned += len(items)
            total_count = _safe_int(result.get("TotalCount"), len(keys))
            if not items or scanned >= total_count:
                return keys
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
            )
        except Exception as error:
            raise ModelCatalogError(
                "无法访问 API Key 服务，请检查云账号权限后重试。"
            ) from error
        if not isinstance(payload, dict):
            raise ModelCatalogError("API Key 服务返回了无法解析的结果。")
        metadata = payload.get("ResponseMetadata")
        upstream_error = metadata.get("Error") if isinstance(metadata, dict) else None
        if upstream_error:
            permission = (
                "ark:ListApiKeys" if action == "ListApiKeys" else "ark:GetRawApiKey"
            )
            raise ModelCatalogError(
                f"访问 API Key 服务失败，请检查 {permission} 权限后重试。"
            )
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
