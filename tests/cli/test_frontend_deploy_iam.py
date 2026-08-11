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
from unittest.mock import MagicMock, call

import pytest

from veadk.cli.frontend_deploy_iam import ensure_frontend_role
from veadk.cli.frontend_deploy_policy import (
    FRONTEND_DEPLOY_POLICY,
    FRONTEND_DEPLOY_SYSTEM_POLICIES,
)


def _install_iam_service(monkeypatch: pytest.MonkeyPatch, service: MagicMock) -> None:
    iam_module = importlib.import_module("volcengine.iam.IamService")
    monkeypatch.setattr(iam_module, "IamService", lambda: service)


def _policy_response() -> dict:
    return {
        "Result": {"Policy": {"PolicyDocument": json.dumps(FRONTEND_DEPLOY_POLICY)}}
    }


def test_existing_frontend_role_gets_missing_system_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.get_role.return_value = {
        "Result": {"Role": {"Trn": "trn:iam::123:role/VeADKFrontendServiceRole"}}
    }
    service.list_attached_role_policies.return_value = {
        "Result": {
            "AttachedPolicyMetadata": [
                {"PolicyName": FRONTEND_DEPLOY_SYSTEM_POLICIES[0]}
            ]
        }
    }
    service.update_policy.return_value = {"Result": {}}
    service.get_policy.return_value = _policy_response()
    service.attach_role_policy.return_value = {"Result": {}}
    _install_iam_service(monkeypatch, service)

    trn = ensure_frontend_role("ak", "sk")

    assert trn == "trn:iam::123:role/VeADKFrontendServiceRole"
    service.set_session_token.assert_not_called()
    service.create_role.assert_not_called()
    service.update_policy.assert_called_once()
    service.create_policy.assert_not_called()
    assert service.attach_role_policy.call_args_list == [
        call(
            {
                "RoleName": "VeADKFrontendServiceRole",
                "PolicyName": "VeADKFrontendPolicy",
                "PolicyType": "Custom",
            }
        ),
        *[
            call(
                {
                    "RoleName": "VeADKFrontendServiceRole",
                    "PolicyName": policy_name,
                    "PolicyType": "System",
                }
            )
            for policy_name in FRONTEND_DEPLOY_SYSTEM_POLICIES[1:]
        ],
    ]


