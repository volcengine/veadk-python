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

"""Offline contracts for exclusive MPA resource cleanup."""

import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed.database import agent_suffix
from veadk.integrations.mpa.managed.deletion import (
    OwnedResourceCleanup,
    ResourceDeletionError,
)


class Entry:
    def __init__(self, record=None, others=()):
        self.record = copy.deepcopy(record or {})
        self.others = list(others)
        self.saved = []

    async def read(self):
        return copy.deepcopy(self.record)

    async def save(self, record):
        self.record = copy.deepcopy(record)
        self.saved.append(copy.deepcopy(record))

    async def other_records(self):
        return self.others


def setup(record=None, others=(), runtimes=()):
    suffix = agent_suffix("account", "cn-beijing", "mi-one")
    tags = [
        {"Key": "managed_by", "Value": "mpa-deployment"},
        {"Key": "mpa_agent_key", "Value": suffix},
    ]
    record = (
        record
        if record is not None
        else {
            "runtime_id": "r-one",
            "worker_id": "t-one",
            "worker_managed": True,
            "skill_space_id": "ss-one",
            "skill_space_managed": True,
        }
    )
    entry = Entry(record, others)
    cloud = AsyncMock()
    cloud.list_runtimes.return_value = list(runtimes)
    cloud.get_skill_space.return_value = {
        "Id": "ss-one",
        "Tags": tags,
        "ProjectName": "default",
    }
    worker = AsyncMock()
    worker.get.return_value = {
        "ToolId": "t-one",
        "Tags": tags,
        "ProjectName": "default",
        "Envs": [{"Key": "MPA_AGENT_ID", "Value": "mi-one"}],
    }
    runtime = {
        "RuntimeId": "r-one",
        "ToolId": "t-one",
        "ProjectName": "default",
        "Envs": [{"Key": "SKILL_SPACE_ID", "Value": "ss-one"}],
    }
    cleanup = OwnedResourceCleanup(
        entry=entry,
        cloud=cloud,
        worker=worker,
        account="account",
        region="cn-beijing",
        agent_id="mi-one",
        runtime=runtime,
    )
    return cleanup, entry, cloud, worker


def test_exclusive_cleanup_is_ordered_and_durable():
    async def run():
        cleanup, entry, cloud, worker = setup()
        events = []
        worker.delete.side_effect = lambda resource: events.append(("worker", resource))
        cloud.delete_skill_space.side_effect = lambda resource: events.append(
            ("skills", resource)
        )
        plan = await cleanup.preview()
        assert [item["stage"] for item in plan["cleanupPlan"]] == [
            "worker_template",
            "skill_space",
        ]
        assert [item["resourceId"] for item in plan["cleanupPlan"]] == [
            "t-one",
            "ss-one",
        ]
        await cleanup.delete_resources()
        assert events == [("worker", "t-one"), ("skills", "ss-one")]
        assert entry.record["deletion"]["worker_template"] == "deleted"
        assert entry.record["deletion"]["skill_space"] == "deleted"
        assert entry.record["state"] == "deleting"
        await cleanup.mark_runtime_deleted()
        assert entry.record["state"] == "deleted"

    asyncio.run(run())


@pytest.mark.parametrize("reference", ["registry", "runtime"])
def test_shared_resources_are_preserved(reference):
    async def run():
        others = (
            [{"worker_id": "t-one", "skill_space_id": "ss-one"}]
            if reference == "registry"
            else []
        )
        runtimes = (
            [
                {
                    "RuntimeId": "r-other",
                    "ToolId": "t-one",
                    "Envs": [{"Key": "SKILL_SPACE_ID", "Value": "ss-one"}],
                }
            ]
            if reference == "runtime"
            else []
        )
        cleanup, _, cloud, worker = setup(others=others, runtimes=runtimes)
        plan = await cleanup.preview()
        assert plan["cleanupPlan"] == []
        assert len(plan["retainedResources"]) == 2
        assert all(item["reason"] == "shared" for item in plan["retainedResources"])
        await cleanup.delete_resources()
        worker.delete.assert_not_awaited()
        cloud.delete_skill_space.assert_not_awaited()

    asyncio.run(run())


