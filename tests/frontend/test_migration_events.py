# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.migration import routes
from frontend.server.migration.events import (
    ACTIVITY_EVENT,
    DONE_EVENT,
    ERROR_EVENT,
    TASK_EVENT,
    MigrationEventHub,
    MigrationEventLog,
    MigrationSnapshot,
    MigrationStream,
)
from frontend.server.migration.routes import (
    migration_activity_visible,
    migration_task_settled,
    mount_migration_routes,
)
from frontend.server.migration.service import MigrationError

TASK_ID = "migration-v1-" + "1" * 32


def task_payload(state: str, **extra: Any) -> dict[str, object]:
    return {"id": TASK_ID, "state": state, **extra}


class ScriptedRead:
    """Serves prepared snapshots, repeating the last one until it is replaced."""

    def __init__(self, *snapshots: MigrationSnapshot) -> None:
        self.pending = list(snapshots)
        self.calls = 0

    async def __call__(self) -> MigrationSnapshot:
        self.calls += 1
        if len(self.pending) > 1:
            return self.pending.pop(0)
        if self.pending:
            return self.pending[0]
        return MigrationSnapshot(settled=True)

    def push(self, *snapshots: MigrationSnapshot) -> None:
        self.pending.extend(snapshots)


async def collect(
    stream: MigrationStream,
    after: int = 0,
    *,
    limit: int | None = None,
    timeout: float = 3.0,
) -> list[Any]:
    """Events from ``after``; stops at ``limit`` so a live stream cannot block a test."""

    async def drain() -> list[Any]:
        collected: list[Any] = []
        async for event in stream.follow(after):
            if event is None:
                continue
            collected.append(event)
            if limit is not None and len(collected) >= limit:
                return collected
        return collected

    return await asyncio.wait_for(drain(), timeout)


async def next_event(stream: MigrationStream, after: int, timeout: float = 2.0) -> Any:
    """First event after ``after``, or ``None`` when the follower returns/keeps waiting."""

    async def first() -> Any:
        async for event in stream.follow(after):
            return event
        return None

    return await asyncio.wait_for(first(), timeout)


def test_log_replays_only_retained_events_and_tracks_its_window() -> None:
    log = MigrationEventLog(history_limit=3)
    assert log.last_seq == 0
    assert log.earliest_seq == 1
    for index in range(5):
        log.append(TASK_EVENT, {"index": index})
    assert log.last_seq == 5
    assert [event.seq for event in log.replay(0)] == [3, 4, 5]
    assert [event.seq for event in log.replay(4)] == [5]
    assert log.replay(5) == []
    assert log.size == 3
    assert log.earliest_seq == 3


@pytest.mark.asyncio
async def test_log_wait_wakes_on_append_and_reports_timeouts() -> None:
    log = MigrationEventLog()
    assert await log.wait(0, 0.01) is False
    waiter = asyncio.create_task(log.wait(0, 5))
    await asyncio.sleep(0)
    log.append(TASK_EVENT, {"state": "analyzing"})
    assert await asyncio.wait_for(waiter, 1) is True
    assert await log.wait(1, 0.01) is False


@pytest.mark.asyncio
async def test_log_wake_releases_waiters_without_an_event() -> None:
    log = MigrationEventLog()
    waiter = asyncio.create_task(log.wait(0, 5))
    await asyncio.sleep(0)
    log.wake()
    assert await asyncio.wait_for(waiter, 1) is False


@pytest.mark.asyncio
async def test_stream_publishes_a_snapshot_once_and_marks_changes() -> None:
    read = ScriptedRead(
        MigrationSnapshot(task=task_payload("analyzing")),
        MigrationSnapshot(task=task_payload("analyzing")),
        MigrationSnapshot(task=task_payload("migrating")),
    )
    stream = MigrationStream(read, poll_seconds=0.01, idle_seconds=30)
    stream.attach()
    assert await next_event(stream, 0) is not None
    events = await collect(stream, 0, limit=2)
    assert [event.type for event in events] == [TASK_EVENT, TASK_EVENT]
    assert [event.payload["state"] for event in events] == ["analyzing", "migrating"]
    assert [event.seq for event in events] == [1, 2]
    stream.detach()
    stream.retire()


