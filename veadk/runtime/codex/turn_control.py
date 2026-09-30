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

"""Turn control for persistent Codex threads.

Once a Codex thread outlives one invocation, several turns can reach the same
thread, and the app-server's turn semantics become load-bearing. Measured
against the pinned Codex binary (0.159.2):

- ``thread.turn()`` while a regular turn is active does **not** start a turn:
  it *joins* the active one (same turn id) and the input is steered into it.
  Racing ``interrupt()`` against ``turn()`` joined the dying turn in 2 of 5
  runs, and the new input was lost with it.
- ``interrupt()`` issued right after ``turn()`` returns, before the turn has
  sent its first model request, fails with JSON-RPC ``-32600`` "no active turn
  to interrupt" (:class:`openai_codex.InvalidRequestError`) -- and the turn
  then runs to completion as if nothing had been asked.
- After an accepted interrupt, ``turn/completed`` (status ``interrupted``)
  arrives 10-70 ms later, including mid ``exec_command`` (the tool output
  reads "aborted by user"). Until then the turn is still active and a
  ``turn()`` would join it.
- ``thread.compact()`` returns immediately and runs a separate compaction
  turn. A ``turn()`` during it fails with ``-32603``
  ``ActiveTurnNotSteerable { turn_kind: Compact }``
  (:class:`openai_codex.InternalRpcError`). Its events reach no turn handle;
  the only way to see it finish is ``thread.read(include_turns=True)``, where
  it appears as a turn holding a single ``contextCompaction`` item. Ephemeral
  threads reject ``include_turns`` (``-32600``).
- ``steer()`` on a finished turn fails with ``-32600`` "no active turn to
  steer"; on a stale turn id while another turn is active, ``-32600``
  "expected active turn id ... but found ...".

This module turns those facts into a small set of primitives. None of them
starts a model request on its own; they only sequence the SDK calls the
runtime already makes.

Wiring into ``CodexRuntime.run_async`` (one invocation = one turn)::

    key = session_key(app_name, user_id, session_id, agent.name)
    async with SESSION_LOCKS.hold(key):              # serialise turns per session
        handle = await start_fresh_turn(thread, input_items,
                                        previous_turn_id=last_turn_id, ...)
        completion = TurnCompletion(handle.id)

        async def _pump_codex():
            try:
                async for note in handle.stream():
                    completion.observe(note)          # resolves on turn/completed
                    ...translate + event_queue.put(...)
            except BaseException as e:
                await event_queue.put(e)
            finally:
                completion.close()                    # stream ended: never hang waiters
                await event_queue.put(_QUEUE_DONE)

        pump = asyncio.create_task(_pump_codex())
        watchdog = asyncio.create_task(run_with_turn_timeout(
            handle, pump, completion=completion,
            timeout=config.turn_timeout_seconds, grace=config.interrupt_grace_seconds))
        with ACTIVE_TURNS.register(key, handle, completion=completion):
            while True:
                queued = await event_queue.get()
                if queued is _QUEUE_DONE:
                    break
                if isinstance(queued, BaseException):
                    # a pump cancelled by the watchdog shows up here first
                    if watchdog.done() and watchdog.exception() is not None:
                        raise watchdog.exception()
                    raise queued
                yield ...
        await watchdog          # raises CodexTurnTimeout if the deadline fired
        last_turn_id = handle.id

    # on invocation cancellation (CancelledError), replace the bare
    # ``await turn.interrupt()`` with
    #     await interrupt_turn(handle, completion=completion, timeout=grace)
    # so the next invocation's ``start_fresh_turn`` cannot join the dying turn.

A "steer" entry point (an API that adds user input to a running invocation)
calls ``await ACTIVE_TURNS.steer(key, text)`` and reports "no active turn" to
its caller on ``False``. It must *not* fall back to ``thread.turn()``: that
would race the running invocation for the same thread.

Compaction (``compact_and_wait``) must run while holding the session lock, on a
non-ephemeral thread, and between turns; a ``turn()`` racing it fails with
``ActiveTurnNotSteerable`` (see :func:`is_turn_not_steerable`), which
:func:`start_fresh_turn` retries within its ``start_timeout``.

All primitives are process-local. A second worker process holding the same
Codex thread is out of scope; the session lock only serialises this process.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Hashable, Iterator
from typing import Any, Protocol, TypeVar

from openai_codex import (  # type: ignore[import-not-found]
    CodexRpcError,
    InternalRpcError,
    InvalidRequestError,
)

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

#: ``interrupt_turn``'s result when the turn's stream ended without a
#: ``turn/completed`` notification (the pump failed or was cancelled).
STATUS_UNKNOWN = "unknown"

_TURN_COMPLETED = "turn/completed"
_COMPACTION_ITEM = "contextCompaction"
_IN_PROGRESS = "inProgress"

SessionKey = tuple[str, str, str, str]


def session_key(
    app_name: str, user_id: str, session_id: str, agent_name: str
) -> SessionKey:
    """The key every per-session primitive here is indexed by.

    The agent name is part of it because each agent of a multi-agent app gets
    its own Codex thread for the same ADK session.
    """
    return (app_name, user_id, session_id, agent_name)


class CodexTurnTimeout(TimeoutError):
    """A Codex turn exceeded the runtime's turn-level timeout.

    Attributes:
        turn_id: The turn that timed out.
        timeout: The timeout that expired, in seconds.
        status: The turn's final status once the interrupt landed
            (normally ``"interrupted"``; ``"completed"`` if it finished while
            being stopped), or ``None`` if the stop could not be confirmed
            within the grace period.
    """

    def __init__(self, turn_id: str, timeout: float, status: str | None) -> None:
        self.turn_id = turn_id
        self.timeout = timeout
        self.status = status
        stopped = (
            f"stopped with status {status!r}"
            if status is not None
            else "could not be confirmed stopped"
        )
        super().__init__(
            f"Codex turn {turn_id} exceeded its {timeout:g}s timeout and {stopped}"
        )

    @property
    def stopped(self) -> bool:
        """Whether the turn is known to have ended on the Codex side."""
        return self.status is not None


class CodexInterruptTimeout(TimeoutError):
    """An interrupt could not be confirmed (no ``turn/completed``) in time.

    The turn may still be running; a ``turn()`` on the same thread would join
    it. The caller should treat the thread as unusable (drop the cached
    thread / restart the Codex process) rather than start another turn.
    """

    def __init__(self, turn_id: str, timeout: float) -> None:
        self.turn_id = turn_id
        self.timeout = timeout
        super().__init__(
            f"Codex turn {turn_id} did not report turn/completed within "
            f"{timeout:g}s of being interrupted"
        )


class CodexCompactTimeout(TimeoutError):
    """The compaction turn started by ``thread.compact()`` did not finish."""


class CodexTurnJoinedError(RuntimeError):
    """``thread.turn()`` kept joining an older turn instead of starting one."""

    def __init__(self, turn_id: str) -> None:
        self.turn_id = turn_id
        super().__init__(
            f"thread.turn() kept joining still-active turn {turn_id}; "
            "the previous turn was not stopped before a new one was started"
        )


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def _rpc_message(exc: BaseException) -> str:
    return str(getattr(exc, "message", "") or exc).lower()


def is_no_active_turn(exc: BaseException) -> bool:
    """``-32600`` "no active turn to interrupt/steer" (or a stale turn id).

    Raised for a turn that has not reached its first model request yet *and*
    for one that already finished; only the turn's own ``turn/completed``
    tells the two apart.
    """
    if not isinstance(exc, InvalidRequestError):
        return False
    message = _rpc_message(exc)
    return "no active turn" in message or "expected active turn id" in message


def is_turn_not_steerable(exc: BaseException) -> bool:
    """``-32603`` ``ActiveTurnNotSteerable``: a compaction turn is running."""
    return isinstance(exc, InternalRpcError) and (
        "activeturnnotsteerable" in _rpc_message(exc)
    )


def _status_value(status: Any) -> str:
    """``TurnStatus.interrupted`` -> ``"interrupted"``; ``None`` -> unknown."""
    if status is None:
        return STATUS_UNKNOWN
    return str(getattr(status, "value", status))


# ---------------------------------------------------------------------------
# Per-session lock
# ---------------------------------------------------------------------------


class _LockEntry:
    __slots__ = ("lock", "users")

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.users = 0


class SessionTurnLocks:
    """One ``asyncio.Lock`` per session key, dropped when nobody holds or waits.

    Hold it for the whole invocation (turn start through the last event), and
    for compaction. Waiters queue in FIFO order, so a second message for the
    same session runs after the first instead of joining its turn.
    """

    def __init__(self) -> None:
        self._entries: dict[Hashable, _LockEntry] = {}

    @contextlib.asynccontextmanager
    async def hold(self, key: Hashable) -> AsyncIterator[None]:
        # No await between registering as a user and acquiring, and the
        # count is dropped in `finally`, so a waiter cancelled while queued
        # does not pin the entry forever.
        entry = self._entries.get(key)
        if entry is None:
            entry = self._entries[key] = _LockEntry()
        entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.users -= 1
            if entry.users == 0 and self._entries.get(key) is entry:
                del self._entries[key]

    def is_busy(self, key: Hashable) -> bool:
        """True while some task holds or waits for ``key``'s lock."""
        return key in self._entries

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Turn completion
# ---------------------------------------------------------------------------


