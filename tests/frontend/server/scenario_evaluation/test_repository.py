from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest

from frontend.server.scenario_evaluation.errors import ScenarioUnavailable
from frontend.server.scenario_evaluation.models import (
    ScenarioRecord,
    ScenarioRecordType,
)
from frontend.server.scenario_evaluation.repository import (
    InMemoryScenarioEvaluationRepository,
    OwnerScopedScenarioEvaluationRepository,
    ScenarioRecordConflict,
    TosScenarioEvaluationRepository,
    UnavailableScenarioEvaluationRepository,
    bind_repository_owner,
    authorize_repository_agent_claim,
)
from frontend.server.scenario_evaluation.errors import ScenarioForbidden


def _record(
    record_id: str,
    *,
    agent_id: str = "agent-1",
    owner_id: str = "developer-1",
    record_type: ScenarioRecordType = ScenarioRecordType.CANDIDATE_VERSION,
    asset_id: str = "candidate",
    version: int = 1,
    minute: int = 0,
    payload_json: str = '{"value":"original"}',
) -> ScenarioRecord:
    return ScenarioRecord(
        record_id=record_id,
        agent_id=agent_id,
        owner_id=owner_id,
        record_type=record_type,
        asset_id=asset_id,
        version=version,
        created_at=datetime(2026, 8, 14, 12, minute, tzinfo=timezone.utc),
        payload_json=payload_json,
    )


@pytest.mark.asyncio
async def test_in_memory_repository_appends_gets_and_lists_in_stable_order() -> None:
    repository = InMemoryScenarioEvaluationRepository()
    later = _record("candidate-2", version=2, minute=2)
    earlier = _record("candidate-1", version=1, minute=1)

    await repository.append(later)
    await repository.append(earlier)

    assert (
        await repository.get(
            agent_id="agent-1",
            record_type=ScenarioRecordType.CANDIDATE_VERSION,
            record_id="candidate-1",
        )
        == earlier
    )
    assert await repository.list(
        agent_id="agent-1",
        record_type=ScenarioRecordType.CANDIDATE_VERSION,
    ) == (earlier, later)
    assert (
        await repository.latest_version(
            agent_id="agent-1",
            record_type=ScenarioRecordType.CANDIDATE_VERSION,
            asset_id="candidate",
        )
        == later
    )


@pytest.mark.asyncio
async def test_immutable_append_is_idempotent_for_same_content_and_conflicts_otherwise() -> (
    None
):
    repository = InMemoryScenarioEvaluationRepository()
    original = _record("candidate-1")

    await repository.append(original)
    await repository.append(original)

    with pytest.raises(ScenarioRecordConflict):
        await repository.append(
            original.model_copy(update={"payload_json": '{"value":"changed"}'})
        )


@pytest.mark.asyncio
async def test_draft_append_uses_expected_revision_and_never_overwrites() -> None:
    repository = InMemoryScenarioEvaluationRepository()
    first = _record(
        "dataset-1:1",
        record_type=ScenarioRecordType.DATASET_DRAFT,
        asset_id="dataset-1",
        version=1,
    )
    second = _record(
        "dataset-1:2",
        record_type=ScenarioRecordType.DATASET_DRAFT,
        asset_id="dataset-1",
        version=2,
        minute=1,
    )

    await repository.append_draft(first, expected_revision=0)
    with pytest.raises(ScenarioRecordConflict):
        await repository.append_draft(second, expected_revision=0)
    await repository.append_draft(second, expected_revision=1)

    assert (
        await repository.latest_version(
            agent_id="agent-1",
            record_type=ScenarioRecordType.DATASET_DRAFT,
            asset_id="dataset-1",
        )
        == second
    )


@pytest.mark.asyncio
async def test_agent_and_owner_scopes_do_not_leak_records() -> None:
    repository = InMemoryScenarioEvaluationRepository()
    owned = _record("candidate-owned")
    other_owner = _record("candidate-other", owner_id="developer-2", minute=1)
    other_agent = _record("candidate-agent-2", agent_id="agent-2", minute=2)
    for record in (owned, other_owner, other_agent):
        await repository.append(record)

    assert await repository.list(
        agent_id="agent-1",
        record_type=ScenarioRecordType.CANDIDATE_VERSION,
        owner_id="developer-1",
    ) == (owned,)


@pytest.mark.asyncio
async def test_agent_repository_rejects_another_developer_but_allows_admin_handoff() -> (
    None
):
    async def verify_agent(*_args: object) -> bool:
        return True

    repository = OwnerScopedScenarioEvaluationRepository(
        InMemoryScenarioEvaluationRepository(),
        agent_access_verifier=verify_agent,
    )
    bind_repository_owner("developer-1")
    owned = _record("candidate-owned")
    await repository.append(owned)

    bind_repository_owner("developer-2")
    with pytest.raises(ScenarioForbidden):
        await repository.get(
            agent_id="agent-1",
            record_type=ScenarioRecordType.CANDIDATE_VERSION,
            record_id="candidate-owned",
        )

    bind_repository_owner("admin", is_admin=True)
    assert (
        await repository.get(
            agent_id="agent-1",
            record_type=ScenarioRecordType.CANDIDATE_VERSION,
            record_id="candidate-owned",
        )
        is not None
    )


