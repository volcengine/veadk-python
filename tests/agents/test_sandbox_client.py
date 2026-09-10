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


"""Verify remote sandbox endpoint selection and signing configuration offline."""

import os
from unittest.mock import patch

import pytest

from veadk.agents._remote_sandbox.client import create_agentkit_client


@pytest.mark.parametrize("service", ["agentkit_ppe", "agentkit_stg"])
def test_veadk_overrides_sdk_endpoint_and_signing(service):
    env = {
        "CLOUD_PROVIDER": "volcengine",
        "VOLCENGINE_AGENTKIT_SERVICE": "agentkit",
        "VOLCENGINE_AGENTKIT_HOST": "sdk.example.test",
        "AGENTKIT_TOOL_SERVICE_CODE": service,
        "AGENTKIT_TOOL_HOST": "sandbox.example.test",
        "AGENTKIT_TOOL_SCHEME": "http",
        "AGENTKIT_TOOL_REGION": "cn-beijing",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch(
            "veadk.agents._remote_sandbox.client.get_agentkit_credentials",
            return_value=(
                "fixture-ak",
                "fixture-sk",
                {"X-Security-Token": "fixture-sts"},
            ),
        ),
    ):
        before = dict(os.environ)
        client = create_agentkit_client({})
        assert client.host == client.service_info.host == "sandbox.example.test"
        assert client.service == client.service_info.credentials.service == service
        assert client.scheme == client.service_info.scheme == "http"
        assert client.region == client.service_info.credentials.region == "cn-beijing"
        assert client.service_info.credentials.session_token == "fixture-sts"
        assert dict(os.environ) == before


def test_sdk_overrides_remain_available_without_veadk_overrides():
    env = {
        "CLOUD_PROVIDER": "volcengine",
        "VOLCENGINE_AGENTKIT_SERVICE": "agentkit_stg",
        "VOLCENGINE_AGENTKIT_HOST": "sdk.example.test",
        "VOLCENGINE_AGENTKIT_SCHEME": "http",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch(
            "veadk.agents._remote_sandbox.client.get_agentkit_credentials",
            return_value=("fixture-ak", "fixture-sk", {}),
        ),
    ):
        client = create_agentkit_client()
        assert client.service_info.host == "sdk.example.test"
        assert client.service_info.credentials.service == "agentkit_stg"
        assert client.service_info.scheme == "http"


def test_service_only_uses_veadk_derived_host():
    with (
        patch.dict(
            os.environ,
            {
                "CLOUD_PROVIDER": "volcengine",
                "AGENTKIT_TOOL_SERVICE_CODE": "agentkit_ppe",
                "AGENTKIT_TOOL_REGION": "cn-beijing",
            },
            clear=True,
        ),
        patch(
            "veadk.agents._remote_sandbox.client.get_agentkit_credentials",
            return_value=("fixture-ak", "fixture-sk", {}),
        ),
    ):
        client = create_agentkit_client()
        assert client.service_info.host == "agentkit_ppe.cn-beijing.volces.com"
        assert client.service_info.credentials.service == "agentkit_ppe"
