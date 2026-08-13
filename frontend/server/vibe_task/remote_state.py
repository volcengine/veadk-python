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

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import shlex
from typing import Any, Iterable, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .models import ArtifactInfo, TaskEvent, TaskStage, TaskState, TaskStatus, VibeModel


REMOTE_SCHEMA_VERSION = 1
REMOTE_TASK_ROOT = "/home/gem/.vibe/task"
REMOTE_REQUEST_PATH = f"{REMOTE_TASK_ROOT}/request.json"
REMOTE_STATUS_PATH = f"{REMOTE_TASK_ROOT}/status.json"
REMOTE_EVENTS_PATH = f"{REMOTE_TASK_ROOT}/events.jsonl"
REMOTE_RUNNER_RESULT_PATH = f"{REMOTE_TASK_ROOT}/runner-result.json"
REMOTE_LOCK_PATH = f"{REMOTE_TASK_ROOT}/state.lock"
EVENT_CHAIN_GENESIS = "0" * 64
_HASH_PATTERN = r"^[0-9a-f]{64}$"


class RemoteTaskRequest(VibeModel):
    schema_version: Literal[1] = REMOTE_SCHEMA_VERSION
    task_id: str = Field(pattern=r"^vt-[0-9a-f]{12}-[0-9a-f]{24}$")
    request_id: UUID
    goal: str = Field(min_length=1, max_length=20_000)
    display_name: str = Field(default="", max_length=80)


class RemoteStatusProjection(VibeModel):
    state: TaskState | None = None
    stage: TaskStage | None = None
    attempt: int | None = Field(default=None, ge=0)
    credentials_configured: bool | None = None
    intent_revision: int | None = Field(default=None, ge=0)
    sandbox_session_id: str | None = None
    validation_runtime_id: str | None = None
    validation_runtime_status: str | None = None
    artifact: ArtifactInfo | None = None
    warnings: list[str] | None = None
    error: str | None = None


class RemoteEventRecord(VibeModel):
    schema_version: Literal[1] = REMOTE_SCHEMA_VERSION
    task_id: str = Field(pattern=r"^vt-[0-9a-f]{12}-[0-9a-f]{24}$")
    sequence: int = Field(ge=1)
    previous_hash: str = Field(pattern=_HASH_PATTERN)
    event_hash: str = Field(pattern=_HASH_PATTERN)
    event_type: str = Field(min_length=1, max_length=80)
    stage: TaskStage
    timestamp: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    projection: RemoteStatusProjection = Field(default_factory=RemoteStatusProjection)

    @model_validator(mode="after")
    def validate_hash(self) -> "RemoteEventRecord":
        if self.event_hash != _event_hash(self.model_dump(exclude={"event_hash"})):
            raise ValueError("event hash does not match record")
        return self

    @property
    def event(self) -> TaskEvent:
        return TaskEvent(
            sequence=self.sequence,
            event_type=self.event_type,
            stage=self.stage,
            timestamp=self.timestamp,
            payload=self.payload,
        )


@dataclass(frozen=True)
class EventReplay:
    events: tuple[RemoteEventRecord, ...]
    last_hash: str
    truncated_tail: bool = False


def task_id_for(owner_id: str, request_id: UUID) -> str:
    owner = owner_id.strip()
    if not owner:
        raise ValueError("owner_id must not be blank")
    owner_hash = hashlib.sha256(owner.encode()).hexdigest()[:12]
    suffix = hashlib.sha256(f"{owner}\0{request_id}".encode()).hexdigest()[:24]
    return f"vt-{owner_hash}-{suffix}"


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _event_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def make_event_record(
    *,
    task_id: str,
    sequence: int,
    previous_hash: str,
    event_type: str,
    stage: TaskStage,
    timestamp: str,
    payload: dict[str, Any],
    projection: RemoteStatusProjection | None = None,
) -> RemoteEventRecord:
    values: dict[str, Any] = {
        "schema_version": REMOTE_SCHEMA_VERSION,
        "task_id": task_id,
        "sequence": sequence,
        "previous_hash": previous_hash,
        "event_type": event_type,
        "stage": stage,
        "timestamp": timestamp,
        "payload": payload,
        "projection": projection or RemoteStatusProjection(),
    }
    serialized = RemoteEventRecord.model_construct(event_hash=EVENT_CHAIN_GENESIS, **values)
    return RemoteEventRecord.model_validate(
        {**serialized.model_dump(), "event_hash": _event_hash(serialized.model_dump(exclude={"event_hash"}))}
    )


