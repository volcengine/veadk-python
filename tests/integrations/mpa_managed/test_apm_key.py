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

"""BytePlus APM AppKey lookup and Runtime-only secret handoff."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import requests

from veadk.integrations.mpa.managed import apm_key, service
from veadk.integrations.mpa.managed.config import load_studio_profile
from veadk.integrations.mpa.managed.diagnostics import diagnostic_scope

KEY = "test-apm-app-value"


class Cloud:
    def __init__(self):
        self.count = 0

    def _credentials(self):
        self.count += 1
        return SimpleNamespace(
            access_key_id=f"test-ak-{self.count}",
            secret_access_key="test-sk",
            session_token=f"test-sts-{self.count}",
        )


def test_signed_lookup_returns_key_without_mutating_profile(monkeypatch):
    calls = []
    monkeypatch.setattr(
        apm_key,
        "volcengine_signed_request",
        lambda **kw: calls.append(kw) or {"data": {"app_key": KEY}},
    )
    profile = load_studio_profile(provider="byteplus")
    original = profile.managed.model_dump()
    assert asyncio.run(apm_key.get_runtime_apm_key(profile, Cloud())) == KEY
    assert profile.managed.model_dump() == original
    assert KEY not in repr(profile) and KEY not in str(profile.summary())
    call = calls[0]
    assert call["host"] == "apmplus-server.ap-southeast-1.byteplusapi.com"
    assert call["region"] == "ap-southeast-1"
    assert call["service"] == "apmplus_server"
    assert call["query"] == {"Action": "GetAppKey", "Version": "2024-07-30"}
    assert call["header"] == {
        "X-Security-Token": "test-sts-1",
        "X-Apmplus-Region": "ap_southeast_1",
    }
    assert call["ak"] == "test-ak-1"
    assert call["timeout"] == (10, 30)


def test_explicit_runtime_key_skips_lookup_and_domestic_is_unchanged(monkeypatch):
    def forbidden(**kw):
        raise AssertionError("Unexpected APM lookup")

    monkeypatch.setattr(apm_key, "volcengine_signed_request", forbidden)
    profile = load_studio_profile(provider="byteplus")
    profile.managed.runtime.env[apm_key.RUNTIME_APM_KEY] = KEY
    assert asyncio.run(apm_key.get_runtime_apm_key(profile, Cloud())) == KEY
    assert (
        asyncio.run(apm_key.get_runtime_apm_key(load_studio_profile(), Cloud())) == ""
    )


@pytest.mark.parametrize(
    "response",
    [None, [], {}, {"data": []}]
    + [
        {"data": {"app_key": value}}
        for value in [None, 42, "", "***", " has-space", "x" * 4097]
    ],
)
def test_invalid_response_fails_safely_without_retry(monkeypatch, response):
    calls = []
    monkeypatch.setattr(
        apm_key, "volcengine_signed_request", lambda **kw: calls.append(kw) or response
    )
    diagnostics = []
    with (
        diagnostic_scope(diagnostics.append),
        pytest.raises(apm_key.ApmKeyError) as error,
    ):
        asyncio.run(
            apm_key.get_runtime_apm_key(
                load_studio_profile(provider="byteplus"), Cloud()
            )
        )
    assert len(calls) == 1
    assert diagnostics[-1]["category"] == "protocol_error"
    assert "app_key" not in str(error.value)


@pytest.mark.parametrize(
    "code,category,attempts",
    [
        ("AccessDenied", "permission", 1),
        ("InternalServiceTimeout", "timeout", 3),
        ("Throttling", "throttled", 3),
    ],
)
def test_provider_failure_reports_only_safe_metadata(
    monkeypatch, code, category, attempts
):
    def request(**kw):
        return {
            "ResponseMetadata": {
                "RequestId": "0123456789ABCDEF0123456789ABCDEF",
                "Error": {"Code": code, "Message": KEY},
            },
            "data": {"app_key": KEY},
        }

    monkeypatch.setattr(apm_key, "volcengine_signed_request", request)
    diagnostics = []
    cloud = Cloud()
    with (
        diagnostic_scope(diagnostics.append),
        pytest.raises(apm_key.ApmKeyError) as error,
    ):
        asyncio.run(
            apm_key.get_runtime_apm_key(load_studio_profile(provider="byteplus"), cloud)
        )
    assert cloud.count == attempts
    assert diagnostics[-1]["category"] == category
    assert diagnostics[-1]["errorCode"] == code
    assert diagnostics[-1]["requestId"] == "0123456789ABCDEF0123456789ABCDEF"
    assert KEY not in str(diagnostics) + str(error.value)


def test_http_error_retains_metadata_without_provider_text(monkeypatch):
    response = requests.Response()
    response.status_code = 403
    response._content = b'{"ResponseMetadata":{"RequestId":"0123456789ABCDEF","Error":{"Code":"AccessDenied","Message":"test-apm-app-value"}}}'

    def request(**kw):
        raise requests.HTTPError(KEY, response=response)

    monkeypatch.setattr(apm_key, "volcengine_signed_request", request)
    diagnostics = []
    with diagnostic_scope(diagnostics.append), pytest.raises(apm_key.ApmKeyError):
        asyncio.run(
            apm_key.get_runtime_apm_key(
                load_studio_profile(provider="byteplus"), Cloud()
            )
        )
    assert diagnostics[-1]["category"] == "permission"
    assert diagnostics[-1]["errorCode"] == "AccessDenied"
    assert KEY not in str(diagnostics)


def test_transient_retry_refreshes_credentials(monkeypatch):
    calls = []

    def request(**kw):
        calls.append(kw)
        if len(calls) == 1:
            raise requests.Timeout(KEY)
        return {"data": {"app_key": KEY}}

    monkeypatch.setattr(apm_key, "volcengine_signed_request", request)
    assert (
        asyncio.run(
            apm_key.get_runtime_apm_key(
                load_studio_profile(provider="byteplus"), Cloud()
            )
        )
        == KEY
    )
    assert [c["ak"] for c in calls] == ["test-ak-1", "test-ak-2"]


def test_cancellation_does_not_retry_or_continue(monkeypatch):
    async def run():
        started, release = threading.Event(), threading.Event()
        cloud = Cloud()

        def request(**kw):
            started.set()
            release.wait(2)
            return {"data": {"app_key": KEY}}

        monkeypatch.setattr(apm_key, "volcengine_signed_request", request)
        task = asyncio.create_task(
            apm_key.get_runtime_apm_key(load_studio_profile(provider="byteplus"), cloud)
        )
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cloud.count == 1

    asyncio.run(run())


def test_lookup_failure_precedes_resource_mutations(monkeypatch):
    profile = load_studio_profile(provider="byteplus")
    cloud = Cloud()
    monkeypatch.setattr(
        cloud, "account_id", AsyncMock(return_value="test-account"), raising=False
    )
    monkeypatch.setattr(service, "RuntimeCloud", lambda **kw: cloud)
    monkeypatch.setattr(service, "resolve_model_key", AsyncMock(return_value=profile))
    lookup = AsyncMock(side_effect=apm_key.ApmKeyError("APM AppKey lookup failed"))
    monkeypatch.setattr(service, "get_runtime_apm_key", lookup)
    iam, identity = AsyncMock(), AsyncMock()
    monkeypatch.setattr(service, "ensure_runtime_role", iam)
    monkeypatch.setattr(service, "ensure_workload_identity", identity)
    with pytest.raises(apm_key.ApmKeyError):
        asyncio.run(
            service.provision(
                profile,
                agent_id="mi-test",
                owner="test-owner",
                studio_runtime_owner="studio-user",
            )
        )
    lookup.assert_awaited_once_with(profile, cloud)
    iam.assert_not_awaited()
    identity.assert_not_awaited()


@pytest.mark.parametrize(
    "provider,studio_owner", [("volcengine", "studio-user"), ("byteplus", None)]
)
def test_domestic_and_cli_provision_do_not_lookup_apm(
    monkeypatch, provider, studio_owner
):
    profile = load_studio_profile(provider=provider)
    cloud = Cloud()
    monkeypatch.setattr(
        cloud, "account_id", AsyncMock(return_value="test-account"), raising=False
    )
    monkeypatch.setattr(service, "RuntimeCloud", lambda **kw: cloud)
    monkeypatch.setattr(service, "resolve_model_key", AsyncMock(return_value=profile))
    lookup = AsyncMock(return_value=KEY)
    monkeypatch.setattr(service, "get_runtime_apm_key", lookup)
    monkeypatch.setattr(service, "ensure_runtime_role", AsyncMock())
    monkeypatch.setattr(
        service,
        "ensure_workload_identity",
        AsyncMock(side_effect=RuntimeError("isolated-stop-before-resources")),
    )
    with pytest.raises(RuntimeError, match="isolated-stop-before-resources"):
        asyncio.run(
            service.provision(
                profile,
                agent_id="mi-test",
                owner="test-owner",
                studio_runtime_owner=studio_owner,
            )
        )
    lookup.assert_not_awaited()


@pytest.mark.parametrize("value", ["masked***", "bad\nkey"])
def test_invalid_explicit_key_does_not_lookup(monkeypatch, value):
    profile = load_studio_profile(provider="byteplus")
    profile.managed.runtime.env[apm_key.RUNTIME_APM_KEY] = value

    def request(**kw):
        raise AssertionError("Explicit invalid key must fail before lookup")

    monkeypatch.setattr(apm_key, "volcengine_signed_request", request)
    with pytest.raises(apm_key.ApmKeyError, match="Configured APM AppKey is invalid"):
        asyncio.run(apm_key.get_runtime_apm_key(profile, Cloud()))
