"""Nonsecret defaults for this Studio deployment's managed MPA creation."""

from __future__ import annotations


def studio_profile_values() -> dict:
    """Return a fresh Beijing profile; secrets remain server environment values."""
    account = "2112682748"
    region = "cn-beijing"
    role = "IDRoleForArkClawShareAgent"
    model = "doubao-seed-2-0-pro-260215"
    registry = f"agentkit-platform-{account}-{region}.cr.volces.com/agentkit"
    return {
        "region": region,
        "account-id": account,
        "model-provider": "openai",
        "model-name": model,
        "model-api-base": "https://ark.cn-beijing.volces.com/api/v3/",
        "model-api-key": "${VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY}",
        "managed": {
            "version": 1,
            "apig": {"adopt-id": "gd72bh4cnjkrkkoplj2ig"},
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
                "image": f"{registry}/mpa_agent_studio:studio-a1f9627-20260923-172555",
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
                    "CLAW_SPACE_ID": f"csi-{account}",
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
                    "RUNTIME_IAM_ROLE_NAME": role,
                    "RUNTIME_IAM_ROLE_TRN": f"trn:iam::{account}:role/{role}",
                    "RUNTIME_PROVIDER": "VEFAAS",
                    "SCHEDULED_TASK_BACKEND": "postgresql",
                    "ENABLE_APMPLUS": "true",
                    "OTEL_RESOURCE_ATTRIBUTES": "apmplus.business_carrier=agentkit_runtime",
                    "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT": "2048",
                    "OTEL_EXPERIMENTAL_RESOURCE_DETECTORS": "otel,process",
                },
            },
            "worker": {
                "image": (
                    f"{registry}/agentkit_mpa_codex_worker:"
                    "20260921-master-81f3496-160404"
                ),
                "reference-id": "t-yeuujqfldstkidoad4p0",
                "role-name": role,
            },
            "timeout-seconds": 1800,
            "network": {
                "vpc-id": "vpc-iior17eqo0lc74o8cuqfopoj",
                "subnet-ids": ["subnet-iior802kmtj474o8cu9arqzl"],
            },
        },
    }
