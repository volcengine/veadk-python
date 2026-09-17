from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.mpa.routes import MpaRuntimeBinding, mount_mpa_profile_routes
from frontend.server.mpa.operations import MpaLifecycleOperation, MpaOperationConflict
from frontend.server.mpa.runtime_client import MpaRuntimeError


class FakeRuntimeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.sessions: list[dict[str, Any]] = []

    async def apply_profile(self, **kwargs: Any) -> Any:
        self.calls.append(("apply", kwargs))
        return {
            "operationId": "runtime-op-1",
            "status": "applied",
            "profileRevision": 3,
            "runtimeRevision": "3",
            "etag": '"3"',
        }

    async def profile_status(self, **kwargs: Any) -> Any:
        self.calls.append(("status", kwargs))
        return {
            "operationId": "runtime-op-1",
            "status": "applied",
            "profileRevision": 3,
            "runtimeRevision": "3",
            "etag": '"3"',
        }

    async def session_execution_config(self, **kwargs: Any) -> Any:
        self.calls.append(("execution_config", kwargs))
        return {
            "appName": "default",
            "sessionId": kwargs["session_id"],
            "revision": 1,
            "etag": '"1"',
            "mpaInstanceId": "mpa-1",
            "profileRevision": 3,
            "profileDefaultRevision": 3,
            "overrides": {},
            "effectiveRefs": {"mcpServers": [{"id": "ais-1"}]},
            "invalidRefs": [],
            "updatedBy": "user-1",
            "createdAt": "2026-09-15T00:00:00Z",
            "updatedAt": "2026-09-15T00:00:00Z",
        }

    async def list_sessions(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("list_sessions", kwargs))
        return list(self.sessions)

    async def delete_session(self, **kwargs: Any) -> None:
        self.calls.append(("delete_session", kwargs))

    async def patch_session_execution_config(self, **kwargs: Any) -> Any:
        self.calls.append(("patch_execution_config", kwargs))
        return {
            "appName": "default",
            "sessionId": kwargs["session_id"],
            "revision": 2,
            "etag": '"2"',
            "mpaInstanceId": "mpa-1",
            "profileRevision": 3,
            "profileDefaultRevision": 3,
            "overrides": {
                "mcpServers": {"mode": "replace", "value": [{"id": "ais-2"}]}
            },
            "effectiveRefs": {"mcpServers": [{"id": "ais-2"}]},
            "invalidRefs": [],
            "updatedBy": "user-1",
            "createdAt": "2026-09-15T00:00:00Z",
            "updatedAt": "2026-09-15T00:00:00Z",
        }

    async def upgrade_session_profile(self, **kwargs: Any) -> Any:
        self.calls.append(("upgrade_profile", kwargs))
        return {
            "appName": "default",
            "sessionId": kwargs["session_id"],
            "revision": 3,
            "etag": '"3"',
            "mpaInstanceId": "mpa-1",
            "profileRevision": kwargs["target_profile_revision"],
            "profileDefaultRevision": kwargs["target_profile_revision"],
            "overrides": {},
            "effectiveRefs": {},
            "invalidRefs": [],
            "updatedBy": "user-1",
            "createdAt": "2026-09-15T00:00:00Z",
            "updatedAt": "2026-09-15T00:00:00Z",
        }


class FailingRuntimeClient(FakeRuntimeClient):
    async def apply_profile(self, **kwargs: Any) -> Any:
        self.calls.append(("apply", kwargs))
        raise MpaRuntimeError(
            "profile_version_conflict",
            status_code=409,
            request_id="req-1",
        )


class StaleExecutionConfigRuntimeClient(FakeRuntimeClient):
    async def patch_session_execution_config(self, **kwargs: Any) -> Any:
        self.calls.append(("patch_execution_config", kwargs))
        raise MpaRuntimeError(
            "execution_config_changed",
            status_code=412,
            request_id="req-cas",
            current_state={
                "appName": "default",
                "sessionId": kwargs["session_id"],
                "revision": 2,
                "etag": '"2"',
                "mpaInstanceId": "mpa-1",
                "profileRevision": 3,
                "profileDefaultRevision": 3,
                "overrides": {},
                "effectiveRefs": {"model": {"id": "model-a"}},
                "invalidRefs": [],
            },
        )


