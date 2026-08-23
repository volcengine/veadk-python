from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Self

import regex as safe_regex
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from veadk.cli.studio_rbac import StudioRole


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ScenarioModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )


class AttemptOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INFRA_ERROR = "infra_error"
    CANCELLED = "cancelled"


class CaseOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"


class SceneOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"


class EvaluationRequirement(str, Enum):
    MUST_PASS = "must_pass"
    OBSERVATION = "observation"


class QualityRecommendationValue(str, Enum):
    RECOMMEND = "recommend"
    DO_NOT_RECOMMEND = "do_not_recommend"
    INDETERMINATE = "indeterminate"


class ScenarioRecordType(str, Enum):
    AGENT_ACCESS = "agent_access"
    CANDIDATE_SOURCE = "candidate_source"
    CANDIDATE_TRANSACTION = "candidate_transaction"
    FEEDBACK_CANDIDATE = "feedback_candidate"
    SCENE_DRAFT = "scene_draft"
    SCENE_VERSION = "scene_version"
    DATASET_DRAFT = "dataset_draft"
    DATASET_VERSION = "dataset_version"
    EVALUATOR_DRAFT = "evaluator_draft"
    EVALUATOR_TRIAL = "evaluator_trial"
    EVALUATOR_VERSION = "evaluator_version"
    POLICY_DRAFT = "policy_draft"
    POLICY_VERSION = "policy_version"
    CANDIDATE_PROJECT = "candidate_project"
    CANDIDATE_VERSION = "candidate_version"
    EVALUATION_RUN = "evaluation_run"
    QUALITY_RECOMMENDATION = "quality_recommendation"
    BADCASE = "badcase"
    PUBLISH_INTENT = "publish_intent"
    PUBLISHED_VERSION = "published_version"
    PUBLISH_AUDIT = "publish_audit"


class FeedbackDecision(str, Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    REJECTED = "rejected"
    MERGED = "merged"
    CONVERTED = "converted"


class EvaluatorKind(str, Enum):
    DETERMINISTIC = "deterministic"
    LLM_RUBRIC = "llm_rubric"


class EvaluationRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BadcaseStatus(str, Enum):
    OPEN = "open"
    VERIFYING = "verifying"
    CLOSED = "closed"


class PublishPath(str, Enum):
    NORMAL = "normal"
    SKIP = "skip"
    RISK = "risk"


class PublishIntentStatus(str, Enum):
    PREPARED = "prepared"
    STARTED = "started"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SUCCEEDED = "succeeded"


class PublishAuditEvent(str, Enum):
    PREPARED = "prepared"
    STARTED = "started"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SUCCEEDED = "succeeded"


class DeterministicRule(str, Enum):
    OUTPUT_CONTAINS_TOOL_EVIDENCE = "output_contains_tool_evidence"
    OUTPUT_CONTAINS_EXPECTED = "output_contains_expected"
    OUTPUT_EXCLUDES_FORBIDDEN = "output_excludes_forbidden"
    OUTPUT_MATCHES_REGEX = "output_matches_regex"
    OUTPUT_EXCLUDES_REGEX = "output_excludes_regex"


class DatasetCaseSource(str, Enum):
    MANUAL = "manual"
    FILE = "file"
    DEBUG_RUN = "debug_run"
    FEEDBACK = "feedback"


class RedactionStatus(str, Enum):
    PENDING = "pending"
    REDACTED = "redacted"
    NOT_REQUIRED = "not_required"


class ScenarioActor(ScenarioModel):
    owner_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: StudioRole
    identifiers: tuple[str, ...] = Field(min_length=1)


class FeedbackSource(ScenarioModel):
    agent_id: str = Field(min_length=1)
    agent_version: str = Field(min_length=1)
    runtime_id: str = Field(min_length=1)
    app_name: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    invocation_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    trace_ref: str = Field(min_length=1)
    input: str = Field(min_length=1)
    output: str = Field(min_length=1)
    rating: Literal["good", "bad"]
    comment: str = ""


class FeedbackCandidateVersion(ScenarioModel):
    candidate_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    source: FeedbackSource
    decision: FeedbackDecision
    reviewed_input: str = ""
    expected_output: str = ""
    review_comment: str = ""
    labels: tuple[str, ...] = ()
    decision_reason: str = ""
    target_candidate_id: str | None = None
    target_dataset_id: str | None = None
    created_at: datetime
    created_by: str = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def _require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("createdAt must include a timezone")
        return value


class DatasetCase(ScenarioModel):
    case_id: str = Field(min_length=1)
    scene_version_id: str = ""
    input: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)
    preloaded_context: str = ""
    test_data_refs: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    pass_criteria: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    forbidden_output: tuple[str, ...] = ()
    source_feedback_candidate_ids: tuple[str, ...] = ()
    source_type: DatasetCaseSource = DatasetCaseSource.MANUAL
    source_refs: tuple[str, ...] = ()
    redaction_status: RedactionStatus = RedactionStatus.NOT_REQUIRED


