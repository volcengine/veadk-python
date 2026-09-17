"""Loopback-only scenario controls for browser contract tests."""

from __future__ import annotations

import hmac
import json
import os
import stat
import threading
import time
from copy import deepcopy
from pathlib import Path
from re import fullmatch
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field


class ScenarioRequest(BaseModel):
    barriers: list[str] = Field(default_factory=list)


class _ScenarioState:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active = ""
        self._scenarios: dict[str, dict[str, Any]] = {}

    def replace(self, scenario: str, barriers: list[str]) -> dict[str, Any]:
        with self._condition:
            state = {
                "barriers": {name: "blocked" for name in barriers},
                "calls": {},
                "data": _default_scenario_data(scenario),
            }
            self._scenarios[scenario] = state
            self._active = scenario
            self._condition.notify_all()
            return self._copy(state)

    def get(self, scenario: str) -> dict[str, Any]:
        with self._condition:
            state = self._scenarios.get(scenario)
            if state is None:
                raise KeyError(scenario)
            return self._copy(state)

    def active(self) -> tuple[str, dict[str, Any]] | None:
        with self._condition:
            if not self._active:
                return None
            state = self._scenarios.get(self._active)
            if state is None:
                return None
            return self._active, self._copy(state)

    def names(self) -> list[str]:
        with self._condition:
            return sorted(self._scenarios)

    def count(self, scenario: str, call: str) -> int:
        with self._condition:
            state = self._require(scenario)
            calls = state["calls"]
            calls[call] = int(calls.get(call, 0)) + 1
            self._condition.notify_all()
            return int(calls[call])

    def append_payload(self, scenario: str, key: str, payload: dict[str, Any]) -> None:
        with self._condition:
            state = self._require(scenario)
            payloads = state["data"].setdefault("payloads", {})
            items = payloads.setdefault(key, [])
            items.append(deepcopy(payload))
            self._condition.notify_all()

    def release(self, scenario: str, barrier: str) -> None:
        with self._condition:
            state = self._require(scenario)
            if barrier not in state["barriers"]:
                raise KeyError(barrier)
            state["barriers"][barrier] = "released"
            if scenario == "turn_lifecycle":
                participants = state["data"].setdefault("participants", {})
                participant_id = {
                    "participant_ack": "primary",
                    "primary_ack": "primary",
                    "worker_1_ack": "worker-1",
                    "worker_2_ack": "worker-2",
                }.get(barrier)
                if participant_id and participant_id in participants:
                    participants[participant_id] = "paused"
            self._condition.notify_all()

    def wait_if_blocked(
        self, scenario: str, barrier: str, timeout: float = 30.0
    ) -> None:
        with self._condition:
            state = self._require(scenario)
            if barrier not in state["barriers"]:
                return
            deadline = time.monotonic() + timeout
            while state["barriers"].get(barrier) != "released":
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(barrier)
                self._condition.wait(timeout=remaining)

    def control(self, scenario: str) -> dict[str, Any]:
        with self._condition:
            state = self._require(scenario)
            return deepcopy(state["data"]["turnControl"])

    def control_action(
        self,
        scenario: str,
        action: str,
        *,
        idempotency_key: str,
        expected_generation: int,
    ) -> tuple[dict[str, Any], int]:
        with self._condition:
            state = self._require(scenario)
            data = state["data"]
            control = data["turnControl"]
            calls = state["calls"]
            key = f"{action}:{idempotency_key}"
            replays = data.setdefault("controlReplays", {})
            if key in replays:
                calls[f"control-{action}-replay"] = (
                    int(calls.get(f"control-{action}-replay", 0)) + 1
                )
                return deepcopy(replays[key]), 200
            calls[f"control-{action}"] = int(calls.get(f"control-{action}", 0)) + 1
            payload = {
                "action": action,
                "expectedGeneration": expected_generation,
                "idempotencyKey": idempotency_key,
            }
            data.setdefault("payloads", {}).setdefault("control", []).append(payload)
            if expected_generation != int(control["generation"]):
                return deepcopy(control), 409
            if action == "pause":
                if control["state"] != "running":
                    return deepcopy(control), 409
                control.update(
                    {
                        "state": "pausing",
                        "generation": int(control["generation"]) + 1,
                        "desiredState": "paused",
                        "allowedActions": [],
                        "resumeDisposition": "same_turn",
                    }
                )
                data["participants"] = {
                    "primary": "running",
                    "worker-1": "running",
                    "worker-2": "running",
                }
                replays[key] = deepcopy(control)
                self._condition.notify_all()
                return deepcopy(control), 200
            if action == "resume":
                if control.get("resumeDisposition") == "new_turn_required":
                    return deepcopy(control), 200
                if control["state"] != "paused":
                    return deepcopy(control), 409
                control.update(
                    {
                        "state": "running",
                        "generation": int(control["generation"]) + 1,
                        "desiredState": "running",
                        "safePoint": None,
                        "checkpoint": None,
                        "allowedActions": ["pause"],
                        "resumeDisposition": "same_turn",
                        "continuationPrompt": None,
                    }
                )
                data["participants"] = {
                    "primary": "running",
                    "worker-1": "running",
                    "worker-2": "running",
                }
                replays[key] = deepcopy(control)
                self._condition.notify_all()
                return deepcopy(control), 200
            raise ValueError(action)

    def maybe_advance_pause(self, scenario: str) -> None:
        with self._condition:
            state = self._require(scenario)
            control = state["data"]["turnControl"]
            participants = state["data"].get("participants", {})
            if (
                control["state"] == "pausing"
                and participants
                and all(value == "paused" for value in participants.values())
            ):
                control.update(
                    {
                        "state": "paused",
                        "desiredState": "paused",
                        "safePoint": "after_tool",
                        "checkpoint": {"participants": sorted(participants)},
                        "allowedActions": ["resume"],
                        "pausedAt": "2026-09-15T00:00:00Z",
                        "resumableUntil": "2026-09-15T00:05:00Z",
                        "resumeDisposition": "same_turn",
                    }
                )
                self._condition.notify_all()

    def seed_new_turn_required(self, scenario: str) -> dict[str, Any]:
        with self._condition:
            state = self._require(scenario)
            control = state["data"]["turnControl"]
            control.update(
                {
                    "state": "interrupted",
                    "generation": int(control["generation"]) + 1,
                    "desiredState": "running",
                    "allowedActions": ["resume"],
                    "pausedAt": "2026-09-15T00:00:00Z",
                    "resumableUntil": "2026-09-15T00:05:00Z",
                    "resumeDisposition": "new_turn_required",
                    "continuationPrompt": (
                        "Continue from the last safe point without repeating "
                        "completed side effects."
                    ),
                }
            )
            self._condition.notify_all()
            return deepcopy(control)

    def continue_turn(
        self,
        scenario: str,
        *,
        idempotency_key: str,
        expected_generation: int,
    ) -> tuple[dict[str, Any], int]:
        with self._condition:
            state = self._require(scenario)
            data = state["data"]
            control = data["turnControl"]
            calls = state["calls"]
            key = f"continue:{idempotency_key}"
            replays = data.setdefault("continuationReplays", {})
            if key in replays:
                calls["runtime-continue-replay"] = (
                    int(calls.get("runtime-continue-replay", 0)) + 1
                )
                return deepcopy(replays[key]), 200
            calls["runtime-continue"] = int(calls.get("runtime-continue", 0)) + 1
            data.setdefault("payloads", {}).setdefault("continue", []).append(
                {
                    "expectedGeneration": expected_generation,
                    "idempotencyKey": idempotency_key,
                }
            )
            if expected_generation != int(control["generation"]):
                return deepcopy(control), 409
            if control.get("resumeDisposition") != "new_turn_required":
                return {
                    "code": "turn_not_continuable",
                    "message": "turn_not_continuable",
                }, 409
            result = {
                "taskId": control["taskId"],
                "sessionId": data["sessionId"],
                "invocationId": f"{scenario}-continued-invocation",
                "turnId": f"{scenario}-continued-turn",
                "operationId": f"{scenario}-continued-operation",
                "executionConfigRevision": data["executionConfig"]["revision"],
                "continuationOf": f"{scenario}-turn",
                "idempotentReplay": False,
            }
            replays[key] = {**result, "idempotentReplay": True}
            data.setdefault("events", []).append(
                {
                    "id": "event-after-continue",
                    "invocationId": result["invocationId"],
                    "author": data["appName"],
                    "partial": False,
                    "content": {
                        "role": "model",
                        "parts": [{"text": "Continued after safe point"}],
                    },
                    "turnComplete": True,
                }
            )
            self._condition.notify_all()
            return result, 200

    def execution_config(self) -> dict[str, Any]:
        with self._condition:
            state = self._require_active_session()
            return deepcopy(state["data"]["executionConfig"])

    def session_events(self) -> list[dict[str, Any]]:
        with self._condition:
            state = self._require_active_session()
            return deepcopy(state["data"].get("events", []))

    def update_execution_config(
        self,
        *,
        if_match: str,
        changes: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], bool]:
        with self._condition:
            state = self._require_active_session()
            config = state["data"]["executionConfig"]
            if if_match != config["etag"]:
                return deepcopy(config), False
            next_revision = int(config["revision"]) + 1
            overrides = deepcopy(config["overrides"])
            effective_refs = deepcopy(config["effectiveRefs"])
            for change in changes:
                category = str(change.get("category") or "")
                mode = str(change.get("mode") or "")
                if category == "model":
                    if mode == "inherit":
                        overrides.pop("model", None)
                        effective_refs["model"] = {
                            "id": _profile_model_for(config["profileRevision"])
                        }
                    elif mode == "replace":
                        value = change.get("value")
                        model_id = (
                            str(value.get("id") or "").strip()
                            if isinstance(value, dict)
                            else ""
                        )
                        if model_id:
                            overrides["model"] = {
                                "mode": mode,
                                "value": {"id": model_id},
                            }
                            effective_refs["model"] = {"id": model_id}
                elif category == "mcpServers":
                    if mode == "clear":
                        overrides["mcpServers"] = {"mode": "clear"}
                        effective_refs["mcpServers"] = []
                    elif mode == "inherit":
                        overrides.pop("mcpServers", None)
                        effective_refs["mcpServers"] = _profile_mcp_for(
                            config["profileRevision"]
                        )
            config.update(
                {
                    "revision": next_revision,
                    "etag": f'"{next_revision}"',
                    "overrides": overrides,
                    "effectiveRefs": effective_refs,
                    "updatedAt": "2026-09-15T01:00:00Z",
                }
            )
            self._condition.notify_all()
            return deepcopy(config), True

    def upgrade_profile(
        self,
        *,
        if_match: str,
        idempotency_key: str,
        target_profile_revision: int,
    ) -> tuple[dict[str, Any], int, str]:
        with self._condition:
            state = self._require_active_session()
            data = state["data"]
            upgrades = data.setdefault("profileUpgrades", {})
            prior = upgrades.get(idempotency_key)
            if prior is not None:
                if int(prior["targetProfileRevision"]) != target_profile_revision:
                    return (
                        deepcopy(data["executionConfig"]),
                        409,
                        "idempotency_mismatch",
                    )
                return deepcopy(prior["result"]), 200, ""
            config = data["executionConfig"]
            if if_match != config["etag"]:
                return deepcopy(config), 412, "execution_config_changed"
            latest = int(data["latestProfileRevision"])
            current = int(config["profileRevision"])
            if target_profile_revision <= current:
                return deepcopy(config), 409, "downgrade_not_allowed"
            if target_profile_revision != latest:
                return deepcopy(config), 409, "profile_revision_unavailable"
            next_revision = int(config["revision"]) + 1
            effective_refs = deepcopy(config["effectiveRefs"])
            if "model" not in config["overrides"]:
                effective_refs["model"] = {
                    "id": _profile_model_for(target_profile_revision)
                }
            if "mcpServers" not in config["overrides"]:
                effective_refs["mcpServers"] = _profile_mcp_for(target_profile_revision)
            config.update(
                {
                    "revision": next_revision,
                    "etag": f'"{next_revision}"',
                    "profileRevision": target_profile_revision,
                    "profileDefaultRevision": target_profile_revision,
                    "effectiveRefs": effective_refs,
                    "updatedAt": "2026-09-15T01:00:00Z",
                }
            )
            result = deepcopy(config)
            upgrades[idempotency_key] = {
                "targetProfileRevision": target_profile_revision,
                "result": result,
            }
            self._condition.notify_all()
            return result, 200, ""

    def _require(self, scenario: str) -> dict[str, Any]:
        state = self._scenarios.get(scenario)
        if state is None:
            raise KeyError(scenario)
        return state

    def _require_active_session(self) -> dict[str, Any]:
        if self._active not in {
            "session_revision_6",
            "cursor_expired",
            "turn_lifecycle",
        }:
            raise KeyError(self._active)
        return self._require(self._active)

    @staticmethod
    def _copy(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "barriers": dict(state["barriers"]),
            "calls": dict(state["calls"]),
            "data": deepcopy(state["data"]),
        }


