#!/usr/bin/env python3
"""Smoke-test Studio backend validation/error surfacing paths."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from studio_shared_workflows import (
    SmokeError,
    StepLogger,
    StudioClient,
    build_basic_draft,
    deep_get,
    default_config_path,
    dry_summary,
    generate_project_for_winner,
    load_config,
    print_json,
    validate_config,
    verify_studio_ready,
)


DEFAULT_CONFIG = default_config_path(__file__, "error_surface.local.yaml")


def assert_error(response_status: int, response_text: str, expected_statuses: set[int], expected_text: str, label: str) -> dict[str, Any]:
    if response_status not in expected_statuses:
        raise SmokeError(f"{label}: expected {sorted(expected_statuses)} but got {response_status}: {response_text}")
    if expected_text and expected_text.lower() not in response_text.lower():
        raise SmokeError(f"{label}: expected error text {expected_text!r}: {response_text}")
    return {"status": response_status, "body": response_text[:1000]}


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    draft = build_basic_draft(config, "studio-e2e-errors")
    if dry_run:
        return dry_summary("error surface", {"agentName": draft["name"]})
    log = StepLogger()
    client = StudioClient(config)
    verify_studio_ready(client, log)

    log.step("Submit invalid custom-agent draft", "POST /web/generated-agent-projects")
    invalid_draft = dict(draft)
    invalid_draft["shortTermBackend"] = "not-a-backend"
    invalid_draft["memory"] = {"shortTerm": True, "longTerm": False}
    response = client.request(
        "POST",
        "/web/generated-agent-projects",
        {"draft": invalid_draft},
        allow_statuses={400, 422},
    )
    draft_error = assert_error(
        response.status,
        response.text(),
        {400, 422},
        str(deep_get(config, "error.expected_draft_error_contains", "shortTermBackend") or ""),
        "invalid draft",
    )

    log.step("Submit invalid deploy options", "POST /web/deploy-agentkit")
    project = generate_project_for_winner(client, log, "error-surface", draft)
    deploy = config.get("deploy") or {}
    response = client.request(
        "POST",
        "/web/deploy-agentkit",
        {
            "name": project["name"],
            "files": project["files"],
            "config": {
                "region": str(deploy.get("region") or "cn-beijing"),
                "projectName": str(deploy.get("project_name") or "default"),
            },
            "taskId": "studio-e2e-invalid-deploy",
            "minInstance": 3,
            "maxInstance": 1,
        },
        allow_statuses={400, 409, 422},
    )
    deploy_error = assert_error(
        response.status,
        response.text(),
        {400, 409, 422},
        str(deep_get(config, "error.expected_deploy_error_contains", "minInstance") or ""),
        "invalid deploy",
    )
    return {"success": True, "draftError": draft_error, "deployError": deploy_error}


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