class SceneDraft(ScenarioModel):
    scene_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    user_task: str = ""
    pass_criteria: tuple[str, ...] = ()
    hard_failure_conditions: tuple[str, ...] = ()
    owner_id: str = ""
    linked_dataset_ids: tuple[str, ...] = ()
    enabled: bool = True
    requirement: EvaluationRequirement
    updated_at: datetime
    updated_by: str = Field(min_length=1)


class SceneVersion(ScenarioModel):
    scene_version_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    source_draft_revision: int = Field(ge=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    user_task: str = Field(min_length=1)
    pass_criteria: tuple[str, ...] = Field(min_length=1)
    hard_failure_conditions: tuple[str, ...] = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    linked_dataset_ids: tuple[str, ...] = ()
    enabled: bool = True
    requirement: EvaluationRequirement
    created_at: datetime
    created_by: str = Field(min_length=1)


class DatasetDraft(ScenarioModel):
    dataset_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1)
    cases: tuple[DatasetCase, ...] = Field(min_length=1)
    updated_at: datetime
    updated_by: str = Field(min_length=1)


class DatasetVersion(ScenarioModel):
    dataset_version_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    source_draft_revision: int = Field(ge=1)
    name: str = Field(min_length=1)
    cases: tuple[DatasetCase, ...] = Field(min_length=1)
    created_at: datetime
    created_by: str = Field(min_length=1)


class EvaluatorDraft(ScenarioModel):
    evaluator_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1)
    scene_version_id: str = ""
    kind: EvaluatorKind
    rule: DeterministicRule | None = None
    rubric: str = ""
    regex_pattern: str = Field(default="", max_length=512)
    hard_failure: bool = False
    updated_at: datetime
    updated_by: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_controlled_configuration(self) -> Self:
        _validate_evaluator_configuration(
            kind=self.kind,
            rule=self.rule,
            rubric=self.rubric,
            regex_pattern=self.regex_pattern,
        )
        return self


class EvaluatorVersion(ScenarioModel):
    evaluator_version_id: str = Field(min_length=1)
    evaluator_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    source_draft_revision: int = Field(ge=1)
    name: str = Field(min_length=1)
    scene_version_id: str = ""
    kind: EvaluatorKind
    rule: DeterministicRule | None = None
    rubric: str = ""
    regex_pattern: str = Field(default="", max_length=512)
    hard_failure: bool = False
    scene_name: str = ""
    scene_user_task: str = ""
    scene_pass_criteria: tuple[str, ...] = ()
    scene_hard_failure_conditions: tuple[str, ...] = ()
    trial_report_id: str = ""
    trial_dataset_version_id: str = ""
    created_at: datetime
    created_by: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_controlled_configuration(self) -> Self:
        _validate_evaluator_configuration(
            kind=self.kind,
            rule=self.rule,
            rubric=self.rubric,
            regex_pattern=self.regex_pattern,
        )
        return self


class EvaluationCriteriaContext(ScenarioModel):
    scene_version_id: str = ""
    scene_name: str = ""
    scene_user_task: str = ""
    scene_pass_criteria: tuple[str, ...] = ()
    scene_hard_failure_conditions: tuple[str, ...] = ()
    case_id: str = Field(min_length=1)
    user_input: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)
    case_pass_criteria: tuple[str, ...] = ()
    forbidden_output: tuple[str, ...] = ()


