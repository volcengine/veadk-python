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
from typing import Any

import pytest

from veadk.integrations.mpa.managed.config import Managed, Worker, load_studio_profile
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
        self.role: dict[str, Any] | None = None
        self.policy: dict[str, Any] | None = None
        self.bindings = {("unrelated", "Custom")}
        self.calls = []
        self.fail: str | None = None
        self.hidden = 0
        self.race = False

    async def call(self, method, **params) -> dict[str, Any]:
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


class FakeTosIAM(FakeIAM):
    def __init__(self):
        super().__init__()
        self.role = {
            "RoleName": ROLE_NAME,
            "Trn": f"trn:iam::123:role/{ROLE_NAME}",
            "TrustPolicyDocument": copy.deepcopy(TRUST_DOCUMENT),
        }
        self.policies = {}
        self.checked_buckets = []

    async def verify_tos_bucket(self, bucket):
        self.checked_buckets.append(bucket)

    async def call(self, method, **params):
        if method not in {"get_policy", "create_policy"}:
            return await super().call(method, **params)
        self.calls.append((method, params))
        if self.fail == method:
            raise IamError("AccessDenied")
        name = params["PolicyName"]
        if method == "get_policy":
            if name not in self.policies:
                raise IamError("PolicyNotExist")
            return {"Policy": {"PolicyDocument": copy.deepcopy(self.policies[name])}}
        self.policies[name] = json.loads(params["PolicyDocument"])
        if self.race:
            raise IamError("PolicyAlreadyExist")
        return {}


@pytest.mark.asyncio
@pytest.mark.parametrize("race", [False, True])
async def test_tos_role_grant_is_scoped_additive_and_repeatable(race):
    from veadk.integrations.mpa.managed import iam

    cloud = FakeTosIAM()
    cloud.race = race
    await iam.ensure_tos_mount_permissions(
        cloud, "123", "session-output", poll_interval=0
    )
    assert cloud.checked_buckets == ["session-output"]
    assert len(cloud.policies) == 1
    name, policy = next(iter(cloud.policies.items()))
    assert cloud.bindings == {("unrelated", "Custom"), (name, "Custom")}
    assert policy == {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["tos:HeadBucket", "tos:ListBucket"],
                "Resource": ["trn:tos:::session-output"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "tos:GetObject",
                    "tos:PutObject",
                    "tos:AbortMultipartUpload",
                    "tos:DeleteObject",
                ],
                "Resource": ["trn:tos:::session-output/sandbox-session/*"],
            },
        ]
    }
    cloud.calls.clear()
    await iam.ensure_tos_mount_permissions(
        cloud, "123", "session-output", poll_interval=0
    )
    assert not any(
        method.startswith(("create_", "attach_")) for method, _ in cloud.calls
    )
    await iam.ensure_tos_mount_permissions(
        cloud, "123", "other-output", poll_interval=0
    )
    assert len(cloud.policies) == 2
    assert cloud.policies[name] == policy


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["account", "trust", "policy", "permission"])
async def test_tos_role_grant_refuses_conflicts_without_overwriting(problem):
    from veadk.integrations.mpa.managed import iam

    cloud = FakeTosIAM()
    await iam.ensure_tos_mount_permissions(
        cloud, "123", "session-output", poll_interval=0
    )
    if problem == "account":
        cloud.role["Trn"] = f"trn:iam::456:role/{ROLE_NAME}"
    elif problem == "trust":
        cloud.role["TrustPolicyDocument"] = {"Statement": []}
    elif problem == "policy":
        next(iter(cloud.policies.values()))["Statement"][1]["Resource"] = ["*"]
    else:
        cloud.fail = "get_role"
    cloud.calls.clear()
    with pytest.raises(IamError):
        await iam.ensure_tos_mount_permissions(
            cloud, "123", "session-output", poll_interval=0
        )
    assert all(method.startswith(("get_", "list_")) for method, _ in cloud.calls)


