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

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from click.testing import CliRunner
from typing_extensions import Self
from volcenginesdkcore.interceptor.interceptors.build_request_interceptor import (
    sanitize_for_serialization,
)
from volcenginesdkcore.rest import ApiException

from veadk.cli.cli_frontend import (
    _StudioOpenApiRateLimiter,
    _resolve_studio_cloud_credentials,
    _resolve_studio_identity_region,
    studio,
)
from veadk.cli.studio_telemetry import (
    studio_apmplus_environment_from_options,
)
from veadk.config import veadk_environments
from veadk.consts import (
    STUDIO_APMPLUS_DOMAIN,
    STUDIO_APMPLUS_ENV,
)
from veadk.integrations.ve_identity.identity_client import IdentityClient


def test_studio_openapi_rate_limiter_spaces_requests_evenly() -> None:
    now = 10.0
    waits: list[float] = []

    def _clock() -> float:
        return now

    def _sleep(delay: float) -> None:
        nonlocal now
        waits.append(delay)
        now += delay

    limiter = _StudioOpenApiRateLimiter(
        3,
        clock=_clock,
        sleeper=_sleep,
    )

    for _ in range(5):
        limiter.wait()

    assert waits == pytest.approx([1 / 3, 1 / 3, 1 / 3, 1 / 3])


@pytest.fixture(autouse=True)
def _skip_serverless_role_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOLCENGINE_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("VOLC_SESSIONTOKEN", raising=False)
    monkeypatch.delenv("SANDBOX_CHAT_CODEX", raising=False)
    monkeypatch.delenv("SANDBOX_CHAT_CODEX_SNAPSHOT", raising=False)
    monkeypatch.delenv("SANDBOX_CHAT_OPENCLAW", raising=False)
    monkeypatch.delenv("SANDBOX_CHAT_OPENCLAW_SNAPSHOT", raising=False)
    monkeypatch.delenv("SANDBOX_CHAT_HERMES", raising=False)
    monkeypatch.delenv("SANDBOX_CHAT_HERMES_SNAPSHOT", raising=False)
    monkeypatch.delenv("SANDBOX_SKILL_CREATOR", raising=False)
    monkeypatch.setattr(
        "veadk.cli.studio_deploy_serverless_iam.ensure_serverless_application_role",
        lambda *_, **__: None,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_code_env_tool",
        lambda **kwargs: f"auto-{kwargs['name']}",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_agent_tool",
        lambda **kwargs: f"auto-{kwargs['name']}",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_tool_snapshot",
        lambda **kwargs: str(kwargs["tool_id"]),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_agent_model_credential",
        lambda **_: None,
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_creator.ensure_skill_creator_model_credential",
        lambda **_: None,
    )


def test_studio_credentials_prefer_inline_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    credentials_path = tmp_path / "credentials"
    credentials_path.write_text(
        "[default]\naccess_key_id=file-ak\nsecret_access_key=file-sk\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "env-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "env-sk")
    monkeypatch.setenv("VOLCENGINE_SESSION_TOKEN", "env-token")

    credentials = _resolve_studio_cloud_credentials(
        None,
        None,
        credentials_path,
    )

    assert credentials == ("env-ak", "env-sk", "env-token")


def test_studio_credentials_fall_back_to_volc_default_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    credentials_path = tmp_path / "credentials"
    credentials_path.write_text(
        "[default]\naccess_key_id=file-ak\nsecret_access_key=file-sk\n"
        "session_token=file-token\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY", raising=False)

    credentials = _resolve_studio_cloud_credentials(
        None,
        None,
        credentials_path,
    )

    assert credentials == ("file-ak", "file-sk", "file-token")


def test_studio_credentials_support_long_term_keys_without_session_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "env-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "env-sk")

    credentials = _resolve_studio_cloud_credentials(
        None,
        None,
        tmp_path / "missing-credentials",
    )

    assert credentials == ("env-ak", "env-sk", "")


