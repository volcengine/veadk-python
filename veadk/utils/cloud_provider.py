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
DEFAULT_BYTEPLUS_VIKING_MEMORY_REGION = "cn-hongkong"
DEFAULT_BYTEPLUS_VIKING_MEMORY_HOST = (
    f"api-knowledgebase.mlp.{DEFAULT_BYTEPLUS_VIKING_MEMORY_REGION}.bytepluses.com"
)
DEFAULT_VOLCENGINE_REGION = "cn-beijing"
_VEFAAS_APPLICATION_TEMPLATE_IDS: dict[CloudProvider, dict[str, str]] = {
    "volcengine": {
        "cn-beijing": "6874f3360bdbc40008ecf8c7",
        "cn-shanghai": "6a685988162bcd00083c9001",
    },
    "byteplus": {
        DEFAULT_BYTEPLUS_REGION: "697a03b8adb54b0008fdebd0",
    },
}


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
    return os.getenv("REGION") or DEFAULT_VOLCENGINE_REGION


def default_vefaas_application_template_id(
    provider: CloudProvider,
    region: str,
) -> str:
    """Return the built-in VeFaaS Application Center template id, if known."""
    provider_templates = _VEFAAS_APPLICATION_TEMPLATE_IDS.get(provider, {})
    if provider == "volcengine":
        return (
            provider_templates.get(region)
            or provider_templates[DEFAULT_VOLCENGINE_REGION]
        )
    return provider_templates.get(region, "")


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


def iam_openapi_host(provider: CloudProvider) -> str:
    """Return the IAM OpenAPI host for a provider."""
    if provider == "byteplus":
        return "iam.byteplusapi.com"
    return "iam.volcengineapi.com"


def apmplus_openapi_host(provider: CloudProvider) -> str:
    """Return the APMPlus OpenAPI host for a provider."""
    if provider == "byteplus":
        return "open.byteplusapi.com"
    return "open.volcengineapi.com"


def apmplus_otlp_endpoint(region: str) -> str:
    """Return the regional APMPlus OTLP/gRPC endpoint."""
    return f"http://apmplus-{region}.volces.com:4317"


def agentkit_openapi_base(region: str, provider: CloudProvider) -> str:
    """Return the AgentKit OpenAPI base URL used by Studio proxy helpers."""
    if provider == "byteplus":
        return f"https://agentkit.{region}.byteplusapi.com"
    return f"https://agentkit.{region}.volcengineapi.com"
