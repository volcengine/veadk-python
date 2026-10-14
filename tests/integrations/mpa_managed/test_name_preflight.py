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

"""Offline name preflight, account scope and retry ownership contracts."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.integrations.mpa_managed.test_auto_pg import recovery_setup
from veadk.integrations.mpa.managed.database import agent_suffix


def setup(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed import names

    profile, _, _, _ = recovery_setup(tmp_path, monkeypatch)
    assert profile.managed.postgres is not None
    profile.managed.postgres = profile.managed.postgres.model_copy(
        update={
            "business_workspace_mode": "per-agent",
            "business_database_name": "aidb",
        }
    )
    runtime = SimpleNamespace(
        account_id=AsyncMock(return_value="account"),
        find_runtimes=AsyncMock(return_value=[]),
        get=AsyncMock(),
        _credentials=lambda: None,
    )
    worker = SimpleNamespace(find=AsyncMock(return_value=[]), get=AsyncMock())
    pg = SimpleNamespace(find=AsyncMock(return_value=[]))
    monkeypatch.setattr(names, "WorkerCloud", lambda *_: worker)
    monkeypatch.setattr(names, "PGCloud", lambda **kw: pg)
    return names, profile, runtime, worker, pg


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["runtime", "worker", "workspace"])
async def test_foreign_name_collision_blocks_before_writes(tmp_path, monkeypatch, kind):
    names, profile, runtime, worker, pg = setup(tmp_path, monkeypatch)
    if kind == "runtime":
        runtime.find_runtimes.return_value = [
            {"RuntimeId": "r-foreign", "Name": "test-name"}
        ]
        runtime.get.return_value = {"Envs": [{"Key": "MPA_AGENT_ID", "Value": "other"}]}
    elif kind == "worker":
        worker.find.return_value = [{"ToolId": "t-other"}]
        worker.get.return_value = {"Envs": [{"Key": "MPA_AGENT_ID", "Value": "other"}]}
    else:
        pg.find.return_value = [{"workspace_tags": []}]
    with pytest.raises(names.NameCheckError) as caught:
        await names.check_creation_name(
            profile, runtime, agent_id="mi-test", name="test-name", owner="local"
        )
    assert caught.value.key == "runtimeNameTaken"


@pytest.mark.asyncio
async def test_verified_own_runtime_and_worker_allow_retry(tmp_path, monkeypatch):
    names, profile, runtime, worker, _ = setup(tmp_path, monkeypatch)
    runtime.find_runtimes.return_value = [{"RuntimeId": "r-own", "Name": "test-name"}]
    runtime.get.return_value = {
        "Envs": [{"Key": "MPA_AGENT_ID", "Value": "mi-test"}],
        "Tags": [{"Key": "veadk:owner", "Value": "local"}],
    }
    worker.find.return_value = [{"ToolId": "t-own"}]
    worker.get.return_value = {
        "Envs": [{"Key": "MPA_AGENT_ID", "Value": "mi-test"}],
        "Tags": [
            {"Key": "managed_by", "Value": "mpa-deployment"},
            {
                "Key": "mpa_agent_key",
                "Value": agent_suffix("account", profile.region, "mi-test"),
            },
        ],
    }
    assert (
        await names.check_creation_name(
            profile, runtime, agent_id="mi-test", name="test-name", owner="local"
        )
        == "account"
    )


@pytest.mark.asyncio
async def test_worker_with_matching_env_but_foreign_managed_tag_blocks_retry(
    tmp_path, monkeypatch
):
    names, profile, runtime, worker, _ = setup(tmp_path, monkeypatch)
    worker.find.return_value = [{"ToolId": "t-foreign"}]
    worker.get.return_value = {
        "Envs": [{"Key": "MPA_AGENT_ID", "Value": "mi-test"}],
        "Tags": [
            {"Key": "managed_by", "Value": "mpa-deployment"},
            {"Key": "mpa_agent_key", "Value": "foreign"},
        ],
    }
    with pytest.raises(names.NameCheckError) as caught:
        await names.check_creation_name(
            profile, runtime, agent_id="mi-test", name="test-name", owner="local"
        )
    assert caught.value.key == "runtimeNameTaken"


@pytest.mark.asyncio
async def test_query_failure_is_not_available_or_secret_output(tmp_path, monkeypatch):
    names, profile, runtime, _, _ = setup(tmp_path, monkeypatch)
    runtime.find_runtimes.side_effect = RuntimeError("private credential")
    with pytest.raises(names.NameCheckError) as caught:
        await names.check_creation_name(
            profile, runtime, agent_id="mi-test", name="test-name", owner="local"
        )
    assert caught.value.key == "runtimeNameCheckFailed"
    assert "private" not in str(caught.value)


@pytest.mark.asyncio
async def test_runtime_lookup_does_not_expand_unrelated_details(monkeypatch):
    from veadk.integrations.mpa.managed.runtime import RuntimeCloud

    cloud = RuntimeCloud(region="cn-beijing", credential_file="")
    cloud.call = AsyncMock(
        side_effect=[
            {
                "AgentKitRuntimes": [{"RuntimeId": "r-1", "Name": "other"}],
                "NextToken": "next",
            },
            {"AgentKitRuntimes": [{"RuntimeId": "r-2", "Name": "match"}]},
        ]
    )
    cloud.get = AsyncMock(side_effect=AssertionError("Must not expand details"))
    assert await cloud.find_runtimes("match") == [{"RuntimeId": "r-2", "Name": "match"}]


@pytest.mark.asyncio
async def test_runtime_name_pagination_repeated_token_fails_closed():
    from veadk.integrations.mpa.managed.runtime import RuntimeCloud
    from veadk.integrations.mpa.managed.database import DeploymentError

    cloud = RuntimeCloud(region="cn-beijing", credential_file="")
    cloud.call = AsyncMock(return_value={"AgentKitRuntimes": [], "NextToken": "repeat"})
    with pytest.raises(DeploymentError):
        await cloud.find_runtimes("name")
    assert cloud.call.await_count == 2


@pytest.mark.asyncio
async def test_verified_own_workspace_can_be_reused(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed.pg_bootstrap import agent_business_scope
    from tests.integrations.mpa_managed.test_auto_pg import workspace

    names, profile, runtime, _, pg = setup(tmp_path, monkeypatch)
    pg.find.return_value = [
        {
            **workspace("mpa_agent_test-name", "ws-own"),
            "workspace_tags": [
                {
                    "key": "veadk-pg-scope",
                    "value": agent_business_scope(
                        "account", profile.region, "default", "mi-test"
                    ),
                },
                {"key": "veadk-pg-purpose", "value": "business"},
                {"key": "veadk-pg-database", "value": "aidb"},
            ],
        }
    ]
    assert (
        await names.check_creation_name(
            profile, runtime, agent_id="mi-test", name="test-name", owner="local"
        )
        == "account"
    )


@pytest.mark.asyncio
async def test_creation_account_snapshot_is_checked_before_prerequisites(
    tmp_path, monkeypatch
):
    from veadk.integrations.mpa.managed import service
    from veadk.integrations.mpa.managed.database import DeploymentError

    profile, _, _, _ = recovery_setup(tmp_path, monkeypatch)
    cloud = SimpleNamespace(account_id=AsyncMock(return_value="changed-account"))
    monkeypatch.setattr(service, "RuntimeCloud", lambda **kw: cloud)
    identity = AsyncMock()
    monkeypatch.setattr(service, "ensure_workload_identity", identity)
    with pytest.raises(DeploymentError, match="account snapshot"):
        await service.provision(
            profile,
            agent_id="mi-test",
            owner="local",
            expected_account="original-account",
        )
    identity.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
async def test_sdk_runtime_list_tags_allow_retry_when_detail_omits_tags(
    tmp_path, monkeypatch, provider
):
    from agentkit.sdk.runtime.types import GetRuntimeResponse

    names, profile, runtime, _, _ = setup(tmp_path, monkeypatch)
    profile = replace(profile, values={**profile.values, "cloud_provider": provider})
    runtime.find_runtimes.return_value = [
        {
            "RuntimeId": "r-own",
            "Name": "test-name",
            "Tags": [
                {"Key": "veadk:owner", "Value": "local"},
                {"Key": "veadk:mpa-instance-id", "Value": "mi-test"},
            ],
        }
    ]
    runtime.get.return_value = GetRuntimeResponse.model_validate(
        {"RuntimeId": "r-own", "Envs": [{"Key": "MPA_AGENT_ID", "Value": "mi-test"}]}
    ).model_dump(by_alias=True, exclude_none=True)
    assert "Tags" not in runtime.get.return_value
    assert (
        await names.check_creation_name(
            profile, runtime, agent_id="mi-test", name="test-name", owner="local"
        )
        == "account"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tag_key,wrong",
    [("veadk:owner", "foreign"), ("veadk:mpa-instance-id", "mi-foreign")],
)
@pytest.mark.parametrize("source", ["list", "detail"])
async def test_runtime_ownership_contradiction_never_hides_in_other_response(
    tmp_path, monkeypatch, tag_key, wrong, source
):
    names, profile, runtime, _, _ = setup(tmp_path, monkeypatch)
    own = {"veadk:owner": "local", "veadk:mpa-instance-id": "mi-test"}
    other = {**own, tag_key: wrong}
    listing, detail = (other, own) if source == "list" else (own, other)
    runtime.find_runtimes.return_value = [
        {
            "RuntimeId": "r-own",
            "Tags": [{"Key": k, "Value": v} for k, v in listing.items()],
        }
    ]
    runtime.get.return_value = {
        "Envs": [{"Key": "MPA_AGENT_ID", "Value": "mi-test"}],
        "Tags": [{"Key": k, "Value": v} for k, v in detail.items()],
    }
    with pytest.raises(names.NameCheckError, match="runtimeNameTaken"):
        await names.check_creation_name(
            profile, runtime, agent_id="mi-test", name="test-name", owner="local"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "managed,agent_tag",
    [
        (None, None),
        ("other", "own"),
        ("mpa-deployment", "foreign"),
        ("mpa-deployment", None),
    ],
)
async def test_worker_requires_creation_tags_not_a_legacy_agent_id_tag(
    tmp_path, monkeypatch, managed, agent_tag
):
    names, profile, runtime, worker, _ = setup(tmp_path, monkeypatch)
    worker.find.return_value = [{"ToolId": "t-existing"}]
    labels = {"MPA_AGENT_ID": "mi-test"}
    if managed is not None:
        labels["managed_by"] = managed
    if agent_tag is not None:
        labels["mpa_agent_key"] = agent_suffix(
            "account", profile.region, "mi-test" if agent_tag == "own" else "mi-foreign"
        )
    worker.get.return_value = {
        "Envs": [{"Key": "MPA_AGENT_ID", "Value": "mi-test"}],
        "Tags": [{"Key": k, "Value": v} for k, v in labels.items()],
    }
    with pytest.raises(names.NameCheckError, match="runtimeNameTaken"):
        await names.check_creation_name(
            profile, runtime, agent_id="mi-test", name="test-name", owner="local"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope_account,expected", [("account", True), ("foreign", False), ("", False)]
)
async def test_missing_runtime_owner_needs_verified_original_creation_account(
    tmp_path, monkeypatch, scope_account, expected
):
    names, profile, runtime, _, _ = setup(tmp_path, monkeypatch)
    runtime.find_runtimes.return_value = [{"RuntimeId": "r-own", "Name": "test-name"}]
    runtime.get.return_value = {"Envs": [{"Key": "MPA_AGENT_ID", "Value": "mi-test"}]}
    if expected:
        assert (
            await names.check_creation_name(
                profile,
                runtime,
                agent_id="mi-test",
                name="test-name",
                owner="local",
                verified_creation_account=scope_account,
            )
            == "account"
        )
    else:
        with pytest.raises(names.NameCheckError):
            await names.check_creation_name(
                profile,
                runtime,
                agent_id="mi-test",
                name="test-name",
                owner="local",
                verified_creation_account=scope_account,
            )


@pytest.mark.asyncio
async def test_verified_creation_account_never_overrides_foreign_runtime_owner(
    tmp_path, monkeypatch
):
    names, profile, runtime, _, _ = setup(tmp_path, monkeypatch)
    runtime.find_runtimes.return_value = [
        {"RuntimeId": "r-other", "Tags": [{"Key": "veadk:owner", "Value": "foreign"}]}
    ]
    runtime.get.return_value = {"Envs": [{"Key": "MPA_AGENT_ID", "Value": "mi-test"}]}
    with pytest.raises(names.NameCheckError, match="runtimeNameTaken"):
        await names.check_creation_name(
            profile,
            runtime,
            agent_id="mi-test",
            name="test-name",
            owner="local",
            verified_creation_account="account",
        )


def test_saved_name_scope_requires_owner_and_identical_secret_free_inputs(tmp_path):
    import json
    import time
    from veadk.integrations.mpa.managed.tasks import CreationTasks, TaskError

    tasks = CreationTasks(tmp_path / "tasks.db")
    payload = {
        "requestId": "original-request",
        "name": "test-name",
        "agentId": "mi-test",
        "region": "ap-southeast-1",
        "provider": "byteplus",
        "description": "",
    }
    scope = {"provider": "byteplus", "account": "account", "region": "ap-southeast-1"}
    with tasks.db() as db:
        db.execute(
            "INSERT INTO tasks (id,owner,request,payload,state,stage,supervisor,updated,name_scope) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "original-task",
                "owner",
                payload["requestId"],
                json.dumps(payload, sort_keys=True),
                "failed",
                "verifying",
                0,
                time.time(),
                json.dumps(scope),
            ),
        )
    assert tasks.name_scope_for_request("owner", payload) == scope
    assert tasks.name_scope_for_request("other-owner", payload) is None
    assert (
        tasks.name_scope_for_request("owner", {**payload, "requestId": "new-request"})
        is None
    )
    with pytest.raises(TaskError, match="different inputs"):
        tasks.name_scope_for_request("owner", {**payload, "description": "changed"})
