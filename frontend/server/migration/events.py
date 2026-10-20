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

"""Append-only event log that turns the migration page from polling into a stream.

The Sandbox stays the source of truth.  One poller per task runs the very same service
calls the page used to issue, and appends an event only when a payload actually changed;
subscribers replay from their cursor and then follow the log.  A refresh, a second tab,
or a reconnecting client therefore resumes from a sequence number instead of driving its
own Sandbox reads, and progress no longer depends on a page being open.

Payloads are whole snapshots rather than deltas: each event replaces the previous value
of its kind, so replaying a bounded window is always safe and a client that fell behind
the retained history simply re-syncs instead of corrupting its view.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

TASK_EVENT = "task"
ACTIVITY_EVENT = "activity"
ERROR_EVENT = "error"
DONE_EVENT = "done"

DEFAULT_HISTORY_LIMIT = 256
DEFAULT_POLL_SECONDS = 1.5
DEFAULT_HEARTBEAT_SECONDS = 15.0
DEFAULT_IDLE_SECONDS = 120.0
DEFAULT_FAILURE_BACKOFF_SECONDS = 5.0
DEFAULT_MAX_STREAMS = 64


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: object) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MigrationEvent:
    """One immutable log entry; ``seq`` is the cursor the client resumes from."""

    seq: int
    type: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class MigrationSnapshot:
    """One read of a task, and whether it can still change without user action."""

    task: dict[str, object] | None = None
    activity: dict[str, object] | None = None
    error: dict[str, object] | None = None
    settled: bool = False


class MigrationEventLog:
    """Monotonic, bounded, append-only log with a per-waiter wake-up."""

    def __init__(self, *, history_limit: int = DEFAULT_HISTORY_LIMIT) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be positive")
        self._events: deque[MigrationEvent] = deque(maxlen=history_limit)
        self._seq = 0
        self._waiters: set[asyncio.Event] = set()

    @property
    def last_seq(self) -> int:
        return self._seq

    @property
    def earliest_seq(self) -> int:
        """First sequence still retained; one past the end while the log is empty."""
        return self._events[0].seq if self._events else self._seq + 1

    @property
    def size(self) -> int:
        return len(self._events)

    def append(self, event_type: str, payload: dict[str, object]) -> MigrationEvent:
        self._seq += 1
        event = MigrationEvent(self._seq, event_type, payload)
        self._events.append(event)
        waiters, self._waiters = self._waiters, set()
        for waiter in waiters:
            waiter.set()
        return event

    def replay(self, after: int) -> list[MigrationEvent]:
        """Retained events after ``after``; a stale cursor simply re-syncs."""
        return [event for event in self._events if event.seq > after]

    def wake(self) -> None:
        """Release every waiter so it can re-read state that is not in the log."""
        waiters, self._waiters = self._waiters, set()
        for waiter in waiters:
            waiter.set()

    async def wait(self, after: int, timeout: float) -> bool:
        """Wait for an event newer than ``after``; ``False`` when the wait timed out."""
        if self._seq > after:
            return True
        waiter = asyncio.Event()
        self._waiters.add(waiter)
        try:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(waiter.wait(), timeout)
        finally:
            self._waiters.discard(waiter)
        return self._seq > after


class MigrationStream:
    """One poller and one log for a single task.

    The poller is the only writer, so sequence numbers, change detection, and the
    ``done`` marker cannot race with a request handler.
    """

    def __init__(
        self,
        read: Callable[[], Awaitable[MigrationSnapshot]],
        *,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
        idle_seconds: float = DEFAULT_IDLE_SECONDS,
        failure_backoff_seconds: float = DEFAULT_FAILURE_BACKOFF_SECONDS,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> None:
        self.log = MigrationEventLog(history_limit=history_limit)
        self._read = read
        self._poll_seconds = poll_seconds
        self._heartbeat_seconds = heartbeat_seconds
        self._idle_seconds = idle_seconds
        self._failure_backoff_seconds = failure_backoff_seconds
        self._digests: dict[str, str] = {}
        self._subscribers = 0
        self._retire_at: float | None = None
        self._settled = False
        self._retired = False
        self._runner: asyncio.Task[None] | None = None
        self._failures = 0

    @property
    def settled(self) -> bool:
        return self._settled

    @property
    def subscribers(self) -> int:
        return self._subscribers

    @property
    def idle(self) -> bool:
        """No subscriber is attached and the resume window has elapsed."""
        return (
            self._subscribers == 0
            and self._retire_at is not None
            and time.monotonic() - self._retire_at >= self._idle_seconds
        )

    def attach(self) -> None:
        self._subscribers += 1
        self._retire_at = None
        if self._settled:
            # Nothing left to poll: the follower replays the log and returns on ``done``.
            return
        if self._runner is None or self._runner.done():
            self._runner = asyncio.create_task(self._run())

    def detach(self) -> None:
        self._subscribers = max(0, self._subscribers - 1)
        if self._subscribers == 0:
            self._retire_at = time.monotonic()

    def retire(self) -> None:
        """Stop polling and make every follower return.

        Retirement is not settlement: the task may still be running, the hub just has no
        reason to keep a stream for it.  A later subscriber builds a fresh stream.
        """
        self._retired = True
        runner = self._runner
        if runner is not None and not runner.done():
            runner.cancel()
        self.log.wake()

    async def follow(self, after: int) -> AsyncIterator[MigrationEvent | None]:
        """Replay from ``after`` and then follow; ``None`` marks a heartbeat."""
        cursor = after
        while True:
            for event in self.log.replay(cursor):
                cursor = event.seq
                yield event
                if event.type == DONE_EVENT:
                    return
            if self._settled or self._retired:
                return
            if not await self.log.wait(cursor, self._heartbeat_seconds):
                yield None

    async def _run(self) -> None:
        try:
            while True:
                try:
                    snapshot = await self._read()
                except asyncio.CancelledError:
                    raise
                except Exception as error:  # noqa: BLE001 - the page must survive a read fault
                    self._failures += 1
                    if self._failures == 1 or self._failures % 10 == 0:
                        logger.warning(
                            "Studio migration event read failed attempts=%d error_type=%s",
                            self._failures,
                            type(error).__name__,
                        )
                    self._publish(
                        MigrationSnapshot(
                            error={
                                "code": "MIGRATION_EVENT_READ_FAILED",
                                "message": "迁移状态暂时无法读取，正在重试。",
                                "retryable": True,
                            }
                        )
                    )
                    if self.idle:
                        return
                    await asyncio.sleep(self._failure_backoff_seconds)
                    continue
                self._failures = 0
                self._publish(snapshot)
                if self._settled or self._retired:
                    return
                if self.idle:
                    return
                await asyncio.sleep(self._poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a dead poller must not kill the loop silently
            logger.exception("Studio migration event poller failed")

    def _publish(self, snapshot: MigrationSnapshot) -> None:
        if snapshot.error is None:
            # Clearing is a change too: a follower must drop a stale read-failure
            # banner even when nothing else about the task moved.  An ``error`` event
            # without a code or a message is that "readable again" frame.
            if self._digests.pop(ERROR_EVENT, None) is not None:
                self.log.append(ERROR_EVENT, {})
        else:
            self._append_changed(ERROR_EVENT, dict(snapshot.error))
        if snapshot.task is not None:
            self._append_changed(TASK_EVENT, snapshot.task)
        if snapshot.activity is not None:
            self._append_changed(ACTIVITY_EVENT, snapshot.activity)
        if snapshot.settled:
            self._settle(snapshot.task)

    def _settle(self, task: dict[str, object] | None) -> None:
        if self._settled:
            return
        self._settled = True
        state = str(task.get("state") or "") if isinstance(task, dict) else ""
        self.log.append(DONE_EVENT, {"state": state, "at": _timestamp()})

    def _append_changed(self, event_type: str, payload: dict[str, object]) -> None:
        digest = _digest(payload)
        if self._digests.get(event_type) == digest:
            return
        self._digests[event_type] = digest
        self.log.append(event_type, payload)


class MigrationEventHub:
    """One stream per task, created on demand and dropped once nobody listens."""

    def __init__(
        self,
        read: Callable[[Hashable], Callable[[], Awaitable[MigrationSnapshot]]],
        *,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
        idle_seconds: float = DEFAULT_IDLE_SECONDS,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        max_streams: int = DEFAULT_MAX_STREAMS,
    ) -> None:
        self._read = read
        self._poll_seconds = poll_seconds
        self._heartbeat_seconds = heartbeat_seconds
        self._idle_seconds = idle_seconds
        self._history_limit = history_limit
        self._max_streams = max(1, max_streams)
        self._streams: dict[Hashable, MigrationStream] = {}

    def peek(self, key: Hashable) -> MigrationStream | None:
        return self._streams.get(key)

    def stream(self, key: Hashable) -> MigrationStream:
        """The live stream for ``key``, or a fresh one once it settled or went idle.

        A settled stream must never be handed out again: its log stops growing, so the
        next subscriber would be told the task is over without anyone re-reading it.
        """
        current = self._streams.get(key)
        if current is not None and not current.idle and not current.settled:
            return current
        if current is not None:
            current.retire()
        self._trim(extra=1)
        stream = MigrationStream(
            self._read(key),
            poll_seconds=self._poll_seconds,
            heartbeat_seconds=self._heartbeat_seconds,
            idle_seconds=self._idle_seconds,
            history_limit=self._history_limit,
        )
        self._streams[key] = stream
        return stream

    @asynccontextmanager
    async def subscription(self, key: Hashable) -> AsyncIterator[MigrationStream]:
        """Attach for the lifetime of the block, then drop the stream once idle."""
        stream = self.stream(key)
        stream.attach()
        try:
            yield stream
        finally:
            stream.detach()
            self._reap()

    def close(self) -> None:
        """Stop every poller; used on application shutdown."""
        for stream in self._streams.values():
            stream.retire()
        self._streams.clear()

    def _reap(self) -> None:
        for key, stream in list(self._streams.items()):
            if stream.idle:
                self._streams.pop(key, None)
                stream.retire()

    def _trim(self, *, extra: int) -> None:
        while len(self._streams) + extra > self._max_streams:
            idle = [key for key, stream in self._streams.items() if stream.idle]
            candidates = idle or list(self._streams)
            key = candidates[0]
            self._streams.pop(key, None).retire()


__all__ = [
    "ACTIVITY_EVENT",
    "DONE_EVENT",
    "ERROR_EVENT",
    "TASK_EVENT",
    "MigrationEvent",
    "MigrationEventHub",
    "MigrationEventLog",
    "MigrationSnapshot",
    "MigrationStream",
]
