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

"""Reclaiming the temp roots a killed VeADK process left behind."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

import pytest

from veadk.runtime.codex import private_dirs
from veadk.runtime.codex.private_dirs import (
    HOME_ROOT_PREFIX,
    LEGACY_MAX_AGE_SECONDS,
    OWNER_LOCK,
    WORKSPACE_ROOT_PREFIX,
    create_owned_root,
    reap_orphans,
)

pytestmark = pytest.mark.skipif(
    private_dirs.fcntl is None, reason="ownership locks need fcntl"
)

_OLD = time.time() - LEGACY_MAX_AGE_SECONDS - 60


@pytest.fixture
def temp_dir(monkeypatch, tmp_path):
    """Roots go to an isolated temp dir; no background reaper thread."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(private_dirs, "_reaper_started", True)
    return tmp_path


def _dead_root(temp_dir, prefix: str):
    """A root whose owner exited: its lock file exists, nobody holds it."""
    root = temp_dir / f"{prefix}dead"
    (root / "session").mkdir(parents=True)
    (root / OWNER_LOCK).write_text("")
    return root


def test_a_root_whose_owner_died_is_removed(temp_dir) -> None:
    workspaces = _dead_root(temp_dir, WORKSPACE_ROOT_PREFIX)
    homes = _dead_root(temp_dir, HOME_ROOT_PREFIX)

    assert reap_orphans(str(temp_dir)) == 2
    assert not workspaces.exists() and not homes.exists()


def test_a_root_owned_by_a_live_process_is_kept(temp_dir) -> None:
    mine = create_owned_root(HOME_ROOT_PREFIX)
    # Another live process holding its root's lock.
    other = temp_dir / f"{WORKSPACE_ROOT_PREFIX}other"
    other.mkdir()
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, sys, time; f = open(sys.argv[1], 'w'); "
            "fcntl.flock(f, fcntl.LOCK_EX); print('locked', flush=True); "
            "time.sleep(60)",
            str(other / OWNER_LOCK),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline() == "locked\n"
        assert reap_orphans(str(temp_dir)) == 0
        assert os.path.isdir(mine) and other.is_dir()
    finally:
        holder.kill()
        holder.wait()
    # Its owner is gone now.
    assert reap_orphans(str(temp_dir)) == 1
    assert not other.exists() and os.path.isdir(mine)


def test_legacy_dirs_without_owner_locks_are_never_removed_automatically(
    temp_dir,
) -> None:
    fresh_root = temp_dir / f"{WORKSPACE_ROOT_PREFIX}legacy-fresh"
    old_root = temp_dir / f"{WORKSPACE_ROOT_PREFIX}legacy-old"
    fresh_home = temp_dir / "veadk-codex-fresh"
    old_home = temp_dir / "veadk-codex-old"
    not_a_home = temp_dir / "veadk-codex-something-else"
    for path in (fresh_root, old_root, fresh_home, old_home, not_a_home):
        path.mkdir()
    for home in (fresh_home, old_home):
        (home / "config.toml").write_text("")
    for path in (old_root, old_home / "config.toml", old_home, not_a_home):
        os.utime(path, (_OLD, _OLD))

    assert reap_orphans(str(temp_dir)) == 0
    assert all(
        path.exists()
        for path in (fresh_root, old_root, fresh_home, old_home, not_a_home)
    )


def test_failed_root_removal_is_not_counted_as_success(
    temp_dir, monkeypatch, caplog
) -> None:
    root = _dead_root(temp_dir, WORKSPACE_ROOT_PREFIX)

    def fail_remove(*args, **kwargs):
        raise PermissionError("not allowed")

    monkeypatch.setattr(private_dirs.shutil, "rmtree", fail_remove)

    assert reap_orphans(str(temp_dir)) == 0
    assert root.exists()
    assert "codex_orphan_reap_failed" in caplog.text
    assert "PermissionError" in caplog.text
