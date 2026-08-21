from __future__ import annotations

import pytest

from frontend.server.scenario_evaluation.models import (
    AttemptEvidence,
    AttemptOutcome,
    CaseEvidence,
    CaseOutcome,
    EvaluationDependencies,
    EvaluationRequirement,
    EvaluatorEvidence,
    QualityRecommendationValue,
    SceneEvidence,
    SceneOutcome,
)
from frontend.server.scenario_evaluation.recommendation import (
    aggregate_case,
    aggregate_quality_recommendation,
    aggregate_scene,
    dependency_fingerprint,
    recommendation_is_current,
)


def _attempt(
    outcome: AttemptOutcome,
    *,
    hard_failure: bool = False,
    retry_count: int = 0,
) -> AttemptEvidence:
    evaluator_results = ()
    if outcome in {AttemptOutcome.PASS, AttemptOutcome.FAIL}:
        evaluator_results = (
            EvaluatorEvidence(
                evaluator_version_id="evaluator:v1",
                outcome=AttemptOutcome.FAIL if hard_failure else outcome,
                hard_failure=hard_failure,
            ),
        )
    return AttemptEvidence(
        attempt_index=1,
        outcome=outcome,
        retry_count=retry_count,
        evaluator_results=evaluator_results,
    )


def _case(
    case_id: str,
    outcomes: tuple[AttemptOutcome, AttemptOutcome, AttemptOutcome],
    *,
    scene_id: str = "scene:v1",
    requirement: EvaluationRequirement = EvaluationRequirement.MUST_PASS,
    hard_failure_at: int | None = None,
) -> CaseEvidence:
    attempts = tuple(
        _attempt(outcome, hard_failure=index == hard_failure_at).model_copy(
            update={"attempt_index": index + 1},
        )
        for index, outcome in enumerate(outcomes)
    )
    return CaseEvidence(
        case_version_id=case_id,
        scene_version_id=scene_id,
        requirement=requirement,
        candidate_attempts=attempts,
    )


@pytest.mark.parametrize(
    ("outcomes", "hard_failure_at", "expected"),
    [
        (
            (AttemptOutcome.PASS, AttemptOutcome.PASS, AttemptOutcome.FAIL),
            None,
            CaseOutcome.PASS,
        ),
        (
            (AttemptOutcome.PASS, AttemptOutcome.FAIL, AttemptOutcome.FAIL),
            None,
            CaseOutcome.FAIL,
        ),
        (
            (AttemptOutcome.PASS, AttemptOutcome.PASS, AttemptOutcome.FAIL),
            2,
            CaseOutcome.FAIL,
        ),
        (
            (AttemptOutcome.PASS, AttemptOutcome.FAIL, AttemptOutcome.INFRA_ERROR),
            None,
            CaseOutcome.INDETERMINATE,
        ),
        (
            (AttemptOutcome.PASS, AttemptOutcome.PASS, AttemptOutcome.INFRA_ERROR),
            None,
            CaseOutcome.PASS,
        ),
    ],
)
def test_case_uses_two_of_three_with_hard_failure_precedence(
    outcomes: tuple[AttemptOutcome, AttemptOutcome, AttemptOutcome],
    hard_failure_at: int | None,
    expected: CaseOutcome,
) -> None:
    result = aggregate_case(_case("case:v1", outcomes, hard_failure_at=hard_failure_at))

    assert result.outcome is expected


def test_infrastructure_retry_is_evidence_not_a_fourth_business_attempt() -> None:
    evidence = _case(
        "case:v1",
        (AttemptOutcome.PASS, AttemptOutcome.PASS, AttemptOutcome.INFRA_ERROR),
    )
    retried = evidence.model_copy(
        update={
            "candidate_attempts": (
                evidence.candidate_attempts[0],
                evidence.candidate_attempts[1],
                evidence.candidate_attempts[2].model_copy(update={"retry_count": 1}),
            )
        },
    )

    result = aggregate_case(retried)

    assert len(retried.candidate_attempts) == 3
    assert result.outcome is CaseOutcome.PASS
    assert result.infrastructure_retry_count == 1


