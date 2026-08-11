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

"""Studio telemetry configuration helpers.

This module is the Python-side boundary for Studio WebPro/APMPlus telemetry.
Keep the environment variable names, validation, and /web/ui-config payload
shape here so CLI deploy, release publishing, and runtime config cannot drift.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from veadk.consts import (
    STUDIO_APMPLUS_AID,
    STUDIO_APMPLUS_DOMAIN,
    STUDIO_APMPLUS_ENV,
    STUDIO_APMPLUS_TOKEN,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

STUDIO_APMPLUS_AID_ENV = "VEADK_STUDIO_APMPLUS_AID"
STUDIO_APMPLUS_TOKEN_ENV = "VEADK_STUDIO_APMPLUS_TOKEN"
STUDIO_APMPLUS_DOMAIN_ENV = "VEADK_STUDIO_APMPLUS_DOMAIN"
STUDIO_APMPLUS_ENV_ENV = "VEADK_STUDIO_APMPLUS_ENV"

STUDIO_DEPLOY_ID_ENV = "VEADK_STUDIO_DEPLOY_ID"
STUDIO_USER_POOL_ID_ENV = "VEADK_STUDIO_USER_POOL_ID"
STUDIO_APPLICATION_ID_ENV = "VEADK_STUDIO_APPLICATION_ID"
STUDIO_FUNCTION_ID_ENV = "VEADK_STUDIO_FUNCTION_ID"
STUDIO_DEPLOY_REGION_ENV = "VEADK_STUDIO_DEPLOY_REGION"
STUDIO_PROJECT_ENV = "VEADK_STUDIO_PROJECT"
AGENTKIT_SANDBOX_REGION_ENV = "AGENTKIT_SANDBOX_REGION"

STUDIO_APMPLUS_RELEASE_ENVIRONMENT_KEYS = frozenset(
    {
        STUDIO_APMPLUS_AID_ENV,
        STUDIO_APMPLUS_TOKEN_ENV,
    }
)


class StudioTelemetryConfigurationError(ValueError):
    """Raised when Studio telemetry configuration is incomplete or invalid."""


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
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return the /web/ui-config telemetry payload for the Studio frontend."""
    current_env = _environment(environ)
    aid_text = _env_value(current_env, STUDIO_APMPLUS_AID_ENV) or STUDIO_APMPLUS_AID
    token = _env_value(current_env, STUDIO_APMPLUS_TOKEN_ENV) or STUDIO_APMPLUS_TOKEN
    if not aid_text or not token:
        return {"enabled": False}
    try:
        aid = int(aid_text)
    except ValueError:
        logger.warning(
            "%s must be an integer; telemetry disabled", STUDIO_APMPLUS_AID_ENV
        )
        return {"enabled": False}

    region = _env_value(current_env, STUDIO_DEPLOY_REGION_ENV) or _env_value(
        current_env, AGENTKIT_SANDBOX_REGION_ENV
    )
    return {
        "enabled": True,
        "provider": "apmplus",
        "apmplus": {
            "aid": aid,
            "token": token,
            "domain": _env_value(
                current_env,
                STUDIO_APMPLUS_DOMAIN_ENV,
                STUDIO_APMPLUS_DOMAIN,
            )
            or STUDIO_APMPLUS_DOMAIN,
            "env": _env_value(
                current_env,
                STUDIO_APMPLUS_ENV_ENV,
                STUDIO_APMPLUS_ENV,
            )
            or STUDIO_APMPLUS_ENV,
        },
        "studio": {
            "deployId": _env_value(current_env, STUDIO_DEPLOY_ID_ENV),
            "userPoolId": _env_value(current_env, STUDIO_USER_POOL_ID_ENV),
            "applicationId": _env_value(current_env, STUDIO_APPLICATION_ID_ENV),
            "functionId": _env_value(current_env, STUDIO_FUNCTION_ID_ENV),
            "region": region,
            "project": _env_value(current_env, STUDIO_PROJECT_ENV),
            "version": version,
        },
    }


