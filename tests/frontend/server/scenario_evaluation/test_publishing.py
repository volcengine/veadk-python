from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from frontend.server.scenario_evaluation.errors import (
    ScenarioEvaluationRunning,
    ScenarioInvalidTransition,
)
from frontend.server.scenario_evaluation.models import (
    BadcaseStatus,
    BadcaseVersion,
    CandidateArtifact,
    EvaluationDependencies,
    EvaluationPolicyVersion,
    EvaluationRequirement,
    EvaluationRunStatus,
    EvaluationRunVersion,
    PolicySceneBinding,
    PublishIntentStatus,
    PublishPath,
    PublishedVersion,
    QualityRecommendation,
    QualityRecommendationValue,
    ScenarioActor,
    ScenarioRecord,
    ScenarioRecordType,
)
from frontend.server.scenario_evaluation.publishing import PublishCandidateService
from frontend.server.scenario_evaluation.recommendation import dependency_fingerprint
from frontend.server.scenario_evaluation.repository import (
    InMemoryScenarioEvaluationRepository,
)
from frontend.server.scenario_evaluation.service import ScenarioEvaluationService
from veadk.cli.studio_rbac import StudioRole


class _Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 14, 12, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


class _Ids:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}-{self.value}"


def _actor(
    owner: str = "developer-1",
    role: StudioRole = StudioRole.DEVELOPER,
) -> ScenarioActor:
    return ScenarioActor(
        owner_id=owner,
        display_name=owner,
        role=role,
        identifiers=(owner,),
    )


async def _append_model(
    repository: InMemoryScenarioEvaluationRepository,
    model,
    *,
    record_id: str,
    record_type: ScenarioRecordType,
    asset_id: str,
    version: int,
) -> None:
    await repository.append(
        ScenarioRecord(
            record_id=record_id,
            agent_id="agent-1",
            owner_id="system",
            record_type=record_type,
            asset_id=asset_id,
            version=version,
            created_at=datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
            payload_json=model.model_dump_json(by_alias=True),
        )
    )


async def _setup() -> tuple[
    InMemoryScenarioEvaluationRepository,
    ScenarioEvaluationService,
    PublishCandidateService,
    _Clock,
    str,
    str,
]:
    repository = InMemoryScenarioEvaluationRepository()
    clock = _Clock()
    ids = _Ids()
    assets = ScenarioEvaluationService(repository, clock=clock, id_factory=ids)
    publisher = PublishCandidateService(
        repository,
        assets,
        clock=clock,
        id_factory=ids,
        confirmation_ttl=timedelta(minutes=10),
    )
    candidate = await assets.create_candidate_version(
        _actor(),
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:candidate",
            topology_digest="sha256:topology",
        ),
    )
    policy = EvaluationPolicyVersion(
        policy_version_id="policy:v1",
        policy_id="policy",
        agent_id="agent-1",
        version=1,
        source_draft_revision=1,
        name="发布质量检查",
        bindings=(
            PolicySceneBinding(
                scene_version_id="scene:v1",
                dataset_version_id="dataset:v1",
                evaluator_version_ids=("evaluator:v1",),
                requirement=EvaluationRequirement.MUST_PASS,
            ),
        ),
        created_at=clock(),
        created_by="admin-1",
    )
    await _append_model(
        repository,
        policy,
        record_id=policy.policy_version_id,
        record_type=ScenarioRecordType.POLICY_VERSION,
        asset_id=policy.policy_id,
        version=1,
    )
    return (
        repository,
        assets,
        publisher,
        clock,
        candidate.candidate_id,
        policy.policy_version_id,
    )


def _dependencies(
    candidate_id: str,
    *,
    environment: str = "sha256:runtime",
) -> EvaluationDependencies:
    return EvaluationDependencies(
        candidate_id=candidate_id,
        baseline_version_id=None,
        scene_version_ids=("scene:v1",),
        dataset_version_ids=("dataset:v1",),
        evaluator_version_ids=("evaluator:v1",),
        policy_version_id="policy:v1",
        environment_fingerprint=environment,
    )


