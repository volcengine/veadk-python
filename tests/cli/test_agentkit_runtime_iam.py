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
from unittest.mock import MagicMock

import pytest

from veadk.cli.agentkit_runtime_iam import (
    AGENTKIT_RUNTIME_FULL_ACCESS_POLICY,
    ensure_quick_runtime_full_access,
    is_agentkit_default_runtime_role,
)


def _install_iam_service(monkeypatch: pytest.MonkeyPatch, service: MagicMock) -> None:
    iam_module = importlib.import_module("volcengine.iam.IamService")
    monkeypatch.setattr(iam_module, "IamService", lambda: service)


def test_recognizes_current_and_legacy_agentkit_default_roles() -> None:
    assert is_agentkit_default_runtime_role(
        "AgentKit_Runtime_Default_ServiceRole_abcd123"
    )
    assert is_agentkit_default_runtime_role(
        "trn:iam::123:role/AgentKit-Runtime-Default-ServiceRole-abcd123"
    )
    assert not is_agentkit_default_runtime_role("CustomerRuntimeRole")


def test_attaches_full_access_to_generated_runtime_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.list_attached_role_policies.return_value = {
        "Result": {"AttachedPolicyMetadata": [{"PolicyName": "AgentKitRuntimeAccess"}]}
    }
    service.attach_role_policy.return_value = {"Result": {}}
    _install_iam_service(monkeypatch, service)

    assert ensure_quick_runtime_full_access(
        "AgentKit_Runtime_Default_ServiceRole_abcd123",
        access_key="ak",
        secret_key="sk",
    )
    service.attach_role_policy.assert_called_once_with(
        {
            "RoleName": "AgentKit_Runtime_Default_ServiceRole_abcd123",
            "PolicyName": AGENTKIT_RUNTIME_FULL_ACCESS_POLICY,
            "PolicyType": "System",
        }
    )


def test_keeps_existing_full_access_and_customer_roles_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.list_attached_role_policies.return_value = {
        "Result": {
            "AttachedPolicyMetadata": [
                {"PolicyName": AGENTKIT_RUNTIME_FULL_ACCESS_POLICY}
            ]
        }
    }
    _install_iam_service(monkeypatch, service)

    assert ensure_quick_runtime_full_access(
        "AgentKit_Runtime_Default_ServiceRole_abcd123",
        access_key="ak",
        secret_key="sk",
    )
    assert not ensure_quick_runtime_full_access(
        "CustomerRuntimeRole",
        access_key="ak",
        secret_key="sk",
    )
    service.attach_role_policy.assert_not_called()
    service.list_attached_role_policies.assert_called_once()