def _validate_evaluator_configuration(
    *,
    kind: EvaluatorKind,
    rule: DeterministicRule | None,
    rubric: str,
    regex_pattern: str,
) -> None:
    regex_rules = {
        DeterministicRule.OUTPUT_MATCHES_REGEX,
        DeterministicRule.OUTPUT_EXCLUDES_REGEX,
    }
    if kind is EvaluatorKind.LLM_RUBRIC:
        if rule is not None or regex_pattern.strip():
            raise ValueError(
                "LLM rubric evaluator accepts only optional supplemental guidance"
            )
        return
    if rule is None or rubric.strip():
        raise ValueError("deterministic evaluator requires only a controlled rule")
    if rule not in regex_rules:
        if regex_pattern.strip():
            raise ValueError("only a regular expression rule accepts regexPattern")
        return
    if not regex_pattern.strip():
        raise ValueError("regular expression rule requires a regular expression")
    try:
        safe_regex.compile(regex_pattern)
    except safe_regex.error as error:
        raise ValueError("regexPattern must be a valid regular expression") from error


class EvaluatorRecommendationItem(ScenarioModel):
    evaluator_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    scene_standard: str = Field(min_length=1)


class EvaluatorDraftRecommendation(ScenarioModel):
    scene_version_id: str = Field(min_length=1)
    drafts: tuple[EvaluatorDraft, ...] = Field(min_length=1)
    items: tuple[EvaluatorRecommendationItem, ...] = Field(min_length=1)


class EvaluatorTrialSample(ScenarioModel):
    sample_id: str = Field(min_length=1)
    input: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)
    agent_output: str
    expected_outcome: AttemptOutcome = AttemptOutcome.PASS
    forbidden_output: tuple[str, ...] = ()
    trace_json: str = ""

    @model_validator(mode="after")
    def _require_business_expectation(self) -> Self:
        if self.expected_outcome not in {AttemptOutcome.PASS, AttemptOutcome.FAIL}:
            raise ValueError("trial expectation must be pass or fail")
        return self


class EvaluatorTrialResult(ScenarioModel):
    sample_id: str = Field(min_length=1)
    expected_outcome: AttemptOutcome
    outcome: AttemptOutcome
    matches_expectation: bool = False
    hard_failure: bool = False
    reason: str = ""
    error_message: str = ""


class EvaluatorTrialReport(ScenarioModel):
    report_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    evaluator_id: str = Field(min_length=1)
    evaluator_revision: int = Field(ge=1)
    dataset_version_id: str = Field(min_length=1)
    results: tuple[EvaluatorTrialResult, ...] = Field(min_length=1)
    created_at: datetime
    created_by: str = Field(min_length=1)


class EvaluatorGroupPublicationResult(ScenarioModel):
    scene_version_id: str = Field(min_length=1)
    evaluator_versions: tuple[EvaluatorVersion, ...] = Field(min_length=1)
    check_count: int = Field(ge=1)
    calibration_accurate: bool = True


class PolicySceneBinding(ScenarioModel):
    scene_version_id: str = Field(min_length=1)
    dataset_version_id: str = Field(min_length=1)
    evaluator_version_ids: tuple[str, ...] = Field(min_length=1)
    requirement: EvaluationRequirement


class EvaluationPolicyDraft(ScenarioModel):
    policy_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1)
    bindings: tuple[PolicySceneBinding, ...] = Field(min_length=1)
    updated_at: datetime
    updated_by: str = Field(min_length=1)

    @model_validator(mode="after")
    def _require_must_pass_scene(self) -> Self:
        scene_ids = [item.scene_version_id for item in self.bindings]
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("policy cannot bind the same scene more than once")
        if not any(
            item.requirement is EvaluationRequirement.MUST_PASS
            for item in self.bindings
        ):
            raise ValueError("policy must include at least one must-pass scene")
        return self


class EvaluationPolicyVersion(ScenarioModel):
    policy_version_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    source_draft_revision: int = Field(ge=1)
    name: str = Field(min_length=1)
    bindings: tuple[PolicySceneBinding, ...] = Field(min_length=1)
    created_at: datetime
    created_by: str = Field(min_length=1)


class CredentialReference(ScenarioModel):
    name: str = Field(min_length=1)
    reference: str = Field(min_length=1)


class CandidateProjectFile(ScenarioModel):
    path: str = Field(min_length=1)
    content: str


class CandidateProjectSource(ScenarioModel):
    name: str = Field(min_length=1)
    files: tuple[CandidateProjectFile, ...] = Field(min_length=1)
    deployment_profile: dict[str, Any] = Field(default_factory=dict)
    attestation: str = ""
    agent_identity_attestation: str = ""


class CandidateProjectSnapshot(ScenarioModel):
    project_snapshot_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    files: tuple[CandidateProjectFile, ...] = Field(min_length=1)
    deployment_profile: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    created_by: str = Field(min_length=1)


