"""Checkpointed MPA P0 live runner with mandatory resource cleanup."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


STAGES = ("AC-11", "AC-1", "AC-2", "AC-6", "AC-9")
REQUIRED_MANIFEST_FIELDS = {
    "schemaVersion",
    "runId",
    "resourcePrefix",
    "provider",
    "region",
    "project",
    "runtimeImageDigest",
    "model",
    "postgres",
    "stepTimeoutSeconds",
    "costCapUsd",
    "cleanupOwner",
}
FORBIDDEN_PARTS = ("accesskey", "secret", "token", "password", "cookie")


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _load_manifest(path: Path) -> dict[str, Any]:
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("manifest must have mode 0600")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != REQUIRED_MANIFEST_FIELDS:
        raise ValueError("manifest fields are invalid")
    if any(
        part in str(key).replace("_", "").lower()
        for key in payload
        for part in FORBIDDEN_PARTS
    ):
        raise ValueError("manifest must not contain credentials")
    if payload.get("schemaVersion") != 1:
        raise ValueError("unsupported manifest schema")
    timeout = payload.get("stepTimeoutSeconds")
    if not isinstance(timeout, int) or timeout <= 0 or timeout > 120:
        raise ValueError("step timeout must be within 1..120 seconds")
    return payload


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"completedStages": [], "resources": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("checkpoint is invalid")
    completed = payload.get("completedStages", [])
    if not isinstance(completed, list) or any(
        stage not in STAGES for stage in completed
    ):
        raise ValueError("checkpoint stages are invalid")
    resources = payload.get("resources", [])
    if not isinstance(resources, list):
        raise ValueError("checkpoint resources are invalid")
    return {"completedStages": list(completed), "resources": list(resources)}


def _save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(checkpoint, sort_keys=True), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _driver(driver: Path, request: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        [str(driver)],
        input=json.dumps(request),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError("live driver failed")
    response = json.loads(completed.stdout)
    if not isinstance(response, dict):
        raise RuntimeError("live driver returned an invalid response")
    return response


def _cleanup(
    driver: Path, manifest: dict[str, Any], checkpoint: dict[str, Any]
) -> list[dict[str, Any]]:
    timeout = int(manifest["stepTimeoutSeconds"])
    for resource in reversed(checkpoint["resources"]):
        try:
            _driver(
                driver,
                {"command": "delete_resource", "resource": resource},
                timeout=timeout,
            )
        except Exception:
            pass
    response = _driver(
        driver,
        {
            "command": "list_resources",
            "resourcePrefix": manifest["resourcePrefix"],
        },
        timeout=timeout,
    )
    residue = response.get("resources", [])
    return residue if isinstance(residue, list) else [{"error": "invalid_list"}]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--driver", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stop-after", choices=STAGES)
    args = parser.parse_args()
    try:
        manifest = _load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError):
        _emit({"status": "invalid_manifest", "errorCode": "manifest_invalid"})
        return 2
    if args.dry_run == args.execute:
        _emit({"status": "invalid_arguments", "errorCode": "choose_one_mode"})
        return 2
    if args.dry_run:
        _emit({"mode": "dry-run", "stages": list(STAGES), "status": "planned"})
        return 0
    if os.environ.get("VEADK_MPA_P0_LIVE") != "1":
        _emit(
            {
                "status": "blocked",
                "errorCode": "live_execution_not_authorized",
            }
        )
        return 4
    if args.driver is None or not args.driver.is_file():
        _emit({"status": "blocked", "errorCode": "live_driver_required"})
        return 4

    checkpoint_path = args.checkpoint or args.manifest.with_suffix(".checkpoint.json")
    checkpoint = _load_checkpoint(checkpoint_path)
    interrupted = False
    failure: str | None = None
    residue: list[dict[str, Any]] = []
    try:
        for stage in STAGES:
            if stage in checkpoint["completedStages"]:
                continue
            response = _driver(
                args.driver,
                {"command": "run_stage", "stage": stage, "manifest": manifest},
                timeout=int(manifest["stepTimeoutSeconds"]),
            )
            if response.get("status") != "passed":
                raise RuntimeError(f"stage {stage} failed")
            resources = response.get("resources", [])
            if isinstance(resources, list):
                checkpoint["resources"].extend(resources)
            checkpoint["completedStages"].append(stage)
            _save_checkpoint(checkpoint_path, checkpoint)
            if args.stop_after == stage:
                interrupted = True
                break
    except Exception as error:
        failure = type(error).__name__
    finally:
        try:
            residue = _cleanup(args.driver, manifest, checkpoint)
        except Exception:
            residue = [{"error": "cleanup_verification_failed"}]
        checkpoint["resources"] = []
        _save_checkpoint(checkpoint_path, checkpoint)

    if interrupted:
        _emit({"status": "interrupted", "residue": residue})
        return 75 if not residue else 5
    if failure is not None or residue:
        _emit(
            {
                "status": "failed",
                "errorCode": failure or "cleanup_residue",
                "residue": residue,
            }
        )
        return 5
    _emit({"status": "passed", "residue": []})
    return 0


if __name__ == "__main__":
    sys.exit(main())
