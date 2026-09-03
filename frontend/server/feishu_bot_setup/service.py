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

"""Provider-independent lifecycle for creating a Feishu bot by QR authorization."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4


class FeishuBotSetupError(RuntimeError):
    """Base error returned by the Feishu setup workflow."""


class FeishuBotSetupUnavailable(FeishuBotSetupError):
    """Raised when no production QR provider has been configured."""


class FeishuBotSetupNotFound(FeishuBotSetupError):
    """Raised when a setup session does not exist for the current user."""


@dataclass(frozen=True)
class ProviderSession:
    provider_id: str
    qr_code_data_url: str
    expires_at: float


@dataclass(frozen=True)
class ProviderResult:
    status: str
    app_id: str = ""
    app_secret: str = ""
    message: str = ""


class FeishuBotSetupProvider(Protocol):
    def create(self, *, agent_name: str) -> ProviderSession: ...

    def poll(self, provider_id: str) -> ProviderResult: ...

    def cancel(self, provider_id: str) -> None: ...


@dataclass
class _OwnedSession:
    owner: str
    provider_id: str
    qr_code_data_url: str
    expires_at: float


class FeishuBotSetupService:
    """Owns user-scoped sessions while delegating vendor calls to a provider."""

    def __init__(self, provider: FeishuBotSetupProvider | None) -> None:
        self._provider = provider
        self._sessions: dict[str, _OwnedSession] = {}
        self._lock = threading.Lock()

    def create(self, *, owner: str, agent_name: str) -> dict[str, object]:
        if self._provider is None:
            raise FeishuBotSetupUnavailable(
                "当前 Studio 尚未配置飞书自动建机器人服务，请使用手动配置。"
            )
        provider_session = self._provider.create(agent_name=agent_name)
        session_id = f"fsbot_{uuid4().hex}"
        with self._lock:
            self._sessions[session_id] = _OwnedSession(
                owner=owner,
                provider_id=provider_session.provider_id,
                qr_code_data_url=provider_session.qr_code_data_url,
                expires_at=provider_session.expires_at,
            )
        return self._payload(
            session_id, self._sessions[session_id], ProviderResult("waiting")
        )

    def get(self, *, owner: str, session_id: str) -> dict[str, object]:
        session = self._owned(owner, session_id)
        if time.time() >= session.expires_at:
            return self._payload(
                session_id, session, ProviderResult("expired", message="二维码已失效。")
            )
        assert self._provider is not None
        return self._payload(
            session_id, session, self._provider.poll(session.provider_id)
        )

    def cancel(self, *, owner: str, session_id: str) -> dict[str, object]:
        session = self._owned(owner, session_id)
        assert self._provider is not None
        self._provider.cancel(session.provider_id)
        with self._lock:
            self._sessions.pop(session_id, None)
        return self._payload(session_id, session, ProviderResult("cancelled"))

    def _owned(self, owner: str, session_id: str) -> _OwnedSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None or session.owner != owner:
            raise FeishuBotSetupNotFound("飞书自动配置会话不存在或已结束。")
        return session

    @staticmethod
    def _payload(
        session_id: str, session: _OwnedSession, result: ProviderResult
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": session_id,
            "status": result.status,
            "expiresAt": datetime.fromtimestamp(
                session.expires_at, tz=timezone.utc
            ).isoformat(),
            "message": result.message,
        }
        if result.status == "waiting":
            payload["qrCodeDataUrl"] = session.qr_code_data_url
        if result.status == "success":
            payload["credentials"] = {
                "appId": result.app_id,
                "appSecret": result.app_secret,
            }
        return payload


def create_feishu_bot_setup_service() -> FeishuBotSetupService:
    """Create the service without inventing a vendor authorization flow."""

    return FeishuBotSetupService(None)
