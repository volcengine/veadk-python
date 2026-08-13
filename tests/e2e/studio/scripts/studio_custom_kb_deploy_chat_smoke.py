#!/usr/bin/env python3
"""Smoke-test Studio custom agent with Knowledge Base -> debug -> deploy -> chat.

This follows the UI workflow:

1. User opens Studio and chooses 智能体 -> 添加智能体 -> 从0快速创建 -> 自定义.
2. User enables 知识库, chooses backend/index/options, and starts debug.
3. User deploys the KB-backed agent.
4. Studio verifies the deployed Runtime really has a mounted knowledgebase.
5. User searches/chat-tests the deployed agent through Studio runtime proxy.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from studio_custom_ab_deploy_chat_smoke import (  # noqa: E402
    SmokeError,
    StepLogger,
    StudioClient,
    assert_contains,
    build_agent_draft,
    chat_with_deployed_agent,
    connect_deployed_agent,
    create_debug_run,
    deep_get,
    delete_debug_runs,
    delete_runtime,
    deploy_project,
    generate_project_for_winner,
    load_config,
    print_json,
    run_debug_message,
    runtime_proxy_path,
    truthy,
    validate_config as validate_common_config,
    verify_studio_ready,
)


DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "custom_kb_deploy_chat.local.yaml"
)


def validate_config(config: dict[str, Any]) -> None:
    validate_common_config(config)
    errors: list[str] = []
    if not truthy(deep_get(config, "agent.knowledgebase.enabled")):
        errors.append("agent.knowledgebase.enabled must be true.")
    backend = str(deep_get(config, "agent.knowledgebase.backend", "viking") or "viking")
    if backend not in {"viking", "opensearch", "context_search"}:
        errors.append("agent.knowledgebase.backend must be viking, opensearch, or context_search.")
    if errors:
        raise SmokeError("Invalid config:\n- " + "\n- ".join(errors))


def verify_managed_kb_selection(
    client: StudioClient, log: StepLogger, config: dict[str, Any]
) -> str | None:
    backend = str(deep_get(config, "agent.knowledgebase.backend", "viking") or "viking")
    if backend != "viking" or not truthy(
        deep_get(config, "agent.knowledgebase.verify_managed_list"), default=True
    ):
        return None
    log.step(
        "Open knowledge-base picker and list VikingDB knowledge bases",
        "GET /web/viking-knowledgebases",
    )
    region = str(deep_get(config, "deploy.region", "cn-beijing") or "cn-beijing")
    project = str(deep_get(config, "deploy.project_name", "default") or "default")
    query = urllib.parse.urlencode({"region": region, "project": project})
    payload = client.json_request("GET", f"/web/viking-knowledgebases?{query}")
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise SmokeError(f"Invalid VikingDB knowledgebase list response: {payload}")
    kb_index = str(deep_get(config, "agent.knowledgebase.index", "") or "").strip()
    if kb_index and truthy(deep_get(config, "agent.knowledgebase.require_index_in_list")):
        if not any(item.get("id") == kb_index or item.get("name") == kb_index for item in payload["items"]):
            raise SmokeError(f"Configured VikingDB knowledgebase not found: {kb_index}")
    selected_index = None
    if not kb_index and truthy(deep_get(config, "agent.knowledgebase.prefer_existing"), default=True):
        for item in payload["items"]:
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("id") or item.get("name") or "").strip()
            if candidate:
                selected_index = candidate
                break
    suffix = f"; selected existing index={selected_index}" if selected_index else ""
    log.ok(f"VikingDB knowledgebase list loaded; count={len(payload['items'])}{suffix}")
    return selected_index


def verify_generated_project_contains_kb(
    log: StepLogger, project: dict[str, Any], backend: str, index: str
) -> None:
    log.step(
        "Verify generated code contains knowledge-base wiring",
        "inspect /web/generated-agent-projects response files",
    )
    files = project.get("files") or []
    agent_files = [
        item
        for item in files
        if isinstance(item, dict) and str(item.get("path") or "").endswith("/agent.py")
    ]
    if not agent_files:
        raise SmokeError("Generated project has no agents/*/agent.py file.")
    content = "\n".join(str(item.get("content") or "") for item in agent_files)
    if "KnowledgeBase(" not in content or "knowledgebase=" not in content:
        raise SmokeError("Generated agent.py does not mount KnowledgeBase.")
    if backend and f'backend="{backend}"' not in content:
        raise SmokeError(f"Generated agent.py does not use backend={backend}.")
    if index and f'index="{index}"' not in content:
        raise SmokeError(f"Generated agent.py does not use knowledgebase index={index}.")
    log.ok("generated project includes KnowledgeBase import, instance, and Agent mount")


def verify_runtime_kb_mount(
    log: StepLogger, deployed: dict[str, Any], expected_backend: str
) -> list[dict[str, Any]]:
    log.step(
        "Verify deployed Runtime reports mounted knowledge base",
        "GET /web/runtime-proxy/{runtimeId}/web/agent-info/{app}",
    )
    info = deployed.get("agentInfo") or {}
    components = info.get("components") if isinstance(info, dict) else None
    if not isinstance(components, list):
        raise SmokeError(f"Agent info components invalid: {info}")
    kb_components = [
        item
        for item in components
        if isinstance(item, dict) and item.get("kind") == "knowledgebase"
    ]
    if not kb_components:
        raise SmokeError(f"Runtime agent-info does not report knowledgebase: {info}")
    if expected_backend and not any(item.get("backend") == expected_backend for item in kb_components):
        raise SmokeError(
            f"Runtime knowledgebase backend mismatch. expected={expected_backend}, components={kb_components}"
        )
    sources = info.get("searchSources") or []
    if "knowledge" not in sources:
        raise SmokeError(f"Runtime searchSources does not include knowledge: {info}")
    log.ok(f"knowledgebase mounted: {json.dumps(kb_components, ensure_ascii=False)}")
    return kb_components


def verify_knowledge_search(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    deployed: dict[str, Any],
) -> dict[str, Any] | None:
    if not truthy(deep_get(config, "knowledge_search.enabled"), default=True):
        return None
    log.step(
        "Use Studio search against the deployed knowledge source",
        "GET /web/runtime-proxy/{runtimeId}/web/search?source=knowledge",
    )
    query = str(deep_get(config, "knowledge_search.query", "") or "").strip()
    if not query:
        raise SmokeError("knowledge_search.query is required when knowledge search is enabled.")
    params = urllib.parse.urlencode(
        {
            "source": "knowledge",
            "app_name": deployed["app"],
            "q": query,
            "user_id": str(deep_get(config, "knowledge_search.user_id", "studio-e2e-kb-user")),
        }
    )
    result = client.json_request(
        "GET",
        runtime_proxy_path(
            deployed["runtimeId"],
            deployed["region"],
            f"/web/search?{params}",
        ),
    )
    if not isinstance(result, dict) or not result.get("mounted"):
        raise SmokeError(f"Knowledge search source is not mounted: {result}")
    rows = result.get("results") or []
    if truthy(deep_get(config, "knowledge_search.require_result")) and not rows:
        raise SmokeError(f"Knowledge search returned no results: {result}")
    haystack = "\n".join(
        str(item.get("content") or "") for item in rows if isinstance(item, dict)
    )
    assert_contains(
        haystack,
        str(deep_get(config, "knowledge_search.expected_contains", "") or ""),
        "knowledge search",
    )
    log.ok(f"knowledge search completed; result_count={len(rows)}")
    return result


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    log = StepLogger()
    draft_name = str(deep_get(config, "agent.name", "") or "").strip()
    if not draft_name:
        prefix = str(deep_get(config, "agent.name_prefix", "studio-e2e-kb") or "studio-e2e-kb")
        import time

        draft_name = f"{prefix}-{int(time.time())}"
    draft = build_agent_draft(config, draft_name)
    backend = str(deep_get(config, "agent.knowledgebase.backend", "viking") or "viking")
    index = str(deep_get(config, "agent.knowledgebase.index", "") or "")
    print("Studio:", deep_get(config, "studio.base_url", ""))
    print("Agent:", draft_name)
    print("Knowledgebase:", backend, index or "<derived>")
    print("Region:", deep_get(config, "deploy.region", "cn-beijing"))
    if dry_run:
        return {"success": True, "dryRun": True, "agentName": draft_name}

    client = StudioClient(config)
    debug_runs: list[dict[str, Any]] = []
    deployed_runtime: dict[str, str] | None = None
    try:
        verify_studio_ready(client, log)
        log.step(
            "Click Agents -> Add Agent -> Quick Create -> Custom; enable 知识库",
            "client-side AgentDraft assembly with knowledgebase=true",
        )
        log.ok("custom KB AgentDraft assembled")
        selected_index = verify_managed_kb_selection(client, log, config)
        if selected_index and not index:
            index = selected_index
            draft["knowledgebaseIndex"] = selected_index

        debug_user = str(deep_get(config, "debug.user_id", "test_user") or "test_user")
        debug_runtime = create_debug_run(client, log, "knowledgebase", draft, debug_user)
        debug_runs.append(debug_runtime)
        debug_result = run_debug_message(
            client,
            log,
            debug_runtime,
            debug_user,
            str(deep_get(config, "debug.message", "Hello") or "Hello"),
            str(deep_get(config, "debug.expected_contains", "") or ""),
            truthy(deep_get(config, "debug.verify_trace"), default=True),
        )

        project = generate_project_for_winner(client, log, "knowledgebase", draft)
        verify_generated_project_contains_kb(log, project, backend, index)
        final = deploy_project(client, log, config, project)
        deployed_runtime = {
            "runtimeId": str(final["runtimeId"]),
            "region": str(final.get("region") or deep_get(config, "deploy.region", "cn-beijing")),
        }
        deployed = connect_deployed_agent(
            client,
            log,
            config,
            final,
            preferred_app=str(project.get("name") or ""),
        )
        kb_components = verify_runtime_kb_mount(log, deployed, backend)
        search = verify_knowledge_search(client, log, config, deployed)
        chat = chat_with_deployed_agent(client, log, config, deployed)

        if truthy(deep_get(config, "cleanup.delete_debug_runs"), default=True):
            delete_debug_runs(client, log, debug_runs)
            debug_runs = []
        if truthy(deep_get(config, "cleanup.delete_runtime_on_success")):
            delete_runtime(
                client,
                log,
                deployed_runtime["runtimeId"],
                deployed_runtime["region"],
                verify=truthy(deep_get(config, "cleanup.verify_runtime_deleted"), default=True),
            )
        return {
            "success": True,
            "agentName": draft_name,
            "debug": debug_result,
            "deployment": {
                "runtimeId": deployed_runtime["runtimeId"],
                "region": deployed_runtime["region"],
                "app": deployed["app"],
                "agentName": final.get("agentName"),
            },
            "knowledgebase": kb_components,
            "search": search,
            "chat": chat,
        }
    except Exception:
        if deployed_runtime and truthy(deep_get(config, "cleanup.delete_runtime_on_failure")):
            try:
                delete_runtime(
                    client,
                    log,
                    deployed_runtime["runtimeId"],
                    deployed_runtime["region"],
                    verify=truthy(deep_get(config, "cleanup.verify_runtime_deleted"), default=True),
                )
            except Exception as cleanup_error:
                print(f"Runtime cleanup after failure failed: {cleanup_error}", file=sys.stderr)
        raise
    finally:
        if debug_runs and truthy(deep_get(config, "cleanup.delete_debug_runs"), default=True):
            try:
                delete_debug_runs(client, log, debug_runs)
            except Exception as cleanup_error:
                print(f"Debug cleanup failed: {cleanup_error}", file=sys.stderr)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to workflow config YAML.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    config = load_config(Path(args.config).expanduser().resolve())
    result = run_workflow(config, dry_run=args.dry_run)
    print("\n=== Summary ===")
    print_json("result", result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SmokeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
