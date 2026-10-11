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

"""Rollout file I/O and the Codex thread stores.

Everything except the last test is offline file/sqlite work. The store
contract tests also run against a real MySQL / PostgreSQL when
``VEADK_TEST_MYSQL_URL`` / ``VEADK_TEST_POSTGRES_URL`` hold an async SQLAlchemy
URL (``mysql+aiomysql://...``, ``postgresql+asyncpg://...``); each test gets
its own table, dropped afterwards. The last test
(``codex_smoke``, opt in with ``CODEX_RUN_SMOKE=1``) runs the real Codex binary
against a stub Responses backend to prove that a rollout that went through a
``DatabaseThreadStore`` really resumes in a fresh ``CODEX_HOME``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import stat
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from veadk.runtime.codex import rollout_io
from veadk.runtime.codex.rollout_io import (
    Rollout,
    export_rollout,
    find_rollout,
    import_rollout,
)
from veadk.runtime.codex.thread_store import (
    DatabaseThreadStore,
    InMemoryThreadStore,
    LocalDirThreadStore,
    ThreadKey,
    ThreadRecord,
    MAX_ROLLOUT_BYTES,
    SCHEMA_VERSION,
    RolloutTooLarge,
    ThreadStoreConflict,
    ThreadStoreCorrupt,
    ThreadStoreError,
    ThreadStoreIncompatible,
    ThreadStoreSchemaError,
    instruction_hash,
    rollout_size_limit,
    select_thread_store,
)

pytest.importorskip("greenlet", reason="SQLAlchemy's async engine needs greenlet")
pytest.importorskip("aiosqlite")

TID = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
KEY = ThreadKey(app_name="app", user_id="u1", session_id="s1", agent_name="agent")


def _relpath(tid: str = TID) -> str:
    return f"sessions/2026/09/30/rollout-2026-09-30T10-00-00-{tid}.jsonl"


def _rollout(data: bytes = b'{"type":"session_meta"}\n', tid: str = TID) -> Rollout:
    return Rollout(thread_id=tid, relpath=_relpath(tid), data=data)


def _write(home: Path, relpath: str, data: bytes) -> Path:
    path = home / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------------------
# rollout_io
# ---------------------------------------------------------------------------


def test_find_export_import_round_trip(tmp_path: Path) -> None:
    home_a, home_b = tmp_path / "a", tmp_path / "b"
    data = b'{"a":1}\n{"b":2}\n'
    src = _write(home_a, _relpath(), data)
    # Another thread's rollout must not be picked up.
    _write(home_a, _relpath(str(uuid.uuid4())), b"other\n")

    assert find_rollout(str(home_a), TID) == str(src.resolve())
    rollout = export_rollout(str(home_a), TID)
    assert rollout == Rollout(thread_id=TID, relpath=_relpath(), data=data)
    assert "data" not in repr(rollout) and '"a"' not in repr(rollout)

    dest = import_rollout(str(home_b), rollout)
    assert Path(dest) == (home_b / _relpath()).resolve()
    assert Path(dest).read_bytes() == data
    assert export_rollout(str(home_b), TID) == rollout


def test_find_rollout_missing_and_ignores_partial_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    assert find_rollout(str(home), TID) is None
    day = home / "sessions/2026/09/30"
    day.mkdir(parents=True)
    (day / f".veadk-import-rollout-x-{TID}.jsonl").write_bytes(b"tmp")
    (day / f"rollout-x-{TID}.jsonl.tmp").write_bytes(b"tmp")
    (day / f".rollout-x-{TID}.jsonl").write_bytes(b"hidden")
    assert find_rollout(str(home), TID) is None
    assert export_rollout(str(home), TID) is None
    real = _write(home, _relpath(), b"ok\n")
    assert find_rollout(str(home), TID) == str(real.resolve())


def test_find_rollout_ambiguous_returns_none(tmp_path: Path) -> None:
    _write(tmp_path, _relpath(), b"1")
    _write(
        tmp_path, f"sessions/2026/10/01/rollout-2026-10-01T00-00-00-{TID}.jsonl", b"2"
    )
    assert find_rollout(str(tmp_path), TID) is None


def test_find_rollout_rejects_glob_thread_id(tmp_path: Path) -> None:
    _write(tmp_path, _relpath(), b"1")
    with pytest.raises(ValueError):
        find_rollout(str(tmp_path), "*")


@pytest.mark.parametrize(
    "relpath",
    [
        f"/etc/rollout-x-{TID}.jsonl",
        f"sessions/../../rollout-x-{TID}.jsonl",
        f"sessions/2026/../../../rollout-x-{TID}.jsonl",
        f"sessions/./rollout-x-{TID}.jsonl",
        f"sessions//rollout-x-{TID}.jsonl",
        f"sessions\\..\\rollout-x-{TID}.jsonl",
        "config.toml",
        f"rollout-x-{TID}.jsonl",
        "sessions/2026/09/30/config.toml",
        # Another thread's rollout. A fixed id, not uuid4(): parametrize ids
        # must be identical in every `pytest -n` worker.
        "sessions/2026/09/30/rollout-x-6f1c2d3e-4a5b-4c6d-8e9f-0a1b2c3d4e5f.jsonl",
        "",
    ],
)
def test_import_rejects_escaping_or_foreign_relpath(
    tmp_path: Path, relpath: str
) -> None:
    home = tmp_path / "home"
    with pytest.raises(ValueError):
        import_rollout(str(home), Rollout(thread_id=TID, relpath=relpath, data=b"x"))
    assert not (tmp_path / f"rollout-x-{TID}.jsonl").exists()
    assert not home.exists() or not any(home.rglob("*.jsonl"))


def test_import_rejects_symlinked_dir_escape(tmp_path: Path) -> None:
    home, outside = tmp_path / "home", tmp_path / "outside"
    (home / "sessions").mkdir(parents=True)
    outside.mkdir()
    (home / "sessions" / "2026").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        import_rollout(str(home), _rollout())
    assert not any(outside.rglob("*.jsonl"))


def test_import_is_atomic_and_private(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    old = b"old-complete-rollout\n"
    target = _write(home, _relpath(), old)

    # A crash mid-write (here: at the rename) must leave the old file intact
    # and no temp file behind.
    def boom(src, dst):
        raise OSError("simulated crash")

    monkeypatch.setattr(rollout_io.os, "replace", boom)
    with pytest.raises(OSError):
        import_rollout(str(home), _rollout(b"new\n"))
    assert target.read_bytes() == old
    assert sorted(p.name for p in target.parent.iterdir()) == [target.name]
    monkeypatch.undo()

    # The rename is the only way the final path is touched.
    seen: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append((str(src), str(dst)))
        assert Path(src).read_bytes() == b"new\n"
        assert Path(dst).read_bytes() == old
        real_replace(src, dst)

    monkeypatch.setattr(rollout_io.os, "replace", spy)
    path = import_rollout(str(home), _rollout(b"new\n"))
    assert len(seen) == 1 and seen[0][1] == path
    assert Path(seen[0][0]).parent == Path(path).parent
    assert Path(path).read_bytes() == b"new\n"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert sorted(p.name for p in Path(path).parent.iterdir()) == [Path(path).name]


# ---------------------------------------------------------------------------
# Store contract
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def _make_store(kind: str, tmp_path: Path):
    if kind == "memory":
        yield InMemoryThreadStore()
    elif kind == "localdir":
        yield LocalDirThreadStore(tmp_path / "threads")
    elif kind == "database":
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
        try:
            yield DatabaseThreadStore(engine)
        finally:
            await engine.dispose()
    else:
        from sqlalchemy.ext.asyncio import create_async_engine

        url = os.getenv(_SERVER_DB_ENVS[kind])
        if not url:
            pytest.skip(f"set {_SERVER_DB_ENVS[kind]} to run against {kind}")
        engine = create_async_engine(url)
        store = DatabaseThreadStore(
            engine, table_name=f"veadk_codex_threads_t{uuid.uuid4().hex[:12]}"
        )
        try:
            yield store
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(store._metadata.drop_all, checkfirst=True)
            await engine.dispose()


_SERVER_DB_ENVS = {
    "mysql": "VEADK_TEST_MYSQL_URL",
    "postgresql": "VEADK_TEST_POSTGRES_URL",
}
DB_KINDS = ["database", *_SERVER_DB_ENVS]
STORE_KINDS = ["memory", "localdir", *DB_KINDS]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", STORE_KINDS)
async def test_store_create_load_update(kind: str, tmp_path: Path) -> None:
    ih = instruction_hash("be helpful")
    async with _make_store(kind, tmp_path) as store:
        assert await store.load(KEY) is None
        r1 = _rollout(b"turn1\n")
        assert await store.save(KEY, TID, r1, ih, expected_version=None) == 1
        assert await store.load(KEY) == ThreadRecord(
            thread_id=TID, rollout=r1, version=1, instruction_hash=ih
        )
        r2 = _rollout(b"turn1\nturn2\n")
        assert await store.save(KEY, TID, r2, ih, expected_version=1) == 2
        rec = await store.load(KEY)
        assert rec is not None and rec.version == 2 and rec.rollout == r2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", STORE_KINDS)
async def test_store_version_conflicts(kind: str, tmp_path: Path) -> None:
    async with _make_store(kind, tmp_path) as store:
        with pytest.raises(ThreadStoreConflict):
            await store.save(KEY, TID, _rollout(), "h", expected_version=1)
        assert await store.load(KEY) is None
        await store.save(KEY, TID, _rollout(b"v1"), "h", expected_version=None)
        with pytest.raises(ThreadStoreConflict):
            await store.save(KEY, TID, _rollout(b"x"), "h", expected_version=None)
        for stale in (0, 2, 7):
            with pytest.raises(ThreadStoreConflict):
                await store.save(KEY, TID, _rollout(b"x"), "h", expected_version=stale)
        rec = await store.load(KEY)
        assert rec is not None and rec.version == 1 and rec.rollout.data == b"v1"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", STORE_KINDS)
async def test_store_concurrent_saves_exactly_one_wins(
    kind: str, tmp_path: Path
) -> None:
    async with _make_store(kind, tmp_path) as store:
        n = 8
        creates = await asyncio.gather(
            *(
                store.save(
                    KEY, TID, _rollout(f"c{i}".encode()), "h", expected_version=None
                )
                for i in range(n)
            ),
            return_exceptions=True,
        )
        assert creates.count(1) == 1
        assert sum(isinstance(r, ThreadStoreConflict) for r in creates) == n - 1

        updates = await asyncio.gather(
            *(
                store.save(
                    KEY, TID, _rollout(f"u{i}".encode()), "h", expected_version=1
                )
                for i in range(n)
            ),
            return_exceptions=True,
        )
        assert updates.count(2) == 1
        assert sum(isinstance(r, ThreadStoreConflict) for r in updates) == n - 1
        winner = updates.index(2)
        rec = await store.load(KEY)
        assert rec is not None and rec.version == 2
        assert rec.rollout.data == f"u{winner}".encode()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", STORE_KINDS)
async def test_store_delete(kind: str, tmp_path: Path) -> None:
    async with _make_store(kind, tmp_path) as store:
        await store.delete(KEY)  # no-op when absent
        await store.save(KEY, TID, _rollout(), "h", expected_version=None)
        await store.delete(KEY)
        assert await store.load(KEY) is None
        # Deleted: an update of the old version conflicts, a create succeeds.
        with pytest.raises(ThreadStoreConflict):
            await store.save(KEY, TID, _rollout(), "h", expected_version=1)
        assert await store.save(KEY, TID, _rollout(), "h", expected_version=None) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", STORE_KINDS)
async def test_store_large_blob(kind: str, tmp_path: Path) -> None:
    # ~6 MiB, half incompressible, so the stored blob is still several MB.
    data = os.urandom(3 * 1024 * 1024) + b'{"type":"response_item"}\n' * 130_000
    rollout = _rollout(data)
    async with _make_store(kind, tmp_path) as store:
        await store.save(KEY, TID, rollout, "h", expected_version=None)
        rec = await store.load(KEY)
        assert rec is not None and rec.rollout.data == data


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", STORE_KINDS)
async def test_store_key_isolation(kind: str, tmp_path: Path) -> None:
    keys = [
        KEY,
        ThreadKey("app2", "u1", "s1", "agent"),
        ThreadKey("app", "u2", "s1", "agent"),
        ThreadKey("app", "u1", "s2", "agent"),
        ThreadKey("app", "u1", "s1", "agent2"),
    ]
    async with _make_store(kind, tmp_path) as store:
        for i, key in enumerate(keys):
            tid = str(uuid.UUID(int=i + 1))
            await store.save(
                key, tid, _rollout(f"{i}".encode(), tid), f"h{i}", expected_version=None
            )
        for i, key in enumerate(keys):
            rec = await store.load(key)
            assert rec is not None
            assert rec.thread_id == str(uuid.UUID(int=i + 1))
            assert rec.rollout.data == f"{i}".encode()
            assert rec.instruction_hash == f"h{i}"
        await store.delete(keys[0])
        assert await store.load(keys[0]) is None
        assert all([await store.load(k) for k in keys[1:]])


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", STORE_KINDS)
async def test_store_rejects_mismatched_rollout(kind: str, tmp_path: Path) -> None:
    async with _make_store(kind, tmp_path) as store:
        other = str(uuid.uuid4())
        with pytest.raises(ValueError):
            await store.save(KEY, other, _rollout(), "h", expected_version=None)
        with pytest.raises(ValueError):
            await store.save(
                KEY,
                TID,
                Rollout(thread_id=TID, relpath="../x.jsonl", data=b""),
                "h",
                expected_version=None,
            )
        assert await store.load(KEY) is None


async def _tamper(store: Any, kind: str, how: str) -> None:
    """Damage the stored record for ``KEY`` the way bad storage would.

    ``how="blob"`` replaces the compressed rollout with bytes that are not
    gzip; ``how="sha"`` keeps a decodable rollout but records a checksum that
    does not match it (a torn write, or the payload swapped under the header).
    """
    bad_sha = "0" * 64
    if kind == "localdir":
        path, _ = store._paths(KEY)
        header_line, _, payload = path.read_bytes().partition(b"\n")
        header = json.loads(header_line)
        if how == "blob":
            payload = b"definitely not gzip"
        else:
            header["rollout_sha256"] = bad_sha
        path.write_bytes(json.dumps(header).encode("utf-8") + b"\n" + payload)
        return
    from sqlalchemy import update

    table = store._table
    if how == "blob":
        values: dict[str, Any] = {"rollout_gz": b"definitely not gzip"}
    else:
        values = {"rollout_sha256": bad_sha}
    async with store.engine.begin() as conn:
        await conn.execute(update(table).where(store._where(KEY)).values(**values))


# `memory` is deliberately absent: `InMemoryThreadStore` keeps its compressed
# blob in process memory, never on storage that can be damaged underneath it.
@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["blob", "sha"])
@pytest.mark.parametrize("kind", ["localdir", *DB_KINDS])
async def test_store_load_rejects_corrupt_rollout(
    kind: str, how: str, tmp_path: Path
) -> None:
    """A damaged rollout must fail ``load`` loudly, not come back as data.

    Handing Codex a rollout that does not decode (or is not the one that was
    written) would resume a thread from garbage, or from another turn's
    history. ``ThreadStoreCorrupt`` is also the only signal the runtime has to
    discard the record: anything else leaves it in place and every later save
    of the session conflicts with it.
    """
    async with _make_store(kind, tmp_path) as store:
        await store.save(KEY, TID, _rollout(b"turn1\n"), "h", expected_version=None)
        await _tamper(store, kind, how)
        with pytest.raises(ThreadStoreCorrupt):
            await store.load(KEY)


async def _set_schema_version(store: Any, kind: str, version: int) -> None:
    if kind == "localdir":
        path, _ = store._paths(KEY)
        header_line, _, payload = path.read_bytes().partition(b"\n")
        header = json.loads(header_line)
        header["schema_version"] = version
        path.write_bytes(json.dumps(header).encode("utf-8") + b"\n" + payload)
        return
    from sqlalchemy import update

    async with store.engine.begin() as conn:
        await conn.execute(
            update(store._table).where(store._where(KEY)).values(schema_version=version)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["localdir", *DB_KINDS])
async def test_store_refuses_newer_schema_and_keeps_record(
    kind: str, tmp_path: Path
) -> None:
    """A record written by a newer VeADK is neither read nor overwritten.

    Mid rolling upgrade an old instance can meet a record in a format it does
    not know. Reading it could hand Codex a misparsed rollout; saving over it
    would destroy the thread the newer instances are still resuming.
    """
    async with _make_store(kind, tmp_path) as store:
        await store.save(KEY, TID, _rollout(b"new\n"), "h", expected_version=None)
        await _set_schema_version(store, kind, SCHEMA_VERSION + 1)
        with pytest.raises(ThreadStoreIncompatible) as info:
            await store.load(KEY)
        assert not isinstance(info.value, ThreadStoreCorrupt)
        # Neither a create nor an update replaces it.
        for expected in (None, 1):
            with pytest.raises(ThreadStoreError):
                await store.save(
                    KEY, TID, _rollout(b"old\n"), "h", expected_version=expected
                )
        await _set_schema_version(store, kind, SCHEMA_VERSION)
        rec = await store.load(KEY)
        assert rec is not None and rec.version == 1 and rec.rollout.data == b"new\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["localdir", *DB_KINDS])
async def test_store_writes_current_schema_version(kind: str, tmp_path: Path) -> None:
    async with _make_store(kind, tmp_path) as store:
        await store.save(KEY, TID, _rollout(), "h", expected_version=None)
        if kind == "localdir":
            path, _ = store._paths(KEY)
            header = json.loads(path.read_bytes().partition(b"\n")[0])
            assert header["schema_version"] == SCHEMA_VERSION
            return
        from sqlalchemy import select

        async with store.engine.connect() as conn:
            version = (
                await conn.execute(select(store._table.c.schema_version))
            ).scalar_one()
        assert version == SCHEMA_VERSION


@pytest.mark.asyncio
async def test_database_store_rejects_table_without_schema_column(
    tmp_path: Path,
) -> None:
    """A table left by a pre-release build fails loudly, not on every insert."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE veadk_codex_threads (app_name VARCHAR(128), "
                    "user_id VARCHAR(128), session_id VARCHAR(128), "
                    "agent_name VARCHAR(128), thread_id VARCHAR(128))"
                )
            )
        store = DatabaseThreadStore(engine)
        with pytest.raises(ThreadStoreSchemaError, match="schema_version"):
            await store.load(KEY)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_store_compresses_at_rest(tmp_path: Path) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    try:
        store = DatabaseThreadStore(engine)
        data = b'{"type":"response_item","payload":"same"}\n' * 20_000
        await store.save(KEY, TID, _rollout(data), "h", expected_version=None)
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT rollout_gz, rollout_size FROM veadk_codex_threads")
                )
            ).one()
        assert row.rollout_size == len(data)
        assert bytes(row.rollout_gz)[:2] == b"\x1f\x8b"
        assert len(row.rollout_gz) < len(data) // 20
        # A second store on the same database sees the existing table and row.
        again = await DatabaseThreadStore(engine).load(KEY)
        assert again is not None and again.rollout.data == data
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Size limits
# ---------------------------------------------------------------------------


