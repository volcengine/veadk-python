"""Trace the PRD acceptance cases to executable backend/frontend evidence."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]

ACCEPTANCE_EVIDENCE: dict[str, tuple[str, ...]] = {
    "TC-01": (
        "tests/cli/test_frontend_evaluation_feedback.py::test_studio_feedback",
        "tests/frontend/server/scenario_evaluation/test_service_assets.py::test_end_user_feedback_creates_owned_immutable_candidate",
    ),
    "TC-02": (
        "tests/frontend/server/scenario_evaluation/test_service_assets.py::test_tc_02_merged_feedback_keeps_all_sources_and_requires_redaction",
    ),
    "TC-03": (
        "tests/frontend/server/scenario_evaluation/test_service_assets.py::test_developer_edits_drafts_but_only_admin_publishes_versions",
        "tests/frontend/server/scenario_evaluation/test_repository.py::test_draft_append_uses_expected_revision_and_never_overwrites",
    ),
    "TC-04": (
        "tests/frontend/server/scenario_evaluation/test_service_assets.py::test_admin_publishes_dataset_evaluator_and_complete_policy",
    ),
    "TC-05": (
        "tests/frontend/server/scenario_evaluation/test_evaluator_lifecycle.py::test_tc_05_scene_recommends_controlled_rule_and_structured_rubric_drafts",
    ),
    "TC-06": (
        "tests/frontend/server/scenario_evaluation/test_evaluator_lifecycle.py::test_tc_06_draft_trial_separates_business_failure_from_infrastructure_error",
        "tests/frontend/server/scenario_evaluation/test_evaluators.py::test_llm_rubric_failure_is_retryable_infrastructure_error",
    ),
    "TC-07": (
        "tests/frontend/server/scenario_evaluation/test_service_runs.py::test_client_cannot_reduce_the_published_policy_case_set",
    ),
    "TC-08": (
        "tests/frontend/server/scenario_evaluation/test_service_assets.py::test_candidate_stores_immutable_runtime_project_behind_server_reference",
        "frontend/tests/scenarioPublishConfirmation.test.mjs::project candidate builder freezes code",
    ),
    "TC-09": (
        "tests/frontend/server/scenario_evaluation/test_executor.py::test_candidate_and_baseline_each_run_three_independent_sessions",
    ),
    "TC-10": (
        "tests/frontend/server/scenario_evaluation/test_recommendation.py::test_case_uses_two_of_three_with_hard_failure_precedence",
    ),
    "TC-11": (
        "tests/frontend/server/scenario_evaluation/test_recommendation.py::test_case_uses_two_of_three_with_hard_failure_precedence",
    ),
    "TC-12": (
        "tests/frontend/server/scenario_evaluation/test_executor.py::test_second_infrastructure_failure_becomes_indeterminate_evidence",
        "tests/frontend/server/scenario_evaluation/test_publishing.py::test_negative_or_indeterminate_recommendation_requires_risk_publish",
    ),
    "TC-13": (
        "tests/frontend/server/scenario_evaluation/test_recommendation.py::test_observation_scene_failure_only_warns_in_overall_recommendation",
    ),
    "TC-14": (
        "frontend/tests/scenarioEvaluationWorkspace.test.mjs::scenario workspace supports evidence drill-down",
        "tests/frontend/server/scenario_evaluation/test_evaluators.py::test_controlled_rules_use_output_expected_and_persisted_trace",
    ),
    "TC-15": (
        "tests/frontend/server/scenario_evaluation/test_executor.py::test_valid_business_failure_never_triggers_runtime_retry",
        "tests/frontend/server/scenario_evaluation/test_service_runs.py::test_badcase_closes_only_for_new_candidate_with_same_standard_scope",
    ),
    "TC-16": (
        "tests/frontend/server/scenario_evaluation/test_service_runs.py::test_badcase_closes_only_for_new_candidate_with_same_standard_scope",
    ),
    "TC-17": (
        "tests/frontend/server/scenario_evaluation/test_recommendation.py::test_any_dependency_change_invalidates_the_recommendation",
        "tests/frontend/server/scenario_evaluation/test_publishing.py::test_unevaluated_and_stale_candidates_require_confirmed_skip_reason",
    ),
    "TC-18": (
        "tests/frontend/server/scenario_evaluation/test_publishing.py::test_failed_deploy_retries_idempotently_and_success_sets_baseline_once",
    ),
    "TC-19": (
        "tests/frontend/server/scenario_evaluation/test_publishing.py::test_running_evaluation_must_finish_or_cancel_before_prepare",
        "tests/frontend/server/scenario_evaluation/test_service_runs.py::test_cancel_waits_for_terminal_state_and_closes_runtime",
    ),
    "TC-20": (
        "tests/frontend/server/scenario_evaluation/test_publishing.py::test_negative_or_indeterminate_recommendation_requires_risk_publish",
        "frontend/tests/scenarioPublishConfirmation.test.mjs::guarded risk paths",
    ),
    "TC-21": (
        "tests/frontend/server/scenario_evaluation/test_service_assets.py::test_reviewed_feedback_converts_to_dataset_case_with_source_lineage",
    ),
    "TC-22": (
        "tests/frontend/server/scenario_evaluation/test_publishing.py::test_valid_recommendation_uses_normal_path_without_risk_reason",
        "tests/frontend/server/scenario_evaluation/test_publishing.py::test_unevaluated_and_stale_candidates_require_confirmed_skip_reason",
        "tests/frontend/server/scenario_evaluation/test_publishing.py::test_negative_or_indeterminate_recommendation_requires_risk_publish",
        "tests/frontend/server/scenario_evaluation/test_service_runs.py::test_badcase_closes_only_for_new_candidate_with_same_standard_scope",
    ),
}


@pytest.mark.parametrize(
    ("case_id", "evidence"),
    ACCEPTANCE_EVIDENCE.items(),
    ids=ACCEPTANCE_EVIDENCE,
)
def test_prd_acceptance_case_has_executable_evidence(
    case_id: str,
    evidence: tuple[str, ...],
) -> None:
    assert case_id.startswith("TC-")
    assert evidence
    for pointer in evidence:
        relative_path, marker = pointer.split("::", maxsplit=1)
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert marker in source, f"{case_id} lost evidence {pointer}"


def test_acceptance_matrix_covers_tc_01_through_tc_22_exactly_once() -> None:
    assert set(ACCEPTANCE_EVIDENCE) == {f"TC-{index:02d}" for index in range(1, 23)}
