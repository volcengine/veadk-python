from __future__ import annotations

from uuid import UUID

import pytest

from frontend.server.vibe_task.models import CreateTaskRequest, IntentSummary, TaskEvent, TaskStage, TaskState, TaskStatus
from frontend.server.vibe_task.service import VibeTaskError, VibeTaskService


class SandboxStore:
    def __init__(self):
        self.deleted = []

    def capabilities(self):
        return {"enabled": True, "stateSource": "dev-sandbox"}

    async def create(self, owner, body):
        return self._status()

    async def get(self, owner, task_id):
        return self._status()

    async def list(self, owner):
        return [self._status()]

    async def get_intent(self, owner, task_id):
        return IntentSummary(revision=1, goal="Build")

    async def events_after(self, owner, task_id, sequence):
        if sequence == 0:
            return [TaskEvent(sequence=1, eventType="task.created", stage=TaskStage.DONE, timestamp="now")]
        return []

    async def delete(self, owner, task_id):
        self.deleted.append((owner, task_id))
        return True

    @staticmethod
    def _status():
        return TaskStatus(
            taskId="vt-4c1029697ee3-000000000000000000000000",
            goal="Build",
            state=TaskState.COMPLETED,
            stage=TaskStage.DONE,
            createdAt="now",
            expiresAt="later",
            lastSequence=1,
        )


@pytest.mark.asyncio
async def test_sandbox_service_reads_only_remote_boundary() -> None:
    store = SandboxStore()
    service = VibeTaskService(sandbox_store=store)
    body = CreateTaskRequest(requestId=UUID(int=1), goal="Build")
    assert (await service.create("owner", body)).state is TaskState.COMPLETED
    assert len(await service.list("owner")) == 1
    assert (await service.get_intent("owner", "task")).revision == 1
    assert [event.sequence async for event in service.events("owner", "task")] == [1]
    assert await service.delete("owner", "task") is True
    assert store.deleted == [("owner", "task")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "code"),
    [
        ("credentials", "VIBE_CREDENTIALS_NOT_READY"),
        ("intent", "VIBE_INTENT_UPDATE_NOT_READY"),
        ("stop", "VIBE_STOP_NOT_READY"),
    ],
)
async def test_sandbox_mutations_fail_explicitly_until_control_channel(
    operation, code
) -> None:
    service = VibeTaskService(sandbox_store=SandboxStore())
    with pytest.raises(VibeTaskError) as captured:
        if operation == "credentials":
            from frontend.server.vibe_task.models import CredentialUpload
            await service.configure_credentials("owner", "task", CredentialUpload(accessKeyId="ak", secretAccessKey="sk"))
        elif operation == "intent":
            from frontend.server.vibe_task.models import IntentSummaryUpdate
            await service.update_intent("owner", "task", IntentSummaryUpdate(expectedRevision=1, summary=IntentSummary(goal="Build")))
        else:
            await service.stop("owner", "task")
    assert captured.value.code == code
    assert captured.value.status_code == 501