def test_rollout_size_limit_env(monkeypatch) -> None:
    monkeypatch.delenv("VEADK_CODEX_MAX_ROLLOUT_BYTES", raising=False)
    assert rollout_size_limit() == MAX_ROLLOUT_BYTES == 32 * 1024 * 1024
    monkeypatch.setenv("VEADK_CODEX_MAX_ROLLOUT_BYTES", " 4096 ")
    assert rollout_size_limit() == 4096
    monkeypatch.setenv("VEADK_CODEX_MAX_ROLLOUT_BYTES", "")
    assert rollout_size_limit() == MAX_ROLLOUT_BYTES
    for bad in ("0", "-1", "abc", "1.5", "32MiB"):
        monkeypatch.setenv("VEADK_CODEX_MAX_ROLLOUT_BYTES", bad)
        with pytest.raises(ValueError, match="VEADK_CODEX_MAX_ROLLOUT_BYTES"):
            rollout_size_limit()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", STORE_KINDS)
async def test_store_rejects_too_large_rollout_and_keeps_previous(
    kind: str, tmp_path: Path, monkeypatch
) -> None:
    """A rollout over the cap is refused before any write.

    The runtime reacts by starting a new thread next turn, so the record it
    already has must survive untouched: same version, same data.
    """
    monkeypatch.setenv("VEADK_CODEX_MAX_ROLLOUT_BYTES", "64")
    async with _make_store(kind, tmp_path) as store:
        # One byte over is refused, for a create too; at the limit is fine.
        other = ThreadKey("app", "u1", "s-other", "agent")
        with pytest.raises(RolloutTooLarge) as info:
            await store.save(
                other, TID, _rollout(b"x" * 65), "h", expected_version=None
            )
        assert isinstance(info.value, ThreadStoreError)
        assert (info.value.size, info.value.limit) == (65, 64)
        assert "x" * 10 not in str(info.value)
        assert await store.load(other) is None

        at_limit = _rollout(b"a" * 64)
        await store.save(KEY, TID, at_limit, "h", expected_version=None)
        with pytest.raises(RolloutTooLarge):
            await store.save(
                KEY,
                TID,
                _rollout(b"a" * 64 + b"b"),
                "h2",
                expected_version=1,
                covered_invocation_id="inv-2",
            )
        rec = await store.load(KEY)
        assert rec == ThreadRecord(
            thread_id=TID, rollout=at_limit, version=1, instruction_hash="h"
        )
        # The store still accepts the next save on the unchanged version.
        assert await store.save(KEY, TID, _rollout(b"ok"), "h", expected_version=1) == 2