class TurnCompletion:
    """Resolves once a turn's ``turn/completed`` has been seen on its stream.

    The stream consumer (the runtime's pump) feeds every notification to
    :meth:`observe` and calls :meth:`close` when the stream ends for any
    reason, so a waiter never outlives the stream. Must be created inside a
    running event loop.
    """

    def __init__(self, turn_id: str) -> None:
        self.turn_id = turn_id
        self.future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def observe(self, notification: Any) -> bool:
        """Record ``notification``; True if it completed this turn."""
        if getattr(notification, "method", None) != _TURN_COMPLETED:
            return False
        turn = getattr(getattr(notification, "payload", None), "turn", None)
        if turn is None or getattr(turn, "id", None) != self.turn_id:
            return False
        if not self.future.done():
            self.future.set_result(_status_value(getattr(turn, "status", None)))
        return True

    def close(self) -> None:
        """The stream ended; resolve as ``STATUS_UNKNOWN`` if not completed."""
        if not self.future.done():
            self.future.set_result(STATUS_UNKNOWN)

    def done(self) -> bool:
        return self.future.done()

    @property
    def status(self) -> str | None:
        return self.future.result() if self.future.done() else None


def _as_future(
    completion: "TurnCompletion | Awaitable[Any]",
) -> tuple[asyncio.Future[Any], bool]:
    """Normalise to a future; the bool says whether we own (may cancel) it."""
    if isinstance(completion, TurnCompletion):
        return completion.future, False
    if isinstance(completion, asyncio.Future):
        return completion, False
    return asyncio.ensure_future(completion), True


