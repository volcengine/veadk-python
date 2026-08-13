#!/usr/bin/env python3
"""Smoke-test Studio short-term and long-term memory workflows."""

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
    assert_generated_contains,
    build_basic_draft,
    chat_with_deployed_agent,
    create_debug_run,
    deep_get,
    default_config_path,
    delete_debug_runs,
    deploy_connect_chat,
    dry_summary,
    generate_project_for_winner,
    load_config,
    print_json,
    require_component,
    require_search_source,
    runtime_proxy_path,
    truthy,
    validate_config,
    verify_studio_ready,
)


DEFAULT_CONFIG = default_config_path(__file__, "memory_workflows.local.yaml")


def apply_memory_config(config: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    memory = deep_get(config, "memory", {}) or {}
    mode = str(memory.get("mode") or "both").strip().lower()
    if mode not in {"short_term", "long_term", "both"}:
        raise SmokeError("memory.mode must be short_term, long_term, or both.")
    short_enabled = mode in {"short_term", "both"}
    long_enabled = mode in {"long_term", "both"}
    draft["memory"] = {"shortTerm": short_enabled, "longTerm": long_enabled}
    draft["shortTermBackend"] = str(memory.get("short_term_backend") or "local")
    draft["longTermBackend"] = str(memory.get("long_term_backend") or "local")
    draft["autoSaveSession"] = truthy(memory.get("auto_save_session"), default=True)
    return draft


def verify_generated_memory(project: dict[str, Any], draft: dict[str, Any]) -> None:
    expected = []
    if draft["memory"]["shortTerm"]:
        expected.extend(["ShortTermMemory", f'backend="{draft["shortTermBackend"]}"'])
    if draft["memory"]["longTerm"]:
        expected.extend(["LongTermMemory", f'backend="{draft["longTermBackend"]}"'])
        if draft.get("autoSaveSession"):
            expected.append("auto_save_session=True")
    assert_generated_contains(project, expected, "memory workflow")


def verify_runtime_memory(
    client: StudioClient,
    config: dict[str, Any],
    deployed: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any]:
    del client
    info = deployed["agentInfo"]
    checks: dict[str, Any] = {}
    if draft["memory"]["shortTerm"]:
        checks["shortTerm"] = require_component(
            info,
            "memory",
            source="short_term_memory",
            backend=str(draft["shortTermBackend"]),
        )
    if draft["memory"]["longTerm"]:
        checks["longTerm"] = require_component(
            info,
            "memory",
            source="long_term_memory",
            backend=str(draft["longTermBackend"]),
        )
        require_search_source(info, "memory")
    return checks


def optionally_query_memory_search(
    client: StudioClient,
    config: dict[str, Any],
    deployed: dict[str, Any],
) -> Any:
    if not truthy(deep_get(config, "memory.verify_search"), default=True):
        return None
    query = str(deep_get(config, "memory.search_query", deep_get(config, "chat.message", "memory")) or "memory")
    return client.json_request(
        "GET",
        runtime_proxy_path(
            deployed["runtimeId"],
            deployed["region"],
            f"/web/search?source=memory&q={urllib.parse.quote(query, safe='')}",
        ),
    )


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    log = StepLogger()
    draft = apply_memory_config(config, build_basic_draft(config, "studio-e2e-memory"))
    if dry_run:
        return dry_summary(
            "memory workflow",
            {
                "agentName": draft["name"],
                "memory": draft["memory"],
                "shortTermBackend": draft["shortTermBackend"],
                "longTermBackend": draft["longTermBackend"],
            },
        )

    client = StudioClient(config)
    debug_runs: list[dict[str, Any]] = []
    try:
        verify_studio_ready(client, log)
        if truthy(deep_get(config, "debug.enabled"), default=True):
            debug_user = str(deep_get(config, "debug.user_id", "studio_e2e_memory_user"))
            run = create_debug_run(client, log, "memory", draft, debug_user)
            debug_runs.append(run)
        project = generate_project_for_winner(client, log, "memory", draft)
        verify_generated_memory(project, draft)
        result = deploy_connect_chat(client, log, config, project)
        memory_checks = verify_runtime_memory(client, config, result["deployed"], draft)
        search = None
        if draft["memory"]["longTerm"]:
            search = optionally_query_memory_search(client, config, result["deployed"])
        return {
            "success": True,
            "agentName": draft["name"],
            "deployment": result["final"],
            "memoryChecks": memory_checks,
            "memorySearch": search,
            "chat": result["chat"],
        }
    finally:
        if debug_runs and truthy(deep_get(config, "cleanup.delete_debug_runs"), default=True):
            delete_debug_runs(client, log, debug_runs)


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
