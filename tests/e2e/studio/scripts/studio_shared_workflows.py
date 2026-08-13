#!/usr/bin/env python3
"""Shared helpers for Studio E2E workflow smoke scripts."""

from __future__ import annotations

import copy
import json
import sys
import time
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
    as_list,
    assert_contains,
    build_agent_draft,
    chat_with_deployed_agent,
    cloud_provider,
    connect_deployed_agent,
    config_region,
    create_debug_run,
    deep_get,
    delete_debug_runs,
    delete_runtime,
    deploy_project,
    generate_project_for_winner,
    load_config,
    print_json,
    request_with_retries,
    runtime_proxy_path,
    run_debug_message,
    truthy,
    validate_config,
    verify_studio_ready,
)


def default_config_path(script_file: str, name: str) -> Path:
    del script_file
    return Path(__file__).resolve().parents[1] / "configs" / name


def timestamped_name(config: dict[str, Any], default_prefix: str) -> str:
    explicit = str(deep_get(config, "agent.name", "") or "").strip()
    if explicit:
        return explicit
    prefix = str(deep_get(config, "agent.name_prefix", default_prefix) or default_prefix)
    return f"{prefix}-{int(time.time())}"


def generated_text(project: dict[str, Any]) -> str:
    files = project.get("files") if isinstance(project, dict) else []
    chunks: list[str] = []
    for item in files or []:
        if isinstance(item, dict):
            chunks.append(str(item.get("path") or ""))
            chunks.append(str(item.get("content") or ""))
    return "\n".join(chunks)


def generated_paths(project: dict[str, Any]) -> set[str]:
    files = project.get("files") if isinstance(project, dict) else []
    return {
        str(item.get("path") or "")
        for item in files or []
        if isinstance(item, dict)
    }


def assert_generated_contains(project: dict[str, Any], expected: list[str], label: str) -> None:
    text = generated_text(project)
    missing = [item for item in expected if item and item not in text]
    if missing:
        raise SmokeError(f"{label}: generated project missing {missing}")


def deploy_connect_chat(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    project: dict[str, Any],
    *,
    cleanup_key: str = "cleanup",
    chat: bool = True,
) -> dict[str, Any]:
    final = deploy_project(client, log, config, project)
    deployed = connect_deployed_agent(
        client,
        log,
        config,
        final,
        preferred_app=str(project.get("name") or final.get("agentName") or ""),
    )
    chat_result = chat_with_deployed_agent(client, log, config, deployed) if chat else None
    if truthy(deep_get(config, f"{cleanup_key}.delete_runtime_on_success")):
        delete_runtime(
            client,
            log,
            str(final["runtimeId"]),
            str(final.get("region") or config_region(config)),
            verify=truthy(deep_get(config, f"{cleanup_key}.verify_runtime_deleted"), default=True),
        )
    return {
        "final": final,
        "deployed": deployed,
        "chat": chat_result,
    }


def runtime_detail(client: StudioClient, runtime_id: str, region: str) -> dict[str, Any]:
    detail = client.json_request(
        "GET",
        f"/web/runtime-detail?runtimeId={urllib.parse.quote(runtime_id, safe='')}"
        f"&region={urllib.parse.quote(region, safe='')}",
    )
    if not isinstance(detail, dict):
        raise SmokeError(f"Invalid runtime detail payload: {detail}")
    return detail


def runtime_agent_info(
    client: StudioClient,
    runtime_id: str,
    region: str,
    app: str,
) -> dict[str, Any]:
    info = request_with_retries(
        client,
        "GET",
        runtime_proxy_path(
            runtime_id,
            region,
            f"/web/agent-info/{urllib.parse.quote(app, safe='')}",
        ),
    )
    if not isinstance(info, dict):
        raise SmokeError(f"Invalid runtime agent-info payload: {info}")
    return info


def component_matches(component: dict[str, Any], **expected: str) -> bool:
    for key, value in expected.items():
        if value and str(component.get(key) or "") != value:
            return False
    return True


def require_component(info: dict[str, Any], kind: str, *, source: str = "", backend: str = "") -> dict[str, Any]:
    components = info.get("components")
    if not isinstance(components, list):
        raise SmokeError(f"agent-info components missing: {info}")
    for component in components:
        if isinstance(component, dict) and component_matches(
            component,
            kind=kind,
            source=source,
            backend=backend,
        ):
            return component
    raise SmokeError(
        "agent-info missing component "
        + json.dumps({"kind": kind, "source": source, "backend": backend}, ensure_ascii=False)
        + f": {components}"
    )