def _read_token(path: Path) -> str:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("scenario token file must have mode 0600")
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("scenario token file must not be empty")
    return token


def _profile_model_for(profile_revision: int) -> str:
    return "model-upgraded" if profile_revision >= 7 else "model-base"


def _profile_mcp_for(profile_revision: int) -> list[dict[str, str]]:
    if profile_revision >= 7:
        return [{"id": "mcp-upgraded"}]
    return [{"id": "mcp-default"}]


def _default_execution_config(session_id: str = "session-s2") -> dict[str, Any]:
    return {
        "appName": "a2a-default",
        "sessionId": session_id,
        "revision": 6,
        "etag": '"6"',
        "mpaInstanceId": "runtime-mpa-s2",
        "profileRevision": 6,
        "profileDefaultRevision": 6,
        "overrides": {},
        "effectiveRefs": {
            "model": {"id": _profile_model_for(6)},
            "mcpServers": _profile_mcp_for(6),
        },
        "invalidRefs": [],
        "updatedBy": "scenario-user",
        "createdAt": "2026-09-15T00:00:00Z",
        "updatedAt": "2026-09-15T00:00:00Z",
    }


def _default_scenario_data(scenario: str) -> dict[str, Any]:
    session_id = (
        "session-s2" if scenario == "session_revision_6" else f"{scenario}-session"
    )
    data = {
        "runtimeId": "runtime-mpa-s2",
        "runtimeName": "MPA S2 Fixture",
        "region": "cn-beijing",
        "appName": "a2a-default",
        "sessionId": session_id,
        "profileRevision": 6,
        "latestProfileRevision": 7,
        "executionConfig": _default_execution_config(session_id),
        "profileUpgrades": {},
        "events": [],
        "payloads": {},
        "turnControl": {
            "taskId": f"{scenario}-task",
            "state": "running",
            "generation": 0,
            "desiredState": "running",
            "safePoint": None,
            "checkpoint": None,
            "allowedActions": ["pause"],
            "idempotentReplay": False,
            "pausedAt": None,
            "resumableUntil": None,
            "resumeDisposition": "same_turn",
            "continuationPrompt": None,
        },
        "participants": {
            "primary": "running",
            "worker-1": "running",
            "worker-2": "running",
        },
    }
    if scenario == "cursor_expired":
        data["events"] = [
            {
                "id": "event-before-refresh",
                "author": data["appName"],
                "partial": False,
                "content": {
                    "role": "model",
                    "parts": [{"text": "Before refresh"}],
                },
                "turnComplete": True,
            }
        ]
    return data


