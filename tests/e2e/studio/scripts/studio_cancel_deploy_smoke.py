#!/usr/bin/env python3
"""Smoke-test cancelling an in-flight Studio deployment."""

from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
import urllib.request
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
    truthy,
    validate_config,
    verify_studio_ready,
)
from studio_custom_ab_deploy_chat_smoke import clean_env, network_config


DEFAULT_CONFIG = default_config_path(__file__, "cancel_deploy.local.yaml")


def parse_sse_event(lines: list[str]) -> dict[str, Any] | None:
    if not lines:
        return None
    raw = "\n".join(lines)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return data if isinstance(data, dict) else {"data": data}


def stream_deploy(client: StudioClient, payload: dict[str, Any], events: queue.Queue[Any]) -> None:
    url = client.base_url + "/web/deploy-agentkit"
    headers = dict(client.headers)
    headers["Accept"] = "text/event-stream"
    headers["Content-Type"] = "application/json"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=client.timeout) as resp:
            pending: list[str] = []
            for raw in resp:
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if not line:
                    event = parse_sse_event(pending)
                    pending = []
                    if event is not None:
                        events.put(event)
                    continue
                if line.startswith("data:"):
                    pending.append(line[5:].lstrip())
            event = parse_sse_event(pending)
            if event is not None:
                events.put(event)
    except Exception as exc:
        events.put({"threadError": str(exc)})
    finally:
        events.put(None)


def deploy_payload(config: dict[str, Any], project: dict[str, Any], task_id: str) -> dict[str, Any]:
    deploy = config.get("deploy") or {}
    payload: dict[str, Any] = {
        "name": project["name"],
        "files": project["files"],
        "config": {
            "region": str(deploy.get("region") or "cn-beijing"),
            "projectName": str(deploy.get("project_name") or "default"),
            "network": network_config(config),
        },
        "taskId": task_id,
        "sessionStorage": str(deploy.get("session_storage") or "persistent"),
        "description": str(deploy.get("description") or ""),
        "envs": clean_env(deploy.get("env") or {}),
    }
    if deploy.get("min_instance") is not None:
        payload["minInstance"] = int(deploy["min_instance"])
    if deploy.get("max_instance") is not None:
        payload["maxInstance"] = int(deploy["max_instance"])
    return payload


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    draft = build_basic_draft(config, "studio-e2e-cancel")
    task_id = f"{deep_get(config, 'deploy.task_id_prefix', 'studio-e2e-cancel')}-{int(time.time())}"
    if dry_run:
        return dry_summary("cancel deploy", {"agentName": draft["name"], "taskId": task_id})

    log = StepLogger()
    client = StudioClient(config)
    verify_studio_ready(client, log)
    project = generate_project_for_winner(client, log, "cancel-test", draft)
    payload = deploy_payload(config, project, task_id)
    events: queue.Queue[Any] = queue.Queue()
    thread = threading.Thread(target=stream_deploy, args=(client, payload, events), daemon=True)
    log.step("Click deploy and then cancel while deployment is running", "POST /web/deploy-agentkit, POST /web/cancel-deploy-agentkit")
    thread.start()

    seen: list[dict[str, Any]] = []
    deadline = time.time() + float(deep_get(config, "cancel.wait_before_cancel_seconds", 30) or 30)
    while time.time() < deadline:
        try:
            event = events.get(timeout=1)
        except queue.Empty:
            continue
        if event is None:
            break
        if isinstance(event, dict):
            seen.append(event)
            if event.get("message") or event.get("runtimeName"):
                break

    cancel = client.json_request("POST", "/web/cancel-deploy-agentkit", {"taskId": task_id})
    terminal: dict[str, Any] | None = None
    final_deadline = time.time() + float(deep_get(config, "cancel.wait_after_cancel_seconds", 180) or 180)
    while time.time() < final_deadline:
        try:
            event = events.get(timeout=2)
        except queue.Empty:
            if not thread.is_alive():
                break
            continue
        if event is None:
            break
        if isinstance(event, dict):
            seen.append(event)
            if event.get("done"):
                terminal = event
                break
    thread.join(timeout=5)
    if not isinstance(cancel, dict) or not cancel.get("success"):
        raise SmokeError(f"Cancel endpoint returned unexpected payload: {cancel}")
    if truthy(deep_get(config, "cancel.require_terminal_failure"), default=False):
        if not terminal or terminal.get("success"):
            raise SmokeError(f"Expected cancelled deploy terminal failure frame: {terminal}")
    log.ok(f"cancel requested; destroyed={cancel.get('destroyed')} runtimeId={cancel.get('runtimeId') or ''}")
    return {
        "success": True,
        "agentName": draft["name"],
        "taskId": task_id,
        "cancel": cancel,
        "eventCount": len(seen),
        "terminal": terminal,
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
