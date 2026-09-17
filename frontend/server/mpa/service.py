"""MPA Agent lifecycle orchestration for Studio."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from frontend.server.mpa.operations import (
    MpaLifecycleOperation,
    MpaOperationConflict,
    Stored,
)
from frontend.server.mpa.runtime_client import (
    MpaProfile,
    MpaProfileApplyRequest,
    MpaRuntimeClient,
    MpaRuntimeError,
)


class MpaOperationRepository(Protocol):
    async def create_operation(
        self, operation: MpaLifecycleOperation
    ) -> Stored[MpaLifecycleOperation]: ...

    async def get_operation(
        self, owner_id: str, operation_id: str
    ) -> Stored[MpaLifecycleOperation]: ...

    async def update_operation(
        self,
        operation: MpaLifecycleOperation,
        etag: str,
    ) -> Stored[MpaLifecycleOperation]: ...

    async def list_active_operations(
        self, owner_id: str
    ) -> list[MpaLifecycleOperation]: ...


class MpaRuntimeOrchestrationClient(Protocol):
    async def apply_profile(self, **kwargs: Any) -> Any: ...

    async def execution_smoke(self, **kwargs: Any) -> Any: ...


class MpaAgentOperationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    owner_id: str = Field(alias="ownerId", min_length=1)
    operation_kind: Literal["create", "update"] = Field(alias="operationKind")
    target_key: str = Field(alias="targetKey", min_length=1)
    runtime_id: str = Field(alias="runtimeId", min_length=1)
    runtime_region: str = Field(default="cn-beijing", alias="runtimeRegion")
    runtime_endpoint: str = Field(alias="runtimeEndpoint", min_length=1)
    runtime_authorization: str = Field(alias="runtimeAuthorization", min_length=1)
    mpa_instance_id: str = Field(alias="mpaInstanceId", min_length=1)
    source_profile_id: str = Field(alias="sourceProfileId", min_length=1)
    profile: MpaProfile
    create: bool = False
    runtime_revision: str = Field(default="", alias="runtimeRevision")


class MpaAgentOperationService:
    """Drive MPA create/update operation stages using idempotent Runtime APIs."""

    def __init__(
        self,
        *,
        repository: MpaOperationRepository,
        runtime_client: MpaRuntimeOrchestrationClient | MpaRuntimeClient,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._runtime_client = runtime_client
        self._now = now or (lambda: datetime.now(UTC))

    async def start(
        self,
        request: MpaAgentOperationRequest,
        *,
        idempotency_key: str,
    ) -> MpaLifecycleOperation:
        operation = MpaLifecycleOperation(
            operationKind=request.operation_kind,
            ownerId=request.owner_id,
            targetKey=request.target_key,
            idempotencyKeyHash=_hash_text(idempotency_key),
            requestHash=_request_hash(request),
            stage=(
                "runtime_preparing"
                if request.operation_kind == "create"
                else "profile_applying"
            ),
            status="active",
            mpaInstanceId=request.mpa_instance_id,
            runtimeId=request.runtime_id,
            runtimeRegion=request.runtime_region,
            runtimeRevision=request.runtime_revision,
            profileDigest=_profile_apply_request(request).source_profile_digest,
            createdAt=self._now(),
            updatedAt=self._now(),
        )
        stored = await self._repository.create_operation(operation)
        if not stored.created:
            return stored.value
        if stored.value.status not in {"active", "failed_retryable"}:
            return stored.value
        if (
            stored.value.request_hash != operation.request_hash
            or stored.value.idempotency_key_hash != operation.idempotency_key_hash
        ):
            raise MpaOperationConflict(
                "MPA operation idempotency key was reused with different input."
            )
        if stored.value.stage not in {
            "runtime_preparing",
            "profile_applying",
            "smoke_running",
        }:
            return stored.value
        return await self._advance(stored, request)

    async def retry(
        self,
        request: MpaAgentOperationRequest,
        *,
        operation_id: str,
    ) -> MpaLifecycleOperation:
        stored = await self._repository.get_operation(request.owner_id, operation_id)
        if stored.value.status != "failed_retryable":
            return stored.value
        return await self.resume(request, operation_id=operation_id)

    async def resume(
        self,
        request: MpaAgentOperationRequest,
        *,
        operation_id: str,
    ) -> MpaLifecycleOperation:
        stored = await self._repository.get_operation(request.owner_id, operation_id)
        if stored.value.request_hash != _request_hash(request):
            raise MpaOperationConflict("MPA operation request does not match.")
        if stored.value.status not in {"active", "failed_retryable"}:
            return stored.value
        next_operation = stored.value.model_copy(
            update={
                "status": "active",
                "safe_error_code": "",
                "retry_count": stored.value.retry_count + 1,
                "updated_at": self._now(),
            }
        )
        stored = await self._repository.update_operation(next_operation, stored.etag)
        return await self._advance(stored, request)

    async def list_active(self, owner_id: str) -> list[MpaLifecycleOperation]:
        return await self._repository.list_active_operations(owner_id)

    async def _advance(
        self,
        stored: Stored[MpaLifecycleOperation],
        request: MpaAgentOperationRequest,
    ) -> MpaLifecycleOperation:
        operation = stored.value
        etag = stored.etag
        try:
            if operation.stage == "runtime_preparing":
                operation, etag = await self._store_stage(
                    operation, etag, stage="profile_applying"
                )
            if operation.stage == "profile_applying":
                profile_result = await self._runtime_client.apply_profile(
                    endpoint=request.runtime_endpoint,
                    mpa_instance_id=request.mpa_instance_id,
                    bearer_token=_bearer_value(request.runtime_authorization),
                    idempotency_key=f"{operation.operation_id}-profile",
                    profile=_profile_apply_request(request),
                    create=request.create,
                    runtime_revision=request.runtime_revision,
                )
                profile_payload = _payload(profile_result)
                operation, etag = await self._store_stage(
                    operation,
                    etag,
                    stage=(
                        "smoke_running"
                        if request.operation_kind == "create"
                        else "succeeded"
                    ),
                    profile_operation_id=str(profile_payload.get("operationId") or ""),
                    profile_revision=_int_or_none(
                        profile_payload.get("profileRevision")
                    ),
                    runtime_revision=str(
                        profile_payload.get("runtimeRevision")
                        or profile_payload.get("etag")
                        or ""
                    ),
                )
                if request.operation_kind == "update":
                    operation, _etag = await self._store_stage(
                        operation, etag, status="succeeded", stage="succeeded"
                    )
                    return operation
            if operation.stage == "smoke_running":
                smoke_result = await self._runtime_client.execution_smoke(
                    endpoint=request.runtime_endpoint,
                    mpa_instance_id=request.mpa_instance_id,
                    bearer_token=_bearer_value(request.runtime_authorization),
                    idempotency_key=f"{operation.operation_id}-smoke",
                )
                smoke_payload = _payload(smoke_result)
                if str(smoke_payload.get("status") or "") != "passed":
                    raise MpaRuntimeError(
                        str(
                            smoke_payload.get("lastErrorCode") or "not_execution_ready"
                        ),
                        status_code=503,
                    )
                operation, _etag = await self._store_stage(
                    operation, etag, status="succeeded", stage="runnable"
                )
            return operation
        except MpaRuntimeError as error:
            failed, _etag = await self._store_stage(
                operation,
                etag,
                status="failed_retryable",
                safe_error_code=error.code,
            )
            return failed

    async def _store_stage(
        self,
        operation: MpaLifecycleOperation,
        etag: str,
        **changes: Any,
    ) -> tuple[MpaLifecycleOperation, str]:
        updated = operation.model_copy(
            update={
                **changes,
                "updated_at": self._now(),
            }
        )
        stored = await self._repository.update_operation(updated, etag)
        return stored.value, stored.etag


def _profile_apply_request(
    request: MpaAgentOperationRequest,
) -> MpaProfileApplyRequest:
    return MpaProfileApplyRequest.from_profile(
        source_profile_id=request.source_profile_id,
        profile=request.profile,
    )


def _request_hash(request: MpaAgentOperationRequest) -> str:
    payload = request.model_dump(mode="json", by_alias=True)
    payload.pop("runtimeEndpoint", None)
    payload.pop("runtimeAuthorization", None)
    return _hash_json(payload)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return value
    return {}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bearer_value(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("bearer "):
        return token[7:].strip()
    return token


__all__ = ["MpaAgentOperationRequest", "MpaAgentOperationService"]