@pytest.mark.asyncio
async def test_stream_dedupes_activity_and_settles_with_one_done_event() -> None:
    activity = {"available": True, "complete": False, "items": [{"id": "a"}]}
    read = ScriptedRead(
        MigrationSnapshot(task=task_payload("migrating"), activity=activity),
        MigrationSnapshot(task=task_payload("migrating"), activity=activity),
        MigrationSnapshot(
            task=task_payload("succeeded"),
            activity={**activity, "complete": True},
            settled=True,
        ),
    )
    stream = MigrationStream(read, poll_seconds=0.01, idle_seconds=30)
    stream.attach()
    events = await collect(stream, 0)
    assert [event.type for event in events] == [
        TASK_EVENT,
        ACTIVITY_EVENT,
        TASK_EVENT,
        ACTIVITY_EVENT,
        DONE_EVENT,
    ]
    assert events[-1].payload["state"] == "succeeded"
    # The stream is spent: followers replay the same history and return immediately.
    assert [event.type for event in await collect(stream, 0)] == [
        event.type for event in events
    ]
    assert await next_event(stream, stream.log.last_seq) is None
    stream.detach()
    stream.retire()


@pytest.mark.asyncio
async def test_stream_surfaces_read_faults_once_and_clears_them_on_recovery() -> None:
    read = ScriptedRead(MigrationSnapshot(task=task_payload("analyzing")))
    stream = MigrationStream(
        read,
        poll_seconds=0.01,
        failure_backoff_seconds=0.01,
        idle_seconds=30,
    )
    stream.attach()
    first = await next_event(stream, 0)
    assert first is not None and first.type == TASK_EVENT

    async def fail() -> MigrationSnapshot:
        raise RuntimeError("sandbox unreachable")

    stream._read = fail
    failure = await next_event(stream, stream.log.last_seq)
    assert failure is not None and failure.type == ERROR_EVENT
    assert failure.payload["retryable"] is True
    assert "sandbox unreachable" not in json.dumps(failure.payload)
    # A repeated identical fault is not re-published on every tick.
    await asyncio.sleep(0.05)
    assert [event.seq for event in stream.log.replay(failure.seq)] == []

    stream._read = ScriptedRead(MigrationSnapshot(task=task_payload("migrating")))
    # Recovery itself is a frame: an error event without a code or a message, so a
    # follower can drop a banner even when the task payload did not move.
    cleared = await next_event(stream, stream.log.last_seq)
    assert cleared is not None and cleared.type == ERROR_EVENT
    assert cleared.payload == {}
    recovered = await next_event(stream, cleared.seq)
    assert recovered is not None and recovered.type == TASK_EVENT
    assert recovered.payload["state"] == "migrating"
    # A healthy tick publishes nothing at all, the cleared frame included.
    await asyncio.sleep(0.05)
    assert [event.seq for event in stream.log.replay(recovered.seq)] == []

    stream._read = fail
    again = await next_event(stream, stream.log.last_seq)
    assert again is not None and again.type == ERROR_EVENT
    stream.detach()
    stream.retire()


@pytest.mark.asyncio
async def test_stream_clears_a_read_fault_without_waiting_for_the_task_to_move() -> (
    None
):
    read = ScriptedRead(MigrationSnapshot(task=task_payload("analyzing")))
    stream = MigrationStream(
        read,
        poll_seconds=0.01,
        failure_backoff_seconds=0.01,
        idle_seconds=30,
    )
    stream.attach()
    first = await next_event(stream, 0)
    assert first is not None and first.type == TASK_EVENT

    async def fail() -> MigrationSnapshot:
        raise RuntimeError("sandbox unreachable")

    stream._read = fail
    failure = await next_event(stream, stream.log.last_seq)
    assert failure is not None and failure.type == ERROR_EVENT

    # The very same snapshot comes back readable: the cleared frame is published even
    # though neither the task nor the activity changed.
    stream._read = ScriptedRead(MigrationSnapshot(task=task_payload("analyzing")))
    cleared = await next_event(stream, stream.log.last_seq)
    assert cleared is not None and cleared.type == ERROR_EVENT
    assert cleared.payload == {}
    await asyncio.sleep(0.05)
    assert [event.seq for event in stream.log.replay(cleared.seq)] == []
    stream.detach()
    stream.retire()


@pytest.mark.asyncio
async def test_stream_stops_polling_when_nobody_listens() -> None:
    read = ScriptedRead(MigrationSnapshot(task=task_payload("migrating")))
    stream = MigrationStream(read, poll_seconds=0.01, idle_seconds=0.05)
    stream.attach()
    await next_event(stream, 0)
    stream.detach()
    await asyncio.sleep(0.2)
    settled = read.calls
    await asyncio.sleep(0.1)
    assert read.calls == settled
    assert stream.idle is True


