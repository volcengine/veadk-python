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

"""Durable task contracts: isolation, replay, ownership and user intent."""

import asyncio
import hashlib

import pytest

from frontend.server.intelligent_development_runs.repository import (
    RunConflict,
    RunLeaseLost,
    RunNotFound,
    RunRepository,
)


@pytest.fixture
def clock():
    return [1_000.0]


@pytest.fixture
def repository(tmp_path, clock):
    return RunRepository(tmp_path / "runs.sqlite3", clock=lambda: clock[0])


@pytest.mark.asyncio
async def test_acceptance_is_atomic_idempotent_and_scoped(repository):
    first, second = await asyncio.gather(
        repository.create("alice", "session-a", "request-a", "build an agent"),
        repository.create("alice", "session-a", "request-a", "build an agent"),
    )
    assert first.id == second.id
    with pytest.raises(RunConflict):
        await repository.create("alice", "session-a", "request-a", "different input")
    with pytest.raises(RunConflict):
        await repository.create("alice", "session-a", "request-b", "another task")
    other = await repository.create("bob", "session-b", "request-a", "build an agent")
    assert other.id != first.id
    with pytest.raises(RunNotFound):
        await repository.get("bob", first.id)
    with pytest.raises(RunNotFound):
        await repository.events("bob", first.id, after=0)
    with pytest.raises(RunNotFound):
        await repository.request_stop("bob", first.id)


@pytest.mark.asyncio
async def test_events_survive_reopening_and_replay_from_cursor(repository):
    run = await repository.create("alice", "session-a", "request-a", "build")
    token = await repository.claim("alice", run.id)
    assert token
    event = await repository.append_event(
        "alice", run.id, token, "delta", {"text": "already generated"}
    )
    reopened = RunRepository(repository.path)
    replay = await reopened.events("alice", run.id, after=event["seq"] - 1)
    assert replay[0]["payload"] == {"text": "already generated"}
    assert await reopened.events("alice", run.id, after=replay[-1]["seq"]) == []


@pytest.mark.asyncio
async def test_expired_worker_cannot_write_after_takeover(repository, clock):
    run = await repository.create("alice", "session-a", "request-a", "build")
    old = await repository.claim("alice", run.id, seconds=10)
    assert old
    assert await repository.claim("alice", run.id) is None
    clock[0] += 11
    current = await repository.claim("alice", run.id)
    assert current and current != old
    with pytest.raises(RunLeaseLost):
        await repository.update("alice", run.id, old, state="running")
    with pytest.raises(RunLeaseLost):
        await repository.append_event("alice", run.id, old, "delta", {"text": "stale"})
    await repository.update("alice", run.id, current, state="running")


@pytest.mark.asyncio
async def test_stop_intent_survives_restart_and_cancels_pending_inputs(repository):
    run = await repository.create("alice", "session-a", "request-a", "build")
    token = await repository.claim("alice", run.id)
    assert token
    await repository.add_input("alice", run.id, "steer-a", "change direction")
    stopped = await repository.request_stop("alice", run.id)
    assert stopped.state == "stopping"
    assert stopped.stop_requested
    assert (await RunRepository(repository.path).get("alice", run.id)).stop_requested
    assert not await repository.inputs("alice", run.id, statuses=("pending",))
    with pytest.raises(RunConflict):
        await repository.add_input("alice", run.id, "steer-b", "continue")
    with pytest.raises(RunConflict):
        await repository.update("alice", run.id, token, state="running")


@pytest.mark.asyncio
async def test_retention_only_removes_terminal_runs(repository, clock):
    active = await repository.create("alice", "active", "request-a", "build")
    ended = await repository.create("alice", "ended", "request-b", "build")
    token = await repository.claim("alice", ended.id)
    assert token
    await repository.update("alice", ended.id, token, state="succeeded")
    clock[0] += 21_601
    assert await repository.cleanup() == 1
    assert (await repository.get("alice", active.id)).state == "queued"
    with pytest.raises(RunNotFound):
        await repository.get("alice", ended.id)


@pytest.mark.asyncio
async def test_steer_is_ordered_and_idempotent(repository):
    run = await repository.create("alice", "session-a", "request-a", "build")
    first = await repository.add_input("alice", run.id, "steer-a", "first change")
    repeated = await repository.add_input("alice", run.id, "steer-a", "first change")
    second = await repository.add_input("alice", run.id, "steer-b", "second change")
    assert first == repeated
    assert second["revision"] == first["revision"] + 1
    with pytest.raises(RunConflict):
        await repository.add_input("alice", run.id, "steer-a", "different")
    assert [item["client_id"] for item in await repository.inputs("alice", run.id)] == [
        "request-a",
        "steer-a",
        "steer-b",
    ]


@pytest.mark.asyncio
async def test_redacted_messages_retain_distinct_idempotency_identity(repository):
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    first = await repository.create(
        "alice", "env", "r", "***", message_digest=digest("first")
    )
    same = await repository.create(
        "alice", "env", "r", "***", message_digest=digest("first")
    )
    assert first.id == same.id
    with pytest.raises(RunConflict):
        await repository.create(
            "alice", "env", "r", "***", message_digest=digest("second")
        )
    await repository.add_input(
        "alice", first.id, "s", "***", message_digest=digest("first")
    )
    with pytest.raises(RunConflict):
        await repository.add_input(
            "alice", first.id, "s", "***", message_digest=digest("second")
        )
    assert "message_digest" not in first.public()
    assert "first" not in repository.path.read_bytes().decode(errors="ignore")


