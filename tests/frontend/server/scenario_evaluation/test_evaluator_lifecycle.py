from __future__ import annotations

from datetime import datetime, timezone

import pytest

from frontend.server.scenario_evaluation.evaluators import ControlledEvidenceEvaluator
from frontend.server.scenario_evaluation.errors import ScenarioInvalidTransition
from frontend.server.scenario_evaluation.models import (
    AttemptOutcome,
    DatasetCase,
    EvaluationRequirement,
    EvaluatorKind,
    EvaluatorTrialSample,
    ScenarioActor,
    ScenarioRecordType,
)
from frontend.server.scenario_evaluation.repository import (
    InMemoryScenarioEvaluationRepository,
)
from frontend.server.scenario_evaluation.service import ScenarioEvaluationService
from veadk.cli.studio_rbac import StudioRole


class _Ids:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}-{self.value}"


def _actor(role: StudioRole) -> ScenarioActor:
    return ScenarioActor(
        owner_id=role.value,
        display_name=role.value,
        role=role,
        identifiers=(role.value,),
    )


async def _standards(service: ScenarioEvaluationService):
    developer = _actor(StudioRole.DEVELOPER)
    admin = _actor(StudioRole.ADMIN)
    scene_draft = await service.save_scene_draft(
        developer,
        agent_id="agent-1",
        scene_id="scene-1",
        expected_revision=0,
        name="订单事实查询",
        description="必须基于订单工具的真实状态回答",
        user_task="查询订单状态",
        pass_criteria=("回答与工具结果一致",),
        hard_failure_conditions=("不得编造订单状态",),
        owner_id="order-owner",
        requirement=EvaluationRequirement.MUST_PASS,
    )
    scene = await service.publish_scene_version(
        admin,
        agent_id="agent-1",
        scene_id=scene_draft.scene_id,
        draft_revision=scene_draft.revision,
    )
    dataset_draft = await service.save_dataset_draft(
        developer,
        agent_id="agent-1",
        dataset_id="dataset-1",
        expected_revision=0,
        name="订单事实样本",
        cases=(
            DatasetCase(
                case_id="case-1",
                scene_version_id=scene.scene_version_id,
                input="查询订单",
                expected_output="已发货",
                pass_criteria=scene.pass_criteria,
                source_refs=("manual:case-1",),
            ),
            DatasetCase(
                case_id="case-2",
                scene_version_id=scene.scene_version_id,
                input="查询另一个订单",
                expected_output="已发货",
                pass_criteria=scene.pass_criteria,
                source_refs=("manual:case-2",),
            ),
        ),
    )
    dataset = await service.publish_dataset_version(
        admin,
        agent_id="agent-1",
        dataset_id=dataset_draft.dataset_id,
        draft_revision=dataset_draft.revision,
    )
    return scene, dataset


@pytest.mark.asyncio
async def test_tc_05_scene_recommends_controlled_rule_and_structured_rubric_drafts() -> (
    None
):
    service = ScenarioEvaluationService(
        InMemoryScenarioEvaluationRepository(),
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        id_factory=_Ids(),
    )
    scene = await service.save_scene_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        scene_id="scene-1",
        expected_revision=0,
        name="订单事实查询",
        description="必须先查询订单工具，再按真实状态回答；不得编造物流状态。",
        user_task="查询订单并基于真实状态回答",
        pass_criteria=("必须先查询订单工具", "回答与真实状态一致"),
        hard_failure_conditions=("不得编造物流状态",),
        owner_id="order-owner",
        requirement=EvaluationRequirement.MUST_PASS,
    )
    version = await service.publish_scene_version(
        _actor(StudioRole.ADMIN),
        agent_id="agent-1",
        scene_id=scene.scene_id,
        draft_revision=scene.revision,
    )

    recommendation = await service.recommend_evaluator_drafts(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        scene_version_id=version.scene_version_id,
    )

    assert {item.kind for item in recommendation.drafts} == {
        EvaluatorKind.DETERMINISTIC,
        EvaluatorKind.LLM_RUBRIC,
    }
    assert recommendation.scene_version_id == version.scene_version_id
    assert all(item.rationale for item in recommendation.items)
    assert "任意" not in " ".join(item.rationale for item in recommendation.items)


