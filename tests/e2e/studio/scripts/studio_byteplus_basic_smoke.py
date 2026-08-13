#!/usr/bin/env python3
"""Smoke-test basic Studio functions in BytePlus provider mode.

The script mirrors a small but representative Studio path:

1. Open a Studio server started with provider=byteplus.
2. Confirm backend BytePlus credentials and UI provider config.
3. Probe runtime/catalog endpoints in the BytePlus region.
4. Create a custom agent draft and generate project code with BytePlus defaults.
5. Optionally start a debug environment, deploy to AgentKit Runtime, and chat.
"""

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
    config_region,
    connect_deployed_agent,
    create_debug_run,
    deep_get,
    default_config_path,
    delete_debug_runs,
    delete_runtime,
    deploy_project,
    dry_summary,
    generate_project_for_winner,
    load_config,
    print_json,
    run_debug_message,
    truthy,
    validate_config,
    verify_studio_ready,
)


DEFAULT_CONFIG = default_config_path(__file__, "byteplus_basic.local.yaml")
BYTEPLUS_PROVIDER = "byteplus"
BYTEPLUS_DEFAULT_REGION = "ap-southeast-1"
BYTEPLUS_DEFAULT_MODEL_NAME = "seed-2-0-lite-260228"
BYTEPLUS_MODEL_API_BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"


def require_byteplus_config(config: dict[str, Any]) -> None:
    validate_config(config)
    provider = str(
        deep_get(config, "studio.provider", "")
        or deep_get(config, "agent.cloud_provider", "")
        or ""
    ).strip().lower()
    if provider != BYTEPLUS_PROVIDER:
        raise SmokeError("BytePlus smoke requires studio.provider: byteplus.")


