#!/usr/bin/env python3
"""Run a configured suite of Studio E2E smoke workflows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from studio_shared_workflows import SmokeError, default_config_path, load_config, print_json, truthy


DEFAULT_CONFIG = default_config_path(__file__, "run_all.local.yaml")


def run_workflow_entry(
    entry: dict[str, Any],
    *,
    dry_run: bool,
    default_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    script = Path(str(entry.get("script") or "")).expanduser()
    if not script.is_absolute():
        script = Path(__file__).resolve().parent / script
    config = Path(str(entry.get("config") or "")).expanduser()
    if not config.is_absolute():
        config = Path(__file__).resolve().parents[1] / "configs" / config
    command = [sys.executable, str(script), "--config", str(config)]
    if dry_run or truthy(entry.get("dry_run")):
        command.append("--dry-run")
    timeout_value = entry.get("timeout_seconds")
    timeout_seconds = (
        float(timeout_value)
        if timeout_value not in {None, ""}
        else default_timeout_seconds
    )
    result = {
        "name": str(entry.get("name") or script.stem),
        "script": str(script),
        "config": str(config),
        "returncode": 0,
        "stdoutTail": "",
        "stderrTail": "",
        "timedOut": False,
    }
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
        result.update(
            {
                "returncode": 124,
                "stdoutTail": stdout[-6000:],
                "stderrTail": (stderr + f"\nTimed out after {timeout_seconds} seconds.")[-6000:],
                "timedOut": True,
            }
        )
        return result
    result.update(
        {
            "returncode": completed.returncode,
            "stdoutTail": completed.stdout[-6000:],
            "stderrTail": completed.stderr[-6000:],
        }
    )
    return result


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    entries = [item for item in (config.get("workflows") or []) if isinstance(item, dict)]
    enabled = [item for item in entries if truthy(item.get("enabled"), default=True)]
    if not enabled:
        raise SmokeError("No enabled workflows in suite config.")
    timeout_value = config.get("timeout_seconds")
    default_timeout_seconds = (
        float(timeout_value) if timeout_value not in {None, ""} else None
    )
    results = [
        run_workflow_entry(
            entry,
            dry_run=dry_run,
            default_timeout_seconds=default_timeout_seconds,
        )
        for entry in enabled
    ]
    failed = [item for item in results if item["returncode"] != 0]
    return {"success": not failed, "failed": failed, "results": results}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = run_workflow(load_config(Path(args.config).expanduser().resolve()), dry_run=args.dry_run)
    print("\n=== Summary ===")
    print_json("result", result)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SmokeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