@pytest.mark.asyncio
async def test_hub_reuses_a_live_stream_and_drops_an_idle_one() -> None:
    reads: dict[str, ScriptedRead] = {}

    def read_for(key: str) -> ScriptedRead:
        return reads.setdefault(
            key, ScriptedRead(MigrationSnapshot(task=task_payload("analyzing")))
        )

    hub = MigrationEventHub(read_for, poll_seconds=0.01, idle_seconds=0.05)
    async with hub.subscription("a") as first:
        assert hub.peek("a") is first
        assert hub.peek("a") is hub.stream("a")
    assert hub.peek("a") is first
    await asyncio.sleep(0.1)
    async with hub.subscription("a") as second:
        assert second is not first
        assert hub.peek("b") is None
    hub.close()
    assert hub.peek("a") is None


@pytest.mark.asyncio
async def test_hub_never_hands_out_a_settled_stream() -> None:
    reads = [0]

    async def read() -> MigrationSnapshot:
        reads[0] += 1
        return MigrationSnapshot(task=task_payload("succeeded"), settled=True)

    hub = MigrationEventHub(lambda _key: read, poll_seconds=0.01, idle_seconds=60)
    async with hub.subscription("a") as first:
        assert [event.type for event in await collect(first, 0)] == [
            TASK_EVENT,
            DONE_EVENT,
        ]
    # The task moved on (a new action), so the follower must get a real re-read.
    async with hub.subscription("a") as second:
        assert second is not first
        assert [event.type for event in await collect(second, 0)] == [
            TASK_EVENT,
            DONE_EVENT,
        ]
    assert reads[0] == 2
    hub.close()


@pytest.mark.asyncio
async def test_hub_trims_beyond_its_stream_budget() -> None:
    hub = MigrationEventHub(
        lambda _key: ScriptedRead(MigrationSnapshot(task=task_payload("analyzing"))),
        poll_seconds=0.01,
        idle_seconds=60,
        max_streams=2,
    )
    async with hub.subscription("a"):
        async with hub.subscription("b"):
            async with hub.subscription("c"):
                assert len(hub._streams) == 2
    hub.close()


class StreamService:
    """Minimal migration service whose task finishes on the second read."""

    def __init__(self, *, evaluation: dict[str, object] | None = None) -> None:
        self.reads = 0
        self.activity_calls = 0
        self.recovered = 0
        self.driven = 0
        self.evaluation = evaluation

    def get_task(self, task_id: str, owner_id: str) -> dict[str, object]:
        assert task_id == TASK_ID
        self.reads += 1
        # Read 1 authorizes the stream; the poller then sees an active task twice.
        state = "analyzing" if self.reads <= 2 else "succeeded"
        task: dict[str, object] = {
            "id": TASK_ID,
            "state": state,
            "analysisRef": {"attempt": 1, "sha256": "a" * 64},
        }
        if self.evaluation is not None:
            task["evaluation"] = self.evaluation
        return task

    def recover_stalled_analysis(self, task_id: str, owner_id: str) -> bool:
        self.recovered += 1
        return False

    def drive_delivery_turn(
        self, task_id: str, owner_id: str, **kwargs: object
    ) -> bool:
        del kwargs
        self.driven += 1
        return False

    def activity(self, task_id: str, owner_id: str) -> dict[str, object]:
        self.activity_calls += 1
        return {
            "available": True,
            "complete": self.reads > 1,
            "items": [{"id": f"analysis:1:{self.reads}"}],
        }


def fast_hub(read: Any) -> MigrationEventHub:
    return MigrationEventHub(
        read,
        poll_seconds=0.01,
        heartbeat_seconds=0.05,
        idle_seconds=0.05,
    )


def app_for(service: Any) -> FastAPI:
    app = FastAPI()
    mount_migration_routes(
        app,
        service,
        owner_resolver=lambda request: request.headers.get("x-owner", "owner-1"),
        creator_resolver=lambda _request: "Owner",
    )
    return app


def frames(body: str) -> list[tuple[str, dict[str, object]]]:
    parsed: list[tuple[str, dict[str, object]]] = []
    for block in body.split("\n\n"):
        name = ""
        data = ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if name:
            parsed.append((name, json.loads(data) if data else {}))
    return parsed