def _runtime_item(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": data["runtimeName"],
        "runtimeId": data["runtimeId"],
        "status": "Ready",
        "createdAt": "2026-09-15T00:00:00Z",
        "description": "Browser scenario MPA Runtime",
        "cpuMilli": 2000,
        "memoryMb": 4096,
        "currentVersion": data["latestProfileRevision"],
        "agentCategory": "mpa",
        "region": data["region"],
        "author": "scenario-user",
        "isMine": True,
        "canDelete": False,
        "canManage": True,
        "canPublish": False,
        "visibility": "private",
        "reviewStatus": "",
    }


def _agent_info(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "appName": data["appName"],
        "name": data["runtimeName"],
        "description": "Browser scenario MPA Agent",
        "type": "llm",
        "model": _profile_model_for(data["profileRevision"]),
        "selectableModels": ["model-base", "model-upgraded", "model-browser-a"],
        "turnLifecycleControl": (
            {
                "actions": ["pause", "resume"],
                "pauseMode": "cooperative-safe-point",
                "processReplacementResume": False,
            }
            if data["sessionId"].startswith("turn_lifecycle-")
            else None
        ),
        "resourceTopology": None,
        "tools": [],
        "skills": [],
        "skillsPreviewSupported": True,
        "subAgents": [],
        "components": [],
        "searchSources": [],
    }