@pytest.mark.parametrize(
    ("env", "value"),
    [
        ("VEADK_CODEX_MEMORY_STORE_MAX_BYTES", "0"),
        ("VEADK_CODEX_MEMORY_STORE_MAX_RECORDS", "-3"),
        ("VEADK_CODEX_MEMORY_STORE_MAX_RECORDS", "ten"),
    ],
)
def test_memory_store_budget_env_validation(monkeypatch, env: str, value: str) -> None:
    monkeypatch.setenv(env, value)
    with pytest.raises(ValueError, match=env):
        InMemoryThreadStore()


def test_memory_store_budget_defaults_and_overrides(monkeypatch) -> None:
    monkeypatch.delenv("VEADK_CODEX_MEMORY_STORE_MAX_BYTES", raising=False)
    monkeypatch.delenv("VEADK_CODEX_MEMORY_STORE_MAX_RECORDS", raising=False)
    store = InMemoryThreadStore()
    assert (store.max_bytes, store.max_records) == (256 * 1024 * 1024, 10_000)
    monkeypatch.setenv("VEADK_CODEX_MEMORY_STORE_MAX_BYTES", "1000")
    monkeypatch.setenv("VEADK_CODEX_MEMORY_STORE_MAX_RECORDS", "7")
    store = InMemoryThreadStore()
    assert (store.max_bytes, store.max_records) == (1000, 7)
    store = InMemoryThreadStore(max_bytes=5, max_records=2)
    assert (store.max_bytes, store.max_records) == (5, 2)
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            InMemoryThreadStore(max_records=bad)
        with pytest.raises(ValueError):
            InMemoryThreadStore(max_bytes=bad)


