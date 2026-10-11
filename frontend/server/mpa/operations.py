# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""TOS-CAS persistence for Studio MPA lifecycle operations."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

_MAX_OBJECT_BYTES = 2 * 1024 * 1024
MPA_OPERATION_ROOT_PREFIX = "veadk-studio/v4"
_Value = TypeVar("_Value", bound=BaseModel)
_TERMINAL_STATUSES = {"succeeded", "failed_terminal", "cancelled"}


class MpaOperationNotFound(LookupError):
    """The requested MPA lifecycle operation does not exist."""


class MpaOperationConflict(RuntimeError):
    """The MPA operation changed concurrently or idempotency does not match."""


@dataclass(frozen=True)
class Stored(Generic[_Value]):
    value: _Value
    etag: str
    created: bool = False


class MpaLifecycleOperation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    operation_id: str = Field(default="", alias="operationId")
    operation_kind: Literal["create", "update"] = Field(alias="operationKind")
    owner_id: str = Field(alias="ownerId", min_length=1)
    target_key: str = Field(alias="targetKey", min_length=1)
    idempotency_key_hash: str = Field(alias="idempotencyKeyHash", min_length=1)
    request_hash: str = Field(alias="requestHash", min_length=1)
    stage: str
    status: Literal[
        "active",
        "succeeded",
        "failed_retryable",
        "failed_terminal",
        "cancelled",
    ]
    mpa_instance_id: str = Field(default="", alias="mpaInstanceId")
    runtime_id: str = Field(default="", alias="runtimeId")
    runtime_region: str = Field(default="", alias="runtimeRegion")
    runtime_revision: str = Field(default="", alias="runtimeRevision")
    profile_digest: str = Field(default="", alias="profileDigest")
    profile_revision: int | None = Field(default=None, alias="profileRevision")
    profile_operation_id: str = Field(default="", alias="profileOperationId")
    safe_error_code: str = Field(default="", alias="safeErrorCode")
    retry_count: int = Field(default=0, alias="retryCount")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


