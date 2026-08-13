#!/usr/bin/env python3
"""Smoke-test Studio multi-agent / workflow agent creation."""

from __future__ import annotations

import argparse
import copy
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
    truthy,
    validate_config,
    verify_studio_ready,
)


DEFAULT_CONFIG = default_config_path(__file__, "multi_agent_workflow.local.yaml")


def child_draft(config: dict[str, Any], base: dict[str, Any], index: int, raw: dict[str, Any]) -> dict[str, Any]:
    child = copy.deepcopy(base)
    child["name"] = str(raw.get("name") or f"{base['name']}_child_{index}")
    child["description"] = str(raw.get("description") or f"Workflow child agent {index}.")
    child["instruction"] = str(raw.get("instruction") or "Handle your assigned part and answer concisely.")
    child["agentType"] = "llm"
    child["subAgents"] = []
    if raw.get("model_name") is not None:
        child["modelName"] = str(raw.get("model_name") or "")
    return child


def apply_workflow_config(config: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    workflow = deep_get(config, "workflow", {}) or {}
    workflow_type = str(workflow.get("type") or "sequential").strip().lower()
    if workflow_type not in {"sequential", "parallel", "loop"}:
        raise SmokeError("workflow.type must be sequential, parallel, or loop.")
    raw_children = [item for item in as_list(workflow.get("sub_agents")) if isinstance(item, dict)]
    if not raw_children:
        raw_children = [
            {"name": f"{draft['name']}_researcher", "instruction": "Extract useful facts."},
            {"name": f"{draft['name']}_writer", "instruction": "Write the final concise answer."},
        ]
    children = [child_draft(config, draft, idx + 1, raw) for idx, raw in enumerate(raw_children)]
    draft["agentType"] = workflow_type
    draft["subAgents"] = children
    if workflow_type == "loop":
        draft["maxIterations"] = int(workflow.get("max_iterations") or 3)
    draft["workflow"] = {
        "type": workflow_type,
        "nodes": [{"id": child["name"], "agent": child} for child in children],
        "edges": [
            {"from": children[idx]["name"], "to": children[idx + 1]["name"]}
            for idx in range(max(0, len(children) - 1))
        ],
    }
    return draft


def verify_runtime_graph(deployed: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    info = deployed["agentInfo"]
    graph = info.get("graph")
    if not isinstance(graph, dict):
        raise SmokeError(f"agent-info graph missing: {info}")
    children = graph.get("children")
    if not isinstance(children, list) or len(children) < len(draft["subAgents"]):
        raise SmokeError(f"workflow graph missing child agents: {graph}")
    if str(graph.get("type") or "") != draft["agentType"]:
        raise SmokeError(f"workflow graph type mismatch: {graph}")
    return {"type": graph.get("type"), "childCount": len(children), "subAgents": info.get("subAgents")}


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    log = StepLogger()
    draft = apply_workflow_config(config, build_basic_draft(config, "studio-e2e-flow"))
    if dry_run:
        return dry_summary(
            "multi-agent workflow",
            {
                "agentName": draft["name"],
                "type": draft["agentType"],
                "subAgents": [item["name"] for item in draft["subAgents"]],
            },
        )
    client = StudioClient(config)
    verify_studio_ready(client, log)
    project = generate_project_for_winner(client, log, "workflow", draft)
    expected_class = {
        "sequential": "SequentialAgent",
        "parallel": "ParallelAgent",
        "loop": "LoopAgent",
    }[draft["agentType"]]
    assert_generated_contains(project, [expected_class, "sub_agents=["], "multi-agent workflow")
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
        "graph": verify_runtime_graph(result["deployed"], draft),
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
