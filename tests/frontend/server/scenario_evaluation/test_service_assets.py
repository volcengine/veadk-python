from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from frontend.server.scenario_evaluation.evaluators import ControlledEvidenceEvaluator
from frontend.server.scenario_evaluation.errors import (
    ScenarioForbidden,
    ScenarioInvalidTransition,
)
from frontend.server.scenario_evaluation.models import (
    CandidateArtifact,
    CandidateProjectFile,
    CandidateProjectSource,
    CredentialReference,
    DatasetCase,
    DatasetCaseSource,
    AttemptOutcome,
    EvaluationRequirement,
    EvaluatorKind,
    EvaluatorTrialSample,
    FeedbackDecision,
    FeedbackSource,
    RedactionStatus,
    PolicySceneBinding,
    ScenarioActor,
    ScenarioRecord,
    ScenarioRecordType,
)
from frontend.server.scenario_evaluation.repository import (
    InMemoryScenarioEvaluationRepository,
)
from frontend.server.scenario_evaluation.service import ScenarioEvaluationService
from veadk.cli.studio_rbac import StudioRole


class _Ids:
    def __init__(self) -> None:
        self._value = 0

    def __call__(self, prefix: str) -> str:
        self._value += 1
        return f"{prefix}-{self._value}"


def _service() -> ScenarioEvaluationService:
    async def trust_agent_identity(*_args: object) -> None:
        return None

    return ScenarioEvaluationService(
        InMemoryScenarioEvaluationRepository(),
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        id_factory=_Ids(),
        project_attestation_verifier=lambda _project, _owner, _proof: None,
        agent_identity_verifier=trust_agent_identity,
    )


def _actor(role: StudioRole, owner_id: str) -> ScenarioActor:
    return ScenarioActor(
        owner_id=owner_id,
        display_name=owner_id,
        role=role,
        identifiers=(owner_id.casefold(),),
    )


def _source(*, user_id: str = "end-user") -> FeedbackSource:
    return FeedbackSource(
        agent_id="agent-1",
        agent_version="published-v3",
        runtime_id="runtime-1",
        app_name="support-agent",
        user_id=user_id,
        session_id="session-1",
        message_id="message-1",
        invocation_id="invocation-1",
        run_id="invocation-1",
        trace_ref="trace:runtime-1/session-1/invocation-1",
        input="我的订单为什么还没到？",
        output="订单将在今天送达。",
        rating="bad",
        comment="实际物流还没出库",
    )


async def _publish_scene(
    service: ScenarioEvaluationService,
    *,
    scene_id: str = "scene-logistics",
):
    draft = await service.save_scene_draft(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        scene_id=scene_id,
        expected_revision=0,
        name="物流查询",
        description="根据真实物流状态回答",
        user_task="查询订单物流",
        pass_criteria=("回答包含真实物流状态",),
        hard_failure_conditions=("不得编造物流状态",),
        owner_id="logistics-owner",
        requirement=EvaluationRequirement.MUST_PASS,
    )
    return await service.publish_scene_version(
        _actor(StudioRole.ADMIN, "admin-1"),
        agent_id="agent-1",
        scene_id=scene_id,
        draft_revision=draft.revision,
    )


@pytest.mark.asyncio
async def test_end_user_feedback_creates_owned_immutable_candidate() -> None:
    service = _service()
    actor = _actor(StudioRole.USER, "end-user")

    candidate = await service.create_feedback_candidate(actor, _source())

    assert candidate.revision == 1
    assert candidate.source.user_id == "end-user"
    assert candidate.decision is FeedbackDecision.PENDING
    assert candidate.created_by == "end-user"


@pytest.mark.asyncio
async def test_retried_identical_feedback_returns_the_same_candidate() -> None:
    service = _service()
    actor = _actor(StudioRole.USER, "end-user")

    first = await service.create_feedback_candidate(actor, _source())
    retried = await service.create_feedback_candidate(actor, _source())

    assert retried == first


@pytest.mark.asyncio
async def test_end_user_cannot_submit_feedback_for_someone_else() -> None:
    service = _service()

    with pytest.raises(ScenarioForbidden):
        await service.create_feedback_candidate(
            _actor(StudioRole.USER, "end-user"),
            _source(user_id="other-user"),
        )