@pytest.mark.parametrize(
    ("stage", "expected_prefix"),
    [
        ("tool", "Failed to provision the AgentKit Codex temporary Tool"),
        (
            "credential",
            "Failed to provision the AgentKit Codex temporary model credential",
        ),
    ],
)
def test_studio_deploy_surfaces_redacted_provisioning_error_chain(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    expected_prefix: str,
) -> None:
    access_key = uuid4().hex
    bearer_value = uuid4().hex
    model_key = uuid4().hex
    secret_key = uuid4().hex

    def _fail(**_: object) -> str:
        try:
            raise ValueError(f"Authorization: Bearer {bearer_value}")
        except ValueError as cause:
            raise RuntimeError(
                "CreateApiKeyCredentialProvider: AccessDenied\n"
                f"Request: api_key={model_key}\n"
                f"RequestId=req-123 {access_key}"
            ) from cause

    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_studio_identity_region",
        lambda **kwargs: kwargs["deployment_region"],
    )
    if stage == "tool":
        monkeypatch.setattr(
            "veadk.cli.studio_sandbox_tools.ensure_studio_code_env_tool",
            _fail,
        )
        tool_args: list[str] = []
    else:
        monkeypatch.setattr(
            "veadk.cli.frontend_skill_creator.ensure_skill_creator_model_credential",
            _fail,
        )
        tool_args = [
            "--sandbox-chat-codex-tool-id",
            "chat-tool-id",
            "--sandbox-chat-codex-snapshot-tool-id",
            "chat-snapshot-tool-id",
            "--sandbox-skill-creator-tool-id",
            "skill-tool-id",
        ]

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--user-pool-id",
            "pool-id",
            "--allowed-client-id",
            "client-id",
            "--vefaas-app-name",
            "studio-app",
            "--iam-role",
            "trn:iam::role/test",
            "--gateway-name",
            "gateway",
            "--volcengine-access-key",
            access_key,
            "--volcengine-secret-key",
            secret_key,
            *tool_args,
        ],
    )

    assert result.exit_code == 1
    assert expected_prefix in result.output
    assert (
        "Underlying error:\nCreateApiKeyCredentialProvider: AccessDenied"
        in result.output
    )
    assert "Request: api_key=***" in result.output
    assert "RequestId=req-123" in result.output
    assert "Caused by:\nAuthorization: Bearer ***" in result.output
    assert access_key not in result.output
    assert bearer_value not in result.output
    assert model_key not in result.output
    assert secret_key not in result.output
    assert "***" in result.output