def _key(i: int) -> ThreadKey:
    return ThreadKey("app", "u1", f"s{i}", "agent")


def _tid(i: int) -> str:
    return str(uuid.UUID(int=i + 1))


@pytest.mark.asyncio
async def test_memory_store_evicts_lru_by_record_count(caplog) -> None:
    store = InMemoryThreadStore(max_records=3)
    for i in range(3):
        await store.save(
            _key(i), _tid(i), _rollout(b"%d" % i, _tid(i)), "h", expected_version=None
        )
    # Touch s0 so s1 becomes the least recently used.
    assert await store.load(_key(0)) is not None
    with caplog.at_level("INFO"):
        await store.save(
            _key(3), _tid(3), _rollout(b"3", _tid(3)), "h", expected_version=None
        )
    assert len(store) == 3
    assert await store.load(_key(1)) is None
    for i in (0, 2, 3):
        rec = await store.load(_key(i))
        assert rec is not None and rec.rollout.data == b"%d" % i
    [msg] = [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith("codex_thread_store_evicted")
    ]
    assert "records=1 " in msg
    # Counts only: no key or rollout content in the log line.
    assert "s1" not in msg and _tid(1) not in msg and "app" not in msg

    # A save to an existing key also refreshes it; s2 is now the LRU.
    await store.save(
        _key(0), _tid(0), _rollout(b"0b", _tid(0)), "h", expected_version=1
    )
    await store.save(
        _key(3), _tid(3), _rollout(b"3b", _tid(3)), "h", expected_version=1
    )
    await store.save(
        _key(4), _tid(4), _rollout(b"4", _tid(4)), "h", expected_version=None
    )
    assert await store.load(_key(2)) is None
    assert {i for i in range(5) if await store.load(_key(i))} == {0, 3, 4}


