"""Append-only persistence for scenario evaluation records."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, NoReturn, Protocol
from urllib.parse import quote

from frontend.server.scenario_evaluation.models import (
    ScenarioRecord,
    ScenarioRecordType,
)
from frontend.server.scenario_evaluation.errors import (
    ScenarioForbidden,
    ScenarioUnavailable,
)
from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX

_KEY_PREFIX = f"{STUDIO_STORAGE_ROOT_PREFIX}/scenario-evaluation"
_DEFAULT_MAX_RECORD_BYTES = 8 * 1024 * 1024
_CURRENT_OWNER_ID: ContextVar[str] = ContextVar(
    "scenario_evaluation_owner_id",
    default="local",
)
_CURRENT_IS_ADMIN: ContextVar[bool] = ContextVar(
    "scenario_evaluation_is_admin",
    default=False,
)
_CURRENT_OWNER_IDENTIFIERS: ContextVar[frozenset[str]] = ContextVar(
    "scenario_evaluation_owner_identifiers",
    default=frozenset({"local"}),
)
_CURRENT_AGENT_CLAIMS: ContextVar[frozenset[str]] = ContextVar(
    "scenario_evaluation_agent_claims",
    default=frozenset(),
)
_AGENT_ACCESS_RECORD_ID = "owner"
AgentAccessVerifier = Callable[[str, frozenset[str], bool, bool], Awaitable[bool]]


def bind_repository_owner(
    owner_id: str,
    *,
    is_admin: bool = False,
    identifiers: frozenset[str] | None = None,
) -> None:
    """Bind repository access to the authenticated request actor."""

    normalized = owner_id.strip()
    if not normalized:
        raise ValueError("Scenario evaluation owner id is required.")
    _CURRENT_OWNER_ID.set(normalized)
    _CURRENT_IS_ADMIN.set(is_admin)
    _CURRENT_OWNER_IDENTIFIERS.set(identifiers or frozenset({normalized.casefold()}))
    _CURRENT_AGENT_CLAIMS.set(frozenset())


def authorize_repository_agent_claim(agent_id: str) -> None:
    """Record that this request verified one server-derived Agent identity."""

    normalized = agent_id.strip()
    if not normalized:
        raise ValueError("Scenario evaluation Agent id is required.")
    _CURRENT_AGENT_CLAIMS.set(_CURRENT_AGENT_CLAIMS.get() | {normalized})


class OwnerScopedScenarioEvaluationRepository:
    """Share Agent records with admins while enforcing the Agent owner ACL."""

    def __init__(
        self,
        repository: ScenarioEvaluationRepository,
        *,
        agent_access_verifier: AgentAccessVerifier | None = None,
    ) -> None:
        self._repository = repository
        self._agent_access_verifier = agent_access_verifier

    async def append(self, record: ScenarioRecord) -> None:
        await self._authorize(record.agent_id, claim=True)
        await self._repository.append(record)

    async def append_draft(
        self,
        record: ScenarioRecord,
        *,
        expected_revision: int,
    ) -> None:
        await self._authorize(record.agent_id, claim=True)
        await self._repository.append_draft(record, expected_revision=expected_revision)

    async def get(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        record_id: str,
    ) -> ScenarioRecord | None:
        await self._authorize(agent_id, claim=False)
        return await self._repository.get(
            agent_id=agent_id,
            record_type=record_type,
            record_id=record_id,
        )

    async def list(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        owner_id: str | None = None,
    ) -> tuple[ScenarioRecord, ...]:
        await self._authorize(agent_id, claim=False)
        return await self._repository.list(
            agent_id=agent_id,
            record_type=record_type,
            owner_id=owner_id,
        )

    async def latest_version(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
    ) -> ScenarioRecord | None:
        await self._authorize(agent_id, claim=False)
        return await self._repository.latest_version(
            agent_id=agent_id,
            record_type=record_type,
            asset_id=asset_id,
        )

    async def _authorize(self, agent_id: str, *, claim: bool) -> None:
        access = await self._repository.get(
            agent_id=agent_id,
            record_type=ScenarioRecordType.AGENT_ACCESS,
            record_id=_AGENT_ACCESS_RECORD_ID,
        )
        if access is None and claim:
            owner_id = _CURRENT_OWNER_ID.get()
            verified_evidence = agent_id in _CURRENT_AGENT_CLAIMS.get()
            trusted_claim = _CURRENT_IS_ADMIN.get()
            if not trusted_claim and self._agent_access_verifier is not None:
                trusted_claim = await self._agent_access_verifier(
                    agent_id,
                    _CURRENT_OWNER_IDENTIFIERS.get(),
                    _CURRENT_IS_ADMIN.get(),
                    verified_evidence,
                )
            elif not trusted_claim:
                trusted_claim = verified_evidence
            if not trusted_claim:
                raise ScenarioForbidden(
                    "Agent ownership must be verified before creating evaluation data."
                )
            access = ScenarioRecord(
                record_id=_AGENT_ACCESS_RECORD_ID,
                agent_id=agent_id,
                owner_id=owner_id,
                record_type=ScenarioRecordType.AGENT_ACCESS,
                asset_id=_AGENT_ACCESS_RECORD_ID,
                version=1,
                created_at=datetime.now(timezone.utc),
                payload_json=json.dumps({"ownerId": owner_id}),
            )
            try:
                await self._repository.append(access)
            except ScenarioRecordConflict:
                access = await self._repository.get(
                    agent_id=agent_id,
                    record_type=ScenarioRecordType.AGENT_ACCESS,
                    record_id=_AGENT_ACCESS_RECORD_ID,
                )
        if access is None or _CURRENT_IS_ADMIN.get():
            return
        if access.owner_id != _CURRENT_OWNER_ID.get():
            raise ScenarioForbidden("Only the Agent owner or an admin may access it.")


class ScenarioRecordConflict(RuntimeError):
    """Raised when append-only identity or draft revision checks fail."""


class ScenarioEvaluationRepository(Protocol):
    async def append(self, record: ScenarioRecord) -> None: ...

    async def append_draft(
        self,
        record: ScenarioRecord,
        *,
        expected_revision: int,
    ) -> None: ...

    async def get(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        record_id: str,
    ) -> ScenarioRecord | None: ...

    async def list(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        owner_id: str | None = None,
    ) -> tuple[ScenarioRecord, ...]: ...

    async def latest_version(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
    ) -> ScenarioRecord | None: ...


class UnavailableScenarioEvaluationRepository:
    """Fail closed when Studio persistence is not configured."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def append(self, record: ScenarioRecord) -> None:
        self._raise()

    async def append_draft(
        self,
        record: ScenarioRecord,
        *,
        expected_revision: int,
    ) -> None:
        self._raise()

    async def get(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        record_id: str,
    ) -> ScenarioRecord | None:
        self._raise()

    async def list(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        owner_id: str | None = None,
    ) -> tuple[ScenarioRecord, ...]:
        self._raise()

    async def latest_version(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
    ) -> ScenarioRecord | None:
        self._raise()

    def _raise(self) -> NoReturn:
        raise ScenarioUnavailable(self._reason)