def test_must_pass_scene_requires_every_case_and_preserves_indeterminate() -> None:
    passed = aggregate_scene(
        SceneEvidence(
            scene_version_id="scene:v1",
            requirement=EvaluationRequirement.MUST_PASS,
            cases=(
                _case("case-1:v1", (AttemptOutcome.PASS,) * 3),
                _case("case-2:v1", (AttemptOutcome.PASS,) * 3),
            ),
        )
    )
    indeterminate = aggregate_scene(
        SceneEvidence(
            scene_version_id="scene:v1",
            requirement=EvaluationRequirement.MUST_PASS,
            cases=(
                _case("case-1:v1", (AttemptOutcome.PASS,) * 3),
                _case(
                    "case-2:v1",
                    (
                        AttemptOutcome.PASS,
                        AttemptOutcome.FAIL,
                        AttemptOutcome.INFRA_ERROR,
                    ),
                ),
            ),
        )
    )

    assert passed.outcome is SceneOutcome.PASS
    assert indeterminate.outcome is SceneOutcome.INDETERMINATE


def test_observation_scene_failure_only_warns_in_overall_recommendation() -> None:
    required_scene = SceneEvidence(
        scene_version_id="required:v1",
        requirement=EvaluationRequirement.MUST_PASS,
        cases=(
            _case(
                "required-case:v1",
                (AttemptOutcome.PASS,) * 3,
                scene_id="required:v1",
            ),
        ),
    )
    observation_scene = SceneEvidence(
        scene_version_id="observe:v1",
        requirement=EvaluationRequirement.OBSERVATION,
        cases=(
            _case(
                "observe-case:v1",
                (AttemptOutcome.FAIL,) * 3,
                scene_id="observe:v1",
            ),
        ),
    )

    recommendation = aggregate_quality_recommendation(
        (required_scene, observation_scene),
        dependency_fingerprint="sha256:dependencies",
    )

    assert recommendation.value is QualityRecommendationValue.RECOMMEND
    assert recommendation.warning_scene_version_ids == ("observe:v1",)


def test_required_failure_and_missing_evidence_map_to_three_state_recommendation() -> (
    None
):
    failed = aggregate_quality_recommendation(
        (
            SceneEvidence(
                scene_version_id="required:v1",
                requirement=EvaluationRequirement.MUST_PASS,
                cases=(
                    _case(
                        "case:v1",
                        (AttemptOutcome.FAIL,) * 3,
                        scene_id="required:v1",
                    ),
                ),
            ),
        ),
        dependency_fingerprint="sha256:dependencies",
    )
    indeterminate = aggregate_quality_recommendation(
        (
            SceneEvidence(
                scene_version_id="required:v1",
                requirement=EvaluationRequirement.MUST_PASS,
                cases=(
                    _case(
                        "case:v1",
                        (
                            AttemptOutcome.PASS,
                            AttemptOutcome.FAIL,
                            AttemptOutcome.INFRA_ERROR,
                        ),
                        scene_id="required:v1",
                    ),
                ),
            ),
        ),
        dependency_fingerprint="sha256:dependencies",
    )

    assert failed.value is QualityRecommendationValue.DO_NOT_RECOMMEND
    assert indeterminate.value is QualityRecommendationValue.INDETERMINATE


def test_first_release_does_not_require_baseline_attempts() -> None:
    case = _case("case:v1", (AttemptOutcome.PASS,) * 3)

    result = aggregate_case(case)

    assert case.baseline_attempts == ()
    assert result.outcome is CaseOutcome.PASS


def _dependencies() -> EvaluationDependencies:
    return EvaluationDependencies(
        candidate_id="candidate-1",
        baseline_version_id="published-7",
        scene_version_ids=("scene:v1",),
        dataset_version_ids=("dataset:v1",),
        evaluator_version_ids=("evaluator:v1",),
        policy_version_id="policy:v1",
        environment_fingerprint="sha256:runtime",
    )


@pytest.mark.parametrize(
    ("field", "changed_value"),
    [
        ("candidate_id", "candidate-2"),
        ("baseline_version_id", "published-8"),
        ("scene_version_ids", ("scene:v2",)),
        ("dataset_version_ids", ("dataset:v2",)),
        ("evaluator_version_ids", ("evaluator:v2",)),
        ("policy_version_id", "policy:v2"),
        ("environment_fingerprint", "sha256:new-runtime"),
    ],
)
def test_any_dependency_change_invalidates_the_recommendation(
    field: str,
    changed_value: str | tuple[str, ...],
) -> None:
    original = _dependencies()
    fingerprint = dependency_fingerprint(original)
    recommendation = aggregate_quality_recommendation(
        (
            SceneEvidence(
                scene_version_id="scene:v1",
                requirement=EvaluationRequirement.MUST_PASS,
                cases=(_case("case:v1", (AttemptOutcome.PASS,) * 3),),
            ),
        ),
        dependency_fingerprint=fingerprint,
    )

    assert recommendation_is_current(recommendation, original)
    assert not recommendation_is_current(
        recommendation,
        original.model_copy(update={field: changed_value}),
    )