def decode_response(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text()[:1000]


def probe_json_endpoint(
    client: StudioClient,
    log: StepLogger,
    label: str,
    path: str,
    *,
    required: bool,
) -> dict[str, Any]:
    log.step(label, f"GET {path}")
    response = client.request("GET", path, allow_statuses={400, 401, 403, 409, 422, 502})
    body = decode_response(response)
    ok = 200 <= response.status < 300
    if required and not ok:
        raise SmokeError(f"{label} failed: HTTP {response.status}: {body}")
    log.ok(
        f"status={response.status}"
        + ("" if ok else "; recorded as optional probe failure")
    )
    return {"path": path, "status": response.status, "ok": ok, "body": body}


def list_byteplus_runtimes(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
) -> dict[str, Any]:
    region = config_region(config)
    payload = probe_json_endpoint(
        client,
        log,
        "Open Agents list in BytePlus region",
        f"/web/runtimes?scope=mine&page_size=5&region={urllib.parse.quote(region, safe='')}",
        required=True,
    )
    body = payload["body"]
    runtimes = body.get("runtimes") if isinstance(body, dict) else None
    if not isinstance(runtimes, list):
        raise SmokeError(f"BytePlus runtimes response missing runtimes list: {body}")
    payload["runtimeCount"] = len(runtimes)
    return payload


def probe_catalogs(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    if not truthy(deep_get(config, "catalog_probes.enabled"), default=True):
        return []
    required = truthy(deep_get(config, "catalog_probes.required"), default=False)
    region = config_region(config)
    project = str(deep_get(config, "deploy.project_name", "") or "").strip()
    project_query = (
        f"&project={urllib.parse.quote(project, safe='')}" if project else ""
    )
    return [
        probe_json_endpoint(
            client,
            log,
            "Browse BytePlus Skill Space catalog",
            f"/web/skill-spaces?region=all&page_size=5{project_query}",
            required=required,
        ),
        probe_json_endpoint(
            client,
            log,
            "Browse BytePlus A2A Space catalog",
            f"/web/a2a-spaces?region={urllib.parse.quote(region, safe='')}&page_size=5{project_query}",
            required=required,
        ),
        probe_json_endpoint(
            client,
            log,
            "Browse BytePlus Viking knowledgebases",
            f"/web/viking-knowledgebases?region={urllib.parse.quote(region, safe='')}{project_query}",
            required=required,
        ),
    ]


def assert_byteplus_project(project: dict[str, Any]) -> None:
    assert_generated_contains(
        project,
        [BYTEPLUS_DEFAULT_MODEL_NAME, BYTEPLUS_MODEL_API_BASE],
        "BytePlus generated project",
    )


def maybe_run_debug(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any] | None:
    if not truthy(deep_get(config, "debug.enabled"), default=True):
        return None
    user_id = str(deep_get(config, "debug.user_id", "byteplus_e2e_user") or "byteplus_e2e_user")
    try:
        runtime = create_debug_run(client, log, "byteplus", draft, user_id)
    except SmokeError as exc:
        detail = str(exc)
        if (
            "No ARK API keys found in project" in detail
            or "ARK API Key named" in detail
        ):
            project_name = str(deep_get(config, "deploy.project_name", "default") or "default")
            message = (
                "BytePlus model-key auto-fetch reached ModelArk, but no API "
                + f"key was found in project {project_name!r}. Create a ModelArk "
                + "API key in that project, or set deploy.project_name / "
                + "ARK_PROJECT_NAME to the project that already has one."
            )
            if truthy(deep_get(config, "debug.required"), default=False):
                raise SmokeError(detail + "\n\n" + message) from exc
            log.ok("debug skipped: " + message)
            return {
                "skipped": True,
                "reason": "missing_byteplus_modelark_api_key",
                "projectName": project_name,
                "required": False,
            }
        raise
    try:
        result = run_debug_message(
            client,
            log,
            runtime,
            user_id,
            str(deep_get(config, "debug.message", "Hello from BytePlus smoke.") or "Hello"),
            str(deep_get(config, "debug.expected_contains", "") or ""),
            truthy(deep_get(config, "debug.verify_trace"), default=False),
        )
    finally:
        if truthy(deep_get(config, "cleanup.delete_debug_runs"), default=True):
            delete_debug_runs(client, log, [runtime])
    return result


def maybe_deploy_chat(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    project: dict[str, Any],
) -> dict[str, Any] | None:
    if not truthy(deep_get(config, "deploy.enabled"), default=False):
        return None
    final = deploy_project(client, log, config, project)
    deployed = connect_deployed_agent(
        client,
        log,
        config,
        final,
        preferred_app=str(project.get("name") or final.get("agentName") or ""),
    )
    chat = chat_with_deployed_agent(client, log, config, deployed)
    if truthy(deep_get(config, "cleanup.delete_runtime_on_success")):
        delete_runtime(
            client,
            log,
            str(final["runtimeId"]),
            str(final.get("region") or config_region(config)),
            verify=truthy(deep_get(config, "cleanup.verify_runtime_deleted"), default=True),
        )
    return {"final": final, "deployed": deployed, "chat": chat}


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    require_byteplus_config(config)
    draft = build_basic_draft(config, "studio-e2e-bp")
    draft["cloudProvider"] = BYTEPLUS_PROVIDER
    if not str(draft.get("modelName") or "").strip():
        draft["modelName"] = BYTEPLUS_DEFAULT_MODEL_NAME
    if not str(draft.get("modelApiBase") or "").strip():
        draft["modelApiBase"] = BYTEPLUS_MODEL_API_BASE

    summary = {
        "provider": draft["cloudProvider"],
        "region": config_region(config),
        "agentName": draft["name"],
        "modelName": draft.get("modelName"),
        "deployEnabled": truthy(deep_get(config, "deploy.enabled")),
    }
    if dry_run:
        return dry_summary("byteplus basic", summary)

    log = StepLogger()
    client = StudioClient(config)
    verify_studio_ready(client, log, config)
    runtimes = list_byteplus_runtimes(client, log, config)
    catalog_probes = probe_catalogs(client, log, config)

    project = generate_project_for_winner(client, log, "byteplus-basic", draft)
    assert_byteplus_project(project)
    log.ok("generated project contains BytePlus model and ModelArk endpoint defaults")

    debug = maybe_run_debug(client, log, config, draft)
    deployment = maybe_deploy_chat(client, log, config, project)

    return {
        "success": True,
        **summary,
        "runtimes": {
            "status": runtimes["status"],
            "runtimeCount": runtimes["runtimeCount"],
        },
        "catalogProbes": [
            {"path": item["path"], "status": item["status"], "ok": item["ok"]}
            for item in catalog_probes
        ],
        "project": {
            "name": project.get("name"),
            "fileCount": len(project.get("files") or []),
        },
        "debug": debug,
        "deployment": deployment,
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
