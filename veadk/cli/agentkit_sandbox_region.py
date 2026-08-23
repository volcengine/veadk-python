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

"""Shared AgentKit Sandbox region selection."""

import os

from veadk.utils.cloud_provider import (
    DEFAULT_BYTEPLUS_REGION,
    default_region,
    normalize_cloud_provider,
)

_SANDBOX_REGIONS = ("cn-beijing", "cn-shanghai")
_BYTEPLUS_SANDBOX_REGIONS = ("ap-southeast-1",)
_RESOURCE_NOT_FOUND_CODES = (
    "InvalidResource.NotFound",
    "InvalidAgentKitRuntime.NotFound",
)


def sandbox_region_candidates(
    preferred: str | None = None,
    *,
    provider: str | None = None,
) -> tuple[str, ...]:
    provider_id = (
        (
            provider
            or os.getenv("AGENTKIT_CLOUD_PROVIDER")
            or os.getenv("CLOUD_PROVIDER")
            or "volcengine"
        )
        .strip()
        .lower()
    )
    regions = (
        _BYTEPLUS_SANDBOX_REGIONS if provider_id == "byteplus" else _SANDBOX_REGIONS
    )
    first = (preferred or os.getenv("REGION") or regions[0]).strip() or regions[0]
    if provider_id == "byteplus" and first not in regions:
        first = regions[0]
    return (first, *tuple(region for region in regions if region != first))


def resolve_sandbox_client_region(region: str | None, *, provider: str) -> str:
    """Resolve the region used to instantiate AgentkitToolsClient."""
    provider_id = normalize_cloud_provider(provider)
    resolved = (
        region
        or os.getenv("AGENTKIT_SANDBOX_REGION")
        or os.getenv("REGION")
        or default_region(provider_id)
    ).strip()
    if provider_id == "byteplus" and resolved != DEFAULT_BYTEPLUS_REGION:
        return DEFAULT_BYTEPLUS_REGION
    return resolved or default_region(provider_id)


def is_agentkit_resource_not_found(error: object) -> bool:
    message = str(error or "").lower()
    return any(code.lower() in message for code in _RESOURCE_NOT_FOUND_CODES)