@pytest.mark.parametrize(
    (
        "target_args",
        "expected_region",
        "expected_identity_region",
        "expected_project",
        "expected_update_bucket",
        "update_bucket_env",
    ),
    [
        ([], "cn-beijing", "cn-beijing", "default", "veadk-studio", None),
        (
            [
                "--region",
                "cn-shanghai",
                "--project",
                "studio-project",
                "--studio-update-bucket",
                "custom-studio-releases",
            ],
            "cn-shanghai",
            "cn-beijing",
            "studio-project",
            "custom-studio-releases",
            "environment-studio-releases",
        ),
        (
            [],
            "cn-beijing",
            "cn-beijing",
            "default",
            "environment-studio-releases",
            "environment-studio-releases",
        ),
    ],
)
def test_studio_deploy_passes_region_and_project_to_cloud_engine(
    monkeypatch: pytest.MonkeyPatch,
    target_args: list[str],
    expected_region: str,
    expected_identity_region: str,
    expected_project: str,
    expected_update_bucket: str,
    update_bucket_env: str | None,
) -> None:
    captured: dict[str, object] = {}
    credential_tool_ids: list[str] = []

    if update_bucket_env is None:
        monkeypatch.delenv("VEADK_STUDIO_UPDATE_BUCKET", raising=False)
    else:
        monkeypatch.setenv("VEADK_STUDIO_UPDATE_BUCKET", update_bucket_env)

    class _FakeCloudAgentEngine:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def deploy(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                vefaas_endpoint="https://studio.example.com",
                vefaas_application_id="app-id",
                vefaas_function_id="",
            )

    class _FakeIdentityClient:
        def __init__(self, **kwargs: object) -> None:
            captured["identity_client"] = kwargs

        def register_callback_for_user_pool_client(self, **kwargs: object) -> None:
            captured["callback"] = kwargs

    monkeypatch.setattr(
        "veadk.cloud.cloud_agent_engine.CloudAgentEngine", _FakeCloudAgentEngine
    )
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_studio_identity_region",
        lambda **_: expected_identity_region,
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_identity.identity_client.IdentityClient",
        _FakeIdentityClient,
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_creator.ensure_skill_creator_model_credential",
        lambda **kwargs: credential_tool_ids.append(str(kwargs["tool_id"])),
    )

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--user-pool-id",
            "pool-id",
            "--allowed-client-id",
            "client-id",
            "--vefaas-app-name",
            "studio-app",
            "--sandbox-chat-codex-tool-id",
            "chat-code-env-id",
            "--sandbox-chat-codex-snapshot-tool-id",
            "chat-snapshot-code-env-id",
            "--sandbox-chat-openclaw-tool-id",
            "openclaw-tool-id",
            "--sandbox-chat-openclaw-snapshot-tool-id",
            "openclaw-snapshot-tool-id",
            "--sandbox-chat-hermes-tool-id",
            "hermes-tool-id",
            "--sandbox-chat-hermes-snapshot-tool-id",
            "hermes-snapshot-tool-id",
            "--sandbox-skill-creator-tool-id",
            "skill-code-env-id",
            "--iam-role",
            "trn:iam::role/test",
            "--gateway-name",
            "gateway",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
            "--volcengine-session-token",
            "sts-token",
            *target_args,
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["region"] == expected_region
    assert captured["project"] == expected_project
    assert captured["volcengine_session_token"] == "sts-token"
    assert captured["identity_client"] == {
        "access_key": "ak",
        "secret_key": "sk",
        "session_token": "sts-token",
        "region": expected_identity_region,
    }
    assert veadk_environments["VEIDENTITY_REGION"] == expected_identity_region
    assert "VEADK_STUDIO_ADMINS" not in veadk_environments
    assert "VEADK_STUDIO_DEVELOPERS" not in veadk_environments
    assert veadk_environments["SANDBOX_CHAT_CODEX"] == "chat-code-env-id"
    assert (
        veadk_environments["SANDBOX_CHAT_CODEX_SNAPSHOT"] == "chat-snapshot-code-env-id"
    )
    assert veadk_environments["SANDBOX_CHAT_OPENCLAW"] == "openclaw-tool-id"
    assert (
        veadk_environments["SANDBOX_CHAT_OPENCLAW_SNAPSHOT"]
        == "openclaw-snapshot-tool-id"
    )
    assert veadk_environments["SANDBOX_CHAT_HERMES"] == "hermes-tool-id"
    assert (
        veadk_environments["SANDBOX_CHAT_HERMES_SNAPSHOT"] == "hermes-snapshot-tool-id"
    )
    assert veadk_environments["SANDBOX_SKILL_CREATOR"] == "skill-code-env-id"
    assert veadk_environments["AGENTKIT_SANDBOX_REGION"] == expected_region
    assert veadk_environments["VEADK_STUDIO_UPDATE_BUCKET"] == expected_update_bucket
    assert veadk_environments["VEADK_STUDIO_UPDATE_PREFIX"] == "veadk/studio/main"
    assert veadk_environments["VEADK_STUDIO_DEPLOY_REGION"] == expected_region
    assert veadk_environments["VEADK_STUDIO_PROJECT"] == expected_project
    assert "VEADK_STUDIO_UPDATE_REGION" not in veadk_environments
    assert sorted(credential_tool_ids) == [
        "chat-code-env-id",
        "chat-snapshot-code-env-id",
        "skill-code-env-id",
    ]
    assert f"{expected_region}/{expected_project}" in result.output
    assert ("Warning:" in result.output) == (
        expected_identity_region != expected_region
    )
    callback = captured["callback"]
    assert isinstance(callback, dict)
    assert callback["dismiss_login_page_enabled"] is False
    assert callback["skip_consent_enabled"] is True


