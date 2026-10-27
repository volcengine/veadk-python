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

"""Process-owned temp roots for the Codex runtime, and reclaiming dead ones.

Each VeADK process keeps its session workspaces and its ``CODEX_HOME`` dirs
under roots it creates in the temp dir (``veadk-codex-workspaces-*``,
``veadk-codex-homes-*``). An ``atexit`` hook removes them on a clean exit, but
a ``SIGKILL`` (an OOM kill, a container stop) leaves them behind, holding
session files and rollouts. The app-server children do exit with their parent
(their stdin closes), so only the directories remain.

Ownership is an ``flock`` on ``<root>/.veadk-owner.lock``, held for the
process's lifetime: the kernel drops it whenever the owner dies, however it
dies, and a recycled PID cannot fake it. On first use a background thread
scans the temp dir and removes every root whose lock it can take. Roots and
loose ``CODEX_HOME`` dirs from older VeADK versions carry no lock. Their owner
cannot be proven dead, so they are retained. Without ``fcntl`` (Windows)
nothing is reaped.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path

from veadk.utils.logger import get_logger

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

logger = get_logger(__name__)

WORKSPACE_ROOT_PREFIX = "veadk-codex-workspaces-"
HOME_ROOT_PREFIX = "veadk-codex-homes-"
#: Loose per-invocation homes written by VeADK before the homes root existed.
LEGACY_HOME_PREFIX = "veadk-codex-"
OWNER_LOCK = ".veadk-owner.lock"
LEGACY_MAX_AGE_SECONDS = 24 * 3600

# Open lock files of the roots this process owns; closing one releases it.
_held_locks: list[object] = []
_reaper_started = False
_reaper_lock = threading.Lock()


def create_owned_root(prefix: str) -> str:
    """Create a temp root this process owns for its lifetime.

    Also starts, once per process, the background reclaim of roots whose
    owner died.
    """
    root = tempfile.mkdtemp(prefix=prefix)
    if fcntl is not None:
        lock = open(os.path.join(root, OWNER_LOCK), "w")  # noqa: SIM115 - held
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _held_locks.append(lock)
    _start_reaper(os.path.dirname(root))
    return root


def reap_orphans(temp_dir: str, *, now: float | None = None) -> int:
    """Remove dead processes' roots and stale legacy homes under ``temp_dir``.

    Returns:
        The number of directories removed.
    """
    if fcntl is None:
        return 0
    del now  # retained for caller compatibility; age is not proof of ownership
    removed = 0
    try:
        entries = list(Path(temp_dir).iterdir())
    except OSError as e:
        logger.warning(
            "codex_orphan_reap_failed category=temp_root error_type=%s",
            type(e).__name__,
        )
        return 0
    for entry in entries:
        name = entry.name
        try:
            if not entry.is_dir() or entry.is_symlink():
                continue
            if name.startswith((WORKSPACE_ROOT_PREFIX, HOME_ROOT_PREFIX)):
                if _reap_root(entry):
                    removed += 1
            elif name.startswith(LEGACY_HOME_PREFIX):
                continue
        except OSError as e:
            logger.warning(
                "codex_orphan_reap_failed category=temp_entry error_type=%s",
                type(e).__name__,
            )
            continue
    if removed:
        logger.info("codex_orphaned_dirs_reaped count=%d", removed)
    return removed


def _reap_root(root: Path) -> bool:
    lock_path = root / OWNER_LOCK
    if not lock_path.exists():
        return False
    assert fcntl is not None
    with open(lock_path, "a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False  # its owner is alive
        # Removed while holding the lock, so a live owner cannot be racing us.
        try:
            shutil.rmtree(root)
        except OSError as e:
            logger.warning(
                "codex_orphan_reap_failed category=owned_root error_type=%s",
                type(e).__name__,
            )
            return False
    return not root.exists()


def _start_reaper(temp_dir: str) -> None:
    global _reaper_started
    with _reaper_lock:
        if _reaper_started or fcntl is None:
            return
        _reaper_started = True
    threading.Thread(
        target=_reap_quietly,
        args=(temp_dir,),
        name="veadk-codex-orphan-reaper",
        daemon=True,
    ).start()


def _reap_quietly(temp_dir: str) -> None:
    try:
        reap_orphans(temp_dir)
    except Exception as e:  # noqa: BLE001 - housekeeping must not fail a turn
        logger.warning("codex_orphan_reap_failed error_type=%s", type(e).__name__)