class CandidateArtifact(ScenarioModel):
    code_digest: str = Field(min_length=1)
    topology_digest: str = Field(min_length=1)
    model_refs: tuple[str, ...] = ()
    prompt_refs: tuple[str, ...] = ()
    tool_refs: tuple[str, ...] = ()
    skill_refs: tuple[str, ...] = ()
    knowledge_refs: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    environment_refs: tuple[CredentialReference, ...] = ()
    runtime_project_ref: str | None = None


class CandidateVersion(ScenarioModel):
    candidate_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    artifact: CandidateArtifact
    environment_fingerprint: str = ""
    created_at: datetime
    created_by: str = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def _require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("createdAt must include a timezone")
        return value


class EvaluationDependencies(ScenarioModel):
    candidate_id: str = Field(min_length=1)
    baseline_version_id: str | None = None
    scene_version_ids: tuple[str, ...] = Field(min_length=1)
    dataset_version_ids: tuple[str, ...] = Field(min_length=1)
    evaluator_version_ids: tuple[str, ...] = Field(min_length=1)
    policy_version_id: str = Field(min_length=1)
    environment_fingerprint: str = Field(min_length=1)


class EvaluatorEvidence(ScenarioModel):
    evaluator_version_id: str = Field(min_length=1)
    outcome: AttemptOutcome
    hard_failure: bool = False
    reason: str = ""


class InvalidAttemptEvidence(ScenarioModel):
    session_id: str = ""
    retry_count: int = Field(default=0, ge=0, le=1)
    trace_ref: str = ""
    error_message: str = ""


class AttemptEvidence(ScenarioModel):
    attempt_index: int = Field(ge=1, le=3)
    outcome: AttemptOutcome
    retry_count: int = Field(default=0, ge=0, le=1)
    manual_retry_count: int = Field(default=0, ge=0)
    superseded_invalid_attempts: tuple[InvalidAttemptEvidence, ...] = ()
    evaluator_results: tuple[EvaluatorEvidence, ...] = ()
    session_id: str = ""
    output: str = ""
    trace_ref: str = ""
    trace_json: str = ""
    error_message: str = ""

    @model_validator(mode="after")
    def _require_business_evaluator_evidence(self) -> Self:
        if self.manual_retry_count != len(self.superseded_invalid_attempts):
            raise ValueError(
                "manual retry count must match superseded invalid evidence"
            )
        if (
            self.outcome in {AttemptOutcome.PASS, AttemptOutcome.FAIL}
            and not self.evaluator_results
        ):
            raise ValueError("business attempt requires evaluator results")
        if (
            self.outcome in {AttemptOutcome.INFRA_ERROR, AttemptOutcome.CANCELLED}
            and self.evaluator_results
        ):
            raise ValueError("infrastructure attempt cannot contain evaluator results")
        return self


class CaseEvidence(ScenarioModel):
    case_version_id: str = Field(min_length=1)
    scene_version_id: str = Field(min_length=1)
    requirement: EvaluationRequirement
    candidate_attempts: tuple[AttemptEvidence, ...]
    baseline_attempts: tuple[AttemptEvidence, ...] = ()

    @model_validator(mode="after")
    def _require_three_attempts(self) -> Self:
        if len(self.candidate_attempts) != 3:
            raise ValueError("candidateAttempts must contain exactly three attempts")
        if self.baseline_attempts and len(self.baseline_attempts) != 3:
            raise ValueError("baselineAttempts must be empty or contain three attempts")
        if {item.attempt_index for item in self.candidate_attempts} != {1, 2, 3}:
            raise ValueError("candidate attempt indexes must be 1, 2, and 3")
        if self.baseline_attempts and {
            item.attempt_index for item in self.baseline_attempts
        } != {1, 2, 3}:
            raise ValueError("baseline attempt indexes must be 1, 2, and 3")
        return self