def test_studio_deploy_persists_telemetry_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeVefaasService:
        def update_function_envs_and_release(
            self,
            function_id: str,
            environment: dict[str, str],
        ) -> None:
            captured["release_function_id"] = function_id
            captured["release_environment"] = environment

    class _FakeCloudAgentEngine:
        def __init__(self, **_: object) -> None:
            self._vefaas_service = _FakeVefaasService()

        def deploy(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(
                vefaas_endpoint="https://studio.example.com",
                vefaas_application_id="app-id",
                vefaas_function_id="function-id",
            )

    monkeypatch.setattr(
        "veadk.cloud.cloud_agent_engine.CloudAgentEngine", _FakeCloudAgentEngine
    )
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_studio_identity_region",
        lambda **_: "cn-beijing",
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_identity.identity_client.IdentityClient.register_callback_for_user_pool_client",
        lambda *_args, **_kwargs: None,
    )
    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--user-pool-id",
            "pool-id",
            "--allowed-client-id",
            "client-id",
            "--vefaas-app-name",
            "studio-app",
            "--sandbox-chat-codex-tool-id",
            "chat-code-env-id",
            "--sandbox-chat-openclaw-tool-id",
            "openclaw-tool-id",
            "--sandbox-chat-hermes-tool-id",
            "hermes-tool-id",
            "--sandbox-skill-creator-tool-id",
            "skill-code-env-id",
            "--iam-role",
            "trn:iam::role/test",
            "--gateway-name",
            "gateway",
            "--volcengine-access-key",
            "ak-for-deployer",
            "--volcengine-secret-key",
            "sk-for-deployer",
            "--apmplus-aid",
            "12345",
            "--apmplus-token",
            "client-token",
            "--apmplus-domain",
            "apmplus.example.com",
            "--apmplus-env",
            "test",
        ],
    )

    assert result.exit_code == 0, result.output
    deploy_id = veadk_environments["VEADK_STUDIO_DEPLOY_ID"]
    assert deploy_id.startswith("stddep_")
    assert veadk_environments["VEADK_STUDIO_USER_POOL_ID"] == "pool-id"
    assert veadk_environments["VEADK_STUDIO_DEPLOY_REGION"] == "cn-beijing"
    assert veadk_environments["VEADK_STUDIO_APMPLUS_AID"] == "12345"
    assert veadk_environments["VEADK_STUDIO_APMPLUS_TOKEN"] == "client-token"
    assert veadk_environments["VEADK_STUDIO_APMPLUS_DOMAIN"] == ("apmplus.example.com")
    assert veadk_environments["VEADK_STUDIO_APMPLUS_ENV"] == "test"

    assert captured["release_function_id"] == "function-id"
    release_environment = captured["release_environment"]
    assert isinstance(release_environment, dict)
    assert release_environment["OAUTH2_REDIRECT_URI"] == (
        "https://studio.example.com/oauth2/callback"
    )
    assert release_environment["VEADK_STUDIO_DEPLOY_ID"] == deploy_id
    assert release_environment["VEADK_STUDIO_USER_POOL_ID"] == "pool-id"
    assert release_environment["VEADK_STUDIO_APMPLUS_AID"] == "12345"
    assert release_environment["VEADK_STUDIO_APPLICATION_ID"] == "app-id"
    assert release_environment["VEADK_STUDIO_FUNCTION_ID"] == "function-id"


def test_studio_apmplus_options_are_empty_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_AID", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_TOKEN", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_DOMAIN", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_ENV", raising=False)

    values = studio_apmplus_environment_from_options(
        apmplus_aid="",
        apmplus_token="",
        apmplus_domain="",
        apmplus_env="",
    )

    assert values == {}


def test_studio_apmplus_options_require_aid_with_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_AID", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_TOKEN", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_DOMAIN", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_ENV", raising=False)

    with pytest.raises(Exception, match="requires both --apmplus-aid"):
        studio_apmplus_environment_from_options(
            apmplus_aid="",
            apmplus_token="client-token",
            apmplus_domain="",
            apmplus_env="",
        )


def test_studio_apmplus_options_use_fixed_domain_and_production_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_AID", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_TOKEN", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_DOMAIN", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_APMPLUS_ENV", raising=False)

    values = studio_apmplus_environment_from_options(
        apmplus_aid="12345",
        apmplus_token="client-token",
        apmplus_domain="",
        apmplus_env="",
    )

    assert values == {
        "VEADK_STUDIO_APMPLUS_AID": "12345",
        "VEADK_STUDIO_APMPLUS_TOKEN": "client-token",
        "VEADK_STUDIO_APMPLUS_DOMAIN": STUDIO_APMPLUS_DOMAIN,
        "VEADK_STUDIO_APMPLUS_ENV": STUDIO_APMPLUS_ENV,
    }