def require_search_source(info: dict[str, Any], source: str) -> None:
    sources = info.get("searchSources")
    if source not in (sources or []):
        raise SmokeError(f"agent-info missing search source {source!r}: {sources}")


def choose_runtime(config: dict[str, Any], client: StudioClient, log: StepLogger) -> dict[str, Any]:
    configured = deep_get(config, "runtime", {}) or {}
    runtime_id = str(configured.get("runtime_id") or configured.get("runtimeId") or "").strip()
    region = str(configured.get("region") or config_region(config))
    if runtime_id:
        detail = runtime_detail(client, runtime_id, region)
        app = str(configured.get("app") or detail.get("model") or detail.get("name") or "").strip()
        return {"runtimeId": runtime_id, "region": region, "app": app, "detail": detail}

    scope = str(configured.get("scope") or "mine")
    page_size = int(configured.get("page_size") or 20)
    log.step(
        "Open Agents and choose an existing runtime",
        "GET /web/runtimes",
    )
    payload = client.json_request(
        "GET",
        f"/web/runtimes?scope={urllib.parse.quote(scope, safe='')}"
        f"&page_size={page_size}&region={urllib.parse.quote(region, safe='')}",
    )
    runtimes = payload.get("runtimes") if isinstance(payload, dict) else None
    if not isinstance(runtimes, list) or not runtimes:
        raise SmokeError("No runtimes available. Configure runtime.runtime_id explicitly.")
    name_contains = str(configured.get("name_contains") or "").strip()
    chosen = None
    for item in runtimes:
        if not isinstance(item, dict):
            continue
        if name_contains and name_contains not in str(item.get("name") or ""):
            continue
        chosen = item
        break
    if chosen is None:
        raise SmokeError(f"No runtime matched name_contains={name_contains!r}")
    log.ok(f"selected runtime {chosen.get('name')} ({chosen.get('runtimeId')})")
    detail = runtime_detail(client, str(chosen["runtimeId"]), str(chosen.get("region") or region))
    app = str(configured.get("app") or detail.get("model") or detail.get("name") or "").strip()
    return {
        "runtimeId": str(chosen["runtimeId"]),
        "region": str(chosen.get("region") or region),
        "app": app,
        "detail": detail,
    }


def build_basic_draft(config: dict[str, Any], default_prefix: str) -> dict[str, Any]:
    return build_agent_draft(config, timestamped_name(config, default_prefix))


def merge_deployment_env_values(draft: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    next_draft = copy.deepcopy(draft)
    env_values: dict[str, str] = {}
    raw_env = deep_get(config, "deploy.env", {}) or {}
    if isinstance(raw_env, dict):
        env_values.update({str(k): str(v) for k, v in raw_env.items() if v is not None})
    deployment = next_draft.get("deployment")
    if not isinstance(deployment, dict):
        deployment = {}
    deployment["envValues"] = env_values
    next_draft["deployment"] = deployment
    return next_draft


def dry_summary(label: str, payload: dict[str, Any]) -> dict[str, Any]:
    print(f"{label}: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    return {"success": True, "dryRun": True, **payload}


__all__ = [
    "SmokeError",
    "StepLogger",
    "StudioClient",
    "as_list",
    "assert_contains",
    "assert_generated_contains",
    "build_agent_draft",
    "build_basic_draft",
    "chat_with_deployed_agent",
    "choose_runtime",
    "cloud_provider",
    "component_matches",
    "config_region",
    "create_debug_run",
    "deep_get",
    "default_config_path",
    "delete_debug_runs",
    "delete_runtime",
    "deploy_connect_chat",
    "deploy_project",
    "dry_summary",
    "generated_paths",
    "generated_text",
    "generate_project_for_winner",
    "load_config",
    "merge_deployment_env_values",
    "print_json",
    "request_with_retries",
    "require_component",
    "require_search_source",
    "runtime_agent_info",
    "runtime_detail",
    "runtime_proxy_path",
    "run_debug_message",
    "timestamped_name",
    "truthy",
    "validate_config",
    "verify_studio_ready",
]
