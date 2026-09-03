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

import time

import pytest

from frontend.server.feishu_bot_setup.service import (
    FeishuBotSetupNotFound,
    FeishuBotSetupProvider,
    FeishuBotSetupService,
    FeishuBotSetupUnavailable,
    ProviderResult,
    ProviderSession,
    create_feishu_bot_setup_service,
)


class WaitingProvider(FeishuBotSetupProvider):
    def create(self, *, agent_name: str) -> ProviderSession:
        return ProviderSession(
            provider_id="provider-session",
            qr_code_data_url="data:image/png;base64,cXItY29kZQ==",
            expires_at=time.time() + 600,
        )

    def poll(self, provider_id: str) -> ProviderResult:
        return ProviderResult("waiting")

    def cancel(self, provider_id: str) -> None:
        return None


def test_provider_session_never_returns_credentials_before_success() -> None:
    service = FeishuBotSetupService(WaitingProvider())

    created = service.create(owner="alice", agent_name="Support Agent")
    pending = service.get(owner="alice", session_id=str(created["id"]))

    assert created["status"] == "waiting"
    assert str(created["qrCodeDataUrl"]).startswith("data:image/png;base64,")
    assert pending["status"] == "waiting"
    assert "credentials" not in pending


def test_session_is_scoped_to_the_current_studio_user() -> None:
    service = FeishuBotSetupService(WaitingProvider())
    created = service.create(owner="alice", agent_name="Support Agent")

    with pytest.raises(FeishuBotSetupNotFound):
        service.get(owner="bob", session_id=str(created["id"]))


def test_automatic_setup_requires_a_configured_provider() -> None:
    service = create_feishu_bot_setup_service()

    with pytest.raises(FeishuBotSetupUnavailable):
        service.create(owner="alice", agent_name="Support Agent")