def test_studio_deploy_creates_distinct_sandbox_tools_when_ids_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_CHAT_CODEX", raising=False)
    monkeypatch.delenv("SANDBOX_CHAT_OPENCLAW", raising=False)
    monkeypatch.delenv("SANDBOX_CHAT_HERMES", raising=False)
    monkeypatch.delenv("SANDBOX_SKILL_CREATOR", raising=False)
    created_kinds: list[str] = []
    credential_tool_ids: list[str] = []
    agent_tool_kinds: list[str] = []
    agent_credential_kinds: list[str] = []
    snapshot_tool_ids: list[str] = []
    tool_mutation_slots: list[None] = []
    creation_barrier = threading.Barrier(7)
    created_kinds_lock = threading.Lock()

    class _FakeCloudAgentEngine:
        def __init__(self, **_: object) -> None:
            pass

        def deploy(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(
                vefaas_endpoint="",
                vefaas_application_id="app-id",
                vefaas_function_id="",
            )

    def _ensure_tool(**kwargs: object) -> str:
        name = str(kwargs["name"])
        if "-chat-snapshot-" in name:
            kind = "codex_snapshot"
        elif "-chat-temporary-" in name:
            kind = "codex"
        else:
            kind = "skill_creator"
        before_mutation = kwargs["before_mutation"]
        assert callable(before_mutation)
        before_mutation()
        creation_barrier.wait(timeout=5)
        with created_kinds_lock:
            created_kinds.append(kind)
        return {
            "codex": "chat-tool",
            "codex_snapshot": "chat-snapshot-tool",
            "skill_creator": "skill-tool",
        }[kind]

    def _ensure_agent_tool(**kwargs: object) -> str:
        base_kind = str(kwargs["kind"])
        kind = f"{base_kind}_snapshot" if kwargs["enable_snapshot"] else base_kind
        before_mutation = kwargs["before_mutation"]
        assert callable(before_mutation)
        before_mutation()
        creation_barrier.wait(timeout=5)
        with created_kinds_lock:
            created_kinds.append(kind)
        agent_tool_kinds.append(base_kind)
        return f"{kind}-tool"

    def _ensure_code_credential(**kwargs: object) -> None:
        assert len(created_kinds) == 7
        before_update = kwargs["before_update"]
        assert callable(before_update)
        before_update()
        credential_tool_ids.append(str(kwargs["tool_id"]))

    def _ensure_agent_credential(**kwargs: object) -> None:
        assert len(created_kinds) == 7
        before_update = kwargs["before_update"]
        assert callable(before_update)
        before_update()
        agent_credential_kinds.append(str(kwargs["kind"]))

    def _ensure_snapshot(**kwargs: object) -> str:
        assert len(created_kinds) == 7
        assert callable(kwargs["before_mutation"])
        tool_id = str(kwargs["tool_id"])
        snapshot_tool_ids.append(tool_id)
        return tool_id

    monkeypatch.setattr(
        "veadk.cloud.cloud_agent_engine.CloudAgentEngine", _FakeCloudAgentEngine
    )
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_studio_identity_region",
        lambda **_: "cn-beijing",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_code_env_tool", _ensure_tool
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_agent_tool",
        _ensure_agent_tool,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_agent_model_credential",
        _ensure_agent_credential,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_tool_snapshot",
        _ensure_snapshot,
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_creator.ensure_skill_creator_model_credential",
        _ensure_code_credential,
    )

    class _FakeRateLimiter:
        def __init__(self, requests_per_second: float) -> None:
            assert requests_per_second == 3

        def wait(self) -> None:
            tool_mutation_slots.append(None)

    monkeypatch.setattr(
        "veadk.cli.cli_frontend._StudioOpenApiRateLimiter",
        _FakeRateLimiter,
    )

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--user-pool-id",
            "pool-id",
            "--allowed-client-id",
            "client-id",
            "--vefaas-app-name",
            "studio-app",
            "--iam-role",
            "trn:iam::role/test",
            "--gateway-name",
            "gateway",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
        ],
    )

    assert result.exit_code == 0, result.output
    assert sorted(created_kinds) == [
        "codex",
        "codex_snapshot",
        "hermes",
        "hermes_snapshot",
        "openclaw",
        "openclaw_snapshot",
        "skill_creator",
    ]
    assert veadk_environments["SANDBOX_CHAT_CODEX"] == "chat-tool"
    assert veadk_environments["SANDBOX_CHAT_CODEX_SNAPSHOT"] == "chat-snapshot-tool"
    assert veadk_environments["SANDBOX_SKILL_CREATOR"] == "skill-tool"
    assert sorted(credential_tool_ids) == [
        "chat-snapshot-tool",
        "chat-tool",
        "skill-tool",
    ]
    assert len(tool_mutation_slots) == 14
    assert sorted(agent_tool_kinds) == ["hermes", "hermes", "openclaw", "openclaw"]
    assert sorted(agent_credential_kinds) == [
        "hermes",
        "hermes",
        "openclaw",
        "openclaw",
    ]
    assert sorted(snapshot_tool_ids) == [
        "chat-snapshot-tool",
        "hermes_snapshot-tool",
        "openclaw_snapshot-tool",
    ]
    assert veadk_environments["SANDBOX_CHAT_OPENCLAW"] == "openclaw-tool"
    assert (
        veadk_environments["SANDBOX_CHAT_OPENCLAW_SNAPSHOT"] == "openclaw_snapshot-tool"
    )
    assert veadk_environments["SANDBOX_CHAT_HERMES"] == "hermes-tool"
    assert veadk_environments["SANDBOX_CHAT_HERMES_SNAPSHOT"] == "hermes_snapshot-tool"
    for label in (
        "Codex temporary",
        "Codex recoverable",
        "Skill Creator",
        "OpenClaw temporary",
        "OpenClaw recoverable",
        "Hermes temporary",
        "Hermes recoverable",
    ):
        assert f"Creating AgentKit {label} Tool" in result.output
        assert f"AgentKit {label} Tool is ready." in result.output
        assert f"Creating AgentKit {label} model credential" in result.output
        assert f"AgentKit {label} model credential is ready." in result.output


