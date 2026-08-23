from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from frontend.server.scenario_evaluation.errors import (
    ScenarioForbidden,
    ScenarioInvalidTransition,
)
from frontend.server.scenario_evaluation.executor import (
    EvaluationInfrastructureError,
    FormalEvaluationExecutor,
    RuntimeEvidence,
    RuntimeHandle,
)
from frontend.server.scenario_evaluation.models import (
    AttemptOutcome,
    BadcaseStatus,
    CandidateArtifact,
    DatasetCase,
    EvaluationDependencies,
    EvaluationRequirement,
    EvaluationRunStatus,
    EvaluationRunVersion,
    EvaluatorEvidence,
    EvaluatorKind,
    EvaluatorTrialSample,
    PolicySceneBinding,
    PublishedVersion,
    PublishPath,
    QualityRecommendationValue,
    ScenarioActor,
    ScenarioRecord,
    ScenarioRecordType,
)
from frontend.server.scenario_evaluation.repository import (
    InMemoryScenarioEvaluationRepository,
    OwnerScopedScenarioEvaluationRepository,
    bind_repository_owner,
)
from frontend.server.scenario_evaluation.run_service import FormalEvaluationManager
from frontend.server.scenario_evaluation.service import ScenarioEvaluationService
from veadk.cli.studio_rbac import StudioRole


class _Ids:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}-{self.value}"


def _actor(role: StudioRole, owner: str) -> ScenarioActor:
    return ScenarioActor(
        owner_id=owner,
        display_name=owner,
        role=role,
        identifiers=(owner,),
    )


class _Runtime:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.closed: list[str] = []
        self.block = False
        self.started = asyncio.Event()

    async def create(self, candidate):  # type: ignore[no-untyped-def]
        self.created.append(candidate.candidate_id)
        return RuntimeHandle(
            runtime_id=f"runtime-{candidate.candidate_id}",
            candidate_id=candidate.candidate_id,
        )

    async def run_case(
        self,
        handle: RuntimeHandle,
        case: DatasetCase,
        *,
        session_id: str,
        attempt_index: int,
    ) -> RuntimeEvidence:
        del case, attempt_index
        self.started.set()
        if self.block:
            await asyncio.Event().wait()
        return RuntimeEvidence(
            output=handle.candidate_id,
            trace_ref=f"trace:{session_id}",
        )

    async def close(self, handle: RuntimeHandle) -> None:
        self.closed.append(handle.candidate_id)


class _Evaluator:
    def __init__(self) -> None:
        self.failing_candidates: set[str] = set()
        self.infrastructure_failures = 0

    async def evaluate(
        self,
        evaluator,
        case,
        evidence: RuntimeEvidence,
        *,
        attempt_index: int,
    ) -> EvaluatorEvidence:
        del case, attempt_index
        if self.infrastructure_failures:
            self.infrastructure_failures -= 1
            raise EvaluationInfrastructureError("temporary evaluator outage")
        outcome = (
            AttemptOutcome.FAIL
            if evidence.output in self.failing_candidates
            else AttemptOutcome.PASS
        )
        return EvaluatorEvidence(
            evaluator_version_id=evaluator.evaluator_version_id,
            outcome=outcome,
            hard_failure=evaluator.hard_failure and outcome is AttemptOutcome.FAIL,
        )