class InMemoryScenarioEvaluationRepository:
    """Deterministic repository used by unit tests and explicit local injection."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, ScenarioRecordType, str], ScenarioRecord] = {}
        self._lock = asyncio.Lock()

    async def append(self, record: ScenarioRecord) -> None:
        async with self._lock:
            self._append_locked(record)

    async def append_draft(
        self,
        record: ScenarioRecord,
        *,
        expected_revision: int,
    ) -> None:
        _validate_draft_request(record, expected_revision)
        async with self._lock:
            key = _memory_key(record)
            existing = self._records.get(key)
            if existing == record:
                return
            latest = self._latest_locked(
                agent_id=record.agent_id,
                record_type=record.record_type,
                asset_id=record.asset_id,
            )
            current_revision = latest.version if latest is not None else 0
            if current_revision != expected_revision:
                raise ScenarioRecordConflict(
                    f"Draft {record.asset_id!r} is at revision {current_revision}, "
                    f"not {expected_revision}."
                )
            self._append_locked(record)

    async def get(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        record_id: str,
    ) -> ScenarioRecord | None:
        async with self._lock:
            return self._records.get((agent_id, record_type, record_id))

    async def list(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        owner_id: str | None = None,
    ) -> tuple[ScenarioRecord, ...]:
        async with self._lock:
            records = (
                record
                for (stored_agent, stored_type, _), record in self._records.items()
                if stored_agent == agent_id
                and stored_type is record_type
                and (owner_id is None or record.owner_id == owner_id)
            )
            return _sort_records(records)

    async def latest_version(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
    ) -> ScenarioRecord | None:
        async with self._lock:
            return self._latest_locked(
                agent_id=agent_id,
                record_type=record_type,
                asset_id=asset_id,
            )

    def _append_locked(self, record: ScenarioRecord) -> None:
        key = _memory_key(record)
        existing = self._records.get(key)
        if existing is None:
            self._records[key] = record
            return
        if existing != record:
            raise ScenarioRecordConflict(
                f"Record {record.record_id!r} already has different data."
            )

    def _latest_locked(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
    ) -> ScenarioRecord | None:
        matching = [
            record
            for (stored_agent, stored_type, _), record in self._records.items()
            if stored_agent == agent_id
            and stored_type is record_type
            and record.asset_id == asset_id
        ]
        return max(matching, key=_version_sort_key) if matching else None


class TosScenarioEvaluationRepository:
    """Persist immutable records in Studio TOS storage."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        max_record_bytes: int = _DEFAULT_MAX_RECORD_BYTES,
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS scenario evaluation storage requires a bucket.")
        if max_record_bytes < 1:
            raise ValueError("max_record_bytes must be positive.")
        self._bucket = bucket
        self._client_factory = client_factory
        self._max_record_bytes = max_record_bytes

    async def append(self, record: ScenarioRecord) -> None:
        await asyncio.to_thread(self._append, record)

    async def append_draft(
        self,
        record: ScenarioRecord,
        *,
        expected_revision: int,
    ) -> None:
        _validate_draft_request(record, expected_revision)
        await asyncio.to_thread(self._append_draft, record, expected_revision)

    async def get(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        record_id: str,
    ) -> ScenarioRecord | None:
        return await asyncio.to_thread(
            self._get,
            agent_id,
            record_type,
            record_id,
        )

    async def list(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        owner_id: str | None = None,
    ) -> tuple[ScenarioRecord, ...]:
        return await asyncio.to_thread(
            self._list,
            agent_id,
            record_type,
            owner_id,
        )

    async def latest_version(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
    ) -> ScenarioRecord | None:
        return await asyncio.to_thread(
            self._latest_version,
            agent_id,
            record_type,
            asset_id,
        )

    def _append(self, record: ScenarioRecord) -> None:
        client = self._client_factory()
        content = record.model_dump_json(by_alias=True).encode("utf-8")
        self._validate_size(content)
        key = self._record_key(record)
        try:
            client.put_object(
                bucket=self._bucket,
                key=key,
                content=content,
                content_type="application/json",
                forbid_overwrite=True,
            )
        except Exception as error:
            if _status_code(error) not in {409, 412}:
                raise
            existing = self._get_bytes(client, key)
            if existing != content:
                raise ScenarioRecordConflict(
                    f"Record {record.record_id!r} already has different data."
                ) from error

    def _append_draft(
        self,
        record: ScenarioRecord,
        expected_revision: int,
    ) -> None:
        client = self._client_factory()
        key = self._record_key(record)
        try:
            existing = ScenarioRecord.model_validate_json(self._get_bytes(client, key))
        except Exception as error:
            if _status_code(error) not in {404} and not isinstance(error, KeyError):
                raise
        else:
            if existing == record:
                return
            raise ScenarioRecordConflict(
                f"Draft revision {record.record_id!r} already has different data."
            )

        latest = self._latest_version_with_client(
            client,
            agent_id=record.agent_id,
            record_type=record.record_type,
            asset_id=record.asset_id,
        )
        current_revision = latest.version if latest is not None else 0
        if current_revision != expected_revision:
            raise ScenarioRecordConflict(
                f"Draft {record.asset_id!r} is at revision {current_revision}, "
                f"not {expected_revision}."
            )
        self._append(record)

    def _get(
        self,
        agent_id: str,
        record_type: ScenarioRecordType,
        record_id: str,
    ) -> ScenarioRecord | None:
        client = self._client_factory()
        key = self._lookup_key(agent_id, record_type, record_id)
        try:
            content = self._get_bytes(client, key)
        except Exception as error:
            if _status_code(error) == 404 or isinstance(error, KeyError):
                return None
            raise
        return ScenarioRecord.model_validate_json(content)

    def _list(
        self,
        agent_id: str,
        record_type: ScenarioRecordType,
        owner_id: str | None,
    ) -> tuple[ScenarioRecord, ...]:
        client = self._client_factory()
        records = (
            ScenarioRecord.model_validate_json(self._get_bytes(client, key))
            for key in self._list_keys(client, agent_id, record_type)
        )
        return _sort_records(
            record
            for record in records
            if owner_id is None or record.owner_id == owner_id
        )

    def _latest_version(
        self,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
    ) -> ScenarioRecord | None:
        return self._latest_version_with_client(
            self._client_factory(),
            agent_id=agent_id,
            record_type=record_type,
            asset_id=asset_id,
        )

    def _latest_version_with_client(
        self,
        client: Any,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
    ) -> ScenarioRecord | None:
        records = [
            ScenarioRecord.model_validate_json(self._get_bytes(client, key))
            for key in self._list_keys(client, agent_id, record_type)
        ]
        matching = [record for record in records if record.asset_id == asset_id]
        return max(matching, key=_version_sort_key) if matching else None

    def _list_keys(
        self,
        client: Any,
        agent_id: str,
        record_type: ScenarioRecordType,
    ) -> list[str]:
        prefix = self._record_type_prefix(agent_id, record_type)
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
                str(item.key)
                for item in (getattr(output, "contents", None) or [])
                if str(getattr(item, "key", "")).endswith(".json")
            )
            if not getattr(output, "is_truncated", False):
                return keys
            continuation_token = str(
                getattr(output, "next_continuation_token", "") or ""
            )
            if not continuation_token:
                raise RuntimeError(
                    "TOS truncated a scenario evaluation listing without a token."
                )

    def _get_bytes(self, client: Any, key: str) -> bytes:
        response = client.get_object(bucket=self._bucket, key=key)
        content = response.read() if hasattr(response, "read") else b"".join(response)
        self._validate_size(content)
        return content

    def _validate_size(self, content: bytes) -> None:
        if len(content) > self._max_record_bytes:
            raise ValueError("Studio scenario evaluation record is too large.")

    @classmethod
    def _record_key(cls, record: ScenarioRecord) -> str:
        if record.record_type.value.endswith("_draft"):
            return (
                f"{cls._record_type_prefix(record.agent_id, record.record_type)}"
                f"{quote(record.asset_id, safe='')}/{record.version}.json"
            )
        return (
            f"{cls._record_type_prefix(record.agent_id, record.record_type)}"
            f"{quote(record.record_id, safe='')}.json"
        )

    @classmethod
    def _lookup_key(
        cls,
        agent_id: str,
        record_type: ScenarioRecordType,
        record_id: str,
    ) -> str:
        if record_type.value.endswith("_draft"):
            asset_id, separator, revision = record_id.rpartition(":")
            if not separator or not revision.isdigit():
                raise ValueError("draft record ID must end with a numeric revision")
            return (
                f"{cls._record_type_prefix(agent_id, record_type)}"
                f"{quote(asset_id, safe='')}/{revision}.json"
            )
        return (
            f"{cls._record_type_prefix(agent_id, record_type)}"
            f"{quote(record_id, safe='')}.json"
        )

    @staticmethod
    def _record_type_prefix(
        agent_id: str,
        record_type: ScenarioRecordType,
    ) -> str:
        return (
            f"{_KEY_PREFIX}/{quote(agent_id, safe='')}/"
            f"{quote(record_type.value, safe='')}/"
        )


def _memory_key(
    record: ScenarioRecord,
) -> tuple[str, ScenarioRecordType, str]:
    return (record.agent_id, record.record_type, record.record_id)


def _version_sort_key(record: ScenarioRecord) -> tuple[int, float, str]:
    return (record.version, record.created_at.timestamp(), record.record_id)


def _sort_records(records: Any) -> tuple[ScenarioRecord, ...]:
    return tuple(
        sorted(
            records,
            key=lambda item: (
                item.created_at.timestamp(),
                item.version,
                item.record_id,
            ),
        )
    )


def _validate_draft_request(
    record: ScenarioRecord,
    expected_revision: int,
) -> None:
    if not record.record_type.value.endswith("_draft"):
        raise ValueError("append_draft only accepts draft record types")
    if expected_revision < 0:
        raise ValueError("expected_revision cannot be negative")
    if record.version != expected_revision + 1:
        raise ScenarioRecordConflict(
            f"Draft revision must be {expected_revision + 1}, not {record.version}."
        )


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
