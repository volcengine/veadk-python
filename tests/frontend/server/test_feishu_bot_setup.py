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
from urllib.parse import parse_qs

import httpx
import pytest

from frontend.server.feishu_bot_setup.feishu_app_registration import (
    FeishuAppRegistrationProvider,
)
from frontend.server.feishu_bot_setup.service import (
    FeishuBotSetupNotFound,
    FeishuBotSetupProvider,
    FeishuBotSetupService,
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


def test_default_service_uses_the_real_registration_provider() -> None:
    service = create_feishu_bot_setup_service()

    assert isinstance(service._provider, FeishuAppRegistrationProvider)


def _begin_response() -> dict[str, object]:
    return {
        "device_code": "device-code",
        "user_code": "ABCD-EFGH",
        "verification_uri": "https://open.feishu.cn/page/launcher",
        "verification_uri_complete": (
            "https://open.feishu.cn/page/launcher?user_code=ABCD-EFGH"
        ),
        "expires_in": 3600,
        "interval": 5,
    }


def test_registration_begin_uses_the_official_personal_agent_protocol() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://accounts.feishu.cn/oauth/v1/app/registration"
        )
        assert request.headers["content-type"].startswith(
            "application/x-www-form-urlencoded"
        )
        assert parse_qs(request.content.decode()) == {
            "action": ["begin"],
            "archetype": ["PersonalAgent"],
            "auth_method": ["client_secret"],
            "request_user_info": ["open_id tenant_brand"],
        }
        return httpx.Response(200, json=_begin_response())

    provider = FeishuAppRegistrationProvider(
        httpx.Client(transport=httpx.MockTransport(handler))
    )
    created = provider.create(agent_name="Support Agent")

    assert created.provider_id == "device-code"
    assert created.qr_code_data_url.startswith("data:image/png;base64,")
    assert created.expires_at > time.time()


def test_registration_pending_never_returns_credentials() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=_begin_response())
        assert parse_qs(request.content.decode()) == {
            "action": ["poll"],
            "device_code": ["device-code"],
        }
        return httpx.Response(400, json={"error": "authorization_pending"})

    provider = FeishuAppRegistrationProvider(
        httpx.Client(transport=httpx.MockTransport(handler))
    )
    created = provider.create(agent_name="Support Agent")

    result = provider.poll(created.provider_id)

    assert result == ProviderResult("waiting")
    assert result.app_id == ""
    assert result.app_secret == ""


def test_registration_returns_real_credentials_only_after_success() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(200, json=_begin_response())
        if request_count == 2:
            return httpx.Response(
                200,
                json={
                    "client_id": "cli_real_app_id",
                    "client_secret": "real-secret",
                    "user_info": {
                        "open_id": "ou_real_user",
                        "tenant_brand": "feishu",
                    },
                },
            )
        raise AssertionError("successful credentials must be cached")

    provider = FeishuAppRegistrationProvider(
        httpx.Client(transport=httpx.MockTransport(handler))
    )
    created = provider.create(agent_name="Support Agent")

    success = provider.poll(created.provider_id)
    cached = provider.poll(created.provider_id)

    assert success == ProviderResult(
        "success", app_id="cli_real_app_id", app_secret="real-secret"
    )
    assert cached == success
    assert request_count == 2


def test_registration_switches_to_lark_when_tenant_brand_is_discovered() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if len(hosts) == 1:
            return httpx.Response(200, json=_begin_response())
        if len(hosts) == 2:
            return httpx.Response(
                400,
                json={
                    "error": "authorization_pending",
                    "user_info": {"tenant_brand": "lark"},
                },
            )
        return httpx.Response(
            200,
            json={
                "client_id": "cli_lark_app",
                "client_secret": "lark-secret",
                "user_info": {"tenant_brand": "lark"},
            },
        )

    provider = FeishuAppRegistrationProvider(
        httpx.Client(transport=httpx.MockTransport(handler))
    )
    created = provider.create(agent_name="Support Agent")

    assert provider.poll(created.provider_id).status == "waiting"
    assert provider.poll(created.provider_id).status == "success"
    assert hosts == [
        "accounts.feishu.cn",
        "accounts.feishu.cn",
        "accounts.larksuite.com",
    ]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        ("access_denied", "failed"),
        ("expired_token", "expired"),
        ("invalid_grant", "expired"),
    ],
)
def test_registration_maps_terminal_errors(error: str, status: str) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(200, json=_begin_response())
        return httpx.Response(400, json={"error": error})

    provider = FeishuAppRegistrationProvider(
        httpx.Client(transport=httpx.MockTransport(handler))
    )
    created = provider.create(agent_name="Support Agent")

    assert provider.poll(created.provider_id).status == status


def test_registration_honors_slow_down_without_an_extra_upstream_poll() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(200, json=_begin_response())
        return httpx.Response(400, json={"error": "slow_down"})

    provider = FeishuAppRegistrationProvider(
        httpx.Client(transport=httpx.MockTransport(handler))
    )
    created = provider.create(agent_name="Support Agent")

    assert provider.poll(created.provider_id).status == "waiting"
    assert provider.poll(created.provider_id).status == "waiting"
    assert request_count == 2
