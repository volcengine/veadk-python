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

"""Managed creation endpoint selection without cross-provider fallback."""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

from veadk.utils.cloud_provider import (
    normalize_cloud_provider,
    apig_openapi_host,
    iam_openapi_host,
)


def managed_host(service: str, region: str, provider: str) -> str:
    """Keep domestic transports intact and select overseas service hosts."""
    provider = normalize_cloud_provider(provider)
    if provider == "volcengine":
        if service in {"vpc", "ecs", "apig"}:
            return f"{service}.{region}.volcengineapi.com"
        if service == "iam":
            return "iam.volcengineapi.com"
        if service == "sts":
            return "sts.volcengineapi.com"
        return "open.volcengineapi.com"
    if service == "apig":
        return apig_openapi_host(region, provider)
    if service == "iam":
        return (
            iam_openapi_host(provider)
            if os.getenv("IAM_OPENAPI_HOST")
            else "open.byteplusapi.com"
        )
    if service == "sts":
        return "open.byteplusapi.com"
    if service == "aidap":
        # Account-specific deployments may expose a different regional endpoint.
        override = os.getenv("VEADK_MPA_BYTEPLUS_AIDAP_HOST", "").strip()
        if override:
            parsed = urlsplit("https://" + override)
            if (
                parsed.netloc != override
                or not parsed.hostname
                or any(
                    (
                        parsed.username,
                        parsed.password,
                        parsed.path,
                        parsed.query,
                        parsed.fragment,
                    )
                )
            ):
                raise ValueError("Invalid BytePlus AIDAP host")
            return override
        return "open.byteplusapi.com"
    if service not in {"vpc", "ecs", "ark"}:
        raise ValueError("Unsupported managed service")
    return f"{service}.{region}.byteplusapi.com"


def region_contains_zone(
    region: str, zone: object, provider: str = "volcengine"
) -> bool:
    """Validate regional ownership without rewriting provider resource IDs."""
    if not isinstance(zone, str):
        return False
    if provider == "byteplus":
        return bool(re.fullmatch(re.escape(region) + r"-?[a-z]", zone))
    return zone.startswith(region + "-") and bool(zone[len(region) + 1 :])
