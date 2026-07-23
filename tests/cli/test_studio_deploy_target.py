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

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from click.testing import CliRunner
from volcenginesdkcore.rest import ApiException
from volcenginesdkcore.interceptor.interceptors.build_request_interceptor import (
    sanitize_for_serialization,
)

from veadk.cli.cli_frontend import _resolve_studio_identity_region, studio
from veadk.config import veadk_environments
from veadk.integrations.ve_identity.identity_client import IdentityClient


@pytest.fixture(autouse=True)
def _skip_serverless_role_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "veadk.cli.studio_deploy_serverless_iam.ensure_serverless_application_role",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_code_env_tool",
        lambda **kwargs: f"auto-{kwargs['name']}",
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_creator.ensure_skill_creator_model_credential",
        lambda **_: None,
    )


@pytest.mark.parametrize(
    ("stage", "expected_prefix"),
    [
        ("tool", "Failed to provision the AgentKit chat CodeEnv Tool"),
        (
            "relay",
            "Failed to provision the AgentKit chat model credential relay",
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
    ("target_args", "expected_region", "expected_identity_region", "expected_project"),
    [
        ([], "cn-beijing", "cn-beijing", "default"),
        (
            [
                "--region",
                "cn-shanghai",
                "--project",
                "studio-project",
            ],
            "cn-shanghai",
            "cn-beijing",
            "studio-project",
        ),
    ],
)
def test_studio_deploy_passes_region_and_project_to_cloud_engine(
    monkeypatch: pytest.MonkeyPatch,
    target_args: list[str],
    expected_region: str,
    expected_identity_region: str,
    expected_project: str,
) -> None:
    captured: dict[str, object] = {}
    credential_tool_ids: list[str] = []

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
        def __init__(self, **_: object) -> None:
            pass

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
            *target_args,
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["region"] == expected_region
    assert captured["project"] == expected_project
    assert veadk_environments["VEIDENTITY_REGION"] == expected_identity_region
    assert "VEADK_STUDIO_ADMINS" not in veadk_environments
    assert "VEADK_STUDIO_DEVELOPERS" not in veadk_environments
    assert veadk_environments["SANDBOX_CHAT_CODEX"] == "chat-code-env-id"
    assert veadk_environments["SANDBOX_SKILL_CREATOR"] == "skill-code-env-id"
    assert credential_tool_ids == [
        "chat-code-env-id",
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


def test_studio_deploy_creates_distinct_sandbox_tools_when_ids_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_names: list[str] = []
    credential_tool_ids: list[str] = []

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
        created_names.append(name)
        return f"tool-{len(created_names)}"

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
    assert len(created_names) == 2
    assert created_names[0] != created_names[1]
    assert "chat" in created_names[0]
    assert "skill" in created_names[1]
    assert veadk_environments["SANDBOX_CHAT_CODEX"] == "tool-1"
    assert veadk_environments["SANDBOX_SKILL_CREATOR"] == "tool-2"
    assert credential_tool_ids == ["tool-1", "tool-2"]


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

    class _FakeIdentityClient:
        def __init__(self, **kwargs: str) -> None:
            self.region = kwargs["region"]

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
    )

    assert resolved == "cn-beijing"
    assert checked_regions == ["cn-shanghai", "cn-beijing"]


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
        def __enter__(self) -> "_FakeWheelResponse":
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