@pytest.mark.asyncio
async def test_tos_role_grant_waits_for_readback_and_preserves_cancellation():
    from veadk.integrations.mpa.managed import iam

    cloud = FakeTosIAM()
    cloud.hidden = 3
    await iam.ensure_tos_mount_permissions(
        cloud, "123", "session-output", poll_interval=0
    )
    cloud.hidden = 100000
    with pytest.raises(IamError, match="iamVerificationFailed"):
        await iam.ensure_tos_mount_permissions(
            cloud, "123", "session-output", timeout=0.01, poll_interval=0.02
        )
    task = asyncio.create_task(
        iam.ensure_tos_mount_permissions(
            cloud, "123", "session-output", poll_interval=10
        )
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cloud.policies


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method", ["get_policy", "create_policy", "attach_role_policy"]
)
async def test_tos_role_grant_propagates_provider_permission_errors(method):
    from veadk.integrations.mpa.managed import iam

    cloud = FakeTosIAM()
    cloud.fail = method
    with pytest.raises(IamError, match="iamPermissionDenied"):
        await iam.ensure_tos_mount_permissions(
            cloud, "123", "session-output", poll_interval=0
        )
    assert not any(name.startswith("update_") for name, _ in cloud.calls)


@pytest.mark.asyncio
async def test_tos_role_grant_transient_deadline_and_actual_worker_role(monkeypatch):
    from veadk.integrations.mpa.managed import iam

    cloud = FakeTosIAM()
    cloud.role.update(RoleName="WorkerRole", Trn="trn:iam::123:role/WorkerRole")
    call = cloud.call
    attempts = 0

    async def transient(method, **params):
        nonlocal attempts
        if method == "get_policy" and attempts == 0:
            attempts += 1
            raise IamError("Throttling")
        return await call(method, **params)

    cloud.call = transient
    await iam.ensure_tos_mount_permissions(
        cloud, "123", "session-output", role_name="WorkerRole", poll_interval=0
    )
    assert attempts == 1
    assert all(
        params.get("RoleName", "WorkerRole") == "WorkerRole"
        for _, params in cloud.calls
    )
    times = iter([0, 200])
    monkeypatch.setattr(iam, "time", SimpleNamespace(monotonic=lambda: next(times)))
    cloud.hidden = 1000
    with pytest.raises(IamError, match="iamVerificationFailed"):
        await iam.ensure_tos_mount_permissions(
            cloud, "123", "session-output", role_name="WorkerRole", poll_interval=0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("bucket", ["", "*", "bad/name"])
async def test_tos_role_grant_rejects_unsafe_names_before_cloud(bucket):
    from veadk.integrations.mpa.managed import iam
    from veadk.integrations.mpa.managed.config import ConfigurationError

    cloud = FakeTosIAM()
    with pytest.raises((IamError, ConfigurationError)):
        await iam.ensure_tos_mount_permissions(cloud, "123", bucket)
    assert not cloud.calls and not cloud.checked_buckets


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "owned",
        "region",
        "missing",
        "permission",
        "unknown",
        "constructor",
        "credentials",
    ],
)
async def test_tos_bucket_check_uses_fresh_credentials_and_closes_client(
    monkeypatch, scenario
):
    import tos

    calls = []
    closed = []

    def credentials():
        calls.append("credentials")
        if scenario == "credentials":
            raise RuntimeError("private-token")
        return SimpleNamespace(
            access_key_id="test-ak",
            secret_access_key="test-sk",
            session_token="test-token",
        )

    class Client:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))
            if scenario == "constructor":
                raise RuntimeError("private-token")

        def list_buckets(self):
            if scenario in {"permission", "unknown"}:
                raise RuntimeError(
                    "AccessDenied private-token"
                    if scenario == "permission"
                    else "private-token"
                )
            return SimpleNamespace(
                buckets=[]
                if scenario == "missing"
                else [
                    SimpleNamespace(
                        name="session-output",
                        location="other-region"
                        if scenario == "region"
                        else "cn-beijing",
                    )
                ]
            )

        def close(self):
            closed.append(True)

    monkeypatch.setattr(tos, "TosClientV2", Client)
    cloud = IamCloud(SimpleNamespace(region="cn-beijing", _credentials=credentials))
    if scenario == "owned":
        await cloud.verify_tos_bucket("session-output")
        await cloud.verify_tos_bucket("session-output")
        assert calls.count("credentials") == 2
        assert closed == [True, True]
        assert calls[1][1]["security_token"] == "test-token"
    else:
        with pytest.raises(IamError) as caught:
            await cloud.verify_tos_bucket("session-output")
        assert "private-token" not in str(caught.value)
        if scenario in {"region", "missing"}:
            assert caught.value.key == "tosBucketUnavailable"
        assert bool(closed) == (scenario not in {"constructor", "credentials"})


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
    assert cloud.role is not None
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
    assert cloud.role is not None and cloud.policy is not None
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
    assert (
        Managed(version=1, worker=Worker(image="repo/image:tag")).iam.mode == "existing"
    )
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
    monkeypatch.setattr(service, "resolve_model_key", AsyncMock(return_value=profile))
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
