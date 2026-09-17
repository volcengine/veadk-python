from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from frontend.server.mpa.operations import (
    MpaLifecycleOperation,
    MpaOperationConflict,
    Stored,
)
from frontend.server.mpa.runtime_client import MpaProfile
from frontend.server.mpa.service import (
    MpaAgentOperationRequest,
    MpaAgentOperationService,
)


class MemoryOperationRepository:
    def __init__(self) -> None:
        self.records: dict[str, tuple[MpaLifecycleOperation, str]] = {}
        self.version = 0

    async def create_operation(
        self, operation: MpaLifecycleOperation
    ) -> Stored[MpaLifecycleOperation]:
        from frontend.server.mpa.operations import operation_id_for

        if not operation.operation_id:
            operation = operation.model_copy(
                update={
                    "operation_id": operation_id_for(
                        owner_id=operation.owner_id,
                        operation_kind=operation.operation_kind,
                        target_key=operation.target_key,
                        idempotency_key_hash=operation.idempotency_key_hash,
                    )
                }
            )
        current = self.records.get(operation.operation_id)
        if current is not None:
            existing, etag = current
            if (
                existing.idempotency_key_hash == operation.idempotency_key_hash
                and existing.request_hash == operation.request_hash
                and existing.operation_kind == operation.operation_kind
                and existing.target_key == operation.target_key
            ):
                return Stored(value=existing, etag=etag, created=False)
            raise MpaOperationConflict("idempotency key conflict")
        self.version += 1
        etag = f'"v{self.version}"'
        self.records[operation.operation_id] = (operation, etag)
        return Stored(value=operation, etag=etag, created=True)

    async def get_operation(
        self, owner_id: str, operation_id: str
    ) -> Stored[MpaLifecycleOperation]:
        operation, etag = self.records[operation_id]
        if operation.owner_id != owner_id:
            raise KeyError(operation_id)
        return Stored(value=operation, etag=etag)

    async def update_operation(
        self, operation: MpaLifecycleOperation, etag: str
    ) -> Stored[MpaLifecycleOperation]:
        current, current_etag = self.records[operation.operation_id]
        del current
        if current_etag != etag:
            raise MpaOperationConflict("stale")
        self.version += 1
        next_etag = f'"v{self.version}"'
        self.records[operation.operation_id] = (operation, next_etag)
        return Stored(value=operation, etag=next_etag)

    async def list_active_operations(
        self, owner_id: str
    ) -> list[MpaLifecycleOperation]:
        return [
            operation
            for operation, _etag in self.records.values()
            if operation.owner_id == owner_id and operation.status == "active"
        ]


class FakeRuntimeClient:
    def __init__(self, *, fail_apply: bool = False, fail_smoke: bool = False) -> None:
        self.fail_apply = fail_apply
        self.fail_smoke = fail_smoke
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def apply_profile(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("apply_profile", kwargs))
        if self.fail_apply:
            from frontend.server.mpa.runtime_client import MpaRuntimeError

            raise MpaRuntimeError("profile_version_conflict", status_code=409)
        return {
            "operationId": "profile-op-1",
            "status": "applied",
            "profileRevision": 7,
            "runtimeRevision": "7",
            "etag": '"7"',
        }

    async def execution_smoke(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("execution_smoke", kwargs))
        if self.fail_smoke:
            from frontend.server.mpa.runtime_client import MpaRuntimeError

            raise MpaRuntimeError("smoke_worker_not_ready", status_code=503)
        return {
            "operationId": kwargs["idempotency_key"],
            "status": "passed",
            "readinessPhase": "execution_ready",
        }


def _request(**overrides: Any) -> MpaAgentOperationRequest:
    values: dict[str, Any] = {
        "ownerId": "owner-1",
        "operationKind": "create",
        "targetKey": "create:research",
        "runtimeId": "runtime-1",
        "runtimeRegion": "cn-beijing",
        "mpaInstanceId": "mpa-1",
        "runtimeEndpoint": "https://runtime.example",
        "runtimeAuthorization": "Bearer runtime-token",
        "sourceProfileId": "draft-1",
        "profile": {
            "name": "research",
            "system": "Use cited sources.",
            "model": {"id": "model-1"},
        },
        "create": True,
    }
    values.update(overrides)
    return MpaAgentOperationRequest.model_validate(values)