def test_unregistered_resources_are_preserved():
    async def run():
        cleanup, _, cloud, worker = setup(record={})
        plan = await cleanup.preview()
        assert plan["cleanupPlan"] == []
        assert all(item["reason"] == "unproven" for item in plan["retainedResources"])
        cloud.list_runtimes.assert_not_awaited()
        worker.delete.assert_not_awaited()

    asyncio.run(run())


def test_tag_conflict_blocks_before_any_deletion():
    async def run():
        cleanup, _, cloud, worker = setup()
        cloud.get_skill_space.return_value["Tags"] = []
        with pytest.raises(ResourceDeletionError, match="ownership"):
            await cleanup.delete_resources()
        worker.delete.assert_not_awaited()
        cloud.delete_skill_space.assert_not_awaited()

    asyncio.run(run())


def test_partial_failure_retries_without_redeleting_completed_worker():
    async def run():
        cleanup, entry, cloud, worker = setup()
        cloud.delete_skill_space.side_effect = RuntimeError(
            "sensitive provider details"
        )
        with pytest.raises(ResourceDeletionError, match="skill_space") as caught:
            await cleanup.delete_resources()
        assert "sensitive" not in str(caught.value)
        assert entry.record["deletion"]["worker_template"] == "deleted"
        cloud.delete_skill_space.side_effect = None
        await cleanup.delete_resources()
        worker.delete.assert_awaited_once()
        assert entry.record["deletion"]["skill_space"] == "deleted"

    asyncio.run(run())


@pytest.mark.parametrize("change", ["binding", "discovery", "pending"])
def test_conflicts_fail_closed(change):
    async def run():
        cleanup, entry, cloud, worker = setup()
        if change == "binding":
            entry.record["runtime_id"] = "r-other"
        elif change == "pending":
            entry.record["pending"] = True
        else:
            cloud.list_runtimes.side_effect = RuntimeError("private error")
        with pytest.raises(ResourceDeletionError):
            await cleanup.delete_resources()
        worker.delete.assert_not_awaited()
        cloud.delete_skill_space.assert_not_awaited()

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["get", "delete"])
def test_missing_owned_resource_is_idempotent(phase):
    from agentkit.toolkit.errors import ApiError

    async def run():
        cleanup, entry, cloud, worker = setup()
        missing = ApiError("redacted", error_code="ResourceNotFound")
        if phase == "get":
            worker.get.side_effect = missing
            cloud.get_skill_space.side_effect = missing
        else:
            worker.delete.side_effect = missing
            cloud.delete_skill_space.side_effect = missing
        await cleanup.delete_resources()
        assert entry.record["deletion"]["worker_template"] == "deleted"
        assert entry.record["deletion"]["skill_space"] == "deleted"

    asyncio.run(run())


def test_references_are_rechecked_after_preview():
    async def run():
        cleanup, entry, cloud, worker = setup()
        assert len((await cleanup.preview())["cleanupPlan"]) == 2
        entry.others.append({"worker_id": "t-one", "skill_space_id": "ss-one"})
        await cleanup.delete_resources()
        worker.delete.assert_not_awaited()
        cloud.delete_skill_space.assert_not_awaited()

    asyncio.run(run())


def test_cancelled_cleanup_keeps_durable_intent():
    async def run():
        cleanup, entry, cloud, worker = setup()
        worker.delete.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await cleanup.delete_resources()
        assert entry.record["deletion"]["worker_template"] == "deleting"
        cloud.delete_skill_space.assert_not_awaited()

    asyncio.run(run())