# ---------------------------------------------------------------------------
# Active turns (steer)
# ---------------------------------------------------------------------------


class _Steerable(Protocol):
    id: str

    async def steer(self, input: Any) -> Any: ...


class ActiveTurns:
    """Process-local registry of the turn each session is currently running.

    Only the invocation that owns the turn registers it (see
    :meth:`register`), so :meth:`steer` can add input to that turn without
    ever creating one.
    """

    def __init__(self) -> None:
        self._turns: dict[Hashable, tuple[_Steerable, TurnCompletion | None]] = {}

    @contextlib.contextmanager
    def register(
        self,
        key: Hashable,
        handle: _Steerable,
        *,
        completion: TurnCompletion | None = None,
    ) -> Iterator[None]:
        """Mark ``handle`` as ``key``'s active turn for the ``with`` body.

        With ``completion``, :meth:`steer` stops targeting the turn as soon as
        its ``turn/completed`` is observed, before the ``with`` block exits.
        """
        current = self._turns.get(key)
        if current is not None and current[0] is not handle:
            raise RuntimeError(
                f"session {key!r} already has active turn {current[0].id}; "
                "turns for one session must be serialised (SessionTurnLocks)"
            )
        self._turns[key] = (handle, completion)
        try:
            yield
        finally:
            entry = self._turns.get(key)
            if entry is not None and entry[0] is handle:
                del self._turns[key]

    def get(self, key: Hashable) -> _Steerable | None:
        entry = self._turns.get(key)
        if entry is None:
            return None
        handle, completion = entry
        if completion is not None and completion.done():
            return None
        return handle

    async def steer(self, key: Hashable, text: str) -> bool:
        """Add ``text`` to ``key``'s running turn.

        Returns False when the session has no active turn -- including when
        the turn finished between the lookup and the RPC (``-32600``). Never
        starts a turn. Other RPC errors propagate.
        """
        handle = self.get(key)
        if handle is None:
            return False
        try:
            await handle.steer(text)
        except CodexRpcError as exc:
            if is_no_active_turn(exc):
                return False
            raise
        return True

    def __len__(self) -> int:
        return len(self._turns)


# ---------------------------------------------------------------------------
# Interrupt
# ---------------------------------------------------------------------------


class _Interruptible(Protocol):
    id: str

    async def interrupt(self) -> Any: ...


