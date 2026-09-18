#!/usr/bin/env python3
"""Live VC-21 driver for an isolated AgentKit MPA Runtime."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import httpx

from veadk.cli.mpa_p0_contract import (
    default_mpa_p0_manifest,
    evaluate_mpa_p0_compatibility,
    load_default_matrix,
)


SOURCE_RUNTIME_ID = os.getenv(
    "VEADK_MPA_P0_SOURCE_RUNTIME_ID", "r-yeuujrrcowb21078p9jh"
)
STUDIO_URL = os.getenv(
    "VEADK_MPA_P0_STUDIO_URL", "http://127.0.0.1:8000"
).rstrip("/")
LOCAL_USER = os.getenv("VEADK_MPA_P0_LOCAL_USER", "mpa-p0-e2e")
_SECRET_KEYS = {
    "authorization",
    "apikey",
    "cookie",
    "env",
    "envs",
    "password",
    "runtimeapikey",
    "secret",
    "secretkey",
    "token",
}
_SAFE_ERROR_FRAGMENT = re.compile(r"[^a-z0-9]+")
_PROVIDER_CODE_PATTERNS = (
    re.compile(r'\"Code\"\s*:\s*\"([A-Za-z][A-Za-z0-9_.-]{0,127})\"'),
    re.compile(
        r"\b(?:error_code)[=: ]+"
        r"([A-Za-z][A-Za-z0-9_.-]{0,127})\b",
        re.I,
    ),
)
_EXCEPTION_TYPE = re.compile(
    r"(?:^|[.:\s])([A-Z][A-Za-z0-9_]*(?:Error|Exception|Unavailable))(?=[:\s]|$)",
    re.M,
)
_WORKER_STAGE = re.compile(
    r"\bstage[=: ]+(sandbox_prepare|ready|session|turn|events)\b", re.I
)
_TOOL_API_ACTION = re.compile(
    r"\baction[=: ]+(list_sessions|create_session|delete_session)\b", re.I
)
_TOOL_AUTH_MODE = re.compile(r"\btool_auth_mode[=: ]+(auto|openapi|tip)\b", re.I)
_TOOL_PROVIDER_CODE = re.compile(
    r"\bprovider_code[=: ]+([A-Za-z][A-Za-z0-9_.-]{0,127})\b", re.I
)
_SANDBOX_STAGE = re.compile(
    r"\bsandbox_stage[=: ]+([A-Za-z][A-Za-z0-9_.-]{0,127})\b", re.I
)
_HTTP_STATUS = re.compile(r"\bhttp_status[=: ]+([1-5][0-9]{2})\b", re.I)
_WORKER_PHASE = re.compile(
    r"\bworker_phase[=: ]+([A-Za-z][A-Za-z0-9_.-]{0,127})\b", re.I
)
_KNOWN_RUNTIME_REASONS = {
    "authentication_failed": (
        "authentication failed",
        "invalid credential",
        "signaturedoesnotmatch",
    ),
    "endpoint_unavailable": (
        "endpoint is unavailable",
        "endpoint unavailable",
        "no available endpoint",
    ),
    "invalid_parameter": ("invalidparameter", "invalid parameter"),
    "network_unavailable": (
        "connection refused",
        "network is unreachable",
        "name or service not known",
    ),
    "permission_denied": (
        "accessdenied",
        "permission denied",
        "forbidden",
        "unauthorized",
    ),
    "quota_exceeded": ("quotaexceeded", "quota exceeded"),
    "request_timeout": ("timed out", "timeout"),
    "tool_not_found": ("toolnotfound", "tool not found"),
}
_TOOL_ASSOCIATION_STABILIZATION_SECONDS = 30


class VC21DriverError(RuntimeError):
    """A live-driver failure whose code is safe to persist as evidence."""

    def __init__(self, safe_error_code: str) -> None:
        super().__init__(safe_error_code)
        self.safe_error_code = safe_error_code


def _http_error_code(prefix: str, status_code: int) -> str:
    normalized = _SAFE_ERROR_FRAGMENT.sub("_", prefix.casefold()).strip("_")
    return f"{normalized}_http_{status_code}"


def isolated_runtime_env(
    source: Mapping[str, str],
    *,
    mpa_instance_id: str,
    database_name: str,
    runtime_name: str,
    tool_id: str,
) -> dict[str, str]:
    """Copy source configuration while replacing all tenant identities."""
    result = {str(key): str(value) for key, value in source.items()}
    result.update(
        {
            "MPA_AGENT_ID": mpa_instance_id,
            "CLAW_SPACE_ID": mpa_instance_id,
            "PGDATABASE": database_name,
            "A2A_PUBLIC_URL": "https://pending.invalid",
            "CODEX_MCP_RUNTIME_API_KEY": "pending",
            "AGENTKIT_TOOL_ID": tool_id,
            "MPA_CODEX_WORKER_TOOL_ID": tool_id,
            "MPA_CODEX_WORKER_TOOL_AUTH_MODE": "openapi",
            "OTEL_SERVICE_NAME": runtime_name,
            "OTEL_RESOURCE_ATTRIBUTES": (
                f"service.name={runtime_name},mpa.instance.id={mpa_instance_id}"
            ),
        }
    )
    return result


def safe_evidence(value: Any) -> Any:
    """Recursively remove fields that could contain credentials."""
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).replace("-", "").replace("_", "").casefold()
            if normalized in _SECRET_KEYS:
                continue
            result[str(key)] = safe_evidence(item)
        return result
    if isinstance(value, list):
        return [safe_evidence(item) for item in value]
    return value


def classify_runtime_logs(logs: str) -> dict[str, list[str]]:
    """Reduce Runtime logs to bounded, credential-free failure classes."""
    provider_codes: set[str] = set()
    for pattern in _PROVIDER_CODE_PATTERNS:
        provider_codes.update(
            code
            for code in pattern.findall(logs)
            if not code.casefold().startswith("smoke_worker_")
        )
    exception_types = set(_EXCEPTION_TYPE.findall(logs))
    worker_stages = {match.casefold() for match in _WORKER_STAGE.findall(logs)}
    tool_api_actions = {match.casefold() for match in _TOOL_API_ACTION.findall(logs)}
    tool_auth_modes = {match.casefold() for match in _TOOL_AUTH_MODE.findall(logs)}
    tool_provider_codes = {
        match for match in _TOOL_PROVIDER_CODE.findall(logs) if match != "unclassified"
    }
    sandbox_stages = {match.casefold() for match in _SANDBOX_STAGE.findall(logs)}
    http_statuses = set(_HTTP_STATUS.findall(logs))
    worker_phases = {match.casefold() for match in _WORKER_PHASE.findall(logs)}
    folded = logs.casefold()
    known_reasons = {
        reason
        for reason, markers in _KNOWN_RUNTIME_REASONS.items()
        if any(marker in folded for marker in markers)
    }
    return {
        "providerCodes": sorted(provider_codes),
        "exceptionTypes": sorted(exception_types),
        "httpStatuses": sorted(http_statuses),
        "knownReasons": sorted(known_reasons),
        "sandboxStages": sorted(sandbox_stages),
        "toolApiActions": sorted(tool_api_actions),
        "toolAuthModes": sorted(tool_auth_modes),
        "toolProviderCodes": sorted(tool_provider_codes),
        "workerPhases": sorted(worker_phases),
        "workerStages": sorted(worker_stages),
    }


def _collect_runtime_log_diagnostics(
    client: Any, runtime_id: str
) -> dict[str, list[str]]:
    """Read live instance logs without retaining their raw contents."""
    from agentkit.sdk.runtime import types as rt

    response = client.list_runtime_instances(
        rt.ListRuntimeInstancesRequest(RuntimeId=runtime_id)
    )
    combined = {
        "providerCodes": set(),
        "exceptionTypes": set(),
        "httpStatuses": set(),
        "knownReasons": set(),
        "sandboxStages": set(),
        "toolApiActions": set(),
        "toolAuthModes": set(),
        "toolProviderCodes": set(),
        "workerPhases": set(),
        "workerStages": set(),
    }
    for instance in response.instance_items or []:
        instance_name = str(getattr(instance, "instance_name", "") or "")
        if not instance_name:
            continue
        log_response = client.get_runtime_instance_logs(
            rt.GetRuntimeInstanceLogsRequest(
                RuntimeId=runtime_id,
                InstanceName=instance_name,
                Limit=1000,
            )
        )
        classified = classify_runtime_logs(str(log_response.logs or ""))
        for key, values in classified.items():
            combined[key].update(values)
    return {key: sorted(values) for key, values in combined.items()}


def _record_runtime_log_diagnostics(
    state: dict[str, Any], client: Any, *, failed_stage: str
) -> None:
    """Best-effort diagnostic capture that cannot replace the primary error."""
    try:
        diagnostics = _collect_runtime_log_diagnostics(
            client, str(state["runtimeId"])
        )
    except Exception as error:
        _record(
            state,
            failed_stage,
            event="runtime_log_diagnostics_unavailable",
            diagnosticErrorType=type(error).__name__,
        )
        return
    _record(
        state,
        failed_stage,
        event="runtime_log_diagnostics",
        diagnostics=diagnostics,
    )


def _record_runtime_smoke_diagnostics(
    state: dict[str, Any], *, failed_stage: str
) -> None:
    try:
        response = _proxy_request(
            state,
            "POST",
            "api/v1/readiness/execution-smoke",
            headers={"Idempotency-Key": f"{state['runId']}-diagnostic-smoke"},
            json={},
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        detail = payload.get("detail") if isinstance(payload, dict) else {}
        _record(
            state,
            failed_stage,
            event="runtime_smoke_diagnostics",
            httpStatus=response.status_code,
            detail=safe_evidence(detail if isinstance(detail, dict) else {}),
        )
    except Exception as error:
        _record(
            state,
            failed_stage,
            event="runtime_smoke_diagnostics_unavailable",
            diagnosticErrorType=type(error).__name__,
        )


def _runtime_execution_smoke_passed(state: Mapping[str, Any]) -> bool:
    response = _proxy_request(
        state,
        "POST",
        "api/v1/readiness/execution-smoke",
        headers={"Idempotency-Key": f"{state['runId']}-diagnostic-smoke"},
        json={},
    )
    return response.status_code == 200


def compatibility_fence(
    *,
    veadk_revision: str,
    runtime_revision: str,
    runtime_image_digest: str,
) -> dict[str, dict[str, Any]]:
    """Evaluate positive, incompatible, and malformed manifests locally."""
    manifest = default_mpa_p0_manifest(
        veadk_revision=veadk_revision,
        runtime_revision=runtime_revision,
        runtime_image_digest=runtime_image_digest,
    )
    matrix = load_default_matrix()
    incompatible = dict(manifest)
    incompatible["workerProtocol"] = "codex-v2"
    malformed = dict(manifest)
    malformed["runtimeImageDigest"] = "sha256:invalid"
    return {
        "valid": evaluate_mpa_p0_compatibility(manifest, matrix),
        "incompatible": evaluate_mpa_p0_compatibility(incompatible, matrix),
        "malformed": evaluate_mpa_p0_compatibility(malformed, matrix),
    }


def runtime_artifact_url(manifest: Mapping[str, Any]) -> str:
    """Return the exact image reference authorized by the live manifest."""
    value = manifest.get("runtimeImageUrl")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("live manifest has no Runtime image URL")
    return value.strip()


def _same_runtime_artifact(actual: object, expected: str) -> bool:
    """Compare Runtime artifact references without treating tag/digest forms as different images."""
    actual_value = str(actual or "").strip()
    expected_value = str(expected or "").strip()
    if not actual_value or not expected_value:
        return False
    if actual_value == expected_value:
        return True
    actual_without_digest = actual_value.split("@", 1)[0]
    expected_without_digest = expected_value.split("@", 1)[0]
    return actual_without_digest == expected_without_digest


def _state_path(run_id: str) -> Path:
    root = Path(__file__).resolve().parents[1]
    return root / "evidence" / "live" / run_id / "VC-21" / ".driver-state.json"


def _load_state(run_id: str) -> dict[str, Any]:
    path = _state_path(run_id)
    if not path.exists():
        return {"runId": run_id, "timeline": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("runId") != run_id:
        raise RuntimeError("VC-21 driver state is invalid")
    return payload


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path(str(state["runId"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def _record(state: dict[str, Any], stage: str, **payload: Any) -> None:
    state.setdefault("timeline", []).append(
        safe_evidence(
            {"stage": stage, "observedAt": int(time.time()), **payload}
        )
    )
    _save_state(state)


def _runtime_client(region: str) -> Any:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    return AgentkitRuntimeClient(
        access_key=os.environ["VOLCENGINE_ACCESS_KEY"],
        secret_key=os.environ["VOLCENGINE_SECRET_KEY"],
        session_token=os.getenv("VOLCENGINE_SESSION_TOKEN", ""),
        region=region,
    )


def _tool_client(region: str) -> Any:
    from agentkit.sdk.tools.client import AgentkitToolsClient

    return AgentkitToolsClient(
        access_key=os.environ["VOLCENGINE_ACCESS_KEY"],
        secret_key=os.environ["VOLCENGINE_SECRET_KEY"],
        session_token=os.getenv("VOLCENGINE_SESSION_TOKEN", ""),
        region=region,
    )


def _runtime(client: Any, runtime_id: str) -> Any:
    from agentkit.sdk.runtime import types as rt

    return client.get_runtime(rt.GetRuntimeRequest(runtime_id=runtime_id))


def _env_map(runtime: Any) -> dict[str, str]:
    return {
        str(item.key): str(item.value or "")
        for item in (getattr(runtime, "envs", None) or [])
    }


def _endpoint(runtime: Any) -> str:
    candidate = ""
    for item in getattr(runtime, "network_configurations", None) or []:
        value = str(getattr(item, "endpoint", "") or "")
        if value and not candidate:
            candidate = value
        if value and getattr(item, "network_type", "") == "public":
            return value
    return candidate


def _runtime_key(runtime: Any) -> str:
    authorizer = getattr(runtime, "authorizer_configuration", None)
    key_auth = getattr(authorizer, "key_auth", None) if authorizer else None
    return str(getattr(key_auth, "api_key", "") or "")


def _runtime_resource(state: Mapping[str, Any]) -> dict[str, str]:
    return {
        "type": "runtime",
        "id": str(state["runtimeId"]),
        "region": str(state["region"]),
    }


def _database_resource(state: Mapping[str, Any]) -> dict[str, str]:
    resource = {
        "type": "postgres_database",
        "id": str(state["databaseName"]),
        "sourceRuntimeId": SOURCE_RUNTIME_ID,
        "region": str(state["region"]),
    }
    if state.get("runtimeId"):
        resource["runtimeId"] = str(state["runtimeId"])
    return resource


def _tool_resource(state: Mapping[str, Any]) -> dict[str, str]:
    return {
        "type": "tool",
        "id": str(state["toolId"]),
        "name": str(state["toolName"]),
        "region": str(state["region"]),
    }


def _resources(state: Mapping[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if state.get("databaseName"):
        result.append(_database_resource(state))
    if state.get("toolId"):
        result.append(_tool_resource(state))
    if state.get("runtimeId"):
        result.append(_runtime_resource(state))
    return result


def _tool_env_map(tool: Any) -> dict[str, str]:
    return {
        str(item.key): str(item.value or "")
        for item in (getattr(tool, "envs", None) or [])
        if str(item.key) != "AGENTKIT_TOOL_ID"
    }


def _tool_has_runtime(tool: Any, runtime_id: str) -> bool:
    return any(
        str(getattr(item, "id", "") or "") == runtime_id
        for item in (getattr(tool, "associated_runtimes", None) or [])
    )


def _tool_association_stable(
    state: Mapping[str, Any], *, now: int | None = None
) -> bool:
    observed_at = int(state.get("toolRuntimeAssociationObservedAt") or 0)
    current = int(time.time()) if now is None else now
    return (
        observed_at > 0
        and current - observed_at >= _TOOL_ASSOCIATION_STABILIZATION_SECONDS
    )


def _ensure_isolated_tool(state: dict[str, Any], source_tool: Any) -> bool:
    """Create one worker Tool for this run and wait until it is ready."""
    from agentkit.sdk.tools import types as tt

    client = _tool_client(str(state["region"]))
    if not state.get("toolName"):
        state["toolName"] = f"{state['runtimeName']}-worker"[:128]
        _save_state(state)
    if not state.get("toolId"):
        response = client.create_tool(
            tt.CreateToolRequest(
                Name=state["toolName"],
                ToolType=str(source_tool.tool_type or "Private"),
                ProjectName=str(source_tool.project_name or "default"),
                ClientToken=secrets.token_hex(16),
                Description=f"Isolated VC-21 worker {state['runId']}",
                ImageUrl=str(source_tool.image_url),
                Command=str(source_tool.command or "/opt/gem/run.sh"),
                Port=int(source_tool.port or 8000),
                CpuMilli=int(source_tool.cpu_milli or 2000),
                MemoryMb=int(source_tool.memory_mb or 4096),
                RoleName=str(source_tool.role_name or ""),
                ApmplusEnable=bool(source_tool.apmplus_enable),
                EnableObjectSetIsolation=bool(
                    source_tool.enable_object_set_isolation
                ),
                EnableSecurity=bool(source_tool.enable_security),
                EnableSnapshot=bool(source_tool.enable_snapshot),
                UseCodingPlan=bool(source_tool.use_coding_plan),
                Envs=[
                    tt.EnvsItemForCreateTool(Key=key, Value=value)
                    for key, value in _tool_env_map(source_tool).items()
                ],
                AuthorizerConfiguration=tt.AuthorizerForCreateTool(
                    KeyAuth=tt.AuthorizerKeyAuthForCreateTool(
                        ApiKeyName=f"{state['toolName']}-{secrets.token_hex(4)}",
                        ApiKeyLocation="Header",
                    )
                ),
                NetworkConfiguration=tt.NetworkForCreateTool(
                    EnablePublicNetwork=True,
                    EnablePrivateNetwork=False,
                ),
                Tags=[
                    tt.TagsItemForCreateTool(
                        Key="veadk:e2e-run-id", Value=state["runId"]
                    )
                ],
            )
        )
        state["toolId"] = str(response.tool_id or "")
        if not state["toolId"]:
            raise RuntimeError("AgentKit did not return a Tool ID")
        _record(
            state,
            "VC21-RUNTIME-PROVISION",
            event="worker_tool_created",
            toolId=state["toolId"],
        )
        return False
    tool = client.get_tool(tt.GetToolRequest(ToolId=state["toolId"]))
    status = str(tool.status or "").casefold()
    if status in {"failed", "error", "deleted"}:
        raise RuntimeError(f"isolated worker Tool entered {status}")
    if status != "ready":
        return False
    if not state.get("toolIdentityApplied"):
        env = _tool_env_map(tool)
        env["AGENTKIT_TOOL_ID"] = str(state["toolId"])
        client.update_tool(
            tt.UpdateToolRequest(
                ToolId=state["toolId"],
                ToolType=str(tool.tool_type or "Private"),
                ImageUrl=str(tool.image_url),
                ModelAgentName=str(tool.model_agent_name or ""),
                Command=str(tool.command or "/opt/gem/run.sh"),
                Port=int(tool.port or 8000),
                CpuMilli=int(tool.cpu_milli or 2000),
                MemoryMb=int(tool.memory_mb or 4096),
                Envs=[
                    tt.EnvsItemForUpdateTool(Key=key, Value=value)
                    for key, value in env.items()
                ],
            )
        )
        state["toolIdentityApplied"] = True
        _record(
            state,
            "VC21-RUNTIME-PROVISION",
            event="worker_tool_identity_applied",
            toolId=state["toolId"],
        )
        return False
    return True


def _postgres_connect_args(env: Mapping[str, str]) -> dict[str, Any]:
    return {
        "host": env["PGHOST"],
        "port": int(env.get("PGPORT") or 5432),
        "user": env["PGUSER"],
        "password": env["PGPASSWORD"],
        "database": "postgres",
        "ssl": env.get("PGSSLMODE", "require"),
    }


async def _database_exists(env: Mapping[str, str], name: str) -> bool:
    import asyncpg

    connection = await asyncpg.connect(**_postgres_connect_args(env))
    try:
        return bool(
            await connection.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", name
            )
        )
    finally:
        await connection.close()


async def _create_database(env: Mapping[str, str], name: str) -> None:
    import asyncpg

    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name):
        raise ValueError("unsafe PostgreSQL database name")
    connection = await asyncpg.connect(**_postgres_connect_args(env))
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", name
        )
        if not exists:
            await connection.execute(f'CREATE DATABASE "{name}"')
    finally:
        await connection.close()


async def _drop_database(env: Mapping[str, str], name: str) -> None:
    import asyncpg

    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name):
        raise ValueError("unsafe PostgreSQL database name")
    connection = await asyncpg.connect(**_postgres_connect_args(env))
    try:
        await connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            name,
        )
        await connection.execute(f'DROP DATABASE IF EXISTS "{name}"')
    finally:
        await connection.close()


def _studio_request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    headers = {
        "X-VeADK-Local-User": LOCAL_USER,
        **dict(kwargs.pop("headers", {})),
    }
    return httpx.request(
        method, f"{STUDIO_URL}{path}", headers=headers, timeout=120, **kwargs
    )


def _proxy_request(
    state: Mapping[str, Any], method: str, path: str, **kwargs: Any
) -> httpx.Response:
    return _studio_request(
        method,
        f"/web/runtime-proxy/{state['runtimeId']}/{path.lstrip('/')}",
        params={"_runtime_region": state["region"], **kwargs.pop("params", {})},
        **kwargs,
    )


def _profile(state: Mapping[str, Any], source: Any) -> dict[str, Any]:
    model_id = _env_map(source).get("MODEL_AGENT_NAME", "").strip()
    if not model_id:
        raise RuntimeError("source Runtime has no MODEL_AGENT_NAME")
    return {
        "name": f"MPA P0 E2E {state['runId']}",
        "description": "Isolated VC-21 lifecycle validation Agent.",
        "system": "Complete the requested task accurately and concisely.",
        "model": {"id": model_id},
        "tools": [],
        "skills": [],
        "mcpServers": [],
        "multiagent": None,
        "metadata": {
            "validationCase": "VC-21",
            "runId": state["runId"],
        },
    }


def _operation_payload(state: Mapping[str, Any], source: Any) -> dict[str, Any]:
    return {
        "operationKind": "create",
        "runtimeId": state["runtimeId"],
        "region": state["region"],
        "mpaInstanceId": state["mpaInstanceId"],
        "sourceProfileId": f"vc21:{state['runId']}",
        "targetKey": state["mpaInstanceId"],
        "create": True,
        "profile": _profile(state, source),
    }


def _create_profile_and_prove_active_operation(
    state: dict[str, Any], source: Any
) -> dict[str, Any]:
    """Create through Studio while observing the real active-operation window."""

    def create() -> httpx.Response:
        return _studio_request(
            "POST",
            "/web/mpa/agents",
            headers={"Idempotency-Key": f"{state['runId']}-agent-create"},
            json=_operation_payload(state, source),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(create)
        deadline = time.monotonic() + 90
        active_preview: dict[str, Any] | None = None
        delete_status = 0
        while time.monotonic() < deadline and not future.done():
            status, preview = _delete_preview(state)
            if status == 200 and "active_operation" in preview.get("blockers", []):
                active_preview = preview
                deletion = _studio_request(
                    "POST",
                    "/web/delete-runtime",
                    json={
                        "runtimeId": state["runtimeId"],
                        "region": state["region"],
                        "mpaInstanceId": state["mpaInstanceId"],
                    },
                )
                delete_status = deletion.status_code
                break
            time.sleep(0.5)
        response = future.result(timeout=130)
    if response.status_code not in {200, 202}:
        raise VC21DriverError(
            _http_error_code(
                "studio_create_operation", response.status_code
            )
        )
    payload = response.json()
    if payload.get("status") != "succeeded" or payload.get("stage") != "runnable":
        stage = str(payload.get("stage") or "unknown")
        status = str(payload.get("status") or "unknown")
        if status == "failed_retryable" and stage == "smoke_running":
            try:
                if _runtime_execution_smoke_passed(state):
                    _record(
                        state,
                        "VC21-RUNTIME-PROVISION",
                        event="runtime_smoke_recovered",
                    )
                    payload = {**payload, "status": "succeeded", "stage": "runnable"}
                else:
                    raise VC21DriverError(
                        _SAFE_ERROR_FRAGMENT.sub(
                            "_",
                            f"studio_create_operation_{status}_{stage}".casefold(),
                        ).strip("_")
                    )
            except VC21DriverError:
                raise
            except Exception:
                raise VC21DriverError(
                    _SAFE_ERROR_FRAGMENT.sub(
                        "_",
                        f"studio_create_operation_{status}_{stage}".casefold(),
                    ).strip("_")
                )
        if payload.get("status") != "succeeded" or payload.get("stage") != "runnable":
            raise VC21DriverError(
                _SAFE_ERROR_FRAGMENT.sub(
                    "_", f"studio_create_operation_{status}_{stage}".casefold()
                ).strip("_")
            )
    if active_preview is None or delete_status != 409:
        raise RuntimeError("active MPA operation did not block Runtime deletion")
    state["profileRevision"] = int(payload["profileRevision"])
    state["profileRuntimeRevision"] = str(payload["runtimeRevision"])
    state["activeOperationEvidence"] = safe_evidence(
        {
            "preview": active_preview,
            "deleteStatus": delete_status,
            "operation": payload,
        }
    )
    _save_state(state)
    return safe_evidence(payload)


def _smoke(state: Mapping[str, Any], suffix: str) -> dict[str, Any]:
    response = _proxy_request(
        state,
        "POST",
        "api/v1/readiness/execution-smoke",
        headers={"Idempotency-Key": f"{state['runId']}-{suffix}"},
        json={},
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Runtime smoke failed with HTTP {response.status_code}"
        )
    payload = response.json()
    if payload.get("status") != "passed":
        raise RuntimeError("Runtime execution smoke did not pass")
    return safe_evidence(payload)


def _stage_compatibility(
    state: dict[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    result = compatibility_fence(
        veadk_revision=os.getenv(
            "VEADK_MPA_P0_VEADK_REVISION",
            "dfaf7da1".ljust(40, "0"),
        ),
        runtime_revision=os.getenv(
            "VEADK_MPA_P0_RUNTIME_REVISION",
            "eecc6e3115685e5cb86dcfbff4fb7c6ac7a10dee",
        ),
        runtime_image_digest=str(manifest["runtimeImageDigest"]),
    )
    if result["valid"].get("status") != "compatible":
        raise RuntimeError("valid compatibility manifest was rejected")
    if result["incompatible"].get("status") != "incompatible":
        raise RuntimeError("incompatible manifest crossed the mutation fence")
    if result["malformed"].get("status") != "invalid_manifest":
        raise RuntimeError("malformed manifest crossed the mutation fence")
    _record(
        state,
        "VC21-COMPATIBILITY-FENCE",
        result=result,
        mutationCount=0,
    )
    return {"status": "passed", "resources": _resources(state)}


def _stage_provision(
    state: dict[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    from agentkit.sdk.runtime import types as rt
    from agentkit.sdk.tools import types as tt

    region = str(manifest["region"])
    client = _runtime_client(region)
    source = _runtime(client, SOURCE_RUNTIME_ID)
    source_env = _env_map(source)
    source_tool = _tool_client(region).get_tool(
        tt.GetToolRequest(ToolId=str(source.tool_id))
    )
    if not state.get("databaseName"):
        suffix = re.sub(
            r"[^a-z0-9]+", "_", str(manifest["runId"]).lower()
        ).strip("_")
        state.update(
            {
                "region": region,
                "runtimeName": str(manifest["resourcePrefix"]),
                "databaseName": f"mpa_p0_e2e_{suffix}"[:63],
                "mpaInstanceId": f"mi-{str(manifest['runId']).lower()}"[:64],
            }
        )
        _save_state(state)
    if not _ensure_isolated_tool(state, source_tool):
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    if not asyncio.run(_database_exists(source_env, state["databaseName"])):
        asyncio.run(_create_database(source_env, state["databaseName"]))
        _record(
            state,
            "VC21-RUNTIME-PROVISION",
            event="database_created",
            databaseName=state["databaseName"],
        )
    if not state.get("runtimeId"):
        env = isolated_runtime_env(
            source_env,
            mpa_instance_id=state["mpaInstanceId"],
            database_name=state["databaseName"],
            runtime_name=state["runtimeName"],
            tool_id=state["toolId"],
        )
        authorizer = rt.AuthorizerForCreateRuntime(
            key_auth=rt.AuthorizerKeyAuthForCreateRuntime(
                api_key_name=(
                    f"{state['runtimeName']}-{secrets.token_hex(4)}"
                ),
                api_key_location="Header",
            )
        )
        tags = {
            "veadk:managed": "true",
            "veadk:agent-type": "mpa",
            "veadk:owner": LOCAL_USER,
            "veadk:author": LOCAL_USER,
            "veadk:mpa-instance-id": state["mpaInstanceId"],
            "veadk:e2e-run-id": state["runId"],
        }
        response = client.create_runtime(
            rt.CreateRuntimeRequest(
                Name=state["runtimeName"],
                Description=f"Isolated VC-21 run {state['runId']}",
                ArtifactType=str(source.artifact_type or "image"),
                ArtifactUrl=runtime_artifact_url(manifest),
                ToolId=str(state["toolId"]),
                RoleName=str(source.role_name),
                ProjectName=str(source.project_name or manifest["project"]),
                ClientToken=secrets.token_hex(16),
                CpuMilli=int(source.cpu_milli or 2000),
                MemoryMb=int(source.memory_mb or 4096),
                MinInstance=int(source.min_instance or 1),
                MaxInstance=int(source.max_instance or 1),
                MaxConcurrency=int(source.max_concurrency or 100),
                ApmplusEnable=bool(source.apmplus_enable),
                AuthorizerConfiguration=authorizer,
                NetworkConfiguration=rt.NetworkForCreateRuntime(
                    enable_public_network=True,
                    enable_private_network=False,
                ),
                Envs=[
                    rt.EnvsItemForCreateRuntime(key=key, value=value)
                    for key, value in env.items()
                ],
                Tags=[
                    rt.TagsItemForCreateRuntime.model_validate(
                        {"Key": key, "Value": value}
                    )
                    for key, value in tags.items()
                ],
            )
        )
        state["runtimeId"] = str(response.runtime_id)
        state["provisionPhase"] = "initial_release"
        _record(
            state,
            "VC21-RUNTIME-PROVISION",
            event="runtime_created",
            runtimeId=state["runtimeId"],
        )
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    runtime = _runtime(client, state["runtimeId"])
    status = str(runtime.status or "")
    if status in {"Failed", "Error", "Deleted"}:
        raise RuntimeError(f"isolated Runtime entered {status}")
    if status != "Ready":
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    if state.get("provisionPhase") == "initial_release":
        endpoint = _endpoint(runtime)
        runtime_key = _runtime_key(runtime)
        if not endpoint or not runtime_key:
            raise RuntimeError("Ready Runtime has no endpoint or key auth")
        env = isolated_runtime_env(
            source_env,
            mpa_instance_id=state["mpaInstanceId"],
            database_name=state["databaseName"],
            runtime_name=state["runtimeName"],
            tool_id=state["toolId"],
        )
        env["A2A_PUBLIC_URL"] = endpoint
        env["CODEX_MCP_RUNTIME_API_KEY"] = runtime_key
        client.update_runtime(
            rt.UpdateRuntimeRequest(
                RuntimeId=state["runtimeId"],
                Envs=[
                    rt.EnvsItemForUpdateRuntime(key=key, value=value)
                    for key, value in env.items()
                ],
                ReleaseEnable=True,
            )
        )
        state["provisionPhase"] = "finalizing"
        state["initialVersion"] = int(runtime.current_version_number or 0)
        _record(
            state,
            "VC21-RUNTIME-PROVISION",
            event="endpoint_finalization_requested",
            runtimeId=state["runtimeId"],
            version=state["initialVersion"],
        )
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    if int(runtime.current_version_number or 0) <= int(state["initialVersion"]):
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    tool = _tool_client(region).get_tool(
        tt.GetToolRequest(ToolId=str(state["toolId"]))
    )
    if not _tool_has_runtime(tool, str(state["runtimeId"])):
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    if not state.get("toolRuntimeAssociationObserved"):
        state["toolRuntimeAssociationObserved"] = True
        state["toolRuntimeAssociationObservedAt"] = int(time.time())
        _record(
            state,
            "VC21-RUNTIME-PROVISION",
            event="worker_tool_runtime_association_ready",
            toolId=state["toolId"],
            runtimeId=state["runtimeId"],
        )
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    if not _tool_association_stable(state):
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    if not state.get("profileRevision"):
        try:
            profile = _create_profile_and_prove_active_operation(state, source)
        except Exception:
            _record_runtime_smoke_diagnostics(
                state, failed_stage="VC21-RUNTIME-PROVISION"
            )
            _record_runtime_log_diagnostics(
                state, client, failed_stage="VC21-RUNTIME-PROVISION"
            )
            raise
        state["baselineVersion"] = int(runtime.current_version_number or 0)
        state["provisionPhase"] = "ready"
        _record(
            state,
            "VC21-RUNTIME-PROVISION",
            event="runtime_ready",
            runtimeId=state["runtimeId"],
            version=state["baselineVersion"],
            profile=profile,
            smoke={"status": "passed", "source": "create_operation"},
        )
    return {"status": "passed", "resources": _resources(state)}


def _request_same_image_update(
    client: Any, runtime: Any, state: dict[str, Any], *, description: str
) -> int:
    from agentkit.sdk.runtime import types as rt

    version = int(getattr(runtime, "current_version_number", 0) or 0)
    client.update_runtime(
        rt.UpdateRuntimeRequest(
            RuntimeId=state["runtimeId"],
            Description=description,
            ReleaseEnable=True,
        )
    )
    return version


def _stage_valid_update(
    state: dict[str, Any], _manifest: Mapping[str, Any]
) -> dict[str, Any]:
    client = _runtime_client(state["region"])
    runtime = _runtime(client, state["runtimeId"])
    if not state.get("validUpdateRequested"):
        state["validUpdateFromVersion"] = _request_same_image_update(
            client,
            runtime,
            state,
            description=f"VC-21 valid update {state['runId']}",
        )
        state["validUpdateRequested"] = True
        _record(
            state,
            "VC21-VALID-UPDATE",
            event="update_requested",
            version=state["validUpdateFromVersion"],
        )
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    if str(runtime.status or "") in {"Failed", "Error"}:
        raise RuntimeError("valid update failed")
    version = int(runtime.current_version_number or 0)
    if str(runtime.status or "") != "Ready":
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    smoke = _smoke(state, "valid-update-smoke")
    state["validUpdateVersion"] = version
    _record(
        state,
        "VC21-VALID-UPDATE",
        event="update_ready",
        version=version,
        noVersionChange=version <= int(state["validUpdateFromVersion"]),
        smoke=smoke,
    )
    return {"status": "passed", "resources": _resources(state)}


def _stage_failure_recovery(
    state: dict[str, Any], _manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Prove a provider-rejected update leaves the Runtime recoverable."""
    from agentkit.sdk.runtime import types as rt

    client = _runtime_client(state["region"])
    runtime = _runtime(client, state["runtimeId"])
    if not state.get("controlledFailureObserved"):
        try:
            client.update_runtime(
                rt.UpdateRuntimeRequest(
                    RuntimeId=f"r-vc21-missing-{state['runId']}",
                    Description="VC-21 expected missing-target failure",
                    ReleaseEnable=True,
                )
            )
        except Exception as error:
            state["controlledFailureObserved"] = True
            _record(
                state,
                "VC21-FAILURE-RECOVERY",
                event="controlled_failure",
                errorType=type(error).__name__,
                mutationAccepted=False,
            )
        else:
            raise RuntimeError("missing Runtime update was unexpectedly accepted")
    if not state.get("recoveryRequested"):
        state["recoveryFromVersion"] = _request_same_image_update(
            client,
            runtime,
            state,
            description=f"VC-21 recovered {state['runId']}",
        )
        state["recoveryRequested"] = True
        _save_state(state)
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    runtime = _runtime(client, state["runtimeId"])
    version = int(runtime.current_version_number or 0)
    if str(runtime.status or "") != "Ready":
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    smoke = _smoke(state, "recovery-smoke")
    state["recoveryVersion"] = version
    _record(
        state,
        "VC21-FAILURE-RECOVERY",
        event="recovered",
        version=version,
        noVersionChange=version <= int(state["recoveryFromVersion"]),
        smoke=smoke,
    )
    return {"status": "passed", "resources": _resources(state)}