@pytest.mark.asyncio
async def test_tc_06_draft_trial_separates_business_failure_from_infrastructure_error() -> (
    None
):
    service = ScenarioEvaluationService(
        InMemoryScenarioEvaluationRepository(),
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        id_factory=_Ids(),
    )
    scene, dataset = await _standards(service)
    draft = await service.save_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id="evaluator-1",
        expected_revision=0,
        name="期望内容检查",
        scene_version_id=scene.scene_version_id,
        kind=EvaluatorKind.DETERMINISTIC,
        rule="output_contains_expected",
        rubric="",
        hard_failure=False,
    )

    report = await service.trial_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id=draft.evaluator_id,
        expected_revision=draft.revision,
        dataset_version_id=dataset.dataset_version_id,
        samples=(
            EvaluatorTrialSample(
                sample_id="case-1",
                input="查询订单",
                expected_output="已发货",
                agent_output="订单已发货",
                expected_outcome=AttemptOutcome.PASS,
            ),
            EvaluatorTrialSample(
                sample_id="case-2",
                input="查询另一个订单",
                expected_output="已发货",
                agent_output="订单待付款",
                expected_outcome=AttemptOutcome.FAIL,
            ),
        ),
        evaluator=ControlledEvidenceEvaluator(),
    )

    assert [item.outcome for item in report.results] == [
        AttemptOutcome.PASS,
        AttemptOutcome.FAIL,
    ]
    assert all(not item.error_message for item in report.results)
    assert report.evaluator_revision == draft.revision
    assert report.dataset_version_id == dataset.dataset_version_id
    assert all(item.matches_expectation for item in report.results)


@pytest.mark.asyncio
async def test_evaluator_publish_requires_a_matching_trial_for_the_draft_revision() -> (
    None
):
    service = ScenarioEvaluationService(
        InMemoryScenarioEvaluationRepository(),
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        id_factory=_Ids(),
    )
    scene, dataset = await _standards(service)
    draft = await service.save_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id="evaluator-publish",
        expected_revision=0,
        name="期望内容检查",
        scene_version_id=scene.scene_version_id,
        kind=EvaluatorKind.DETERMINISTIC,
        rule="output_contains_expected",
        rubric="",
        hard_failure=True,
    )

    with pytest.raises(ScenarioInvalidTransition, match="trial"):
        await service.publish_evaluator_version(
            _actor(StudioRole.ADMIN),
            agent_id="agent-1",
            evaluator_id=draft.evaluator_id,
            draft_revision=draft.revision,
        )

    await service.trial_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id=draft.evaluator_id,
        expected_revision=draft.revision,
        dataset_version_id=dataset.dataset_version_id,
        samples=(
            EvaluatorTrialSample(
                sample_id="case-1",
                input="查询订单",
                expected_output="已发货",
                agent_output="订单已发货",
                expected_outcome=AttemptOutcome.PASS,
            ),
        ),
        evaluator=ControlledEvidenceEvaluator(),
    )
    published = await service.publish_evaluator_version(
        _actor(StudioRole.ADMIN),
        agent_id="agent-1",
        evaluator_id=draft.evaluator_id,
        draft_revision=draft.revision,
    )

    assert published.scene_version_id == scene.scene_version_id
    assert published.trial_dataset_version_id == dataset.dataset_version_id


@pytest.mark.asyncio
async def test_evaluator_group_publish_uses_the_combined_judgment() -> None:
    service = ScenarioEvaluationService(
        InMemoryScenarioEvaluationRepository(),
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        id_factory=_Ids(),
    )
    scene, dataset = await _standards(service)
    exclusion_check = await service.save_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id="evaluator-exclusion",
        expected_revision=0,
        name="禁用内容检查",
        scene_version_id=scene.scene_version_id,
        kind=EvaluatorKind.DETERMINISTIC,
        rule="output_excludes_forbidden",
        rubric="",
        hard_failure=True,
    )
    semantic_check = await service.save_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id="evaluator-semantic",
        expected_revision=0,
        name="期望内容检查",
        scene_version_id=scene.scene_version_id,
        kind=EvaluatorKind.DETERMINISTIC,
        rule="output_contains_expected",
        rubric="",
        hard_failure=False,
    )
    sample = EvaluatorTrialSample(
        sample_id="case-1",
        input="查询订单",
        expected_output="已发货",
        agent_output="订单待付款",
        expected_outcome=AttemptOutcome.FAIL,
    )
    for draft in (exclusion_check, semantic_check):
        await service.trial_evaluator_draft(
            _actor(StudioRole.DEVELOPER),
            agent_id="agent-1",
            evaluator_id=draft.evaluator_id,
            expected_revision=draft.revision,
            dataset_version_id=dataset.dataset_version_id,
            samples=(sample,),
            evaluator=ControlledEvidenceEvaluator(),
        )

    published = await service.publish_evaluator_group(
        _actor(StudioRole.ADMIN),
        agent_id="agent-1",
        scene_version_id=scene.scene_version_id,
        draft_revisions={
            exclusion_check.evaluator_id: exclusion_check.revision,
            semantic_check.evaluator_id: semantic_check.revision,
        },
    )

    assert published.scene_version_id == scene.scene_version_id
    assert published.check_count == 2
    assert published.calibration_accurate is True
    assert {item.evaluator_id for item in published.evaluator_versions} == {
        exclusion_check.evaluator_id,
        semantic_check.evaluator_id,
    }


