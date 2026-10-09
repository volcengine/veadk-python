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

"""``veadk.runtime.codex.turn_control``: unit tests on fakes + real-binary smoke.

The unit tests drive every branch with small in-process fakes that raise the
SDK's real error classes with the codes/messages the Codex 0.159.2 app-server
was observed to send. The ``codex_smoke`` tests (opt in with
``CODEX_RUN_SMOKE=1``) run the same primitives against the real Codex binary,
with a stub Responses backend on a loopback port standing in for the model --
no model is called.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

pytest.importorskip("openai_codex")

from openai_codex import InternalRpcError, InvalidRequestError  # noqa: E402

from veadk.runtime.codex.turn_control import (  # noqa: E402
    STATUS_UNKNOWN,
    ActiveTurns,
    CodexCompactTimeout,
    CodexInterruptTimeout,
    CodexTurnJoinedError,
    CodexTurnTimeout,
    SessionTurnLocks,
    TurnCompletion,
    compact_and_wait,
    interrupt_turn,
    is_no_active_turn,
    is_turn_not_steerable,
    run_with_turn_timeout,
    session_key,
    start_fresh_turn,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_codex_runtime_smoke import _skip_reason  # noqa: E402

KEY = session_key("app", "user", "session", "agent")
OTHER = session_key("app", "user", "session-2", "agent")


def _no_active(verb: str = "interrupt") -> InvalidRequestError:
    return InvalidRequestError(-32600, f"no active turn to {verb}")


def _not_steerable() -> InternalRpcError:
    return InternalRpcError(
        -32603,
        "failed to submit turn input: ActiveTurnNotSteerable { turn_kind: Compact }",
    )


def _completed_note(turn_id: str, status: str) -> SimpleNamespace:
    return SimpleNamespace(
        method="turn/completed",
        payload=SimpleNamespace(turn=SimpleNamespace(id=turn_id, status=status)),
    )


class FakeHandle:
    """A turn handle whose interrupt/steer replay a scripted list of outcomes."""

    def __init__(self, turn_id: str = "turn-1", *, interrupts=(), steers=()) -> None:
        self.id = turn_id
        self._interrupts = list(interrupts)
        self._steers = list(steers)
        self.interrupt_calls = 0
        self.steered: list[Any] = []

    async def interrupt(self) -> None:
        self.interrupt_calls += 1
        outcome = self._interrupts.pop(0) if self._interrupts else None
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            outcome()

    async def steer(self, text: Any) -> None:
        outcome = self._steers.pop(0) if self._steers else None
        if isinstance(outcome, BaseException):
            raise outcome
        self.steered.append(text)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def test_error_predicates_match_observed_server_errors() -> None:
    assert is_no_active_turn(_no_active("interrupt"))
    assert is_no_active_turn(_no_active("steer"))
    assert is_no_active_turn(
        InvalidRequestError(-32600, "expected active turn id `a` but found `b`")
    )
    assert not is_no_active_turn(InvalidRequestError(-32600, "bad params"))
    assert not is_no_active_turn(_not_steerable())
    assert is_turn_not_steerable(_not_steerable())
    assert not is_turn_not_steerable(InternalRpcError(-32603, "boom"))
    assert not is_turn_not_steerable(_no_active())


# ---------------------------------------------------------------------------
# SessionTurnLocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_locks_serialise_one_key_and_isolate_others() -> None:
    locks = SessionTurnLocks()
    order: list[str] = []
    first_in = asyncio.Event()
    release = asyncio.Event()

    async def first() -> None:
        async with locks.hold(KEY):
            order.append("first-in")
            first_in.set()
            await release.wait()
            order.append("first-out")

    async def second() -> None:
        async with locks.hold(KEY):
            order.append("second-in")

    async def other() -> None:
        async with locks.hold(OTHER):
            order.append("other-in")

    t1 = asyncio.create_task(first())
    await first_in.wait()
    t2 = asyncio.create_task(second())
    await asyncio.wait_for(other(), 1)  # a different session is not blocked
    await asyncio.sleep(0)
    assert order == ["first-in", "other-in"]
    assert locks.is_busy(KEY)
    release.set()
    await asyncio.gather(t1, t2)
    assert order == ["first-in", "other-in", "first-out", "second-in"]


@pytest.mark.asyncio
async def test_session_locks_drop_idle_entries_including_cancelled_waiters() -> None:
    locks = SessionTurnLocks()
    for i in range(50):
        async with locks.hold(session_key("app", "u", f"s{i}", "a")):
            pass
    assert len(locks) == 0

    holder_in = asyncio.Event()
    release = asyncio.Event()

    async def holder() -> None:
        async with locks.hold(KEY):
            holder_in.set()
            await release.wait()

    async def waiter() -> None:
        async with locks.hold(KEY):
            pass

    h = asyncio.create_task(holder())
    await holder_in.wait()
    w = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    w.cancel()
    with pytest.raises(asyncio.CancelledError):
        await w
    release.set()
    await h
    assert len(locks) == 0
    assert not locks.is_busy(KEY)


@pytest.mark.asyncio
async def test_session_lock_released_when_body_raises() -> None:
    locks = SessionTurnLocks()
    with pytest.raises(ValueError):
        async with locks.hold(KEY):
            raise ValueError("boom")
    assert len(locks) == 0
    async with locks.hold(KEY):  # not left locked
        pass


# ---------------------------------------------------------------------------
# TurnCompletion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_completion_only_resolves_on_its_own_turn_completed() -> None:
    completion = TurnCompletion("turn-1")
    assert not completion.observe(SimpleNamespace(method="item/started", payload=None))
    assert not completion.observe(_completed_note("turn-0", "completed"))
    assert not completion.done() and completion.status is None
    status_enum = SimpleNamespace(value="interrupted")
    assert completion.observe(_completed_note("turn-1", status_enum))
    assert completion.status == "interrupted"
    completion.close()  # no-op once resolved
    assert completion.status == "interrupted"

    closed = TurnCompletion("turn-2")
    closed.close()
    assert closed.status == STATUS_UNKNOWN


# ---------------------------------------------------------------------------
# ActiveTurns / steer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_steer_without_active_turn_returns_false_and_starts_nothing() -> None:
    turns = ActiveTurns()
    assert await turns.steer(KEY, "more") is False
    assert len(turns) == 0


@pytest.mark.asyncio
async def test_steer_reaches_only_the_registered_turn_and_unregisters() -> None:
    turns = ActiveTurns()
    handle = FakeHandle()
    with turns.register(KEY, handle):
        assert await turns.steer(KEY, "more") is True
        assert await turns.steer(OTHER, "nope") is False
        with pytest.raises(RuntimeError):
            with turns.register(KEY, FakeHandle("turn-2")):
                pass
        assert turns.get(KEY) is handle  # the rejected register did not evict
    assert handle.steered == ["more"]
    assert await turns.steer(KEY, "late") is False
    assert len(turns) == 0


@pytest.mark.asyncio
async def test_steer_after_completion_or_server_side_end_returns_false() -> None:
    turns = ActiveTurns()
    completion = TurnCompletion("turn-1")
    handle = FakeHandle(steers=[_no_active("steer")])
    with turns.register(KEY, handle, completion=completion):
        # The turn ended on the server before the RPC landed.
        assert await turns.steer(KEY, "raced") is False
        completion.observe(_completed_note("turn-1", "completed"))
        # Completion observed: not even attempted.
        assert await turns.steer(KEY, "late") is False
    assert handle.steered == []


@pytest.mark.asyncio
async def test_steer_propagates_unexpected_rpc_errors() -> None:
    turns = ActiveTurns()
    handle = FakeHandle(steers=[InternalRpcError(-32603, "boom")])
    with turns.register(KEY, handle):
        with pytest.raises(InternalRpcError):
            await turns.steer(KEY, "x")


# ---------------------------------------------------------------------------
# interrupt_turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interrupt_retries_until_the_turn_has_started() -> None:
    completion = TurnCompletion("turn-1")
    loop = asyncio.get_running_loop()

    def accepted() -> None:
        # The server sends turn/completed(interrupted) a little after.
        loop.call_later(
            0.02, completion.observe, _completed_note("turn-1", "interrupted")
        )

    handle = FakeHandle(interrupts=[_no_active(), _no_active(), accepted])
    status = await interrupt_turn(
        handle, completion=completion, timeout=2, retry_interval=0.01
    )
    assert status == "interrupted"
    assert handle.interrupt_calls == 3


@pytest.mark.asyncio
async def test_interrupt_waits_for_turn_completed_after_acceptance() -> None:
    completion = TurnCompletion("turn-1")
    handle = FakeHandle(interrupts=[None])
    task = asyncio.create_task(interrupt_turn(handle, completion=completion, timeout=2))
    await asyncio.sleep(0.05)
    assert not task.done()  # accepted, but the turn is still active
    completion.observe(_completed_note("turn-1", "interrupted"))
    assert await task == "interrupted"
    assert handle.interrupt_calls == 1


@pytest.mark.asyncio
async def test_interrupt_of_a_turn_that_finished_on_its_own_reports_completed() -> None:
    completion = TurnCompletion("turn-1")
    loop = asyncio.get_running_loop()
    loop.call_later(0.03, completion.observe, _completed_note("turn-1", "completed"))
    handle = FakeHandle(interrupts=[_no_active()] * 1000)
    status = await interrupt_turn(
        handle, completion=completion, timeout=2, retry_interval=0.01
    )
    assert status == "completed"

    already = TurnCompletion("turn-2")
    already.observe(_completed_note("turn-2", "failed"))
    idle = FakeHandle("turn-2")
    assert await interrupt_turn(idle, completion=already, timeout=1) == "failed"
    assert idle.interrupt_calls == 0


@pytest.mark.asyncio
async def test_interrupt_times_out_when_completion_never_arrives() -> None:
    # Rejected forever (and completion never observed).
    handle = FakeHandle(interrupts=[_no_active()] * 1000)
    fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    start = time.monotonic()
    with pytest.raises(CodexInterruptTimeout):
        await interrupt_turn(handle, completion=fut, timeout=0.2, retry_interval=0.01)
    assert time.monotonic() - start < 1
    assert handle.interrupt_calls > 1
    assert not fut.cancelled()  # the caller's future is left alone

    # Accepted, but turn/completed never follows.
    accepted = FakeHandle(interrupts=[None])
    with pytest.raises(CodexInterruptTimeout):
        await interrupt_turn(accepted, completion=TurnCompletion("turn-1"), timeout=0.1)


@pytest.mark.asyncio
async def test_interrupt_propagates_other_rpc_errors_and_owns_coroutines() -> None:
    handle = FakeHandle(interrupts=[InternalRpcError(-32603, "boom")])
    with pytest.raises(InternalRpcError):
        await interrupt_turn(handle, completion=TurnCompletion("turn-1"), timeout=1)

    cancelled = asyncio.Event()

    async def never() -> str:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "x"

    with pytest.raises(CodexInterruptTimeout):
        await interrupt_turn(
            FakeHandle(interrupts=[None]), completion=never(), timeout=0.05
        )
    await asyncio.wait_for(cancelled.wait(), 1)


@pytest.mark.asyncio
async def test_interrupt_reports_unknown_when_the_stream_died() -> None:
    fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    fut.set_exception(RuntimeError("pump crashed"))
    assert (
        await interrupt_turn(FakeHandle(), completion=fut, timeout=1) == STATUS_UNKNOWN
    )


# ---------------------------------------------------------------------------
# start_fresh_turn
# ---------------------------------------------------------------------------


class FakeThread:
    def __init__(self, outcomes) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    async def turn(self, input: Any, **kwargs: Any) -> Any:
        self.calls.append((input, kwargs))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return SimpleNamespace(id=outcome)


@pytest.mark.asyncio
async def test_start_fresh_turn_rejects_a_joined_turn_and_retries() -> None:
    thread = FakeThread(["old", "old", "new"])
    handle = await start_fresh_turn(
        thread, "hi", previous_turn_id="old", retry_interval=0.01, model="m"
    )
    assert handle.id == "new"
    assert thread.calls == [("hi", {"model": "m"})] * 3


@pytest.mark.asyncio
async def test_start_fresh_turn_without_previous_accepts_first_turn() -> None:
    thread = FakeThread(["t1"])
    assert (await start_fresh_turn(thread, "hi", previous_turn_id=None)).id == "t1"


@pytest.mark.asyncio
async def test_start_fresh_turn_gives_up_when_it_keeps_joining() -> None:
    thread = FakeThread(["old"] * 1000)
    with pytest.raises(CodexTurnJoinedError) as info:
        await start_fresh_turn(
            thread, "hi", previous_turn_id="old", start_timeout=0.1, retry_interval=0.01
        )
    assert info.value.turn_id == "old"


@pytest.mark.asyncio
async def test_start_fresh_turn_waits_out_a_compaction_but_not_other_errors() -> None:
    thread = FakeThread([_not_steerable(), _not_steerable(), "new"])
    handle = await start_fresh_turn(
        thread, "hi", previous_turn_id="old", retry_interval=0.01
    )
    assert handle.id == "new"

    with pytest.raises(InternalRpcError):
        await start_fresh_turn(
            FakeThread([_not_steerable()] * 1000),
            "hi",
            previous_turn_id=None,
            start_timeout=0.05,
            retry_interval=0.01,
        )
    with pytest.raises(InvalidRequestError):
        await start_fresh_turn(
            FakeThread([InvalidRequestError(-32600, "bad")]),
            "hi",
            previous_turn_id=None,
        )


# ---------------------------------------------------------------------------
# compact_and_wait
# ---------------------------------------------------------------------------


def _turn(turn_id: str, status: str, *item_types: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=turn_id,
        status=SimpleNamespace(value=status),
        items=[SimpleNamespace(root=SimpleNamespace(type=t)) for t in item_types],
    )


class FakeCompactThread:
    """Thread whose read() replays snapshots; compact() only records the call."""

    def __init__(self, snapshots) -> None:
        self._snapshots = list(snapshots)
        self.compacted = 0
        self.reads = 0

    async def compact(self) -> None:
        self.compacted += 1

    async def read(self, *, include_turns: bool = False) -> Any:
        assert include_turns
        self.reads += 1
        turns = (
            self._snapshots.pop(0) if len(self._snapshots) > 1 else self._snapshots[0]
        )
        return SimpleNamespace(thread=SimpleNamespace(turns=turns))


@pytest.mark.asyncio
async def test_compact_and_wait_returns_when_the_compaction_turn_finishes() -> None:
    old = _turn("t1", "completed", "userMessage", "agentMessage")
    thread = FakeCompactThread(
        [
            [old],  # before compact()
            [old],  # compaction turn not visible yet
            [old, _turn("c1", "inProgress")],
            [old, _turn("c1", "completed", "contextCompaction")],
        ]
    )
    assert await compact_and_wait(thread, timeout=2, poll_interval=0.01) == "completed"
    assert thread.compacted == 1
    assert thread.reads == 4


@pytest.mark.asyncio
async def test_compact_and_wait_ignores_old_compactions_and_reports_failure() -> None:
    earlier = _turn("c0", "completed", "contextCompaction")
    thread = FakeCompactThread(
        [[earlier], [earlier, _turn("c1", "failed", "contextCompaction")]]
    )
    assert await compact_and_wait(thread, timeout=1, poll_interval=0.01) == "failed"


@pytest.mark.asyncio
async def test_compact_and_wait_times_out() -> None:
    thread = FakeCompactThread([[_turn("t1", "completed", "agentMessage")]])
    start = time.monotonic()
    with pytest.raises(CodexCompactTimeout):
        await compact_and_wait(thread, timeout=0.1, poll_interval=0.02)
    assert time.monotonic() - start < 1
    assert thread.compacted == 1


@pytest.mark.asyncio
async def test_compact_and_wait_fails_fast_on_ephemeral_thread() -> None:
    class Ephemeral(FakeCompactThread):
        async def read(self, *, include_turns: bool = False) -> Any:
            raise InvalidRequestError(
                -32600, "ephemeral threads do not support includeTurns"
            )

    thread = Ephemeral([[]])
    with pytest.raises(InvalidRequestError):
        await compact_and_wait(thread, timeout=1)
    assert thread.compacted == 0  # nothing was started


# ---------------------------------------------------------------------------
# run_with_turn_timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_timeout_not_hit_returns_the_work_result() -> None:
    async def work() -> str:
        await asyncio.sleep(0.01)
        return "done"

    handle = FakeHandle()
    result = await run_with_turn_timeout(
        handle, work(), completion=TurnCompletion("turn-1"), timeout=1
    )
    assert result == "done"
    assert handle.interrupt_calls == 0

    async def boom() -> None:
        raise ValueError("pump failed")

    with pytest.raises(ValueError):
        await run_with_turn_timeout(
            handle, boom(), completion=TurnCompletion("turn-1"), timeout=None
        )


@pytest.mark.asyncio
async def test_turn_timeout_interrupts_drains_and_raises() -> None:
    completion = TurnCompletion("turn-1")
    drained: list[str] = []

    async def pump() -> None:
        await completion.future
        drained.append("flushed")  # the pump finishes once the turn ends

    pump_task = asyncio.create_task(pump())

    def accepted() -> None:
        asyncio.get_running_loop().call_later(
            0.02, completion.observe, _completed_note("turn-1", "interrupted")
        )

    handle = FakeHandle(interrupts=[_no_active(), accepted])
    with pytest.raises(CodexTurnTimeout) as info:
        await run_with_turn_timeout(
            handle, pump_task, completion=completion, timeout=0.05, grace=2
        )
    assert isinstance(info.value, TimeoutError)
    assert info.value.status == "interrupted" and info.value.stopped
    assert info.value.turn_id == "turn-1"
    assert drained == ["flushed"]
    assert pump_task.done() and not pump_task.cancelled()


@pytest.mark.asyncio
async def test_turn_timeout_cancels_a_wedged_pump_when_stop_unconfirmed() -> None:
    pump_task = asyncio.create_task(asyncio.sleep(3600))
    handle = FakeHandle(interrupts=[_no_active()] * 1000)
    start = time.monotonic()
    with pytest.raises(CodexTurnTimeout) as info:
        await run_with_turn_timeout(
            handle,
            pump_task,
            completion=TurnCompletion("turn-1"),
            timeout=0.05,
            grace=0.2,
        )
    assert info.value.status is None and not info.value.stopped
    assert time.monotonic() - start < 1.5
    await asyncio.sleep(0)
    assert pump_task.cancelled()


@pytest.mark.asyncio
async def test_turn_timeout_interrupt_rpc_failure_still_raises_timeout() -> None:
    pump_task = asyncio.create_task(asyncio.sleep(3600))
    handle = FakeHandle(interrupts=[InternalRpcError(-32603, "transport")])
    with pytest.raises(CodexTurnTimeout) as info:
        await run_with_turn_timeout(
            handle,
            pump_task,
            completion=TurnCompletion("turn-1"),
            timeout=0.01,
            grace=0.1,
        )
    assert info.value.status is None
    await asyncio.sleep(0)
    assert pump_task.cancelled()


@pytest.mark.asyncio
async def test_cancelling_the_watchdog_leaves_a_caller_owned_pump_running() -> None:
    pump_task = asyncio.create_task(asyncio.sleep(3600))
    watchdog = asyncio.create_task(
        run_with_turn_timeout(
            FakeHandle(), pump_task, completion=TurnCompletion("turn-1"), timeout=60
        )
    )
    await asyncio.sleep(0.01)
    watchdog.cancel()
    with pytest.raises(asyncio.CancelledError):
        await watchdog
    assert not pump_task.done()
    pump_task.cancel()


# ---------------------------------------------------------------------------
# Real Codex binary (opt in: CODEX_RUN_SMOKE=1)
# ---------------------------------------------------------------------------


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class _StubResponses:
    """Minimal Responses API on 127.0.0.1:0 standing in for the model.

    ``delay`` holds a response open after ``response.created`` (so the turn
    is genuinely mid model request); ``script(body)`` returns either reply
    text or a raw output item (e.g. a ``function_call``).
    """

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.delay = 0.0
        self.script = lambda body: "STUB-REPLY"
        app = FastAPI()

        @app.api_route("/{path:path}", methods=["GET", "POST"])
        async def anything(path: str, request: Request):  # noqa: ANN202
            raw = await request.body()
            try:
                body = json.loads(raw) if raw else None
            except ValueError:
                body = None
            record = {"method": request.method, "body": body, "t": time.monotonic()}
            self.requests.append(record)
            if request.method == "GET":
                return JSONResponse({"object": "list", "data": []})
            if not isinstance(body, dict) or not path.endswith("responses"):
                return JSONResponse({"error": "unhandled"}, status_code=404)
            delay, reply = self.delay, self.script(body)

            async def gen():  # noqa: ANN202
                rid = f"resp_{uuid.uuid4().hex[:12]}"
                yield _sse(
                    "response.created",
                    {"type": "response.created", "response": {"id": rid}},
                )
                if delay:
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        record["cancelled"] = True
                        raise
                item = (
                    reply
                    if isinstance(reply, dict)
                    else {
                        "type": "message",
                        "id": f"msg_{uuid.uuid4().hex[:12]}",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": reply, "annotations": []}
                        ],
                    }
                )
                yield _sse(
                    "response.output_item.done",
                    {
                        "type": "response.output_item.done",
                        "output_index": 0,
                        "item": item,
                    },
                )
                yield _sse(
                    "response.completed",
                    {
                        "type": "response.completed",
                        "response": {
                            "id": rid,
                            "object": "response",
                            "status": "completed",
                            "output": [item],
                            "usage": {
                                "input_tokens": 11,
                                "output_tokens": 7,
                                "total_tokens": 18,
                                "input_tokens_details": {"cached_tokens": 0},
                                "output_tokens_details": {"reasoning_tokens": 0},
                            },
                        },
                    },
                )

            return StreamingResponse(gen(), media_type="text/event-stream")

        self.app = app

    async def start(self) -> int:
        config = uvicorn.Config(
            self.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"
        )
        self.server = uvicorn.Server(config)
        self.server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        self.task = asyncio.create_task(self.server.serve())
        while not self.server.started:
            await asyncio.sleep(0.02)
        return self.server.servers[0].sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.server.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.task, 5)

    def posts(self) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["method"] == "POST"]

    async def wait_for_posts(self, count: int, timeout: float = 20) -> None:
        deadline = time.monotonic() + timeout
        while len(self.posts()) < count:
            assert time.monotonic() < deadline, "model request never arrived"
            await asyncio.sleep(0.02)


def _smoke_gate() -> None:
    if os.getenv("CODEX_RUN_SMOKE") != "1":
        pytest.skip(
            "set CODEX_RUN_SMOKE=1 to spawn the real Codex binary "
            "(no model is called; the backend is stubbed)"
        )
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)


@contextlib.asynccontextmanager
async def _real_thread():
    """(stub backend, persistent thread) on a real Codex app-server."""
    _smoke_gate()
    from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox

    stub = _StubResponses()
    port = await stub.start()
    with tempfile.TemporaryDirectory(prefix="veadk-codex-tc-") as root:
        home, cwd = Path(root, "home"), Path(root, "cwd")
        home.mkdir()
        cwd.mkdir()
        codex = AsyncCodex(
            config=CodexConfig(
                cwd=str(cwd),
                env={**os.environ, "CODEX_HOME": str(home), "STUB_KEY": "x"},
                # These tests do not use marketplace plugins. Disable discovery
                # at startup so background clones cannot race with home cleanup.
                config_overrides=("features.plugins=false",),
            )
        )
        try:
            thread = await codex.thread_start(
                model="stub-model",
                model_provider="stub",
                ephemeral=False,
                sandbox=Sandbox.read_only,
                approval_mode=ApprovalMode.deny_all,
                config={
                    "model_providers": {
                        "stub": {
                            "name": "stub",
                            "base_url": f"http://127.0.0.1:{port}/v1",
                            "env_key": "STUB_KEY",
                            "wire_api": "responses",
                        }
                    }
                },
            )
            yield stub, thread
        finally:
            await codex.close()
            await stub.stop()


def _pump(handle: Any) -> tuple[TurnCompletion, asyncio.Task[list[Any]]]:
    """The runtime's stream consumer, reduced to feeding a TurnCompletion."""
    completion = TurnCompletion(handle.id)

    async def consume() -> list[Any]:
        notes: list[Any] = []
        try:
            async for note in handle.stream():
                notes.append(note)
                completion.observe(note)
        finally:
            completion.close()
        return notes

    return completion, asyncio.create_task(consume())


