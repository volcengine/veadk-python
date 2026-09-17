from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from frontend.server.mpa.operations import (
    InMemoryMpaOperationRepository,
    MpaLifecycleOperation,
    MpaOperationConflict,
    MpaOperationNotFound,
    TosMpaOperationRepository,
)


class _TosError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"TOS {status_code}")
        self.status_code = status_code


class _Object(io.BytesIO):
    def __init__(self, content: bytes, etag: str) -> None:
        super().__init__(content)
        self.etag = etag


class _FakeTosClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.put_calls: list[dict[str, Any]] = []
        self._version = 0

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        content: Any,
        forbid_overwrite: bool = False,
        if_match: str | None = None,
        **_: Any,
    ) -> SimpleNamespace:
        object_key = (bucket, key)
        current = self.objects.get(object_key)
        if forbid_overwrite and current is not None:
            raise _TosError(409)
        if if_match is not None and (current is None or current[1] != if_match):
            raise _TosError(412)
        data = content.read() if hasattr(content, "read") else bytes(content)
        self._version += 1
        etag = f'"v{self._version}"'
        self.objects[object_key] = (data, etag)
        self.put_calls.append(
            {
                "key": key,
                "forbid_overwrite": forbid_overwrite,
                "if_match": if_match,
            }
        )
        return SimpleNamespace(etag=etag)

    def get_object(self, *, bucket: str, key: str) -> _Object:
        try:
            content, etag = self.objects[(bucket, key)]
        except KeyError as error:
            raise _TosError(404) from error
        return _Object(content, etag)

    def list_objects_type2(
        self,
        *,
        bucket: str,
        prefix: str,
        continuation_token: str,
        max_keys: int,
    ) -> SimpleNamespace:
        keys = sorted(
            key
            for object_bucket, key in self.objects
            if object_bucket == bucket and key.startswith(prefix)
        )
        start = int(continuation_token or 0)
        page = keys[start : start + max_keys]
        next_index = start + len(page)
        return SimpleNamespace(
            contents=[SimpleNamespace(key=key) for key in page],
            is_truncated=next_index < len(keys),
            next_continuation_token=(
                str(next_index) if next_index < len(keys) else None
            ),
        )


def _repository(tos: _FakeTosClient) -> TosMpaOperationRepository:
    return TosMpaOperationRepository(bucket="studio", client_factory=lambda: tos)


def _operation(**overrides: Any) -> MpaLifecycleOperation:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    values: dict[str, Any] = {
        "operationKind": "create",
        "ownerId": "owner-1",
        "targetKey": "create:agent-name",
        "idempotencyKeyHash": "idem-hash",
        "requestHash": "request-hash",
        "stage": "runtime_preparing",
        "status": "active",
        "createdAt": now,
        "updatedAt": now,
    }
    values.update(overrides)
    return MpaLifecycleOperation.model_validate(values)


@pytest.mark.asyncio
async def test_create_operation_is_stable_and_idempotent_for_same_request() -> None:
    tos = _FakeTosClient()
    repository = _repository(tos)

    created = await repository.create_operation(_operation())
    replayed = await repository.create_operation(_operation())

    assert created.value.operation_id == replayed.value.operation_id
    assert replayed.etag == created.etag
    assert tos.put_calls[0]["forbid_overwrite"] is True
    stored_keys = [key for bucket, key in tos.objects if bucket == "studio"]
    assert stored_keys == [
        (
            "veadk-studio/v4/users/owner-1/mpa-agent-operations/"
            f"{created.value.operation_id}.json"
        )
    ]
    payload = json.loads(tos.objects[("studio", stored_keys[0])][0])
    assert payload["idempotencyKeyHash"] == "idem-hash"
    assert "plain-idempotency-key" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_create_operation_rejects_same_key_with_different_hash() -> None:
    repository = _repository(_FakeTosClient())

    await repository.create_operation(_operation())

    with pytest.raises(MpaOperationConflict, match="idempotency"):
        await repository.create_operation(_operation(requestHash="different"))


@pytest.mark.asyncio
async def test_update_operation_uses_etag_compare_and_swap() -> None:
    tos = _FakeTosClient()
    repository = _repository(tos)
    created = await repository.create_operation(_operation())
    updated = created.value.model_copy(
        update={
            "stage": "profile_applying",
            "runtime_id": "runtime-1",
            "updated_at": datetime(2026, 9, 15, 0, 1, tzinfo=UTC),
        }
    )

    stored = await repository.update_operation(updated, created.etag)

    assert stored.value.stage == "profile_applying"
    assert stored.value.runtime_id == "runtime-1"
    assert tos.put_calls[-1]["if_match"] == created.etag
    with pytest.raises(MpaOperationConflict):
        await repository.update_operation(updated, '"stale"')


@pytest.mark.asyncio
async def test_list_active_operations_filters_terminal_states() -> None:
    repository = _repository(_FakeTosClient())
    active = await repository.create_operation(_operation(targetKey="create:a"))
    failed = await repository.create_operation(
        _operation(
            targetKey="create:b",
            status="failed_retryable",
            stage="profile_applying",
        )
    )
    succeeded = failed.value.model_copy(
        update={
            "status": "succeeded",
            "stage": "runnable",
            "updated_at": datetime(2026, 9, 15, 0, 2, tzinfo=UTC),
        }
    )
    await repository.update_operation(succeeded, failed.etag)

    listed = await repository.list_active_operations("owner-1")

    assert [item.operation_id for item in listed] == [active.value.operation_id]


@pytest.mark.asyncio
async def test_get_operation_missing_raises_not_found() -> None:
    repository = _repository(_FakeTosClient())

    with pytest.raises(MpaOperationNotFound):
        await repository.get_operation("owner-1", "missing")


@pytest.mark.asyncio
async def test_in_memory_repository_matches_idempotency_and_cas() -> None:
    repository = InMemoryMpaOperationRepository()
    created = await repository.create_operation(_operation())
    replayed = await repository.create_operation(_operation())
    updated = created.value.model_copy(
        update={
            "stage": "profile_applying",
            "updated_at": datetime(2026, 9, 15, 0, 1, tzinfo=UTC),
        }
    )

    assert replayed.value.operation_id == created.value.operation_id
    assert replayed.created is False
    stored = await repository.update_operation(updated, created.etag)
    assert stored.value.stage == "profile_applying"
    with pytest.raises(MpaOperationConflict):
        await repository.update_operation(updated, created.etag)
    assert [
        item.operation_id for item in await repository.list_active_operations("owner-1")
    ] == [created.value.operation_id]
