# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Provider-neutral Studio runtime credential tests."""

import json

import pytest
from agentkit.platform.context import default_cloud_provider
from agentkit.sdk.tools.client import AgentkitToolsClient

from veadk.cli.studio_cloud_credentials import (
    StudioCloudCredentialError,
    agentkit_client_options,
    resolve_studio_cloud_credentials,
)


@pytest.fixture(autouse=True)
def _clean_cloud_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AGENTKIT_CLOUD_PROVIDER",
        "CLOUD_PROVIDER",
        "BYTEPLUS_ACCESS_KEY",
        "BYTEPLUS_SECRET_KEY",
        "BYTEPLUS_SESSION_TOKEN",
        "VOLCENGINE_ACCESS_KEY",
        "VOLCENGINE_SECRET_KEY",
        "VOLCENGINE_SESSION_TOKEN",
        "VOLC_SESSIONTOKEN",
    ):
        monkeypatch.delenv(key, raising=False)


def test_byteplus_agentkit_options_use_vefaas_iam_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    credential_path = tmp_path / "credential"
    credential_path.write_text(
        json.dumps(
            {
                "access_key_id": "iam-ak",
                "secret_access_key": "iam-sk",
                "session_token": "iam-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setattr(
        "veadk.cli.studio_cloud_credentials.VEFAAS_IAM_CRIDENTIAL_PATH",
        str(credential_path),
    )

    assert agentkit_client_options("ap-southeast-1") == {
        "access_key": "iam-ak",
        "secret_key": "iam-sk",
        "session_token": "iam-token",
        "region": "ap-southeast-1",
    }


def test_byteplus_agentkit_options_select_byteplus_sdk_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    credential_path = tmp_path / "credential"
    credential_path.write_text(
        json.dumps(
            {
                "access_key_id": "iam-ak",
                "secret_access_key": "iam-sk",
                "session_token": "iam-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setattr(
        "veadk.cli.studio_cloud_credentials.VEFAAS_IAM_CRIDENTIAL_PATH",
        str(credential_path),
    )

    with default_cloud_provider("byteplus"):
        client = AgentkitToolsClient(**agentkit_client_options("ap-southeast-1"))

    assert client.host == "agentkit.ap-southeast-1.byteplusapi.com"
    assert client.region == "ap-southeast-1"
    assert client.session_token == "iam-token"


def test_byteplus_environment_credentials_take_precedence_over_iam(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    missing_path = tmp_path / "missing"
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "env-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "env-sk")
    monkeypatch.setenv("BYTEPLUS_SESSION_TOKEN", "env-token")
    monkeypatch.setattr(
        "veadk.cli.studio_cloud_credentials.VEFAAS_IAM_CRIDENTIAL_PATH",
        str(missing_path),
    )

    credentials = resolve_studio_cloud_credentials("byteplus")

    assert credentials.access_key == "env-ak"
    assert credentials.secret_key == "env-sk"
    assert credentials.session_token == "env-token"
    assert credentials.source == "environment"


def test_volcengine_agentkit_options_preserve_sdk_credential_refresh() -> None:
    assert agentkit_client_options(
        "cn-beijing",
        provider="volcengine",
    ) == {"region": "cn-beijing"}


def test_missing_runtime_credentials_fail_without_secret_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "veadk.cli.studio_cloud_credentials.VEFAAS_IAM_CRIDENTIAL_PATH",
        str(tmp_path / "missing"),
    )

    with pytest.raises(StudioCloudCredentialError) as caught:
        resolve_studio_cloud_credentials("byteplus")

    assert caught.value.provider == "byteplus"
    assert "BytePlus credentials not found" in str(caught.value)
    assert "access_key" not in str(caught.value)
