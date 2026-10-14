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
