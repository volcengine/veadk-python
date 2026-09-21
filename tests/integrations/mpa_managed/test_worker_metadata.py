"""Initialization metadata may lag creation, but conflicts never become retries."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.integrations.mpa_managed.test_agent_deployment import Registry
from tests.integrations.mpa_managed.test_worker_recovery import ready
from veadk.integrations.mpa.managed import diagnostics
from veadk.integrations.mpa.managed.config import Worker
from veadk.integrations.mpa.managed.database import DeploymentError
from veadk.integrations.mpa.managed.worker import ensure_worker


def complete():
    return {**ready(), "ProjectName": "default"}


def intent():
    registry = Registry()
    registry.row = {
        "worker_id": "t-test",
        "worker_managed": True,
        "worker_token": "intent",
        "worker_hash": "digest",
    }
    return registry


async def ensure(registry, cloud, **kwargs):
    return await ensure_worker(
        registry,
        cloud,
        Worker(image="worker:v1"),
        account="a",
        region="r",
        agent_id="agent",
        **kwargs,
    )


@pytest.mark.parametrize(
    "status",
    ["Creating", "Pending", "Starting", "Initializing", "Provisioning", "", None],
)
def test_initial_metadata_is_waited_for_without_recreating(monkeypatch, status):
    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.return_value = "t-test"
        cloud.get.side_effect = [
            {"Status": status},
            {**complete(), "Status": "Starting", "Tags": None},
            complete(),
        ]
        events = []
        with diagnostics.diagnostic_scope(events.append):
            assert await ensure(Registry(), cloud) == "t-test"
        cloud.create.assert_awaited_once()
        assert [c.args[0] for c in sleep.call_args_list] == [5, 10]
        assert {e["operation"] for e in events} == {
            "worker_id",
            "worker_project",
            "worker_managed_by",
            "worker_agent_key",
        }
        assert all(
            e["category"] == "metadata_pending" and e["outcome"] == "retrying"
            for e in events
        )

    asyncio.run(run())


@pytest.mark.parametrize(
    "field", ["ToolId", "ProjectName", "managed_by", "mpa_agent_key", "MPA_AGENT_ID"]
)
def test_present_conflict_wins_over_other_missing_fields(monkeypatch, field):
    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        tool: dict[str, object] = {"Status": "Creating"}
        if field in {"ToolId", "ProjectName"}:
            tool[field] = "private-conflicting-value"
        elif field == "MPA_AGENT_ID":
            tool["Envs"] = [{"Key": field, "Value": "private-conflicting-value"}]
        else:
            tool["Tags"] = [{"Key": field, "Value": "private-conflicting-value"}]
        cloud = AsyncMock()
        cloud.get.return_value = tool
        events = []
        with (
            diagnostics.diagnostic_scope(events.append),
            pytest.raises(DeploymentError),
        ):
            await ensure(intent(), cloud)
        cloud.get.assert_awaited_once()
        sleep.assert_not_called()
        cloud.create.assert_not_called()
        expected = {
            "ToolId": "worker_id",
            "ProjectName": "worker_project",
            "managed_by": "worker_managed_by",
            "mpa_agent_key": "worker_agent_key",
            "MPA_AGENT_ID": "worker_agent_binding",
        }[field]
        assert events == [
            {
                "operation": expected,
                "category": "ownership",
                "attempt": 1,
                "outcome": "failed",
            }
        ]
        assert "private-conflicting-value" not in str(events)

    asyncio.run(run())


@pytest.mark.parametrize(
    "status", ["Ready", "Failed", "Error", "Deleted", "Deleting", "UnknownStatus"]
)
def test_incomplete_ready_terminal_unknown_never_wait(monkeypatch, status):
    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        cloud = AsyncMock()
        cloud.get.return_value = {"ToolId": "t-test", "Status": status}
        events = []
        with (
            diagnostics.diagnostic_scope(events.append),
            pytest.raises(DeploymentError),
        ):
            await ensure(intent(), cloud)
        cloud.get.assert_awaited_once()
        sleep.assert_not_called()
        assert events and all(e["outcome"] == "failed" for e in events)

    asyncio.run(run())


@pytest.mark.parametrize("missing", ["worker_token", "worker_hash", "worker_managed"])
def test_absent_creation_proof_never_grants_grace(monkeypatch, missing):
    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        registry = intent()
        registry.row.pop(missing)
        cloud = AsyncMock()
        cloud.get.return_value = {"Status": "Creating"}
        with pytest.raises(DeploymentError):
            await ensure(registry, cloud)
        cloud.get.assert_awaited_once()
        sleep.assert_not_called()

    asyncio.run(run())


def test_metadata_exhaustion_is_bounded_and_retains_binding(monkeypatch):
    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        cloud = AsyncMock()
        cloud.get.return_value = {
            "ToolId": "t-test",
            "Status": "Creating",
            "ProjectName": "default",
        }
        registry = intent()
        events = []
        with (
            diagnostics.diagnostic_scope(events.append),
            pytest.raises(DeploymentError),
        ):
            await ensure(registry, cloud)
        assert cloud.get.await_count == 4
        assert [c.args[0] for c in sleep.call_args_list] == [5, 10, 20]
        assert (
            events[-1]["category"] == "metadata_missing" and events[-1]["attempt"] == 4
        )
        assert registry.row["worker_id"] == "t-test"
        cloud.create.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("cancel", [True, False])
def test_metadata_wait_obeys_cancel_and_stage_deadline(monkeypatch, cancel):
    async def run():
        waiting = asyncio.Event()

        async def sleep(_):
            waiting.set()
            await asyncio.Future()

        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        cloud = AsyncMock()
        cloud.get.return_value = {"Status": "Creating"}
        task = asyncio.create_task(
            ensure(intent(), cloud, timeout=10 if cancel else 0.02)
        )
        await asyncio.wait_for(waiting.wait(), 1)
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await task
        cloud.get.assert_awaited_once()
        cloud.create.assert_not_called()

    asyncio.run(run())


def test_existing_worker_retains_omitted_default_project_compatibility():
    async def run():
        cloud = AsyncMock()
        cloud.get.return_value = {"ToolId": "t-existing", "Status": "Ready"}
        assert (
            await ensure_worker(
                Registry(),
                cloud,
                Worker(existing_id="t-existing"),
                account="a",
                region="r",
                agent_id="agent",
            )
            == "t-existing"
        )
        cloud.create.assert_not_called()

    asyncio.run(run())


def test_metadata_budget_is_not_reset_by_complete_starting_response(monkeypatch):
    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        partial = {**complete(), "Status": "Starting", "Tags": []}
        full = {**complete(), "Status": "Starting"}
        cloud = AsyncMock()
        cloud.get.side_effect = [partial, full, partial, full, partial, full, partial]
        with pytest.raises(DeploymentError):
            await ensure(intent(), cloud)
        assert cloud.get.await_count == 7
        assert [c.args[0] for c in sleep.call_args_list] == [5, 5, 10, 5, 20, 5]
        cloud.create.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("empty", [None, ""])
def test_empty_project_metadata_can_become_visible(monkeypatch, empty):
    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        cloud = AsyncMock()
        cloud.get.side_effect = [
            {**complete(), "Status": "Creating", "ProjectName": empty},
            complete(),
        ]
        events = []
        with diagnostics.diagnostic_scope(events.append):
            assert await ensure(intent(), cloud) == "t-test"
        sleep.assert_awaited_once_with(5)
        assert events == [
            {
                "operation": "worker_project",
                "category": "metadata_pending",
                "attempt": 1,
                "outcome": "retrying",
            }
        ]

    asyncio.run(run())
