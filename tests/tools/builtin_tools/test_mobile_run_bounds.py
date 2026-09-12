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

"""Regression tests for the bounded waits in the mobile-use tool.

Every wait exercised here used to be unbounded, so each test is written so that
the old behaviour *fails* (loudly, and quickly) instead of hanging forever:

* ``PodPool.acquire_pod`` is driven from a worker thread with a hard
  ``result(timeout=...)`` bound, and the queue is unblocked before the test
  gives up so a stuck worker can never wedge the suite.
* the async tests drive the tool with a fake clock plus a fake ``asyncio.sleep``
  that still yields to the real event loop, so an outer ``asyncio.wait_for``
  can cancel a runaway polling loop.

No network is involved: every ``ve_request`` caller in the module is patched.
"""

import asyncio
import concurrent.futures
import time
import types

import pytest

from veadk.tools.builtin_tools import mobile_run
from veadk.tools.builtin_tools.mobile_run import (
    GetAgentResultResponse,
    GetAgentResultResult,
    ListAgentRunCurrentResponse,
    ListAgentRunCurrentResponseResult,
    PodPool,
    ResponseMetadata,
    RunAgentTaskResponse,
    RunAgentTaskResult,
)

# Real wall-clock ceiling for anything that could regress into an endless wait.
# Generous enough to never flake, short enough that CI fails fast.
_HARD_BOUND_SECONDS = 15

_UNBLOCK_SENTINEL = "unblock-sentinel"


