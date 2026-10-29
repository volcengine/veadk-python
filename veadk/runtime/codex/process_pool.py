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

"""Warm ``codex app-server`` processes, one per persistent session thread.

Without this, every invocation spawned a fresh app-server, imported the
session's whole rollout into a new ``CODEX_HOME`` and had Codex replay it
(``thread_resume``) before the turn could start, so each turn got slower as
the session grew. A process whose turn ended cleanly is instead parked here,
with its ``CODEX_HOME`` and loaded thread, and the session's next invocation
runs its turn on that thread directly.

Reuse is deliberately narrow; anything else takes the cold path:

- Only the direct transport with ``thread_mode="resume"``: those invocations
  hold the per-session turn lock, so one process never serves two turns at
  once. (The shim's per-turn bearer token is baked into the process env.)
- Tool-bearing processes reuse by default (``mcp_process_reuse=True``). Their bridge
  credential owns a fixed manifest; each invocation binds fresh executors and
  validates SDK thread/turn identity before executing business tools.
- A process is parked only after its turn reached ``turn/completed`` and its
  rollout was saved, so a later ``turn()`` can never join a turn still winding
  down, and the store holds exactly what the warm thread holds.
- It is reused only if the invocation's settings produce the same fingerprint
  (config.toml, skills, env, thread config, tools, workspace, instructions)
  and the store namespace, thread ID and version still match. Another
  instance that advanced the thread makes the warm copy stale.
- A process that died, outlived :data:`MAX_TURNS_PER_PROCESS`, or sat idle
  past the idle TTL is closed.

Pools are process-local. Knobs: ``VEADK_CODEX_PROCESS_POOL_SIZE`` (idle
processes kept, default 20; ``0`` disables reuse) and
``VEADK_CODEX_PROCESS_IDLE_TTL_SECONDS`` (default 600).
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import hashlib
import json
import os
import shutil
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable

from veadk.runtime.codex.turn_control import STATUS_UNKNOWN
from veadk.runtime.codex.turn_control import TurnCompletion
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

POOL_SIZE_ENV = "VEADK_CODEX_PROCESS_POOL_SIZE"
IDLE_TTL_ENV = "VEADK_CODEX_PROCESS_IDLE_TTL_SECONDS"
DEFAULT_POOL_SIZE = 20
DEFAULT_IDLE_TTL_SECONDS = 600.0
#: The SDK queues every notification no turn consumes and never drains that
#: queue, so a process is retired after this many turns to bound it.
MAX_TURNS_PER_PROCESS = 100


def pool_size() -> int:
    """Idle processes kept at most; ``0`` disables reuse."""
    raw = os.getenv(POOL_SIZE_ENV, "").strip()
    try:
        return max(0, int(raw)) if raw else DEFAULT_POOL_SIZE
    except ValueError:
        logger.warning("codex_process_pool_invalid_size value_ignored=true")
        return DEFAULT_POOL_SIZE


def idle_ttl_seconds() -> float:
    """How long a parked process may sit idle before it is closed."""
    raw = os.getenv(IDLE_TTL_ENV, "").strip()
    try:
        value = float(raw) if raw else DEFAULT_IDLE_TTL_SECONDS
    except ValueError:
        logger.warning("codex_process_pool_invalid_idle_ttl value_ignored=true")
        return DEFAULT_IDLE_TTL_SECONDS
    return value if value > 0 else DEFAULT_IDLE_TTL_SECONDS


def process_alive(codex: Any) -> bool:
    """Whether ``codex``'s app-server and the SDK's reader are still running.

    Reads the pinned SDK's internals (``AsyncCodex._client._sync``). Once the
    reader thread is gone the SDK fails every pending call but keeps the
    client marked initialized, so a dead process is only detectable here.
    Anything without those internals is treated as not reusable.
    """
    sync = getattr(getattr(codex, "_client", None), "_sync", None)
    proc = getattr(sync, "_proc", None)
    if proc is None:
        return False
    reader = getattr(sync, "_reader_thread", None)
    return proc.poll() is None and (reader is None or reader.is_alive())


def fingerprint(*parts: Any) -> str:
    """Digest of everything a warm process must share with an invocation.

    Only the digest is kept, so credentials among ``parts`` are never stored.
    """
    raw = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def tree_digest(root: str) -> str:
    """Digest every entry under ``root``, including linked skill trees.

    ``root``'s own path is masked in contents: a config naming its own
    ``CODEX_HOME`` (the skills read grant) must digest the same in every home.
    """
    digest = hashlib.sha256()
    own_paths = sorted(
        {root.encode("utf-8"), os.path.realpath(root).encode("utf-8")},
        key=len,
        reverse=True,
    )

    def add(path: str, relative: str, ancestors: frozenset[tuple[int, int]]) -> None:
        try:
            stat = os.stat(path, follow_symlinks=True)
            identity = (stat.st_dev, stat.st_ino)
            if os.path.islink(path):
                target = os.path.realpath(path).encode("utf-8")
                for own in own_paths:
                    target = target.replace(own, b"$CODEX_HOME")
                digest.update(b"L\0" + relative.encode("utf-8") + b"\0" + target)
            if os.path.isdir(path):
                if identity in ancestors:
                    digest.update(b"C\0" + relative.encode("utf-8"))
                    return
                digest.update(b"D\0" + relative.encode("utf-8"))
                next_ancestors = ancestors | {identity}
                with os.scandir(path) as entries:
                    children = sorted(entries, key=lambda entry: entry.name)
                for child in children:
                    child_relative = (
                        f"{relative}/{child.name}" if relative else child.name
                    )
                    add(child.path, child_relative, next_ancestors)
                return
            digest.update(b"F\0" + relative.encode("utf-8") + b"\0")
            with open(path, "rb") as f:
                content = f.read()
            for own in own_paths:
                content = content.replace(own, b"$CODEX_HOME")
            digest.update(hashlib.sha256(content).digest())
        except OSError as e:
            digest.update(
                b"E\0"
                + relative.encode("utf-8")
                + b"\0"
                + type(e).__name__.encode("ascii", "replace")
            )

    add(root, "", frozenset())
    return digest.hexdigest()


@dataclass(eq=False)
class WarmCodex:
    """A parked app-server holding one session's loaded thread."""

    codex: Any
    codex_home: str
    fingerprint: str
    bridge_token: str
    thread: Any
    thread_id: str
    #: Store version of the rollout this process saved last.
    version: int
    covered_invocation_id: str
    turns: int
    on_close: Callable[[], None] | None = None
    loop: asyncio.AbstractEventLoop = field(default_factory=asyncio.get_running_loop)
    expiry: asyncio.TimerHandle | None = None
    idle_since: float = field(default_factory=time.monotonic)


