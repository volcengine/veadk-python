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

from veadk.cli.studio_telemetry import studio_telemetry_config


def test_studio_telemetry_config_builds_ui_payload_from_environment() -> None:
    config = studio_telemetry_config(
        "20260805120000",
        enabled=True,
        environ={
            "VEADK_STUDIO_DEPLOY_ID": "stddep_123",
            "VEADK_STUDIO_USER_POOL_ID": "pool-id",
            "VEADK_STUDIO_APPLICATION_ID": "app-id",
            "VEADK_STUDIO_FUNCTION_ID": "function-id",
            "VEADK_STUDIO_DEPLOY_REGION": "cn-beijing",
            "VEADK_STUDIO_PROJECT": "default",
            "VEADK_STUDIO_ACCOUNT_ID": "2100123456",
            "VEADK_STUDIO_ACCOUNT_ID_RESOLUTION_ERROR": "sts unavailable",
        },
    )

    assert config == {
        "enabled": True,
        "studio": {
            "deployId": "stddep_123",
            "userPoolId": "pool-id",
            "applicationId": "app-id",
            "functionId": "function-id",
            "region": "cn-beijing",
            "project": "default",
            "version": "20260805120000",
            "accountId": "2100123456",
            "accountIdResolutionError": "sts unavailable",
        },
    }