def replay_event_log(value: str, *, expected_task_id: str) -> EventReplay:
    records: list[RemoteEventRecord] = []
    previous_hash = EVENT_CHAIN_GENESIS
    truncated_tail = False
    lines = value.splitlines()
    final_line_complete = not value or value.endswith("\n")

    for index, line in enumerate(lines, start=1):
        if not line.strip():
            raise ValueError(f"event log line {index} is blank")
        try:
            raw_record = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(lines) and not final_line_complete:
                truncated_tail = True
                break
            raise ValueError(f"invalid event log line {index}") from exc
        try:
            record = RemoteEventRecord.model_validate(raw_record)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid event log line {index}") from exc
        if record.task_id != expected_task_id:
            raise ValueError(f"event log line {index} has unexpected task id")
        if record.sequence != index:
            raise ValueError(f"event log line {index} has unexpected sequence")
        if record.previous_hash != previous_hash:
            raise ValueError(f"event log line {index} breaks hash chain")
        records.append(record)
        previous_hash = record.event_hash

    return EventReplay(tuple(records), previous_hash, truncated_tail)


def project_status(
    initial: TaskStatus, records: Iterable[RemoteEventRecord]
) -> TaskStatus:
    status = initial.model_copy(deep=True)
    previous_hash = EVENT_CHAIN_GENESIS
    expected_sequence = 1
    for record in records:
        if record.task_id != status.task_id:
            raise ValueError("event task id does not match status")
        if record.sequence != expected_sequence or record.previous_hash != previous_hash:
            raise ValueError("events are not a contiguous hash chain")
        updates = {
            key: value
            for key, value in record.projection.model_dump().items()
            if value is not None
        }
        updates["last_sequence"] = record.sequence
        status = status.model_copy(update=updates)
        previous_hash = record.event_hash
        expected_sequence += 1
    return TaskStatus.model_validate(status.model_dump())


def _command_for_source(source: str) -> str:
    return f"python -c {shlex.quote(source)}"


def _atomic_write_source() -> str:
    return """
def atomic_write(path, value):
    directory = os.path.dirname(path)
    with tempfile.NamedTemporaryFile("w", dir=directory, delete=False) as temporary:
        temporary.write(value)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = temporary.name
    os.replace(temporary_path, path)
    directory_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
"""


def build_bootstrap_command(request: dict[str, object], status: TaskStatus) -> str:
    validated_request = RemoteTaskRequest.model_validate(request)
    if validated_request.task_id != status.task_id:
        raise ValueError("request and status task ids do not match")
    initial_event = make_event_record(
        task_id=status.task_id,
        sequence=1,
        previous_hash=EVENT_CHAIN_GENESIS,
        event_type="task.created",
        stage=TaskStage.PROVISIONING,
        timestamp=status.created_at,
        payload={"intentSummaryPath": "/home/gem/.vibe/task/intent-summary.json"},
        projection=RemoteStatusProjection(
            state=status.state,
            stage=status.stage,
            intent_revision=1,
            sandbox_session_id=status.sandbox_session_id,
        ),
    )
    status = status.model_copy(update={"last_sequence": 1, "intent_revision": 1})
    request_json = validated_request.model_dump_json(by_alias=True)
    status_json = status.model_dump_json(by_alias=True)
    event_json = initial_event.model_dump_json(by_alias=True)
    source = f"""import fcntl
import json
import os
import tempfile
{_atomic_write_source()}
os.makedirs({REMOTE_TASK_ROOT!r}, mode=0o700, exist_ok=True)
with open({REMOTE_LOCK_PATH!r}, "a+") as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    if os.path.exists({REMOTE_REQUEST_PATH!r}) and os.path.exists({REMOTE_STATUS_PATH!r}):
        existing = json.loads(open({REMOTE_REQUEST_PATH!r}, encoding="utf-8").read())
        if existing.get("taskId") != {status.task_id!r} or existing.get("requestId") != {str(validated_request.request_id)!r}:
            raise RuntimeError("refusing to overwrite another Vibe Task")
        raise SystemExit(0)
    atomic_write({REMOTE_REQUEST_PATH!r}, {request_json!r} + "\\n")
    atomic_write({REMOTE_STATUS_PATH!r}, {status_json!r} + "\\n")
    atomic_write({REMOTE_EVENTS_PATH!r}, {event_json!r} + "\\n")
"""
    return _command_for_source(source)


def build_runner_command(argv: list[str], *, timeout: int) -> str:
    if not argv or any(not isinstance(item, str) or not item for item in argv):
        raise ValueError("argv must contain non-empty strings")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    source = f"""import fcntl
import json
import os
import subprocess
import tempfile
{_atomic_write_source()}
os.makedirs({REMOTE_TASK_ROOT!r}, mode=0o700, exist_ok=True)
result = subprocess.run({argv!r}, capture_output=True, text=True, timeout={timeout!r}, check=False)
payload = json.dumps({{"exitCode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}}, separators=(",", ":")) + "\\n"
with open({REMOTE_LOCK_PATH!r}, "a+") as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    atomic_write({REMOTE_RUNNER_RESULT_PATH!r}, payload)
"""
    return _command_for_source(source)