async def _seed_run(
    repository: InMemoryScenarioEvaluationRepository,
    candidate_id: str,
    *,
    status: EvaluationRunStatus,
    recommendation_value: QualityRecommendationValue | None = None,
    environment: str = "sha256:runtime",
    evaluation_id: str = "evaluation-1",
) -> EvaluationRunVersion:
    dependencies = _dependencies(candidate_id, environment=environment)
    recommendation = (
        QualityRecommendation(
            value=recommendation_value,
            dependency_fingerprint=dependency_fingerprint(dependencies),
            required_scene_results=(),
            observation_scene_results=(),
            warning_scene_version_ids=(),
        )
        if recommendation_value is not None
        else None
    )
    run = EvaluationRunVersion(
        evaluation_id=evaluation_id,
        agent_id="agent-1",
        revision=1,
        status=status,
        candidate_id=candidate_id,
        policy_version_id="policy:v1",
        dependencies=dependencies,
        recommendation=recommendation,
        created_at=datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        created_by="developer-1",
    )
    await _append_model(
        repository,
        run,
        record_id=f"{evaluation_id}:1",
        record_type=ScenarioRecordType.EVALUATION_RUN,
        asset_id=evaluation_id,
        version=1,
    )
    return run


@pytest.mark.asyncio
async def test_unevaluated_and_stale_candidates_require_confirmed_skip_reason() -> None:
    repository, _, publisher, _, candidate_id, policy_id = await _setup()

    with pytest.raises(ScenarioInvalidTransition):
        await publisher.prepare(
            _actor(),
            agent_id="agent-1",
            candidate_id=candidate_id,
            policy_version_id=policy_id,
            environment_fingerprint="sha256:runtime",
            permission_fingerprint="permission:v1",
            second_confirmation=False,
            reason="",
            idempotency_key="prepare-1",
        )
    unevaluated = await publisher.prepare(
        _actor(),
        agent_id="agent-1",
        candidate_id=candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
        permission_fingerprint="permission:v1",
        second_confirmation=True,
        reason="紧急修复，暂未执行评测",
        idempotency_key="prepare-2",
    )

    assert unevaluated.path is PublishPath.SKIP
    assert unevaluated.reason == "紧急修复，暂未执行评测"

    await _seed_run(
        repository,
        candidate_id,
        status=EvaluationRunStatus.SUCCEEDED,
        recommendation_value=QualityRecommendationValue.RECOMMEND,
        environment="sha256:old-runtime",
    )
    stale = await publisher.prepare(
        _actor(),
        agent_id="agent-1",
        candidate_id=candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
        permission_fingerprint="permission:v1",
        second_confirmation=True,
        reason="环境已变化，接受失效风险",
        idempotency_key="prepare-3",
    )
    assert stale.path is PublishPath.SKIP
    assert stale.quality_state == "stale"


