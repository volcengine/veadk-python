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

"""End-to-end checks for the in-Sandbox delivery driver protocol.

These tests execute the real shell command Studio ships to the Dev Sandbox against a
stub ``ak`` binary, so the driver lease, its heartbeat, and the published artifact
manifest are verified as one protocol rather than as isolated strings.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import pytest

from frontend.server.migration import service as migration_service
from frontend.server.migration.contracts import validate_migration_driver

TASK_ID = "migration-v1-" + "c" * 32
CONFIRMATION = {
    "framework": "langchain",
    "app_name": "support-agent",
    "entry": "agent.py:agent",
}


class DeliverySandbox:
    """One temporary Sandbox-like root driving the real migration start command."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = tmp_path / "migration"
        self.bin = tmp_path / "bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        self.plan_path = tmp_path / "plan.json"
        monkeypatch.setenv("FAKE_AK_PLAN", str(self.plan_path))
        for name, value in (
            ("MIGRATION_ROOT", str(self.root)),
            ("_PROJECT_PATH", f"{self.root}/workspace/source"),
            ("_CONFIRMATION_PATH", f"{self.root}/control/route-selection.json"),
            ("_INSTRUCTION_PATH", f"{self.root}/control/instruction.txt"),
            ("_DELIVERY_STATUS_PATH", f"{self.root}/delivery/migration-status.json"),
            ("_DELIVERY_ARTIFACT_PATH", f"{self.root}/delivery/migration-result.zip"),
            ("_MIGRATION_DRIVER_PATH", f"{self.root}/control/migration-driver.json"),
            (
                "_MIGRATION_DRIVER_SCRIPT_PATH",
                f"{self.root}/control/migration-driver.py",
            ),
            ("_MIGRATION_CLI_PID_PATH", f"{self.root}/control/migration-cli.pid"),
            (
                "_PROCESS_EXIT_PATH",
                f"{self.root}/diagnostics/migration/process-exit.json",
            ),
            ("_MIGRATION_DRIVER_HEARTBEAT_SECONDS", 0.1),
        ):
            monkeypatch.setattr(migration_service, name, value)
        # The Sandbox prepares the project tree before the migration starts; the
        # structured copy writes into output/veadk.
        for relative in (
            "workspace/source",
            "output",
            "control",
            "delivery",
            "diagnostics/migration",
        ):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        self._install_stub()

    def _install_stub(self) -> None:
        stub = self.bin / "ak"
        stub.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, time\n"
            "from pathlib import Path\n"
            "plan = json.load(open(os.environ['FAKE_AK_PLAN'], encoding='utf-8'))\n"
            "artifact = Path(plan['artifact'])\n"
            "artifact.parent.mkdir(parents=True, exist_ok=True)\n"
            "artifact.write_bytes(plan['content'].encode('utf-8'))\n"
            "time.sleep(plan.get('sleep', 0))\n"
            "raise SystemExit(plan.get('exit_code', 0))\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)

    def plan(
        self,
        *,
        content: str = "migration-zip",
        sleep: float = 0.0,
        exit_code: int = 0,
    ) -> None:
        self.plan_path.write_text(
            json.dumps(
                {
                    "artifact": migration_service._DELIVERY_ARTIFACT_PATH,
                    "content": content,
                    "sleep": sleep,
                    "exit_code": exit_code,
                }
            ),
            encoding="utf-8",
        )

    def run(self) -> str:
        payload = json.dumps({"schema_version": 1, **CONFIRMATION}).encode()
        digest = hashlib.sha256(payload).hexdigest()
        candidate = f"{self.root}/control/.route-selection-{digest}.json"
        Path(candidate).write_bytes(payload)
        instruction = f"{self.root}/control/.instruction-{digest}.txt"
        Path(instruction).write_text("迁移提示词", encoding="utf-8")
        command = migration_service._start_migration_command(
            TASK_ID,
            CONFIRMATION,
            digest,
            candidate,
            instruction,
        )
        completed = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"},
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == migration_service.MIGRATION_START_MARKER
        return command

    def lease(self) -> dict[str, object]:
        path = Path(migration_service._MIGRATION_DRIVER_PATH)
        assert path.is_file(), "the driver never published a lease"
        return json.loads(path.read_text(encoding="utf-8"))

    def lease_mtime(self) -> float:
        return Path(migration_service._MIGRATION_DRIVER_PATH).stat().st_mtime

    def process_exit(self) -> dict[str, object] | None:
        path = Path(migration_service._PROCESS_EXIT_PATH)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def wait_for_process_exit(self, timeout: float = 20.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            exit_record = self.process_exit()
            if exit_record is not None:
                return exit_record
            time.sleep(0.05)
        raise AssertionError("the launch script never recorded the process exit")

    def wait_for_lease(self, state: str, timeout: float = 20.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if Path(migration_service._MIGRATION_DRIVER_PATH).is_file():
                lease = self.lease()
                if lease.get("state") == state:
                    return lease
            time.sleep(0.05)
        raise AssertionError(f"the driver never reported state {state}")

    def kill_group(self) -> None:
        """Kill the run the way the reported failure did: silently, by group."""
        pid = int(
            Path(f"{self.root}/control/migration.pid").read_text(encoding="ascii")
        )
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
            assert str(self.root).encode() in command
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, FileNotFoundError):
            return


@pytest.mark.skipif(
    shutil.which("setsid") is None or shutil.which("bash") is None,
    reason="the delivery driver protocol needs bash and setsid",
)
def test_delivery_driver_publishes_the_artifact_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = DeliverySandbox(tmp_path, monkeypatch)
    content = "migration-zip"
    sandbox.plan(content=content, sleep=2.0)

    sandbox.run()

    running = sandbox.wait_for_lease("running")
    validate_migration_driver(running, expected_run_id=TASK_ID)
    assert running["finished_at"] is None
    assert running["exit_code"] is None
    assert running["artifact"] is None

    published_at = sandbox.lease_mtime()
    time.sleep(0.5)
    assert sandbox.lease_mtime() > published_at
    assert sandbox.lease()["state"] == "running"

    finished = sandbox.wait_for_lease("finished")
    validate_migration_driver(finished, expected_run_id=TASK_ID)
    assert finished["exit_code"] == 0
    assert finished["artifact"] == {
        "path": "migration-result.zip",
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "size": len(content.encode()),
    }
    exit_record = sandbox.wait_for_process_exit()
    assert exit_record["schema_version"] == 1
    assert exit_record["exit_code"] == 0


@pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="the delivery driver protocol needs bash",
)
def test_the_heartbeat_reports_a_cli_that_left_the_sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A heartbeat whose CLI is gone says so instead of beating on its behalf.

    The reported failure had exactly this shape: the launch shell and its heartbeat
    survived while the migration CLI was signalled away.  A heartbeat that kept
    advancing told Studio the run was still alive, so the task never settled.
    """
    sandbox = DeliverySandbox(tmp_path, monkeypatch)
    script = Path(migration_service._MIGRATION_DRIVER_SCRIPT_PATH)
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(migration_service._migration_driver_script(), encoding="utf-8")
    lease_path = Path(migration_service._MIGRATION_DRIVER_PATH)
    pid_path = Path(migration_service._MIGRATION_CLI_PID_PATH)
    cli = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    beating = subprocess.Popen(
        [
            sys.executable,
            str(script),
            str(lease_path),
            migration_service._DELIVERY_ARTIFACT_PATH,
            TASK_ID,
            "heartbeat",
            str(pid_path),
        ]
    )
    try:
        pid_path.write_text(str(cli.pid), encoding="utf-8")

        assert sandbox.wait_for_lease("running")["state"] == "running"
        assert beating.poll() is None

        cli.terminate()
        cli.wait(timeout=10)

        lost = sandbox.wait_for_lease("lost")
        assert beating.wait(timeout=10) == 0
        validate_migration_driver(lost, expected_run_id=TASK_ID)
        assert lost["finished_at"] is None
        assert lost["exit_code"] is None
        assert lost["artifact"] is None
    finally:
        cli.kill()
        cli.wait(timeout=10)
        if beating.poll() is None:
            beating.kill()
            beating.wait(timeout=10)


@pytest.mark.skipif(
    shutil.which("setsid") is None or shutil.which("bash") is None,
    reason="the delivery driver protocol needs bash and setsid",
)
def test_delivery_driver_stops_heartbeating_when_the_run_is_killed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = DeliverySandbox(tmp_path, monkeypatch)
    sandbox.plan(content="migration-zip", sleep=30.0)

    sandbox.run()

    running = sandbox.wait_for_lease("running")
    heartbeat_at = float(running["heartbeat_at"])
    last_lease = sandbox.lease_mtime()
    try:
        sandbox.kill_group()
        time.sleep(0.5)

        assert sandbox.lease()["state"] == "running"
        assert sandbox.lease_mtime() == last_lease
        # Nothing in the Sandbox can write the delivery state any more, so Studio
        # has to settle the task from the lease instead of waiting for the session
        # to expire.
        assert sandbox.process_exit() is None
    finally:
        sandbox.kill_group()

    stale = migration_service.MigrationService(
        None,  # type: ignore[arg-type] - the lease predicate only needs the clock
        clock=lambda: heartbeat_at + migration_service._MIGRATION_DRIVER_STALE_SECONDS,
    )
    fresh = migration_service.MigrationService(
        None,  # type: ignore[arg-type]
        clock=lambda: heartbeat_at + 5.0,
    )
    lease = validate_migration_driver(sandbox.lease(), expected_run_id=TASK_ID)

    assert stale._migration_driver_lost(lease) is True
    assert fresh._migration_driver_lost(lease) is False
