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

"""Cloud-provider defaults shared by Studio and cloud integrations."""

from __future__ import annotations

import os
from typing import Literal

CloudProvider = Literal["volcengine", "byteplus"]

SUPPORTED_CLOUD_PROVIDERS: tuple[CloudProvider, ...] = ("volcengine", "byteplus")
DEFAULT_CLOUD_PROVIDER: CloudProvider = "volcengine"
DEFAULT_BYTEPLUS_REGION = "ap-southeast-1"
DEFAULT_VOLCENGINE_REGION = "cn-beijing"


def normalize_cloud_provider(value: str | None) -> CloudProvider:
    """Return a supported cloud-provider id, defaulting to Volcengine."""
    normalized = (value or DEFAULT_CLOUD_PROVIDER).strip().lower()
    if normalized == "volces":
        normalized = "volcengine"
    if normalized not in SUPPORTED_CLOUD_PROVIDERS:
        raise ValueError(f"Unsupported cloud provider: {value}")
    return normalized  # type: ignore[return-value]


def cloud_provider_from_env() -> CloudProvider:
    """Resolve the active provider from the process environment."""
    return normalize_cloud_provider(
        os.getenv("AGENTKIT_CLOUD_PROVIDER") or os.getenv("CLOUD_PROVIDER")
    )


def default_region(provider: CloudProvider) -> str:
    """Return the provider's default control-plane region."""
    if provider == "byteplus":
        return os.getenv("BYTEPLUS_REGION") or DEFAULT_BYTEPLUS_REGION
    return DEFAULT_VOLCENGINE_REGION


def vefaas_openapi_host(region: str, provider: CloudProvider) -> str:
    """Return the Function Service OpenAPI host for a provider."""
    if provider == "byteplus":
        return f"vefaas.{region}.byteplusapi.com"
    return "open.volcengineapi.com"


def apig_openapi_host(region: str, provider: CloudProvider) -> str:
    """Return the API Gateway OpenAPI host for a provider."""
    if provider == "byteplus":
        return f"apig.{region}.byteplusapi.com"
    return "open.volcengineapi.com"


def cp_openapi_host(region: str, provider: CloudProvider) -> str:
    """Return the Code Pipeline OpenAPI host for a provider."""
    if provider == "byteplus":
        return f"cp.{region}.byteplusapi.com"
    return "open.volcengineapi.com"


def agentkit_openapi_base(region: str, provider: CloudProvider) -> str:
    """Return the AgentKit OpenAPI base URL used by Studio proxy helpers."""
    if provider == "byteplus":
        return f"https://agentkit.{region}.bytepluses.com"
    return f"https://agentkit.{region}.volcengineapi.com"
