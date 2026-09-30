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

"""Durable storage binding a VeADK session to a persistent Codex thread.

With ``runtime="codex"`` each VeADK session maps to one Codex thread: the first
turn starts it (``ephemeral=False``), later turns resume it. In production
(AgentKit) consecutive turns land on different instances whose disks are
ephemeral, so the thread's rollout file (see :mod:`.rollout_io`) must live
somewhere shared. The store keeps, per ``(app, user, session, agent)``:

* the Codex ``thread_id`` and its rollout (gzip-compressed at rest),
* a ``version`` for optimistic concurrency - two instances racing on one
  session cannot silently overwrite each other's history,
* the hash of the developer instructions the thread was started with, so the
  runtime can tell when the agent's instruction changed and a new thread is
  needed.

Backends:

* :class:`InMemoryThreadStore` - process-local; pairs with the ``local``
  short-term memory backend and tests.
* :class:`LocalDirThreadStore` - files under a directory; for development.
* :class:`DatabaseThreadStore` - a table in the same database as the
  short-term memory's ``DatabaseSessionService`` (sqlite / mysql / postgresql).

:func:`select_thread_store` picks one from a ``ShortTermMemory`` or session
service. Rollout contents are never logged.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import gzip
import hashlib
import json
import os
import tempfile
import threading
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from veadk.runtime.codex.rollout_io import Rollout, validate_rollout
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = get_logger(__name__)

#: Default table name for :class:`DatabaseThreadStore`.
DEFAULT_TABLE_NAME = "veadk_codex_threads"
# Same key width ADK uses for app/user/session ids in its session tables.
_KEY_LENGTH = 128
# gzip level: rollouts are highly repetitive JSON; 6 is the zlib sweet spot.
_GZIP_LEVEL = 6


@dataclass(frozen=True)
class ThreadKey:
    """Identifies the Codex thread of one agent within one VeADK session."""

    app_name: str
    user_id: str
    session_id: str
    agent_name: str

    def _digest(self) -> str:
        raw = json.dumps(
            [self.app_name, self.user_id, self.session_id, self.agent_name],
            ensure_ascii=False,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ThreadRecord:
    """A stored thread binding.

    Attributes:
        thread_id: The Codex thread id.
        rollout: The thread's rollout file.
        version: Store version, starts at 1 and increases by 1 on every save.
        instruction_hash: :func:`instruction_hash` of the developer
            instructions the thread was started with.
    """

    thread_id: str
    rollout: Rollout
    version: int
    instruction_hash: str


class ThreadStoreError(Exception):
    """Base class for thread store failures."""


class ThreadStoreConflict(ThreadStoreError):
    """``save`` was called with an ``expected_version`` that is not current.

    Another writer saved (or deleted) the record first. The caller should
    reload and decide; it must not blindly retry with the new version, which
    would discard the other writer's turn.
    """


class ThreadStoreCorrupt(ThreadStoreError):
    """A stored rollout failed its integrity check on load."""


def instruction_hash(text: str) -> str:
    """Stable hash of developer instructions (``sha256`` hex of UTF-8)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _check_save_args(thread_id: str, rollout: Rollout) -> None:
    validate_rollout(rollout)
    if rollout.thread_id != thread_id:
        raise ValueError(
            f"rollout belongs to thread {rollout.thread_id!r}, not {thread_id!r}"
        )


def _check_key(key: ThreadKey) -> None:
    for name in ("app_name", "user_id", "session_id", "agent_name"):
        value = getattr(key, name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"ThreadKey.{name} must be a non-empty string")
        if len(value) > _KEY_LENGTH:
            raise ValueError(f"ThreadKey.{name} longer than {_KEY_LENGTH} chars")


def _compress(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=_GZIP_LEVEL, mtime=0)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CodexThreadStore(ABC):
    """Versioned key -> :class:`ThreadRecord` storage.

    ``save`` is a compare-and-set on ``version``:

    * ``expected_version=None`` creates the record; it fails with
      :class:`ThreadStoreConflict` if one already exists.
    * ``expected_version=n`` replaces the record only if its current version
      is ``n``; otherwise (including when it was deleted) it raises
      :class:`ThreadStoreConflict`.

    On success ``save`` returns the new version (1 for a create, ``n + 1``
    for an update). Exactly one of several concurrent saves with the same
    ``expected_version`` wins.
    """

    @abstractmethod
    async def load(self, key: ThreadKey) -> ThreadRecord | None:
        """Return the record for ``key``, or ``None`` if there is none."""

    @abstractmethod
    async def save(
        self,
        key: ThreadKey,
        thread_id: str,
        rollout: Rollout,
        instruction_hash: str,
        *,
        expected_version: int | None,
    ) -> int:
        """Create or compare-and-set the record for ``key``; see class doc."""

    @abstractmethod
    async def delete(self, key: ThreadKey) -> None:
        """Remove the record for ``key``; a no-op if it does not exist."""


