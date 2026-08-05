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

import pytest

from veadk.cli.studio_telemetry import (
    StudioTelemetryConfigurationError,
    normalize_studio_apmplus_release_environment,
    studio_apmplus_environment_from_options,
    studio_apmplus_release_environment_from_env,
    studio_telemetry_config,
)
from veadk.consts import STUDIO_APMPLUS_DOMAIN, STUDIO_APMPLUS_ENV


def test_studio_telemetry_config_builds_ui_payload_from_environment() -> None:
    config = studio_telemetry_config(
        "20260805120000",
        environ={
            "VEADK_STUDIO_APMPLUS_AID": "12345",
            "VEADK_STUDIO_APMPLUS_TOKEN": "client-token",
            "VEADK_STUDIO_DEPLOY_ID": "stddep_123",
            "VEADK_STUDIO_USER_POOL_ID": "pool-id",
            "VEADK_STUDIO_APPLICATION_ID": "app-id",
            "VEADK_STUDIO_FUNCTION_ID": "function-id",
            "VEADK_STUDIO_DEPLOY_REGION": "cn-beijing",
            "VEADK_STUDIO_PROJECT": "default",
        },
    )

    assert config == {
        "enabled": True,
        "provider": "apmplus",
        "apmplus": {
            "aid": 12345,
            "token": "client-token",
            "domain": STUDIO_APMPLUS_DOMAIN,
            "env": STUDIO_APMPLUS_ENV,
        },
        "studio": {
            "deployId": "stddep_123",
            "userPoolId": "pool-id",
            "applicationId": "app-id",
            "functionId": "function-id",
            "region": "cn-beijing",
            "project": "default",
            "version": "20260805120000",
        },
    }


def test_studio_apmplus_environment_from_options_requires_aid_and_token() -> None:
    with pytest.raises(
        StudioTelemetryConfigurationError,
        match="requires both --apmplus-aid",
    ):
        studio_apmplus_environment_from_options(
            apmplus_aid="",
            apmplus_token="client-token",
            apmplus_domain="",
            apmplus_env="",
            environ={},
        )


def test_studio_apmplus_environment_from_options_uses_fixed_defaults() -> None:
    assert studio_apmplus_environment_from_options(
        apmplus_aid="12345",
        apmplus_token="client-token",
        apmplus_domain="",
        apmplus_env="",
        environ={},
    ) == {
        "VEADK_STUDIO_APMPLUS_AID": "12345",
        "VEADK_STUDIO_APMPLUS_TOKEN": "client-token",
        "VEADK_STUDIO_APMPLUS_DOMAIN": STUDIO_APMPLUS_DOMAIN,
        "VEADK_STUDIO_APMPLUS_ENV": STUDIO_APMPLUS_ENV,
    }


def test_release_environment_carries_only_aid_and_token() -> None:
    assert studio_apmplus_release_environment_from_env(
        environ={
            "VEADK_STUDIO_APMPLUS_AID": "12345",
            "VEADK_STUDIO_APMPLUS_TOKEN": "client-token",
            "VEADK_STUDIO_APMPLUS_DOMAIN": "apmplus.example.com",
        },
    ) == {
        "VEADK_STUDIO_APMPLUS_AID": "12345",
        "VEADK_STUDIO_APMPLUS_TOKEN": "client-token",
    }


def test_release_environment_rejects_unknown_internal_keys() -> None:
    with pytest.raises(
        StudioTelemetryConfigurationError,
        match="Unsupported Studio release environment key",
    ):
        normalize_studio_apmplus_release_environment(
            {
                "VEADK_STUDIO_APMPLUS_AID": "12345",
                "VEADK_STUDIO_APMPLUS_TOKEN": "client-token",
                "VEADK_STUDIO_APMPLUS_DOMAIN": "apmplus.example.com",
            }
        )
