from __future__ import annotations

import asyncio

import pytest

from frontend.server.vibe_task.models import (
    CredentialUpload,
    CreateTaskRequest,
    IntentSummary,
    IntentSummaryUpdate,
    TaskState,
)
from frontend.server.vibe_task.service import VibeTaskError, VibeTaskService


@pytest.mark.asyncio
async def test_task_lifecycle_intent_events_and_secret_receipt() -> None:
    service = VibeTaskService()
    task = await service.create("owner-a", CreateTaskRequest(goal="Build an Agent"))
    assert task.expires_at > task.created_at
    assert task.intent_revision == 0

    task = await service.configure_credentials(
        "owner-a",
        task.task_id,
        CredentialUpload(accessKeyId="ak", secretAccessKey="sk"),
    )
    assert task.credentials_configured is True

    current = await service.get_intent("owner-a", task.task_id)
    updated = await service.update_intent(
        "owner-a",
        task.task_id,
        IntentSummaryUpdate(
            expectedRevision=current.revision,
            summary=IntentSummary(goal="Build an Agent", successCriteria=["invoke"]),
        ),
    )
    assert updated.revision == current.revision + 1

    events = await service.repository.events_after("owner-a", task.task_id, 0)
    assert [event.event_type for event in events] == [
        "task.created",
        "credentials.configured",
        "vibe.intent.updated",
    ]
    assert "ak" not in repr(events)
    assert "sk" not in repr(events)

    stopped = await service.stop("owner-a", task.task_id)
    assert stopped.state == TaskState.CANCELLED
    assert stopped.credentials_configured is False
    assert (await service.stop("owner-a", task.task_id)).state == TaskState.CANCELLED


@pytest.mark.asyncio
async def test_owner_revision_and_delete_contracts() -> None:
    service = VibeTaskService()
    task = await service.create("owner-a", CreateTaskRequest(goal="Build"))
    with pytest.raises(VibeTaskError) as foreign:
        await service.require("owner-b", task.task_id)
    assert foreign.value.status_code == 404

    current = await service.get_intent("owner-a", task.task_id)
    with pytest.raises(VibeTaskError) as stale:
        await service.update_intent(
            "owner-a",
            task.task_id,
            IntentSummaryUpdate(
                expectedRevision=current.revision + 1,
                summary=IntentSummary(goal="Build"),
            ),
        )
    assert stale.value.status_code == 409
    assert await service.delete("owner-a", task.task_id) is True
    assert await service.delete("owner-a", task.task_id) is False


@pytest.mark.asyncio
async def test_event_stream_replays_after_sequence_and_closes_on_terminal() -> None:
    service = VibeTaskService()
    task = await service.create("owner", CreateTaskRequest(goal="Build"))
    await service.stop("owner", task.task_id)
    received = [event async for event in service.events("owner", task.task_id, after=1)]
    assert [event.sequence for event in received] == [2]
    assert received[0].event_type == "task.cancelled"


@pytest.mark.asyncio
async def test_stream_heartbeat_does_not_mutate_persisted_sequence(monkeypatch) -> None:
    service = VibeTaskService()
    task = await service.create("owner", CreateTaskRequest(goal="Build"))

    async def immediate_timeout(awaitable, timeout):
        del timeout
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", immediate_timeout)
    iterator = service.events("owner", task.task_id, after=1)
    heartbeat = await anext(iterator)
    assert heartbeat.event_type == "heartbeat"
    await iterator.aclose()
    assert (await service.require("owner", task.task_id)).last_sequence == 1
