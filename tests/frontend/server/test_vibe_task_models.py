from __future__ import annotations

from pydantic import ValidationError
import pytest

from frontend.server.vibe_task.models import (
    CredentialUpload,
    CreateTaskRequest,
    IntentSummary,
    TaskStage,
    TaskState,
    TaskStatus,
)


def test_create_task_normalizes_goal_and_rejects_extra_fields() -> None:
    assert CreateTaskRequest(goal="  build an agent  ").goal == "build an agent"
    with pytest.raises(ValidationError):
        CreateTaskRequest.model_validate({"goal": "ok", "unknown": True})
    with pytest.raises(ValidationError):
        CreateTaskRequest(goal="   ")


def test_credentials_never_serialize_or_repr_secret_values() -> None:
    body = CredentialUpload(
        accessKeyId="access-value",
        secretAccessKey="secret-value",
        sessionToken="token-value",
    )
    assert body.model_dump(by_alias=True) == {}
    rendered = repr(body)
    assert "access-value" not in rendered
    assert "secret-value" not in rendered
    assert "token-value" not in rendered


def test_intent_revision_advances_and_status_terminal_contract() -> None:
    summary = IntentSummary(goal="Agent")
    updated = summary.next_revision()
    assert updated.revision == 1
    assert updated.updated_at

    status = TaskStatus(
        taskId="vt-000000000000-000000000000000000000000",
        goal="Agent",
        state=TaskState.COMPLETED,
        stage=TaskStage.DONE,
        createdAt="now",
        expiresAt="later",
    )
    assert status.terminal is True
    assert status.model_dump(by_alias=True)["taskId"] == status.task_id