@pytest.mark.parametrize(
    ("role_args", "expected_environment"),
    [
        (
            ["--admin", "admin@example.com"],
            {"VEADK_STUDIO_ADMINS": "admin@example.com"},
        ),
        (
            ["--developer", "dev@example.com"],
            {"VEADK_STUDIO_DEVELOPERS": "dev@example.com"},
        ),
    ],
)
def test_studio_deploy_enables_rbac_when_either_role_is_configured(
    monkeypatch: pytest.MonkeyPatch,
    role_args: list[str],
    expected_environment: dict[str, str],
) -> None:
    class _FakeCloudAgentEngine:
        def __init__(self, **_: object) -> None:
            pass

        def deploy(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(
                vefaas_endpoint="https://studio.example.com",
                vefaas_application_id="app-id",
                vefaas_function_id="",
            )

    monkeypatch.setattr(
        "veadk.cloud.cloud_agent_engine.CloudAgentEngine", _FakeCloudAgentEngine
    )
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_studio_identity_region",
        lambda **_: "cn-beijing",
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_identity.identity_client.IdentityClient.register_callback_for_user_pool_client",
        lambda *_args, **_kwargs: None,
    )

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--user-pool-id",
            "pool-id",
            "--allowed-client-id",
            "client-id",
            "--vefaas-app-name",
            "studio-app",
            "--iam-role",
            "trn:iam::role/test",
            "--gateway-name",
            "gateway",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
            *role_args,
        ],
    )

    assert result.exit_code == 0, result.output
    configured_roles = {
        key: value
        for key, value in veadk_environments.items()
        if key in {"VEADK_STUDIO_ADMINS", "VEADK_STUDIO_DEVELOPERS"}
    }
    assert configured_roles == expected_environment