@pytest.mark.asyncio
async def test_memory_store_evicts_lru_by_bytes() -> None:
    # Incompressible payloads so the compressed size is ~ the raw size.
    payloads = [os.urandom(1000) for _ in range(4)]
    store = InMemoryThreadStore(max_bytes=3500, max_records=100)
    for i in range(3):
        await store.save(
            _key(i), _tid(i), _rollout(payloads[i], _tid(i)), "h", expected_version=None
        )
    assert len(store) == 3 and 3000 < store.stored_bytes <= 3500
    assert await store.load(_key(0)) is not None  # s1 becomes LRU
    await store.save(
        _key(3), _tid(3), _rollout(payloads[3], _tid(3)), "h", expected_version=None
    )
    assert store.stored_bytes <= 3500
    assert await store.load(_key(1)) is None
    for i in (0, 2, 3):
        rec = await store.load(_key(i))
        assert rec is not None and rec.rollout.data == payloads[i]

    # One record larger than the whole budget pushes out everything else, but
    # the record just saved is kept.
    big = os.urandom(5000)
    await store.save(
        _key(9), _tid(9), _rollout(big, _tid(9)), "h", expected_version=None
    )
    assert len(store) == 1
    rec = await store.load(_key(9))
    assert rec is not None and rec.rollout.data == big

    # Deleting releases its bytes.
    await store.delete(_key(9))
    assert len(store) == 0 and store.stored_bytes == 0