# ---------------------------------------------------------------------------
# In-memory
# ---------------------------------------------------------------------------


class InMemoryThreadStore(CodexThreadStore):
    """Process-local store. Records vanish with the process."""

    def __init__(self) -> None:
        self._records: dict[ThreadKey, ThreadRecord] = {}
        # No awaits happen while it is held, so a thread lock also covers
        # callers on different event loops.
        self._lock = threading.Lock()

    async def load(self, key: ThreadKey) -> ThreadRecord | None:
        with self._lock:
            return self._records.get(key)

    async def save(
        self,
        key: ThreadKey,
        thread_id: str,
        rollout: Rollout,
        instruction_hash: str,
        *,
        expected_version: int | None,
    ) -> int:
        _check_key(key)
        _check_save_args(thread_id, rollout)
        with self._lock:
            current = self._records.get(key)
            current_version = current.version if current else None
            if current_version != expected_version:
                raise ThreadStoreConflict(
                    f"expected version {expected_version}, found {current_version}"
                )
            version = 1 if current is None else current.version + 1
            self._records[key] = ThreadRecord(
                thread_id=thread_id,
                rollout=rollout,
                version=version,
                instruction_hash=instruction_hash,
            )
            return version

    async def delete(self, key: ThreadKey) -> None:
        with self._lock:
            self._records.pop(key, None)


# ---------------------------------------------------------------------------
# Local directory
# ---------------------------------------------------------------------------