def test_events_stream_replays_task_activity_and_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "MigrationEventHub", fast_hub)
    service = StreamService()
    with TestClient(app_for(service)) as client:
        response = client.get(f"/web/agent-migrations/tasks/{TASK_ID}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = frames(response.text)
    assert [name for name, _ in events] == [
        TASK_EVENT,
        ACTIVITY_EVENT,
        TASK_EVENT,
        ACTIVITY_EVENT,
        DONE_EVENT,
    ]
    assert [payload["seq"] for _, payload in events] == [1, 2, 3, 4, 5]
    assert all(payload["taskId"] == TASK_ID for _, payload in events)
    assert events[-1][1]["state"] == "succeeded"
    assert service.recovered >= 1
    assert service.activity_calls >= 1


def test_events_stream_accepts_a_cursor_and_still_replays_the_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cursor from a stream that is gone re-syncs instead of waiting for its own seq."""
    monkeypatch.setattr(routes, "MigrationEventHub", fast_hub)
    for cursor in ("?after=2", "?after=99"):
        with TestClient(app_for(StreamService())) as client:
            response = client.get(
                f"/web/agent-migrations/tasks/{TASK_ID}/events{cursor}"
            )
        assert response.status_code == 200
        assert [payload["seq"] for _, payload in frames(response.text)] == [
            1,
            2,
            3,
            4,
            5,
        ]


def test_events_stream_rejects_a_negative_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "MigrationEventHub", fast_hub)
    with TestClient(app_for(StreamService())) as client:
        response = client.get(f"/web/agent-migrations/tasks/{TASK_ID}/events?after=-1")
    assert response.status_code == 422


def test_events_stream_reports_a_task_the_caller_cannot_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "MigrationEventHub", fast_hub)

    class MissingService(StreamService):
        def get_task(self, task_id: str, owner_id: str) -> dict[str, object]:
            raise MigrationError(
                "MIGRATION_TASK_NOT_FOUND",
                "迁移任务不存在。",
                status_code=404,
            )

    with TestClient(app_for(MissingService())) as client:
        response = client.get(f"/web/agent-migrations/tasks/{TASK_ID}/events")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "MIGRATION_TASK_NOT_FOUND"


@pytest.mark.parametrize(
    ("task", "settled"),
    [
        ({"id": TASK_ID, "state": "migrating"}, False),
        ({"id": TASK_ID, "state": "analyzing"}, False),
        ({"id": TASK_ID, "state": "needs_input"}, True),
        ({"id": TASK_ID, "state": "analysis_ready"}, True),
        ({"id": TASK_ID, "state": "succeeded"}, True),
        (
            {"id": TASK_ID, "state": "succeeded", "persistence": {"state": "saving"}},
            False,
        ),
        (
            {
                "id": TASK_ID,
                "state": "succeeded",
                "evaluation": {"enabled": True, "state": "judging"},
            },
            False,
        ),
        (
            {
                "id": TASK_ID,
                "state": "awaiting_upload",
                "evaluation": {"enabled": True, "state": "judging"},
            },
            False,
        ),
        (
            {
                "id": TASK_ID,
                "state": "succeeded",
                "evaluation": {"enabled": True, "state": "waiting_dataset"},
            },
            True,
        ),
    ],
)
def test_task_settlement_matches_the_states_a_stream_can_close_on(
    task: dict[str, object], settled: bool
) -> None:
    assert migration_task_settled(task) is settled


@pytest.mark.parametrize(
    ("task", "visible"),
    [
        ({"id": TASK_ID, "state": "analyzing"}, True),
        ({"id": TASK_ID, "state": "migrating", "analysisRef": {"attempt": 1}}, True),
        (
            {
                "id": TASK_ID,
                "state": "migrating",
                "confirmation": {"framework": "dify"},
            },
            True,
        ),
        (
            {
                "id": TASK_ID,
                "state": "failed",
                "error": {"code": "MIGRATION_ANALYSIS_EMPTY"},
            },
            True,
        ),
        ({"id": TASK_ID, "state": "awaiting_upload"}, False),
        (
            {"id": TASK_ID, "state": "failed", "error": {"code": "MIGRATION_FAILED"}},
            False,
        ),
    ],
)
def test_activity_visibility_matches_the_page_rule(
    task: dict[str, object], visible: bool
) -> None:
    assert migration_activity_visible(task) is visible