async def _setup() -> tuple[
    InMemoryScenarioEvaluationRepository,
    ScenarioEvaluationService,
    FormalEvaluationManager,
    _Runtime,
    _Evaluator,
    ScenarioActor,
    str,
]:
    repository = InMemoryScenarioEvaluationRepository()
    ids = _Ids()

    def clock() -> datetime:
        return datetime(2026, 8, 14, 12, tzinfo=timezone.utc)

    service = ScenarioEvaluationService(repository, clock=clock, id_factory=ids)
    runtime = _Runtime()
    evaluator = _Evaluator()
    manager = FormalEvaluationManager(
        repository,
        service,
        FormalEvaluationExecutor(runtime, evaluator),
        clock=clock,
        id_factory=ids,
    )
    developer = _actor(StudioRole.ADMIN, "developer-1")
    admin = _actor(StudioRole.ADMIN, "admin-1")

    scene_draft = await service.save_scene_draft(
        developer,
        agent_id="agent-1",
        scene_id="scene-1",
        expected_revision=0,
        name="物流",
        description="物流回复必须基于查询结果",
        user_task="查询订单物流",
        pass_criteria=("回复基于物流查询结果",),
        hard_failure_conditions=("不得编造物流状态",),
        owner_id="logistics-owner",
        requirement=EvaluationRequirement.MUST_PASS,
    )
    scene = await service.publish_scene_version(
        admin,
        agent_id="agent-1",
        scene_id="scene-1",
        draft_revision=scene_draft.revision,
    )
    dataset_draft = await service.save_dataset_draft(
        developer,
        agent_id="agent-1",
        dataset_id="dataset-1",
        expected_revision=0,
        name="物流数据",
        cases=(
            DatasetCase(
                case_id="case-1",
                scene_version_id=scene.scene_version_id,
                input="订单为什么还没到？",
                expected_output="先查物流，再回答。",
                pass_criteria=scene.pass_criteria,
                source_refs=("manual:case-1",),
            ),
        ),
    )
    dataset = await service.publish_dataset_version(
        admin,
        agent_id="agent-1",
        dataset_id="dataset-1",
        draft_revision=dataset_draft.revision,
    )
    evaluator_draft = await service.save_evaluator_draft(
        developer,
        agent_id="agent-1",
        evaluator_id="evaluator-1",
        expected_revision=0,
        name="依据检查",
        scene_version_id=scene.scene_version_id,
        kind=EvaluatorKind.DETERMINISTIC,
        rule="output_contains_tool_evidence",
        rubric="",
        hard_failure=True,
    )
    await service.trial_evaluator_draft(
        developer,
        agent_id="agent-1",
        evaluator_id=evaluator_draft.evaluator_id,
        expected_revision=evaluator_draft.revision,
        dataset_version_id=dataset.dataset_version_id,
        samples=(
            EvaluatorTrialSample(
                sample_id="case-1",
                input="订单为什么还没到？",
                expected_output="先查物流，再回答。",
                agent_output="candidate-trial",
                expected_outcome=AttemptOutcome.PASS,
            ),
        ),
        evaluator=evaluator,
    )
    evaluator_version = await service.publish_evaluator_version(
        admin,
        agent_id="agent-1",
        evaluator_id="evaluator-1",
        draft_revision=evaluator_draft.revision,
    )
    policy_draft = await service.save_policy_draft(
        developer,
        agent_id="agent-1",
        policy_id="policy-1",
        expected_revision=0,
        name="发布质量检查",
        bindings=(
            PolicySceneBinding(
                scene_version_id=scene.scene_version_id,
                dataset_version_id=dataset.dataset_version_id,
                evaluator_version_ids=(evaluator_version.evaluator_version_id,),
                requirement=EvaluationRequirement.MUST_PASS,
            ),
        ),
    )
    policy = await service.publish_policy_version(
        admin,
        agent_id="agent-1",
        policy_id="policy-1",
        draft_revision=policy_draft.revision,
    )
    return (
        repository,
        service,
        manager,
        runtime,
        evaluator,
        developer,
        policy.policy_version_id,
    )


@pytest.mark.asyncio
async def test_formal_run_uses_complete_policy_and_persists_recommendation() -> None:
    _, service, manager, _, _, developer, policy_id = await _setup()
    candidate = await service.create_candidate_version(
        developer,
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:candidate",
            topology_digest="sha256:topology",
        ),
    )

    queued = await manager.start(
        developer,
        agent_id="agent-1",
        candidate_id=candidate.candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
    )
    completed = await manager.wait(
        agent_id="agent-1",
        evaluation_id=queued.evaluation_id,
    )

    assert queued.status is EvaluationRunStatus.QUEUED
    assert completed.status is EvaluationRunStatus.SUCCEEDED
    assert completed.recommendation is not None
    assert completed.recommendation.value is QualityRecommendationValue.RECOMMEND
    assert len(completed.scenes[0].cases[0].candidate_attempts) == 3


@pytest.mark.asyncio
async def test_client_cannot_reduce_the_published_policy_case_set() -> None:
    _, service, manager, _, _, developer, policy_id = await _setup()
    candidate = await service.create_candidate_version(
        developer,
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:candidate",
            topology_digest="sha256:topology",
        ),
    )

    with pytest.raises(ScenarioInvalidTransition):
        await manager.start(
            developer,
            agent_id="agent-1",
            candidate_id=candidate.candidate_id,
            policy_version_id=policy_id,
            environment_fingerprint="sha256:runtime",
            selected_case_ids=(),
        )


@pytest.mark.asyncio
async def test_cancel_waits_for_terminal_state_and_closes_runtime() -> None:
    _, service, manager, runtime, _, developer, policy_id = await _setup()
    runtime.block = True
    candidate = await service.create_candidate_version(
        developer,
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:candidate",
            topology_digest="sha256:topology",
        ),
    )
    queued = await manager.start(
        developer,
        agent_id="agent-1",
        candidate_id=candidate.candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
    )
    await runtime.started.wait()

    cancelled = await manager.cancel(
        developer,
        agent_id="agent-1",
        evaluation_id=queued.evaluation_id,
    )

    assert cancelled.status is EvaluationRunStatus.CANCELLED
    assert runtime.closed == [candidate.candidate_id]


