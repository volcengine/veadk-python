# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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
from unittest.mock import MagicMock, call

import pytest

from frontend.server.runtime_iam import (
    DEFAULT_RUNTIME_POLICY,
    DEFAULT_RUNTIME_ROLE,
    ensure_runtime_role,
)


@pytest.fixture
def iam(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    service = MagicMock()
    service.list_roles.return_value = {"Result": {"RoleMetadata": [], "Total": 0}}
    service.list_attached_role_policies.return_value = {
        "Result": {"AttachedPolicyMetadata": []}
    }
    service.get_role.return_value = {
        "ResponseMetadata": {
            "Error": {
                "Code": "RoleNotExist",
                "Message": "role does not exist",
            }
        }
    }
    service.create_role.return_value = {"ResponseMetadata": {"Action": "CreateRole"}}
    service.attach_role_policy.return_value = {
        "ResponseMetadata": {"Action": "AttachRolePolicy"}
    }
    module = importlib.import_module("volcengine.iam.IamService")
    monkeypatch.setattr(module, "IamService", lambda: service)
    monkeypatch.delenv("IAM_OPENAPI_HOST", raising=False)
    for key in (
        "VOLCENGINE_AGENTKIT_SERVICE",
        "VOLC_AGENTKIT_SERVICE",
        "BYTEPLUS_AGENTKIT_SERVICE",
    ):
        monkeypatch.delenv(key, raising=False)
    return service


@pytest.mark.parametrize(
    ("provider", "host"),
    [("volcengine", "iam.volcengineapi.com"), ("byteplus", "iam.byteplusapi.com")],
)
def test_reuses_matching_role_on_later_page_without_changing_permissions(
    iam: MagicMock, provider, host: str
) -> None:
    iam.list_roles.side_effect = [
        {"Result": {"RoleMetadata": [{"RoleName": "old-role"}], "Total": 3}},
        {
            "Result": {
                "RoleMetadata": [
                    {"RoleName": "shared-role"},
                    {"RoleName": "another-role"},
                ],
                "Total": 3,
            }
        },
    ]
    iam.list_attached_role_policies.side_effect = [
        {"Result": {"AttachedPolicyMetadata": [{"PolicyName": "AgentKitFullAccess"}]}},
        {
            "Result": {
                "AttachedPolicyMetadata": [
                    {"PolicyName": "OtherAccess", "PolicyType": "System"},
                    {"PolicyName": DEFAULT_RUNTIME_POLICY, "PolicyType": "System"},
                ]
            }
        },
    ]

    assert (
        ensure_runtime_role(
            access_key="test-ak",
            secret_key="test-sk",
            session_token="test-token",
            provider=provider,
        )
        == "shared-role"
    )

    assert iam.list_roles.call_args_list == [
        call({"Limit": 100, "Offset": 0}),
        call({"Limit": 100, "Offset": 1}),
    ]
    assert iam.list_attached_role_policies.call_args_list == [
        call({"RoleName": "old-role"}),
        call({"RoleName": "shared-role"}),
    ]
    iam.set_host.assert_called_once_with(host)
    iam.set_ak.assert_called_once_with("test-ak")
    iam.set_sk.assert_called_once_with("test-sk")
    iam.set_session_token.assert_called_once_with("test-token")
    iam.set_scheme.assert_called_once_with("https")
    iam.create_role.assert_not_called()
    iam.attach_role_policy.assert_not_called()
    iam.update_role.assert_not_called()


def test_prefers_well_known_legacy_role_without_scanning_account(
    iam: MagicMock,
) -> None:
    iam.get_role.return_value = {"Result": {"Role": {"RoleName": DEFAULT_RUNTIME_ROLE}}}
    iam.list_attached_role_policies.return_value = {
        "Result": {
            "AttachedPolicyMetadata": [
                {"PolicyName": name, "PolicyType": "System"}
                for name in (
                    "CloudControlReadOnlyAccess",
                    "AgentKitTosAccess",
                    "TorchlightApiFullAccess",
                    "LLMShieldProtectSdkAccess",
                    "AgentKitToolAccess",
                    "IDReadOnlyAccess",
                    "Mem0ReadOnlyAccess",
                    "AgentKitRuntimeAccess",
                )
            ]
        }
    }

    assert ensure_runtime_role(access_key="ak", secret_key="sk") == (
        DEFAULT_RUNTIME_ROLE
    )
    iam.list_roles.assert_not_called()
    iam.create_role.assert_not_called()
    iam.attach_role_policy.assert_not_called()


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_reuses_legacy_agentkit_role_when_role_quota_is_exhausted(
    iam: MagicMock, provider: str
) -> None:
    iam.list_roles.return_value = {
        "Result": {
            "RoleMetadata": [
                {"RoleName": "AgentKit_Runtime_Default_ServiceRole_existing"}
            ],
            "Total": 1,
        }
    }
    iam.list_attached_role_policies.return_value = {
        "Result": {
            "AttachedPolicyMetadata": [
                {"PolicyName": name, "PolicyType": "System"}
                for name in (
                    "CloudControlReadOnlyAccess",
                    "AgentKitTosAccess",
                    "TorchlightApiFullAccess",
                    "LLMShieldProtectSdkAccess",
                    "AgentKitToolAccess",
                    "IDReadOnlyAccess",
                    "Mem0ReadOnlyAccess",
                    "AgentKitRuntimeAccess",
                )
            ]
        }
    }
    iam.create_role.return_value = {
        "ResponseMetadata": {
            "Error": {
                "Code": "LimitExceeded",
                "Message": "Exceeded RolesPerAccount quota, quota: 1000",
            }
        }
    }

    assert (
        ensure_runtime_role(access_key="ak", secret_key="sk", provider=provider)
        == "AgentKit_Runtime_Default_ServiceRole_existing"
    )
    iam.create_role.assert_not_called()
    iam.attach_role_policy.assert_not_called()


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize("existing_roles", [False, True])
def test_creates_only_default_policy_when_no_role_matches(
    iam: MagicMock, provider, existing_roles: bool
) -> None:
    if existing_roles:
        iam.list_roles.return_value = {
            "Result": {"RoleMetadata": [{"RoleName": "unrelated"}], "Total": 1}
        }
        iam.list_attached_role_policies.return_value = {
            "Result": {
                "AttachedPolicyMetadata": [
                    {"PolicyName": DEFAULT_RUNTIME_POLICY, "PolicyType": "Custom"},
                    {"PolicyName": "AgentKitFullAccess", "PolicyType": "System"},
                ]
            }
        }

    name = ensure_runtime_role(access_key="ak", secret_key="sk", provider=provider)

    assert name == DEFAULT_RUNTIME_ROLE
    created = iam.create_role.call_args.args[0]
    assert created["RoleName"] == name
    assert json.loads(created["TrustPolicyDocument"]) == {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["sts:AssumeRole"],
                "Principal": {"Service": ["vefaas"]},
            }
        ]
    }
    iam.attach_role_policy.assert_called_once_with(
        {"RoleName": name, "PolicyName": DEFAULT_RUNTIME_POLICY, "PolicyType": "System"}
    )
    iam.set_session_token.assert_not_called()