@pytest.mark.asyncio
async def test_memory_store_keeps_rollouts_compressed() -> None:
    store = InMemoryThreadStore()
    data = b'{"type":"response_item","payload":"same"}\n' * 20_000
    rollout = _rollout(data)
    await store.save(
        KEY, TID, rollout, "h", expected_version=None, covered_invocation_id="inv-1"
    )
    assert store.stored_bytes < len(data) // 20
    [entry] = store._records.values()
    assert entry.rollout_gz[:2] == b"\x1f\x8b"
    assert b"response_item" not in entry.rollout_gz
    rec = await store.load(KEY)
    assert rec == ThreadRecord(
        thread_id=TID,
        rollout=rollout,
        version=1,
        instruction_hash="h",
        covered_invocation_id="inv-1",
    )
    # Replacing a record accounts for the old blob's bytes.
    await store.save(KEY, TID, _rollout(b"small"), "h", expected_version=1)
    assert 0 < store.stored_bytes < 100


def test_mysql_blob_is_longblob() -> None:
    from sqlalchemy.dialects import mysql, postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    from veadk.runtime.codex.thread_store import _build_table

    _, table = _build_table("veadk_codex_threads")
    assert "LONGBLOB" in str(CreateTable(table).compile(dialect=mysql.dialect()))
    assert "BYTEA" in str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "BLOB" in str(CreateTable(table).compile(dialect=sqlite.dialect()))