@pytest.mark.asyncio
async def test_limits_preserve_events_and_owner_fairness(tmp_path):
    from frontend.server.intelligent_development_runs.repository import RunCapacity

    repository = RunRepository(tmp_path / "runs.db", max_event_bytes=300)
    run = await repository.create("alice", "one", "r", "build")
    token = await repository.claim("alice", run.id)
    assert token
    await repository.append_event("alice", run.id, token, "delta", {"text": "kept"})
    with pytest.raises(RunCapacity):
        await repository.append_event(
            "alice", run.id, token, "delta", {"text": "x" * 300}
        )
    await repository.update("alice", run.id, token, state="waiting_user")
    assert any(
        event["payload"].get("text") == "kept"
        for event in await repository.events("alice", run.id)
    )
    await repository.create("alice", "two", "r", "build")
    await repository.create("alice", "three", "r", "build")
    with pytest.raises(RunCapacity):
        await repository.create("alice", "four", "r", "build")
    other = await repository.create("bob", "four", "r", "build")
    assert [item.id for item in await repository.active_for_owner("bob")] == [other.id]


@pytest.mark.asyncio
async def test_stop_withdrawal_and_completion_race_are_replayable(repository):
    run = await repository.create("alice", "session", "r", "build")
    token = await repository.claim("alice", run.id)
    assert token
    await repository.input_status("alice", run.id, token, "r", "delivered", turn_id="t")
    await repository.add_input("alice", run.id, "steer", "new requirement")
    assert not await repository.finish("alice", run.id, token, 1)
    await repository.request_stop("alice", run.id)
    assert not await repository.finish("alice", run.id, token, 2)
    events = await repository.events("alice", run.id)
    assert any(
        event["type"] == "run.input_status"
        and event["payload"]
        == {"clientId": "steer", "status": "withdrawn", "turnId": ""}
        for event in events
    )


@pytest.mark.asyncio
async def test_turn_metrics_survive_reopen_deduplicate_usage_and_enforce_owner(
    repository,
):
    run = await repository.create("alice", "session-a", "request-a", "build")
    token = await repository.claim("alice", run.id)
    options = dict(thread_id="thread", turn_id="turn", revision=1)
    await repository.record_turn(
        "alice",
        run.id,
        token,
        **options,
        status="inProgress",
        metrics={"startedAt": 100, "model": "test-model"},
    )
    usage = {
        "totalTokens": 100,
        "inputTokens": 80,
        "outputTokens": 20,
        "cachedInputTokens": 40,
        "reasoningOutputTokens": 5,
    }
    await repository.record_turn(
        "alice",
        run.id,
        token,
        **options,
        status="inProgress",
        metrics={"usage": usage, "threadTotal": usage},
    )
    reopened = RunRepository(repository.path, clock=repository.clock)
    await reopened.record_turn(
        "alice",
        run.id,
        token,
        **options,
        status="inProgress",
        metrics={"usage": usage, "threadTotal": usage},
    )
    await reopened.record_turn(
        "alice",
        run.id,
        token,
        **options,
        status="interrupted",
        metrics={"durationMs": 4321, "completedAt": 104},
    )
    events = await reopened.events("alice", run.id)
    final = [e["payload"] for e in events if e["type"] == "run.turn"][-1]
    assert final["usage"] == usage
    assert final["durationMs"] == 4321
    assert final["model"] == "test-model"
    assert final["status"] == "interrupted"
    with pytest.raises(RunNotFound):
        await reopened.record_turn(
            "bob", run.id, token, **options, status="completed", metrics={}
        )


@pytest.mark.asyncio
async def test_usage_increments_are_durable_across_reconnect_and_native_turns(
    repository,
):
    run = await repository.create("alice", "session-a", "request-a", "build")
    token = await repository.claim("alice", run.id)

    async def record(turn, total, usage, status="inProgress"):
        await repository.record_turn(
            "alice",
            run.id,
            token,
            thread_id="thread",
            turn_id=turn,
            revision=1,
            status=status,
            metrics={
                "usage": {"totalTokens": usage},
                "threadTotal": {"totalTokens": total},
            },
        )

    await record("first", 100, 20)
    await record("first", 150, 50)  # new connection's usage counter reset
    await record("first", 150, 50, "completed")
    await record("second", 180, 30)
    await record("second", 10, 10)  # compaction/reset: no negative or invented tokens
    metrics = [
        e["payload"]
        for e in await repository.events("alice", run.id)
        if e["type"] == "run.turn"
    ]
    first = [m for m in metrics if m["turnId"] == "first"][-1]
    second = [m for m in metrics if m["turnId"] == "second"][-1]
    assert first["usage"]["totalTokens"] == 70
    assert second["usage"]["totalTokens"] == 30
    assert second["usageIncomplete"] is True