class SceneEvidence(ScenarioModel):
    scene_version_id: str = Field(min_length=1)
    requirement: EvaluationRequirement
    cases: tuple[CaseEvidence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _require_consistent_cases(self) -> Self:
        if any(item.scene_version_id != self.scene_version_id for item in self.cases):
            raise ValueError("every case must belong to the scene")
        return self


class CaseRecommendation(ScenarioModel):
    case_version_id: str
    outcome: CaseOutcome
    pass_count: int
    fail_count: int
    indeterminate_count: int
    infrastructure_retry_count: int
    hard_failure: bool


class SceneRecommendation(ScenarioModel):
    scene_version_id: str
    requirement: EvaluationRequirement
    outcome: SceneOutcome
    case_results: tuple[CaseRecommendation, ...]


class QualityRecommendation(ScenarioModel):
    value: QualityRecommendationValue
    dependency_fingerprint: str
    required_scene_results: tuple[SceneRecommendation, ...]
    observation_scene_results: tuple[SceneRecommendation, ...]
    warning_scene_version_ids: tuple[str, ...]


class QualityRecommendationRecord(ScenarioModel):
    recommendation_id: str = Field(min_length=1)
    evaluation_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    dependencies: EvaluationDependencies
    recommendation: QualityRecommendation
    created_at: datetime


class EvaluationRunVersion(ScenarioModel):
    evaluation_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    status: EvaluationRunStatus
    candidate_id: str = Field(min_length=1)
    baseline_version_id: str | None = None
    policy_version_id: str = Field(min_length=1)
    dependencies: EvaluationDependencies
    scenes: tuple[SceneEvidence, ...] = ()
    recommendation: QualityRecommendation | None = None
    error_message: str = ""
    created_at: datetime
    updated_at: datetime
    created_by: str = Field(min_length=1)


class BadcaseVersion(ScenarioModel):
    badcase_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    status: BadcaseStatus
    scene_version_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    dataset_version_id: str = Field(min_length=1)
    evaluator_version_ids: tuple[str, ...] = Field(min_length=1)
    source_evaluation_id: str = Field(min_length=1)
    source_candidate_id: str = Field(min_length=1)
    verification_evaluation_id: str | None = None
    verification_candidate_id: str | None = None
    resolution_evaluation_id: str | None = None
    resolution_candidate_id: str | None = None
    created_at: datetime
    updated_at: datetime


class PublishIntentVersion(ScenarioModel):
    intent_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    status: PublishIntentStatus
    candidate_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    path: PublishPath
    quality_state: str = Field(min_length=1)
    quality_fingerprint: str = Field(min_length=1)
    evaluation_id: str | None = None
    recommendation_value: QualityRecommendationValue | None = None
    risk_items: tuple[str, ...] = ()
    policy_version_id: str | None = None
    environment_fingerprint: str = Field(min_length=1)
    permission_fingerprint: str = Field(min_length=1)
    second_confirmation: bool = False
    reason: str = ""
    idempotency_key: str = Field(min_length=1)
    deployment_attempts: int = Field(default=0, ge=0)
    deployment_ref: str | None = None
    error_message: str = ""
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class PublishedVersion(ScenarioModel):
    published_version_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    candidate_id: str = Field(min_length=1)
    candidate_artifact: CandidateArtifact
    publish_intent_id: str = Field(min_length=1)
    publish_path: PublishPath
    deployment_ref: str = Field(min_length=1)
    created_at: datetime
    created_by: str = Field(min_length=1)


class PublishRecoveryIssue(ScenarioModel):
    issue_type: Literal[
        "published_intent_not_finalized",
        "success_audit_missing",
    ]
    intent: PublishIntentVersion
    published_version: PublishedVersion


class PublishAudit(ScenarioModel):
    audit_id: str = Field(min_length=1)
    intent_id: str = Field(min_length=1)
    event_index: int = Field(ge=1)
    event: PublishAuditEvent
    agent_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    path: PublishPath
    quality_state: str = Field(min_length=1)
    recommendation_value: QualityRecommendationValue | None = None
    risk_items: tuple[str, ...] = ()
    reason: str = ""
    deployment_ref: str | None = None
    error_message: str = ""
    created_at: datetime


class ScenarioRecord(ScenarioModel):
    record_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    record_type: ScenarioRecordType
    asset_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    created_at: datetime
    payload_json: str = Field(min_length=2)

    @field_validator("created_at")
    @classmethod
    def _require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("createdAt must include a timezone")
        return value

    @field_validator("payload_json")
    @classmethod
    def _canonicalize_payload(cls, value: str) -> str:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("payloadJson must contain valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("payloadJson must contain a JSON object")
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @model_validator(mode="after")
    def _require_deterministic_draft_id(self) -> Self:
        if self.record_type.value.endswith("_draft"):
            expected = f"{self.asset_id}:{self.version}"
            if self.record_id != expected:
                raise ValueError(f"draft recordId must be {expected!r}")
        return self