def test_keeps_staging_trust_service(iam: MagicMock, monkeypatch) -> None:
    monkeypatch.setenv("VOLCENGINE_AGENTKIT_SERVICE", "agentkit_stg")
    ensure_runtime_role(access_key="ak", secret_key="sk")
    document = json.loads(iam.create_role.call_args.args[0]["TrustPolicyDocument"])
    assert document["Statement"][0]["Principal"]["Service"] == ["vefaas_dev"]


@pytest.mark.parametrize("operation", ["list_roles", "list_attached_role_policies"])
def test_lookup_errors_never_create_a_fallback_role(
    iam: MagicMock, operation: str
) -> None:
    iam.list_roles.return_value = {
        "Result": {"RoleMetadata": [{"RoleName": "existing"}], "Total": 1}
    }
    getattr(iam, operation).return_value = {
        "ResponseMetadata": {"Error": {"Code": "AccessDenied", "Message": "denied"}}
    }
    with pytest.raises(RuntimeError, match="denied"):
        ensure_runtime_role(access_key="ak", secret_key="sk")
    iam.create_role.assert_not_called()
    iam.attach_role_policy.assert_not_called()


def test_network_failure_never_creates_a_fallback_role(iam: MagicMock) -> None:
    iam.list_roles.side_effect = TimeoutError("IAM timeout")
    with pytest.raises(TimeoutError):
        ensure_runtime_role(access_key="ak", secret_key="sk")
    iam.create_role.assert_not_called()


@pytest.mark.parametrize(
    "result",
    [{}, {"RoleMetadata": [], "Total": 1}, {"RoleMetadata": "invalid", "Total": 0}],
)
def test_incomplete_role_list_never_creates_a_role(iam: MagicMock, result) -> None:
    iam.list_roles.return_value = {"Result": result}
    with pytest.raises(RuntimeError):
        ensure_runtime_role(access_key="ak", secret_key="sk")
    iam.create_role.assert_not_called()


@pytest.mark.parametrize("operation", ["create_role", "attach_role_policy"])
def test_creation_or_attachment_failure_is_reported(
    iam: MagicMock, operation: str
) -> None:
    getattr(iam, operation).return_value = {
        "ResponseMetadata": {"Error": {"Message": "IAM operation failed"}}
    }
    with pytest.raises(RuntimeError, match="IAM operation failed"):
        ensure_runtime_role(access_key="ak", secret_key="sk")
    if operation == "create_role":
        iam.attach_role_policy.assert_not_called()