class _AttemptLog:
    """Delegates to a real handle, recording each interrupt() outcome."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle
        self.id = handle.id
        self.outcomes: list[str] = []

    async def interrupt(self) -> Any:
        try:
            result = await self._handle.interrupt()
        except Exception as exc:
            self.outcomes.append(f"{type(exc).__name__}:{getattr(exc, 'code', '')}")
            raise
        self.outcomes.append("accepted")
        return result


def _mentions(body: Any, text: str) -> bool:
    return text in json.dumps(body)


@pytest.mark.codex_smoke
@pytest.mark.asyncio
async def test_real_interrupt_immediately_after_turn_start_still_stops_it() -> None:
    async with _real_thread() as (stub, thread):
        stub.delay = 30
        handle = await thread.turn("first")
        completion, pump = _pump(handle)
        attempts = _AttemptLog(handle)
        start = time.monotonic()
        status = await interrupt_turn(attempts, completion=completion, timeout=15)
        assert status == "interrupted"
        assert time.monotonic() - start < 10  # did not run to completion
        await asyncio.wait_for(pump, 5)
        # The bare interrupt() is rejected this early (5/5 in the spike); the
        # retry is what made the stop land. Accepted first time is not a bug,
        # just a slower machine, so it is reported rather than asserted.
        print(f"interrupt attempts: {attempts.outcomes}")
        assert attempts.outcomes[-1] == "accepted"


@pytest.mark.codex_smoke
@pytest.mark.asyncio
async def test_real_interrupt_then_fresh_turn_never_loses_input() -> None:
    async with _real_thread() as (stub, thread):
        previous: str | None = None
        for i in range(5):
            stub.delay = 30
            before = len(stub.posts())
            first = await start_fresh_turn(
                thread, f"first-{i}", previous_turn_id=previous
            )
            completion, pump = _pump(first)
            if i % 2:  # half the time interrupt mid model request
                await stub.wait_for_posts(before + 1)
            assert await interrupt_turn(first, completion=completion, timeout=15) in (
                "interrupted",
            )
            await asyncio.wait_for(pump, 5)
            stub.delay = 0
            second = await start_fresh_turn(
                thread, f"second-{i}", previous_turn_id=first.id
            )
            assert second.id != first.id
            result = await asyncio.wait_for(second.run(), 30)
            assert str(getattr(result.status, "value", result.status)) == "completed"
            assert result.final_response == "STUB-REPLY"
            assert _mentions(stub.posts()[-1]["body"], f"second-{i}")
            previous = second.id


@pytest.mark.codex_smoke
@pytest.mark.asyncio
async def test_real_interrupt_during_running_exec_command_stops_quickly() -> None:
    async with _real_thread() as (stub, thread):

        def script(body: dict[str, Any]) -> Any:
            items = body.get("input") or []
            if any(i.get("type") == "function_call_output" for i in items):
                return "done"
            return {
                "type": "function_call",
                "id": f"fc_{uuid.uuid4().hex[:8]}",
                "call_id": f"call_{uuid.uuid4().hex[:8]}",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": "sleep 20", "yield_time_ms": 30000}),
                "status": "completed",
            }

        stub.script = script
        handle = await thread.turn("run the sleep")
        completion = TurnCompletion(handle.id)
        started = asyncio.Event()

        async def consume() -> None:
            try:
                async for note in handle.stream():
                    item = getattr(getattr(note, "payload", None), "item", None)
                    root = getattr(item, "root", item)
                    if (
                        note.method == "item/started"
                        and getattr(root, "type", None) == "commandExecution"
                    ):
                        started.set()
                    completion.observe(note)
            finally:
                completion.close()

        pump = asyncio.create_task(consume())
        await asyncio.wait_for(started.wait(), 20)
        await asyncio.sleep(0.5)  # the command is running
        start = time.monotonic()
        status = await interrupt_turn(handle, completion=completion, timeout=10)
        assert status == "interrupted"
        assert time.monotonic() - start < 2
        await asyncio.wait_for(pump, 5)


@pytest.mark.codex_smoke
@pytest.mark.asyncio
async def test_real_steer_reaches_the_next_model_request_of_the_same_turn() -> None:
    async with _real_thread() as (stub, thread):
        turns = ActiveTurns()
        stub.delay = 2
        handle = await thread.turn("first")
        completion, pump = _pump(handle)
        with turns.register(KEY, handle, completion=completion):
            await stub.wait_for_posts(1)
            stub.delay = 0
            assert await turns.steer(KEY, "STEERED-EXTRA-INPUT") is True
            notes = await asyncio.wait_for(pump, 30)
        assert completion.status == "completed"
        steered = [
            p for p in stub.posts() if _mentions(p["body"], "STEERED-EXTRA-INPUT")
        ]
        assert steered, "steered input never reached the model"
        # Not the request that was in flight when steering: the next one.
        assert stub.posts().index(steered[0]) >= 1
        # One turn: every turn/completed seen belongs to the original turn id.
        ids = {n.payload.turn.id for n in notes if n.method == "turn/completed"}
        assert ids == {handle.id}
        assert await turns.steer(KEY, "after") is False


@pytest.mark.codex_smoke
@pytest.mark.asyncio
async def test_real_compact_and_wait_then_new_turn_succeeds() -> None:
    async with _real_thread() as (stub, thread):
        await asyncio.wait_for(thread.run("t1 hello"), 30)
        stub.delay = 1  # keep the compaction request open for a while
        status = await compact_and_wait(thread, timeout=20, poll_interval=0.1)
        assert status == "completed"
        stub.delay = 0
        handle = await start_fresh_turn(
            thread, "t2 after compact", previous_turn_id=None
        )
        result = await asyncio.wait_for(handle.run(), 30)
        assert result.final_response == "STUB-REPLY"
        read = await thread.read(include_turns=True)
        kinds = [
            [getattr(getattr(i, "root", i), "type", None) for i in t.items]
            for t in read.thread.turns
        ]
        assert ["contextCompaction"] in kinds
