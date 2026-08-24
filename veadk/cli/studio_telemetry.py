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

"""Studio frontend telemetry context exposed through ``/web/ui-config``."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

STUDIO_DEPLOY_ID_ENV = "VEADK_STUDIO_DEPLOY_ID"
STUDIO_USER_POOL_ID_ENV = "VEADK_STUDIO_USER_POOL_ID"
STUDIO_APPLICATION_ID_ENV = "VEADK_STUDIO_APPLICATION_ID"
STUDIO_FUNCTION_ID_ENV = "VEADK_STUDIO_FUNCTION_ID"
STUDIO_DEPLOY_REGION_ENV = "VEADK_STUDIO_DEPLOY_REGION"
STUDIO_PROJECT_ENV = "VEADK_STUDIO_PROJECT"
STUDIO_ACCOUNT_ID_ENV = "VEADK_STUDIO_ACCOUNT_ID"
STUDIO_ACCOUNT_ID_RESOLUTION_ERROR_ENV = "VEADK_STUDIO_ACCOUNT_ID_RESOLUTION_ERROR"
AGENTKIT_SANDBOX_REGION_ENV = "AGENTKIT_SANDBOX_REGION"


def _environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def _env_value(
    environ: Mapping[str, str],
    key: str,
    default: str = "",
) -> str:
    return str(environ.get(key, default) or "").strip()


def studio_telemetry_config(
    version: str,
    *,
    enabled: bool,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return the /web/ui-config telemetry payload for the Studio frontend."""
    current_env = _environment(environ)
    region = _env_value(current_env, STUDIO_DEPLOY_REGION_ENV) or _env_value(
        current_env, AGENTKIT_SANDBOX_REGION_ENV
    )
    return {
        "enabled": enabled,
        "studio": {
            "deployId": _env_value(current_env, STUDIO_DEPLOY_ID_ENV),
            "userPoolId": _env_value(current_env, STUDIO_USER_POOL_ID_ENV),
            "applicationId": _env_value(current_env, STUDIO_APPLICATION_ID_ENV),
            "functionId": _env_value(current_env, STUDIO_FUNCTION_ID_ENV),
            "region": region,
            "project": _env_value(current_env, STUDIO_PROJECT_ENV),
            "version": version,
            "accountId": _env_value(current_env, STUDIO_ACCOUNT_ID_ENV),
            "accountIdResolutionError": _env_value(
                current_env,
                STUDIO_ACCOUNT_ID_RESOLUTION_ERROR_ENV,
            ),
        },
    }
