#!/usr/bin/env python3
"""Smoke-test Studio RBAC backend enforcement."""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

from studio_shared_workflows import (
    SmokeError,
    StudioClient,
    build_basic_draft,
    deep_get,
    default_config_path,
    dry_summary,
    load_config,
    print_json,
)


DEFAULT_CONFIG = default_config_path(__file__, "rbac.local.yaml")


def profile_config(base: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    studio = cfg.setdefault("studio", {})
    if "auth" in profile:
        studio["auth"] = profile["auth"]
    return cfg


def expect_status(label: str, status: int, allowed: set[int], body: str) -> None:
    if status not in allowed:
        raise SmokeError(f"{label}: expected status {sorted(allowed)} but got {status}: {body[:500]}")


def test_profile(base: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    cfg = profile_config(base, profile)
    client = StudioClient(cfg)
    name = str(profile.get("name") or "profile")
    access = client.request("GET", "/web/access", allow_statuses={401, 403})
    expected_access = int(profile.get("expected_access_status") or 200)
    expect_status(f"{name} access", access.status, {expected_access}, access.text())
    access_json = access.json() if access.status == 200 else None

    expected_create = bool(profile.get("expect_create_agents"))
    draft = build_basic_draft(cfg, f"studio-e2e-rbac-{name}")
    create = client.request(
        "POST",
        "/web/generated-agent-projects",
        {"draft": draft},
        allow_statuses={401, 403},
    )
    expect_status(
        f"{name} create enforcement",
        create.status,
        {200} if expected_create else {401, 403},
        create.text(),
    )

    expected_manage = bool(profile.get("expect_manage_agents"))
    manage = client.request(
        "POST",
        "/web/delete-runtime",
        {},
        allow_statuses={400, 401, 403},
    )
    expect_status(
        f"{name} manage enforcement",
        manage.status,
        {400} if expected_manage else {401, 403},
        manage.text(),
    )
    return {
        "name": name,
        "accessStatus": access.status,
        "access": access_json,
        "createStatus": create.status,
        "manageStatus": manage.status,
    }


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    profiles = [item for item in (config.get("profiles") or []) if isinstance(item, dict)]
    if not profiles:
        raise SmokeError("profiles must contain at least one auth profile.")
    if dry_run:
        return dry_summary("rbac", {"profiles": [item.get("name") for item in profiles]})
    return {"success": True, "profiles": [test_profile(config, profile) for profile in profiles]}


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