@pytest.mark.asyncio
async def test_developer_reviews_and_redacts_without_mutating_source_evidence() -> None:
    service = _service()
    created = await service.create_feedback_candidate(
        _actor(StudioRole.USER, "end-user"),
        _source(),
    )

    reviewed = await service.review_feedback_candidate(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        candidate_id=created.candidate_id,
        expected_revision=1,
        input="订单为什么还没到？",
        expected_output="先查询物流状态，再回答预计送达时间。",
        comment="已删除订单标识并补充预期行为",
        labels=("物流", "事实性"),
    )

    assert reviewed.revision == 2
    assert reviewed.decision is FeedbackDecision.REVIEWED
    assert reviewed.source == created.source
    assert reviewed.reviewed_input == "订单为什么还没到？"
    assert reviewed.labels == ("物流", "事实性")


@pytest.mark.asyncio
async def test_developer_can_reject_or_merge_feedback_with_traceability() -> None:
    service = _service()
    developer = _actor(StudioRole.DEVELOPER, "developer-1")
    rejected_source = await service.create_feedback_candidate(
        _actor(StudioRole.USER, "end-user"), _source()
    )
    merge_source = await service.create_feedback_candidate(
        _actor(StudioRole.USER, "end-user"),
        _source().model_copy(update={"message_id": "message-2"}),
    )

    rejected = await service.reject_feedback_candidate(
        developer,
        agent_id="agent-1",
        candidate_id=rejected_source.candidate_id,
        expected_revision=1,
        reason="无法复现",
    )
    merged = await service.merge_feedback_candidate(
        developer,
        agent_id="agent-1",
        candidate_id=merge_source.candidate_id,
        expected_revision=1,
        target_candidate_id=rejected_source.candidate_id,
        reason="同一问题的重复反馈",
    )

    assert rejected.decision is FeedbackDecision.REJECTED
    assert rejected.decision_reason == "无法复现"
    assert merged.decision is FeedbackDecision.MERGED
    assert merged.target_candidate_id == rejected_source.candidate_id


@pytest.mark.asyncio
async def test_reviewed_feedback_converts_to_dataset_case_with_source_lineage() -> None:
    service = _service()
    scene = await _publish_scene(service)
    developer = _actor(StudioRole.DEVELOPER, "developer-1")
    created = await service.create_feedback_candidate(
        _actor(StudioRole.USER, "end-user"), _source()
    )
    reviewed = await service.review_feedback_candidate(
        developer,
        agent_id="agent-1",
        candidate_id=created.candidate_id,
        expected_revision=1,
        input="订单为什么还没到？",
        expected_output="先查询物流状态，再回答预计送达时间。",
        comment="已脱敏",
        labels=("物流",),
    )

    converted, dataset = await service.convert_feedback_candidate(
        developer,
        agent_id="agent-1",
        candidate_id=created.candidate_id,
        expected_revision=reviewed.revision,
        dataset_id="dataset-logistics",
        expected_dataset_revision=0,
        dataset_name="物流问答",
        scene_version_id=scene.scene_version_id,
        pass_criteria=scene.pass_criteria,
    )

    assert converted.decision is FeedbackDecision.CONVERTED
    assert converted.target_dataset_id == "dataset-logistics"
    assert dataset.revision == 1
    assert dataset.cases[0].source_feedback_candidate_ids == (created.candidate_id,)
    assert dataset.cases[0].input == reviewed.reviewed_input


@pytest.mark.asyncio
async def test_tc_02_merged_feedback_keeps_all_sources_and_requires_redaction() -> None:
    service = _service()
    scene = await _publish_scene(service)
    developer = _actor(StudioRole.DEVELOPER, "developer-1")
    target = await service.create_feedback_candidate(
        _actor(StudioRole.USER, "end-user"), _source()
    )
    duplicate = await service.create_feedback_candidate(
        _actor(StudioRole.USER, "end-user"),
        _source().model_copy(update={"message_id": "message-duplicate"}),
    )
    reviewed = await service.review_feedback_candidate(
        developer,
        agent_id="agent-1",
        candidate_id=target.candidate_id,
        expected_revision=1,
        input="订单为什么还没到？",
        expected_output="先查询物流状态。",
        comment="等待脱敏确认",
        labels=("物流",),
    )
    await service.merge_feedback_candidate(
        developer,
        agent_id="agent-1",
        candidate_id=duplicate.candidate_id,
        expected_revision=1,
        target_candidate_id=target.candidate_id,
        reason="同一问题",
    )

    _, dataset = await service.convert_feedback_candidate(
        developer,
        agent_id="agent-1",
        candidate_id=target.candidate_id,
        expected_revision=reviewed.revision,
        dataset_id="dataset-1",
        expected_dataset_revision=0,
        dataset_name="物流回归",
        scene_version_id=scene.scene_version_id,
        pass_criteria=scene.pass_criteria,
        redaction_status=RedactionStatus.PENDING,
    )

    assert set(dataset.cases[0].source_feedback_candidate_ids) == {
        target.candidate_id,
        duplicate.candidate_id,
    }
    with pytest.raises(ScenarioInvalidTransition, match="redaction"):
        await service.publish_dataset_version(
            _actor(StudioRole.ADMIN, "admin-1"),
            agent_id="agent-1",
            dataset_id=dataset.dataset_id,
            draft_revision=dataset.revision,
        )