def _adk_session(
    data: dict[str, Any], user_id: str = "scenario-user"
) -> dict[str, Any]:
    return {
        "id": data["sessionId"],
        "userId": user_id,
        "lastUpdateTime": 1789490000,
        "events": deepcopy(data.get("events", [])),
        "state": {},
    }


def mount_test_scenario_routes(app: FastAPI, *, token_file: Path) -> bool:
    """Mount test routes only when both isolation switches are explicit."""
    if not (
        os.environ.get("APP_ENV") == "test"
        and os.environ.get("VEADK_MPA_TEST_SCENARIOS") == "1"
    ):
        return False
    token = _read_token(token_file)
    state = _ScenarioState()

    def authorize_loopback(request: Request) -> None:
        remote = request.headers.get("X-MPA-Test-Remote-Addr")
        if remote is None and request.client is not None:
            remote = request.client.host
        if remote not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(status_code=403, detail="loopback_required")

    def authorize(request: Request) -> None:
        authorize_loopback(request)
        supplied = request.headers.get("Authorization", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="invalid_scenario_token")

    def active_mpa_scenario(
        request: Request,
    ) -> tuple[str, dict[str, Any]] | None:
        authorize_loopback(request)
        active = state.active()
        if active is None or active[0] not in {
            "session_revision_6",
            "cursor_expired",
            "turn_lifecycle",
        }:
            return None
        return active[0], active[1]["data"]

    def active_s2_data(request: Request) -> dict[str, Any] | None:
        active = active_mpa_scenario(request)
        if active is None or active[0] != "session_revision_6":
            return None
        return active[1]

    def active_mpa_data(request: Request) -> dict[str, Any] | None:
        active = active_mpa_scenario(request)
        if active is None:
            return None
        return active[1]

    def current_state_response(
        config: dict[str, Any], status_code: int, code: str
    ) -> JSONResponse:
        return JSONResponse(
            {
                "detail": {
                    "code": code,
                    "message": code,
                    "requestId": "scenario-request",
                    "currentState": config,
                }
            },
            status_code=status_code,
        )

    @app.get("/web/runtimes")
    def fixture_runtimes(request: Request, agentCategory: str = "") -> dict[str, Any]:
        active = active_mpa_scenario(request)
        if active is None:
            return {"runtimes": [], "nextToken": ""}
        scenario, data = active
        category = agentCategory.strip().lower()
        if category and category != "mpa":
            return {"runtimes": [], "nextToken": ""}
        state.count(scenario, "runtime-list")
        return {"runtimes": [_runtime_item(data)], "nextToken": ""}

    @app.get("/web/runtime-detail")
    def fixture_runtime_detail(
        request: Request,
        runtimeId: str = "",
        region: str = "",
    ) -> dict[str, Any]:
        data = active_mpa_data(request)
        if data is None or runtimeId != data["runtimeId"]:
            raise HTTPException(status_code=404, detail="runtime_not_found")
        return {
            "runtimeId": data["runtimeId"],
            "name": data["runtimeName"],
            "description": "Browser scenario MPA Runtime",
            "status": "Ready",
            "statusMessage": "",
            "model": _profile_model_for(data["profileRevision"]),
            "project": "mpa-s2-browser",
            "region": region or data["region"],
            "createdAt": "2026-09-15T00:00:00Z",
            "updatedAt": "2026-09-15T00:00:00Z",
            "currentVersion": data["latestProfileRevision"],
            "resources": {},
            "envs": [],
            "memoryId": "",
            "toolId": "",
            "knowledgeId": "",
            "mcpToolsetId": "",
            "artifactUrl": "",
            "artifactType": "",
            "networkTypes": ["public"],
            "endpoint": "http://127.0.0.1/scenario-runtime",
            "authType": "custom_jwt",
        }

    @app.get("/web/runtime-update-capability")
    def fixture_runtime_update_capability(
        request: Request,
        runtimeId: str = "",
        region: str = "",
        appName: str = "",
    ) -> dict[str, Any]:
        data = active_mpa_data(request)
        if data is None or runtimeId != data["runtimeId"]:
            raise HTTPException(status_code=404, detail="runtime_not_found")
        return {
            "canUpdate": True,
            "reason": "",
            "recoveryStatus": "complete",
            "editMode": "source-preserving",
            "recoverySource": "agent-info",
            "warnings": [],
            "etag": '"7"',
            "runtime": {
                "runtimeId": data["runtimeId"],
                "name": data["runtimeName"],
                "region": region or data["region"],
                "currentVersion": data["latestProfileRevision"],
                "envs": [],
                "configuredEnvKeys": [],
                "network": {"type": "public"},
            },
            "agent": _agent_info({**data, "appName": appName or data["appName"]}),
        }

    @app.get("/web/workspaces")
    def fixture_workspaces(request: Request) -> dict[str, Any]:
        if active_mpa_data(request) is None:
            return {"items": []}
        return {"items": []}

    @app.get("/web/v3/environments")
    def fixture_environments(request: Request) -> dict[str, Any]:
        if active_mpa_data(request) is None:
            return {"items": []}
        return {"items": []}

    @app.get("/web/runtime-tool-channel/{runtime_id}/capabilities")
    def fixture_runtime_tool_capabilities(
        runtime_id: str,
        request: Request,
    ) -> dict[str, Any]:
        data = active_mpa_data(request)
        if data is None or runtime_id != data["runtimeId"]:
            raise HTTPException(status_code=404, detail="runtime_not_found")
        return {
            "enabled": False,
            "supported": False,
            "tools": [],
        }

    @app.get("/web/evaluation/statuses")
    def fixture_evaluation_statuses(
        request: Request,
        runtimeId: str = "",
        region: str = "",
        appName: str = "",
        userId: str = "",
    ) -> dict[str, Any]:
        data = active_mpa_data(request)
        if data is None or runtimeId != data["runtimeId"]:
            raise HTTPException(status_code=404, detail="runtime_not_found")
        return {
            "runtimeId": runtimeId,
            "region": region or data["region"],
            "appName": appName or data["appName"],
            "userId": userId,
            "items": [],
        }

    @app.post("/web/runtime-route-channel/{runtime_id}/connect")
    def fixture_runtime_route_channel(
        runtime_id: str,
        request: Request,
    ) -> dict[str, Any]:
        active = active_mpa_scenario(request)
        if active is None:
            raise HTTPException(status_code=404, detail="runtime_not_found")
        scenario, data = active
        if data is None or runtime_id != data["runtimeId"]:
            raise HTTPException(status_code=404, detail="runtime_not_found")
        state.count(scenario, "route-channel-connect")
        return {
            "enabled": True,
            "supported": True,
            "connected": True,
            "catalogRevision": "scenario",
        }

    @app.api_route(
        "/web/runtime-proxy/{runtime_id}/{path:path}",
        methods=["GET", "HEAD", "POST", "PATCH", "DELETE"],
    )
    async def fixture_runtime_proxy(runtime_id: str, path: str, request: Request):
        active = active_mpa_scenario(request)
        if active is None:
            raise HTTPException(status_code=404, detail="runtime_not_found")
        scenario, data = active
        if data is None or runtime_id != data["runtimeId"]:
            raise HTTPException(status_code=404, detail="runtime_not_found")
        if request.method == "GET" and path == "list-apps":
            state.count(scenario, "list-apps")
            return [data["appName"]]
        if request.method == "GET" and path == f"web/agent-info/{data['appName']}":
            return _agent_info(data)
        if request.method == "GET" and path == f"web/agent-draft/{data['appName']}":
            return {
                "draft": {
                    "name": data["runtimeName"],
                    "description": "Browser scenario MPA Agent",
                    "instruction": "Use the scenario fixture.",
                    "modelName": _profile_model_for(data["profileRevision"]),
                    "agentType": "llm",
                }
            }
        profile_status_match = fullmatch(
            rf"api/v1/agents/{data['runtimeId']}/profile-status",
            path,
        )
        if request.method == "GET" and profile_status_match:
            state.count(scenario, "runtime-profile-status")
            return {
                "operationId": "scenario-profile",
                "status": "applied",
                "profileRevision": data["latestProfileRevision"],
                "runtimeRevision": str(data["latestProfileRevision"]),
                "etag": f'"{data["latestProfileRevision"]}"',
            }
        if request.method == "POST" and path == "api/v1/sessions":
            state.count(scenario, "runtime-session-create")
            payload = await request.json()
            if scenario == "cursor_expired":
                state.append_payload(scenario, "session-create", payload)
            return {
                "sessionId": data["sessionId"],
                "id": data["sessionId"],
                "appName": data["appName"],
                "userId": "scenario-user",
                "mpaInstanceId": data["runtimeId"],
                "profileRevision": payload.get(
                    "profileRevision", data["profileRevision"]
                ),
            }
        session_detail_match = fullmatch(
            rf"api/v1/sessions/{data['sessionId']}",
            path,
        )
        if request.method == "GET" and session_detail_match:
            state.count(scenario, "runtime-session-read")
            return _adk_session(data)
        control_by_session_match = fullmatch(
            rf"api/v1/a2a/tasks/by-session/{data['sessionId']}/control",
            path,
        )
        if request.method == "GET" and control_by_session_match:
            state.count(scenario, "runtime-control-status")
            state.maybe_advance_pause(scenario)
            return state.control(scenario)
        control_by_task_match = fullmatch(
            rf"api/v1/a2a/tasks/{data['turnControl']['taskId']}/control",
            path,
        )
        if request.method == "GET" and control_by_task_match:
            state.count(scenario, "runtime-control-status")
            state.maybe_advance_pause(scenario)
            return state.control(scenario)
        control_action_match = fullmatch(
            rf"api/v1/a2a/tasks/by-session/{data['sessionId']}/control/(pause|resume)",
            path,
        ) or fullmatch(
            rf"api/v1/a2a/tasks/{data['turnControl']['taskId']}/control/(pause|resume)",
            path,
        )
        if request.method == "POST" and control_action_match:
            payload = await request.json()
            idempotency_key = request.headers.get("Idempotency-Key", "").strip()
            result, status_code = state.control_action(
                scenario,
                control_action_match.group(1),
                idempotency_key=idempotency_key,
                expected_generation=int(payload.get("expectedGeneration", -1)),
            )
            if status_code >= 400:
                return JSONResponse({"detail": result}, status_code=status_code)
            return result
        continue_match = fullmatch(
            rf"api/v1/a2a/tasks/{data['turnControl']['taskId']}/continue",
            path,
        )
        if request.method == "POST" and continue_match:
            payload = await request.json()
            idempotency_key = request.headers.get("Idempotency-Key", "").strip()
            result, status_code = state.continue_turn(
                scenario,
                idempotency_key=idempotency_key,
                expected_generation=int(payload.get("expectedGeneration", -1)),
            )
            if status_code >= 400:
                return JSONResponse({"detail": result}, status_code=status_code)
            return result
        sessions_match = fullmatch(
            rf"apps/{data['appName']}/users/([^/]+)/sessions(?:/([^/]+))?",
            path,
        )
        if sessions_match:
            user_id = sessions_match.group(1)
            requested_session_id = sessions_match.group(2)
            if requested_session_id and requested_session_id != data["sessionId"]:
                raise HTTPException(status_code=404, detail="session_not_found")
            if request.method == "POST":
                state.count(scenario, "session-create")
                return _adk_session(data, user_id)
            if request.method == "GET":
                return (
                    _adk_session(data, user_id)
                    if requested_session_id
                    else [_adk_session(data, user_id)]
                )
        run_match = fullmatch(
            rf"api/v1/sessions/{data['sessionId']}/run",
            path,
        )
        if request.method == "POST" and run_match:
            state.count(scenario, "runtime-run")
            payload = await request.json()
            if scenario == "cursor_expired":
                state.append_payload(scenario, "run", payload)
            return {
                "sessionId": data["sessionId"],
                "invocationId": f"{scenario}-invocation",
                "turnId": f"{scenario}-turn",
                "operationId": f"{scenario}-operation",
                "executionConfigRevision": int(
                    payload.get("executionConfigVersion")
                    or data["executionConfig"]["revision"]
                ),
            }
        sse_match = fullmatch(
            rf"api/v1/sessions/{data['sessionId']}/sse",
            path,
        )
        if request.method == "POST" and sse_match:
            state.count(scenario, "runtime-sse")
            payload = await request.json()
            if scenario == "cursor_expired":
                state.append_payload(scenario, "sse", payload)
                last_event_id = str(payload.get("lastEventId") or "")
                known_event_ids = {
                    str(event.get("id"))
                    for event in state.session_events()
                    if event.get("id")
                }
                if last_event_id and last_event_id not in known_event_ids:
                    return JSONResponse(
                        {
                            "detail": {
                                "code": "cursor_expired",
                                "message": "cursor_expired",
                            }
                        },
                        status_code=410,
                    )

            async def body():
                if (
                    scenario == "turn_lifecycle"
                    and payload.get("invocationId")
                    == "turn_lifecycle-continued-invocation"
                ):
                    yield (
                        'data: {"partial":false,"id":"event-after-continue",'
                        '"invocationId":"turn_lifecycle-continued-invocation",'
                        '"content":{"parts":[{"text":"Continued after safe point"}]},'
                        '"turnComplete":true}\n\n'
                    ).encode("utf-8")
                    return
                events = (
                    state.session_events()
                    if scenario in {"cursor_expired", "turn_lifecycle"}
                    else []
                )
                last_event_id = str(payload.get("lastEventId") or "")
                if not last_event_id:
                    for event in events:
                        yield f"data: {json.dumps(event)}\n\n".encode("utf-8")
                event = {
                    "id": "event-after-refresh",
                    "invocationId": f"{scenario}-invocation",
                    "author": data["appName"],
                    "partial": False,
                    "content": {
                        "role": "model",
                        "parts": [{"text": "After refresh"}],
                    },
                    "turnComplete": True,
                }
                yield f"data: {json.dumps(event)}\n\n".encode("utf-8")

            return StreamingResponse(body(), media_type="text/event-stream")
        if request.method == "POST" and path == "run_sse":
            state.count(scenario, "run-sse")

            async def body():
                event = {
                    "id": "scenario-event-1",
                    "author": data["appName"],
                    "partial": False,
                    "content": {
                        "role": "model",
                        "parts": [{"text": "Scenario response"}],
                    },
                    "turnComplete": True,
                }
                yield f"data: {json.dumps(event)}\\n\\n".encode("utf-8")

            return StreamingResponse(body(), media_type="text/event-stream")
        raise HTTPException(status_code=404, detail="scenario_runtime_path_not_found")

    @app.get("/web/mpa/agents/{mpa_instance_id}/profile-status")
    def fixture_profile_status(
        mpa_instance_id: str,
        request: Request,
        response: Response,
    ) -> dict[str, Any]:
        data = active_mpa_data(request)
        if data is None or mpa_instance_id != data["runtimeId"]:
            raise HTTPException(status_code=404, detail="profile_status_not_found")
        etag = f'"{data["latestProfileRevision"]}"'
        response.headers["ETag"] = etag
        return {
            "operationId": "scenario-profile",
            "status": "applied",
            "profileRevision": data["latestProfileRevision"],
            "runtimeRevision": str(data["latestProfileRevision"]),
            "etag": etag,
        }

    @app.get("/web/mpa/sessions/{session_id}/execution-config")
    def fixture_get_execution_config(
        session_id: str,
        request: Request,
        response: Response,
    ) -> dict[str, Any]:
        data = active_mpa_data(request)
        if data is None or session_id != data["sessionId"]:
            raise HTTPException(status_code=404, detail="execution_config_not_found")
        config = state.execution_config()
        response.headers["ETag"] = config["etag"]
        return config

    @app.patch("/web/mpa/sessions/{session_id}/execution-config")
    async def fixture_patch_execution_config(
        session_id: str,
        request: Request,
        response: Response,
    ) -> Any:
        data = active_s2_data(request)
        if data is None or session_id != data["sessionId"]:
            raise HTTPException(status_code=404, detail="execution_config_not_found")
        if_match = request.headers.get("If-Match", "").strip()
        if not if_match:
            raise HTTPException(
                status_code=428,
                detail={
                    "code": "precondition_required",
                    "message": "precondition_required",
                },
            )
        payload = await request.json()
        changes = payload.get("changes") if isinstance(payload, dict) else None
        if not isinstance(changes, list):
            raise HTTPException(status_code=400, detail="changes must be an array")
        call = "config-patch"
        if any(
            isinstance(change, dict) and change.get("category") == "model"
            for change in changes
        ):
            call = "config-patch-a"
        elif any(
            isinstance(change, dict) and change.get("category") == "mcpServers"
            for change in changes
        ):
            call = "config-patch-b"
        state.count("session_revision_6", call)
        try:
            state.wait_if_blocked("session_revision_6", call)
        except TimeoutError as error:
            raise HTTPException(
                status_code=504, detail="scenario_barrier_timeout"
            ) from error
        config, updated = state.update_execution_config(
            if_match=if_match,
            changes=changes,
        )
        if not updated:
            return current_state_response(config, 412, "execution_config_changed")
        response.headers["ETag"] = config["etag"]
        return config

    @app.post("/web/mpa/sessions/{session_id}/profile-upgrade")
    async def fixture_profile_upgrade(
        session_id: str,
        request: Request,
        response: Response,
    ) -> Any:
        data = active_s2_data(request)
        if data is None or session_id != data["sessionId"]:
            raise HTTPException(status_code=404, detail="execution_config_not_found")
        if_match = request.headers.get("If-Match", "").strip()
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "idempotency_key_required",
                    "message": "idempotency_key_required",
                },
            )
        if not if_match:
            raise HTTPException(
                status_code=428,
                detail={
                    "code": "precondition_required",
                    "message": "precondition_required",
                },
            )
        payload = await request.json()
        target_revision = (
            int(payload.get("targetProfileRevision", 0))
            if isinstance(payload, dict)
            else 0
        )
        state.count("session_revision_6", "profile-upgrade")
        try:
            state.wait_if_blocked("session_revision_6", "profile-upgrade")
        except TimeoutError as error:
            raise HTTPException(
                status_code=504, detail="scenario_barrier_timeout"
            ) from error
        config, status_code, code = state.upgrade_profile(
            if_match=if_match,
            idempotency_key=idempotency_key,
            target_profile_revision=target_revision,
        )
        if status_code == 412:
            return current_state_response(config, status_code, code)
        if status_code >= 400:
            raise HTTPException(
                status_code=status_code,
                detail={"code": code, "message": code},
            )
        response.headers["ETag"] = config["etag"]
        return config

    @app.get("/__test/mpa/scenarios")
    def list_scenarios(request: Request) -> dict[str, Any]:
        authorize(request)
        return {"scenarios": state.names()}

    @app.put("/__test/mpa/scenarios/{scenario}")
    def put_scenario(
        scenario: str, payload: ScenarioRequest, request: Request
    ) -> dict[str, Any]:
        authorize(request)
        return state.replace(scenario, payload.barriers)

    @app.get("/__test/mpa/scenarios/{scenario}")
    def get_scenario(scenario: str, request: Request) -> dict[str, Any]:
        authorize(request)
        try:
            return state.get(scenario)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="scenario_not_found") from error

    @app.post("/__test/mpa/scenarios/{scenario}/calls/{call}")
    def record_call(scenario: str, call: str, request: Request) -> dict[str, int]:
        authorize(request)
        try:
            return {"count": state.count(scenario, call)}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="scenario_not_found") from error

    @app.post("/__test/mpa/scenarios/{scenario}/barriers/{barrier}/release")
    def release_barrier(
        scenario: str, barrier: str, request: Request
    ) -> dict[str, bool]:
        authorize(request)
        try:
            state.release(scenario, barrier)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="barrier_not_found") from error
        return {"released": True}

    @app.post("/__test/mpa/scenarios/{scenario}/new-turn-required")
    def seed_new_turn_required(scenario: str, request: Request) -> dict[str, Any]:
        authorize(request)
        try:
            return state.seed_new_turn_required(scenario)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="scenario_not_found") from error

    return True
