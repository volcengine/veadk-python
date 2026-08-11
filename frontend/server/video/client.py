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

"""Provider-aware ModelArk clients used by Studio video creation."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from typing import Any, Literal

import httpx

from veadk.auth.veauth.ark_veauth import get_ark_token
from veadk.utils.logger import get_logger

from .models import VideoProviderConfig

logger = get_logger(__name__)

_INVALID_PARAMETER_MESSAGES = {
    "duration": "视频时长不受当前模型支持，请选择 4 至 30 秒。",
    "ratio": "当前模型不支持所选视频画幅。",
    "resolution": "当前模型不支持所选视频清晰度。",
    "output_format": "当前任务不支持所选视频输出格式。",
    "content": "视频提示词或参考素材参数无效，请检查后重试。",
    "generate_audio": "当前任务不支持所选音频生成参数。",
    "model": "当前视频生成模型参数无效，请联系管理员检查配置。",
}

CredentialResolver = Callable[[], tuple[str, str, str | None]]


class ArkServiceError(RuntimeError):
    """A sanitized upstream failure safe to expose through Studio."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class ArkTokenCache:
    """Cache an IAM-derived Ark API key without exposing it to the browser."""

    def __init__(
        self,
        *,
        provider: str,
        region: str,
        resolve_credentials: CredentialResolver,
        api_key_name: str | None = None,
        ttl_seconds: float = 900,
        token_loader: Callable[..., str] = get_ark_token,
    ) -> None:
        self._provider = provider
        self._region = region
        self._resolve_credentials = resolve_credentials
        self._api_key_name = api_key_name
        self._ttl_seconds = ttl_seconds
        self._token_loader = token_loader
        self._value = ""
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, *, force_refresh: bool = False) -> str:
        now = time.monotonic()
        if not force_refresh and self._value and now < self._expires_at:
            return self._value
        async with self._lock:
            now = time.monotonic()
            if not force_refresh and self._value and now < self._expires_at:
                return self._value
            access_key, secret_key, session_token = self._resolve_credentials()
            token = await asyncio.to_thread(
                self._token_loader,
                self._region,
                self._api_key_name,
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token,
            )
            if not token:
                raise ArkServiceError("模型服务凭据不可用，请联系管理员检查配置。")
            self._value = token
            self._expires_at = time.monotonic() + self._ttl_seconds
            return token


class ArkTokenProvider:
    """Prefer an explicit model token, falling back to the shared IAM cache."""

    def __init__(self, cache: ArkTokenCache, explicit_token: str = "") -> None:
        self._cache = cache
        self._explicit_token = explicit_token.strip()

    async def get(self, *, force_refresh: bool = False) -> str:
        if self._explicit_token:
            return self._explicit_token
        return await self._cache.get(force_refresh=force_refresh)


