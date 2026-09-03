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

"""Feishu's official PersonalAgent app-registration device flow."""

from __future__ import annotations

import base64
import io
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
import qrcode

from .service import (
    FeishuBotSetupError,
    ProviderResult,
    ProviderSession,
)

_REGISTRATION_PATH = "/oauth/v1/app/registration"
_ACCOUNTS_ENDPOINTS = {
    "feishu": f"https://accounts.feishu.cn{_REGISTRATION_PATH}",
    "lark": f"https://accounts.larksuite.com{_REGISTRATION_PATH}",
}
_VERIFICATION_HOSTS = {"open.feishu.cn", "open.larksuite.com"}
_DEFAULT_EXPIRES_IN_SECONDS = 600
_DEFAULT_POLL_INTERVAL_SECONDS = 5
_MAX_POLL_INTERVAL_SECONDS = 60


@dataclass
class _RegistrationState:
    device_code: str
    expires_at: float
    poll_interval: int
    next_poll_at: float
    brand: str = "feishu"
    brand_switched: bool = False
    terminal_result: ProviderResult | None = None


class FeishuAppRegistrationProvider:
    """Create PersonalAgent apps through Feishu's public registration flow."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30),
            follow_redirects=True,
        )
        self._states: dict[str, _RegistrationState] = {}
        self._lock = threading.Lock()

    def create(self, *, agent_name: str) -> ProviderSession:
        del agent_name  # The registration protocol does not accept an app name.
        data = self._post(
            _ACCOUNTS_ENDPOINTS["feishu"],
            {
                "action": "begin",
                "archetype": "PersonalAgent",
                "auth_method": "client_secret",
                "request_user_info": "open_id tenant_brand",
            },
            operation="创建飞书授权会话",
        )
        self._raise_begin_error(data)

        device_code = self._string(data, "device_code")
        user_code = self._string(data, "user_code")
        if not device_code or not user_code:
            raise FeishuBotSetupError("飞书授权服务返回的数据不完整，请稍后重试。")

        expires_in = self._positive_int(
            data.get("expires_in", data.get("expire_in")),
            _DEFAULT_EXPIRES_IN_SECONDS,
        )
        poll_interval = self._positive_int(
            data.get("interval"), _DEFAULT_POLL_INTERVAL_SECONDS
        )
        verification_url = self._verification_url(data, user_code)
        expires_at = time.time() + expires_in
        state = _RegistrationState(
            device_code=device_code,
            expires_at=expires_at,
            poll_interval=poll_interval,
            next_poll_at=0,
        )
        with self._lock:
            self._discard_expired_locked()
            self._states[device_code] = state

        return ProviderSession(
            provider_id=device_code,
            qr_code_data_url=self._qr_code_data_url(verification_url),
            expires_at=expires_at,
        )

    def poll(self, provider_id: str) -> ProviderResult:
        # Serialize polls so two browser requests cannot consume the same
        # one-time success response or bypass the provider's polling interval.
        with self._lock:
            state = self._states.get(provider_id)
            if state is None:
                return ProviderResult("expired", message="二维码已失效，请重新生成。")
            if state.terminal_result is not None:
                return state.terminal_result
            if time.time() >= state.expires_at:
                result = ProviderResult("expired", message="二维码已失效，请重新生成。")
                state.terminal_result = result
                return result
            if time.monotonic() < state.next_poll_at:
                return ProviderResult("waiting")

            state.next_poll_at = time.monotonic() + state.poll_interval
            try:
                data = self._post(
                    _ACCOUNTS_ENDPOINTS[state.brand],
                    {"action": "poll", "device_code": state.device_code},
                    operation="查询飞书授权状态",
                    accept_error_response=True,
                )
            except FeishuBotSetupError:
                state.poll_interval = min(
                    state.poll_interval + 1, _MAX_POLL_INTERVAL_SECONDS
                )
                state.next_poll_at = time.monotonic() + state.poll_interval
                return ProviderResult("waiting")

            tenant_brand = self._tenant_brand(data)
            if (
                not state.brand_switched
                and tenant_brand in _ACCOUNTS_ENDPOINTS
                and tenant_brand != state.brand
            ):
                state.brand = tenant_brand
                state.brand_switched = True
                state.next_poll_at = 0
                return ProviderResult("waiting")

            result = self._poll_result(data, state)
            if result.status != "waiting":
                state.terminal_result = result
            return result

    def cancel(self, provider_id: str) -> None:
        with self._lock:
            self._states.pop(provider_id, None)

    def _poll_result(
        self, data: dict[str, Any], state: _RegistrationState
    ) -> ProviderResult:
        error = self._string(data, "error")
        if error == "authorization_pending":
            return ProviderResult("waiting")
        if error == "slow_down":
            state.poll_interval = min(
                state.poll_interval + 5, _MAX_POLL_INTERVAL_SECONDS
            )
            state.next_poll_at = time.monotonic() + state.poll_interval
            return ProviderResult("waiting")
        if error == "access_denied":
            return ProviderResult("failed", message="你已取消飞书授权。")
        if error in {"expired_token", "invalid_grant"}:
            return ProviderResult("expired", message="二维码已失效，请重新生成。")
        if error:
            description = self._string(data, "error_description")
            return ProviderResult(
                "failed",
                message=description or "飞书授权失败，请重新生成二维码。",
            )

        app_id = self._string(data, "client_id")
        app_secret = self._string(data, "client_secret")
        if not app_id or not app_secret:
            return ProviderResult("waiting")

        tenant_brand = self._tenant_brand(data)
        if tenant_brand and tenant_brand != state.brand:
            return ProviderResult("failed", message="飞书授权返回的平台信息不一致。")
        return ProviderResult("success", app_id=app_id, app_secret=app_secret)

    def _post(
        self,
        endpoint: str,
        form: dict[str, str],
        *,
        operation: str,
        accept_error_response: bool = False,
    ) -> dict[str, Any]:
        try:
            response = self._client.post(
                endpoint,
                data=form,
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as error:
            raise FeishuBotSetupError(f"{operation}失败，请检查网络后重试。") from error

        try:
            data = response.json()
        except ValueError as error:
            raise FeishuBotSetupError(f"{operation}返回了无法解析的响应。") from error
        if not isinstance(data, dict):
            raise FeishuBotSetupError(f"{operation}返回了无法解析的响应。")
        if response.is_error and not accept_error_response:
            description = self._string(data, "error_description")
            raise FeishuBotSetupError(description or f"{operation}失败。")
        return data

    @classmethod
    def _raise_begin_error(cls, data: dict[str, Any]) -> None:
        error = cls._string(data, "error")
        if not error:
            return
        description = cls._string(data, "error_description")
        raise FeishuBotSetupError(description or "创建飞书授权会话失败。")

    @classmethod
    def _verification_url(cls, data: dict[str, Any], user_code: str) -> str:
        raw_url = cls._string(data, "verification_uri_complete")
        if not raw_url:
            base_url = cls._string(data, "verification_uri")
            raw_url = base_url or "https://open.feishu.cn/page/launcher"

        parsed = urlparse(raw_url)
        if parsed.scheme != "https" or parsed.hostname not in _VERIFICATION_HOSTS:
            raise FeishuBotSetupError("飞书授权服务返回了无效的二维码地址。")
        query = parse_qs(parsed.query, keep_blank_values=True)
        query["user_code"] = [user_code]
        query["from"] = ["studio"]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    @staticmethod
    def _qr_code_data_url(value: str) -> str:
        image = qrcode.make(value)
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    @staticmethod
    def _positive_int(value: object, default: int) -> int:
        if isinstance(value, bool):
            return default
        try:
            parsed = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    @staticmethod
    def _string(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        return value if isinstance(value, str) else ""

    @classmethod
    def _tenant_brand(cls, data: dict[str, Any]) -> str:
        user_info = data.get("user_info")
        if not isinstance(user_info, dict):
            return ""
        return cls._string(user_info, "tenant_brand").strip().lower()

    def _discard_expired_locked(self) -> None:
        now = time.time()
        expired = [
            provider_id
            for provider_id, state in self._states.items()
            if state.expires_at <= now
        ]
        for provider_id in expired:
            self._states.pop(provider_id, None)