def test_studio_identity_region_searches_deployment_region_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_regions: list[str] = []
    checked_tokens: list[str] = []

    class _FakeIdentityClient:
        def __init__(self, **kwargs: str) -> None:
            self.region = kwargs["region"]
            checked_tokens.append(kwargs["session_token"])

        def user_pool_client_exists(self, **_: str) -> bool:
            checked_regions.append(self.region)
            return self.region == "cn-beijing"

    monkeypatch.setattr(
        "veadk.integrations.ve_identity.identity_client.IdentityClient",
        _FakeIdentityClient,
    )

    resolved = _resolve_studio_identity_region(
        access_key="ak",
        secret_key="sk",
        user_pool_id="pool-id",
        client_id="client-id",
        deployment_region="cn-shanghai",
        session_token="sts-token",
    )

    assert resolved == "cn-beijing"
    assert checked_regions == ["cn-shanghai", "cn-beijing"]
    assert checked_tokens == ["sts-token", "sts-token"]


def test_identity_client_preserves_external_sts_token() -> None:
    identity_client = IdentityClient(
        access_key="test_access_key",
        secret_key="test_secret_key",
        session_token="sts-token",
    )
    identity_client._api_client.get_user_pool_client = Mock(return_value=object())

    assert identity_client.user_pool_client_exists("pool-id", "client-id")
    assert not identity_client._is_sts_credential_expired()
    assert (
        identity_client._api_client.api_client.configuration.session_token
        == "sts-token"
    )


def test_identity_client_lists_all_user_pool_pages() -> None:
    identity_client = IdentityClient(
        access_key="test_access_key",
        secret_key="test_secret_key",
    )
    identity_client._api_client = Mock()
    identity_client._api_client.list_user_pools.side_effect = [
        SimpleNamespace(
            data=[
                SimpleNamespace(
                    uid="pool-1", name="Studio", domain="studio.example.com"
                ),
                SimpleNamespace(
                    uid="pool-2", name="Customers", domain="users.example.com"
                ),
            ],
            total_count=3,
        ),
        SimpleNamespace(
            data=[
                SimpleNamespace(
                    uid="pool-3", name="Partners", domain="partners.example.com"
                ),
            ],
            total_count=3,
        ),
    ]

    pools = identity_client.list_user_pools(page_size=2)

    assert pools == [
        {"uid": "pool-1", "name": "Studio", "domain": "studio.example.com"},
        {"uid": "pool-2", "name": "Customers", "domain": "users.example.com"},
        {"uid": "pool-3", "name": "Partners", "domain": "partners.example.com"},
    ]
    requests = [
        call.args[0]
        for call in identity_client._api_client.list_user_pools.call_args_list
    ]
    assert [(request.page_number, request.page_size) for request in requests] == [
        (1, 2),
        (2, 2),
    ]


def test_identity_client_refreshes_known_sts_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity_client = IdentityClient(
        access_key="test_access_key",
        secret_key="test_secret_key",
    )
    monkeypatch.setattr("time.time", lambda: 1_000)

    identity_client._sts_credential_expires_at = 1_301
    assert not identity_client._is_sts_credential_expired()

    identity_client._sts_credential_expires_at = 1_300
    assert identity_client._is_sts_credential_expired()


def test_identity_region_probe_only_swallows_not_found() -> None:
    identity_client = IdentityClient(
        access_key="test_access_key",
        secret_key="test_secret_key",
    )
    identity_client._api_client = Mock()
    identity_client._api_client.get_user_pool_client.side_effect = ApiException(
        status=404,
        reason="Not Found",
    )

    assert not identity_client.user_pool_client_exists("pool-id", "client-id")

    identity_client._api_client.get_user_pool_client.side_effect = ApiException(
        status=403,
        reason="Forbidden",
    )
    with pytest.raises(ApiException):
        identity_client.user_pool_client_exists("pool-id", "client-id")


