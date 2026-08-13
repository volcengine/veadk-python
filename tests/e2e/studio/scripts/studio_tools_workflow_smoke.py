#!/usr/bin/env python3
"""Smoke-test Studio tool selection workflows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from studio_shared_workflows import (
    SmokeError,
    StepLogger,
    StudioClient,
    as_list,
    assert_generated_contains,
    build_basic_draft,
    deep_get,
    default_config_path,
    deploy_connect_chat,
    dry_summary,
    generate_project_for_winner,
    load_config,
    print_json,
    require_component,
    truthy,
    validate_config,
    verify_studio_ready,
)


DEFAULT_CONFIG = default_config_path(__file__, "tools_workflow.local.yaml")


def apply_tools_config(config: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    tools = deep_get(config, "tools", {}) or {}
    draft["builtinTools"] = [str(item) for item in as_list(tools.get("builtin")) if str(item).strip()]
    draft["tools"] = [str(item) for item in as_list(tools.get("legacy")) if str(item).strip()]
    draft["customTools"] = [item for item in as_list(tools.get("custom")) if isinstance(item, dict)]
    draft["mcpTools"] = [item for item in as_list(tools.get("mcp")) if isinstance(item, dict)]
    return draft


def verify_generated_tools(project: dict[str, Any], draft: dict[str, Any]) -> None:
    expected: list[str] = []
    for tool_id in draft.get("builtinTools") or []:
        expected.append(str(tool_id))
    for tool in draft.get("customTools") or []:
        expected.append(str(tool.get("name") or ""))
    for tool in draft.get("mcpTools") or []:
        if str(tool.get("transport") or "") == "http":
            expected.append("StreamableHTTPConnectionParams")
        if str(tool.get("transport") or "") == "stdio":
            expected.append("StdioConnectionParams")
        expected.append(str(tool.get("name") or ""))
    assert_generated_contains(project, [item for item in expected if item], "tools workflow")


def verify_runtime_tools(deployed: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    info = deployed["agentInfo"]
    expected_labels = set()
    expected_labels.update(str(item) for item in draft.get("builtinTools") or [])
    expected_labels.update(str(item.get("name") or "") for item in draft.get("customTools") or [])
    tools = {str(item) for item in info.get("tools") or []}
    missing = [item for item in expected_labels if item and item not in tools]
    if missing:
        raise SmokeError(f"Runtime agent-info missing expected tools {missing}: {sorted(tools)}")
    mcp_component = None
    if draft.get("mcpTools"):
        mcp_component = require_component(info, "toolset")
    return {
        "tools": sorted(tools),
        "expectedLabels": sorted(expected_labels),
        "missingRuntimeLabels": missing,
        "mcpComponent": mcp_component,
    }


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    log = StepLogger()
    draft = apply_tools_config(config, build_basic_draft(config, "studio-e2e-tools"))
    if dry_run:
        return dry_summary(
            "tools workflow",
            {
                "agentName": draft["name"],
                "builtinTools": draft.get("builtinTools"),
                "customTools": draft.get("customTools"),
                "mcpTools": draft.get("mcpTools"),
            },
        )
    client = StudioClient(config)
    verify_studio_ready(client, log)
    project = generate_project_for_winner(client, log, "tools", draft)
    verify_generated_tools(project, draft)
    result = deploy_connect_chat(
        client,
        log,
        config,
        project,
        chat=truthy(deep_get(config, "chat.enabled"), default=True),
    )
    return {
        "success": True,
        "agentName": draft["name"],
        "deployment": result["final"],
        "toolChecks": verify_runtime_tools(result["deployed"], draft),
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