def test_legacy_cleanup_does_not_create_or_contact_registry(monkeypatch):
    from veadk.integrations.mpa.managed.deletion import owned_resource_cleanup
    from unittest.mock import Mock

    factory = Mock(side_effect=AssertionError("no registry provisioning"))
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.deletion.AgentDeploymentRegistry", factory
    )

    async def run():
        cloud = AsyncMock()
        async with owned_resource_cleanup(
            runtime={"RuntimeId": "r-legacy"},
            agent_id="mi-old",
            region="cn-beijing",
            cloud=cloud,
        ) as cleanup:
            assert (await cleanup.preview())["cleanupPlan"] == []
            await cleanup.delete_resources()
            await cleanup.mark_runtime_deleted()
        cloud.account_id.assert_not_awaited()
        factory.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_cleanup_cloud_requests_and_complete_discovery(provider):
    from veadk.integrations.mpa.managed.runtime import RuntimeCloud
    from veadk.integrations.mpa.managed.worker import WorkerCloud

    async def run():
        cloud = RuntimeCloud(
            region="test-region", credential_file="", provider=provider
        )
        cloud.call = AsyncMock(
            side_effect=[
                {"AgentKitRuntimes": [{"RuntimeId": "r-one"}], "NextToken": "next"},
                {"AgentKitRuntimes": [{"RuntimeId": "r-two"}]},
                {},
            ]
        )
        cloud.get = AsyncMock(
            side_effect=[
                {"RuntimeId": "r-one", "Envs": []},
                {"RuntimeId": "r-two", "ToolId": "t-one"},
            ]
        )
        result = await cloud.list_runtimes()
        assert result[1]["ToolId"] == "t-one"
        assert cloud.call.call_args_list[1].args[1].next_token == "next"
        await cloud.delete_skill_space("ss-one")
        method, request = cloud.call.call_args.args
        assert method == "delete_skill_space" and request.id == "ss-one"
        assert cloud.call.call_args.kwargs["skills"] is True
        worker = WorkerCloud(cloud)
        worker.call = AsyncMock()
        await worker.delete("t-one")
        worker.call.assert_awaited_once_with(
            "delete_tool", "DeleteToolRequest", ToolId="t-one"
        )

    asyncio.run(run())


def test_changed_target_binding_blocks_cleanup():
    async def run():
        cleanup, _, cloud, worker = setup(
            runtimes=[{"RuntimeId": "r-one", "ToolId": "t-replacement"}]
        )
        with pytest.raises(ResourceDeletionError, match="resource_binding_conflict"):
            await cleanup.delete_resources()
        worker.delete.assert_not_awaited()
        cloud.delete_skill_space.assert_not_awaited()

    asyncio.run(run())


def test_runtime_reference_discovery_uses_bounded_parallel_reads():
    from veadk.integrations.mpa.managed.runtime import RuntimeCloud

    async def run():
        cloud = RuntimeCloud(region="cn-beijing", credential_file="")
        cloud.call = AsyncMock(
            return_value={
                "AgentKitRuntimes": [{"RuntimeId": f"r-{i}"} for i in range(12)]
            }
        )
        active = peak = 0

        async def get(runtime_id):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            await asyncio.sleep(0.001)
            active -= 1
            return {"RuntimeId": runtime_id}

        cloud.get = get
        records = await cloud.list_runtimes()
        assert 1 < peak <= 4
        assert [r["RuntimeId"] for r in records] == [f"r-{i}" for i in range(12)]

    asyncio.run(run())


def test_deletion_identity_cache_rechecks_rotated_credentials(monkeypatch):
    from veadk.integrations.mpa.managed.credentials import Credentials
    from veadk.integrations.mpa.managed.runtime import RuntimeCloud
    from unittest.mock import Mock

    selected = [Credentials("test-ak", "test-sk", "session-one")]
    identity = Mock(
        side_effect=[{"AccountId": "one"}, {"AccountId": "one"}, {"AccountId": "other"}]
    )
    monkeypatch.setattr("agentkit.auth.sts.get_caller_identity", identity)
    cloud = RuntimeCloud(
        region="cn-beijing",
        credential_file="",
        credentials=lambda: selected[0],
        cache_identity=True,
    )
    cloud._credentials()
    cloud._credentials()
    assert identity.call_count == 1
    selected[0] = Credentials("test-ak", "test-sk", "session-two")
    cloud._credentials()
    assert identity.call_count == 2
    selected[0] = Credentials("other-ak", "other-sk", "session-three")
    with pytest.raises(Exception, match="changed accounts"):
        cloud._credentials()
    assert identity.call_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("component", ["runtime", "worker"])
async def test_deletion_rejects_unresolved_image_updates(component):
    cleanup, entry, cloud, worker = setup()
    entry.record["image_updates"] = {
        component: {"phase": "uncertain", "target": "public/repo:tag"}
    }
    with pytest.raises(ResourceDeletionError, match="active_image_update"):
        await cleanup.delete_resources()
    worker.delete.assert_not_awaited()
    cloud.delete_skill_space.assert_not_awaited()
