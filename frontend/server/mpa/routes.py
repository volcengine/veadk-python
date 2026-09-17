"""Studio BFF routes for MPA Profile application."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import inspect
from typing import Any

from fastapi import Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from frontend.server.mpa.runtime_client import (
    MpaExecutionConfigChange,
    MpaProfile,
    MpaProfileApplyRequest,
    MpaRuntimeClient,
    MpaRuntimeError,
)
from frontend.server.mpa.service import (
    MpaAgentOperationRequest,
    MpaAgentOperationService,
)
from frontend.server.mpa.operations import MpaOperationConflict

RuntimeAuthorizer = Callable[[Request, str, str], Any]
RuntimeConnectionResolver = Callable[
    [Request, str, str, Any], tuple[str, str, str, str]
]
RuntimeBindingResolver = Callable[[Request, str, str], Any]
_ACTIVE_SESSION_STATUSES = {"queued", "running", "pausing", "paused", "resuming"}


@dataclass(frozen=True)
class MpaRuntimeBinding:
    runtime_id: str
    region: str
    runtime: Any
    visible: dict[str, Any]


class MpaProfileApplyBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    runtime_id: str = Field(alias="runtimeId", min_length=1)
    region: str = "cn-beijing"
    mpa_instance_id: str = Field(default="", alias="mpaInstanceId")
    source_profile_id: str = Field(alias="sourceProfileId", min_length=1)
    profile: MpaProfile
    create: bool = False
    runtime_revision: str = Field(default="", alias="runtimeRevision")


class MpaAgentOperationBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    operation_kind: str | None = Field(default=None, alias="operationKind")
    runtime_id: str = Field(alias="runtimeId", min_length=1)
    region: str = "cn-beijing"
    mpa_instance_id: str = Field(default="", alias="mpaInstanceId")
    source_profile_id: str = Field(alias="sourceProfileId", min_length=1)
    profile: MpaProfile
    target_key: str = Field(default="", alias="targetKey")
    runtime_revision: str = Field(default="", alias="runtimeRevision")
    create: bool | None = None


class MpaRuntimeSessionBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    runtime_id: str = Field(alias="runtimeId", min_length=1)
    region: str = "cn-beijing"


class MpaSessionExecutionConfigPatchBody(MpaRuntimeSessionBody):
    changes: list[MpaExecutionConfigChange] = Field(default_factory=list)


class MpaSessionProfileUpgradeBody(MpaRuntimeSessionBody):
    target_profile_revision: int = Field(alias="targetProfileRevision", ge=1)


def mount_mpa_profile_routes(
    app: Any,
    *,
    runtime_client: MpaRuntimeClient,
    authorize_runtime: RuntimeAuthorizer,
    resolve_runtime_connection: RuntimeConnectionResolver,
    operation_service: MpaAgentOperationService | None = None,
    owner_resolver: Callable[[Request], str] | None = None,
    resolve_runtime_bindings: RuntimeBindingResolver | None = None,
) -> None:
    def owner_id(request: Request) -> str:
        return owner_resolver(request) if owner_resolver is not None else "local"

    def operation_request(
        *,
        request: Request,
        mpa_instance_id: str,
        body: MpaAgentOperationBody,
        operation_kind: str,
        create: bool,
    ) -> MpaAgentOperationRequest:
        runtime = authorize_runtime(request, body.runtime_id, body.region)
        endpoint, authorization, _auth_type, _network_type = resolve_runtime_connection(
            request,
            body.runtime_id,
            body.region,
            runtime,
        )
        return MpaAgentOperationRequest(
            ownerId=owner_id(request),
            operationKind=operation_kind,
            targetKey=body.target_key or mpa_instance_id,
            runtimeId=body.runtime_id,
            runtimeRegion=body.region,
            runtimeEndpoint=endpoint,
            runtimeAuthorization=authorization,
            mpaInstanceId=mpa_instance_id,
            sourceProfileId=body.source_profile_id,
            profile=body.profile,
            create=create,
            runtimeRevision=body.runtime_revision,
        )

    @app.post(
        "/web/mpa/agents",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_mpa_agent(
        body: MpaAgentOperationBody, request: Request
    ) -> dict[str, Any]:
        if operation_service is None:
            raise HTTPException(
                status_code=503, detail="mpa_operation_service_unavailable"
            )
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "idempotency_key_required",
                    "message": "idempotency_key_required",
                },
            )
        try:
            operation = await operation_service.start(
                operation_request(
                    request=request,
                    mpa_instance_id=body.mpa_instance_id or body.runtime_id,
                    body=body,
                    operation_kind="create",
                    create=True,
                ),
                idempotency_key=idempotency_key,
            )
        except MpaOperationConflict as error:
            _raise_operation_conflict(error)
        return _operation_payload(operation)

    @app.patch(
        "/web/mpa/agents/{mpa_instance_id}",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def update_mpa_agent(
        mpa_instance_id: str,
        body: MpaAgentOperationBody,
        request: Request,
    ) -> dict[str, Any]:
        if operation_service is None:
            raise HTTPException(
                status_code=503, detail="mpa_operation_service_unavailable"
            )
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "idempotency_key_required",
                    "message": "idempotency_key_required",
                },
            )
        try:
            operation = await operation_service.start(
                operation_request(
                    request=request,
                    mpa_instance_id=mpa_instance_id,
                    body=body,
                    operation_kind="update",
                    create=False,
                ),
                idempotency_key=idempotency_key,
            )
        except MpaOperationConflict as error:
            _raise_operation_conflict(error)
        return _operation_payload(operation)

    @app.get("/web/mpa/agent-operations")
    async def list_agent_operations(
        request: Request,
        status_filter: str = Query(default="active", alias="status"),
    ) -> dict[str, Any]:
        if operation_service is None:
            raise HTTPException(
                status_code=503, detail="mpa_operation_service_unavailable"
            )
        if status_filter != "active":
            raise HTTPException(status_code=400, detail="unsupported operation status")
        operations = await operation_service.list_active(owner_id(request))
        return {
            "operations": [_operation_payload(operation) for operation in operations]
        }

    @app.get("/web/mpa/agents/{mpa_instance_id}/view")
    async def mpa_agent_view(
        mpa_instance_id: str,
        request: Request,
        response: Response,
        runtime_id: str = Query(default="", alias="runtimeId"),
        region: str = Query(default="all"),
    ) -> dict[str, Any]:
        owner = owner_id(request)
        active_operation = await _active_operation(
            operation_service,
            owner,
            mpa_instance_id,
        )
        if runtime_id.strip():
            normalized_region = (
                region
                if region.strip().lower() not in {"", "all", "*"}
                else "cn-beijing"
            )
            runtime = authorize_runtime(request, runtime_id.strip(), normalized_region)
            bindings = [
                MpaRuntimeBinding(
                    runtime_id=runtime_id.strip(),
                    region=normalized_region,
                    runtime=runtime,
                    visible=_runtime_visible_payload(
                        runtime,
                        runtime_id.strip(),
                        normalized_region,
                        mpa_instance_id=mpa_instance_id,
                    ),
                )
            ]
        else:
            bindings = await _runtime_bindings(
                request=request,
                mpa_instance_id=mpa_instance_id,
                region=region,
                authorize_runtime=authorize_runtime,
                resolve_runtime_bindings=resolve_runtime_bindings,
            )
        if not bindings:
            return _mpa_agent_view_payload(
                mpa_instance_id=mpa_instance_id,
                binding_status="runtime_missing",
                active_operation=active_operation,
                safe_error_code="runtime_missing",
            )
        if len(bindings) > 1:
            return _mpa_agent_view_payload(
                mpa_instance_id=mpa_instance_id,
                binding_status="binding_ambiguous",
                active_operation=active_operation,
                bindings=[binding.visible for binding in bindings],
                safe_error_code="binding_ambiguous",
            )

        binding = bindings[0]
        try:
            endpoint, bearer_token, _auth_type, _network_type = (
                resolve_runtime_connection(
                    request,
                    binding.runtime_id,
                    binding.region,
                    binding.runtime,
                )
            )
            profile_status_result = await runtime_client.profile_status(
                endpoint=endpoint,
                mpa_instance_id=mpa_instance_id,
                bearer_token=_bearer_value(bearer_token),
            )
        except MpaRuntimeError as error:
            if error.status_code == 404:
                return _mpa_agent_view_payload(
                    mpa_instance_id=mpa_instance_id,
                    binding_status="orphan_runtime",
                    runtime=binding.visible,
                    active_operation=active_operation,
                    safe_error_code=error.code,
                )
            _raise_runtime_error(error)
        payload = _result_payload(profile_status_result)
        if etag := str(payload.get("etag") or ""):
            response.headers["ETag"] = etag
        return _mpa_agent_view_payload(
            mpa_instance_id=mpa_instance_id,
            binding_status="bound",
            runtime=binding.visible,
            profile=payload,
            active_operation=active_operation,
        )

    @app.get("/web/mpa/agents/{mpa_instance_id}/delete-preview")
    async def mpa_agent_delete_preview(
        mpa_instance_id: str,
        request: Request,
        runtime_id: str = Query(default="", alias="runtimeId"),
        region: str = Query(default="all"),
    ) -> dict[str, Any]:
        return await _mpa_agent_delete_preview_payload(
            request=request,
            mpa_instance_id=mpa_instance_id,
            runtime_id=runtime_id,
            region=region,
            runtime_client=runtime_client,
            authorize_runtime=authorize_runtime,
            resolve_runtime_connection=resolve_runtime_connection,
            operation_service=operation_service,
            owner=owner_id(request),
            resolve_runtime_bindings=resolve_runtime_bindings,
        )

    @app.post(
        "/web/mpa/agent-operations/{operation_id}/retry",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def retry_agent_operation(
        operation_id: str,
        body: MpaAgentOperationBody,
        request: Request,
    ) -> dict[str, Any]:
        if operation_service is None:
            raise HTTPException(
                status_code=503, detail="mpa_operation_service_unavailable"
            )
        operation_kind = str(body.operation_kind or "").strip() or (
            "update" if body.runtime_revision.strip() else "create"
        )
        if operation_kind not in {"create", "update"}:
            raise HTTPException(status_code=400, detail="invalid operationKind")
        mpa_instance_id = body.mpa_instance_id or (
            body.target_key if operation_kind == "update" else body.runtime_id
        )
        if not mpa_instance_id:
            raise HTTPException(status_code=400, detail="mpaInstanceId is required")
        try:
            operation = await operation_service.retry(
                operation_request(
                    request=request,
                    mpa_instance_id=mpa_instance_id,
                    body=body,
                    operation_kind=operation_kind,
                    create=operation_kind == "create",
                ),
                operation_id=operation_id,
            )
        except MpaOperationConflict as error:
            _raise_operation_conflict(error)
        return _operation_payload(operation)

    @app.put(
        "/web/mpa/agents/{mpa_instance_id}/profile",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def apply_profile(
        mpa_instance_id: str,
        body: MpaProfileApplyBody,
        request: Request,
        response: Response,
    ) -> dict[str, Any]:
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "idempotency_key_required",
                    "message": "idempotency_key_required",
                },
            )
        if not body.create and not body.runtime_revision.strip():
            raise HTTPException(
                status_code=400,
                detail="runtimeRevision is required for update",
            )
        runtime = authorize_runtime(request, body.runtime_id, body.region)
        endpoint, bearer_token, _auth_type, _network_type = resolve_runtime_connection(
            request,
            body.runtime_id,
            body.region,
            runtime,
        )
        try:
            result = await runtime_client.apply_profile(
                endpoint=endpoint,
                mpa_instance_id=mpa_instance_id,
                bearer_token=_bearer_value(bearer_token),
                idempotency_key=idempotency_key,
                profile=MpaProfileApplyRequest.from_profile(
                    source_profile_id=body.source_profile_id,
                    profile=body.profile,
                ),
                create=body.create,
                runtime_revision=body.runtime_revision.strip(),
            )
        except MpaRuntimeError as error:
            _raise_runtime_error(error)
        payload = _result_payload(result)
        if etag := str(payload.get("etag") or ""):
            response.headers["ETag"] = etag
        return payload

    @app.get("/web/mpa/agents/{mpa_instance_id}/profile-status")
    async def profile_status(
        mpa_instance_id: str,
        request: Request,
        response: Response,
        runtime_id: str = Query(..., alias="runtimeId", min_length=1),
        region: str = Query(default="cn-beijing"),
    ) -> dict[str, Any]:
        runtime = authorize_runtime(request, runtime_id, region)
        endpoint, bearer_token, _auth_type, _network_type = resolve_runtime_connection(
            request,
            runtime_id,
            region,
            runtime,
        )
        try:
            result = await runtime_client.profile_status(
                endpoint=endpoint,
                mpa_instance_id=mpa_instance_id,
                bearer_token=_bearer_value(bearer_token),
            )
        except MpaRuntimeError as error:
            _raise_runtime_error(error)
        payload = _result_payload(result)
        if etag := str(payload.get("etag") or ""):
            response.headers["ETag"] = etag
        return payload

    @app.get("/web/mpa/sessions/{session_id}/execution-config")
    async def get_session_execution_config(
        session_id: str,
        request: Request,
        response: Response,
        runtime_id: str = Query(..., alias="runtimeId", min_length=1),
        region: str = Query(default="cn-beijing"),
    ) -> dict[str, Any]:
        runtime = authorize_runtime(request, runtime_id, region)
        endpoint, bearer_token, _auth_type, _network_type = resolve_runtime_connection(
            request,
            runtime_id,
            region,
            runtime,
        )
        try:
            result = await runtime_client.session_execution_config(
                endpoint=endpoint,
                session_id=session_id,
                bearer_token=_bearer_value(bearer_token),
            )
        except MpaRuntimeError as error:
            _raise_runtime_error(error)
        payload = _result_payload(result)
        if etag := str(payload.get("etag") or ""):
            response.headers["ETag"] = etag
        return payload

    @app.patch("/web/mpa/sessions/{session_id}/execution-config")
    async def patch_session_execution_config(
        session_id: str,
        body: MpaSessionExecutionConfigPatchBody,
        request: Request,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> dict[str, Any]:
        if not if_match:
            raise HTTPException(
                status_code=428,
                detail={
                    "code": "precondition_required",
                    "message": "precondition_required",
                },
            )
        runtime = authorize_runtime(request, body.runtime_id, body.region)
        endpoint, bearer_token, _auth_type, _network_type = resolve_runtime_connection(
            request,
            body.runtime_id,
            body.region,
            runtime,
        )
        try:
            result = await runtime_client.patch_session_execution_config(
                endpoint=endpoint,
                session_id=session_id,
                bearer_token=_bearer_value(bearer_token),
                if_match=if_match,
                changes=body.changes,
            )
        except MpaRuntimeError as error:
            _raise_runtime_error(error)
        payload = _result_payload(result)
        if etag := str(payload.get("etag") or ""):
            response.headers["ETag"] = etag
        return payload

    @app.post("/web/mpa/sessions/{session_id}/profile-upgrade")
    async def upgrade_session_profile(
        session_id: str,
        body: MpaSessionProfileUpgradeBody,
        request: Request,
        response: Response,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> dict[str, Any]:
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
        runtime = authorize_runtime(request, body.runtime_id, body.region)
        endpoint, bearer_token, _auth_type, _network_type = resolve_runtime_connection(
            request,
            body.runtime_id,
            body.region,
            runtime,
        )
        try:
            result = await runtime_client.upgrade_session_profile(
                endpoint=endpoint,
                session_id=session_id,
                bearer_token=_bearer_value(bearer_token),
                if_match=if_match,
                idempotency_key=idempotency_key,
                target_profile_revision=body.target_profile_revision,
            )
        except MpaRuntimeError as error:
            _raise_runtime_error(error)
        payload = _result_payload(result)
        if etag := str(payload.get("etag") or ""):
            response.headers["ETag"] = etag
        return payload


def _bearer_value(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("bearer "):
        return token[7:].strip()
    return token


def _result_payload(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json", by_alias=True)
    if isinstance(result, dict):
        return dict(result)
    raise HTTPException(status_code=502, detail="runtime_invalid_response")


def _raise_runtime_error(error: MpaRuntimeError) -> None:
    detail = {
        "code": error.code,
        "message": error.code,
        "requestId": error.request_id,
    }
    if error.current_state:
        detail["currentState"] = error.current_state
    raise HTTPException(status_code=error.status_code, detail=detail) from error


def _raise_operation_conflict(error: MpaOperationConflict) -> None:
    raise HTTPException(
        status_code=409,
        detail={
            "code": "idempotency_mismatch",
            "message": "idempotency_mismatch",
        },
    ) from error


def _operation_payload(operation: Any) -> dict[str, Any]:
    if hasattr(operation, "model_dump"):
        return operation.model_dump(mode="json", by_alias=True)
    if isinstance(operation, dict):
        return dict(operation)
    raise HTTPException(status_code=502, detail="mpa_operation_invalid_response")


async def _active_operation(
    operation_service: MpaAgentOperationService | None,
    owner_id: str,
    mpa_instance_id: str,
) -> dict[str, Any] | None:
    if operation_service is None:
        return None
    operations = await operation_service.list_active(owner_id)
    for operation in operations:
        payload = _operation_payload(operation)
        if (
            str(payload.get("mpaInstanceId") or "") == mpa_instance_id
            or str(payload.get("runtimeId") or "") == mpa_instance_id
            or str(payload.get("targetKey") or "") == mpa_instance_id
        ):
            return payload
    return None


async def _runtime_bindings(
    *,
    request: Request,
    mpa_instance_id: str,
    region: str,
    authorize_runtime: RuntimeAuthorizer,
    resolve_runtime_bindings: RuntimeBindingResolver | None,
) -> list[MpaRuntimeBinding]:
    if resolve_runtime_bindings is None:
        if region.strip().lower() in {"", "all", "*"}:
            return []
        runtime = authorize_runtime(request, mpa_instance_id, region)
        return [
            MpaRuntimeBinding(
                runtime_id=mpa_instance_id,
                region=region,
                runtime=runtime,
                visible=_runtime_visible_payload(
                    runtime,
                    mpa_instance_id,
                    region,
                    mpa_instance_id=mpa_instance_id,
                ),
            )
        ]
    result = resolve_runtime_bindings(request, mpa_instance_id, region)
    if inspect.isawaitable(result):
        result = await result
    return [
        _coerce_runtime_binding(item, mpa_instance_id, region) for item in result or []
    ]


async def _resolve_delete_binding(
    *,
    request: Request,
    mpa_instance_id: str,
    runtime_id: str,
    region: str,
    authorize_runtime: RuntimeAuthorizer,
    resolve_runtime_bindings: RuntimeBindingResolver | None,
) -> tuple[str, MpaRuntimeBinding | None, list[MpaRuntimeBinding]]:
    requested_runtime_id = runtime_id.strip()
    if requested_runtime_id:
        normalized_region = (
            region if region.strip().lower() not in {"", "all", "*"} else "cn-beijing"
        )
        runtime = authorize_runtime(request, requested_runtime_id, normalized_region)
        return (
            "bound",
            MpaRuntimeBinding(
                runtime_id=requested_runtime_id,
                region=normalized_region,
                runtime=runtime,
                visible=_runtime_visible_payload(
                    runtime,
                    requested_runtime_id,
                    normalized_region,
                    mpa_instance_id=mpa_instance_id,
                ),
            ),
            [],
        )
    bindings = await _runtime_bindings(
        request=request,
        mpa_instance_id=mpa_instance_id,
        region=region,
        authorize_runtime=authorize_runtime,
        resolve_runtime_bindings=resolve_runtime_bindings,
    )
    if not bindings:
        return "runtime_missing", None, []
    if len(bindings) > 1:
        return "binding_ambiguous", None, bindings
    return "bound", bindings[0], []


async def _mpa_agent_delete_preview_payload(
    *,
    request: Request,
    mpa_instance_id: str,
    runtime_id: str,
    region: str,
    runtime_client: MpaRuntimeClient,
    authorize_runtime: RuntimeAuthorizer,
    resolve_runtime_connection: RuntimeConnectionResolver,
    operation_service: MpaAgentOperationService | None,
    owner: str,
    resolve_runtime_bindings: RuntimeBindingResolver | None,
) -> dict[str, Any]:
    active_operation = await _active_operation(
        operation_service, owner, mpa_instance_id
    )
    binding_status, binding, ambiguous_bindings = await _resolve_delete_binding(
        request=request,
        mpa_instance_id=mpa_instance_id,
        runtime_id=runtime_id,
        region=region,
        authorize_runtime=authorize_runtime,
        resolve_runtime_bindings=resolve_runtime_bindings,
    )
    blockers: list[str] = []
    if binding_status != "bound":
        blockers.append(binding_status)
        if active_operation:
            blockers.append("active_operation")
        return _delete_preview_payload(
            mpa_instance_id=mpa_instance_id,
            binding_status=binding_status,
            runtime=None,
            profile=None,
            active_operation=active_operation,
            bindings=[item.visible for item in ambiguous_bindings],
            blockers=blockers,
            sessions=[],
        )

    assert binding is not None
    profile: dict[str, Any] | None = None
    sessions: list[Any] = []
    try:
        endpoint, bearer_token, _auth_type, _network_type = resolve_runtime_connection(
            request,
            binding.runtime_id,
            binding.region,
            binding.runtime,
        )
        profile = _result_payload(
            await runtime_client.profile_status(
                endpoint=endpoint,
                mpa_instance_id=mpa_instance_id,
                bearer_token=_bearer_value(bearer_token),
            )
        )
        sessions = await runtime_client.list_sessions(
            endpoint=endpoint,
            bearer_token=_bearer_value(bearer_token),
            include_a2a=True,
        )
    except MpaRuntimeError as error:
        if error.status_code == 404:
            blockers.append("orphan_runtime")
            binding_status = "orphan_runtime"
        else:
            _raise_runtime_error(error)
    if active_operation:
        blockers.append("active_operation")
    if _active_session_payloads(sessions):
        blockers.append("active_sessions")
    return _delete_preview_payload(
        mpa_instance_id=mpa_instance_id,
        binding_status=binding_status,
        runtime=binding.visible,
        profile=profile,
        active_operation=active_operation,
        bindings=[],
        blockers=blockers,
        sessions=sessions,
    )


def _session_payload(session: Any) -> dict[str, Any]:
    if hasattr(session, "model_dump"):
        payload = session.model_dump(mode="json", by_alias=True)
    elif isinstance(session, dict):
        payload = dict(session)
    else:
        payload = {
            "sessionId": str(
                getattr(session, "session_id", "") or getattr(session, "id", "")
            ),
            "status": str(getattr(session, "status", "") or ""),
            "appName": str(getattr(session, "app_name", "") or ""),
        }
    session_id = str(
        payload.get("sessionId") or payload.get("session_id") or payload.get("id") or ""
    )
    result = {
        "sessionId": session_id,
        "status": str(payload.get("status") or ""),
        "appName": str(payload.get("appName") or payload.get("app_name") or ""),
    }
    if bool(payload.get("adminDebug") or payload.get("admin_debug")):
        result["adminDebug"] = True
    return result


def _active_session_payloads(sessions: list[Any]) -> list[dict[str, Any]]:
    return [
        payload
        for payload in (_session_payload(session) for session in sessions)
        if payload["status"].casefold() in _ACTIVE_SESSION_STATUSES
    ]


def _delete_preview_payload(
    *,
    mpa_instance_id: str,
    binding_status: str,
    runtime: dict[str, Any] | None,
    profile: dict[str, Any] | None,
    active_operation: dict[str, Any] | None,
    bindings: list[dict[str, Any]],
    blockers: list[str],
    sessions: list[Any],
) -> dict[str, Any]:
    session_payloads = [_session_payload(session) for session in sessions]
    active_sessions = _active_session_payloads(sessions)
    idle_sessions = [
        item
        for item in session_payloads
        if item["status"].casefold() not in _ACTIVE_SESSION_STATUSES
    ]
    debug_count = sum(1 for item in session_payloads if item.get("adminDebug") is True)
    can_delete = (
        binding_status == "bound"
        and not blockers
        and bool((runtime or {}).get("canManage", True))
    )
    return {
        "mpaInstanceId": mpa_instance_id,
        "bindingStatus": binding_status,
        "runtime": runtime,
        "profile": profile,
        "activeOperation": active_operation,
        "bindings": bindings,
        "canDelete": can_delete,
        "blockers": blockers,
        "sessionCounts": {
            "total": len(session_payloads),
            "active": len(active_sessions),
            "idle": len(idle_sessions),
            "debug": debug_count,
        },
        "activeSessions": active_sessions,
        "cleanupPlan": [
            {
                "stage": "runtime_sessions",
                "description": "Delete visible idle Runtime sessions before deleting the Runtime resource.",
                "count": len(idle_sessions),
            },
            {
                "stage": "runtime_diagnostics",
                "description": "Runtime session cleanup removes associated diagnostics and mounted metadata.",
                "count": len(session_payloads),
            },
            {
                "stage": "agentkit_runtime",
                "description": "Delete the AgentKit Runtime resource after Runtime-side cleanup is complete.",
                "count": 1 if binding_status in {"bound", "orphan_runtime"} else 0,
            },
        ],
    }


def _coerce_runtime_binding(
    item: Any,
    mpa_instance_id: str,
    requested_region: str,
) -> MpaRuntimeBinding:
    if isinstance(item, MpaRuntimeBinding):
        return item
    if isinstance(item, dict):
        runtime = item.get("runtime") or item
        runtime_id = str(item.get("runtimeId") or item.get("runtime_id") or "")
        region = str(item.get("region") or requested_region or "")
        visible = dict(item.get("visible") or item)
        visible.pop("runtime", None)
        resolved_runtime_id = runtime_id or str(
            visible.get("runtimeId") or mpa_instance_id
        )
        visible.setdefault("mpaInstanceId", mpa_instance_id)
        return MpaRuntimeBinding(
            runtime_id=resolved_runtime_id,
            region=region,
            runtime=runtime,
            visible={**visible, "runtimeId": resolved_runtime_id, "region": region},
        )
    runtime_id = str(getattr(item, "runtime_id", "") or mpa_instance_id)
    region = str(getattr(item, "region", "") or requested_region or "")
    return MpaRuntimeBinding(
        runtime_id=runtime_id,
        region=region,
        runtime=item,
        visible=_runtime_visible_payload(
            item,
            runtime_id,
            region,
            mpa_instance_id=mpa_instance_id,
        ),
    )


def _runtime_visible_payload(
    runtime: Any,
    runtime_id: str,
    region: str,
    *,
    mpa_instance_id: str = "",
) -> dict[str, Any]:
    return {
        "runtimeId": runtime_id,
        "region": region,
        "mpaInstanceId": mpa_instance_id
        or str(getattr(runtime, "mpa_instance_id", "") or ""),
        "name": str(getattr(runtime, "name", "") or runtime_id),
        "status": str(getattr(runtime, "status", "") or ""),
        "currentVersion": getattr(runtime, "current_version_number", None),
        "readinessPhase": str(getattr(runtime, "readiness_phase", "") or ""),
        "agentCategory": "mpa",
    }


def _mpa_agent_view_payload(
    *,
    mpa_instance_id: str,
    binding_status: str,
    runtime: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    active_operation: dict[str, Any] | None = None,
    bindings: list[dict[str, Any]] | None = None,
    safe_error_code: str = "",
) -> dict[str, Any]:
    can_manage = bool((runtime or {}).get("canManage", True))
    can_read = binding_status in {"bound", "orphan_runtime"}
    can_write = binding_status in {"bound", "orphan_runtime"} and can_manage
    return {
        "mpaInstanceId": mpa_instance_id,
        "bindingStatus": binding_status,
        "runtime": runtime,
        "profile": profile,
        "activeOperation": active_operation,
        "bindings": bindings or [],
        "capabilities": {
            "canRead": can_read,
            "canWrite": can_write,
            "canDebug": binding_status == "bound",
        },
        "safeError": (
            {"code": safe_error_code, "message": safe_error_code}
            if safe_error_code
            else None
        ),
    }


__all__ = [
    "MpaAgentOperationBody",
    "MpaProfileApplyBody",
    "MpaRuntimeBinding",
    "MpaRuntimeSessionBody",
    "MpaSessionExecutionConfigPatchBody",
    "MpaSessionProfileUpgradeBody",
    "_ACTIVE_SESSION_STATUSES",
    "_active_operation",
    "_delete_preview_payload",
    "_mpa_agent_delete_preview_payload",
    "_session_payload",
    "mount_mpa_profile_routes",
]