def test_create_operation_applies_profile_runs_smoke_and_marks_runnable():
    async def scenario():
        repository = MemoryOperationRepository()
        runtime = FakeRuntimeClient()
        service = MpaAgentOperationService(
            repository=repository,
            runtime_client=runtime,
            now=lambda: datetime(2026, 9, 15, tzinfo=UTC),
        )

        result = await service.start(_request(), idempotency_key="idem-1")

        assert result.status == "succeeded"
        assert result.stage == "runnable"
        assert result.profile_revision == 7
        assert result.profile_operation_id == "profile-op-1"
        assert [call[0] for call in runtime.calls] == [
            "apply_profile",
            "execution_smoke",
        ]
        assert runtime.calls[0][1]["create"] is True
        assert runtime.calls[0][1]["runtime_revision"] == ""
        assert runtime.calls[1][1]["idempotency_key"] == (
            f"{result.operation_id}-smoke"
        )

    import asyncio

    asyncio.run(scenario())


def test_update_operation_applies_profile_without_smoke_and_marks_succeeded():
    async def scenario():
        repository = MemoryOperationRepository()
        runtime = FakeRuntimeClient()
        service = MpaAgentOperationService(
            repository=repository,
            runtime_client=runtime,
            now=lambda: datetime(2026, 9, 15, tzinfo=UTC),
        )

        result = await service.start(
            _request(
                operationKind="update",
                targetKey="mpa-1",
                create=False,
                runtimeRevision='"6"',
            ),
            idempotency_key="idem-1",
        )

        assert result.status == "succeeded"
        assert result.stage == "succeeded"
        assert [call[0] for call in runtime.calls] == ["apply_profile"]
        assert runtime.calls[0][1]["create"] is False
        assert runtime.calls[0][1]["runtime_revision"] == '"6"'

    import asyncio

    asyncio.run(scenario())


def test_same_operation_request_replays_without_duplicate_runtime_effects():
    async def scenario():
        repository = MemoryOperationRepository()
        runtime = FakeRuntimeClient()
        service = MpaAgentOperationService(
            repository=repository,
            runtime_client=runtime,
            now=lambda: datetime(2026, 9, 15, tzinfo=UTC),
        )
        request = _request()

        first = await service.start(request, idempotency_key="idem-1")
        second = await service.start(request, idempotency_key="idem-1")

        assert second.operation_id == first.operation_id
        assert [call[0] for call in runtime.calls] == [
            "apply_profile",
            "execution_smoke",
        ]

    import asyncio

    asyncio.run(scenario())


def test_failed_operation_replay_does_not_retry_without_explicit_retry():
    async def scenario():
        repository = MemoryOperationRepository()
        runtime = FakeRuntimeClient(fail_apply=True)
        service = MpaAgentOperationService(
            repository=repository,
            runtime_client=runtime,
            now=lambda: datetime(2026, 9, 15, tzinfo=UTC),
        )
        request = _request()

        failed = await service.start(request, idempotency_key="idem-1")
        runtime.fail_apply = False
        replay = await service.start(request, idempotency_key="idem-1")

        assert failed.status == "failed_retryable"
        assert replay.operation_id == failed.operation_id
        assert replay.status == "failed_retryable"
        assert [call[0] for call in runtime.calls] == ["apply_profile"]

    import asyncio

    asyncio.run(scenario())


def test_same_key_different_request_hash_conflicts():
    async def scenario():
        service = MpaAgentOperationService(
            repository=MemoryOperationRepository(),
            runtime_client=FakeRuntimeClient(),
            now=lambda: datetime(2026, 9, 15, tzinfo=UTC),
        )

        await service.start(_request(), idempotency_key="idem-1")
        with pytest.raises(MpaOperationConflict):
            await service.start(
                _request(
                    profile=MpaProfile(name="other", system="x", model={"id": "m"})
                ),
                idempotency_key="idem-1",
            )

    import asyncio

    asyncio.run(scenario())


def test_failed_retryable_operation_can_retry_from_safe_stage():
    async def scenario():
        repository = MemoryOperationRepository()
        runtime = FakeRuntimeClient(fail_apply=True)
        service = MpaAgentOperationService(
            repository=repository,
            runtime_client=runtime,
            now=lambda: datetime(2026, 9, 15, tzinfo=UTC),
        )
        request = _request()
        failed = await service.start(request, idempotency_key="idem-1")
        runtime.fail_apply = False

        retried = await service.retry(
            request,
            operation_id=failed.operation_id,
        )

        assert failed.status == "failed_retryable"
        assert failed.safe_error_code == "profile_version_conflict"
        assert retried.status == "succeeded"
        assert retried.retry_count == 1
        assert [call[0] for call in runtime.calls] == [
            "apply_profile",
            "apply_profile",
            "execution_smoke",
        ]

    import asyncio

    asyncio.run(scenario())
