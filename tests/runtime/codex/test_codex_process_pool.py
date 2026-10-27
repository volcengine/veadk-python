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

"""Unit tests for the warm Codex process pool (no Codex binary involved)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("openai_codex")

from veadk.runtime.codex import process_pool  # noqa: E402
from veadk.runtime.codex.process_pool import (  # noqa: E402
    CodexProcessLease,
    CodexProcessPool,
    WarmCodex,
    tree_digest,
)
from veadk.runtime.codex.turn_control import TurnCompletion  # noqa: E402


class _Proc:
    def __init__(self) -> None:
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


class _Codex:
    def __init__(self) -> None:
        self._client = SimpleNamespace(
            _sync=SimpleNamespace(_proc=_Proc(), _reader_thread=None)
        )
        self.closed = False

    async def __aenter__(self) -> "_Codex":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self.closed = True
        self._client._sync._proc.returncode = 0


def _entry(tmp_path, name: str, fingerprint: str = "fp") -> WarmCodex:
    home = tmp_path / name
    home.mkdir()
    return WarmCodex(
        codex=_Codex(),
        codex_home=str(home),
        fingerprint=fingerprint,
        bridge_token="",
        thread=object(),
        thread_id="t",
        version=1,
        covered_invocation_id="inv",
        turns=1,
    )


async def _settle(pool: CodexProcessPool) -> None:
    await asyncio.gather(*list(pool._closing), return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_identity_check_closes_removed_process(tmp_path, monkeypatch):
    from veadk.runtime.codex import runtime

    pool = CodexProcessPool()
    monkeypatch.setattr(runtime, "_PROCESS_POOL", pool)
    entry = _entry(tmp_path, "cancelled")
    started = asyncio.Event()

    class Store:
        async def current_identity(self, key):
            started.set()
            await asyncio.sleep(60)

    pool.put("key", entry)
    store = cast(Any, Store())
    key = cast(Any, object())
    ctx = cast(Any, SimpleNamespace())
    task = asyncio.create_task(runtime._take_warm_process("key", "fp", store, key, ctx))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await _settle(pool)
    assert entry.codex.closed
    assert not Path(entry.codex_home).exists()


@pytest.mark.asyncio
async def test_equal_version_different_thread_invalidates_warm_entry(
    tmp_path, monkeypatch
):
    from veadk.runtime.codex import runtime

    pool = CodexProcessPool()
    monkeypatch.setattr(runtime, "_PROCESS_POOL", pool)
    entry = _entry(tmp_path, "recreated")

    class Store:
        async def current_identity(self, key):
            return "a-different-thread", entry.version

    pool.put("key", entry)
    store = cast(Any, Store())
    key = cast(Any, object())
    ctx = cast(Any, SimpleNamespace(invocation_id="inv"))
    assert await runtime._take_warm_process("key", "fp", store, key, ctx) is None
    await _settle(pool)
    assert entry.codex.closed


@pytest.mark.asyncio
async def test_pool_release_revokes_process_credential(tmp_path):
    pool = CodexProcessPool()
    entry = _entry(tmp_path, "released")
    revoked = []
    entry.on_close = lambda: revoked.append("released")
    pool.put("key", entry)
    assert await pool.release(lambda key: key == "key") == 1
    assert revoked == ["released"]
    assert entry.codex.closed


@pytest.mark.asyncio
async def test_borrowed_lease_setup_failure_revokes_its_binding(tmp_path):
    entry = _entry(tmp_path, "borrowed")
    revoked = []
    entry.on_close = lambda: revoked.append("closed")
    lease = CodexProcessLease(lambda: None, entry, reusable=True)
    await lease.close()
    assert revoked == ["closed"]
    assert entry.codex.closed


def test_tree_digest_changes_when_a_directory_symlink_target_changes(tmp_path) -> None:
    source_a = tmp_path / "source-a"
    source_b = tmp_path / "source-b"
    source_a.mkdir()
    source_b.mkdir()
    (source_a / "marker.txt").write_text("same contents")
    (source_b / "marker.txt").write_text("same contents")
    homes = []
    for name, source in (("home-a", source_a), ("home-b", source_b)):
        home = tmp_path / name
        (home / "skills").mkdir(parents=True)
        os.symlink(source, home / "skills" / "example", target_is_directory=True)
        homes.append(home)

    assert tree_digest(str(homes[0])) != tree_digest(str(homes[1]))


def test_tree_digest_follows_skill_contents_and_terminates_on_cycles(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    marker = source / "marker.txt"
    marker.write_text("before")
    os.symlink(source, source / "cycle", target_is_directory=True)
    home = tmp_path / "home"
    (home / "skills").mkdir(parents=True)
    os.symlink(source, home / "skills" / "example", target_is_directory=True)

    before = tree_digest(str(home))
    marker.write_text("after")

    assert tree_digest(str(home)) != before


@pytest.mark.asyncio
async def test_discard_close_work_is_bounded(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(process_pool.POOL_SIZE_ENV, "2")
    blocker = asyncio.Event()

    async def blocked_close(entry):
        await blocker.wait()

    monkeypatch.setattr(process_pool, "_close_warm", blocked_close)
    pool = CodexProcessPool()
    entries = [_entry(tmp_path, f"entry-{i}") for i in range(10)]

    for entry in entries:
        pool.discard(entry)

    assert len(pool._closing) <= 2
    assert (
        sum(entry.codex._client._sync._proc.returncode == -9 for entry in entries) >= 8
    )
    blocker.set()
    await pool.close_all()


@pytest.mark.asyncio
async def test_warm_home_deletion_does_not_block_the_event_loop(
    monkeypatch, tmp_path
) -> None:
    started = threading.Event()
    release = threading.Event()
    real_rmtree = process_pool.shutil.rmtree

    def slow_rmtree(path, ignore_errors=False):
        started.set()
        assert release.wait(1)
        real_rmtree(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(process_pool.shutil, "rmtree", slow_rmtree)
    pool = CodexProcessPool()
    pool.discard(_entry(tmp_path, "slow-delete"))
    assert await asyncio.to_thread(started.wait, 1)

    heartbeat = asyncio.Event()
    asyncio.get_running_loop().call_soon(heartbeat.set)
    await asyncio.wait_for(heartbeat.wait(), 0.1)

    release.set()
    await pool.close_all()


@pytest.mark.asyncio
async def test_pool_evicts_least_recently_used_beyond_its_size(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(process_pool.POOL_SIZE_ENV, "2")
    pool = CodexProcessPool()
    a, b, c = (_entry(tmp_path, n) for n in "abc")
    for key, entry in (("a", a), ("b", b), ("c", c)):
        assert pool.put(key, entry)
    await _settle(pool)

    assert a.codex.closed and not (tmp_path / "a").exists()
    assert pool.take("b", "fp") is b and pool.take("c", "fp") is c
    await pool.close_all()


@pytest.mark.asyncio
async def test_pool_closes_idle_processes_after_the_ttl(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(process_pool.IDLE_TTL_ENV, "0.01")
    pool = CodexProcessPool()
    entry = _entry(tmp_path, "a")
    assert pool.put("a", entry)
    await asyncio.sleep(0.05)
    await _settle(pool)

    assert entry.codex.closed
    assert pool.take("a", "fp") is None


@pytest.mark.asyncio
async def test_pool_refuses_changed_settings_and_dead_processes(tmp_path) -> None:
    pool = CodexProcessPool()
    changed, dead = _entry(tmp_path, "a"), _entry(tmp_path, "b")
    assert pool.put("a", changed) and pool.put("b", dead)
    dead.codex._client._sync._proc.returncode = 1

    assert pool.take("a", "other-fp") is None
    assert pool.take("b", "fp") is None
    await _settle(pool)
    assert changed.codex.closed and dead.codex.closed


@pytest.mark.asyncio
async def test_pool_size_zero_and_turn_cap_refuse_to_park(
    monkeypatch, tmp_path
) -> None:
    pool = CodexProcessPool()
    worn = _entry(tmp_path, "a")
    worn.turns = process_pool.MAX_TURNS_PER_PROCESS
    assert not pool.put("a", worn)

    monkeypatch.setenv(process_pool.POOL_SIZE_ENV, "0")
    assert not pool.put("b", _entry(tmp_path, "b"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error", "kept"),
    [
        ("completed", None, True),
        ("interrupted", None, True),
        (None, None, False),  # the turn never reported turn/completed
        ("completed", RuntimeError("boom"), False),
    ],
)
async def test_lease_keeps_a_process_only_after_a_clean_turn(
    status, error, kept
) -> None:
    lease = CodexProcessLease(_Codex, None, reusable=True)
    completion = TurnCompletion("turn-1")
    if status is not None:
        completion.future.set_result(status)
    codex: Any = None
    with pytest.raises(RuntimeError) if error else contextlib.nullcontext():
        async with lease:
            codex = lease.codex
            lease.completion = completion
            if error:
                raise error

    assert lease.kept is kept
    assert codex.closed is (not kept)


@pytest.mark.asyncio
async def test_pool_sweeps_expired_processes_whose_timer_never_fired(
    monkeypatch, tmp_path
) -> None:
    """A stopped loop never runs the expiry timer; the next pool use reclaims."""
    monkeypatch.setenv(process_pool.IDLE_TTL_ENV, "60")
    pool = CodexProcessPool()
    stale, fresh = _entry(tmp_path, "a"), _entry(tmp_path, "b")
    assert pool.put("a", stale) and pool.put("b", fresh)
    assert stale.expiry is not None
    stale.expiry.cancel()  # as if its loop had stopped
    stale.idle_since -= 120

    assert pool.take("b", "fp") is fresh
    await _settle(pool)
    assert stale.codex.closed and not fresh.codex.closed
    assert pool.take("a", "fp") is None


@pytest.mark.asyncio
async def test_release_codex_session_closes_only_that_sessions_processes(
    monkeypatch, tmp_path
) -> None:
    from veadk.runtime.codex import runtime as runtime_module

    pool = CodexProcessPool()
    monkeypatch.setattr(runtime_module, "_PROCESS_POOL", pool)
    first, second, other = (_entry(tmp_path, name) for name in "abc")
    assert pool.put(("app", "user", "s1", "agent_a"), first)
    assert pool.put(("app", "user", "s1", "agent_b"), second)
    assert pool.put(("app", "user", "s2", "agent_a"), other)

    assert await runtime_module.release_codex_session("app", "user", "s1") == 2
    assert first.codex.closed and second.codex.closed and not other.codex.closed
    assert pool.take(("app", "user", "s2", "agent_a"), "fp") is other