@pytest.mark.asyncio
async def test_developer_edits_drafts_but_only_admin_publishes_versions() -> None:
    service = _service()
    developer = _actor(StudioRole.DEVELOPER, "developer-1")
    admin = _actor(StudioRole.ADMIN, "admin-1")

    scene_draft = await service.save_scene_draft(
        developer,
        agent_id="agent-1",
        scene_id="scene-logistics",
        expected_revision=0,
        name="物流查询",
        description="回答前先查询物流状态",
        user_task="查询订单物流并解释预计送达时间",
        pass_criteria=("先查询物流工具", "回答与查询结果一致"),
        hard_failure_conditions=("不得编造物流状态",),
        owner_id="logistics-owner",
        requirement=EvaluationRequirement.MUST_PASS,
    )
    with pytest.raises(ScenarioForbidden):
        await service.publish_scene_version(
            developer,
            agent_id="agent-1",
            scene_id="scene-logistics",
            draft_revision=scene_draft.revision,
        )

    published = await service.publish_scene_version(
        admin,
        agent_id="agent-1",
        scene_id="scene-logistics",
        draft_revision=scene_draft.revision,
    )

    assert published.version == 1
    assert published.source_draft_revision == scene_draft.revision
    assert published.user_task == "查询订单物流并解释预计送达时间"
    assert published.pass_criteria == ("先查询物流工具", "回答与查询结果一致")
    assert published.hard_failure_conditions == ("不得编造物流状态",)
    assert published.owner_id == "logistics-owner"
    with pytest.raises(ValidationError):
        published.name = "被改写"


@pytest.mark.asyncio
async def test_scene_publish_rejects_incomplete_structured_standard() -> None:
    service = _service()
    draft = await service.save_scene_draft(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        scene_id="scene-incomplete",
        expected_revision=0,
        name="不完整场景",
        description="只有说明，没有正式判定口径",
        user_task="",
        pass_criteria=(),
        hard_failure_conditions=(),
        owner_id="",
        requirement=EvaluationRequirement.MUST_PASS,
    )

    with pytest.raises(ScenarioInvalidTransition, match="user task"):
        await service.publish_scene_version(
            _actor(StudioRole.ADMIN, "admin-1"),
            agent_id="agent-1",
            scene_id=draft.scene_id,
            draft_revision=draft.revision,
        )


@pytest.mark.asyncio
async def test_dataset_publish_requires_scene_source_criteria_and_redaction() -> None:
    service = _service()
    developer = _actor(StudioRole.DEVELOPER, "developer-1")
    admin = _actor(StudioRole.ADMIN, "admin-1")
    scene_draft = await service.save_scene_draft(
        developer,
        agent_id="agent-1",
        scene_id="scene-logistics",
        expected_revision=0,
        name="物流查询",
        description="根据真实物流状态回答",
        user_task="查询订单物流",
        pass_criteria=("回答包含真实物流状态",),
        hard_failure_conditions=("不得编造物流状态",),
        owner_id="logistics-owner",
        requirement=EvaluationRequirement.MUST_PASS,
    )
    scene = await service.publish_scene_version(
        admin,
        agent_id="agent-1",
        scene_id=scene_draft.scene_id,
        draft_revision=scene_draft.revision,
    )
    draft = await service.save_dataset_draft(
        developer,
        agent_id="agent-1",
        dataset_id="dataset-incomplete",
        expected_revision=0,
        name="待补齐数据集",
        cases=(
            DatasetCase(
                case_id="case-1",
                scene_version_id=scene.scene_version_id,
                input="订单到哪了？",
                expected_output="订单已出库",
                pass_criteria=("包含真实物流状态",),
                source_type=DatasetCaseSource.FILE,
                source_refs=(),
                redaction_status=RedactionStatus.REDACTED,
            ),
        ),
    )

    with pytest.raises(ScenarioInvalidTransition, match="source"):
        await service.publish_dataset_version(
            admin,
            agent_id="agent-1",
            dataset_id=draft.dataset_id,
            draft_revision=draft.revision,
        )