class ArkHttpClient:
    def __init__(
        self,
        *,
        provider: Literal["volcengine", "byteplus"],
        api_base: str,
        token_provider: ArkTokenProvider,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._provider = provider
        self._api_base = api_base.rstrip("/")
        self._token_provider = token_provider
        self.http_client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            follow_redirects=True,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        response: httpx.Response | None = None
        for attempt in range(2):
            token = await self._token_provider.get(force_refresh=attempt == 1)
            try:
                response = await self.http_client.request(
                    method,
                    f"{self._api_base}/{path.lstrip('/')}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=json,
                )
            except httpx.RequestError as error:
                raise ArkServiceError("无法连接模型服务，请稍后重试。") from error
            if response.status_code != 401 or attempt == 1:
                break
        assert response is not None
        if response.status_code >= 400:
            upstream_code = ""
            upstream_message = ""
            try:
                payload = response.json()
                error_payload = (
                    payload.get("error", payload) if isinstance(payload, dict) else {}
                )
                if isinstance(error_payload, dict):
                    upstream_code = str(error_payload.get("code") or "")
                    upstream_message = str(error_payload.get("message") or "")
            except ValueError:
                pass
            logger.warning(
                "Model service request failed: status=%s code=%s message=%s",
                response.status_code,
                upstream_code[:120],
                upstream_message[:300],
            )
            if response.status_code in {401, 403}:
                raise ArkServiceError(
                    "模型服务鉴权失败，请联系管理员检查模型凭据。",
                    status_code=502,
                )
            if upstream_code == "ModelNotOpen":
                model = str((json or {}).get("model") or "").strip()
                model_name = f"{model} 模型" if model else "所选模型"
                console_name = (
                    "方舟控制台"
                    if self._provider == "volcengine"
                    else "ModelArk 控制台"
                )
                raise ArkServiceError(
                    f"当前账号尚未开通 {model_name}，请先在{console_name}开通模型服务。",
                    status_code=502,
                )
            if upstream_code == "InvalidParameter":
                raise ArkServiceError(
                    _invalid_parameter_message(upstream_message),
                    status_code=400,
                )
            raise ArkServiceError(
                f"模型服务请求失败（HTTP {response.status_code}）。",
                status_code=502,
            )
        return response


def _invalid_parameter_message(upstream_message: str) -> str:
    """Return parameter-specific guidance without exposing upstream values."""

    message = upstream_message.lower()
    for parameter, user_message in _INVALID_PARAMETER_MESSAGES.items():
        if f"parameter `{parameter}`" in message or f"parameter {parameter}" in message:
            return user_message
    return "视频生成参数无效，请检查当前任务配置。"


class ArkPromptClient:
    def __init__(
        self,
        *,
        config: VideoProviderConfig,
        transport: ArkHttpClient,
    ) -> None:
        self._config = config
        self._transport = transport

    async def enhance(self, messages: Sequence[dict[str, str]]) -> str:
        response = await self._transport.request(
            "POST",
            "/responses",
            json={
                "model": self._config.enhancer_model,
                "input": list(messages),
                "thinking": {"type": "disabled"},
            },
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise ArkServiceError("提示词增强服务返回了无法解析的结果。") from error
        content = self._response_text(payload)
        if not content:
            raise ArkServiceError("提示词增强服务没有返回有效内容。")
        return content

    @staticmethod
    def _response_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        fragments: list[str] = []
        output = payload.get("output")
        if not isinstance(output, list):
            return ""
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") != "output_text":
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    fragments.append(text.strip())
        return "\n".join(fragments)


class ArkVideoClient:
    def __init__(
        self,
        *,
        config: VideoProviderConfig,
        transport: ArkHttpClient,
    ) -> None:
        self._config = config
        self._transport = transport

    async def create_task(self, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._transport.request(
            "POST", "/contents/generations/tasks", json=body
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise ArkServiceError("视频生成服务返回了无法解析的响应。") from error
        if not isinstance(payload, dict) or not str(payload.get("id") or ""):
            raise ArkServiceError("视频生成服务没有返回任务 ID。")
        return payload

    async def get_task(self, task_id: str) -> dict[str, Any]:
        response = await self._transport.request(
            "GET", f"/contents/generations/tasks/{task_id}"
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise ArkServiceError("视频生成服务返回了无法解析的任务状态。") from error
        if not isinstance(payload, dict):
            raise ArkServiceError("视频生成服务返回了无法解析的任务状态。")
        return payload

    async def open_download(self, url: str) -> httpx.Response:
        if not url.startswith("https://"):
            raise ArkServiceError("视频下载地址无效。")
        request = self._transport.http_client.build_request("GET", url)
        try:
            response = await self._transport.http_client.send(request, stream=True)
        except httpx.RequestError as error:
            raise ArkServiceError("无法连接视频下载服务，请稍后重试。") from error
        if response.status_code >= 400:
            await response.aclose()
            raise ArkServiceError(
                f"视频下载失败（HTTP {response.status_code}）。",
                status_code=502,
            )
        return response
