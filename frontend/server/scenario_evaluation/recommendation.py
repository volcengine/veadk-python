from __future__ import annotations

import hashlib
import json

from frontend.server.scenario_evaluation.models import (
    AttemptEvidence,
    AttemptOutcome,
    CaseEvidence,
    CaseOutcome,
    CaseRecommendation,
    EvaluationDependencies,
    EvaluationRequirement,
    QualityRecommendation,
    QualityRecommendationValue,
    SceneEvidence,
    SceneOutcome,
    SceneRecommendation,
)


def _attempt_outcome(attempt: AttemptEvidence) -> CaseOutcome:
    if attempt.outcome in (AttemptOutcome.INFRA_ERROR, AttemptOutcome.CANCELLED):
        return CaseOutcome.INDETERMINATE
    if attempt.outcome is not AttemptOutcome.PASS:
        return CaseOutcome.FAIL
    if all(
        result.outcome is AttemptOutcome.PASS for result in attempt.evaluator_results
    ):
        return CaseOutcome.PASS
    return CaseOutcome.FAIL


def aggregate_case(evidence: CaseEvidence) -> CaseRecommendation:
    hard_failure = any(
        evaluator.hard_failure
        for attempt in evidence.candidate_attempts
        for evaluator in attempt.evaluator_results
    )
    attempt_outcomes = tuple(
        _attempt_outcome(attempt) for attempt in evidence.candidate_attempts
    )
    pass_count = attempt_outcomes.count(CaseOutcome.PASS)
    fail_count = attempt_outcomes.count(CaseOutcome.FAIL)
    indeterminate_count = attempt_outcomes.count(CaseOutcome.INDETERMINATE)

    if hard_failure:
        outcome = CaseOutcome.FAIL
    elif pass_count >= 2:
        outcome = CaseOutcome.PASS
    elif fail_count >= 2:
        outcome = CaseOutcome.FAIL
    else:
        outcome = CaseOutcome.INDETERMINATE

    return CaseRecommendation(
        case_version_id=evidence.case_version_id,
        outcome=outcome,
        pass_count=pass_count,
        fail_count=fail_count,
        indeterminate_count=indeterminate_count,
        infrastructure_retry_count=sum(
            attempt.retry_count for attempt in evidence.candidate_attempts
        ),
        hard_failure=hard_failure,
    )


def aggregate_scene(evidence: SceneEvidence) -> SceneRecommendation:
    case_results = tuple(aggregate_case(item) for item in evidence.cases)
    outcomes = {item.outcome for item in case_results}
    if CaseOutcome.FAIL in outcomes:
        outcome = SceneOutcome.FAIL
    elif CaseOutcome.INDETERMINATE in outcomes:
        outcome = SceneOutcome.INDETERMINATE
    else:
        outcome = SceneOutcome.PASS
    return SceneRecommendation(
        scene_version_id=evidence.scene_version_id,
        requirement=evidence.requirement,
        outcome=outcome,
        case_results=case_results,
    )


def aggregate_quality_recommendation(
    scenes: tuple[SceneEvidence, ...],
    *,
    dependency_fingerprint: str,
) -> QualityRecommendation:
    scene_results = tuple(aggregate_scene(scene) for scene in scenes)
    required = tuple(
        result
        for result in scene_results
        if result.requirement is EvaluationRequirement.MUST_PASS
    )
    observation = tuple(
        result
        for result in scene_results
        if result.requirement is EvaluationRequirement.OBSERVATION
    )

    if any(result.outcome is SceneOutcome.FAIL for result in required):
        value = QualityRecommendationValue.DO_NOT_RECOMMEND
    elif not required or any(
        result.outcome is SceneOutcome.INDETERMINATE for result in required
    ):
        value = QualityRecommendationValue.INDETERMINATE
    else:
        value = QualityRecommendationValue.RECOMMEND

    return QualityRecommendation(
        value=value,
        dependency_fingerprint=dependency_fingerprint,
        required_scene_results=required,
        observation_scene_results=observation,
        warning_scene_version_ids=tuple(
            result.scene_version_id
            for result in observation
            if result.outcome is not SceneOutcome.PASS
        ),
    )


def dependency_fingerprint(dependencies: EvaluationDependencies) -> str:
    payload = json.dumps(
        dependencies.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def recommendation_is_current(
    recommendation: QualityRecommendation,
    dependencies: EvaluationDependencies,
) -> bool:
    return recommendation.dependency_fingerprint == dependency_fingerprint(dependencies)