class CodexProcessLease:
    """The Codex process one invocation runs its turn on.

    Used as ``async with lease:``. A cold lease spawns its process on entry.
    On exit the process is closed, unless the turn ended cleanly
    (``completion`` resolved with a known status) and the process may be
    reused, in which case it is ``kept`` for the caller to park or close.
    """

    def __init__(
        self,
        factory: Callable[[], Any],
        warm: WarmCodex | None,
        *,
        reusable: bool,
    ) -> None:
        self._factory = factory
        self.warm = warm
        self.reusable = reusable
        self.codex: Any = warm.codex if warm is not None else None
        self.completion: TurnCompletion | None = None
        self.kept = False
        self.detached = False

    @property
    def thread(self) -> Any:
        """The warm thread to run on, or ``None`` to start or resume one."""
        return self.warm.thread if self.warm is not None else None

    async def __aenter__(self) -> "CodexProcessLease":
        if self.codex is None:
            self.codex = self._factory()
            try:
                await self.codex.__aenter__()
            except BaseException:
                await self.close()
                raise
        return self

    async def __aexit__(self, exc_type: Any, _exc: Any, _tb: Any) -> bool:
        status = self.completion.status if self.completion is not None else None
        if (
            exc_type is None
            and self.reusable
            and status not in (None, STATUS_UNKNOWN)
            and process_alive(self.codex)
        ):
            self.kept = True
        else:
            await self.close()
        return False

    def detach(self) -> None:
        """Hand the process to the pool; :meth:`close` no longer touches it."""
        self.codex = None
        self.kept = False
        self.detached = True

    async def close(self) -> None:
        codex, self.codex = self.codex, None
        self.kept = False
        if codex is not None:
            if self.warm is not None:
                _revoke_binding(self.warm)
            await _close_codex(codex)


