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

"""Move a Codex thread's rollout file in and out of a ``CODEX_HOME``.

A persistent (non-ephemeral) Codex thread keeps its whole context in a single
JSONL rollout file::

    $CODEX_HOME/sessions/YYYY/MM/DD/rollout-<timestamp>-<thread_id>.jsonl

Copying just that file into a fresh ``CODEX_HOME`` is enough for
``thread_resume`` to see the full history (the sqlite state files are not
needed). VeADK runs stateless and multi-instance, so it exports the rollout
after a turn and imports it before the next one, possibly on another host.

This module is plain file I/O. It does not depend on the Codex SDK, so it stays
importable without the optional ``openai-codex`` extra.

Rollout contents are user conversation data: nothing here logs them, and
:class:`Rollout` keeps ``data`` out of its ``repr``.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: Directory (relative to ``CODEX_HOME``) Codex writes live rollouts into.
SESSIONS_DIR = "sessions"

# Codex thread ids are UUIDs. Accept a conservative superset (no path or glob
# metacharacters) so the id is safe inside a glob and a file name.
_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
# Prefix of the temp file `import_rollout` writes before renaming it into
# place. Dot-prefixed so `find_rollout` never mistakes it for a real rollout.
_TMP_PREFIX = ".veadk-import-"


@dataclass(frozen=True)
class Rollout:
    """One Codex thread's rollout file, detached from any ``CODEX_HOME``.

    Attributes:
        thread_id: The Codex thread id the rollout belongs to.
        relpath: POSIX path relative to ``CODEX_HOME``, e.g.
            ``sessions/2026/09/30/rollout-2026-09-30T10-00-00-<id>.jsonl``.
        data: The raw file bytes. Excluded from ``repr`` so a logged record
            never leaks conversation content.
    """

    thread_id: str
    relpath: str
    data: bytes = field(repr=False)


def validate_thread_id(thread_id: str) -> None:
    """Raise ``ValueError`` unless ``thread_id`` is safe in a path and a glob."""
    if not isinstance(thread_id, str) or not _THREAD_ID_RE.match(thread_id):
        raise ValueError(f"invalid Codex thread id: {thread_id!r}")


def validate_rollout(rollout: Rollout) -> None:
    """Check ``rollout`` is safe to materialise under a ``CODEX_HOME``.

    The relpath comes from storage that may be shared or tampered with, so it
    must be a relative POSIX path under ``sessions/`` with no ``..``/``.``
    segments, and its file name must be a rollout file for ``thread_id``. That
    keeps an import from overwriting anything else in ``CODEX_HOME`` (for
    example ``config.toml`` or ``auth.json``).

    Raises:
        ValueError: if any check fails.
    """
    validate_thread_id(rollout.thread_id)
    relpath = rollout.relpath
    if not isinstance(relpath, str) or not relpath or "\\" in relpath:
        raise ValueError(f"invalid rollout relpath: {relpath!r}")
    if "\x00" in relpath:
        raise ValueError("rollout relpath contains a NUL byte")
    path = PurePosixPath(relpath)
    if path.is_absolute():
        raise ValueError(f"rollout relpath must be relative: {relpath!r}")
    parts = relpath.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"rollout relpath escapes CODEX_HOME: {relpath!r}")
    if parts[0] != SESSIONS_DIR or len(parts) < 2:
        raise ValueError(f"rollout relpath must be under {SESSIONS_DIR}/: {relpath!r}")
    if not _is_rollout_name(parts[-1], rollout.thread_id):
        raise ValueError(
            f"rollout file name does not match thread {rollout.thread_id!r}: "
            f"{relpath!r}"
        )


def _is_rollout_name(name: str, thread_id: str) -> bool:
    return name.startswith("rollout-") and name.endswith(f"-{thread_id}.jsonl")


def find_rollout(codex_home: str, thread_id: str) -> str | None:
    """Return the absolute path of ``thread_id``'s rollout, or ``None``.

    Only regular, non-hidden files named ``rollout-*-<thread_id>.jsonl`` under
    ``$CODEX_HOME/sessions`` count; temp/partial files (dot-prefixed, or with a
    suffix after ``.jsonl``) and symlinks are ignored. If more than one file
    matches, the thread is ambiguous and ``None`` is returned.
    """
    validate_thread_id(thread_id)
    sessions = Path(codex_home) / SESSIONS_DIR
    if not sessions.is_dir():
        return None
    matches = [
        p
        for p in sessions.rglob(f"rollout-*-{thread_id}.jsonl")
        if not p.name.startswith(".") and not p.is_symlink() and p.is_file()
    ]
    if len(matches) != 1:
        if matches:
            logger.warning(
                "codex_rollout_ambiguous thread_id=%s matches=%d",
                thread_id,
                len(matches),
            )
        return None
    return str(matches[0].resolve())


def export_rollout(codex_home: str, thread_id: str) -> Rollout | None:
    """Read ``thread_id``'s rollout out of ``codex_home``.

    Call it only once the turn has finished, so the file is not mid-write.

    Returns:
        The rollout, or ``None`` if :func:`find_rollout` finds no unique file.
    """
    path = find_rollout(codex_home, thread_id)
    if path is None:
        return None
    home = Path(codex_home).resolve()
    relpath = Path(path).relative_to(home).as_posix()
    with open(path, "rb") as f:
        data = f.read()
    rollout = Rollout(thread_id=thread_id, relpath=relpath, data=data)
    validate_rollout(rollout)
    logger.debug("codex_rollout_exported thread_id=%s bytes=%d", thread_id, len(data))
    return rollout


def import_rollout(codex_home: str, rollout: Rollout) -> str:
    """Write ``rollout`` into ``codex_home`` and return its absolute path.

    The file is written to a temp file in the destination directory, fsynced,
    chmod ``0600`` and renamed into place, so a reader never sees a partial
    rollout. Missing directories are created (``0700``). An existing file at
    the same path is replaced.

    Raises:
        ValueError: if the rollout fails :func:`validate_rollout`, or its path
            would resolve outside ``codex_home`` (e.g. via a symlinked
            directory).
    """
    validate_rollout(rollout)
    home = Path(codex_home).resolve()
    target = home.joinpath(*rollout.relpath.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Guard against a symlinked directory inside CODEX_HOME pointing elsewhere.
    parent = target.parent.resolve()
    if parent != home and home not in parent.parents:
        raise ValueError(f"rollout relpath escapes CODEX_HOME: {rollout.relpath!r}")
    target = parent / target.name

    fd, tmp = tempfile.mkstemp(prefix=_TMP_PREFIX, dir=str(parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(rollout.data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    logger.debug(
        "codex_rollout_imported thread_id=%s bytes=%d",
        rollout.thread_id,
        len(rollout.data),
    )
    return str(target)