def _acquire_pod_bounded(pool: PodPool, hint: str):
    """Call ``pool.acquire_pod()`` off-thread under a hard real-time bound.

    If ``acquire_pod`` blocks (the pre-fix ``Queue.get(block=True)`` behaviour)
    the test fails instead of hanging, and a sentinel is pushed into the queue
    first so the stranded worker thread can finish and be joined.
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(pool.acquire_pod)
        try:
            return future.result(timeout=_HARD_BOUND_SECONDS)
        except concurrent.futures.TimeoutError:
            pool.available_pods.put(_UNBLOCK_SENTINEL)
            pytest.fail(
                f"acquire_pod() blocked for more than {_HARD_BOUND_SECONDS}s "
                f"({hint}); the bounded wait on the pod queue has regressed"
            )
    finally:
        executor.shutdown(wait=True)


def test_acquire_pod_returns_none_when_pool_is_empty():
    """An empty pool must give up instead of parking the caller forever."""
    pool = PodPool([])

    started = time.monotonic()
    pod = _acquire_pod_bounded(pool, hint="empty pool")
    elapsed = time.monotonic() - started

    assert pod is None
    # The wait must be governed by the module constant, not by luck.
    assert elapsed < mobile_run.POD_ACQUIRE_TIMEOUT_SECONDS + 5


def test_acquire_pod_round_trips_a_single_pod():
    """Exhausting the pool yields ``None``; releasing makes the pod available again."""
    pool = PodPool(["pod-1"])

    assert _acquire_pod_bounded(pool, hint="first acquire") == "pod-1"
    assert pool.get_pod_status("pod-1") == "pending"
    assert pool.get_available_count() == 0

    assert _acquire_pod_bounded(pool, hint="exhausted pool") is None

    pool.release_pod("pod-1")
    assert pool.get_pod_status("pod-1") == "available"

    assert _acquire_pod_bounded(pool, hint="after release") == "pod-1"


def test_acquire_pod_propagates_non_empty_queue_errors():
    """Only ``queue.Empty`` maps to ``None``.

    The handler used to be a blanket ``except Exception`` that swallowed real
    failures and reported them as "no pod available".
    """

    class _ExplodingQueue:
        def get(self, block=True, timeout=None):
            raise RuntimeError("queue backend exploded")

        def qsize(self):
            return 0

    pool = PodPool(["pod-1"])
    pool.available_pods = _ExplodingQueue()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="queue backend exploded"):
        pool.acquire_pod()


class _FakeClock:
    """Deterministic stand-in for the module-level ``time`` module.

    ``monotonic()`` and ``time()`` are tracked separately on purpose. Every
    deadline in the tool is armed on the monotonic clock, so a test can step the
    wall clock the way an NTP correction would and assert that no deadline
    moves. Keeping ``time()`` here (rather than dropping it once the module
    stopped calling it) is what makes a regression back to wall-clock arithmetic
    fail loudly instead of going unnoticed.
    """

    def __init__(self, start: float = 1_000.0) -> None:
        self._now = start
        self._wall_skew = 0.0

    def monotonic(self) -> float:
        return self._now

    def time(self) -> float:
        return self._now + self._wall_skew

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def step_wall_clock(self, seconds: float) -> None:
        """Jump ``time()`` only, leaving ``monotonic()`` untouched."""
        self._wall_skew += seconds


def _metadata(action: str) -> ResponseMetadata:
    return ResponseMetadata(
        RequestId="req-1",
        Action=action,
        Version="2023-08-01",
        Service="ipaas",
        Region="cn-north-1",
    )


def _install_fake_backend(
    monkeypatch,
    *,
    is_success,
    timeout_seconds: int,
    content: str = "still working",
    pods_available: bool = True,
    wall_clock_step_per_sleep: float = 0.0,
    max_sleeps: int = 100,
):
    """Build a fully offline ``mobile_use_tool`` whose result poll never finishes.

    ``_get_task_result`` always reports ``is_success``; time only moves when the
    (faked) ``asyncio.sleep`` inside a wait loop is awaited, so the tests run
    instantly while still exercising the real deadline arithmetic.

    ``pods_available=False`` starves ``acquire_pod`` so the pod-wait loop is the
    one under test, ``wall_clock_step_per_sleep`` skews ``time()`` on every
    retry without touching ``monotonic()``, and ``max_sleeps`` turns a loop that
    stopped honouring its deadline into a fast failure instead of a spin.
    """
    # The module reads these at call time via ``_require_env_vars`` /
    # ``_get_product_and_pod``; monkeypatch keeps a clean machine clean.
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test-sk")
    monkeypatch.setenv("TOOL_MOBILE_USE_TOOL_ID", "['product1-pod1']")
    monkeypatch.setattr(mobile_run, "tool_ids", ["product1-pod1"])
    monkeypatch.setattr(mobile_run, "product_id", None)
    monkeypatch.setattr(mobile_run, "pod_ids", None)

    calls: dict = {
        "run": 0,
        "result": 0,
        "step": 0,
        "cancel": 0,
        "cancelled": [],
        "sleeps": [],
    }
    clock = _FakeClock()

    if not pods_available:
        # Nothing to hand out, so the tool has to fall through to the pod-wait
        # deadline instead of starting a run.
        monkeypatch.setattr(mobile_run.PodPool, "acquire_pod", lambda self: None)

    def fake_run_agent_task(*_args, **_kwargs) -> RunAgentTaskResponse:
        calls["run"] += 1
        return RunAgentTaskResponse(
            ResponseMetadata=_metadata("RunAgentTaskOneStep"),
            Result=RunAgentTaskResult(
                RunId="run-1", RunName="test-run", ThreadId="thread-1"
            ),
        )

    def fake_get_task_result(_task_id: str) -> GetAgentResultResponse:
        calls["result"] += 1
        return GetAgentResultResponse(
            ResponseMetadata=_metadata("GetAgentResult"),
            Result=GetAgentResultResult(
                IsSuccess=is_success,
                Content=content,
                StructOutput="",
                ScreenShots=[],
            ),
        )

    def fake_get_current_step(_task_id: str) -> ListAgentRunCurrentResponse:
        calls["step"] += 1
        return ListAgentRunCurrentResponse(
            ResponseMetadata=_metadata("ListAgentRunCurrentStep"),
            Result=ListAgentRunCurrentResponseResult(
                RunId="run-1", ThreadId="thread-1", Results=[]
            ),
        )

    def fake_cancel_task(_task_id: str) -> None:
        calls["cancel"] += 1
        calls["cancelled"].append(_task_id)

    async def fake_sleep(delay):
        calls["sleeps"].append(delay)
        if len(calls["sleeps"]) > max_sleeps:
            # Fail fast rather than spin: a loop that ignores its deadline must
            # not burn the outer ``asyncio.wait_for`` bound to be noticed.
            raise AssertionError(
                f"faked asyncio.sleep called more than {max_sleeps} times; "
                "a wait loop is no longer honouring its deadline"
            )
        clock.advance(delay)
        clock.step_wall_clock(wall_clock_step_per_sleep)
        # A real yield, so an outer ``asyncio.wait_for`` can still cancel a
        # polling loop that refuses to terminate.
        await asyncio.sleep(0)

    monkeypatch.setattr(mobile_run, "_run_agent_task", fake_run_agent_task)
    monkeypatch.setattr(mobile_run, "_get_task_result", fake_get_task_result)
    monkeypatch.setattr(mobile_run, "_get_current_step", fake_get_current_step)
    monkeypatch.setattr(mobile_run, "_cancel_task", fake_cancel_task)
    monkeypatch.setattr(mobile_run, "time", clock)
    monkeypatch.setattr(
        mobile_run,
        "asyncio",
        types.SimpleNamespace(
            sleep=fake_sleep,
            gather=asyncio.gather,
            # The blocking ACEP helpers are awaited via `asyncio.to_thread`, so
            # the stand-in namespace must carry it or the tool fails before it
            # can ever reach the bounds these tests pin.
            to_thread=asyncio.to_thread,
        ),
    )

    tool = mobile_run.create_mobile_use_tool(
        system_prompt="you are a test agent",
        timeout_seconds=timeout_seconds,
        max_step=3,
        step_interval_seconds=1,
    )
    return tool, calls


async def _run_tool_bounded(tool, prompts):
    """Await the tool under a hard real-time bound so a spin cannot hang CI."""
    try:
        return await asyncio.wait_for(tool(prompts), timeout=_HARD_BOUND_SECONDS)
    except asyncio.TimeoutError:
        pytest.fail(
            f"mobile_use_tool did not return within {_HARD_BOUND_SECONDS}s; "
            "the result-polling loop no longer honours its deadline"
        )


@pytest.mark.asyncio
async def test_result_polling_gives_up_at_the_deadline(monkeypatch):
    """A task that never finishes must end at ``timeout_seconds``, not spin forever."""
    tool, calls = _install_fake_backend(monkeypatch, is_success=0, timeout_seconds=12)

    results = await _run_tool_bounded(tool, ["open the app"])

    assert len(results) == 1
    assert "timed out waiting for result after 12s" in results[0]
    # Three polls, each followed by the loop's 5s sleep, cross the 12s deadline.
    assert calls["result"] == 3
    assert calls["sleeps"] == [5, 5, 5]
    # The pod is still handed back on the timeout path.
    assert calls["cancel"] == 1


@pytest.mark.asyncio
async def test_unknown_terminal_status_ends_task_without_spinning(monkeypatch):
    """An unrecognised ``IsSuccess`` is terminal: stop at once, do not keep polling."""
    tool, calls = _install_fake_backend(
        monkeypatch, is_success=3, timeout_seconds=12, content="device offline"
    )

    results = await _run_tool_bounded(tool, ["open the app"])

    assert "unknown status 3" in results[0]
    assert "device offline" in results[0]
    # Terminal means terminal: one poll, no sleep, no fall-through to the deadline.
    assert calls["result"] == 1
    assert calls["sleeps"] == []
    assert "timed out" not in results[0]
    assert calls["cancel"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("in_progress_status", [0, None])
async def test_in_progress_status_keeps_polling_until_deadline(
    monkeypatch, in_progress_status
):
    """``IsSuccess`` of ``0``/``None`` means "still running", never "unknown status".

    The service reports ``1`` for success and ``2`` for failure; ``0`` is the
    in-progress marker, and a missing ``IsSuccess`` field is decoded as ``None``
    by ``_dict_to_dataclass``. Both are therefore excluded on purpose from the
    unknown-terminal-status branch: treating them as terminal would abort every
    task on its very first poll. This test pins that decision, so the task must
    end via the deadline, not via the unknown-status error.
    """
    tool, calls = _install_fake_backend(
        monkeypatch, is_success=in_progress_status, timeout_seconds=12
    )

    results = await _run_tool_bounded(tool, ["open the app"])

    assert "unknown status" not in results[0]
    assert "timed out waiting for result after 12s" in results[0]
    # It really kept polling instead of bailing out on the first response.
    assert calls["result"] > 1
    assert calls["step"] == calls["result"]


@pytest.mark.asyncio
@pytest.mark.parametrize("wall_clock_step", [600.0, -600.0])
async def test_pod_acquire_deadline_ignores_wall_clock_jumps(
    monkeypatch, wall_clock_step
):
    """The pod wait is timed on the monotonic clock, exactly like the result poll.

    Both phases spend the same ``timeout_seconds`` budget, so both have to be
    armed on the same clock. Wall-clock arithmetic would let an NTP step forward
    abort the wait after a single 1s retry, and an NTP step backwards stretch it
    past its budget indefinitely. Here ``monotonic()`` advances by the real 1s
    per retry while ``time()`` jumps ten minutes in either direction, so either
    regression changes the retry count -- and the faked-sleep budget aborts the
    run long before the outer hard bound, so a regression never hangs CI.
    """
    tool, calls = _install_fake_backend(
        monkeypatch,
        is_success=0,
        timeout_seconds=12,
        pods_available=False,
        wall_clock_step_per_sleep=wall_clock_step,
    )

    results = await _run_tool_bounded(tool, ["open the app"])

    assert "timed out acquiring pod after 12s" in results[0]
    # Twelve 1s retries: the budget is spent in monotonic seconds, nothing else.
    assert calls["sleeps"] == [1] * 12
    # The task never held a pod, so nothing was started and nothing cancelled.
    assert calls["run"] == 0
    assert calls["result"] == 0
    assert calls["cancel"] == 0


@pytest.mark.asyncio
async def test_run_id_is_recorded_and_read_back_through_pod_pool(monkeypatch):
    """``task_map`` is reached only through ``PodPool``'s locked accessors.

    ``acquire_pod`` runs on a worker thread (``asyncio.to_thread``), so the run
    id written from the event loop and the read in the ``finally`` are the two
    places that could skip ``pod_lock``. Spying on the accessors pins the
    routing, and the recorded ids show the cancel still targets the run this
    task actually started.
    """
    seen: dict = {"set": [], "get": []}
    real_set = PodPool.set_pod_task
    real_get = PodPool.get_pod_task

    def spy_set(self, pid, task_id):
        seen["set"].append((pid, task_id))
        return real_set(self, pid, task_id)

    def spy_get(self, pid):
        value = real_get(self, pid)
        seen["get"].append((pid, value))
        return value

    monkeypatch.setattr(PodPool, "set_pod_task", spy_set)
    monkeypatch.setattr(PodPool, "get_pod_task", spy_get)

    tool, calls = _install_fake_backend(
        monkeypatch, is_success=1, timeout_seconds=12, content="all done"
    )

    results = await _run_tool_bounded(tool, ["open the app"])

    assert "task success: all done" in results[0]
    assert ("pod1", "run-1") in seen["set"]
    assert seen["get"] == [("pod1", "run-1")]
    assert calls["cancelled"] == ["run-1"]


def test_task_map_stays_consistent_under_concurrent_acquire_release():
    """Concurrent workers never observe another worker's entry in ``task_map``.

    Each worker writes a run id only it can produce and reads it straight back
    while it still owns the pod, so a lost or interleaved entry surfaces as a
    mismatch. The whole fan-out is bounded once and the executor is torn down
    with ``wait=False``: an accessor that deadlocks against ``pod_lock`` (say,
    by being called while the lock is already held) fails the test instead of
    wedging the suite.
    """
    pods = [f"pod-{i}" for i in range(3)]
    pool = PodPool(pods)
    workers, rounds = 6, 5
    mismatches: list = []

    def worker(worker_id: int) -> int:
        completed = 0
        for round_id in range(rounds):
            # Each attempt is already bounded by POD_ACQUIRE_TIMEOUT_SECONDS, so
            # a couple of tries cannot hang and leave plenty of slack for a
            # loaded machine; a genuinely lost round just lowers `completed`.
            pid = pool.acquire_pod() or pool.acquire_pod()
            if pid is None:
                continue
            try:
                run_id = f"run-{worker_id}-{round_id}"
                pool.set_pod_task(pid, run_id)
                observed = pool.get_pod_task(pid)
                if observed != run_id:
                    mismatches.append((pid, run_id, observed))
                completed += 1
            finally:
                pool.release_pod(pid)
        return completed

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [executor.submit(worker, w) for w in range(workers)]
        _, not_done = concurrent.futures.wait(futures, timeout=_HARD_BOUND_SECONDS)
        if not_done:
            pytest.fail(
                f"concurrent acquire/release did not settle within "
                f"{_HARD_BOUND_SECONDS}s; a task_map accessor is blocking on "
                "PodPool.pod_lock"
            )
        completed = [future.result() for future in futures]
    finally:
        # Never wait on a possibly deadlocked worker during teardown.
        executor.shutdown(wait=False)

    assert mismatches == []
    assert sum(completed) == workers * rounds
    # Every pod came back and no task entry outlived its holder.
    assert pool.get_available_count() == len(pods)
    assert pool.task_map == {}
    for pid in pods:
        assert pool.get_pod_status(pid) == "available"
        assert pool.get_pod_task(pid) is None