class CodexProcessPool:
    """Idle warm processes by session key, least recently used first."""

    def __init__(self) -> None:
        self._idle: OrderedDict[Hashable, WarmCodex] = OrderedDict()
        self._closing: set[asyncio.Task[None]] = set()
        self._atexit_registered = False

    def take(self, key: Hashable, process_fingerprint: str) -> WarmCodex | None:
        """Remove and return ``key``'s warm process if it can serve this turn."""
        self._sweep()
        entry = self._idle.pop(key, None)
        if entry is None:
            return None
        _cancel_expiry(entry)
        reason = ""
        if entry.fingerprint != process_fingerprint:
            reason = "settings_changed"
        elif entry.loop is not _running_loop():
            reason = "event_loop_changed"
        elif not process_alive(entry.codex):
            reason = "process_exited"
        if reason:
            logger.info("codex_process_discarded reason=%s", reason)
            self.discard(entry)
            return None
        return entry

    def put(self, key: Hashable, entry: WarmCodex) -> bool:
        """Park ``entry``; ``False`` means the caller still owns and closes it."""
        size = pool_size()
        if (
            size <= 0
            or entry.turns >= MAX_TURNS_PER_PROCESS
            or not process_alive(entry.codex)
        ):
            return False
        self._sweep()
        previous = self._idle.pop(key, None)
        if previous is not None and previous is not entry:
            _cancel_expiry(previous)
            self.discard(previous)
        self._register_atexit()
        entry.idle_since = time.monotonic()
        entry.expiry = entry.loop.call_later(
            idle_ttl_seconds(), self._expire, key, entry
        )
        self._idle[key] = entry
        while len(self._idle) > size:
            _, evicted = self._idle.popitem(last=False)
            _cancel_expiry(evicted)
            logger.info("codex_process_discarded reason=evicted")
            self.discard(evicted)
        return True

    def discard(self, entry: WarmCodex) -> None:
        """Close ``entry`` in the background."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            _kill(entry)
            return
        if len(self._closing) >= max(1, pool_size()):
            logger.warning("codex_process_close_overflow action=kill")
            _kill_process(entry)
            return
        task = loop.create_task(_close_warm(entry))
        self._closing.add(task)
        task.add_done_callback(self._closing.discard)

    async def release(self, match: Callable[[Hashable], bool]) -> int:
        """Close the parked processes whose key ``match`` accepts.

        A process serving a turn right now is not parked, so it is not
        released; it is parked again when its turn ends and expires with the
        idle TTL.

        Returns:
            The number of processes closed.
        """
        entries = [
            (key, entry) for key, entry in list(self._idle.items()) if match(key)
        ]
        for key, entry in entries:
            del self._idle[key]
            _cancel_expiry(entry)
        await asyncio.gather(
            *(_close_warm(entry) for _, entry in entries), return_exceptions=True
        )
        return len(entries)

    async def close_all(self) -> None:
        """Close every parked process (server shutdown, tests)."""
        entries = list(self._idle.values())
        self._idle.clear()
        for entry in entries:
            _cancel_expiry(entry)
        await asyncio.gather(
            *(_close_warm(entry) for entry in entries),
            *list(self._closing),
            return_exceptions=True,
        )

    def _sweep(self) -> None:
        """Close idle processes past the TTL whose timer never fired.

        The expiry timer runs on the loop that parked the process; if that
        loop stopped (a caller running each request in its own loop), only
        this sweep reclaims the process.
        """
        deadline = time.monotonic() - idle_ttl_seconds()
        for key, entry in list(self._idle.items()):
            if entry.idle_since <= deadline:
                self._expire(key, entry)

    def _expire(self, key: Hashable, entry: WarmCodex) -> None:
        if self._idle.get(key) is entry:
            del self._idle[key]
            _cancel_expiry(entry)
            logger.info("codex_process_discarded reason=idle_ttl")
            self.discard(entry)

    def _register_atexit(self) -> None:
        if not self._atexit_registered:
            self._atexit_registered = True
            atexit.register(self._kill_all)

    def _kill_all(self) -> None:
        entries = list(self._idle.values())
        self._idle.clear()
        for entry in entries:
            _kill(entry)


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _cancel_expiry(entry: WarmCodex) -> None:
    if entry.expiry is not None:
        entry.expiry.cancel()
        entry.expiry = None


async def _close_codex(codex: Any) -> None:
    try:
        await codex.__aexit__(None, None, None)
    except Exception as e:  # noqa: BLE001 - closing must not mask the turn
        logger.warning("codex_process_close_failed error_type=%s", type(e).__name__)


async def _close_warm(entry: WarmCodex) -> None:
    _revoke_binding(entry)
    await _close_codex(entry.codex)
    await asyncio.to_thread(shutil.rmtree, entry.codex_home, True)


def _kill(entry: WarmCodex) -> None:
    """Synchronous close for when no event loop is running (``atexit``)."""
    _revoke_binding(entry)
    sync = getattr(getattr(entry.codex, "_client", None), "_sync", None)
    with contextlib.suppress(Exception):
        if sync is not None:
            sync.close()
    shutil.rmtree(entry.codex_home, ignore_errors=True)


def _kill_process(entry: WarmCodex) -> None:
    """Stop an already-discarded idle child without blocking or deleting."""
    _revoke_binding(entry)
    sync = getattr(getattr(entry.codex, "_client", None), "_sync", None)
    proc = getattr(sync, "_proc", None)
    with contextlib.suppress(Exception):
        if proc is not None and proc.poll() is None:
            proc.kill()


def _revoke_binding(entry: WarmCodex) -> None:
    callback, entry.on_close = entry.on_close, None
    if callback is not None:
        callback()