def _stage_rollback(
    state: dict[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    from agentkit.sdk.runtime import types as rt

    client = _runtime_client(state["region"])
    runtime = _runtime(client, state["runtimeId"])
    target = int(state["baselineVersion"])
    if not state.get("rollbackRequested"):
        current_version = int(runtime.current_version_number or 0)
        runtime_ready = str(runtime.status or "") == "Ready"
        no_runtime_change_needed = runtime_ready and (
            current_version == target
            or _same_runtime_artifact(
                getattr(runtime, "artifact_url", ""),
                runtime_artifact_url(manifest),
            )
        )
        if no_runtime_change_needed:
            smoke = _smoke(state, "rollback-smoke")
            state["rollbackRequested"] = True
            state["rollbackFromVersion"] = current_version
            _record(
                state,
                "VC21-COMPATIBLE-ROLLBACK",
                event="rollback_ready",
                version=current_version,
                targetVersion=target,
                noRollbackNeeded=True,
                reason=(
                    "already_on_target_version"
                    if current_version == target
                    else "already_on_target_artifact"
                ),
                smoke=smoke,
            )
            return {"status": "passed", "resources": _resources(state)}
        client.release_runtime(
            rt.ReleaseRuntimeRequest(
                runtime_id=state["runtimeId"],
                version_number=target,
            )
        )
        state["rollbackRequested"] = True
        state["rollbackFromVersion"] = int(runtime.current_version_number or 0)
        _record(
            state,
            "VC21-COMPATIBLE-ROLLBACK",
            event="rollback_requested",
            fromVersion=state["rollbackFromVersion"],
            targetVersion=target,
        )
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    if str(runtime.status or "") != "Ready" or int(
        runtime.current_version_number or 0
    ) != target:
        return {
            "status": "pending",
            "retryAfterSeconds": 10,
            "resources": _resources(state),
        }
    smoke = _smoke(state, "rollback-smoke")
    _record(
        state,
        "VC21-COMPATIBLE-ROLLBACK",
        event="rollback_ready",
        version=target,
        smoke=smoke,
    )
    return {"status": "passed", "resources": _resources(state)}


def _delete_preview(state: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
    response = _studio_request(
        "GET",
        f"/web/mpa/agents/{state['mpaInstanceId']}/delete-preview",
        params={
            "runtimeId": state["runtimeId"],
            "region": state["region"],
        },
    )
    return response.status_code, safe_evidence(response.json())


def _stage_active_operation(
    state: dict[str, Any], _manifest: Mapping[str, Any]
) -> dict[str, Any]:
    evidence = state.get("activeOperationEvidence")
    if not isinstance(evidence, dict):
        raise RuntimeError("active operation evidence was not captured")
    if evidence.get("deleteStatus") != 409:
        raise RuntimeError("active operation deletion did not return HTTP 409")
    if "active_operation" not in evidence.get("preview", {}).get("blockers", []):
        raise RuntimeError("delete preview missed the active operation blocker")
    _record(state, "VC21-DELETE-ACTIVE-OPERATION", **evidence)
    return {"status": "passed", "resources": _resources(state)}


def _stage_active_session(
    state: dict[str, Any], _manifest: Mapping[str, Any]
) -> dict[str, Any]:
    if not state.get("sessionId"):
        created = _proxy_request(
            state,
            "POST",
            "api/v1/sessions",
            json={
                "mpaInstanceId": state["mpaInstanceId"],
                "profileRevision": state["profileRevision"],
            },
        )
        if created.status_code != 201:
            raise RuntimeError(
                f"Session create failed with HTTP {created.status_code}"
            )
        state["sessionId"] = str(created.json()["sessionId"])
        _save_state(state)
    if not state.get("activeSessionRunStarted"):
        run = _proxy_request(
            state,
            "POST",
            f"api/v1/sessions/{state['sessionId']}/run",
            headers={
                "Idempotency-Key": f"{state['runId']}-active-session"
            },
            json={
                "content": (
                    "Use the sandbox to sleep for 45 seconds, then reply done."
                ),
                "executionConfigVersion": 1,
            },
        )
        if run.status_code not in {200, 202}:
            raise RuntimeError(
                f"Session run failed with HTTP {run.status_code}"
            )
        state["activeSessionRunStarted"] = True
        _save_state(state)
    status, preview = _delete_preview(state)
    if status != 200 or "active_sessions" not in preview.get("blockers", []):
        raise RuntimeError("active Session did not block delete preview")
    deletion = _studio_request(
        "POST",
        "/web/delete-runtime",
        json={
            "runtimeId": state["runtimeId"],
            "region": state["region"],
            "mpaInstanceId": state["mpaInstanceId"],
        },
    )
    if deletion.status_code != 409:
        raise RuntimeError("active Session deletion did not return HTTP 409")
    aborted = _proxy_request(
        state,
        "POST",
        f"api/v1/sessions/{state['sessionId']}/abort",
        json={},
    )
    if aborted.status_code != 200:
        raise RuntimeError(
            f"Session abort failed with HTTP {aborted.status_code}"
        )
    _record(
        state,
        "VC21-DELETE-ACTIVE-SESSION",
        preview=preview,
        deleteStatus=deletion.status_code,
        abortStatus=aborted.status_code,
    )
    return {"status": "passed", "resources": _resources(state)}


def _stage_idle_sessions(
    state: dict[str, Any], _manifest: Mapping[str, Any]
) -> dict[str, Any]:
    deadline = time.monotonic() + 90
    while True:
        status, preview = _delete_preview(state)
        if status == 200 and "active_sessions" not in preview.get("blockers", []):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("aborted Session did not become idle")
        time.sleep(3)
    if not preview.get("sessionCounts", {}).get("total"):
        raise RuntimeError("idle Session is not visible to delete preview")
    _record(state, "VC21-DELETE-IDLE-SESSIONS", preview=preview)
    return {"status": "passed", "resources": _resources(state)}


def _stage_final_delete(
    state: dict[str, Any], _manifest: Mapping[str, Any]
) -> dict[str, Any]:
    if state.get("runtimeId") and not state.get("runtimeDeleted"):
        response = _studio_request(
            "POST",
            "/web/delete-runtime",
            json={
                "runtimeId": state["runtimeId"],
                "region": state["region"],
                "mpaInstanceId": state["mpaInstanceId"],
            },
        )
        if response.status_code not in {200, 404}:
            raise RuntimeError(
                f"Studio Runtime delete failed with HTTP {response.status_code}"
            )
        state["runtimeDeleted"] = True
        _save_state(state)
    if state.get("databaseName") and not state.get("databaseDeleted"):
        source = _runtime(
            _runtime_client(state["region"]), SOURCE_RUNTIME_ID
        )
        asyncio.run(_drop_database(_env_map(source), state["databaseName"]))
        state["databaseDeleted"] = True
        _save_state(state)
    _record(
        state,
        "VC21-FINAL-DELETE",
        runtimeId=state.get("runtimeId", ""),
        databaseName=state.get("databaseName", ""),
        status="deleted",
    )
    return {"status": "passed", "resources": []}


STAGE_HANDLERS = {
    "VC21-COMPATIBILITY-FENCE": _stage_compatibility,
    "VC21-RUNTIME-PROVISION": _stage_provision,
    "VC21-VALID-UPDATE": _stage_valid_update,
    "VC21-FAILURE-RECOVERY": _stage_failure_recovery,
    "VC21-COMPATIBLE-ROLLBACK": _stage_rollback,
    "VC21-DELETE-ACTIVE-OPERATION": _stage_active_operation,
    "VC21-DELETE-ACTIVE-SESSION": _stage_active_session,
    "VC21-DELETE-IDLE-SESSIONS": _stage_idle_sessions,
    "VC21-FINAL-DELETE": _stage_final_delete,
}


def _find_runtime_resources(prefix: str, region: str) -> list[dict[str, str]]:
    from agentkit.sdk.runtime import types as rt

    client = _runtime_client(region)
    result: list[dict[str, str]] = []
    token = ""
    for _ in range(20):
        request = rt.ListRuntimesRequest(
            page_size=100,
            next_token=token or None,
        )
        response = client.list_runtimes(request)
        for runtime in response.agent_kit_runtimes or []:
            if str(runtime.name or "").startswith(prefix):
                result.append(
                    {
                        "type": "runtime",
                        "id": str(runtime.runtime_id),
                        "region": region,
                    }
                )
        token = str(response.next_token or "")
        if not token:
            break
    return result


def _find_tool_resources(prefix: str, region: str) -> list[dict[str, str]]:
    from agentkit.sdk.tools import types as tt

    client = _tool_client(region)
    result: list[dict[str, str]] = []
    token = ""
    for _ in range(20):
        response = client.list_tools(
            tt.ListToolsRequest(
                PageSize=100,
                NextToken=token or None,
            )
        )
        for tool in response.tools or []:
            name = str(tool.name or "")
            if name.startswith(prefix):
                result.append(
                    {
                        "type": "tool",
                        "id": str(tool.tool_id),
                        "name": name,
                        "region": region,
                    }
                )
        token = str(response.next_token or "")
        if not token:
            break
    return result


def _list_resources(
    prefix: str, state: Mapping[str, Any]
) -> list[dict[str, str]]:
    region = str(state.get("region") or "cn-beijing")
    resources = _find_runtime_resources(prefix, region)
    resources.extend(_find_tool_resources(prefix, region))
    if state.get("databaseName") and not state.get("databaseDeleted"):
        try:
            source = _runtime(_runtime_client(region), SOURCE_RUNTIME_ID)
            if asyncio.run(
                _database_exists(_env_map(source), str(state["databaseName"]))
            ):
                resources.append(_database_resource(state))
        except Exception:
            resources.append(_database_resource(state))
    return resources


def _delete_resource(resource: Mapping[str, Any]) -> None:
    from agentkit.sdk.runtime import types as rt

    resource_type = str(resource.get("type") or "")
    region = str(resource.get("region") or "cn-beijing")
    if resource_type == "runtime":
        try:
            _runtime_client(region).delete_runtime(
                rt.DeleteRuntimeRequest(runtime_id=str(resource["id"]))
            )
        except Exception as error:
            detail = f"{type(error).__name__}: {error}".casefold()
            if "notfound" not in detail and "not found" not in detail:
                raise
    elif resource_type == "tool":
        from agentkit.sdk.tools import types as tt

        client = _tool_client(region)
        try:
            sessions = client.list_sessions(
                tt.ListSessionsRequest(
                    ToolId=str(resource["id"]),
                    MaxResults=100,
                )
            )
            for session in sessions.session_infos or []:
                if session.session_id:
                    client.delete_session(
                        tt.DeleteSessionRequest(
                            SessionId=str(session.session_id),
                            ToolId=str(resource["id"]),
                        )
                    )
            client.delete_tool(
                tt.DeleteToolRequest(ToolId=str(resource["id"]))
            )
        except Exception as error:
            detail = f"{type(error).__name__}: {error}".casefold()
            if "notfound" not in detail and "not found" not in detail:
                raise
    elif resource_type == "postgres_database":
        runtime_id = str(resource.get("runtimeId") or "")
        if runtime_id:
            try:
                _runtime(_runtime_client(region), runtime_id)
            except Exception as error:
                detail = f"{type(error).__name__}: {error}".casefold()
                if "notfound" not in detail and "not found" not in detail:
                    raise
            else:
                # Runtime deletion is asynchronous. Keep its database alive
                # until no instance can reconnect during termination.
                return
        source = _runtime(
            _runtime_client(region), str(resource["sourceRuntimeId"])
        )
        asyncio.run(_drop_database(_env_map(source), str(resource["id"])))


def main() -> int:
    request = json.loads(sys.stdin.read())
    command = str(request.get("command") or "")
    if command == "run_stage":
        manifest = request["manifest"]
        state = _load_state(str(manifest["runId"]))
        handler = STAGE_HANDLERS.get(str(request.get("stage") or ""))
        if handler is None:
            raise RuntimeError("unsupported VC-21 stage")
        print(json.dumps(handler(state, manifest), sort_keys=True))
        return 0
    if command == "delete_resource":
        _delete_resource(request["resource"])
        print('{"status":"deleted"}')
        return 0
    if command == "list_resources":
        prefix = str(request["resourcePrefix"])
        run_id = prefix.removeprefix("mpa-p0-e2e-")
        state = _load_state(run_id)
        print(
            json.dumps(
                {"resources": _list_resources(prefix, state)},
                sort_keys=True,
            )
        )
        return 0
    raise RuntimeError("unsupported driver command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        safe_error_code = (
            error.safe_error_code
            if isinstance(error, VC21DriverError)
            else type(error).__name__
        )
        print(
            json.dumps(
                {
                    "status": "failed",
                    "errorCode": type(error).__name__,
                    "safeErrorCode": safe_error_code,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1) from error