@pytest.mark.parametrize(
    ("switches", "expected_switches"),
    [
        ({}, {}),
        (
            {
                "dismiss_login_page_enabled": False,
                "skip_consent_enabled": True,
            },
            {
                "DismissLoginPageEnabled": False,
                "SkipConsentEnabled": True,
            },
        ),
    ],
)
def test_register_callback_only_sends_requested_login_switches(
    switches: dict[str, bool],
    expected_switches: dict[str, bool],
) -> None:
    identity_client = IdentityClient(
        access_key="test_access_key",
        secret_key="test_secret_key",
    )
    identity_client._api_client = Mock()
    identity_client._api_client.get_user_pool_client.return_value = SimpleNamespace(
        allowed_callback_urls=["https://existing.example.com/oauth2/callback"],
        allowed_web_origins=["https://existing.example.com"],
        name="studio-client",
        description=None,
        allowed_logout_urls=None,
        allowed_cors=None,
        id_token=None,
        refresh_token=None,
    )

    identity_client.register_callback_for_user_pool_client(
        user_pool_uid="pool-id",
        client_uid="client-id",
        callback_url="https://studio.example.com/oauth2/callback",
        web_origin="https://studio.example.com",
        **switches,
    )

    update_request = identity_client._api_client.update_user_pool_client.call_args.args[
        0
    ]
    assert update_request.user_pool_uid == "pool-id"
    assert update_request.client_uid == "client-id"
    assert update_request.allowed_callback_urls == [
        "https://existing.example.com/oauth2/callback",
        "https://studio.example.com/oauth2/callback",
    ]
    assert update_request.allowed_web_origins == [
        "https://existing.example.com",
        "https://studio.example.com",
    ]
    serialized_request = sanitize_for_serialization(update_request)
    for key in ("DismissLoginPageEnabled", "SkipConsentEnabled"):
        assert (key in serialized_request) == (key in expected_switches)
    assert {
        key: serialized_request[key] for key in expected_switches
    } == expected_switches


def test_studio_deploy_rejects_unsupported_region() -> None:
    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--user-pool-id",
            "pool-id",
            "--allowed-client-id",
            "client-id",
            "--vefaas-app-name",
            "studio-app",
            "--region",
            "cn-guangzhou",
        ],
    )

    assert result.exit_code == 2
    assert "Invalid value for '--region'" in result.output


def test_studio_deploy_from_source_bundles_unmirrored_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class _FakeCloudAgentEngine:
        def __init__(self, **_: object) -> None:
            pass

        def deploy(self, **kwargs: object) -> SimpleNamespace:
            deploy_path = Path(str(kwargs["path"]))
            captured["requirements"] = (deploy_path / "requirements.txt").read_text()
            return SimpleNamespace(
                vefaas_endpoint="",
                vefaas_application_id="app-id",
                vefaas_function_id="",
            )

    def _fake_build(command: list[str], check: bool) -> None:
        assert check is True
        output_dir = Path(command[-1])
        (output_dir / "veadk_python-test-py3-none-any.whl").write_bytes(b"wheel")

    class _FakeWheelResponse:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def read(self) -> bytes:
            return b"dependency-wheel"

    monkeypatch.setattr(
        "veadk.cloud.cloud_agent_engine.CloudAgentEngine", _FakeCloudAgentEngine
    )
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_studio_identity_region",
        lambda **kwargs: kwargs["deployment_region"],
    )
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr("subprocess.run", _fake_build)
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_args, **_kwargs: _FakeWheelResponse()
    )
    wheel_hashes = iter(
        [
            "3e89f6c9f5fb17cb70aaaa37df21a6e01722ccb1eec6cb8fc2e61417016986d4",
            "3a74fa7a7baa5d5f604b175f967660cd0aa4c7057ce44d98c4041fbaf7944b5b",
            "369cc9fc8cc10cb24143873a0d95438bb8ee257bb80c71989e3ee290e8d72c67",
            "1e9f23332b1b687dd7f272e660953992de60ad3e9d07d62f7460fd4aedb99616",
        ]
    )
    monkeypatch.setattr(
        "hashlib.sha256",
        lambda _: SimpleNamespace(hexdigest=lambda: next(wheel_hashes)),
    )

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--user-pool-id",
            "pool-id",
            "--allowed-client-id",
            "client-id",
            "--vefaas-app-name",
            "studio-app",
            "--iam-role",
            "trn:iam::role/test",
            "--gateway-name",
            "gateway",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
            "--from-source",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["requirements"] == (
        "./trustedmcp-0.0.5-py3-none-any.whl\n"
        "./volcengine_python_sdk-5.0.36-py2.py3-none-any.whl\n"
        "./tokenizers-0.22.2-cp39-abi3-manylinux_2_17_x86_64."
        "manylinux2014_x86_64.whl\n"
        "./openviking_sdk-0.1.4-py3-none-any.whl\n"
        "./veadk_python-test-py3-none-any.whl\n"
    )
