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

"""Nonsecret defaults for this Studio deployment's managed MPA creation."""

from __future__ import annotations

import os


def studio_profile_values(provider: str = "volcengine") -> dict:
    """Return provider defaults; model keys resolve with deployment identity."""
    region = "cn-beijing"
    role = "IDRoleForArkClawShareAgent"
    model = "doubao-seed-2-0-pro-260215"
    registry = "agentkit-platform-2112682748-cn-beijing.cr.volces.com/mpa"
    values = {
        "region": region,
        "model-provider": "openai",
        "model-name": model,
        "model-api-base": "https://ark.cn-beijing.volces.com/api/v3/",
        "managed": {
            "version": 1,
            "model-key": {
                "mode": "ark",
                "api-key-id": os.getenv("VEADK_MPA_ARK_API_KEY_ID", "").strip(),
                "api-key-name": os.getenv("VEADK_MPA_ARK_API_KEY_NAME", "").strip(),
            },
            "iam": {"mode": "auto"},
            "postgres": {
                "mode": "auto",
                "legacy-urls": "ignore",
                "admin-workspace-name": "mpa_admin_workspace",
                "business-workspace-name": "mpa_business_workspace",
                "bootstrap-path": "/tmp/veadk-studio/mpa-pg-bootstrap.sqlite3",
            },
            "database-admin-url-env": "DEPLOYMENT_DATABASE_ADMIN_URL",
            "shared-database-url-env": "SHARED_APIG_DATABASE_URL",
            "runtime": {
                "image": f"{registry}/mpa_agent:latest",
                "role-name": role,
                "cpu-milli": 2000,
                "memory-mb": 4096,
                "min-instance": 1,
                "max-instance": 1,
                "max-concurrency": 100,
                "apmplus-enable": True,
                "project-name": "default",
                "env": {
                    "A2A_TIP_VERIFY_ENABLED": "false",
                    "APMPLUS_TRACE_CONTENT": "false",
                    "APPCENTER_RESOURCE_DISCOVERY_ENABLED": "false",
                    "CHANNEL_ADMIN_AUTH_MODE": "runtime_key",
                    "CHANNEL_BACKEND": "postgresql",
                    "CLOUD_PROVIDER": "volcengine",
                    "FORCE_APMPLUS_EXPORTER_REGISTRATION": "true",
                    "IDENTITY_REGION": region,
                    "IDENTITY_STARTUP_ENABLED": "false",
                    "IM_GATEWAY_STARTUP_ENABLED": "false",
                    "MPA_CODEX_WORKER_ALLOW_PUBLIC_FALLBACK": "true",
                    "MPA_CODEX_WORKER_DEFAULT_MODEL": model,
                    "MPA_CODEX_WORKER_ENDPOINT_PREFERENCE": "public",
                    "MPA_LAZY_LOGIN": "false",
                    "MPA_SELECTABLE_MODELS": (
                        "doubao-seed-2-0-pro-260215,doubao-seed-2-1-pro-260628"
                    ),
                    "MPA_SESSION_MEMORY_BACKEND": "postgresql",
                    "REGION": region,
                    "RUNTIME_PROVIDER": "VEFAAS",
                    "SCHEDULED_TASK_BACKEND": "postgresql",
                    "ENABLE_APMPLUS": "true",
                    "OTEL_RESOURCE_ATTRIBUTES": "apmplus.business_carrier=agentkit_runtime",
                    "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT": "2048",
                    "OTEL_EXPERIMENTAL_RESOURCE_DETECTORS": "otel,process",
                },
            },
            "worker": {
                "image": f"{registry}/mpa_codex_worker:latest",
                "role-name": role,
            },
            "timeout-seconds": 1800,
        },
    }

    if provider == "volcengine":
        return values
    if provider != "byteplus":
        raise ValueError("Unsupported managed cloud provider")
    from veadk.cli.studio_model_catalog import (
        modelark_base_url,
        studio_agent_model_name,
    )

    from .provider import managed_host

    region = "ap-southeast-1"
    model = studio_agent_model_name(provider)
    values.update(
        {
            "cloud-provider": provider,
            "region": region,
            "model-name": model,
            "model-api-base": modelark_base_url(provider),
        }
    )
    managed = values["managed"]
    managed["credential-file"] = os.getenv(
        "VEADK_MPA_BYTEPLUS_CREDENTIAL_FILE", ""
    ).strip()
    managed_host("aidap", region, "byteplus")
    managed["postgres"]["bootstrap-path"] = (
        "/tmp/veadk-studio/mpa-pg-bootstrap-byteplus.sqlite3"
    )
    runtime = managed["runtime"]
    runtime["image"] = (
        os.getenv("VEADK_MPA_BYTEPLUS_RUNTIME_IMAGE", "").strip() or runtime["image"]
    )
    managed["worker"]["image"] = (
        os.getenv("VEADK_MPA_BYTEPLUS_WORKER_IMAGE", "").strip()
        or managed["worker"]["image"]
    )
    runtime["env"].update(
        {
            "CLOUD_PROVIDER": provider,
            "AGENTKIT_CLOUD_PROVIDER": provider,
            "BYTEPLUS_REGION": region,
            "REGION": region,
            "IDENTITY_REGION": region,
            "MPA_CODEX_WORKER_DEFAULT_MODEL": model,
            "MPA_SELECTABLE_MODELS": model,
            "APIG_TOP_ENDPOINT": managed_host("apig", region, provider),
        }
    )
    # The Worker SDK must resolve overseas services in the same way as Runtime.
    managed["worker"]["env"] = {
        "CLOUD_PROVIDER": provider,
        "AGENTKIT_CLOUD_PROVIDER": provider,
        "BYTEPLUS_REGION": region,
        "REGION": region,
    }
    return values
