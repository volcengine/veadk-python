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

import importlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from click.testing import CliRunner

from veadk.cli.cli_frontend import studio
from veadk.cli.studio_deploy_serverless_iam import (
    CUSTOM_POLICY_NAME,
    ROLE_NAME,
    SYSTEM_POLICIES,
    ensure_serverless_application_role,
)


def _install_iam_service(monkeypatch: pytest.MonkeyPatch, service: MagicMock) -> None:
    iam_module = importlib.import_module("volcengine.iam.IamService")
    monkeypatch.setattr(iam_module, "IamService", lambda: service)


def _iam_error(code: str, message: str) -> Exception:
    return Exception(
        json.dumps({"ResponseMetadata": {"Error": {"Code": code, "Message": message}}})
    )


def test_existing_role_is_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    service.get_role.return_value = {"Result": {"Role": {"RoleName": ROLE_NAME}}}
    _install_iam_service(monkeypatch, service)

    created = ensure_serverless_application_role("ak", "sk")

    assert created is False
    service.get_policy.assert_not_called()
    service.create_policy.assert_not_called()
    service.create_role.assert_not_called()
    service.attach_role_policy.assert_not_called()


def test_missing_role_is_created_with_all_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.get_role.side_effect = _iam_error("RoleNotExist", "role not found")
    service.get_policy.side_effect = _iam_error("PolicyNotExist", "policy not found")
    service.create_policy.return_value = {"Result": {}}
    service.create_role.return_value = {"Result": {"Role": {"RoleName": ROLE_NAME}}}
    service.attach_role_policy.return_value = {"Result": {}}
    _install_iam_service(monkeypatch, service)

    role_module = importlib.import_module("veadk.cli.studio_deploy_serverless_iam")
    warning = MagicMock()
    monkeypatch.setattr(role_module.click, "secho", warning)

    created = ensure_serverless_application_role("ak", "sk")

    assert created is True
    warning.assert_called_once()
    assert "automatically" in warning.call_args.args[0]
    assert warning.call_args.kwargs == {"fg": "yellow"}
    service.create_policy.assert_called_once()
    service.create_role.assert_called_once()
    assert service.attach_role_policy.call_args_list == [
        call(
            {
                "RoleName": ROLE_NAME,
                "PolicyName": CUSTOM_POLICY_NAME,
                "PolicyType": "Custom",
            }
        ),
        *[
            call(
                {
                    "RoleName": ROLE_NAME,
                    "PolicyName": policy_name,
                    "PolicyType": "System",
                }
            )
            for policy_name in SYSTEM_POLICIES
        ],
    ]


def test_existing_custom_policy_is_reused_when_role_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.get_role.side_effect = _iam_error("RoleNotExist", "role not found")
    service.get_policy.return_value = {
        "Result": {"Policy": {"PolicyName": CUSTOM_POLICY_NAME}}
    }
    service.create_role.return_value = {"Result": {"Role": {"RoleName": ROLE_NAME}}}
    service.attach_role_policy.return_value = {"Result": {}}
    _install_iam_service(monkeypatch, service)

    ensure_serverless_application_role("ak", "sk")

    service.create_policy.assert_not_called()


def test_role_lookup_permission_error_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.get_role.side_effect = _iam_error("AccessDenied", "permission denied")
    _install_iam_service(monkeypatch, service)

    with pytest.raises(Exception, match="permission denied"):
        ensure_serverless_application_role("ak", "sk")

    service.create_role.assert_not_called()


def test_studio_deploy_checks_serverless_role_with_custom_function_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_credentials: list[tuple[str, str]] = []

    class _FakeCloudAgentEngine:
        def __init__(self, **_: object) -> None:
            pass

        def deploy(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(
                vefaas_endpoint="",
                vefaas_application_id="app-id",
                vefaas_function_id="",
            )

    monkeypatch.setattr(
        "veadk.cli.studio_deploy_serverless_iam.ensure_serverless_application_role",
        lambda access_key, secret_key: checked_credentials.append(
            (access_key, secret_key)
        ),
    )
    monkeypatch.setattr(
        "veadk.cloud.cloud_agent_engine.CloudAgentEngine", _FakeCloudAgentEngine
    )
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_studio_identity_region",
        lambda **kwargs: kwargs["deployment_region"],
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
    assert checked_credentials == [("ak", "sk")]
