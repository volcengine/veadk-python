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

_SANDBOX_REGIONS = ("cn-beijing", "cn-shanghai")
_BYTEPLUS_SANDBOX_REGIONS = ("ap-southeast-1",)
_RESOURCE_NOT_FOUND_CODE = "InvalidResource.NotFound"


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
    first = (preferred or regions[0]).strip() or regions[0]
    if provider_id == "byteplus" and first not in regions:
        first = regions[0]
    return (first, *tuple(region for region in regions if region != first))


def is_agentkit_resource_not_found(error: object) -> bool:
    return _RESOURCE_NOT_FOUND_CODE.lower() in str(error or "").lower()
