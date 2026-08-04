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

"""Harness plugin assembly for HarnessApp Runtime."""

from __future__ import annotations

import os
from collections.abc import Mapping

from google.adk.plugins import BasePlugin

from veadk.cloud.harness_app.types import HarnessEnhanceOverrides
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


def build_harness_plugins_from_runtime_env(
    env: Mapping[str, str] | None = None,
) -> list[BasePlugin]:
    """Build Harness plugins from environment values."""

    values = dict(env or os.environ)
    try:
        from veadk.extensions.harness.env import build_harness_plugins_from_env
    except ImportError as e:
        if _truthy(values.get("HARNESS_ENHANCE_ENABLED")):
            logger.warning(
                "HARNESS_ENHANCE_ENABLED is set but the Harness extension "
                f"could not be imported: {e!r}"
            )
        return []
    return build_harness_plugins_from_env(values)


def build_harness_plugins_from_headers(
    headers: Mapping[str, str],
    *,
    base_env: Mapping[str, str] | None = None,
) -> list[BasePlugin]:
    """Build per-invocation plugins from AgentKit/HTTP Harness headers."""

    header_env = harness_env_from_headers(headers)
    if not header_env:
        return []
    values = dict(base_env or os.environ)
    values.update(header_env)
    return build_harness_plugins_from_runtime_env(values)


def build_harness_plugins_from_enhance(
    enhance: HarnessEnhanceOverrides | None,
    *,
    base_env: Mapping[str, str] | None = None,
) -> list[BasePlugin]:
    """Build per-invocation plugins from request-body Harness settings."""

    body_env = harness_env_from_enhance(enhance)
    if not body_env:
        return []
    values = dict(base_env or os.environ)
    values.update(body_env)
    return build_harness_plugins_from_runtime_env(values)


def harness_env_from_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Convert generic Harness headers into SDK environment keys."""

    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    enabled = normalized.get("x-harness-enhance") or normalized.get(
        "x-harness-enable-context"
    )
    if not _truthy(enabled):
        return {}
    env = {"HARNESS_ENHANCE_ENABLED": "true"}
    components = normalized.get("x-harness-components")
    if components:
        env["HARNESS_COMPONENTS"] = components
        env["HARNESS_ENHANCE_COMPONENTS"] = components
    profile = normalized.get("x-harness-profile")
    if profile:
        env["HARNESS_PROFILE"] = profile
        env["HARNESS_ENHANCE_PROFILE"] = profile
    compression_provider = normalized.get("x-harness-compression-provider")
    if compression_provider:
        env["HARNESS_COMPRESSION_PROVIDER"] = compression_provider
        env["HARNESS_ENHANCE_COMPRESSION_PROVIDER"] = compression_provider
    return env


def harness_env_from_enhance(
    enhance: HarnessEnhanceOverrides | None,
) -> dict[str, str]:
    """Convert request-body Harness settings into SDK environment keys."""

    if enhance is None or not enhance.enabled:
        return {}
    env = {"HARNESS_ENHANCE_ENABLED": "true"}
    if enhance.components:
        env["HARNESS_COMPONENTS"] = enhance.components
        env["HARNESS_ENHANCE_COMPONENTS"] = enhance.components
    if enhance.profile:
        env["HARNESS_PROFILE"] = enhance.profile
        env["HARNESS_ENHANCE_PROFILE"] = enhance.profile
    if enhance.compression_provider:
        env["HARNESS_COMPRESSION_PROVIDER"] = enhance.compression_provider
        env["HARNESS_ENHANCE_COMPRESSION_PROVIDER"] = enhance.compression_provider
    return env


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in _TRUTHY)
