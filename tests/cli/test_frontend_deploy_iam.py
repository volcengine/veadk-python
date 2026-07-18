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
from unittest.mock import MagicMock, call

import pytest

from veadk.cli.frontend_deploy_iam import ensure_frontend_role
from veadk.cli.frontend_deploy_policy import FRONTEND_DEPLOY_SYSTEM_POLICIES


def _install_iam_service(monkeypatch: pytest.MonkeyPatch, service: MagicMock) -> None:
    iam_module = importlib.import_module("volcengine.iam.IamService")
    monkeypatch.setattr(iam_module, "IamService", lambda: service)


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
    service.attach_role_policy.return_value = {"Result": {}}
    _install_iam_service(monkeypatch, service)

    trn = ensure_frontend_role("ak", "sk")

    assert trn == "trn:iam::123:role/VeADKFrontendServiceRole"
    service.create_role.assert_not_called()
    service.create_policy.assert_not_called()
    assert service.attach_role_policy.call_args_list == [
        call(
            {
                "RoleName": "VeADKFrontendServiceRole",
                "PolicyName": policy_name,
                "PolicyType": "System",
            }
        )
        for policy_name in FRONTEND_DEPLOY_SYSTEM_POLICIES[1:]
    ]


def test_new_frontend_role_gets_custom_and_system_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.get_role.return_value = {
        "ResponseMetadata": {"Error": {"Message": "role not found"}}
    }
    service.create_policy.return_value = {"Result": {}}
    service.create_role.return_value = {
        "Result": {"Role": {"Trn": "trn:iam::123:role/VeADKFrontendServiceRole"}}
    }
    service.list_attached_role_policies.return_value = {
        "Result": {"AttachedPolicyMetadata": [{"PolicyName": "VeADKFrontendPolicy"}]}
    }
    service.attach_role_policy.return_value = {"Result": {}}
    _install_iam_service(monkeypatch, service)

    ensure_frontend_role("ak", "sk")

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
    service.list_attached_role_policies.return_value = {
        "ResponseMetadata": {"Error": {"Message": "permission denied"}}
    }
    _install_iam_service(monkeypatch, service)

    with pytest.raises(RuntimeError, match="permission denied"):
        ensure_frontend_role("ak", "sk")

    service.create_role.assert_not_called()