@pytest.mark.asyncio
async def test_publish_recovery_surfaces_and_finalizes_a_persisted_runtime_success() -> (
    None
):
    repository, assets, publisher, clock, candidate_id, policy_id = await _setup()
    intent = await publisher.prepare(
        _actor(),
        agent_id="agent-1",
        candidate_id=candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
        permission_fingerprint="permission:v1",
        second_confirmation=True,
        reason="本次跳过评测",
        idempotency_key="recover-1",
    )
    started = await publisher.record_started(
        _actor(),
        agent_id="agent-1",
        intent_id=intent.intent_id,
        permission_fingerprint="permission:v1",
    )
    candidate = await assets.get_candidate_version(
        agent_id="agent-1",
        candidate_id=candidate_id,
    )
    published = PublishedVersion(
        published_version_id="published-v1",
        agent_id="agent-1",
        version=1,
        candidate_id=candidate_id,
        candidate_artifact=candidate.artifact,
        publish_intent_id=intent.intent_id,
        publish_path=intent.path,
        deployment_ref="runtime-1",
        created_at=clock(),
        created_by="developer-1",
    )
    await _append_model(
        repository,
        published,
        record_id=published.published_version_id,
        record_type=ScenarioRecordType.PUBLISHED_VERSION,
        asset_id="online",
        version=1,
    )

    issues = await publisher.list_recovery_issues(agent_id="agent-1")
    assert issues[0].intent == started
    assert issues[0].issue_type == "published_intent_not_finalized"

    recovered, recovered_published = await publisher.finalize_succeeded(
        _actor(),
        agent_id="agent-1",
        intent_id=intent.intent_id,
        deployment_ref="runtime-1",
    )
    assert recovered.status is PublishIntentStatus.SUCCEEDED
    assert recovered_published == published
    assert await publisher.list_recovery_issues(agent_id="agent-1") == ()


@pytest.mark.asyncio
async def test_valid_recommendation_uses_normal_path_without_risk_reason() -> None:
    repository, _, publisher, _, candidate_id, policy_id = await _setup()
    await _seed_run(
        repository,
        candidate_id,
        status=EvaluationRunStatus.SUCCEEDED,
        recommendation_value=QualityRecommendationValue.RECOMMEND,
    )

    intent = await publisher.prepare(
        _actor(),
        agent_id="agent-1",
        candidate_id=candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
        permission_fingerprint="permission:v1",
        second_confirmation=False,
        reason="",
        idempotency_key="prepare-normal",
    )

    assert intent.path is PublishPath.NORMAL
    assert intent.reason == ""


@pytest.mark.parametrize(
    "value",
    [
        QualityRecommendationValue.DO_NOT_RECOMMEND,
        QualityRecommendationValue.INDETERMINATE,
    ],
)
@pytest.mark.asyncio
async def test_negative_or_indeterminate_recommendation_requires_risk_publish(
    value: QualityRecommendationValue,
) -> None:
    repository, _, publisher, _, candidate_id, policy_id = await _setup()
    await _seed_run(
        repository,
        candidate_id,
        status=EvaluationRunStatus.SUCCEEDED,
        recommendation_value=value,
    )

    intent = await publisher.prepare(
        _actor(),
        agent_id="agent-1",
        candidate_id=candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
        permission_fingerprint="permission:v1",
        second_confirmation=True,
        reason="业务负责人接受当前质量风险",
        idempotency_key=f"prepare-{value.value}",
    )

    assert intent.path is PublishPath.RISK
    assert intent.risk_items


@pytest.mark.asyncio
async def test_running_evaluation_must_finish_or_cancel_before_prepare() -> None:
    repository, _, publisher, _, candidate_id, policy_id = await _setup()
    await _seed_run(
        repository,
        candidate_id,
        status=EvaluationRunStatus.RUNNING,
    )

    with pytest.raises(ScenarioEvaluationRunning):
        await publisher.prepare(
            _actor(),
            agent_id="agent-1",
            candidate_id=candidate_id,
            policy_version_id=policy_id,
            environment_fingerprint="sha256:runtime",
            permission_fingerprint="permission:v1",
            second_confirmation=True,
            reason="先发布",
            idempotency_key="prepare-running",
        )


