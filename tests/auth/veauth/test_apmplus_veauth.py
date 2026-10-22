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

from unittest.mock import patch

import pytest

from veadk.auth.veauth.apmplus_veauth import get_apmplus_token


@pytest.fixture(autouse=True)
def _environment(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.delenv("VOLCENGINE_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("VOLC_SESSIONTOKEN", raising=False)
    monkeypatch.delenv("CLOUD_PROVIDER", raising=False)
    monkeypatch.delenv("AGENTKIT_CLOUD_PROVIDER", raising=False)
    monkeypatch.delenv("REGION", raising=False)
    monkeypatch.delenv("BYTEPLUS_REGION", raising=False)


def test_volcengine_uses_volcengine_host_and_region():
    with patch("veadk.auth.veauth.apmplus_veauth.ve_request") as request:
        request.return_value = {"data": {"app_key": "app-key"}}

        assert get_apmplus_token() == "app-key"

    assert request.call_args.kwargs["region"] == "cn-beijing"
    assert request.call_args.kwargs["host"] == "open.volcengineapi.com"
    assert request.call_args.kwargs["header"]["X-Apmplus-Region"] == "cn_beijing"


def test_byteplus_uses_byteplus_host_and_region(monkeypatch):
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    with patch("veadk.auth.veauth.apmplus_veauth.ve_request") as request:
        request.return_value = {"data": {"app_key": "app-key"}}

        assert get_apmplus_token() == "app-key"

    assert request.call_args.kwargs["region"] == "ap-southeast-1"
    assert request.call_args.kwargs["host"] == "open.byteplusapi.com"
    assert request.call_args.kwargs["header"]["X-Apmplus-Region"] == "ap_southeast_1"


def test_explicit_provider_and_credentials_override_environment(monkeypatch):
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("VOLCENGINE_SESSION_TOKEN", "environment-token")
    with patch("veadk.auth.veauth.apmplus_veauth.ve_request") as request:
        request.return_value = {"data": {"app_key": "app-key"}}

        get_apmplus_token(
            cloud_provider="byteplus",
            access_key="explicit-ak",
            secret_key="explicit-sk",
            session_token="explicit-token",
        )

    assert request.call_args.kwargs["ak"] == "explicit-ak"
    assert request.call_args.kwargs["sk"] == "explicit-sk"
    assert request.call_args.kwargs["host"] == "open.byteplusapi.com"
    assert request.call_args.kwargs["header"]["X-Security-Token"] == "explicit-token"


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"data": None},
        {"data": {}},
        {"data": {"app_key": " "}},
        {"data": {"app_key": 42}},
        None,
    ],
)
def test_malformed_response_is_rejected_without_payload(response):
    with patch("veadk.auth.veauth.apmplus_veauth.ve_request", return_value=response):
        with pytest.raises(ValueError, match="missing or invalid AppKey"):
            get_apmplus_token()


def test_iam_credentials_include_session_token(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY")
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY")
    with (
        patch(
            "veadk.auth.veauth.apmplus_veauth.get_credential_from_vefaas_iam",
            return_value=SimpleNamespace(
                access_key_id="iam-ak",
                secret_access_key="iam-sk",
                session_token="iam-session",
            ),
        ),
        patch(
            "veadk.auth.veauth.apmplus_veauth.ve_request",
            return_value={"data": {"app_key": " key "}},
        ) as request,
    ):
        assert get_apmplus_token() == "key"
    assert request.call_args.kwargs["ak"] == "iam-ak"
    assert request.call_args.kwargs["header"]["X-Security-Token"] == "iam-session"
