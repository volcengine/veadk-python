from __future__ import annotations

from uuid import UUID

from pydantic import ValidationError
import pytest

from frontend.server.vibe_task.models import TaskStage, TaskState, TaskStatus
from frontend.server.vibe_task.remote_state import (
    EVENT_CHAIN_GENESIS,
    REMOTE_EVENTS_PATH,
    REMOTE_REQUEST_PATH,
    REMOTE_RUNNER_RESULT_PATH,
    REMOTE_STATUS_PATH,
    RemoteStatusProjection,
    build_bootstrap_command,
    build_runner_command,
    make_event_record,
    project_status,
    replay_event_log,
    task_id_for,
)


def _status(task_id: str) -> TaskStatus:
    return TaskStatus(
        taskId=task_id,
        goal="Build an agent",
        state=TaskState.PROVISIONING,
        stage=TaskStage.PROVISIONING,
        createdAt="2026-01-01T00:00:00+00:00",
        expiresAt="2026-01-01T08:00:00+00:00",
    )


def test_task_id_is_deterministic_and_owner_bound() -> None:
    request_id = UUID("12345678-1234-5678-9234-567812345678")
    task_id = task_id_for("owner-a", request_id)

    assert task_id == task_id_for("owner-a", request_id)
    assert task_id != task_id_for("owner-b", request_id)
    assert task_id.startswith("vt-")
    assert len(task_id) == 40
    with pytest.raises(ValueError):
        task_id_for("  ", request_id)


def test_event_replay_validates_hash_chain_and_ignores_only_truncated_tail() -> None:
    task_id = task_id_for("owner", UUID(int=1))
    first = make_event_record(
        task_id=task_id,
        sequence=1,
        previous_hash=EVENT_CHAIN_GENESIS,
        event_type="task.created",
        stage=TaskStage.PROVISIONING,
        timestamp="2026-01-01T00:00:00+00:00",
        payload={},
        projection=RemoteStatusProjection(
            state=TaskState.READY,
            stage=TaskStage.UNDERSTANDING,
        ),
    )
    second = make_event_record(
        task_id=task_id,
        sequence=2,
        previous_hash=first.event_hash,
        event_type="task.started",
        stage=TaskStage.BUILDING,
        timestamp="2026-01-01T00:01:00+00:00",
        payload={"attempt": 1},
        projection=RemoteStatusProjection(
            state=TaskState.RUNNING,
            stage=TaskStage.BUILDING,
            attempt=1,
        ),
    )
    log = "\n".join(
        (
            first.model_dump_json(by_alias=True),
            second.model_dump_json(by_alias=True),
        )
    ) + "\n"

    replay = replay_event_log(log + '{"schemaVersion":1', expected_task_id=task_id)
    assert replay.truncated_tail is True
    assert replay.last_hash == second.event_hash
    assert [item.event.sequence for item in replay.events] == [1, 2]

    tampered = log.replace('"attempt":1', '"attempt":2')
    with pytest.raises(ValueError, match="line 2"):
        replay_event_log(tampered, expected_task_id=task_id)

    with pytest.raises(ValueError, match="line 2"):
        replay_event_log(
            first.model_dump_json(by_alias=True) + "\nnot-json\n",
            expected_task_id=task_id,
        )

    valid_json_with_invalid_schema = log + '{"schemaVersion":2}'
    with pytest.raises(ValueError, match="line 3"):
        replay_event_log(valid_json_with_invalid_schema, expected_task_id=task_id)


def test_projection_reduces_validated_events_without_mutating_identity() -> None:
    task_id = task_id_for("owner", UUID(int=2))
    initial = _status(task_id)
    event = make_event_record(
        task_id=task_id,
        sequence=1,
        previous_hash=EVENT_CHAIN_GENESIS,
        event_type="task.ready",
        stage=TaskStage.UNDERSTANDING,
        timestamp="2026-01-01T00:00:01+00:00",
        payload={},
        projection=RemoteStatusProjection(
            state=TaskState.READY,
            stage=TaskStage.UNDERSTANDING,
            intentRevision=1,
        ),
    )

    projected = project_status(initial, [event])
    assert projected.task_id == task_id
    assert projected.goal == initial.goal
    assert projected.state is TaskState.READY
    assert projected.stage is TaskStage.UNDERSTANDING
    assert projected.intent_revision == 1
    assert projected.last_sequence == 1
    assert initial.last_sequence == 0

    foreign = event.model_copy(update={"task_id": task_id_for("other", UUID(int=2))})
    with pytest.raises(ValueError, match="task id"):
        project_status(initial, [foreign])


def test_remote_schema_is_strict() -> None:
    with pytest.raises(ValidationError):
        RemoteStatusProjection.model_validate({"state": "ready", "unknown": True})
    with pytest.raises(ValidationError):
        make_event_record(
            task_id=task_id_for("owner", UUID(int=4)),
            sequence=1,
            previous_hash=EVENT_CHAIN_GENESIS,
            event_type="task.created",
            stage=TaskStage.PROVISIONING,
            timestamp="now",
            payload={},
        ).model_validate(
            {
                "schemaVersion": 2,
                "taskId": task_id_for("owner", UUID(int=4)),
                "sequence": 1,
                "previousHash": EVENT_CHAIN_GENESIS,
                "eventHash": EVENT_CHAIN_GENESIS,
                "eventType": "task.created",
                "stage": "provisioning",
                "timestamp": "now",
            }
        )


def test_sandbox_builders_use_locked_durable_atomic_writes() -> None:
    task_id = task_id_for("owner", UUID(int=3))
    request = {
        "schemaVersion": 1,
        "taskId": task_id,
        "requestId": str(UUID(int=3)),
        "goal": "Build an agent",
        "displayName": "Agent",
    }
    command = build_bootstrap_command(request, _status(task_id))
    runner = build_runner_command(["python", "-m", "worker"], timeout=60)

    for value in (
        "flock",
        "NamedTemporaryFile",
        "fsync",
        "replace",
        REMOTE_REQUEST_PATH,
        REMOTE_STATUS_PATH,
        REMOTE_EVENTS_PATH,
    ):
        assert value in command
    assert "shell=True" not in runner
    for value in ("flock", "NamedTemporaryFile", "fsync", "replace", REMOTE_RUNNER_RESULT_PATH):
        assert value in runner
