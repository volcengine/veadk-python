#!/usr/bin/env python3
"""Smoke-test Studio manage/update/feedback-cases/delete-agent workflow.

This mirrors the UI journey:

1. User opens 智能体 and chooses an existing agent.
2. User opens details and updates the agent through the custom options page.
3. Studio updates the existing AgentKit Runtime and the version becomes v2+.
4. User chats with the updated agent.
5. User thumbs-up and thumbs-down responses.
6. User opens the feedback cases page, navigates from a case back to chat,
   deletes a case, and verifies the backend/AgentKit data changed.
7. User deletes explicitly configured agents and verifies they are gone from
   AgentKit, not merely hidden from the UI.
"""

from __future__ import annotations

import argparse
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
    HttpResponse,
    SmokeError,
    StepLogger,
    StudioClient,
    assert_contains,
    assert_no_event_errors,
    clean_env,
    codegen_draft,
    collect_event_text,
    deep_get,
    delete_runtime,
    load_config,
    network_config as _custom_network_config,
    parse_simple_yaml,
    print_json,
    request_with_retries,
    runtime_proxy_path,
    truthy,
    validate_config as _unused_validate_custom_config,
)


DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "manage_update_feedback_delete.local.yaml"
)


def validate_config(config: dict[str, Any]) -> None:
    errors: list[str] = []
    if not str(deep_get(config, "studio.base_url", "") or "").strip():
        errors.append("studio.base_url is required.")
    if not str(deep_get(config, "target.runtime_id", "") or "").strip() and not str(
        deep_get(config, "target.name_contains", "") or ""
    ).strip():
        errors.append("target.runtime_id or target.name_contains is required.")
    scope = str(deep_get(config, "target.scope", "mine") or "mine")
    if scope not in {"mine", "all"}:
        errors.append("target.scope must be mine or all.")
    delete_cfg = config.get("delete_agents") or {}
    if truthy(delete_cfg.get("enabled")):
        runtimes = delete_cfg.get("runtimes") or []
        if not isinstance(runtimes, list) or not runtimes:
            errors.append("delete_agents.runtimes must list at least one runtime when enabled.")
        for index, item in enumerate(runtimes):
            if not isinstance(item, dict):
                errors.append(f"delete_agents.runtimes[{index}] must be a mapping.")
                continue
            if not str(item.get("runtime_id") or "").strip():
                errors.append(f"delete_agents.runtimes[{index}].runtime_id is required.")
            has_guard = bool(
                str(item.get("expected_name_contains") or "").strip()
                or str(item.get("expected_name") or "").strip()
            )
            if not has_guard and not truthy(delete_cfg.get("allow_without_name_guard")):
                errors.append(
                    f"delete_agents.runtimes[{index}] needs expected_name or "
                    "expected_name_contains, or set allow_without_name_guard=true."
                )
    if errors:
        raise SmokeError("Invalid config:\n- " + "\n- ".join(errors))


def network_config(config: dict[str, Any]) -> dict[str, Any] | None:
    clone = {"deploy": {"network": deep_get(config, "update.deploy.network", {}) or {}}}
    return _custom_network_config(clone)


def verify_studio_manage_ready(client: StudioClient, log: StepLogger) -> None:
    log.step(
        "Open Studio and click 智能体",
        "GET /web/runtime-config, GET /web/access, GET /web/runtimes",
    )
    runtime_config = client.json_request("GET", "/web/runtime-config")
    if not isinstance(runtime_config, dict) or not runtime_config.get("credentials"):
        raise SmokeError("Studio backend does not report Volcengine credentials.")
    access = client.json_request("GET", "/web/access")
    capabilities = access.get("capabilities") if isinstance(access, dict) else {}
    if not capabilities.get("manageAgents"):
        raise SmokeError(f"Signed-in user cannot manage agents: {access}")
    if not capabilities.get("createAgents"):
        raise SmokeError(f"Signed-in user cannot update/redeploy agents: {access}")
    log.ok("backend credentials present; user can manage and update agents")