@pytest.mark.asyncio
async def test_admin_publishes_dataset_evaluator_and_complete_policy() -> None:
    service = _service()
    developer = _actor(StudioRole.DEVELOPER, "developer-1")
    admin = _actor(StudioRole.ADMIN, "admin-1")
    scene = await _publish_scene(service)

    dataset_draft = await service.save_dataset_draft(
        developer,
        agent_id="agent-1",
        dataset_id="dataset-logistics",
        expected_revision=0,
        name="物流问答",
        cases=(
            DatasetCase(
                case_id="case-logistics-1",
                scene_version_id=scene.scene_version_id,
                input="订单为什么还没到？",
                expected_output="先查询物流状态，再回答预计送达时间。",
                pass_criteria=scene.pass_criteria,
                labels=("物流",),
                source_refs=("manual:case-logistics-1",),
            ),
        ),
    )
    dataset = await service.publish_dataset_version(
        admin,
        agent_id="agent-1",
        dataset_id=dataset_draft.dataset_id,
        draft_revision=dataset_draft.revision,
    )
    evaluator_draft = await service.save_evaluator_draft(
        developer,
        agent_id="agent-1",
        evaluator_id="evaluator-grounding",
        expected_revision=0,
        name="事实依据检查",
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
                sample_id="case-logistics-1",
                input="订单为什么还没到？",
                expected_output="先查询物流状态，再回答预计送达时间。",
                agent_output="先查询物流状态，再回答预计送达时间。",
                expected_outcome=AttemptOutcome.PASS,
                trace_json='[{"type":"tool_call"}]',
            ),
        ),
        evaluator=ControlledEvidenceEvaluator(),
    )
    evaluator = await service.publish_evaluator_version(
        admin,
        agent_id="agent-1",
        evaluator_id=evaluator_draft.evaluator_id,
        draft_revision=evaluator_draft.revision,
    )
    policy_draft = await service.save_policy_draft(
        developer,
        agent_id="agent-1",
        policy_id="policy-release",
        expected_revision=0,
        name="发布质量检查",
        bindings=(
            PolicySceneBinding(
                scene_version_id=scene.scene_version_id,
                dataset_version_id=dataset.dataset_version_id,
                evaluator_version_ids=(evaluator.evaluator_version_id,),
                requirement=EvaluationRequirement.MUST_PASS,
            ),
        ),
    )
    policy = await service.publish_policy_version(
        admin,
        agent_id="agent-1",
        policy_id=policy_draft.policy_id,
        draft_revision=policy_draft.revision,
    )

    assert policy.bindings == policy_draft.bindings
    assert policy.version == 1


@pytest.mark.asyncio
async def test_policy_publish_rejects_omitting_an_enabled_scene() -> None:
    service = _service()
    developer = _actor(StudioRole.DEVELOPER, "developer-1")
    admin = _actor(StudioRole.ADMIN, "admin-1")
    first = await _publish_scene(service, scene_id="scene-1")
    await _publish_scene(service, scene_id="scene-2")
    draft = await service.save_policy_draft(
        developer,
        agent_id="agent-1",
        policy_id="policy-incomplete",
        expected_revision=0,
        name="遗漏场景的方案",
        bindings=(
            PolicySceneBinding(
                scene_version_id=first.scene_version_id,
                dataset_version_id="dataset-placeholder:v1",
                evaluator_version_ids=("evaluator-placeholder:v1",),
                requirement=EvaluationRequirement.MUST_PASS,
            ),
        ),
    )

    with pytest.raises(ScenarioInvalidTransition, match="every enabled latest Scene"):
        await service.publish_policy_version(
            admin,
            agent_id="agent-1",
            policy_id=draft.policy_id,
            draft_revision=draft.revision,
        )


def test_policy_rejects_missing_must_pass_scene_or_evaluator_binding() -> None:
    with pytest.raises(ValidationError):
        PolicySceneBinding(
            scene_version_id="scene:v1",
            dataset_version_id="dataset:v1",
            evaluator_version_ids=(),
            requirement=EvaluationRequirement.MUST_PASS,
        )


