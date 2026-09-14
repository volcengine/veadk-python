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

"""Provisioning helpers for the veadk-version mpa-agent one-click flow.

This module holds the pure, side-effect-free pieces of ``veadk mpa create``:
parameter shape, identity adaptation, runtime env assembly, and secret masking.
Cloud deployment, ``mpa_meta`` seeding, and HTTP verification live in their own
modules so this part stays trivially testable.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

# Env keys whose values are secrets and must never be logged or printed in the
# clear (masked in dry-run output).
SECRET_ENV_KEYS: frozenset[str] = frozenset(
    {
        "PGPASSWORD",
        "MODEL_AGENT_API_KEY",
        "OPENVIKING_API_KEY",
        "FEISHU_APP_SECRET",
        "CODEX_MCP_RUNTIME_API_KEY",
    }
)


@dataclass
class MpaProvisionParams:
    """Resolved parameters for one ``veadk mpa create`` invocation."""

    image: str
    registry_name: str
    mpa_agent_id: str
    account_id: str
    region: str
    pg_host: str
    pg_port: str
    pg_database: str
    pg_user: str
    pg_password: str
    model_provider: str
    model_api_base: str
    model_api_key: str
    model_name: str
    agentkit_tool_id: str
    # Optional / defaulted.
    claw_space_id: str | None = None
    pg_sslmode: str = "require"
    pg_channel_binding: str = "require"
    agentkit_tool_region: str = "cn-beijing"
    skill_space_id: str = ""
    identity_region: str = "cn-beijing"
    openviking_url: str = ""
    openviking_resource_id: str = ""
    openviking_api_key: str = ""
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    selectable_models: tuple[str, ...] = ()
    extra_env: dict[str, str] = field(default_factory=dict)


def derive_claw_space_id(claw_space_id: str | None, *, account_id: str) -> str:
    """Return the explicit space id, or derive ``csi-<account_id>`` (FR-10)."""
    explicit = (claw_space_id or "").strip()
    if explicit:
        return explicit
    account = (account_id or "").strip()
    if not account:
        raise ValueError("account_id is required to derive CLAW_SPACE_ID")
    return f"csi-{account}"


# Mirror arkclaw-team GenerateTemplateID: lowercase alnum, fixed-length suffix.
_ID_CHARSET = "abcdefghijklmnopqrstuvwxyz0123456789"
_ID_SUFFIX_LENGTH = 12


def generate_mpa_agent_id() -> str:
    """Generate a globally-unique ``mi-<12 lowercase alnum>`` instance id.

    Follows the arkclaw-team ``GenerateTemplateID`` strategy (charset + fixed
    suffix length) but uses ``secrets`` for the random source.
    """
    suffix = "".join(secrets.choice(_ID_CHARSET) for _ in range(_ID_SUFFIX_LENGTH))
    return f"mi-{suffix}"


def tool_name_for_agent(mpa_agent_id: str) -> str:
    """Return the Codex worker Tool name for an agent id.

    Matches the observed convention where a per-agent Tool is named
    ``mi_<id>`` (underscore form of the ``mi-<id>`` instance id), giving each
    agent its own dynamically-created Tool while keeping same-id re-runs
    idempotent (reuse-by-name).
    """
    return (mpa_agent_id or "").strip().replace("-", "_")


def mask_secret(value: str) -> str:
    """Mask a secret for display: keep the first char, star the rest.

    Short secrets (<= 4 chars) are fully masked. Empty stays empty.
    """
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 1)


def build_runtime_env(
    params: MpaProvisionParams,
    *,
    public_endpoint: str,
) -> dict[str, str]:
    """Assemble the runtime environment variables for the mpa-agent function.

    In the veadk scenario the public endpoint is authoritative (FR-11) and
    identity startup is disabled with a derived space id (FR-10). OpenViking and
    Feishu keys are included only when supplied.
    """
    claw_space_id = derive_claw_space_id(
        params.claw_space_id, account_id=params.account_id
    )

    env: dict[str, str] = {
        # Model
        "MODEL_AGENT_PROVIDER": params.model_provider,
        "MODEL_AGENT_API_BASE": params.model_api_base,
        "MODEL_AGENT_API_KEY": params.model_api_key,
        "MODEL_AGENT_NAME": params.model_name,
        # mpa-agent's Codex setting has the non-empty default ``auto`` and is
        # preferred over MODEL_AGENT_NAME. Set it explicitly so delegated
        # worker turns use the same CLI-selected model as the primary agent.
        "MPA_CODEX_WORKER_DEFAULT_MODEL": params.model_name,
        "MPA_SELECTABLE_MODELS": ",".join(
            dict.fromkeys((params.model_name, *params.selectable_models))
        ),
        # PostgreSQL session store
        "MPA_SESSION_MEMORY_BACKEND": "postgresql",
        "PGHOST": params.pg_host,
        "PGPORT": str(params.pg_port),
        "PGDATABASE": params.pg_database,
        "PGUSER": params.pg_user,
        "PGPASSWORD": params.pg_password,
        "PGSSLMODE": params.pg_sslmode,
        "PGCHANNELBINDING": params.pg_channel_binding,
        # Channels + scheduler share the PostgreSQL backend by default.
        "CHANNEL_BACKEND": "postgresql",
        "SCHEDULED_TASK_BACKEND": "postgresql",
        # Identity adaptation (FR-10): no arkclaw identity pools in this scenario.
        "IDENTITY_STARTUP_ENABLED": "false",
        "MPA_LAZY_LOGIN": "false",
        # VeADK uses external resources and only retains CLAW_SPACE_ID as a
        # compatibility identifier. It must not query the ArkClaw registry.
        "APPCENTER_RESOURCE_DISCOVERY_ENABLED": "false",
        "IM_GATEWAY_STARTUP_ENABLED": "false",
        # Keep trace timing and structured spans without exporting raw content.
        "APMPLUS_TRACE_CONTENT": "false",
        "FORCE_APMPLUS_EXPORTER_REGISTRATION": "true",
        # Without arkclaw userpool/client/workload resources there is no TIP
        # issuer for Studio. The Runtime remains protected by APIG key auth;
        # disable only the inner TIP gate so Studio A2A calls can reach it.
        "A2A_TIP_VERIFY_ENABLED": "false",
        "CLAW_SPACE_ID": claw_space_id,
        "MPA_AGENT_ID": params.mpa_agent_id,
        "IDENTITY_REGION": params.identity_region,
        # AgentKit sandbox tool
        "AGENTKIT_TOOL_ID": params.agentkit_tool_id,
        "AGENTKIT_TOOL_REGION": params.agentkit_tool_region,
        # APIG region for runtime OpenAPI calls.
        "REGION": params.region,
        # Codex worker endpoint preference (FR-11): public endpoint scenario.
        "MPA_CODEX_WORKER_ENDPOINT_PREFERENCE": "public",
        "MPA_CODEX_WORKER_ALLOW_PUBLIC_FALLBACK": "true",
    }

    if params.skill_space_id:
        env["SKILL_SPACE_ID"] = params.skill_space_id

    if params.openviking_url:
        env["OPENVIKING_URL"] = params.openviking_url
        if params.openviking_resource_id:
            env["OPENVIKING_RESOURCE_ID"] = params.openviking_resource_id
        if params.openviking_api_key:
            env["OPENVIKING_API_KEY"] = params.openviking_api_key

    if params.feishu_app_id and params.feishu_app_secret:
        env["FEISHU_APP_ID"] = params.feishu_app_id
        env["FEISHU_APP_SECRET"] = params.feishu_app_secret

    # Public endpoint is authoritative; expose it for integrations that read it.
    env["A2A_PUBLIC_URL"] = public_endpoint

    # Caller-supplied overrides win last.
    env.update({k: str(v) for k, v in params.extra_env.items()})
    return env


def redact_env_for_display(env: dict[str, str]) -> dict[str, str]:
    """Return a copy of env with secret values masked for dry-run output."""
    return {
        key: (mask_secret(value) if key in SECRET_ENV_KEYS else value)
        for key, value in env.items()
    }
