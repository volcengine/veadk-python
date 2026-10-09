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

"""Isolated role reconciliation contracts; never call real IAM."""

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from veadk.integrations.mpa.managed.config import Managed, load_studio_profile
from veadk.integrations.mpa.managed.iam import (
    ACTIONS,
    POLICY_NAME,
    ROLE_NAME,
    SYSTEM_POLICIES,
    TRUST_DOCUMENT,
    IamCloud,
    IamError,
    ensure_runtime_role,
)


class FakeIAM:
    def __init__(self):
        self.role = None
        self.policy = None
        self.bindings = {("unrelated", "Custom")}
        self.calls = []
        self.fail = None
        self.hidden = 0
        self.race = False

    async def call(self, method, **params):
        self.calls.append((method, params))
        if self.fail == method:
            raise IamError("AccessDenied")
        if method == "get_role":
            if self.role is None:
                raise IamError("RoleNotExist")
            return {"Role": copy.deepcopy(self.role)}
        if method == "create_role":
            self.role = {
                "RoleName": ROLE_NAME,
                "Trn": f"trn:iam::123:role/{ROLE_NAME}",
                "TrustPolicyDocument": params["TrustPolicyDocument"],
            }
            if self.race:
                raise IamError("RoleAlreadyExists")
        if method == "get_policy":
            if self.policy is None:
                raise IamError("PolicyNotExist")
            return {"Policy": {"PolicyDocument": copy.deepcopy(self.policy)}}
        if method == "create_policy":
            self.policy = json.loads(params["PolicyDocument"])
            if self.race:
                raise IamError("PolicyAlreadyExist")
        if method == "list_attached_role_policies":
            if self.hidden:
                self.hidden -= 1
                return {"AttachedPolicyMetadata": []}
            return {
                "AttachedPolicyMetadata": [
                    {
                        "PolicyName": name,
                        "PolicyType": kind,
                        "PolicyScope": [{"PolicyScopeType": "Global"}],
                    }
                    for name, kind in self.bindings
                ]
            }
        if method == "attach_role_policy":
            binding = (params["PolicyName"], params["PolicyType"])
            if binding in self.bindings:
                raise IamError("PolicyAttachConflict")
            self.bindings.add(binding)
        return {}


@pytest.mark.asyncio
@pytest.mark.parametrize("race", [False, True])
async def test_new_role_and_policy_converge_and_retry_is_additive(race):
    cloud = FakeIAM()
    cloud.race = race
    await ensure_runtime_role(cloud, "123", poll_interval=0)
    assert len(SYSTEM_POLICIES) == 12 and len(ACTIONS) == 14
    assert cloud.bindings == {("unrelated", "Custom"), (POLICY_NAME, "Custom")} | {
        (name, "System") for name in SYSTEM_POLICIES
    }
    assert json.loads(cloud.role["TrustPolicyDocument"]) == TRUST_DOCUMENT
    cloud.calls.clear()
    await ensure_runtime_role(cloud, "123", poll_interval=0)
    assert not any(
        method.startswith(("create_", "attach_")) for method, _ in cloud.calls
    )


@pytest.mark.asyncio
async def test_partial_failure_preserves_state_and_same_identity_can_resume():
    cloud = FakeIAM()
    cloud.fail = "attach_role_policy"
    with pytest.raises(IamError) as caught:
        await ensure_runtime_role(cloud, "123", poll_interval=0)
    assert caught.value.key == "iamPermissionDenied"
    assert cloud.role and cloud.policy
    cloud.fail = None
    cloud.hidden = 2
    await ensure_runtime_role(cloud, "123", poll_interval=0)
    assert (POLICY_NAME, "Custom") in cloud.bindings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem,key",
    [
        ("account", "iamOwnershipConflict"),
        ("trust", "iamTrustConflict"),
        ("deny", "iamTrustConflict"),
        ("policy", "iamPolicyConflict"),
    ],
)
async def test_conflicting_existing_resources_are_never_overwritten(problem, key):
    cloud = FakeIAM()
    await ensure_runtime_role(cloud, "123", poll_interval=0)
    if problem == "account":
        cloud.role["Trn"] = f"trn:iam::456:role/{ROLE_NAME}"
    elif problem == "trust":
        cloud.role["TrustPolicyDocument"] = json.dumps({"Statement": []})
    elif problem == "deny":
        trust = copy.deepcopy(TRUST_DOCUMENT)
        trust["Statement"].append({"Effect": "Deny", "Action": ["sts:AssumeRole"]})
        cloud.role["TrustPolicyDocument"] = trust
    else:
        cloud.policy["Statement"][0]["Resource"] = ["different"]
    cloud.calls.clear()
    with pytest.raises(IamError) as caught:
        await ensure_runtime_role(cloud, "123", poll_interval=0)
    assert caught.value.key == key
    assert all(method.startswith(("get_", "list_")) for method, _ in cloud.calls)