def list_runtimes(
    client: StudioClient,
    *,
    region: str,
    scope: str,
    page_size: int = 100,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    runtimes: list[dict[str, Any]] = []
    next_token = ""
    for _ in range(max_pages):
        params = urllib.parse.urlencode(
            {
                "scope": scope,
                "page_size": str(page_size),
                "region": region,
                **({"next_token": next_token} if next_token else {}),
            }
        )
        payload = client.json_request("GET", f"/web/runtimes?{params}")
        if not isinstance(payload, dict):
            raise SmokeError(f"/web/runtimes returned invalid payload: {payload}")
        page = payload.get("runtimes") or []
        if not isinstance(page, list):
            raise SmokeError(f"/web/runtimes.runtimes is invalid: {payload}")
        runtimes.extend([item for item in page if isinstance(item, dict)])
        next_token = str(payload.get("nextToken") or "")
        if not next_token:
            break
    return runtimes


def choose_target_runtime(
    client: StudioClient, log: StepLogger, config: dict[str, Any]
) -> dict[str, Any]:
    log.step(
        "Choose an agent and open details",
        "GET /web/runtimes, GET /web/runtime-detail, GET /web/runtime-update-capability",
    )
    region = str(deep_get(config, "target.region", "cn-beijing") or "cn-beijing")
    scope = str(deep_get(config, "target.scope", "mine") or "mine")
    runtime_id = str(deep_get(config, "target.runtime_id", "") or "").strip()
    target: dict[str, Any] | None = None
    runtimes = list_runtimes(client, region=region, scope=scope)
    if runtime_id:
        target = next((item for item in runtimes if item.get("runtimeId") == runtime_id), None)
        if target is None:
            target = {"runtimeId": runtime_id, "region": region}
    else:
        needle = str(deep_get(config, "target.name_contains", "") or "").lower()
        target = next(
            (
                item
                for item in runtimes
                if needle in str(item.get("name") or "").lower()
            ),
            None,
        )
    if target is None or not target.get("runtimeId"):
        raise SmokeError("No target runtime matched target.runtime_id/name_contains.")

    runtime_id = str(target["runtimeId"])
    region = str(target.get("region") or region)
    detail = client.json_request(
        "GET",
        f"/web/runtime-detail?runtimeId={urllib.parse.quote(runtime_id, safe='')}"
        f"&region={urllib.parse.quote(region, safe='')}",
    )
    if not isinstance(detail, dict):
        raise SmokeError(f"Runtime detail returned invalid payload: {detail}")
    capability = client.json_request(
        "GET",
        f"/web/runtime-update-capability?runtimeId={urllib.parse.quote(runtime_id, safe='')}"
        f"&region={urllib.parse.quote(region, safe='')}",
    )
    if not isinstance(capability, dict) or not capability.get("canUpdate"):
        raise SmokeError(f"Runtime cannot be updated through Studio: {capability}")
    app_name = str(deep_get(capability, "agent.appName", "") or "")
    if not app_name:
        raise SmokeError(f"Update capability did not include appName: {capability}")
    log.ok(
        f"selected runtime={runtime_id}; app={app_name}; currentVersion={detail.get('currentVersion')}"
    )
    return {
        "runtimeId": runtime_id,
        "region": region,
        "detail": detail,
        "capability": capability,
        "appName": app_name,
    }


def fallback_draft(target: dict[str, Any]) -> dict[str, Any]:
    agent = deep_get(target, "capability.agent", {}) or {}
    detail = target.get("detail") or {}
    app_name = str(agent.get("appName") or agent.get("name") or detail.get("name") or "agent")
    return {
        "name": app_name,
        "description": str(agent.get("description") or detail.get("description") or "Updated Studio E2E agent."),
        "instruction": str(
            agent.get("instruction")
            or "You are a concise assistant. Reply to Studio E2E checks clearly."
        ),
        "agentType": "llm",
        "maxIterations": 3,
        "a2aUrl": "",
        "model": "",
        "modelName": str(agent.get("model") or detail.get("model") or "doubao-seed-2-1-pro-260628"),
        "modelProvider": "",
        "modelApiBase": "",
        "tools": [],
        "skills": [],
        "memory": {"shortTerm": False, "longTerm": False},
        "knowledgebase": False,
        "tracing": False,
        "subAgents": [],
        "builtinTools": [],
        "customTools": [],
        "mcpTools": [],
        "shortTermBackend": "local",
        "longTermBackend": "local",
        "autoSaveSession": False,
        "knowledgebaseBackend": "local",
        "knowledgebaseIndex": "",
        "tracingExporters": [],
        "selectedSkills": [],
        "deployment": {"feishuEnabled": False},
    }


def updated_draft(config: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(deep_get(target, "capability.agent.draft", None) or fallback_draft(target))
    if not isinstance(draft, dict):
        raise SmokeError(f"Target draft is invalid: {draft}")
    if deep_get(config, "update.model_name", None) is not None:
        draft["modelName"] = str(deep_get(config, "update.model_name", "") or "")
    description_suffix = str(deep_get(config, "update.description_suffix", "") or "")
    instruction_suffix = str(deep_get(config, "update.instruction_suffix", "") or "")
    if description_suffix and description_suffix not in str(draft.get("description") or ""):
        draft["description"] = str(draft.get("description") or "") + description_suffix
    if instruction_suffix and instruction_suffix not in str(draft.get("instruction") or ""):
        draft["instruction"] = str(draft.get("instruction") or "") + instruction_suffix
    draft["name"] = str(draft.get("name") or target["appName"])
    return draft


def generate_update_project(
    client: StudioClient, log: StepLogger, draft: dict[str, Any]
) -> dict[str, Any]:
    log.step(
        "Click update agent and go through options page again",
        "POST /web/generated-agent-projects",
    )
    project = client.json_request(
        "POST",
        "/web/generated-agent-projects",
        {"draft": codegen_draft(draft)},
    )
    if not isinstance(project, dict) or not project.get("name") or not project.get("files"):
        raise SmokeError(f"Invalid generated project response: {project}")
    log.ok(f"updated project generated: {project['name']} ({len(project['files'])} files)")
    return project


def deploy_update(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    target: dict[str, Any],
    draft: dict[str, Any],
    project: dict[str, Any],
) -> dict[str, Any]:
    log.step(
        "Click deploy/update for existing agent",
        "POST /web/deploy-agentkit with runtimeId and appName",
    )
    deploy = deep_get(config, "update.deploy", {}) or {}
    task_prefix = str(deploy.get("task_id_prefix") or "studio-e2e-update")
    payload: dict[str, Any] = {
        "name": project["name"],
        "files": project["files"],
        "runtimeId": target["runtimeId"],
        "appName": target["appName"],
        "description": str(draft.get("description") or ""),
        "config": {
            "region": target["region"],
            "projectName": str(deploy.get("project_name") or target["detail"].get("project") or "default"),
            "network": network_config(config),
        },
        "taskId": f"{task_prefix}-{int(time.time())}",
        "sessionStorage": str(deploy.get("session_storage") or "persistent"),
        "envs": clean_env(deploy.get("env") or {}),
    }
    if deploy.get("min_instance") is not None:
        payload["minInstance"] = int(deploy["min_instance"])
    if deploy.get("max_instance") is not None:
        payload["maxInstance"] = int(deploy["max_instance"])

    events = client.stream_sse("POST", "/web/deploy-agentkit", payload)
    final = next((event for event in reversed(events) if event.get("done")), None)
    if not final:
        raise SmokeError("Update deployment stream ended without a terminal frame.")
    if not final.get("success"):
        raise SmokeError(f"Update deployment failed: {final.get('error') or final}")
    if str(final.get("runtimeId") or target["runtimeId"]) != target["runtimeId"]:
        raise SmokeError(f"Update returned unexpected runtime: {final}")
    log.ok(f"update deployed to runtime={target['runtimeId']}")
    return final


def verify_updated_version(
    client: StudioClient, log: StepLogger, config: dict[str, Any], target: dict[str, Any]
) -> dict[str, Any]:
    log.step(
        "Choose updated agent and verify it says v2",
        "GET /web/runtime-detail",
    )
    expected_min = int(deep_get(config, "update.expected_min_version_after", 2) or 2)
    before = target["detail"].get("currentVersion")
    detail: dict[str, Any] | None = None
    deadline = time.time() + 240
    while time.time() < deadline:
        candidate = client.json_request(
            "GET",
            f"/web/runtime-detail?runtimeId={urllib.parse.quote(target['runtimeId'], safe='')}"
            f"&region={urllib.parse.quote(target['region'], safe='')}",
        )
        if isinstance(candidate, dict):
            detail = candidate
            version = candidate.get("currentVersion")
            if isinstance(version, int) and version >= expected_min:
                log.ok(f"runtime version is v{version}")
                return candidate
            if isinstance(version, int) and isinstance(before, int) and version > before:
                log.ok(f"runtime version advanced from v{before} to v{version}")
                return candidate
        time.sleep(10)
    raise SmokeError(f"Runtime version did not reach v{expected_min}: {detail}")


def create_runtime_session(
    client: StudioClient,
    runtime_id: str,
    region: str,
    app: str,
    user_id: str,
) -> str:
    session_path = (
        f"/apps/{urllib.parse.quote(app, safe='')}/users/"
        f"{urllib.parse.quote(user_id, safe='')}/sessions"
    )
    session = client.json_request(
        "POST",
        runtime_proxy_path(runtime_id, region, session_path),
        {},
    )
    if isinstance(session, dict) and session.get("id"):
        return str(session["id"])
    return f"studio-manage-e2e-{int(time.time())}"


def get_runtime_session(
    client: StudioClient,
    runtime_id: str,
    region: str,
    app: str,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    session_path = (
        f"/apps/{urllib.parse.quote(app, safe='')}/users/"
        f"{urllib.parse.quote(user_id, safe='')}/sessions/"
        f"{urllib.parse.quote(session_id, safe='')}"
    )
    session = client.json_request("GET", runtime_proxy_path(runtime_id, region, session_path))
    if not isinstance(session, dict):
        raise SmokeError(f"Runtime session returned invalid payload: {session}")
    return session


def find_assistant_event_id(session: dict[str, Any], after_event_ids: set[str]) -> str:
    events = session.get("events") or []
    if not isinstance(events, list):
        raise SmokeError(f"Session events are invalid: {session}")
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id") or "")
        if not event_id or event_id in after_event_ids:
            continue
        author = str(event.get("author") or "")
        content = event.get("content") if isinstance(event.get("content"), dict) else {}
        parts = content.get("parts") if isinstance(content, dict) else []
        has_text = any(isinstance(part, dict) and part.get("text") for part in (parts or []))
        if has_text and author != "user":
            return event_id
    raise SmokeError("Could not find new assistant event id in session.")


def chat_and_collect_feedback_targets(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    target: dict[str, Any],
) -> dict[str, Any]:
    log.step(
        "Chat with updated agent",
        "POST /web/runtime-proxy/{runtimeId}/sessions, POST /web/runtime-proxy/{runtimeId}/run_sse, GET session",
    )
    runtime_id = target["runtimeId"]
    region = target["region"]
    app = target["appName"]
    user_id = str(deep_get(config, "chat.user_id", "studio-e2e-user") or "studio-e2e-user")
    session_id = create_runtime_session(client, runtime_id, region, app, user_id)
    feedback_targets: dict[str, dict[str, Any]] = {}
    for kind in ("good", "bad"):
        message_cfg = deep_get(config, f"chat.messages.{kind}", {}) or {}
        text = str(message_cfg.get("text") or f"Studio E2E {kind} message")
        before_session = get_runtime_session(client, runtime_id, region, app, user_id, session_id)
        before_ids = {
            str(event.get("id"))
            for event in before_session.get("events", [])
            if isinstance(event, dict) and event.get("id")
        }
        events = client.stream_sse(
            "POST",
            runtime_proxy_path(runtime_id, region, "/run_sse"),
            {
                "app_name": app,
                "user_id": user_id,
                "session_id": session_id,
                "new_message": {"role": "user", "parts": [{"text": text}]},
                "streaming": True,
            },
            timeout=float(deep_get(config, "chat.sse_idle_timeout_seconds", 45) or 45),
            echo_messages=False,
            return_events_on_timeout=True,
        )
        assert_no_event_errors(events, f"updated chat {kind}")
        response_text = collect_event_text(events)
        if not response_text.strip():
            raise SmokeError(f"updated chat {kind}: empty assistant response")
        assert_contains(
            response_text,
            str(message_cfg.get("expected_contains") or ""),
            f"updated chat {kind}",
        )
        after_session = get_runtime_session(client, runtime_id, region, app, user_id, session_id)
        event_id = find_assistant_event_id(after_session, before_ids)
        feedback_targets[kind] = {
            "kind": kind,
            "userId": user_id,
            "sessionId": session_id,
            "eventId": event_id,
            "response": response_text,
            "comment": str(message_cfg.get("comment") or ""),
        }
    log.ok(
        "collected assistant events for feedback: "
        + ", ".join(f"{kind}={item['eventId']}" for kind, item in feedback_targets.items())
    )
    return {
        "userId": user_id,
        "sessionId": session_id,
        "targets": feedback_targets,
    }


def submit_feedback(
    client: StudioClient,
    log: StepLogger,
    target: dict[str, Any],
    feedback_targets: dict[str, Any],
) -> dict[str, Any]:
    log.step(
        "Thumbs up and thumbs down agent responses",
        "POST /web/evaluation/feedback",
    )
    states: dict[str, Any] = {}
    for kind, item in feedback_targets["targets"].items():
        state = client.json_request(
            "POST",
            "/web/evaluation/feedback",
            {
                "runtimeId": target["runtimeId"],
                "region": target["region"],
                "appName": target["appName"],
                "userId": item["userId"],
                "sessionId": item["sessionId"],
                "eventId": item["eventId"],
                "rating": kind,
                "comment": item["comment"],
            },
        )
        if not isinstance(state, dict) or state.get("rating") != kind:
            raise SmokeError(f"Feedback state invalid for {kind}: {state}")
        states[kind] = state
    log.ok("feedback synced to AgentKit evaluation datasets")
    return states


def get_feedback_cases(
    client: StudioClient,
    target: dict[str, Any],
    page_size: int,
) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "runtimeId": target["runtimeId"],
            "region": target["region"],
            "appName": target["appName"],
            "page_size": str(page_size),
        }
    )
    payload = client.json_request("GET", f"/web/evaluation/feedback-cases?{query}")
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise SmokeError(f"Feedback cases payload invalid: {payload}")
    return payload


def verify_cases_page(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    target: dict[str, Any],
    feedback_targets: dict[str, Any],
) -> dict[str, Any]:
    log.step(
        "Open cases page and verify good/bad cases",
        "GET /web/evaluation/feedback-cases",
    )
    page_size = int(deep_get(config, "cases.page_size", 100) or 100)
    cases = get_feedback_cases(client, target, page_size)
    items = cases["items"]
    by_kind: dict[str, dict[str, Any]] = {}
    for kind, target_item in feedback_targets["targets"].items():
        match = next(
            (
                item
                for item in items
                if item.get("kind") == kind
                and item.get("sessionId") == target_item["sessionId"]
                and item.get("messageId") == target_item["eventId"]
            ),
            None,
        )
        if not match:
            raise SmokeError(f"Feedback case missing for {kind}: {cases}")
        by_kind[kind] = match
    log.ok(f"cases found: good={by_kind['good']['id']}, bad={by_kind['bad']['id']}")

    if truthy(deep_get(config, "cases.verify_nav_to_chat"), default=True):
        log.step(
            "Click case navigation back to chat",
            "GET runtime session referenced by feedback case",
        )
        for kind, item in by_kind.items():
            session = get_runtime_session(
                client,
                target["runtimeId"],
                target["region"],
                target["appName"],
                str(item.get("userId") or feedback_targets["userId"]),
                str(item.get("sessionId")),
            )
            event_ids = {
                str(event.get("id"))
                for event in session.get("events", [])
                if isinstance(event, dict) and event.get("id")
            }
            if str(item.get("messageId")) not in event_ids:
                raise SmokeError(f"Case {kind} does not navigate to an existing event.")
        log.ok("each case references an existing chat session/event")

    deleted: dict[str, Any] | None = None
    if truthy(deep_get(config, "cases.delete_one_case"), default=True):
        delete_kind = str(deep_get(config, "cases.delete_kind", "bad") or "bad")
        deleted = delete_case(client, log, config, target, by_kind[delete_kind])
    return {"cases": cases, "matched": by_kind, "deleted": deleted}


def delete_case(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    target: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    log.step(
        "Delete a feedback case from cases page",
        "POST /web/evaluation/feedback-cases/delete, GET /web/evaluation/feedback-cases, GET session",
    )
    item_id = str(item.get("id") or "")
    if not item_id:
        raise SmokeError(f"Cannot delete case without id: {item}")
    response = client.json_request(
        "POST",
        "/web/evaluation/feedback-cases/delete",
        {
            "runtimeId": target["runtimeId"],
            "region": target["region"],
            "appName": target["appName"],
            "itemIds": [item_id],
        },
    )
    if not isinstance(response, dict) or int(response.get("deletedCount") or 0) < 1:
        raise SmokeError(f"Feedback case delete did not report deletion: {response}")
    cases = get_feedback_cases(
        client,
        target,
        int(deep_get(config, "cases.page_size", 100) or 100),
    )
    if any(case.get("id") == item_id for case in cases.get("items", [])):
        raise SmokeError(f"Deleted case still appears in feedback cases: {item_id}")

    session = get_runtime_session(
        client,
        target["runtimeId"],
        target["region"],
        target["appName"],
        str(item.get("userId") or deep_get(config, "chat.user_id", "")),
        str(item.get("sessionId")),
    )
    state = session.get("state") if isinstance(session.get("state"), dict) else {}
    feedback_key = f"veadk_feedback:{item.get('messageId')}"
    feedback_state = state.get(feedback_key)
    if isinstance(feedback_state, dict) and feedback_state.get("rating") is not None:
        raise SmokeError(f"Deleted case did not clear session feedback state: {feedback_state}")
    log.ok(f"deleted case {item_id} and verified case list/session state")
    return {"itemId": item_id, "deleteResponse": response}


def verify_runtime_deleted(
    client: StudioClient,
    runtime_id: str,
    region: str,
    *,
    verify_list_absence: bool,
    scope: str,
) -> None:
    deadline = time.time() + 240
    detail_gone = False
    while time.time() < deadline:
        response: HttpResponse = client.request(
            "GET",
            f"/web/runtime-detail?runtimeId={urllib.parse.quote(runtime_id, safe='')}"
            f"&region={urllib.parse.quote(region, safe='')}",
            allow_statuses={403, 404, 502},
        )
        if response.status in {403, 404} or (
            response.status == 502 and "not found" in response.text().lower()
        ):
            detail_gone = True
            break
        time.sleep(10)
    if not detail_gone:
        raise SmokeError(f"Runtime still accessible after delete: {runtime_id}")

    if not verify_list_absence:
        return
    deadline = time.time() + 120
    while time.time() < deadline:
        runtimes = list_runtimes(client, region=region, scope=scope)
        if not any(item.get("runtimeId") == runtime_id for item in runtimes):
            return
        time.sleep(15)
    raise SmokeError(f"Runtime still appears in /web/runtimes after delete: {runtime_id}")


def delete_configured_agents(
    client: StudioClient, log: StepLogger, config: dict[str, Any]
) -> list[dict[str, Any]]:
    delete_cfg = config.get("delete_agents") or {}
    if not truthy(delete_cfg.get("enabled")):
        return []
    log.step(
        "Go back to 智能体 and delete configured agents",
        "GET /web/runtime-detail, POST /web/delete-runtime, verify AgentKit deletion",
    )
    deleted: list[dict[str, Any]] = []
    for item in delete_cfg.get("runtimes") or []:
        runtime_id = str(item.get("runtime_id") or "").strip()
        region = str(item.get("region") or deep_get(config, "target.region", "cn-beijing"))
        detail = client.json_request(
            "GET",
            f"/web/runtime-detail?runtimeId={urllib.parse.quote(runtime_id, safe='')}"
            f"&region={urllib.parse.quote(region, safe='')}",
        )
        if not isinstance(detail, dict):
            raise SmokeError(f"Runtime detail invalid before delete: {detail}")
        name = str(detail.get("name") or "")
        expected_name = str(item.get("expected_name") or "").strip()
        expected_contains = str(item.get("expected_name_contains") or "").strip()
        if expected_name and name != expected_name:
            raise SmokeError(f"Delete guard failed for {runtime_id}: {name} != {expected_name}")
        if expected_contains and expected_contains not in name:
            raise SmokeError(
                f"Delete guard failed for {runtime_id}: {expected_contains!r} not in {name!r}"
            )
        client.json_request(
            "POST",
            "/web/delete-runtime",
            {"runtimeId": runtime_id, "region": region},
        )
        if truthy(delete_cfg.get("verify_deleted"), default=True):
            verify_runtime_deleted(
                client,
                runtime_id,
                region,
                verify_list_absence=truthy(delete_cfg.get("verify_list_absence"), default=True),
                scope=str(deep_get(config, "target.scope", "mine") or "mine"),
            )
        deleted.append({"runtimeId": runtime_id, "region": region, "name": name})
        log.ok(f"deleted runtime={runtime_id} name={name}")
    return deleted


def print_plan(config: dict[str, Any]) -> None:
    print("Studio:", deep_get(config, "studio.base_url", ""))
    print("Target runtime:", deep_get(config, "target.runtime_id", "") or f"name contains {deep_get(config, 'target.name_contains', '')}")
    print("Target region:", deep_get(config, "target.region", "cn-beijing"))
    print("Delete agents enabled:", truthy(deep_get(config, "delete_agents.enabled")))


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    print_plan(config)
    if dry_run:
        return {"success": True, "dryRun": True}

    client = StudioClient(config)
    log = StepLogger()
    verify_studio_manage_ready(client, log)
    target = choose_target_runtime(client, log, config)
    draft = updated_draft(config, target)
    project = generate_update_project(client, log, draft)
    deploy_final = deploy_update(client, log, config, target, draft, project)
    updated_detail = verify_updated_version(client, log, config, target)
    target["detail"] = updated_detail
    feedback_targets = chat_and_collect_feedback_targets(client, log, config, target)
    feedback_states = submit_feedback(client, log, target, feedback_targets)
    case_results = verify_cases_page(client, log, config, target, feedback_targets)
    deleted_agents = delete_configured_agents(client, log, config)
    return {
        "success": True,
        "target": {
            "runtimeId": target["runtimeId"],
            "region": target["region"],
            "appName": target["appName"],
            "currentVersion": updated_detail.get("currentVersion"),
        },
        "deploy": {
            "runtimeId": deploy_final.get("runtimeId") or target["runtimeId"],
            "agentName": deploy_final.get("agentName"),
        },
        "feedback": feedback_states,
        "cases": {
            "matchedIds": {
                kind: item.get("id")
                for kind, item in (case_results.get("matched") or {}).items()
            },
            "deleted": case_results.get("deleted"),
        },
        "deletedAgents": deleted_agents,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to workflow config YAML.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and print planned workflow without API calls.",
    )
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