async def interrupt_turn(
    handle: _Interruptible,
    *,
    completion: "TurnCompletion | Awaitable[Any]",
    timeout: float,
    retry_interval: float = 0.05,
) -> str:
    """Stop ``handle``'s turn and wait until it has really ended.

    ``interrupt()`` is rejected with "no active turn" both before the turn's
    first model request and after it ended, so a rejection is retried every
    ``retry_interval`` until either the interrupt is accepted or
    ``completion`` resolves (the turn finished on its own). After an accepted
    interrupt the turn is still active until its ``turn/completed``
    (interrupted) arrives, so this then waits for ``completion`` too.

    Args:
        handle: The turn to stop.
        completion: Resolves when the turn's ``turn/completed`` has been
            observed by whoever consumes ``handle.stream()`` -- a
            :class:`TurnCompletion`, a future, or any awaitable. Its result is
            the final status. It is never cancelled if the caller owns it.
        timeout: Overall budget for the interrupt and the wait, in seconds.
        retry_interval: Delay between rejected interrupt attempts.

    Returns:
        The final status: ``"interrupted"``, ``"completed"`` if the turn beat
        the interrupt, ``"failed"``, or ``STATUS_UNKNOWN`` if the stream ended
        without a ``turn/completed``.

    Raises:
        CodexInterruptTimeout: Completion was not observed within ``timeout``.
            The turn may still be running.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    done_future, owned = _as_future(completion)
    try:
        attempts = 0
        while not done_future.done():
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise CodexInterruptTimeout(handle.id, timeout)
            attempts += 1
            try:
                await asyncio.wait_for(handle.interrupt(), remaining)
            except CodexRpcError as exc:
                if not is_no_active_turn(exc):
                    raise
                # Not started yet, or already over: only completion can say.
                await asyncio.wait(
                    {done_future},
                    timeout=min(retry_interval, max(deadline - loop.time(), 0)),
                )
                continue
            except asyncio.TimeoutError:
                raise CodexInterruptTimeout(handle.id, timeout) from None
            logger.debug(
                "codex_interrupt_accepted turn_id=%s attempts=%d", handle.id, attempts
            )
            break
        remaining = deadline - loop.time()
        if not done_future.done():
            await asyncio.wait({done_future}, timeout=max(remaining, 0))
        if not done_future.done():
            raise CodexInterruptTimeout(handle.id, timeout)
        if done_future.cancelled() or done_future.exception() is not None:
            # The stream consumer died: the turn is over as far as it can tell.
            return STATUS_UNKNOWN
        return _status_value(done_future.result())
    finally:
        if owned and not done_future.done():
            done_future.cancel()


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------


class _Thread(Protocol):
    async def turn(self, input: Any, **kwargs: Any) -> Any: ...


async def start_fresh_turn(
    thread: _Thread,
    input: Any,
    *,
    previous_turn_id: str | None,
    start_timeout: float = 10.0,
    retry_interval: float = 0.1,
    **turn_kwargs: Any,
) -> Any:
    """``thread.turn(input, **turn_kwargs)`` that never returns a joined turn.

    ``turn()`` joins whatever regular turn is still active, so a handle whose
    id equals ``previous_turn_id`` means the previous turn has not ended and
    ``input`` was steered into it. That is retried until a genuinely new turn
    starts. It should never happen when the previous turn was stopped with
    :func:`interrupt_turn` (which waits for its ``turn/completed``); this is
    the backstop. Note the joined input is not taken back: if the old turn
    was not interrupted it may also answer it.

    A turn start rejected with ``ActiveTurnNotSteerable`` (a compaction turn
    is running) is retried the same way. Any other error propagates.

    Raises:
        CodexTurnJoinedError: Still joining ``previous_turn_id`` after
            ``start_timeout``.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + start_timeout
    while True:
        try:
            handle = await thread.turn(input, **turn_kwargs)
        except CodexRpcError as exc:
            if not is_turn_not_steerable(exc) or loop.time() >= deadline:
                raise
            logger.info("codex_turn_start_blocked_by_compaction; retrying")
            await asyncio.sleep(retry_interval)
            continue
        if previous_turn_id is None or handle.id != previous_turn_id:
            return handle
        logger.warning(
            "codex_turn_joined_previous turn_id=%s; previous turn still active",
            handle.id,
        )
        if loop.time() >= deadline:
            raise CodexTurnJoinedError(handle.id)
        await asyncio.sleep(retry_interval)


# ---------------------------------------------------------------------------
# Compact
# ---------------------------------------------------------------------------


class _Compactable(Protocol):
    async def compact(self) -> Any: ...

    async def read(self, *, include_turns: bool = False) -> Any: ...


def _item_type(item: Any) -> str | None:
    root = getattr(item, "root", item)
    return getattr(root, "type", None)


def _is_compaction_turn(turn: Any) -> bool:
    items = getattr(turn, "items", None) or []
    return any(_item_type(item) == _COMPACTION_ITEM for item in items)