class LocalDirThreadStore(CodexThreadStore):
    """Stores each record as one file under ``root``; for development.

    The file name is a hash of the key (user-controlled ids never become
    paths). Each file is a JSON header line followed by the gzip payload, and
    is replaced atomically. Saves hold an ``flock`` on a per-key lock file, so
    the compare-and-set is safe across threads and processes on one host.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)

    def _paths(self, key: ThreadKey) -> tuple[Path, Path]:
        digest = key._digest()
        return self._root / f"{digest}.thread", self._root / f"{digest}.lock"

    async def load(self, key: ThreadKey) -> ThreadRecord | None:
        return await asyncio.to_thread(self._load_sync, key)

    async def save(
        self,
        key: ThreadKey,
        thread_id: str,
        rollout: Rollout,
        instruction_hash: str,
        *,
        expected_version: int | None,
    ) -> int:
        _check_key(key)
        _check_save_args(thread_id, rollout)
        return await asyncio.to_thread(
            self._save_sync, key, thread_id, rollout, instruction_hash, expected_version
        )

    async def delete(self, key: ThreadKey) -> None:
        await asyncio.to_thread(self._delete_sync, key)

    # -- sync helpers (run in a worker thread) ------------------------------

    def _read_file(self, path: Path) -> ThreadRecord | None:
        try:
            with open(path, "rb") as f:
                header = json.loads(f.readline())
                payload = f.read()
        except FileNotFoundError:
            return None
        try:
            data = gzip.decompress(payload)
        except (OSError, EOFError) as e:
            raise ThreadStoreCorrupt(f"undecodable rollout in {path.name}") from e
        if _sha256(data) != header["rollout_sha256"]:
            raise ThreadStoreCorrupt(f"rollout checksum mismatch in {path.name}")
        return ThreadRecord(
            thread_id=header["thread_id"],
            rollout=Rollout(
                thread_id=header["thread_id"], relpath=header["relpath"], data=data
            ),
            version=int(header["version"]),
            instruction_hash=header["instruction_hash"],
        )

    def _load_sync(self, key: ThreadKey) -> ThreadRecord | None:
        path, _ = self._paths(key)
        return self._read_file(path)

    def _locked(self, key: ThreadKey):
        return _FileLock(self._paths(key)[1])

    def _save_sync(
        self,
        key: ThreadKey,
        thread_id: str,
        rollout: Rollout,
        instruction_hash: str,
        expected_version: int | None,
    ) -> int:
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path, _ = self._paths(key)
        with self._locked(key):
            current = self._read_file(path)
            current_version = current.version if current else None
            if current_version != expected_version:
                raise ThreadStoreConflict(
                    f"expected version {expected_version}, found {current_version}"
                )
            version = 1 if current is None else current.version + 1
            header = {
                "thread_id": thread_id,
                "relpath": rollout.relpath,
                "version": version,
                "instruction_hash": instruction_hash,
                "rollout_sha256": _sha256(rollout.data),
                "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }
            body = json.dumps(header).encode("utf-8") + b"\n" + _compress(rollout.data)
            fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(self._root))
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(body)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
                raise
            return version

    def _delete_sync(self, key: ThreadKey) -> None:
        if not self._root.is_dir():
            return
        path, _ = self._paths(key)
        with self._locked(key):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


class _FileLock:
    """Exclusive ``flock`` on a lock file (process-local lock without fcntl)."""

    _fallback_locks: dict[str, threading.Lock] = {}
    _fallback_guard = threading.Lock()

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None
        self._fallback: threading.Lock | None = None

    def __enter__(self) -> "_FileLock":
        try:
            import fcntl
        except ImportError:  # pragma: no cover - non-POSIX
            with self._fallback_guard:
                lock = self._fallback_locks.setdefault(
                    str(self._path), threading.Lock()
                )
            lock.acquire()
            self._fallback = lock
            return self
        self._fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._fd is not None:
            os.close(self._fd)  # closing releases the flock
            self._fd = None
        if self._fallback is not None:
            self._fallback.release()
            self._fallback = None


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def _build_table(table_name: str):
    from sqlalchemy import (
        Column,
        DateTime,
        Integer,
        LargeBinary,
        MetaData,
        String,
        Table,
    )
    from sqlalchemy.dialects.mysql import LONGBLOB

    metadata = MetaData()
    table = Table(
        table_name,
        metadata,
        Column("app_name", String(_KEY_LENGTH), primary_key=True),
        Column("user_id", String(_KEY_LENGTH), primary_key=True),
        Column("session_id", String(_KEY_LENGTH), primary_key=True),
        Column("agent_name", String(_KEY_LENGTH), primary_key=True),
        Column("thread_id", String(_KEY_LENGTH), nullable=False),
        Column("relpath", String(512), nullable=False),
        # BLOB on sqlite, BYTEA on postgresql; MySQL's plain BLOB caps at
        # 64 KiB, so use LONGBLOB (4 GiB) there.
        Column(
            "rollout_gz",
            LargeBinary().with_variant(LONGBLOB(), "mysql"),
            nullable=False,
        ),
        Column("rollout_size", Integer, nullable=False),
        Column("rollout_sha256", String(64), nullable=False),
        Column("version", Integer, nullable=False),
        Column("instruction_hash", String(64), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    return metadata, table


class DatabaseThreadStore(CodexThreadStore):
    """Stores records in a SQL table via a SQLAlchemy ``AsyncEngine``.

    Pass the short-term memory's engine (``DatabaseSessionService.db_engine``)
    so threads live next to the sessions they belong to; the connection
    settings (driver, pool, PostgreSQL ``search_path`` schema) are inherited.
    The table is created on first use if missing. The compare-and-set is a
    single ``UPDATE ... WHERE version = :expected`` (or an ``INSERT`` guarded
    by the primary key), so it is safe across instances.
    """

    def __init__(
        self, engine: "AsyncEngine", *, table_name: str = DEFAULT_TABLE_NAME
    ) -> None:
        self._engine = engine
        self._metadata, self._table = _build_table(table_name)
        self._ready = False
        self._ready_lock: asyncio.Lock | None = None

    @property
    def engine(self) -> "AsyncEngine":
        return self._engine

    async def _ensure_table(self) -> None:
        if self._ready:
            return
        if self._ready_lock is None:
            self._ready_lock = asyncio.Lock()
        async with self._ready_lock:
            if self._ready:
                return
            try:
                async with self._engine.begin() as conn:
                    await conn.run_sync(self._metadata.create_all, checkfirst=True)
            except Exception:
                # Another instance may have created it between check and create.
                async with self._engine.connect() as conn:
                    exists = await conn.run_sync(
                        lambda c: c.dialect.has_table(c, self._table.name)
                    )
                if not exists:
                    raise
            self._ready = True

    def _where(self, key: ThreadKey):
        t = self._table
        return (
            (t.c.app_name == key.app_name)
            & (t.c.user_id == key.user_id)
            & (t.c.session_id == key.session_id)
            & (t.c.agent_name == key.agent_name)
        )

    async def load(self, key: ThreadKey) -> ThreadRecord | None:
        from sqlalchemy import select

        await self._ensure_table()
        t = self._table
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    select(
                        t.c.thread_id,
                        t.c.relpath,
                        t.c.rollout_gz,
                        t.c.rollout_sha256,
                        t.c.version,
                        t.c.instruction_hash,
                    ).where(self._where(key))
                )
            ).first()
        if row is None:
            return None
        try:
            data = await asyncio.to_thread(gzip.decompress, bytes(row.rollout_gz))
        except (OSError, EOFError) as e:
            raise ThreadStoreCorrupt(
                f"undecodable rollout for thread {row.thread_id}"
            ) from e
        if _sha256(data) != row.rollout_sha256:
            raise ThreadStoreCorrupt(f"rollout checksum mismatch for {row.thread_id}")
        return ThreadRecord(
            thread_id=row.thread_id,
            rollout=Rollout(thread_id=row.thread_id, relpath=row.relpath, data=data),
            version=int(row.version),
            instruction_hash=row.instruction_hash,
        )

    async def save(
        self,
        key: ThreadKey,
        thread_id: str,
        rollout: Rollout,
        instruction_hash: str,
        *,
        expected_version: int | None,
    ) -> int:
        from sqlalchemy import insert, update
        from sqlalchemy.exc import IntegrityError

        _check_key(key)
        _check_save_args(thread_id, rollout)
        await self._ensure_table()
        blob = await asyncio.to_thread(_compress, rollout.data)
        values = {
            "thread_id": thread_id,
            "relpath": rollout.relpath,
            "rollout_gz": blob,
            "rollout_size": len(rollout.data),
            "rollout_sha256": _sha256(rollout.data),
            "instruction_hash": instruction_hash,
            "updated_at": _dt.datetime.now(_dt.timezone.utc),
        }
        t = self._table
        if expected_version is None:
            try:
                async with self._engine.begin() as conn:
                    await conn.execute(
                        insert(t).values(
                            app_name=key.app_name,
                            user_id=key.user_id,
                            session_id=key.session_id,
                            agent_name=key.agent_name,
                            version=1,
                            **values,
                        )
                    )
            except IntegrityError as e:
                raise ThreadStoreConflict("record already exists") from e
            new_version = 1
        else:
            new_version = expected_version + 1
            async with self._engine.begin() as conn:
                result = await conn.execute(
                    update(t)
                    .where(self._where(key) & (t.c.version == expected_version))
                    .values(version=new_version, **values)
                )
                matched = result.rowcount
            if matched != 1:
                raise ThreadStoreConflict(
                    f"expected version {expected_version} is not current"
                )
        logger.debug(
            "codex_thread_saved thread_id=%s version=%d bytes=%d stored_bytes=%d",
            thread_id,
            new_version,
            len(rollout.data),
            len(blob),
        )
        return new_version

    async def delete(self, key: ThreadKey) -> None:
        from sqlalchemy import delete

        await self._ensure_table()
        async with self._engine.begin() as conn:
            await conn.execute(delete(self._table).where(self._where(key)))


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

# One store per session service, so every turn in a process shares the same
# in-memory records / table-created flag. Weak keys: the store goes when the
# session service does.
_STORES: "weakref.WeakKeyDictionary[Any, CodexThreadStore]" = (
    weakref.WeakKeyDictionary()
)
_STORES_LOCK = threading.Lock()


def select_thread_store(short_term_memory_or_session_service: Any) -> CodexThreadStore:
    """Pick the thread store matching a short-term memory backend.

    Accepts a VeADK ``ShortTermMemory`` or any ADK ``BaseSessionService``.

    * ADK ``DatabaseSessionService`` (the ``sqlite``, ``mysql`` and
      ``postgresql`` backends, and any ``db_url``): a
      :class:`DatabaseThreadStore` on the service's own ``db_engine``.
    * anything else (``local`` -> ``InMemorySessionService``, or a custom /
      hosted service with no SQL engine): an :class:`InMemoryThreadStore`,
      which does not survive the process.

    The same store object is returned for the same session service.
    """
    from google.adk.sessions import DatabaseSessionService

    service = short_term_memory_or_session_service
    if not _is_session_service(service):
        service = getattr(service, "session_service", service)

    with _STORES_LOCK:
        try:
            cached = _STORES.get(service)
        except TypeError:  # not weak-referenceable
            cached = None
        if cached is not None:
            return cached

        if isinstance(service, DatabaseSessionService):
            engine = getattr(service, "db_engine", None)
            if engine is None or not hasattr(engine, "sync_engine"):
                raise TypeError(
                    "DatabaseSessionService has no AsyncEngine `db_engine`; "
                    "cannot place Codex threads in its database"
                )
            store: CodexThreadStore = DatabaseThreadStore(engine)
            logger.info(
                "codex_thread_store backend=database dialect=%s",
                engine.dialect.name,
            )
        else:
            store = InMemoryThreadStore()
            logger.info(
                "codex_thread_store backend=in_memory session_service=%s",
                type(service).__name__,
            )
        try:
            _STORES[service] = store
        except TypeError:
            pass
        return store


def _is_session_service(obj: Any) -> bool:
    from google.adk.sessions import BaseSessionService

    return isinstance(obj, BaseSessionService)