def test_instruction_hash() -> None:
    assert instruction_hash("a") == instruction_hash("a")
    assert instruction_hash("a") != instruction_hash("b")
    assert len(instruction_hash("")) == 64


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_select_local_backend_is_in_memory() -> None:
    from veadk.memory.short_term_memory import ShortTermMemory

    stm = ShortTermMemory(backend="local")
    store = select_thread_store(stm)
    assert isinstance(store, InMemoryThreadStore)
    assert select_thread_store(stm) is store
    assert select_thread_store(stm.session_service) is store
    assert select_thread_store(ShortTermMemory(backend="local")) is not store


@pytest.mark.asyncio
async def test_select_sqlite_backend_uses_session_db(tmp_path: Path) -> None:
    from sqlalchemy import inspect as sa_inspect

    from veadk.memory.short_term_memory import ShortTermMemory

    stm = ShortTermMemory(
        backend="sqlite", local_database_path=str(tmp_path / "stm.db")
    )
    store = select_thread_store(stm)
    assert isinstance(store, DatabaseThreadStore)
    assert store.engine is stm.session_service.db_engine
    assert select_thread_store(stm) is store

    await stm.create_session(app_name="app", user_id="u1", session_id="s1")
    await store.save(KEY, TID, _rollout(), "h", expected_version=None)
    async with store.engine.connect() as conn:
        tables = await conn.run_sync(lambda c: sa_inspect(c).get_table_names())
    assert "veadk_codex_threads" in tables and "sessions" in tables
    await store.engine.dispose()


