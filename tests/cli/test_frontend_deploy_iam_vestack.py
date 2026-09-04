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
from unittest.mock import MagicMock

import pytest

from veadk.cli.frontend_deploy_iam_vestack import ensure_frontend_role_vestack
from veadk.cli.frontend_deploy_policy import (
    FRONTEND_DEPLOY_POLICY,
    FRONTEND_DEPLOY_SYSTEM_POLICIES,
)


def _install_iam_service(monkeypatch: pytest.MonkeyPatch, service: MagicMock) -> None:
    iam_module = importlib.import_module("volcengine.iam.IamService")
    monkeypatch.setattr(iam_module, "IamService", lambda: service)


def _existing_role_service() -> MagicMock:
    service = MagicMock()
    service.get_role.return_value = {
        "Result": {"Role": {"Trn": "trn:iam::123:role/VeADKFrontendServiceRole"}}
    }
    service.update_policy.return_value = {"Result": {}}
    service.get_policy.return_value = {
        "Result": {"Policy": {"PolicyDocument": json.dumps(FRONTEND_DEPLOY_POLICY)}}
    }
    service.list_attached_role_policies.return_value = {
        "Result": {"AttachedPolicyMetadata": [{"PolicyName": "VeADKFrontendPolicy"}]}
    }
    return service


def test_vestack_skips_only_unavailable_system_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _existing_role_service()

    def attach_policy(request: dict) -> dict:
        if request["PolicyName"] == FRONTEND_DEPLOY_SYSTEM_POLICIES[0]:
            raise RuntimeError("PolicyNotExist: Policy does not exist")
        return {"Result": {}}

    service.attach_role_policy.side_effect = attach_policy
    _install_iam_service(monkeypatch, service)

    trn = ensure_frontend_role_vestack("ak", "sk")

    assert trn == "trn:iam::123:role/VeADKFrontendServiceRole"
    attempted_system_policies = [
        call.args[0]["PolicyName"] for call in service.attach_role_policy.call_args_list
    ]
    assert attempted_system_policies == list(FRONTEND_DEPLOY_SYSTEM_POLICIES)


def test_vestack_does_not_hide_other_policy_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _existing_role_service()
    service.attach_role_policy.side_effect = RuntimeError("permission denied")
    _install_iam_service(monkeypatch, service)

    with pytest.raises(RuntimeError, match="permission denied"):
        ensure_frontend_role_vestack("ak", "sk")