@pytest.mark.asyncio
async def test_intent_binds_actor_permission_quality_and_expiry() -> None:
    repository, _, publisher, clock, candidate_id, policy_id = await _setup()
    await _seed_run(
        repository,
        candidate_id,
        status=EvaluationRunStatus.SUCCEEDED,
        recommendation_value=QualityRecommendationValue.RECOMMEND,
    )
    intent = await publisher.prepare(
        _actor(),
        agent_id="agent-1",
        candidate_id=candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
        permission_fingerprint="permission:v1",
        second_confirmation=False,
        reason="",
        idempotency_key="prepare-bound",
    )

    with pytest.raises(ScenarioInvalidTransition):
        await publisher.record_started(
            _actor("developer-2"),
            agent_id="agent-1",
            intent_id=intent.intent_id,
            permission_fingerprint="permission:v1",
        )
    with pytest.raises(ScenarioInvalidTransition):
        await publisher.record_started(
            _actor(role=StudioRole.ADMIN),
            agent_id="agent-1",
            intent_id=intent.intent_id,
        )
    clock.value += timedelta(minutes=11)
    with pytest.raises(ScenarioInvalidTransition):
        await publisher.record_started(
            _actor(),
            agent_id="agent-1",
            intent_id=intent.intent_id,
            permission_fingerprint="permission:v1",
        )


@pytest.mark.asyncio
async def test_failed_deploy_retries_idempotently_and_success_sets_baseline_once() -> (
    None
):
    repository, _, publisher, _, candidate_id, policy_id = await _setup()
    await _seed_run(
        repository,
        candidate_id,
        status=EvaluationRunStatus.SUCCEEDED,
        recommendation_value=QualityRecommendationValue.DO_NOT_RECOMMEND,
    )
    badcase = BadcaseVersion(
        badcase_id="badcase-1",
        agent_id="agent-1",
        revision=1,
        status=BadcaseStatus.OPEN,
        scene_version_id="scene:v1",
        case_id="case-1",
        dataset_version_id="dataset:v1",
        evaluator_version_ids=("evaluator:v1",),
        source_evaluation_id="evaluation-1",
        source_candidate_id=candidate_id,
        created_at=datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
    )
    await _append_model(
        repository,
        badcase,
        record_id="badcase-1:1",
        record_type=ScenarioRecordType.BADCASE,
        asset_id="badcase-1",
        version=1,
    )
    intent = await publisher.prepare(
        _actor(),
        agent_id="agent-1",
        candidate_id=candidate_id,
        policy_version_id=policy_id,
        environment_fingerprint="sha256:runtime",
        permission_fingerprint="permission:v1",
        second_confirmation=True,
        reason="接受当前失败 Case 风险",
        idempotency_key="prepare-risk",
    )
    started = await publisher.record_started(
        _actor(),
        agent_id="agent-1",
        intent_id=intent.intent_id,
        permission_fingerprint="permission:v1",
    )
    failed = await publisher.record_failed(
        _actor(),
        agent_id="agent-1",
        intent_id=intent.intent_id,
        deployment_ref="deploy-1",
        error_message="runtime update failed",
    )
    restarted = await publisher.record_started(
        _actor(),
        agent_id="agent-1",
        intent_id=intent.intent_id,
        permission_fingerprint="permission:v1",
    )
    completed, published = await publisher.finalize_succeeded(
        _actor(),
        agent_id="agent-1",
        intent_id=intent.intent_id,
        deployment_ref="deploy-2",
    )
    repeated, repeated_published = await publisher.finalize_succeeded(
        _actor(),
        agent_id="agent-1",
        intent_id=intent.intent_id,
        deployment_ref="deploy-2",
    )

    assert started.status is PublishIntentStatus.STARTED
    assert failed.status is PublishIntentStatus.FAILED
    assert restarted.status is PublishIntentStatus.STARTED
    assert completed.status is PublishIntentStatus.SUCCEEDED
    assert repeated == completed
    assert repeated_published == published
    assert published.candidate_id == candidate_id
    assert await publisher.latest_published(agent_id="agent-1") == published
    audits = await publisher.list_audits(agent_id="agent-1", intent_id=intent.intent_id)
    assert [item.event.value for item in audits] == [
        "prepared",
        "started",
        "failed",
        "started",
        "succeeded",
    ]
    badcase_records = await repository.list(
        agent_id="agent-1",
        record_type=ScenarioRecordType.BADCASE,
    )
    assert len(badcase_records) == 1