class OrphanRuntimeClient(FakeRuntimeClient):
    async def profile_status(self, **kwargs: Any) -> Any:
        self.calls.append(("status", kwargs))
        raise MpaRuntimeError("profile_not_found", status_code=404)


class FakeOperationService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.started: list[tuple[Any, str]] = []
        self.retried: list[tuple[Any, str]] = []
        self.listed: list[str] = []

    async def start(self, request, *, idempotency_key: str) -> MpaLifecycleOperation:
        self.started.append((request, idempotency_key))
        if self.fail:
            raise MpaOperationConflict("idempotency key conflict")
        return _operation(operationId="mpaop-1", ownerId=request.owner_id)

    async def retry(self, request, *, operation_id: str) -> MpaLifecycleOperation:
        self.retried.append((request, operation_id))
        return _operation(
            operationId=operation_id, ownerId=request.owner_id, retryCount=1
        )

    async def list_active(self, owner_id: str) -> list[MpaLifecycleOperation]:
        self.listed.append(owner_id)
        return [_operation(operationId="mpaop-1", ownerId=owner_id)]


def _operation(**overrides: Any) -> MpaLifecycleOperation:
    values: dict[str, Any] = {
        "operationId": "mpaop-1",
        "operationKind": "create",
        "ownerId": "owner-1",
        "targetKey": "create:research",
        "idempotencyKeyHash": "idem-hash",
        "requestHash": "request-hash",
        "stage": "runnable",
        "status": "succeeded",
        "mpaInstanceId": "mpa-1",
        "runtimeId": "runtime-1",
        "runtimeRegion": "cn-beijing",
        "createdAt": "2026-09-15T00:00:00Z",
        "updatedAt": "2026-09-15T00:00:00Z",
    }
    values.update(overrides)
    return MpaLifecycleOperation.model_validate(values)


def _app(
    runtime_client: FakeRuntimeClient,
    *,
    authorize_error: Exception | None = None,
    operation_service: FakeOperationService | None = None,
    runtime_bindings: list[MpaRuntimeBinding] | None = None,
) -> TestClient:
    app = FastAPI()

    def authorize(_request, runtime_id: str, region: str):
        if authorize_error is not None:
            raise authorize_error
        return {"runtimeId": runtime_id, "region": region}

    def resolve(_request, _runtime_id: str, _region: str, _runtime: Any):
        return (
            "https://runtime.example",
            "runtime-secret",
            "key_auth",
            "public",
        )

    async def resolve_bindings(_request, mpa_instance_id: str, region: str):
        del mpa_instance_id, region
        return runtime_bindings

    mount_mpa_profile_routes(
        app,
        runtime_client=runtime_client,
        authorize_runtime=authorize,
        resolve_runtime_connection=resolve,
        operation_service=operation_service,
        owner_resolver=lambda _request: "owner-1",
        resolve_runtime_bindings=(
            resolve_bindings if runtime_bindings is not None else None
        ),
    )
    return TestClient(app)


def _binding(runtime_id: str, *, region: str = "cn-beijing") -> MpaRuntimeBinding:
    return MpaRuntimeBinding(
        runtime_id=runtime_id,
        region=region,
        runtime={"runtimeId": runtime_id},
        visible={
            "runtimeId": runtime_id,
            "region": region,
            "name": f"Runtime {runtime_id}",
            "status": "Ready",
            "currentVersion": 8,
            "agentCategory": "mpa",
            "isMine": True,
        },
    )


def _profile_payload() -> dict[str, Any]:
    return {
        "runtimeId": "runtime-1",
        "region": "cn-beijing",
        "mpaInstanceId": "mpa-1",
        "sourceProfileId": "draft-1",
        "create": True,
        "profile": {
            "name": "research",
            "system": "Use cited sources.",
            "model": {"id": "model-1"},
        },
    }


