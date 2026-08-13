#!/usr/bin/env python3
"""Smoke-test Studio deploy-page runtime options."""

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
    deploy_connect_chat,
    dry_summary,
    generate_project_for_winner,
    load_config,
    print_json,
    runtime_detail,
    truthy,
    validate_config,
    verify_studio_ready,
)


DEFAULT_CONFIG = default_config_path(__file__, "runtime_options.local.yaml")


def verify_options(config: dict[str, Any], final: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    deploy = config.get("deploy") or {}
    resources = detail.get("resources") if isinstance(detail.get("resources"), dict) else {}
    expected_min = deploy.get("min_instance")
    expected_max = deploy.get("max_instance")
    if expected_min is not None and resources.get("minInstance") != int(expected_min):
        raise SmokeError(f"minInstance mismatch: {resources}")
    if expected_max is not None and resources.get("maxInstance") != int(expected_max):
        raise SmokeError(f"maxInstance mismatch: {resources}")

    network = deep_get(config, "deploy.network", {}) or {}
    mode = str(network.get("mode") or "public").lower()
    network_types = detail.get("networkTypes") or []
    if mode in {"private", "both"} and not network_types:
        raise SmokeError(f"Expected private/both network config in runtime detail: {detail}")

    feishu_expected = truthy(deep_get(config, "deploy.im.feishu.enabled"))
    feishu_channel = final.get("feishuChannel")
    if feishu_expected and not (isinstance(feishu_channel, dict) and feishu_channel.get("enabled")):
        raise SmokeError(f"Feishu was enabled but deploy result did not report a channel: {final}")

    return {
        "resources": resources,
        "networkTypes": network_types,
        "feishuChannel": feishu_channel,
        "sessionStorage": deploy.get("session_storage") or "persistent",
    }


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    draft = build_basic_draft(config, "studio-e2e-options")
    if dry_run:
        return dry_summary(
            "runtime options",
            {
                "agentName": draft["name"],
                "deploy": config.get("deploy") or {},
            },
        )
    log = StepLogger()
    client = StudioClient(config)
    verify_studio_ready(client, log)
    project = generate_project_for_winner(client, log, "runtime-options", draft)
    result = deploy_connect_chat(
        client,
        log,
        config,
        project,
        chat=truthy(deep_get(config, "chat.enabled"), default=True),
    )
    final = result["final"]
    detail = runtime_detail(
        client,
        str(final["runtimeId"]),
        str(final.get("region") or deep_get(config, "deploy.region", "cn-beijing")),
    )
    return {
        "success": True,
        "agentName": draft["name"],
        "deployment": final,
        "optionChecks": verify_options(config, final, detail),
        "chat": result["chat"],
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
