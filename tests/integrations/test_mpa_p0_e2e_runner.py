from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "verify-mpa-p0-e2e.sh"


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "live-manifest.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "runId": "run-20260915-001",
                "resourcePrefix": "mpa-p0-e2e-run-20260915-001",
                "provider": "volcengine",
                "region": "cn-beijing",
                "project": "test-project",
                "runtimeImageDigest": "sha256:" + "a" * 64,
                "model": "test-model",
                "postgres": "isolated-test-schema",
                "stepTimeoutSeconds": 120,
                "costCapUsd": 1,
                "cleanupOwner": "mpa-p0-test",
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _run(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(RUNNER), *args],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_dry_run_emits_ordered_plan_without_creating_checkpoint(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    checkpoint = tmp_path / "checkpoint.json"

    result = _run(
        "--manifest", str(manifest), "--checkpoint", str(checkpoint), "--dry-run"
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "dry-run"
    assert report["stages"] == ["AC-11", "AC-1", "AC-2", "AC-6", "AC-9"]
    assert checkpoint.exists() is False


def test_execute_requires_explicit_live_switch(tmp_path: Path) -> None:
    result = _run("--manifest", str(_manifest(tmp_path)), "--execute")

    assert result.returncode == 4
    assert json.loads(result.stdout)["errorCode"] == "live_execution_not_authorized"


def test_checkpoint_resume_and_cleanup_are_zero_residue(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    checkpoint = tmp_path / "checkpoint.json"
    driver_log = tmp_path / "driver.jsonl"
    driver = tmp_path / "driver.py"
    driver.write_text(
        """#!/usr/bin/env python3
import json, os, sys
request = json.loads(sys.stdin.read())
with open(os.environ[\"DRIVER_LOG\"], \"a\", encoding=\"utf-8\") as stream:
    stream.write(json.dumps(request, sort_keys=True) + \"\\n\")
if request[\"command\"] == \"run_stage\":
    print(json.dumps({\"status\": \"passed\", \"resources\": [{\"type\": \"agent\", \"id\": request[\"stage\"]}]}))
elif request[\"command\"] == \"list_resources\":
    print(json.dumps({\"resources\": []}))
else:
    print(json.dumps({\"status\": \"deleted\"}))
""",
        encoding="utf-8",
    )
    driver.chmod(0o700)
    env = dict(os.environ, VEADK_MPA_P0_LIVE="1", DRIVER_LOG=str(driver_log))

    first = _run(
        "--manifest",
        str(manifest),
        "--checkpoint",
        str(checkpoint),
        "--driver",
        str(driver),
        "--execute",
        "--stop-after",
        "AC-2",
        env=env,
    )
    assert first.returncode == 75
    second = _run(
        "--manifest",
        str(manifest),
        "--checkpoint",
        str(checkpoint),
        "--driver",
        str(driver),
        "--execute",
        env=env,
    )

    assert second.returncode == 0, second.stderr
    report = json.loads(second.stdout)
    assert report["status"] == "passed"
    assert report["residue"] == []
    calls = [json.loads(line) for line in driver_log.read_text().splitlines()]
    stages = [item["stage"] for item in calls if item["command"] == "run_stage"]
    assert stages == ["AC-11", "AC-1", "AC-2", "AC-6", "AC-9"]
    assert any(item["command"] == "delete_resource" for item in calls)
    assert calls[-1]["command"] == "list_resources"