def test_mpa_profile_apply_route_normalizes_and_forwards_runtime_request():
    runtime_client = FakeRuntimeClient()
    client = _app(runtime_client)

    response = client.put(
        "/web/mpa/agents/mpa-1/profile",
        headers={"Idempotency-Key": "idem-1"},
        json=_profile_payload(),
    )

    assert response.status_code == 202, response.text
    assert response.headers["etag"] == '"3"'
    assert response.json()["operationId"] == "runtime-op-1"
    call = runtime_client.calls[0]
    assert call[0] == "apply"
    assert call[1]["endpoint"] == "https://runtime.example"
    assert call[1]["mpa_instance_id"] == "mpa-1"
    assert call[1]["bearer_token"] == "runtime-secret"
    assert call[1]["idempotency_key"] == "idem-1"
    assert call[1]["create"] is True
    assert call[1]["profile"].source_profile_id == "draft-1"
    assert call[1]["profile"].source_profile_digest.startswith("sha256:")


def test_mpa_profile_update_requires_runtime_revision():
    runtime_client = FakeRuntimeClient()
    client = _app(runtime_client)
    payload = {**_profile_payload(), "create": False}

    response = client.put(
        "/web/mpa/agents/mpa-1/profile",
        headers={"Idempotency-Key": "idem-1"},
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "runtimeRevision is required for update"
    assert runtime_client.calls == []


def test_mpa_profile_status_route_forwards_authorized_runtime_request():
    runtime_client = FakeRuntimeClient()
    client = _app(runtime_client)

    response = client.get(
        "/web/mpa/agents/mpa-1/profile-status",
        params={"runtimeId": "runtime-1", "region": "cn-beijing"},
    )

    assert response.status_code == 200
    assert response.headers["etag"] == '"3"'
    assert runtime_client.calls == [
        (
            "status",
            {
                "endpoint": "https://runtime.example",
                "mpa_instance_id": "mpa-1",
                "bearer_token": "runtime-secret",
            },
        )
    ]


def test_mpa_agent_view_returns_runtime_missing_with_matching_active_operation():
    operation_service = FakeOperationService()
    client = _app(
        FakeRuntimeClient(),
        operation_service=operation_service,
        runtime_bindings=[],
    )

    response = client.get("/web/mpa/agents/mpa-1/view", params={"region": "all"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mpaInstanceId"] == "mpa-1"
    assert body["bindingStatus"] == "runtime_missing"
    assert body["runtime"] is None
    assert body["profile"] is None
    assert body["activeOperation"]["operationId"] == "mpaop-1"
    assert body["capabilities"] == {
        "canRead": False,
        "canWrite": False,
        "canDebug": False,
    }
    assert body["safeError"]["code"] == "runtime_missing"
    assert operation_service.listed == ["owner-1"]


def test_mpa_agent_view_hydrates_unique_runtime_binding_and_profile_status():
    runtime_client = FakeRuntimeClient()
    binding = _binding("runtime-1")
    client = _app(
        runtime_client,
        operation_service=FakeOperationService(),
        runtime_bindings=[binding],
    )

    response = client.get("/web/mpa/agents/mpa-1/view", params={"region": "all"})

    assert response.status_code == 200, response.text
    assert response.headers["etag"] == '"3"'
    body = response.json()
    assert body["bindingStatus"] == "bound"
    assert body["runtime"]["runtimeId"] == "runtime-1"
    assert body["runtime"]["currentVersion"] == 8
    assert body["profile"]["profileRevision"] == 3
    assert body["profile"]["runtimeRevision"] == "3"
    assert body["activeOperation"]["operationId"] == "mpaop-1"
    assert body["bindings"] == []
    assert body["safeError"] is None
    assert body["capabilities"] == {
        "canRead": True,
        "canWrite": True,
        "canDebug": True,
    }
    assert runtime_client.calls == [
        (
            "status",
            {
                "endpoint": "https://runtime.example",
                "mpa_instance_id": "mpa-1",
                "bearer_token": "runtime-secret",
            },
        )
    ]


def test_mpa_agent_view_allows_profile_write_for_orphan_runtime():
    runtime_client = OrphanRuntimeClient()
    binding = _binding("runtime-1")
    client = _app(
        runtime_client,
        operation_service=FakeOperationService(),
        runtime_bindings=[binding],
    )

    response = client.get("/web/mpa/agents/mpa-1/view", params={"region": "all"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bindingStatus"] == "orphan_runtime"
    assert body["runtime"]["runtimeId"] == "runtime-1"
    assert body["profile"] is None
    assert body["capabilities"] == {
        "canRead": True,
        "canWrite": True,
        "canDebug": False,
    }
    assert body["safeError"]["code"] == "profile_not_found"


def test_mpa_agent_view_blocks_writes_when_runtime_binding_is_ambiguous():
    runtime_client = FakeRuntimeClient()
    client = _app(
        runtime_client,
        operation_service=FakeOperationService(),
        runtime_bindings=[
            _binding("runtime-1", region="cn-beijing"),
            _binding("runtime-2", region="cn-shanghai"),
        ],
    )

    response = client.get("/web/mpa/agents/mpa-1/view", params={"region": "all"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bindingStatus"] == "binding_ambiguous"
    assert body["runtime"] is None
    assert body["profile"] is None
    assert [item["runtimeId"] for item in body["bindings"]] == [
        "runtime-1",
        "runtime-2",
    ]
    assert body["capabilities"] == {
        "canRead": False,
        "canWrite": False,
        "canDebug": False,
    }
    assert body["safeError"]["code"] == "binding_ambiguous"
    assert runtime_client.calls == []


def test_mpa_agent_delete_preview_blocks_active_sessions_and_reports_cleanup_plan():
    runtime_client = FakeRuntimeClient()
    runtime_client.sessions = [
        {"sessionId": "session-running", "status": "running", "appName": "mpa"},
        {"sessionId": "session-paused", "status": "paused", "appName": "mpa"},
        {"sessionId": "session-idle", "status": "idle", "appName": "mpa"},
    ]
    client = _app(
        runtime_client,
        operation_service=FakeOperationService(),
        runtime_bindings=[_binding("runtime-1")],
    )

    response = client.get(
        "/web/mpa/agents/mpa-1/delete-preview",
        params={"runtimeId": "runtime-1", "region": "cn-beijing"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mpaInstanceId"] == "mpa-1"
    assert body["canDelete"] is False
    assert body["blockers"] == ["active_operation", "active_sessions"]
    assert body["sessionCounts"] == {
        "total": 3,
        "active": 2,
        "idle": 1,
        "debug": 0,
    }
    assert body["activeSessions"] == [
        {"sessionId": "session-running", "status": "running", "appName": "mpa"},
        {"sessionId": "session-paused", "status": "paused", "appName": "mpa"},
    ]
    assert [stage["stage"] for stage in body["cleanupPlan"]] == [
        "runtime_sessions",
        "runtime_diagnostics",
        "agentkit_runtime",
    ]
    assert runtime_client.calls == [
        (
            "status",
            {
                "endpoint": "https://runtime.example",
                "mpa_instance_id": "mpa-1",
                "bearer_token": "runtime-secret",
            },
        ),
        (
            "list_sessions",
            {
                "endpoint": "https://runtime.example",
                "bearer_token": "runtime-secret",
                "include_a2a": True,
            },
        ),
    ]


def test_mpa_agent_delete_preview_allows_visible_idle_sessions():
    runtime_client = FakeRuntimeClient()
    runtime_client.sessions = [
        {"sessionId": "session-idle", "status": "idle", "appName": "mpa"},
        {"sessionId": "session-done", "status": "completed", "appName": "mpa"},
    ]
    client = _app(
        runtime_client,
        runtime_bindings=[_binding("runtime-1")],
    )

    response = client.get(
        "/web/mpa/agents/mpa-1/delete-preview",
        params={"runtimeId": "runtime-1", "region": "cn-beijing"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["canDelete"] is True
    assert body["blockers"] == []
    assert body["sessionCounts"]["total"] == 2
    assert body["sessionCounts"]["active"] == 0
    assert body["cleanupPlan"][0]["count"] == 2


def test_mpa_agent_delete_preview_requires_single_runtime_binding():
    client = _app(
        FakeRuntimeClient(),
        runtime_bindings=[
            _binding("runtime-1", region="cn-beijing"),
            _binding("runtime-2", region="cn-shanghai"),
        ],
    )

    response = client.get(
        "/web/mpa/agents/mpa-1/delete-preview", params={"region": "all"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bindingStatus"] == "binding_ambiguous"
    assert body["canDelete"] is False
    assert body["blockers"] == ["binding_ambiguous"]


def test_mpa_agent_delete_preview_marks_orphan_runtime_from_profile_status():
    runtime_client = OrphanRuntimeClient()
    client = _app(runtime_client)

    response = client.get(
        "/web/mpa/agents/mpa-1/delete-preview",
        params={"runtimeId": "runtime-1", "region": "cn-beijing"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bindingStatus"] == "orphan_runtime"
    assert body["canDelete"] is False
    assert body["blockers"] == ["orphan_runtime"]
    assert runtime_client.calls == [
        (
            "status",
            {
                "endpoint": "https://runtime.example",
                "mpa_instance_id": "mpa-1",
                "bearer_token": "runtime-secret",
            },
        )
    ]


def test_session_execution_config_routes_forward_runtime_request():
    runtime_client = FakeRuntimeClient()
    client = _app(runtime_client)

    current = client.get(
        "/web/mpa/sessions/session-1/execution-config",
        params={"runtimeId": "runtime-1", "region": "cn-beijing"},
    )
    patched = client.patch(
        "/web/mpa/sessions/session-1/execution-config",
        headers={"If-Match": '"1"'},
        json={
            "runtimeId": "runtime-1",
            "region": "cn-beijing",
            "changes": [
                {
                    "category": "mcpServers",
                    "mode": "replace",
                    "value": [{"id": "ais-2"}],
                }
            ],
        },
    )
    upgraded = client.post(
        "/web/mpa/sessions/session-1/profile-upgrade",
        headers={"If-Match": '"2"', "Idempotency-Key": "upgrade-1"},
        json={
            "runtimeId": "runtime-1",
            "region": "cn-beijing",
            "targetProfileRevision": 4,
        },
    )

    assert current.status_code == 200, current.text
    assert current.headers["etag"] == '"1"'
    assert patched.status_code == 200, patched.text
    assert patched.headers["etag"] == '"2"'
    assert upgraded.status_code == 200, upgraded.text
    assert upgraded.headers["etag"] == '"3"'
    assert runtime_client.calls[0] == (
        "execution_config",
        {
            "endpoint": "https://runtime.example",
            "session_id": "session-1",
            "bearer_token": "runtime-secret",
        },
    )
    assert runtime_client.calls[1][0] == "patch_execution_config"
    assert runtime_client.calls[1][1]["if_match"] == '"1"'
    assert runtime_client.calls[1][1]["changes"][0].category == "mcpServers"
    assert runtime_client.calls[2][0] == "upgrade_profile"
    assert runtime_client.calls[2][1]["idempotency_key"] == "upgrade-1"
    assert runtime_client.calls[2][1]["target_profile_revision"] == 4


def test_session_execution_config_routes_validate_headers_before_runtime_call():
    runtime_client = FakeRuntimeClient()
    client = _app(runtime_client)

    missing_match = client.patch(
        "/web/mpa/sessions/session-1/execution-config",
        json={"runtimeId": "runtime-1", "changes": []},
    )
    missing_key = client.post(
        "/web/mpa/sessions/session-1/profile-upgrade",
        headers={"If-Match": '"1"'},
        json={"runtimeId": "runtime-1", "targetProfileRevision": 4},
    )

    assert missing_match.status_code == 428
    assert missing_match.json()["detail"]["code"] == "precondition_required"
    assert missing_key.status_code == 400
    assert missing_key.json()["detail"]["code"] == "idempotency_key_required"
    assert runtime_client.calls == []


def test_session_execution_config_conflict_forwards_current_state():
    runtime_client = StaleExecutionConfigRuntimeClient()
    client = _app(runtime_client)

    response = client.patch(
        "/web/mpa/sessions/session-1/execution-config",
        headers={"If-Match": '"1"'},
        json={
            "runtimeId": "runtime-1",
            "region": "cn-beijing",
            "changes": [
                {"category": "model", "mode": "replace", "value": {"id": "model-b"}}
            ],
        },
    )

    assert response.status_code == 412
    assert response.json()["detail"]["code"] == "execution_config_changed"
    assert response.json()["detail"]["currentState"]["etag"] == '"2"'
    assert response.json()["detail"]["currentState"]["effectiveRefs"]["model"] == {
        "id": "model-a"
    }


def test_mpa_profile_apply_route_maps_runtime_errors_without_secret():
    runtime_client = FailingRuntimeClient()
    client = _app(runtime_client)
    payload = _profile_payload()
    payload["profile"]["metadata"] = {"safe": "value"}

    response = client.put(
        "/web/mpa/agents/mpa-1/profile",
        headers={"Idempotency-Key": "idem-1"},
        json=payload,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "profile_version_conflict",
        "message": "profile_version_conflict",
        "requestId": "req-1",
    }
    assert "runtime-secret" not in response.text


def test_mpa_profile_apply_route_requires_idempotency_key():
    runtime_client = FakeRuntimeClient()
    client = _app(runtime_client)

    response = client.put("/web/mpa/agents/mpa-1/profile", json=_profile_payload())

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "idempotency_key_required"
    assert runtime_client.calls == []


def test_mpa_profile_apply_route_rejects_secret_fields_before_runtime_call():
    runtime_client = FakeRuntimeClient()
    client = _app(runtime_client)
    payload = _profile_payload()
    payload["profile"]["model"]["apiKey"] = "plain-secret"

    response = client.put(
        "/web/mpa/agents/mpa-1/profile",
        headers={"Idempotency-Key": "idem-1"},
        json=payload,
    )

    assert response.status_code == 422
    assert runtime_client.calls == []


def test_mpa_agent_create_route_starts_operation_service():
    operation_service = FakeOperationService()
    client = _app(FakeRuntimeClient(), operation_service=operation_service)

    response = client.post(
        "/web/mpa/agents",
        headers={"Idempotency-Key": "idem-1"},
        json=_profile_payload(),
    )

    assert response.status_code == 202, response.text
    assert response.json()["operationId"] == "mpaop-1"
    request, key = operation_service.started[0]
    assert key == "idem-1"
    assert request.operation_kind == "create"
    assert request.owner_id == "owner-1"
    assert request.mpa_instance_id == "mpa-1"
    assert request.runtime_endpoint == "https://runtime.example"
    assert request.runtime_authorization == "runtime-secret"


def test_mpa_agent_update_route_starts_update_operation_service():
    operation_service = FakeOperationService()
    client = _app(FakeRuntimeClient(), operation_service=operation_service)
    payload = {**_profile_payload(), "runtimeRevision": '"7"'}

    response = client.patch(
        "/web/mpa/agents/mpa-1",
        headers={"Idempotency-Key": "idem-2"},
        json=payload,
    )

    assert response.status_code == 202, response.text
    request, key = operation_service.started[0]
    assert key == "idem-2"
    assert request.operation_kind == "update"
    assert request.create is False
    assert request.mpa_instance_id == "mpa-1"
    assert request.runtime_revision == '"7"'


def test_mpa_agent_operations_route_lists_active_for_owner():
    operation_service = FakeOperationService()
    client = _app(FakeRuntimeClient(), operation_service=operation_service)

    response = client.get("/web/mpa/agent-operations")

    assert response.status_code == 200
    assert response.json()["operations"][0]["operationId"] == "mpaop-1"
    assert operation_service.listed == ["owner-1"]


def test_mpa_agent_operation_retry_route_resumes_from_request_body():
    operation_service = FakeOperationService()
    client = _app(FakeRuntimeClient(), operation_service=operation_service)

    response = client.post(
        "/web/mpa/agent-operations/mpaop-1/retry",
        json={**_profile_payload(), "operationKind": "create"},
    )

    assert response.status_code == 202
    request, operation_id = operation_service.retried[0]
    assert operation_id == "mpaop-1"
    assert request.operation_kind == "create"


def test_mpa_agent_operation_route_maps_idempotency_conflict():
    operation_service = FakeOperationService(fail=True)
    client = _app(FakeRuntimeClient(), operation_service=operation_service)

    response = client.post(
        "/web/mpa/agents",
        headers={"Idempotency-Key": "idem-1"},
        json=_profile_payload(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "idempotency_mismatch"