@pytest.mark.asyncio
async def test_badcase_closes_only_for_new_candidate_with_same_standard_scope() -> None:
    _, service, manager, _, evaluator, developer, policy_id = await _setup()
    failing = await service.create_candidate_version(
        developer,
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:failing",
            topology_digest="sha256:topology",
        ),
    )
    evaluator.failing_candidates.add(failing.candidate_id)
    first = await manager.start(
        developer,
        agent_id="agent-1",
        candidate_id=failing.candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
    )
    await manager.wait(agent_id="agent-1", evaluation_id=first.evaluation_id)

    opened = await manager.list_badcases(agent_id="agent-1")
    assert len(opened) == 1
    assert opened[0].status is BadcaseStatus.OPEN

    evaluator.failing_candidates.clear()
    same_candidate_retry = await manager.start(
        developer,
        agent_id="agent-1",
        candidate_id=failing.candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
    )
    await manager.wait(
        agent_id="agent-1",
        evaluation_id=same_candidate_retry.evaluation_id,
    )
    still_open = await manager.list_badcases(agent_id="agent-1")
    assert still_open[0].status is BadcaseStatus.OPEN

    fixed = await service.create_candidate_version(
        developer,
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:fixed",
            topology_digest="sha256:topology",
        ),
    )
    verification = await manager.start(
        developer,
        agent_id="agent-1",
        candidate_id=fixed.candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
    )
    verifying = await manager.list_badcases(agent_id="agent-1")
    assert verifying[0].status is BadcaseStatus.VERIFYING
    await manager.wait(
        agent_id="agent-1",
        evaluation_id=verification.evaluation_id,
    )

    closed = await manager.list_badcases(agent_id="agent-1")
    assert closed[0].status is BadcaseStatus.CLOSED
    assert closed[0].resolution_candidate_id == fixed.candidate_id


@pytest.mark.asyncio
async def test_published_candidate_becomes_the_next_formal_evaluation_baseline() -> (
    None
):
    repository, service, manager, runtime, _, developer, policy_id = await _setup()
    baseline = await service.create_candidate_version(
        developer,
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:baseline",
            topology_digest="sha256:topology",
        ),
    )
    published = PublishedVersion(
        published_version_id="published-v1",
        agent_id="agent-1",
        version=1,
        candidate_id=baseline.candidate_id,
        candidate_artifact=baseline.artifact,
        publish_intent_id="intent-1",
        publish_path=PublishPath.NORMAL,
        deployment_ref="deploy-1",
        created_at=datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        created_by="developer-1",
    )
    await repository.append(
        ScenarioRecord(
            record_id=published.published_version_id,
            agent_id="agent-1",
            owner_id="developer-1",
            record_type=ScenarioRecordType.PUBLISHED_VERSION,
            asset_id="online",
            version=1,
            created_at=published.created_at,
            payload_json=published.model_dump_json(by_alias=True),
        )
    )
    candidate = await service.create_candidate_version(
        developer,
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:new-candidate",
            topology_digest="sha256:topology",
        ),
    )

    queued = await manager.start(
        developer,
        agent_id="agent-1",
        candidate_id=candidate.candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
    )
    completed = await manager.wait(
        agent_id="agent-1",
        evaluation_id=queued.evaluation_id,
    )

    assert runtime.created == [candidate.candidate_id, baseline.candidate_id]
    assert completed.baseline_version_id == published.published_version_id
    assert completed.dependencies.baseline_version_id == published.published_version_id
    assert len(completed.scenes[0].cases[0].baseline_attempts) == 3


