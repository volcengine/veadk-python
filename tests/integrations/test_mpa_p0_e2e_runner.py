from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "verify-mpa-p0-e2e.sh"
VC21_STAGES = [
    "VC21-COMPATIBILITY-FENCE",
    "VC21-RUNTIME-PROVISION",
    "VC21-VALID-UPDATE",
    "VC21-FAILURE-RECOVERY",
    "VC21-COMPATIBLE-ROLLBACK",
    "VC21-DELETE-ACTIVE-OPERATION",
    "VC21-DELETE-ACTIVE-SESSION",
    "VC21-DELETE-IDLE-SESSIONS",
    "VC21-FINAL-DELETE",
]


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
                "runtimeImageUrl": (
                    "registry.example.com/agentkit/mpa_agent:test-build"
                ),
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


def test_vc21_dry_run_emits_case_specific_lifecycle_plan(tmp_path: Path) -> None:
    result = _run(
        "--manifest",
        str(_manifest(tmp_path)),
        "--case",
        "VC-21",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report == {
        "case": "VC-21",
        "mode": "dry-run",
        "stages": VC21_STAGES,
        "status": "planned",
    }


def test_unsupported_case_returns_structured_error(tmp_path: Path) -> None:
    result = _run(
        "--manifest",
        str(_manifest(tmp_path)),
        "--case",
        "VC-99",
        "--dry-run",
    )

    assert result.returncode == 2
    assert json.loads(result.stdout) == {
        "case": "VC-99",
        "errorCode": "unsupported_case",
        "status": "invalid_arguments",
    }


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


def test_failed_stage_resources_are_checkpointed_before_cleanup(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    checkpoint = tmp_path / "checkpoint.json"
    driver_log = tmp_path / "driver.jsonl"
    driver = tmp_path / "driver.py"
    driver.write_text(
        """#!/usr/bin/env python3
import json, os, sys
request = json.loads(sys.stdin.read())
with open(os.environ["DRIVER_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(request, sort_keys=True) + "\\n")
if request["command"] == "run_stage":
    print(json.dumps({"status": "failed", "resources": [{"type": "runtime", "id": "r-created-before-failure"}]}))
elif request["command"] == "list_resources":
    print(json.dumps({"resources": []}))
else:
    print(json.dumps({"status": "deleted"}))
""",
        encoding="utf-8",
    )
    driver.chmod(0o700)
    env = dict(os.environ, VEADK_MPA_P0_LIVE="1", DRIVER_LOG=str(driver_log))

    result = _run(
        "--manifest",
        str(manifest),
        "--checkpoint",
        str(checkpoint),
        "--driver",
        str(driver),
        "--execute",
        env=env,
    )

    assert result.returncode == 5
    calls = [json.loads(line) for line in driver_log.read_text().splitlines()]
    delete_calls = [item for item in calls if item["command"] == "delete_resource"]
    assert delete_calls == [
        {
            "command": "delete_resource",
            "resource": {
                "type": "runtime",
                "id": "r-created-before-failure",
            },
        }
    ]


def test_failed_driver_preserves_safe_error_code_and_stage(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    checkpoint = tmp_path / "checkpoint.json"
    driver = tmp_path / "driver.py"
    driver.write_text(
        """#!/usr/bin/env python3
import json, sys
request = json.loads(sys.stdin.read())
if request["command"] == "run_stage":
    print(json.dumps({
        "status": "failed",
        "errorCode": "RuntimeError",
        "safeErrorCode": "studio_create_operation_http_500",
    }))
    raise SystemExit(1)
if request["command"] == "list_resources":
    print(json.dumps({"resources": []}))
else:
    print(json.dumps({"status": "deleted"}))
""",
        encoding="utf-8",
    )
    driver.chmod(0o700)
    env = dict(os.environ, VEADK_MPA_P0_LIVE="1")

    result = _run(
        "--manifest",
        str(manifest),
        "--checkpoint",
        str(checkpoint),
        "--driver",
        str(driver),
        "--execute",
        env=env,
    )

    assert result.returncode == 5
    assert json.loads(result.stdout) == {
        "errorCode": "studio_create_operation_http_500",
        "failedStage": "AC-11",
        "residue": [],
        "status": "failed",
    }


def test_cleanup_deletes_discovered_orphans_before_final_residue_check(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    checkpoint = tmp_path / "checkpoint.json"
    driver_log = tmp_path / "driver.jsonl"
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps({"resources": [{"type": "runtime", "id": "r-orphan"}]}),
        encoding="utf-8",
    )
    driver = tmp_path / "driver.py"
    driver.write_text(
        """#!/usr/bin/env python3
import json, os, sys
request = json.loads(sys.stdin.read())
with open(os.environ["DRIVER_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(request, sort_keys=True) + "\\n")
with open(os.environ["DRIVER_STATE"], encoding="utf-8") as stream:
    state = json.load(stream)
if request["command"] == "run_stage":
    print(json.dumps({"status": "failed", "resources": []}))
elif request["command"] == "list_resources":
    print(json.dumps({"resources": state["resources"]}))
else:
    state["resources"] = [item for item in state["resources"] if item != request["resource"]]
    with open(os.environ["DRIVER_STATE"], "w", encoding="utf-8") as stream:
        json.dump(state, stream)
    print(json.dumps({"status": "deleted"}))
""",
        encoding="utf-8",
    )
    driver.chmod(0o700)
    env = dict(
        os.environ,
        VEADK_MPA_P0_LIVE="1",
        DRIVER_LOG=str(driver_log),
        DRIVER_STATE=str(state),
    )

    result = _run(
        "--manifest",
        str(manifest),
        "--checkpoint",
        str(checkpoint),
        "--driver",
        str(driver),
        "--execute",
        env=env,
    )

    assert result.returncode == 5
    assert json.loads(result.stdout)["residue"] == []
    calls = [json.loads(line) for line in driver_log.read_text().splitlines()]
    assert [item["command"] for item in calls[-3:]] == [
        "list_resources",
        "delete_resource",
        "list_resources",
    ]


def test_pending_stage_is_retried_without_cleanup_or_duplicate_resources(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    checkpoint = tmp_path / "checkpoint.json"
    driver_log = tmp_path / "driver.jsonl"
    state = tmp_path / "state.json"
    state.write_text('{"attempts": 0}', encoding="utf-8")
    driver = tmp_path / "driver.py"
    driver.write_text(
        """#!/usr/bin/env python3
import json, os, sys
request = json.loads(sys.stdin.read())
with open(os.environ["DRIVER_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(request, sort_keys=True) + "\\n")
with open(os.environ["DRIVER_STATE"], encoding="utf-8") as stream:
    state = json.load(stream)
if request["command"] == "run_stage":
    state["attempts"] += 1
    with open(os.environ["DRIVER_STATE"], "w", encoding="utf-8") as stream:
        json.dump(state, stream)
    status = "pending" if state["attempts"] == 1 else "passed"
    print(json.dumps({"status": status, "retryAfterSeconds": 0, "resources": [{"type": "runtime", "id": "r-one"}]}))
elif request["command"] == "list_resources":
    print(json.dumps({"resources": []}))
else:
    print(json.dumps({"status": "deleted"}))
""",
        encoding="utf-8",
    )
    driver.chmod(0o700)
    env = dict(
        os.environ,
        VEADK_MPA_P0_LIVE="1",
        DRIVER_LOG=str(driver_log),
        DRIVER_STATE=str(state),
    )

    result = _run(
        "--manifest",
        str(manifest),
        "--checkpoint",
        str(checkpoint),
        "--driver",
        str(driver),
        "--execute",
        "--stop-after",
        "AC-11",
        env=env,
    )

    assert result.returncode == 75, result.stderr
    calls = [json.loads(line) for line in driver_log.read_text().splitlines()]
    run_calls = [item for item in calls if item["command"] == "run_stage"]
    assert len(run_calls) == 2
    saved = json.loads(checkpoint.read_text())
    assert saved["completedStages"] == ["AC-11"]


def test_retryable_driver_network_error_retries_same_stage_without_cleanup(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    checkpoint = tmp_path / "checkpoint.json"
    driver_log = tmp_path / "driver.jsonl"
    state = tmp_path / "state.json"
    state.write_text('{"attempts": 0}', encoding="utf-8")
    driver = tmp_path / "driver.py"
    driver.write_text(
        """#!/usr/bin/env python3
import json, os, sys
request = json.loads(sys.stdin.read())
with open(os.environ["DRIVER_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(request, sort_keys=True) + "\\n")
with open(os.environ["DRIVER_STATE"], encoding="utf-8") as stream:
    state = json.load(stream)
if request["command"] == "run_stage":
    state["attempts"] += 1
    with open(os.environ["DRIVER_STATE"], "w", encoding="utf-8") as stream:
        json.dump(state, stream)
    if state["attempts"] == 1:
        print(json.dumps({"status": "failed", "safeErrorCode": "NetworkError"}))
        raise SystemExit(1)
    print(json.dumps({"status": "passed", "resources": [{"type": "runtime", "id": "r-one"}]}))
elif request["command"] == "list_resources":
    print(json.dumps({"resources": []}))
else:
    print(json.dumps({"status": "deleted"}))
""",
        encoding="utf-8",
    )
    driver.chmod(0o700)
    env = dict(
        os.environ,
        VEADK_MPA_P0_LIVE="1",
        VEADK_MPA_P0_ASYNC_STAGE_TIMEOUT_SECONDS="5",
        DRIVER_LOG=str(driver_log),
        DRIVER_STATE=str(state),
    )

    result = _run(
        "--manifest",
        str(manifest),
        "--checkpoint",
        str(checkpoint),
        "--driver",
        str(driver),
        "--execute",
        "--stop-after",
        "AC-11",
        env=env,
    )

    assert result.returncode == 75, result.stderr
    calls = [json.loads(line) for line in driver_log.read_text().splitlines()]
    assert [item["command"] for item in calls] == [
        "run_stage",
        "run_stage",
        "delete_resource",
        "list_resources",
    ]
    saved = json.loads(checkpoint.read_text())
    assert saved["completedStages"] == ["AC-11"]
