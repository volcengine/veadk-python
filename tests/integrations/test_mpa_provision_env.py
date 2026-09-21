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

"""Tests for mpa-agent runtime env assembly (FR-5/FR-10/FR-11, VC-10)."""

import pytest

from veadk.integrations.mpa.mpa_provision import (
    SECRET_ENV_KEYS,
    MpaProvisionParams,
    build_runtime_env,
    derive_claw_space_id,
    generate_mpa_agent_id,
    mask_secret,
    tool_name_for_agent,
    validate_mpa_agent_id,
    workload_identity_name,
)


def _params(**overrides) -> MpaProvisionParams:
    base = dict(
        image="registry.example.com/mpa:latest",
        registry_name="registry",
        mpa_agent_id="mi-abc123def456",
        account_id="2100000001",
        region="cn-beijing",
        pg_host="pg.example.com",
        pg_port="5432",
        pg_database="mpa",
        pg_user="mpauser",
        pg_password="pg-secret",
        model_provider="openai",
        model_api_base="https://ark.example.com/api/v3/",
        model_api_key="model-secret",
        model_name="doubao-seed",
        agentkit_tool_id="tool-1",
    )
    base.update(overrides)
    return MpaProvisionParams(**base)


def test_derive_claw_space_id_from_account() -> None:
    """FR-10: CLAW_SPACE_ID defaults to csi-<account_id> when not supplied."""
    assert derive_claw_space_id(None, account_id="2100000001") == "csi-2100000001"
    assert derive_claw_space_id("", account_id="2100000001") == "csi-2100000001"
    # Explicit value wins.
    assert derive_claw_space_id("csi-custom", account_id="2100") == "csi-custom"


def test_generate_mpa_agent_id_is_valid_and_unique() -> None:
    """FR-12: generated ids follow arkclaw's fixed lowercase-alnum shape."""
    generated = {generate_mpa_agent_id() for _ in range(100)}
    assert len(generated) == 100
    for agent_id in generated:
        assert len(agent_id) == len("mi-") + 12
        assert agent_id.startswith("mi-")
        assert agent_id[3:].isalnum()
        assert agent_id[3:] == agent_id[3:].lower()


def test_validate_mpa_agent_id_requires_canonical_shape() -> None:
    assert validate_mpa_agent_id(" mi-abc123def456 ") == "mi-abc123def456"
    for value in ("mi-short", "mi-ABC123DEF456", "agent-abc123def456", ""):
        with pytest.raises(ValueError, match="mi-"):
            validate_mpa_agent_id(value)


def test_workload_identity_name_keeps_base_agent_id() -> None:
    assert workload_identity_name("mi-abc123def456") == "mi-abc123def456-studio"


def test_tool_name_is_derived_from_agent_id() -> None:
    """FR-13: each agent's default Tool name follows the observed convention."""
    assert tool_name_for_agent("mi-ab12cd34ef56") == "mi_ab12cd34ef56"


def test_env_contains_startup_keys_and_identity_adaptation() -> None:
    """VC-10: env carries all startup keys, identity disabled, space derived."""
    env = build_runtime_env(_params(), public_endpoint="https://app.example.com")

    # Model
    assert env["MODEL_AGENT_PROVIDER"] == "openai"
    assert env["MODEL_AGENT_API_BASE"] == "https://ark.example.com/api/v3/"
    assert env["MODEL_AGENT_API_KEY"] == "model-secret"
    assert env["MODEL_AGENT_NAME"] == "doubao-seed"
    # mpa-agent's Codex setting defaults to the non-empty literal ``auto``,
    # which otherwise wins over MODEL_AGENT_NAME and makes worker requests use
    # a nonexistent model. Keep both execution paths on the CLI-selected model.
    assert env["MPA_CODEX_WORKER_DEFAULT_MODEL"] == "doubao-seed"
    # PostgreSQL session store
    assert env["MPA_SESSION_MEMORY_BACKEND"] == "postgresql"
    assert env["PGHOST"] == "pg.example.com"
    assert env["PGPORT"] == "5432"
    assert env["PGDATABASE"] == "mpa"
    assert env["PGUSER"] == "mpauser"
    assert env["PGPASSWORD"] == "pg-secret"
    # Identity adaptation (FR-10)
    assert env["IDENTITY_STARTUP_ENABLED"] == "false"
    # veadk has no arkclaw identity pools/TIP issuer; APIG key-auth remains the
    # outer access control for Studio and direct Runtime callers.
    assert env["A2A_TIP_VERIFY_ENABLED"] == "false"
    assert env["MPA_LAZY_LOGIN"] == "false"
    assert env["APPCENTER_RESOURCE_DISCOVERY_ENABLED"] == "false"
    assert env["IM_GATEWAY_STARTUP_ENABLED"] == "false"
    assert env["APMPLUS_TRACE_CONTENT"] == "false"
    assert env["FORCE_APMPLUS_EXPORTER_REGISTRATION"] == "true"
    assert env["CLAW_SPACE_ID"] == "csi-2100000001"
    assert env["MPA_AGENT_ID"] == "mi-abc123def456"
    assert env["MPA_WORKLOAD_POOL_NAME"] == "agentkit-studio-workload"
    assert env["MPA_WORKLOAD_IDENTITY_NAME"] == "mi-abc123def456-studio"
    # AgentKit
    assert env["AGENTKIT_TOOL_ID"] == "tool-1"