@pytest.mark.asyncio
async def test_agent_repository_rejects_an_unverified_first_claim() -> None:
    evidence_checks: list[bool] = []

    async def verify_agent(
        _agent_id: str,
        _identifiers: frozenset[str],
        _is_admin: bool,
        verified_evidence: bool,
    ) -> bool:
        evidence_checks.append(verified_evidence)
        return verified_evidence

    repository = OwnerScopedScenarioEvaluationRepository(
        InMemoryScenarioEvaluationRepository(),
        agent_access_verifier=verify_agent,
    )
    bind_repository_owner("developer-1")

    with pytest.raises(ScenarioForbidden, match="ownership must be verified"):
        await repository.append(_record("candidate-owned"))

    authorize_repository_agent_claim("agent-1")
    await repository.append(_record("candidate-owned"))
    assert evidence_checks == [False, True]


class _TosError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"TOS status {status_code}")
        self.status_code = status_code


class _FakeTosClient:
    def __init__(self, *, page_size: int = 1000) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[dict[str, object]] = []
        self.page_size = page_size

    def put_object(self, **kwargs: object) -> None:
        self.put_calls.append(kwargs)
        key = str(kwargs["key"])
        if kwargs.get("forbid_overwrite") and key in self.objects:
            raise _TosError(412)
        self.objects[key] = bytes(kwargs["content"])

    def get_object(self, **kwargs: object) -> BytesIO:
        return BytesIO(self.objects[str(kwargs["key"])])

    def list_objects_type2(self, **kwargs: object) -> SimpleNamespace:
        prefix = str(kwargs["prefix"])
        offset = int(str(kwargs.get("continuation_token") or "0"))
        keys = sorted(key for key in self.objects if key.startswith(prefix))
        page = keys[offset : offset + self.page_size]
        next_offset = offset + len(page)
        return SimpleNamespace(
            contents=[SimpleNamespace(key=key) for key in page],
            is_truncated=next_offset < len(keys),
            next_continuation_token=(
                str(next_offset) if next_offset < len(keys) else ""
            ),
        )


@pytest.mark.asyncio
async def test_tos_repository_uses_forbid_overwrite_and_validates_conflicts() -> None:
    client = _FakeTosClient()
    repository = TosScenarioEvaluationRepository(
        bucket="studio-bucket",
        client_factory=lambda: client,
    )
    original = _record("candidate-1")

    await repository.append(original)
    await repository.append(original)

    assert client.put_calls[0]["forbid_overwrite"] is True
    with pytest.raises(ScenarioRecordConflict):
        await repository.append(
            original.model_copy(update={"payload_json": '{"value":"changed"}'})
        )


@pytest.mark.asyncio
async def test_tos_repository_paginates_and_returns_validated_records() -> None:
    client = _FakeTosClient(page_size=1)
    repository = TosScenarioEvaluationRepository(
        bucket="studio-bucket",
        client_factory=lambda: client,
    )
    first = _record("candidate-1", minute=1)
    second = _record("candidate-2", version=2, minute=2)
    await repository.append(first)
    await repository.append(second)

    assert await repository.list(
        agent_id="agent-1",
        record_type=ScenarioRecordType.CANDIDATE_VERSION,
    ) == (first, second)


@pytest.mark.asyncio
async def test_tos_repository_rejects_oversized_records_on_write_and_read() -> None:
    client = _FakeTosClient()
    repository = TosScenarioEvaluationRepository(
        bucket="studio-bucket",
        client_factory=lambda: client,
        max_record_bytes=700,
    )
    oversized = _record("candidate-large", payload_json='{"value":"' + "x" * 900 + '"}')

    with pytest.raises(ValueError, match="too large"):
        await repository.append(oversized)

    normal = _record("candidate-1")
    await repository.append(normal)
    key = next(iter(client.objects))
    client.objects[key] += b" " * 1000
    with pytest.raises(ValueError, match="too large"):
        await repository.get(
            agent_id="agent-1",
            record_type=ScenarioRecordType.CANDIDATE_VERSION,
            record_id="candidate-1",
        )


def test_record_timestamps_are_part_of_conflict_identity() -> None:
    original = _record("candidate-1")
    later = original.model_copy(
        update={"created_at": original.created_at + timedelta(seconds=1)}
    )

    assert original != later


@pytest.mark.asyncio
async def test_unavailable_repository_fails_explicitly_instead_of_using_memory() -> (
    None
):
    repository = UnavailableScenarioEvaluationRepository(
        "persistent storage is not configured"
    )

    with pytest.raises(ScenarioUnavailable, match="persistent storage"):
        await repository.list(
            agent_id="agent-1",
            record_type=ScenarioRecordType.CANDIDATE_VERSION,
        )