@pytest.mark.asyncio
async def test_candidate_snapshot_is_created_by_managers_and_keeps_only_secret_refs() -> (
    None
):
    service = _service()
    artifact = CandidateArtifact(
        code_digest="sha256:code",
        topology_digest="sha256:topology",
        environment_refs=(
            CredentialReference(name="MODEL_API_KEY", reference="secret://model-key"),
        ),
    )

    candidate = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        artifact=artifact,
    )
    next_candidate = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        artifact=artifact.model_copy(update={"code_digest": "sha256:code-v2"}),
    )

    assert candidate.version == 1
    assert next_candidate.version == 2
    assert candidate.artifact.environment_refs[0].reference == "secret://model-key"
    with pytest.raises(ScenarioForbidden):
        await service.create_candidate_version(
            _actor(StudioRole.USER, "end-user"),
            agent_id="agent-1",
            artifact=artifact,
        )


@pytest.mark.asyncio
async def test_candidate_stores_immutable_runtime_project_behind_server_reference() -> (
    None
):
    service = _service()
    project = CandidateProjectSource(
        name="demo_agent",
        files=(
            CandidateProjectFile(
                path="agents/demo_agent/agent.py",
                content="root_agent = object()\n",
            ),
        ),
        deployment_profile={"region": "cn-beijing"},
        attestation="trusted-test-project",
    )

    candidate = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:code",
            topology_digest="sha256:topology",
        ),
        runtime_project=project,
    )
    stored = await service.get_candidate_runtime_project(
        agent_id="agent-1",
        project_snapshot_id=candidate.artifact.runtime_project_ref or "",
    )

    assert candidate.artifact.runtime_project_ref == (
        f"{candidate.candidate_id}:runtime-project"
    )
    assert stored.candidate_id == candidate.candidate_id
    assert stored.name == "demo_agent"
    assert stored.files == project.files
    assert stored.deployment_profile == project.deployment_profile
    assert stored.created_by == "developer-1"
    assert candidate.environment_fingerprint.startswith("sha256:")


@pytest.mark.asyncio
async def test_candidate_source_index_is_isolated_by_owner() -> None:
    service = _service()
    project = CandidateProjectSource(
        name="demo_agent",
        files=(
            CandidateProjectFile(
                path="agents/demo_agent/agent.py",
                content="root_agent = object()\n",
            ),
        ),
        deployment_profile={"region": "cn-beijing"},
        attestation="trusted-test-project",
    )

    first = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        artifact=CandidateArtifact(
            code_digest="sha256:code",
            topology_digest="sha256:topology",
        ),
        runtime_project=project,
    )
    second = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-2"),
        agent_id="agent-2",
        artifact=CandidateArtifact(
            code_digest="sha256:code",
            topology_digest="sha256:topology",
        ),
        runtime_project=project,
    )

    assert first.agent_id == "agent-1"
    assert second.agent_id == "agent-2"


@pytest.mark.asyncio
async def test_candidate_transaction_includes_the_frozen_deployment_profile() -> None:
    service = _service()
    project = CandidateProjectSource(
        name="demo_agent",
        files=(
            CandidateProjectFile(
                path="agents/demo_agent/agent.py",
                content="root_agent = object()\n",
            ),
        ),
        deployment_profile={"region": "cn-beijing", "network": "public"},
        attestation="trusted-test-project",
    )
    artifact = CandidateArtifact(
        code_digest="sha256:code",
        topology_digest="sha256:topology",
    )

    first = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        artifact=artifact,
        runtime_project=project,
    )
    second = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        artifact=artifact,
        runtime_project=project.model_copy(
            update={
                "deployment_profile": {
                    "region": "cn-shanghai",
                    "network": "private",
                }
            }
        ),
    )
    repeated = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-1",
        artifact=artifact,
        runtime_project=project.model_copy(
            update={
                "deployment_profile": {
                    "region": "cn-shanghai",
                    "network": "private",
                }
            }
        ),
    )
    renamed = await service.create_candidate_version(
        _actor(StudioRole.DEVELOPER, "developer-1"),
        agent_id="agent-2",
        artifact=artifact,
        runtime_project=project,
    )

    assert second.candidate_id != first.candidate_id
    assert second.version == 2
    assert second.environment_fingerprint != first.environment_fingerprint
    assert repeated == second
    assert renamed.agent_id == "agent-2"