async def _turns(thread: _Compactable) -> list[Any]:
    response = await thread.read(include_turns=True)
    return list(getattr(response.thread, "turns", None) or [])


async def compact_and_wait(
    thread: _Compactable, *, timeout: float, poll_interval: float = 0.2
) -> str:
    """Compact ``thread`` and return once the compaction turn has finished.

    ``thread.compact()`` only *starts* a compaction turn, and that turn's
    events reach no turn handle, so completion is observed by polling
    ``thread.read(include_turns=True)`` for a new turn that is no longer in
    progress. The thread must be non-ephemeral (ephemeral threads reject
    ``include_turns`` with ``-32600``; that error surfaces before anything is
    compacted).

    Call it holding the session's :class:`SessionTurnLocks` lock and with no
    turn running. A ``turn()`` that races the compaction anyway fails with
    ``ActiveTurnNotSteerable`` -- retrying that is the caller's concern
    (:func:`start_fresh_turn` does).

    Returns:
        The compaction turn's final status (``"completed"``, ``"failed"``,
        ...). A failed compaction is reported, not raised.

    Raises:
        CodexCompactTimeout: The compaction turn did not finish in ``timeout``.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    known = {getattr(turn, "id", None) for turn in await _turns(thread)}
    await thread.compact()
    while True:
        new_turns = [t for t in await _turns(thread) if t.id not in known]
        for turn in new_turns:
            status = _status_value(getattr(turn, "status", None))
            if status != _IN_PROGRESS and _is_compaction_turn(turn):
                return status
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise CodexCompactTimeout(
                f"Codex compaction did not finish within {timeout:g}s"
            )
        await asyncio.sleep(min(poll_interval, remaining))


# ---------------------------------------------------------------------------
# Turn timeout
# ---------------------------------------------------------------------------


async def run_with_turn_timeout(
    handle: _Interruptible,
    work: Awaitable[T],
    *,
    completion: "TurnCompletion | Awaitable[Any]",
    timeout: float | None,
    grace: float = 5.0,
) -> T:
    """Await ``work`` (the turn's stream pump) under a turn-level deadline.

    Within ``timeout`` this is just ``await work``. Past it, the turn is
    stopped with :func:`interrupt_turn` (budget ``grace``), ``work`` is given
    the rest of ``grace`` to drain what the interrupt flushed, and
    :class:`CodexTurnTimeout` is raised. If ``work`` still has not finished
    it is cancelled, so a consumer blocked on the pump's queue wakes up.

    Run it as a task next to the pump (see the module docstring): ``work``
    keeps being consumed while this waits, and ``await``-ing the task after
    the pump finished yields ``work``'s result or the timeout.

    Args:
        handle: The turn to interrupt on timeout.
        work: The pump. A task/future is never cancelled before the deadline
            (not even if this coroutine is cancelled); a bare coroutine is
            wrapped in a task owned here.
        completion: As for :func:`interrupt_turn`.
        timeout: Seconds; ``None`` disables the deadline.
        grace: Seconds allowed for the interrupt and the drain after it.

    Raises:
        CodexTurnTimeout: The deadline fired. ``status`` is ``None`` when the
            turn could not be confirmed stopped.
    """
    owned = not isinstance(work, asyncio.Future)
    task: asyncio.Future[T] = asyncio.ensure_future(work)
    try:
        done, _ = await asyncio.wait({task}, timeout=timeout)
        if done or timeout is None:
            return task.result()
        loop = asyncio.get_running_loop()
        grace_deadline = loop.time() + grace
        logger.warning(
            "codex_turn_timeout turn_id=%s timeout=%s; interrupting",
            handle.id,
            timeout,
        )
        status: str | None
        try:
            status = await interrupt_turn(handle, completion=completion, timeout=grace)
        except CodexInterruptTimeout:
            status = None
        except CodexRpcError as exc:
            logger.warning(
                "codex_turn_timeout_interrupt_failed turn_id=%s error=%s",
                handle.id,
                exc,
            )
            status = None
        if not task.done():
            await asyncio.wait({task}, timeout=max(grace_deadline - loop.time(), 0))
        if not task.done():
            task.cancel()
        elif not task.cancelled() and task.exception() is not None:
            # Retrieved so asyncio does not log it; the timeout is the cause.
            logger.debug(
                "codex_turn_timeout_pump_error turn_id=%s error=%r",
                handle.id,
                task.exception(),
            )
        raise CodexTurnTimeout(handle.id, timeout, status)
    finally:
        if owned and not task.done():
            task.cancel()