@pytest.mark.asyncio
async def test_select_db_url_uses_session_db(tmp_path: Path) -> None:
    from veadk.memory.short_term_memory import ShortTermMemory

    stm = ShortTermMemory(db_url=f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    store = select_thread_store(stm)
    assert isinstance(store, DatabaseThreadStore)
    assert store.engine is stm.session_service.db_engine
    await store.engine.dispose()


# ---------------------------------------------------------------------------
# Real binary: rollout survives a DB round trip into a fresh CODEX_HOME
# ---------------------------------------------------------------------------


class _SSEStub:
    """Minimal streaming Responses backend (from the resume spike harness)."""

    def __init__(self) -> None:
        # Plain Starlette: this module uses `from __future__ import annotations`,
        # which would hide a locally imported `Request` annotation from FastAPI.
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse, StreamingResponse
        from starlette.routing import Route

        self.posts: list[dict[str, Any]] = []

        async def anything(request):
            if request.method == "GET":
                return JSONResponse({"object": "list", "data": []})
            body = json.loads(await request.body() or b"null")
            if not request.url.path.endswith("responses") or not isinstance(body, dict):
                return JSONResponse({"error": "unhandled"}, status_code=404)
            self.posts.append(body)
            return StreamingResponse(self._stream(), media_type="text/event-stream")

        app = Starlette(
            routes=[Route("/{path:path}", anything, methods=["GET", "POST"])]
        )
        self._app = app
        self._server = None
        self._task = None

    @staticmethod
    def _sse(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    async def _stream(self):
        rid = f"resp_{uuid.uuid4().hex[:12]}"
        item = {
            "type": "message",
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "role": "assistant",
            "status": "completed",
            "content": [
                {"type": "output_text", "text": "STUB-REPLY", "annotations": []}
            ],
        }
        yield self._sse(
            "response.created", {"type": "response.created", "response": {"id": rid}}
        )
        yield self._sse(
            "response.output_item.done",
            {"type": "response.output_item.done", "output_index": 0, "item": item},
        )
        yield self._sse(
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

    async def start(self) -> int:
        import uvicorn

        server = uvicorn.Server(
            uvicorn.Config(
                self._app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"
            )
        )
        server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        self._server = server
        self._task = asyncio.create_task(server.serve())
        deadline = time.monotonic() + 10
        while not server.started:
            if self._task.done() or time.monotonic() > deadline:
                raise RuntimeError("stub backend failed to start")
            await asyncio.sleep(0.02)
        return server.servers[0].sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._task, 5)


@pytest.mark.codex_smoke
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", DB_KINDS)
async def test_rollout_resumes_in_fresh_codex_home_via_db_store(
    kind: str, tmp_path: Path
) -> None:
    if os.getenv("CODEX_RUN_SMOKE") != "1":
        pytest.skip("set CODEX_RUN_SMOKE=1 to spawn the real Codex binary")
    from tests.runtime.codex.test_codex_runtime_smoke import _skip_reason

    reason = _skip_reason()
    if reason:
        pytest.skip(reason)

    from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox

    first_text = f"veadk-first-turn-{uuid.uuid4().hex}"
    second_text = f"veadk-second-turn-{uuid.uuid4().hex}"
    stub = _SSEStub()
    port = await stub.start()
    provider = {
        "model_providers": {
            "stub": {
                "name": "stub",
                "base_url": f"http://127.0.0.1:{port}/v1",
                "env_key": "STUB_KEY",
                "wire_api": "responses",
            }
        }
    }
    opts = dict(
        model="stub-model",
        model_provider="stub",
        config=provider,
        sandbox=Sandbox.read_only,
        approval_mode=ApprovalMode.deny_all,
    )
    home_a, home_b, cwd = tmp_path / "home_a", tmp_path / "home_b", tmp_path / "cwd"
    for d in (home_a, home_b, cwd):
        d.mkdir()

    def codex(home: Path) -> AsyncCodex:
        env = {**os.environ, "CODEX_HOME": str(home), "STUB_KEY": "x"}
        return AsyncCodex(config=CodexConfig(cwd=str(cwd), env=env))

    async with contextlib.AsyncExitStack() as stack:
        stack.push_async_callback(stub.stop)
        # Two store objects on one engine: the reader shares nothing with the
        # writer but the database, as on another instance.
        store = await stack.enter_async_context(_make_store(kind, tmp_path))
        reader = DatabaseThreadStore(store.engine, table_name=store._table.name)

        async def drive() -> None:
            async with codex(home_a) as c:
                thread = await c.thread_start(ephemeral=False, **opts)
                await thread.run(first_text)
                thread_id = thread.id
            rollout = export_rollout(str(home_a), thread_id)
            assert rollout is not None and first_text.encode() in rollout.data

            await store.save(
                KEY, thread_id, rollout, instruction_hash(""), expected_version=None
            )
            record = await reader.load(KEY)
            assert record is not None and record.rollout == rollout
            import_rollout(str(home_b), record.rollout)

            async with codex(home_b) as c:
                thread = await c.thread_resume(
                    record.thread_id, include_turns=False, **opts
                )
                n_before = len(stub.posts)
                await thread.run(second_text)
            turn_posts = [
                json.dumps(p)
                for p in stub.posts[n_before:]
                if second_text in json.dumps(p)
            ]
            assert turn_posts, "second turn never reached the model"
            assert turn_posts[0].count(first_text) == 1, turn_posts[0].count(first_text)

        await asyncio.wait_for(drive(), 90)