@pytest.mark.asyncio
async def test_developer_retries_only_an_invalid_attempt_and_keeps_its_history() -> (
    None
):
    _, service, manager, _, evaluator, developer, policy_id = await _setup()
    evaluator.infrastructure_failures = 2
    candidate = await service.create_candidate_version(
        developer,
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:manual-retry",
            topology_digest="sha256:topology",
        ),
    )
    queued = await manager.start(
        developer,
        agent_id="agent-1",
        candidate_id=candidate.candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
    )
    completed = await manager.wait(
        agent_id="agent-1",
        evaluation_id=queued.evaluation_id,
    )
    invalid = completed.scenes[0].cases[0].candidate_attempts[0]
    assert invalid.outcome is AttemptOutcome.INFRA_ERROR

    retried = await manager.retry_invalid_attempt(
        developer,
        agent_id="agent-1",
        evaluation_id=completed.evaluation_id,
        scene_version_id="scene-1:v1",
        case_id="case-1",
        target="candidate",
        attempt_index=1,
    )
    replacement = retried.scenes[0].cases[0].candidate_attempts[0]

    assert replacement.outcome is AttemptOutcome.PASS
    assert replacement.manual_retry_count == 1
    assert replacement.superseded_invalid_attempts[0].session_id == invalid.session_id
    assert len(replacement.superseded_invalid_attempts) == 1

    with pytest.raises(ScenarioInvalidTransition, match="infrastructure"):
        await manager.retry_invalid_attempt(
            developer,
            agent_id="agent-1",
            evaluation_id=retried.evaluation_id,
            scene_version_id="scene-1:v1",
            case_id="case-1",
            target="candidate",
            attempt_index=1,
        )


@pytest.mark.asyncio
async def test_only_admin_can_start_formal_evaluation() -> None:
    _, service, manager, _, _, _, policy_id = await _setup()
    candidate = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:developer-candidate",
            topology_digest="sha256:topology",
        ),
    )

    with pytest.raises(ScenarioForbidden, match="Admin"):
        await manager.start(
            _actor(StudioRole.DEVELOPER, "developer-1"),
            agent_id="agent-1",
            candidate_id=candidate.candidate_id,
            policy_version_id=policy_id,
            environment_fingerprint="sha256:runtime",
        )


@pytest.mark.asyncio
async def test_admin_can_run_developer_owned_candidate_in_shared_agent_scope() -> None:
    repository, _, _, runtime, evaluator, _, policy_id = await _setup()

    async def verify_agent(*_args: object) -> bool:
        return True

    access_repository = OwnerScopedScenarioEvaluationRepository(
        repository,
        agent_access_verifier=verify_agent,
    )
    service = ScenarioEvaluationService(access_repository)
    manager = FormalEvaluationManager(
        access_repository,
        service,
        FormalEvaluationExecutor(runtime, evaluator),
    )

    bind_repository_owner("developer-1")
    candidate = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:developer-candidate",
            topology_digest="sha256:topology",
        ),
    )

    bind_repository_owner("admin-1", is_admin=True)
    queued = await manager.start(
        _actor(StudioRole.ADMIN, "admin-1"),
        agent_id="agent-1",
        candidate_id=candidate.candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
    )
    completed = await manager.wait(
        agent_id="agent-1",
        evaluation_id=queued.evaluation_id,
    )

    assert completed.status is EvaluationRunStatus.SUCCEEDED
    assert completed.created_by == "admin-1"


@pytest.mark.asyncio
async def test_stale_run_from_lost_worker_is_failed_on_read() -> None:
    repository = InMemoryScenarioEvaluationRepository()
    now = datetime(2026, 8, 14, 12, tzinfo=timezone.utc)
    service = ScenarioEvaluationService(repository, clock=lambda: now)
    manager = FormalEvaluationManager(
        repository,
        service,
        FormalEvaluationExecutor(_Runtime(), _Evaluator()),
        clock=lambda: now,
    )
    run = EvaluationRunVersion(
        evaluation_id="evaluation-orphaned",
        agent_id="agent-1",
        revision=2,
        status=EvaluationRunStatus.RUNNING,
        candidate_id="candidate-1",
        policy_version_id="policy-1:v1",
        dependencies=EvaluationDependencies(
            candidate_id="candidate-1",
            scene_version_ids=("scene-1:v1",),
            dataset_version_ids=("dataset-1:v1",),
            evaluator_version_ids=("evaluator-1:v1",),
            policy_version_id="policy-1:v1",
            environment_fingerprint="sha256:runtime",
        ),
        created_at=now - timedelta(hours=5),
        updated_at=now - timedelta(hours=5),
        created_by="admin-1",
    )
    await repository.append(
        ScenarioRecord(
            record_id=f"{run.evaluation_id}:{run.revision}",
            agent_id=run.agent_id,
            owner_id=run.created_by,
            record_type=ScenarioRecordType.EVALUATION_RUN,
            asset_id=run.evaluation_id,
            version=run.revision,
            created_at=run.updated_at,
            payload_json=run.model_dump_json(by_alias=True),
        )
    )

    recovered = await manager.get(
        agent_id="agent-1",
        evaluation_id=run.evaluation_id,
    )

    assert recovered.status is EvaluationRunStatus.FAILED
    assert recovered.revision == 3
    assert "worker is no longer available" in recovered.error_message