@pytest.mark.asyncio
async def test_candidate_source_transaction_recovers_after_partial_materialization() -> (
    None
):
    class FailCandidateOnceRepository(InMemoryScenarioEvaluationRepository):
        failed = False

        async def append(self, record: ScenarioRecord) -> None:
            if (
                record.record_type is ScenarioRecordType.CANDIDATE_VERSION
                and not self.failed
            ):
                self.failed = True
                raise RuntimeError("candidate write interrupted")
            await super().append(record)

    repository = FailCandidateOnceRepository()

    async def trust_agent_identity(*_args: object) -> None:
        return None

    service = ScenarioEvaluationService(
        repository,
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        id_factory=_Ids(),
        project_attestation_verifier=lambda _project, _owner, _proof: None,
        agent_identity_verifier=trust_agent_identity,
    )
    project = CandidateProjectSource(
        name="demo_agent",
        files=(
            CandidateProjectFile(
                path="agents/demo_agent/agent.py",
                content="root_agent = object()\n",
            ),
        ),
        deployment_profile={"region": "cn-beijing"},
        attestation="trusted-test-project",
    )
    kwargs = {
        "actor": _actor(StudioRole.DEVELOPER, "developer-1"),
        "agent_id": "agent-1",
        "artifact": CandidateArtifact(
            code_digest="sha256:code",
            topology_digest="sha256:topology",
        ),
        "runtime_project": project,
    }

    with pytest.raises(RuntimeError, match="write interrupted"):
        await service.create_candidate_version(**kwargs)
    recovered = await service.create_candidate_version(**kwargs)

    assert recovered.candidate_id == "candidate-1"
    assert (
        await service.get_candidate_version(
            agent_id="agent-1",
            candidate_id=recovered.candidate_id,
        )
        == recovered
    )


@pytest.mark.asyncio
async def test_candidate_rejects_unsafe_runtime_project_before_persistence() -> None:
    service = _service()

    with pytest.raises(ScenarioInvalidTransition, match="Illegal file path"):
        await service.create_candidate_version(
            _actor(StudioRole.DEVELOPER, "developer-1"),
            agent_id="agent-1",
            artifact=CandidateArtifact(
                code_digest="sha256:code",
                topology_digest="sha256:topology",
            ),
            runtime_project=CandidateProjectSource(
                name="demo_agent",
                files=(
                    CandidateProjectFile(
                        path="../secret.py",
                        content="do_not_store = True\n",
                    ),
                ),
                deployment_profile={"region": "cn-beijing"},
            ),
        )


@pytest.mark.asyncio
async def test_candidate_rejects_unattested_browser_runtime_project() -> None:
    service = ScenarioEvaluationService(InMemoryScenarioEvaluationRepository())
    actor = _actor(StudioRole.DEVELOPER, "developer-1")

    with pytest.raises(
        ScenarioInvalidTransition,
        match="trusted server-generated project",
    ):
        await service.create_candidate_version(
            actor,
            agent_id="agent-1",
            artifact=CandidateArtifact(
                code_digest="sha256:code",
                topology_digest="sha256:topology",
            ),
            runtime_project=CandidateProjectSource(
                name="demo_agent",
                files=(
                    CandidateProjectFile(
                        path="agents/demo_agent/agent.py",
                        content="root_agent = object()\n",
                    ),
                ),
                deployment_profile={"region": "cn-beijing"},
            ),
        )


@pytest.mark.asyncio
async def test_candidate_rejects_unverified_agent_identity_claim() -> None:
    service = ScenarioEvaluationService(
        InMemoryScenarioEvaluationRepository(),
        project_attestation_verifier=lambda _project, _owner, _proof: None,
    )

    with pytest.raises(
        ScenarioInvalidTransition,
        match="trusted Agent identity",
    ):
        await service.create_candidate_version(
            _actor(StudioRole.DEVELOPER, "developer-1"),
            agent_id="claimed-agent",
            artifact=CandidateArtifact(
                code_digest="sha256:code",
                topology_digest="sha256:topology",
            ),
            runtime_project=CandidateProjectSource(
                name="demo_agent",
                files=(
                    CandidateProjectFile(
                        path="agents/demo_agent/agent.py",
                        content="root_agent = object()\n",
                    ),
                ),
                deployment_profile={"region": "cn-beijing"},
                attestation="trusted-project",
            ),
        )