def operation_id_for(
    *,
    owner_id: str,
    operation_kind: str,
    target_key: str,
    idempotency_key_hash: str,
) -> str:
    canonical = json.dumps(
        {
            "ownerId": owner_id,
            "operationKind": operation_kind,
            "targetKey": target_key,
            "idempotencyKeyHash": idempotency_key_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"mpaop_{hashlib.sha256(canonical).hexdigest()[:32]}"


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class TosMpaOperationRepository:
    """Persist MPA lifecycle operations with TOS conditional writes."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        root_prefix: str = MPA_OPERATION_ROOT_PREFIX,
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS MPA operation storage requires a bucket.")
        self._bucket = bucket
        self._client_factory = client_factory
        self._root_prefix = root_prefix.strip("/")

    async def create_operation(
        self, operation: MpaLifecycleOperation
    ) -> Stored[MpaLifecycleOperation]:
        return await asyncio.to_thread(self._create_operation, operation)

    async def get_operation(
        self, owner_id: str, operation_id: str
    ) -> Stored[MpaLifecycleOperation]:
        return await asyncio.to_thread(self._get_operation, owner_id, operation_id)

    async def update_operation(
        self,
        operation: MpaLifecycleOperation,
        etag: str,
    ) -> Stored[MpaLifecycleOperation]:
        return await asyncio.to_thread(self._update_operation, operation, etag)

    async def list_active_operations(
        self, owner_id: str
    ) -> list[MpaLifecycleOperation]:
        return await asyncio.to_thread(self._list_active_operations, owner_id)

    def _create_operation(
        self, operation: MpaLifecycleOperation
    ) -> Stored[MpaLifecycleOperation]:
        resolved = self._with_operation_id(operation)
        key = self._operation_key(resolved.owner_id, resolved.operation_id)
        client = self._client_factory()
        try:
            return self._create(client, key, resolved)
        except MpaOperationConflict:
            current = self._read(client, key, MpaLifecycleOperation)
            if (
                current.value.idempotency_key_hash == resolved.idempotency_key_hash
                and current.value.request_hash == resolved.request_hash
                and current.value.operation_kind == resolved.operation_kind
                and current.value.target_key == resolved.target_key
            ):
                return current
            raise MpaOperationConflict(
                "MPA operation idempotency key was reused with different input."
            )

    def _get_operation(
        self, owner_id: str, operation_id: str
    ) -> Stored[MpaLifecycleOperation]:
        return self._read(
            self._client_factory(),
            self._operation_key(owner_id, operation_id),
            MpaLifecycleOperation,
        )

    def _update_operation(
        self,
        operation: MpaLifecycleOperation,
        etag: str,
    ) -> Stored[MpaLifecycleOperation]:
        resolved = self._with_operation_id(operation)
        return self._replace(
            self._client_factory(),
            self._operation_key(resolved.owner_id, resolved.operation_id),
            resolved,
            etag,
        )

    def _list_active_operations(self, owner_id: str) -> list[MpaLifecycleOperation]:
        client = self._client_factory()
        operations: list[MpaLifecycleOperation] = []
        for key in self._list_keys(client, f"{self._owner_prefix(owner_id)}/"):
            if not key.endswith(".json"):
                continue
            try:
                operation = self._read(client, key, MpaLifecycleOperation).value
            except MpaOperationNotFound:
                continue
            if operation.status not in _TERMINAL_STATUSES:
                operations.append(operation)
        return sorted(operations, key=lambda item: item.updated_at, reverse=True)

    def _with_operation_id(
        self, operation: MpaLifecycleOperation
    ) -> MpaLifecycleOperation:
        if operation.operation_id:
            return operation
        return operation.model_copy(
            update={
                "operation_id": operation_id_for(
                    owner_id=operation.owner_id,
                    operation_kind=operation.operation_kind,
                    target_key=operation.target_key,
                    idempotency_key_hash=operation.idempotency_key_hash,
                )
            }
        )

    def _create(self, client: Any, key: str, value: _Value) -> Stored[_Value]:
        content = self._encode(value)
        try:
            output = client.put_object(
                bucket=self._bucket,
                key=key,
                content=content,
                content_length=len(content),
                content_type="application/json",
                forbid_overwrite=True,
            )
        except Exception as error:
            if _status_code(error) in {409, 412}:
                raise MpaOperationConflict("MPA operation already exists.") from error
            raise
        return Stored(
            value=value, etag=self._write_etag(output, client, key), created=True
        )

    def _replace(
        self, client: Any, key: str, value: _Value, etag: str
    ) -> Stored[_Value]:
        content = self._encode(value)
        try:
            output = client.put_object(
                bucket=self._bucket,
                key=key,
                content=content,
                content_length=len(content),
                content_type="application/json",
                if_match=etag,
            )
        except Exception as error:
            if _status_code(error) in {409, 412}:
                raise MpaOperationConflict(
                    "MPA operation changed concurrently; reload and try again."
                ) from error
            if _status_code(error) == 404:
                raise MpaOperationNotFound("MPA operation does not exist.") from error
            raise
        return Stored(value=value, etag=self._write_etag(output, client, key))

    def _read(self, client: Any, key: str, model: type[_Value]) -> Stored[_Value]:
        payload, etag = self._read_payload(client, key)
        return Stored(value=model.model_validate(payload), etag=etag)

    def _read_payload(self, client: Any, key: str) -> tuple[dict[str, Any], str]:
        try:
            response = client.get_object(bucket=self._bucket, key=key)
        except Exception as error:
            if _status_code(error) == 404:
                raise MpaOperationNotFound("MPA operation does not exist.") from error
            raise
        content = response.read(_MAX_OBJECT_BYTES + 1)
        if not isinstance(content, bytes) or len(content) > _MAX_OBJECT_BYTES:
            raise ValueError("MPA operation object is invalid or too large.")
        etag = self._etag(response)
        if not etag:
            raise RuntimeError("TOS MPA operation object did not include an ETag.")
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise TypeError("MPA operation object must be a JSON object.")
        return payload, etag

    def _list_keys(self, client: Any, prefix: str) -> list[str]:
        continuation_token = ""
        keys: list[str] = []
        while True:
            output = client.list_objects_type2(
                bucket=self._bucket,
                prefix=prefix,
                continuation_token=continuation_token,
                max_keys=1000,
            )
            keys.extend(
                str(item.key) for item in (getattr(output, "contents", None) or [])
            )
            if not getattr(output, "is_truncated", False):
                return keys
            continuation_token = str(
                getattr(output, "next_continuation_token", "") or ""
            )
            if not continuation_token:
                raise RuntimeError(
                    "TOS truncated an MPA operation listing without a continuation token."
                )

    @staticmethod
    def _encode(value: BaseModel) -> bytes:
        content = json.dumps(
            value.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(content) > _MAX_OBJECT_BYTES:
            raise ValueError("MPA operation object is too large.")
        return content

    def _write_etag(self, output: Any, client: Any, key: str) -> str:
        etag = self._etag(output)
        if etag:
            return etag
        response = client.get_object(bucket=self._bucket, key=key)
        etag = self._etag(response)
        if not etag:
            raise RuntimeError("TOS MPA operation write did not include an ETag.")
        return etag

    @staticmethod
    def _etag(value: Any) -> str:
        direct = getattr(value, "etag", None)
        if direct:
            return str(direct)
        return str(getattr(getattr(value, "meta", None), "etag", "") or "")

    def _operation_key(self, owner_id: str, operation_id: str) -> str:
        return f"{self._owner_prefix(owner_id)}/{self._part(operation_id)}.json"

    def _owner_prefix(self, owner_id: str) -> str:
        return f"{self._root_prefix}/users/{self._part(owner_id)}/mpa-agent-operations"

    @staticmethod
    def _part(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("TOS MPA operation key segment cannot be empty.")
        return quote(text, safe="")


class InMemoryMpaOperationRepository:
    """Process-local MPA operation store for local Studio development."""

    def __init__(self) -> None:
        self._records: dict[str, tuple[MpaLifecycleOperation, str]] = {}
        self._version = 0
        self._lock = asyncio.Lock()

    async def create_operation(
        self, operation: MpaLifecycleOperation
    ) -> Stored[MpaLifecycleOperation]:
        async with self._lock:
            resolved = self._with_operation_id(operation)
            current = self._records.get(resolved.operation_id)
            if current is not None:
                existing, etag = current
                if (
                    existing.idempotency_key_hash == resolved.idempotency_key_hash
                    and existing.request_hash == resolved.request_hash
                    and existing.operation_kind == resolved.operation_kind
                    and existing.target_key == resolved.target_key
                ):
                    return Stored(value=deepcopy(existing), etag=etag, created=False)
                raise MpaOperationConflict(
                    "MPA operation idempotency key was reused with different input."
                )
            etag = self._next_etag()
            self._records[resolved.operation_id] = (deepcopy(resolved), etag)
            return Stored(value=deepcopy(resolved), etag=etag, created=True)

    async def get_operation(
        self, owner_id: str, operation_id: str
    ) -> Stored[MpaLifecycleOperation]:
        async with self._lock:
            current = self._records.get(operation_id)
            if current is None or current[0].owner_id != owner_id:
                raise MpaOperationNotFound("MPA operation does not exist.")
            operation, etag = current
            return Stored(value=deepcopy(operation), etag=etag)

    async def update_operation(
        self,
        operation: MpaLifecycleOperation,
        etag: str,
    ) -> Stored[MpaLifecycleOperation]:
        async with self._lock:
            resolved = self._with_operation_id(operation)
            current = self._records.get(resolved.operation_id)
            if current is None:
                raise MpaOperationNotFound("MPA operation does not exist.")
            _existing, current_etag = current
            if current_etag != etag:
                raise MpaOperationConflict(
                    "MPA operation changed concurrently; reload and try again."
                )
            next_etag = self._next_etag()
            self._records[resolved.operation_id] = (deepcopy(resolved), next_etag)
            return Stored(value=deepcopy(resolved), etag=next_etag)

    async def list_active_operations(
        self, owner_id: str
    ) -> list[MpaLifecycleOperation]:
        async with self._lock:
            operations = [
                deepcopy(operation)
                for operation, _etag in self._records.values()
                if operation.owner_id == owner_id
                and operation.status not in _TERMINAL_STATUSES
            ]
        return sorted(operations, key=lambda item: item.updated_at, reverse=True)

    def _with_operation_id(
        self, operation: MpaLifecycleOperation
    ) -> MpaLifecycleOperation:
        if operation.operation_id:
            return operation
        return operation.model_copy(
            update={
                "operation_id": operation_id_for(
                    owner_id=operation.owner_id,
                    operation_kind=operation.operation_kind,
                    target_key=operation.target_key,
                    idempotency_key_hash=operation.idempotency_key_hash,
                )
            }
        )

    def _next_etag(self) -> str:
        self._version += 1
        return f'"mem-{self._version}"'


__all__ = [
    "InMemoryMpaOperationRepository",
    "MpaLifecycleOperation",
    "MpaOperationConflict",
    "MpaOperationNotFound",
    "MPA_OPERATION_ROOT_PREFIX",
    "Stored",
    "TosMpaOperationRepository",
    "operation_id_for",
]