@pytest.mark.asyncio
async def test_permission_error_does_not_trigger_create():
    cloud = FakeIAM()
    cloud.fail = "get_role"
    with pytest.raises(IamError, match="iamPermissionDenied"):
        await ensure_runtime_role(cloud, "123", poll_interval=0)
    assert [method for method, _ in cloud.calls] == ["get_role"]


@pytest.mark.asyncio
async def test_readback_timeout_and_cancellation_keep_resources():
    cloud = FakeIAM()
    cloud.hidden = 100000
    with pytest.raises(IamError, match="iamVerificationFailed"):
        await ensure_runtime_role(cloud, "123", timeout=0.01, poll_interval=0.02)
    assert cloud.role and cloud.policy
    task = asyncio.create_task(ensure_runtime_role(cloud, "123", poll_interval=10))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    count = len(cloud.calls)
    await asyncio.sleep(0.01)
    assert len(cloud.calls) == count


def test_default_modes_and_auto_rejects_custom_sources(monkeypatch):
    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-key")
    assert load_studio_profile(region="cn-beijing").managed.iam.mode == "auto"
    assert Managed(version=1, worker={"image": "repo/image:tag"}).iam.mode == "existing"
    for extra in [
        {"from_runtime": "r-reference"},
        {"template_file": "x.json"},
        {"runtime": {"role_name": "CustomRole"}},
        {"worker": {"image": "repo/image:tag", "role_name": "CustomRole"}},
    ]:
        with pytest.raises(ValueError):
            Managed.model_validate(
                {
                    "version": 1,
                    "worker": {"image": "repo/image:tag"},
                    "iam": {"mode": "auto"},
                    **extra,
                }
            )


@pytest.mark.asyncio
async def test_sdk_isolation_fresh_credentials_and_safe_errors(monkeypatch):
    from volcengine.iam.IamService import IamService

    clients = []

    def initialize(client):
        clients.append(client)

    monkeypatch.setattr(IamService, "__init__", initialize)
    for setter in [
        "set_ak",
        "set_sk",
        "set_session_token",
        "set_scheme",
        "set_connection_timeout",
        "set_socket_timeout",
    ]:
        monkeypatch.setattr(IamService, setter, lambda self, value: None)
    monkeypatch.setattr(
        IamService,
        "get_role",
        lambda self, params: {
            "ResponseMetadata": {
                "Error": {"Code": "AccessDenied", "Message": "private-token"}
            }
        },
    )
    credentials = []

    def fresh():
        credentials.append(True)
        return SimpleNamespace(
            access_key_id="test", secret_access_key="test", session_token="test"
        )

    cloud = IamCloud(SimpleNamespace(_credentials=fresh))
    for _ in range(2):
        with pytest.raises(IamError) as caught:
            await cloud.call("get_role", RoleName=ROLE_NAME)
        assert "private-token" not in str(caught.value)
    assert len(credentials) == 2 and clients[0] is not clients[1]
    monkeypatch.setattr(
        IamService,
        "get_role",
        lambda self, params: (_ for _ in ()).throw(
            Exception(
                json.dumps(
                    {
                        "ResponseMetadata": {
                            "Error": {
                                "Code": "RoleNotExist",
                                "Message": "private-token",
                            }
                        }
                    }
                )
            )
        ),
    )
    with pytest.raises(IamError) as caught:
        await cloud.call("get_role", RoleName=ROLE_NAME)
    assert caught.value.code == "RoleNotExist"


@pytest.mark.asyncio
async def test_role_failure_stops_before_identity_and_pg(monkeypatch):
    from unittest.mock import AsyncMock
    from veadk.integrations.mpa.managed import service

    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-key")
    profile = load_studio_profile(region="cn-beijing")
    profile.values["account_id"] = "123"
    runtime = SimpleNamespace(account_id=AsyncMock(return_value="123"))
    monkeypatch.setattr(service, "RuntimeCloud", lambda **kwargs: runtime)
    prepare = AsyncMock(side_effect=IamError("AccessDenied"))
    identity = AsyncMock()
    monkeypatch.setattr(service, "ensure_runtime_role", prepare)
    monkeypatch.setattr(service, "ensure_workload_identity", identity)
    stages = []
    with pytest.raises(IamError):
        await service.provision(
            profile, agent_id="mi-test", owner="test", progress=stages.append
        )
    assert stages == ["checking", "iam_role"]
    prepare.assert_awaited_once()
    identity.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_only_binding_does_not_satisfy_global_access():
    cloud = FakeIAM()
    await ensure_runtime_role(cloud, "123", poll_interval=0)
    original = cloud.call
    reads = 0

    async def call(method, **params):
        nonlocal reads
        result = await original(method, **params)
        if method == "list_attached_role_policies":
            reads += 1
            if reads == 1:
                for binding in result["AttachedPolicyMetadata"]:
                    binding["PolicyScope"] = [{"PolicyScopeType": "Project"}]
        return result

    cloud.call = call
    cloud.calls.clear()
    await ensure_runtime_role(cloud, "123", poll_interval=0)
    assert len([m for m, _ in cloud.calls if m == "attach_role_policy"]) == 13
