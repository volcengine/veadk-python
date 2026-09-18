"""Checkpointed MPA P0 live runner with mandatory resource cleanup."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


_SAFE_ERROR_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,127}$")
_RETRYABLE_DRIVER_ERROR_CODES = {"NetworkError"}


class LiveDriverError(RuntimeError):
    """A credential-free failure returned by the isolated live driver."""

    def __init__(self, error_code: str = "live_driver_failed") -> None:
        super().__init__(error_code)
        self.error_code = error_code


DEFAULT_STAGES = ("AC-11", "AC-1", "AC-2", "AC-6", "AC-9")
CASE_STAGES = {
    "VC-21": (
        "VC21-COMPATIBILITY-FENCE",
        "VC21-RUNTIME-PROVISION",
        "VC21-VALID-UPDATE",
        "VC21-FAILURE-RECOVERY",
        "VC21-COMPATIBLE-ROLLBACK",
        "VC21-DELETE-ACTIVE-OPERATION",
        "VC21-DELETE-ACTIVE-SESSION",
        "VC21-DELETE-IDLE-SESSIONS",
        "VC21-FINAL-DELETE",
    )
}
ALL_STAGES = tuple(
    dict.fromkeys(
        (
            *DEFAULT_STAGES,
            *(stage for stages in CASE_STAGES.values() for stage in stages),
        )
    )
)
REQUIRED_MANIFEST_FIELDS = {
    "schemaVersion",
    "runId",
    "resourcePrefix",
    "provider",
    "region",
    "project",
    "runtimeImageUrl",
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
    image_url = payload.get("runtimeImageUrl")
    if (
        not isinstance(image_url, str)
        or not image_url.strip()
        or "@" in image_url
        or "://" in image_url
    ):
        raise ValueError(
            "runtime image URL must be a credential-free registry reference"
        )
    timeout = payload.get("stepTimeoutSeconds")
    if not isinstance(timeout, int) or timeout <= 0 or timeout > 120:
        raise ValueError("step timeout must be within 1..120 seconds")
    return payload


def _load_checkpoint(path: Path, stages: tuple[str, ...]) -> dict[str, Any]:
    if not path.exists():
        return {"completedStages": [], "resources": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("checkpoint is invalid")
    completed = payload.get("completedStages", [])
    if not isinstance(completed, list) or any(
        stage not in stages for stage in completed
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
    command = [sys.executable, str(driver)] if driver.suffix == ".py" else [str(driver)]
    completed = subprocess.run(
        command,
        input=json.dumps(request),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        error_code = "live_driver_failed"
        try:
            failure = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError):
            failure = None
        if isinstance(failure, dict):
            candidate = failure.get("safeErrorCode") or failure.get("errorCode")
            if isinstance(candidate, str) and _SAFE_ERROR_CODE.fullmatch(candidate):
                error_code = candidate
        raise LiveDriverError(error_code)
    response = json.loads(completed.stdout)
    if not isinstance(response, dict):
        raise RuntimeError("live driver returned an invalid response")
    return response


def _cleanup(
    driver: Path, manifest: dict[str, Any], checkpoint: dict[str, Any]
) -> list[dict[str, Any]]:
    timeout = int(manifest["stepTimeoutSeconds"])
    cleanup_timeout = int(os.environ.get("VEADK_MPA_P0_CLEANUP_TIMEOUT_SECONDS", "300"))

    def delete(resource: dict[str, Any]) -> None:
        try:
            _driver(
                driver,
                {"command": "delete_resource", "resource": resource},
                timeout=timeout,
            )
        except Exception:
            pass

    for resource in reversed(checkpoint["resources"]):
        if isinstance(resource, dict):
            delete(resource)
    deadline = time.monotonic() + max(1, cleanup_timeout)
    while True:
        response = _driver(
            driver,
            {
                "command": "list_resources",
                "resourcePrefix": manifest["resourcePrefix"],
            },
            timeout=timeout,
        )
        residue = response.get("resources", [])
        if not isinstance(residue, list):
            return [{"error": "invalid_list"}]
        if not residue or time.monotonic() >= deadline:
            return residue
        for resource in reversed(residue):
            if isinstance(resource, dict):
                delete(resource)
        time.sleep(min(5, max(0, deadline - time.monotonic())))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--driver", type=Path)
    parser.add_argument("--case")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stop-after", choices=ALL_STAGES)
    args = parser.parse_args()
    if args.case is not None and args.case not in CASE_STAGES:
        _emit(
            {
                "case": args.case,
                "status": "invalid_arguments",
                "errorCode": "unsupported_case",
            }
        )
        return 2
    stages = CASE_STAGES.get(args.case, DEFAULT_STAGES)
    try:
        manifest = _load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError):
        _emit({"status": "invalid_manifest", "errorCode": "manifest_invalid"})
        return 2
    if args.dry_run == args.execute:
        _emit({"status": "invalid_arguments", "errorCode": "choose_one_mode"})
        return 2
    if args.dry_run:
        report: dict[str, Any] = {
            "mode": "dry-run",
            "stages": list(stages),
            "status": "planned",
        }
        if args.case is not None:
            report["case"] = args.case
        _emit(report)
        return 0
    if os.environ.get("VEADK_MPA_P0_LIVE") != "1":
        _emit(
            {
                "status": "blocked",
                "errorCode": "live_execution_not_authorized",
            }
        )
        return 4
    if args.driver is None and args.case == "VC-21":
        args.driver = Path(__file__).with_name("mpa_p0_vc21_driver.py")
    if args.driver is None or not args.driver.is_file():
        _emit({"status": "blocked", "errorCode": "live_driver_required"})
        return 4

    checkpoint_path = args.checkpoint or args.manifest.with_suffix(".checkpoint.json")
    checkpoint = _load_checkpoint(checkpoint_path, stages)
    interrupted = False
    failure: str | None = None
    failed_stage: str | None = None
    residue: list[dict[str, Any]] = []
    try:
        for stage in stages:
            if stage in checkpoint["completedStages"]:
                continue
            asynchronous_timeout = int(
                os.environ.get(
                    "VEADK_MPA_P0_ASYNC_STAGE_TIMEOUT_SECONDS",
                    "900"
                    if args.case == "VC-21"
                    else str(manifest["stepTimeoutSeconds"]),
                )
            )
            deadline = time.monotonic() + asynchronous_timeout
            while True:
                try:
                    response = _driver(
                        args.driver,
                        {
                            "command": "run_stage",
                            "stage": stage,
                            "manifest": manifest,
                        },
                        timeout=max(1, int(deadline - time.monotonic())),
                    )
                except LiveDriverError as error:
                    if (
                        error.error_code in _RETRYABLE_DRIVER_ERROR_CODES
                        and time.monotonic() < deadline
                    ):
                        time.sleep(min(5, max(0, deadline - time.monotonic())))
                        continue
                    raise
                resources = response.get("resources", [])
                if not isinstance(resources, list):
                    raise RuntimeError(f"stage {stage} returned invalid resources")
                existing_resources = {
                    json.dumps(item, sort_keys=True, separators=(",", ":"))
                    for item in checkpoint["resources"]
                }
                for resource in resources:
                    identity = json.dumps(
                        resource, sort_keys=True, separators=(",", ":")
                    )
                    if identity not in existing_resources:
                        checkpoint["resources"].append(resource)
                        existing_resources.add(identity)
                _save_checkpoint(checkpoint_path, checkpoint)
                status = response.get("status")
                if status == "passed":
                    break
                if status != "pending" or time.monotonic() >= deadline:
                    raise RuntimeError(f"stage {stage} failed")
                retry_after = response.get("retryAfterSeconds", 1)
                if not isinstance(retry_after, (int, float)) or retry_after < 0:
                    raise RuntimeError(f"stage {stage} returned invalid retry delay")
                time.sleep(min(float(retry_after), max(0, deadline - time.monotonic())))
            checkpoint["completedStages"].append(stage)
            _save_checkpoint(checkpoint_path, checkpoint)
            if args.stop_after == stage:
                interrupted = True
                break
    except Exception as error:
        failure = (
            error.error_code
            if isinstance(error, LiveDriverError)
            else type(error).__name__
        )
        failed_stage = stage
    finally:
        try:
            residue = _cleanup(args.driver, manifest, checkpoint)
        except Exception:
            residue = [{"error": "cleanup_verification_failed"}]
        checkpoint["resources"] = []
        _save_checkpoint(checkpoint_path, checkpoint)

    report_base = {"case": args.case} if args.case is not None else {}

    if interrupted:
        _emit({**report_base, "status": "interrupted", "residue": residue})
        return 75 if not residue else 5
    if failure is not None or residue:
        report = {
            **report_base,
            "status": "failed",
            "errorCode": failure or "cleanup_residue",
            "residue": residue,
        }
        if failed_stage is not None:
            report["failedStage"] = failed_stage
        _emit(report)
        return 5
    _emit({**report_base, "status": "passed", "residue": []})
    return 0


if __name__ == "__main__":
    sys.exit(main())