def studio_apmplus_environment_from_options(
    *,
    apmplus_aid: str,
    apmplus_token: str,
    apmplus_domain: str,
    apmplus_env: str,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return VeFaaS environment overrides for Studio APMPlus telemetry."""
    current_env = _environment(environ)
    configured_aid = apmplus_aid.strip() or _env_value(
        current_env, STUDIO_APMPLUS_AID_ENV
    )
    configured_token = apmplus_token.strip() or _env_value(
        current_env, STUDIO_APMPLUS_TOKEN_ENV
    )
    configured_domain = apmplus_domain.strip() or _env_value(
        current_env, STUDIO_APMPLUS_DOMAIN_ENV
    )
    configured_env = apmplus_env.strip() or _env_value(
        current_env,
        STUDIO_APMPLUS_ENV_ENV,
    )
    if not any([configured_aid, configured_token, configured_domain, configured_env]):
        return {}
    values = {
        STUDIO_APMPLUS_AID_ENV: configured_aid or STUDIO_APMPLUS_AID,
        STUDIO_APMPLUS_TOKEN_ENV: configured_token or STUDIO_APMPLUS_TOKEN,
        STUDIO_APMPLUS_DOMAIN_ENV: configured_domain or STUDIO_APMPLUS_DOMAIN,
        STUDIO_APMPLUS_ENV_ENV: configured_env or STUDIO_APMPLUS_ENV,
    }
    _validate_studio_apmplus_pair(
        values[STUDIO_APMPLUS_AID_ENV],
        values[STUDIO_APMPLUS_TOKEN_ENV],
        message=(
            "Studio APMPlus telemetry requires both --apmplus-aid and "
            "--apmplus-token when any APMPlus option is configured."
        ),
    )
    return values


def studio_apmplus_release_environment_from_env(
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return release-time APMPlus defaults from the publisher environment."""
    current_env = _environment(environ)
    aid = _env_value(current_env, STUDIO_APMPLUS_AID_ENV)
    token = _env_value(current_env, STUDIO_APMPLUS_TOKEN_ENV)
    if not aid and not token:
        return {}
    _validate_studio_apmplus_pair(
        aid,
        token,
        message=(
            "Studio APMPlus release environment requires both "
            f"{STUDIO_APMPLUS_AID_ENV} and {STUDIO_APMPLUS_TOKEN_ENV}."
        ),
    )
    return {
        STUDIO_APMPLUS_AID_ENV: aid,
        STUDIO_APMPLUS_TOKEN_ENV: token,
    }


def normalize_studio_apmplus_release_environment(value: object) -> dict[str, str]:
    """Validate the internal release-bundle telemetry environment payload."""
    if not isinstance(value, dict):
        raise StudioTelemetryConfigurationError(
            "Studio release environment must be a JSON object."
        )
    environment: dict[str, str] = {}
    for key, item in value.items():
        if key not in STUDIO_APMPLUS_RELEASE_ENVIRONMENT_KEYS:
            raise StudioTelemetryConfigurationError(
                f"Unsupported Studio release environment key: {key}."
            )
        if not isinstance(item, str) or not item.strip():
            raise StudioTelemetryConfigurationError(
                f"Studio release environment value is invalid: {key}."
            )
        environment[key] = item.strip()
    _validate_studio_apmplus_pair(
        environment.get(STUDIO_APMPLUS_AID_ENV, ""),
        environment.get(STUDIO_APMPLUS_TOKEN_ENV, ""),
        message=(
            "Studio release environment requires both "
            f"{STUDIO_APMPLUS_AID_ENV} and {STUDIO_APMPLUS_TOKEN_ENV}."
        ),
    )
    return environment


def _validate_studio_apmplus_pair(
    aid: str,
    token: str,
    *,
    message: str,
) -> None:
    if bool(aid) != bool(token):
        raise StudioTelemetryConfigurationError(message)
    if aid:
        try:
            int(aid)
        except ValueError as error:
            raise StudioTelemetryConfigurationError(
                f"{STUDIO_APMPLUS_AID_ENV} must be an integer."
            ) from error