def test_frontend_role_uses_session_token(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    service.get_role.return_value = {
        "Result": {"Role": {"Trn": "trn:iam::123:role/VeADKFrontendServiceRole"}}
    }
    service.list_attached_role_policies.return_value = {
        "Result": {
            "AttachedPolicyMetadata": [
                {"PolicyName": "VeADKFrontendPolicy"},
                *[
                    {"PolicyName": policy_name}
                    for policy_name in FRONTEND_DEPLOY_SYSTEM_POLICIES
                ],
            ]
        }
    }
    service.update_policy.return_value = {"Result": {}}
    service.get_policy.return_value = _policy_response()
    _install_iam_service(monkeypatch, service)

    ensure_frontend_role("ak", "sk", session_token="sts-token")

    service.set_session_token.assert_called_once_with("sts-token")


def test_frontend_role_uses_byteplus_iam_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.get_role.return_value = {
        "Result": {"Role": {"Trn": "trn:iam::123:role/VeADKFrontendServiceRole"}}
    }
    service.list_attached_role_policies.return_value = {
        "Result": {
            "AttachedPolicyMetadata": [
                {"PolicyName": "VeADKFrontendPolicy"},
                *[
                    {"PolicyName": policy_name}
                    for policy_name in FRONTEND_DEPLOY_SYSTEM_POLICIES
                ],
            ]
        }
    }
    service.update_policy.return_value = {"Result": {}}
    service.get_policy.return_value = _policy_response()
    _install_iam_service(monkeypatch, service)

    ensure_frontend_role("ak", "sk", provider="byteplus")

    service.set_host.assert_called_once_with("iam.byteplusapi.com")
    service.set_scheme.assert_called_once_with("https")


def test_new_frontend_role_gets_custom_and_system_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.get_role.return_value = {
        "ResponseMetadata": {"Error": {"Message": "role not found"}}
    }
    service.update_policy.return_value = {
        "ResponseMetadata": {"Error": {"Message": "policy not found"}}
    }
    service.create_policy.return_value = {"Result": {}}
    service.get_policy.return_value = _policy_response()
    service.create_role.return_value = {
        "Result": {"Role": {"Trn": "trn:iam::123:role/VeADKFrontendServiceRole"}}
    }
    service.list_attached_role_policies.return_value = {
        "Result": {"AttachedPolicyMetadata": []}
    }
    service.attach_role_policy.return_value = {"Result": {}}
    _install_iam_service(monkeypatch, service)

    ensure_frontend_role("ak", "sk")

    service.create_policy.assert_called_once()
    assert service.attach_role_policy.call_args_list == [
        call(
            {
                "RoleName": "VeADKFrontendServiceRole",
                "PolicyName": "VeADKFrontendPolicy",
                "PolicyType": "Custom",
            }
        ),
        *[
            call(
                {
                    "RoleName": "VeADKFrontendServiceRole",
                    "PolicyName": policy_name,
                    "PolicyType": "System",
                }
            )
            for policy_name in FRONTEND_DEPLOY_SYSTEM_POLICIES
        ],
    ]


def test_existing_frontend_role_policy_error_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.get_role.return_value = {
        "Result": {"Role": {"Trn": "trn:iam::123:role/VeADKFrontendServiceRole"}}
    }
    service.update_policy.return_value = {"Result": {}}
    service.get_policy.return_value = _policy_response()
    service.list_attached_role_policies.return_value = {
        "ResponseMetadata": {"Error": {"Message": "permission denied"}}
    }
    _install_iam_service(monkeypatch, service)

    with pytest.raises(RuntimeError, match="permission denied"):
        ensure_frontend_role("ak", "sk")

    service.create_role.assert_not_called()


def test_existing_frontend_policy_uses_new_document_and_verifies_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.get_role.return_value = {
        "Result": {"Role": {"Trn": "trn:iam::123:role/VeADKFrontendServiceRole"}}
    }
    service.list_attached_role_policies.return_value = {
        "Result": {
            "AttachedPolicyMetadata": [
                {"PolicyName": "VeADKFrontendPolicy"},
                *[
                    {"PolicyName": policy_name}
                    for policy_name in FRONTEND_DEPLOY_SYSTEM_POLICIES
                ],
            ]
        }
    }
    service.update_policy.return_value = {"Result": {}}
    service.get_policy.return_value = _policy_response()
    _install_iam_service(monkeypatch, service)

    ensure_frontend_role("ak", "sk")

    request = service.update_policy.call_args.args[0]
    assert "NewPolicyDocument" in request
    assert "PolicyDocument" not in request
    service.get_policy.assert_called_once_with(
        {"PolicyName": "VeADKFrontendPolicy", "PolicyType": "Custom"}
    )


def test_frontend_policy_verification_fails_when_action_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.update_policy.return_value = {"Result": {}}
    service.get_policy.return_value = {
        "Result": {
            "Policy": {
                "PolicyDocument": json.dumps(
                    {"Statement": [{"Action": ["vefaas:GetFunction"]}]}
                )
            }
        }
    }
    _install_iam_service(monkeypatch, service)

    with pytest.raises(RuntimeError, match="missing required actions"):
        ensure_frontend_role("ak", "sk")


def test_frontend_policy_allows_release_download() -> None:
    actions = FRONTEND_DEPLOY_POLICY["Statement"][0]["Action"]

    assert "tos:GetObject" in actions
    assert "vefaas:GetCodeUploadAddress" in actions
    assert "vefaas:GetApplication" in actions
    assert "vefaas:CodeUploadCallback" in actions
    assert "vefaas:UpdateFunction" in actions
    assert "vefaas:ReleaseApplication" in actions
