import asyncio
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed.worker import WorkerCloud, ensure_worker
from veadk.integrations.mpa.managed.config import Worker
from veadk.integrations.mpa.managed.database import DeploymentError
from tests.integrations.mpa_managed.test_agent_deployment import Registry


def test_lost_worker_response_reuses_token_and_scoped_identity():
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
            token,
            token,
        ]
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
