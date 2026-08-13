#!/usr/bin/env python3
"""Smoke-test opening and chatting with an existing AgentKit Runtime."""

from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from studio_shared_workflows import (
    SmokeError,
    StepLogger,
    StudioClient,
    chat_with_deployed_agent,
    choose_runtime,
    deep_get,
    default_config_path,
    dry_summary,
    load_config,
    print_json,
    request_with_retries,
    runtime_proxy_path,
    validate_config,
    verify_studio_ready,
)


DEFAULT_CONFIG = default_config_path(__file__, "existing_runtime_connect.local.yaml")


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    runtime_hint = deep_get(config, "runtime", {}) or {}
    if dry_run:
        return dry_summary("existing runtime", {"runtime": runtime_hint})
    log = StepLogger()
    client = StudioClient(config)
    verify_studio_ready(client, log)
    runtime = choose_runtime(config, client, log)
    runtime_id = runtime["runtimeId"]
    region = runtime["region"]
    apps = request_with_retries(client, "GET", runtime_proxy_path(runtime_id, region, "/list-apps"))
    if not isinstance(apps, list) or not apps:
        raise SmokeError(f"Runtime returned no apps: {apps}")
    app = runtime["app"] if runtime.get("app") in apps else str(apps[0])
    info = request_with_retries(
        client,
        "GET",
        runtime_proxy_path(runtime_id, region, f"/web/agent-info/{urllib.parse.quote(app, safe='')}"),
    )
    if not isinstance(info, dict) or not info.get("name"):
        raise SmokeError(f"Invalid agent-info payload: {info}")
    chat = chat_with_deployed_agent(
        client,
        log,
        config,
        {"runtimeId": runtime_id, "region": region, "app": app},
    )
    return {
        "success": True,
        "runtimeId": runtime_id,
        "region": region,
        "app": app,
        "detail": runtime["detail"],
        "agentInfo": info,
        "chat": chat,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = run_workflow(load_config(Path(args.config).expanduser().resolve()), dry_run=args.dry_run)
    print("\n=== Summary ===")
    print_json("result", result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SmokeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