def test_env_uses_public_endpoint_for_codex_worker_preference() -> None:
    """FR-11: veadk scenario prefers the public endpoint for the Codex worker."""
    env = build_runtime_env(_params(), public_endpoint="https://app.example.com")
    assert env["MPA_CODEX_WORKER_ENDPOINT_PREFERENCE"] == "public"
    assert env["MPA_CODEX_WORKER_ALLOW_PUBLIC_FALLBACK"] == "true"


def test_env_advertises_default_and_additional_selectable_models() -> None:
    env = build_runtime_env(
        _params(selectable_models=("doubao-seed", "doubao-alt")),
        public_endpoint="https://app.example.com",
    )

    assert env["MPA_SELECTABLE_MODELS"] == "doubao-seed,doubao-alt"


def test_env_openviking_included_only_when_provided() -> None:
    """OpenViking keys appear only when a URL is supplied."""
    env_without = build_runtime_env(
        _params(), public_endpoint="https://app.example.com"
    )
    assert "OPENVIKING_URL" not in env_without

    env_with = build_runtime_env(
        _params(
            openviking_url="http://ov.example.com",
            openviking_resource_id="ov-1",
            openviking_api_key="ov-secret",
        ),
        public_endpoint="https://app.example.com",
    )
    assert env_with["OPENVIKING_URL"] == "http://ov.example.com"
    assert env_with["OPENVIKING_RESOURCE_ID"] == "ov-1"
    assert env_with["OPENVIKING_API_KEY"] == "ov-secret"


def test_env_feishu_included_only_when_provided() -> None:
    """Feishu credentials appear only when both id and secret are supplied."""
    env = build_runtime_env(
        _params(feishu_app_id="cli_x", feishu_app_secret="fs-secret"),
        public_endpoint="https://app.example.com",
    )
    assert env["FEISHU_APP_ID"] == "cli_x"
    assert env["FEISHU_APP_SECRET"] == "fs-secret"

    env_none = build_runtime_env(_params(), public_endpoint="https://app.example.com")
    assert "FEISHU_APP_ID" not in env_none
    assert "FEISHU_APP_SECRET" not in env_none


def test_mask_secret_hides_middle() -> None:
    """Secrets are masked for dry-run output (no plaintext leak)."""
    assert mask_secret("model-secret") not in {"model-secret"}
    assert mask_secret("model-secret").startswith("m")
    assert "*" in mask_secret("model-secret")
    assert mask_secret("") == ""
    # Very short secrets are fully masked.
    assert set(mask_secret("ab")) == {"*"}
    assert "CODEX_MCP_RUNTIME_API_KEY" in SECRET_ENV_KEYS


def test_runtime_jwt_default_and_explicit_override() -> None:
    env = build_runtime_env(_params(), public_endpoint="https://runtime.example.com")
    assert env["DISABLE_JWT_AUTH"] == "true"
    overrides = {"DISABLE_JWT_AUTH": "false"}
    env = build_runtime_env(
        _params(extra_env=overrides), public_endpoint="https://runtime.example.com"
    )
    assert env["DISABLE_JWT_AUTH"] == "false"
    assert overrides == {"DISABLE_JWT_AUTH": "false"}


def test_database_instrumentation_default_and_explicit_override() -> None:
    key = "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS"
    env = build_runtime_env(_params(), public_endpoint="https://app.example.com")
    assert env[key] == "sqlalchemy,asyncpg,psycopg,psycopg2,dbapi"
    for override in ("", "sqlalchemy"):
        env = build_runtime_env(
            _params(extra_env={key: override}),
            public_endpoint="https://app.example.com",
        )
        assert env[key] == override
        assert env["FORCE_APMPLUS_EXPORTER_REGISTRATION"] == "true"