@pytest.mark.asyncio
async def test_evaluator_group_publish_requires_every_current_check_trial() -> None:
    repository = InMemoryScenarioEvaluationRepository()
    service = ScenarioEvaluationService(
        repository,
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        id_factory=_Ids(),
    )
    scene, dataset = await _standards(service)
    first = await service.save_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id="evaluator-first",
        expected_revision=0,
        name="第一项检查",
        scene_version_id=scene.scene_version_id,
        kind=EvaluatorKind.DETERMINISTIC,
        rule="output_contains_expected",
        rubric="",
        hard_failure=False,
    )
    second = await service.save_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id="evaluator-second",
        expected_revision=0,
        name="第二项检查",
        scene_version_id=scene.scene_version_id,
        kind=EvaluatorKind.DETERMINISTIC,
        rule="output_excludes_forbidden",
        rubric="",
        hard_failure=True,
    )
    await service.trial_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id=first.evaluator_id,
        expected_revision=first.revision,
        dataset_version_id=dataset.dataset_version_id,
        samples=(
            EvaluatorTrialSample(
                sample_id="case-1",
                input="查询订单",
                expected_output="已发货",
                agent_output="订单已发货",
                expected_outcome=AttemptOutcome.PASS,
            ),
        ),
        evaluator=ControlledEvidenceEvaluator(),
    )

    with pytest.raises(ScenarioInvalidTransition, match="current trial"):
        await service.publish_evaluator_group(
            _actor(StudioRole.ADMIN),
            agent_id="agent-1",
            scene_version_id=scene.scene_version_id,
            draft_revisions={
                first.evaluator_id: first.revision,
                second.evaluator_id: second.revision,
            },
        )

    versions = await repository.list(
        agent_id="agent-1",
        record_type=ScenarioRecordType.EVALUATOR_VERSION,
    )
    assert versions == ()


@pytest.mark.asyncio
async def test_evaluator_group_publish_rejects_a_combined_mismatch() -> None:
    repository = InMemoryScenarioEvaluationRepository()
    service = ScenarioEvaluationService(
        repository,
        clock=lambda: datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        id_factory=_Ids(),
    )
    scene, dataset = await _standards(service)
    draft = await service.save_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id="evaluator-mismatch",
        expected_revision=0,
        name="期望内容检查",
        scene_version_id=scene.scene_version_id,
        kind=EvaluatorKind.DETERMINISTIC,
        rule="output_contains_expected",
        rubric="",
        hard_failure=False,
    )
    await service.trial_evaluator_draft(
        _actor(StudioRole.DEVELOPER),
        agent_id="agent-1",
        evaluator_id=draft.evaluator_id,
        expected_revision=draft.revision,
        dataset_version_id=dataset.dataset_version_id,
        samples=(
            EvaluatorTrialSample(
                sample_id="case-1",
                input="查询订单",
                expected_output="已发货",
                agent_output="订单待付款",
                expected_outcome=AttemptOutcome.PASS,
            ),
        ),
        evaluator=ControlledEvidenceEvaluator(),
    )

    with pytest.raises(ScenarioInvalidTransition, match="combined judgment"):
        await service.publish_evaluator_group(
            _actor(StudioRole.ADMIN),
            agent_id="agent-1",
            scene_version_id=scene.scene_version_id,
            draft_revisions={draft.evaluator_id: draft.revision},
        )
