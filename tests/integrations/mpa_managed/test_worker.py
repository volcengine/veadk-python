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

import asyncio
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed.worker import (
    WorkerCloud,
    _missing_worker_metadata,
    ensure_worker,
)
from veadk.integrations.mpa.managed.config import Worker
from veadk.integrations.mpa.managed.database import DeploymentError, agent_suffix
from tests.integrations.mpa_managed.test_agent_deployment import Registry


def test_lost_worker_response_reuses_token_and_scoped_identity(monkeypatch):
    from veadk.integrations.mpa.managed import diagnostics

    monkeypatch.setattr(diagnostics.asyncio, "sleep", AsyncMock())

    async def run():
        registry = Registry()
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.side_effect = TimeoutError()
        options = Worker(image="registry.example/worker:v1")
        with pytest.raises(TimeoutError):
            await ensure_worker(
                registry, cloud, options, account="a", region="r", agent_id="agent"
            )
        token = registry.row["worker_token"]
        with pytest.raises(TimeoutError):
            await ensure_worker(
                registry, cloud, options, account="a", region="r", agent_id="agent"
            )
        assert [c.args[0]["ClientToken"] for c in cloud.create.call_args_list] == [
            token
        ] * 8
        assert "Envs" not in str(registry.row)

    asyncio.run(run())


def test_worker_ownership_collision_stops_before_creation():
    async def run():
        cloud = AsyncMock()
        cloud.find.return_value = [{"ToolId": "t-other", "Tags": []}]
        with pytest.raises(DeploymentError):
            await ensure_worker(
                Registry(),
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id="agent",
            )
        cloud.create.assert_not_called()

    asyncio.run(run())


def test_managed_worker_create_includes_tos_output_mount():
    async def run():
        registry = Registry()
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.return_value = "t-created"
        cloud.get.return_value = {
            "ToolId": "t-created",
            "ProjectName": "default",
            "Status": "Ready",
            "Tags": [
                {"Key": "managed_by", "Value": "mpa-deployment"},
                {
                    "Key": "mpa_agent_key",
                    "Value": agent_suffix("a", "r", "agent"),
                },
            ],
            "Envs": [{"Key": "MPA_AGENT_ID", "Value": "agent"}],
            "TosMountConfig": {
                "EnableTos": True,
                "MountPoints": [
                    {
                        "BucketName": "mpa-output",
                        "BucketPath": "/sandbox-session/default/default",
                        "Endpoint": "http://tos-r.ivolces.com",
                        "LocalMountPath": "/data/output",
                        "ReadOnly": False,
                    }
                ],
            },
        }
        options = Worker(
            image="worker:v1",
            tos_access_key="tos-ak",
            tos_secret_key="tos-sk",
            tos_bucket="mpa-output",
        )

        assert (
            await ensure_worker(
                registry,
                cloud,
                options,
                account="a",
                region="r",
                agent_id="agent",
            )
            == "t-created"
        )
        request = cloud.create.await_args.args[0]
        config = request["TosMountConfig"]
        assert config["Credentials"] == {
            "AccessKeyId": "tos-ak",
            "SecretAccessKey": "tos-sk",
        }
        assert config["MountPoints"][0]["LocalMountPath"] == "/data/output"
        assert "tos-ak" not in str(registry.row)
        assert "tos-sk" not in str(registry.row)

    asyncio.run(run())


def test_worker_tos_metadata_mismatch_fails_closed():
    expected = {
        "EnableTos": True,
        "MountPoints": [
            {
                "BucketName": "mpa-output",
                "BucketPath": "/sandbox-session/default/default",
                "Endpoint": "http://tos-r.ivolces.com",
                "LocalMountPath": "/data/output",
                "ReadOnly": False,
            }
        ],
    }

    with pytest.raises(DeploymentError, match="TOS output mount"):
        _missing_worker_metadata(
            {"TosMountConfig": {"EnableTos": True, "MountPoints": []}},
            tool_id="t-one",
            project="default",
            owned={"managed_by": "mpa-deployment", "mpa_agent_key": "key"},
            agent_id="agent",
            managed=True,
            expected_tos=expected,
        )


def test_worker_discovery_follows_cursor_even_after_short_page():
    cloud = WorkerCloud(None)
    target = {"Name": "target", "ToolId": "target-id"}
    cloud.call = AsyncMock(
        side_effect=[
            {"Tools": [{"Name": "other", "ToolId": "other-id"}], "NextToken": "next"},
            {"Tools": [target]},
        ]
    )
    assert asyncio.run(cloud.find("target")) == [target]
    assert [call.kwargs for call in cloud.call.call_args_list] == [
        {"MaxResults": 100},
        {"MaxResults": 100, "NextToken": "next"},
    ]


def test_worker_discovery_stops_on_full_final_page():
    cloud = WorkerCloud(None)
    cloud.call = AsyncMock(return_value={"Tools": [{"Name": "other"}] * 100})
    assert asyncio.run(cloud.find("target")) == []
    cloud.call.assert_awaited_once()


def test_worker_discovery_deduplicates_ids_but_retains_distinct_name_collisions():
    cloud = WorkerCloud(None)
    first = {"Name": "target", "ToolId": "one"}
    second = {"Name": "target", "ToolId": "two"}
    cloud.call = AsyncMock(
        side_effect=[
            {"Tools": [first], "NextToken": "next"},
            {"Tools": [first, second]},
        ]
    )
    assert asyncio.run(cloud.find("target")) == [first, second]


def test_worker_discovery_rejects_repeated_cursor_without_partial_matches():
    cloud = WorkerCloud(None)
    cloud.call = AsyncMock(
        side_effect=[
            {"Tools": [{"Name": "target", "ToolId": "one"}], "NextToken": "same"},
            {"Tools": [], "NextToken": "same"},
        ]
    )
    with pytest.raises(DeploymentError, match="repeated pagination token"):
        asyncio.run(cloud.find("target"))
    assert cloud.call.await_count == 2


def test_worker_discovery_rejects_page_limit_without_partial_matches():
    cloud = WorkerCloud(None)
    cloud.call = AsyncMock(
        side_effect=[{"Tools": [], "NextToken": str(i)} for i in range(1000)]
    )
    with pytest.raises(DeploymentError, match="pagination limit"):
        asyncio.run(cloud.find("target"))
    assert cloud.call.await_count == 1000


def test_worker_discovery_propagates_provider_failure():
    cloud = WorkerCloud(None)
    cloud.call = AsyncMock(
        side_effect=[{"Tools": [], "NextToken": "next"}, TimeoutError()]
    )
    with pytest.raises(TimeoutError):
        asyncio.run(cloud.find("target"))
