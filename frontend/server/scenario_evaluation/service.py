"""Application service for governed scenario-evaluation assets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel

from frontend.server.scenario_evaluation.errors import (
    ScenarioForbidden,
    ScenarioInvalidTransition,
    ScenarioNotFound,
)
from frontend.server.scenario_evaluation.executor import (
    EvaluationInfrastructureError,
    EvidenceEvaluator,
    RuntimeEvidence,
)
from frontend.server.scenario_evaluation.models import (
    AttemptOutcome,
    CandidateArtifact,
    CandidateProjectFile,
    CandidateProjectSnapshot,
    CandidateProjectSource,
    CandidateVersion,
    DatasetCase,
    DatasetCaseSource,
    DatasetDraft,
    DatasetVersion,
    DeterministicRule,
    EvaluationPolicyDraft,
    EvaluationPolicyVersion,
    EvaluationRequirement,
    EvaluatorDraft,
    EvaluatorDraftRecommendation,
    EvaluatorGroupPublicationResult,
    EvaluatorKind,
    EvaluatorRecommendationItem,
    EvaluatorTrialReport,
    EvaluatorTrialResult,
    EvaluatorTrialSample,
    EvaluatorVersion,
    FeedbackCandidateVersion,
    FeedbackDecision,
    FeedbackSource,
    PolicySceneBinding,
    RedactionStatus,
    ScenarioActor,
    ScenarioRecord,
    ScenarioRecordType,
    SceneDraft,
    SceneVersion,
)
from frontend.server.scenario_evaluation.repository import (
    ScenarioEvaluationRepository,
    ScenarioRecordConflict,
    authorize_repository_agent_claim,
)
from veadk.cli.generated_agent_codegen import GeneratedFile, GeneratedProject
from veadk.cli.generated_agent_runtime import (
    GeneratedAgentRuntimeError,
    validate_generated_project,
)
from veadk.cli.studio_rbac import StudioRole

_ModelT = TypeVar("_ModelT", bound=BaseModel)
ProjectAttestationVerifier = Callable[[GeneratedProject, str, str], None]
AgentIdentityVerifier = Callable[
    [ScenarioActor, str, Mapping[str, object], str], Awaitable[None]
]


def _candidate_source_digest(files: tuple[CandidateProjectFile, ...]) -> str:
    payload = sorted(
        (item.model_dump(mode="json") for item in files),
        key=lambda item: (str(item["path"]), str(item["content"])),
    )
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(b"candidate-source-v1\0" + canonical).hexdigest()


def _candidate_source_agent_id(
    owner_id: str,
    files: tuple[CandidateProjectFile, ...],
) -> str:
    owner_digest = hashlib.sha256(
        b"candidate-source-owner-v1\0" + owner_id.encode("utf-8")
    ).hexdigest()
    return f"_candidate-source:{owner_digest}:{_candidate_source_digest(files)}"


def _candidate_transaction_agent_id(
    owner_id: str,
    agent_id: str,
    artifact: CandidateArtifact,
    project: CandidateProjectSource,
) -> str:
    payload = {
        "agentId": agent_id,
        "artifact": artifact.model_dump(
            mode="json",
            by_alias=True,
            exclude={"runtime_project_ref"},
        ),
        "project": {
            "name": project.name,
            "files": sorted(
                (item.model_dump(mode="json") for item in project.files),
                key=lambda item: (str(item["path"]), str(item["content"])),
            ),
            "deploymentProfile": project.deployment_profile,
        },
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    owner_digest = hashlib.sha256(
        b"candidate-transaction-owner-v1\0" + owner_id.encode("utf-8")
    ).hexdigest()
    request_digest = hashlib.sha256(
        b"candidate-transaction-v1\0" + canonical
    ).hexdigest()
    return f"_candidate-transaction:{owner_digest}:{request_digest}"


def _default_id_factory(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class ScenarioEvaluationService:
    def __init__(
        self,
        repository: ScenarioEvaluationRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
        project_attestation_verifier: ProjectAttestationVerifier | None = None,
        agent_identity_verifier: AgentIdentityVerifier | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or _default_id_factory
        self._project_attestation_verifier = project_attestation_verifier
        self._agent_identity_verifier = agent_identity_verifier

    async def create_feedback_candidate(
        self,
        actor: ScenarioActor,
        source: FeedbackSource,
    ) -> FeedbackCandidateVersion:
        if source.user_id.casefold() not in {
            item.casefold() for item in actor.identifiers
        }:
            raise ScenarioForbidden(
                "Feedback can only be submitted for the current user."
            )
        source_json = source.model_dump_json(by_alias=True)
        source_digest = hashlib.sha256(source_json.encode("utf-8")).hexdigest()
        candidate_id = f"feedback-{source_digest[:32]}"
        record_id = f"{candidate_id}:1"
        existing = await self._repository.get(
            agent_id=source.agent_id,
            record_type=ScenarioRecordType.FEEDBACK_CANDIDATE,
            record_id=record_id,
        )
        if existing is not None:
            candidate = FeedbackCandidateVersion.model_validate_json(
                existing.payload_json
            )
            if candidate.source == source and candidate.created_by == actor.owner_id:
                return candidate
            raise ScenarioRecordConflict(
                "Feedback candidate identity already has different source evidence."
            )
        candidate = FeedbackCandidateVersion(
            candidate_id=candidate_id,
            agent_id=source.agent_id,
            revision=1,
            source=source,
            decision=FeedbackDecision.PENDING,
            created_at=self._now(),
            created_by=actor.owner_id,
        )
        try:
            await self._append_model(
                candidate,
                record_id=record_id,
                agent_id=source.agent_id,
                owner_id=actor.owner_id,
                record_type=ScenarioRecordType.FEEDBACK_CANDIDATE,
                asset_id=candidate_id,
                version=1,
            )
        except ScenarioRecordConflict:
            existing = await self._repository.get(
                agent_id=source.agent_id,
                record_type=ScenarioRecordType.FEEDBACK_CANDIDATE,
                record_id=record_id,
            )
            if existing is None:
                raise
            concurrent = FeedbackCandidateVersion.model_validate_json(
                existing.payload_json
            )
            if concurrent.source != source or concurrent.created_by != actor.owner_id:
                raise
            return concurrent
        return candidate

    async def review_feedback_candidate(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        candidate_id: str,
        expected_revision: int,
        input: str,
        expected_output: str,
        comment: str,
        labels: tuple[str, ...],
    ) -> FeedbackCandidateVersion:
        self._require_manager(actor)
        if not input.strip() or not expected_output.strip():
            raise ScenarioInvalidTransition(
                "Reviewed feedback requires input and expected output."
            )
        current = await self._feedback_at_revision(
            agent_id, candidate_id, expected_revision
        )
        self._require_feedback_open(current)
        return await self._append_feedback_revision(
            actor,
            current,
            decision=FeedbackDecision.REVIEWED,
            reviewed_input=input.strip(),
            expected_output=expected_output.strip(),
            review_comment=comment.strip(),
            labels=tuple(item.strip() for item in labels if item.strip()),
        )

    async def reject_feedback_candidate(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        candidate_id: str,
        expected_revision: int,
        reason: str,
    ) -> FeedbackCandidateVersion:
        self._require_manager(actor)
        if not reason.strip():
            raise ScenarioInvalidTransition("Rejecting feedback requires a reason.")
        current = await self._feedback_at_revision(
            agent_id, candidate_id, expected_revision
        )
        self._require_feedback_open(current)
        return await self._append_feedback_revision(
            actor,
            current,
            decision=FeedbackDecision.REJECTED,
            decision_reason=reason.strip(),
        )

    async def merge_feedback_candidate(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        candidate_id: str,
        expected_revision: int,
        target_candidate_id: str,
        reason: str,
    ) -> FeedbackCandidateVersion:
        self._require_manager(actor)
        if candidate_id == target_candidate_id:
            raise ScenarioInvalidTransition("Feedback cannot be merged into itself.")
        if not reason.strip():
            raise ScenarioInvalidTransition("Merging feedback requires a reason.")
        current = await self._feedback_at_revision(
            agent_id, candidate_id, expected_revision
        )
        self._require_feedback_open(current)
        await self._latest_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.FEEDBACK_CANDIDATE,
            asset_id=target_candidate_id,
            model_type=FeedbackCandidateVersion,
        )
        return await self._append_feedback_revision(
            actor,
            current,
            decision=FeedbackDecision.MERGED,
            target_candidate_id=target_candidate_id,
            decision_reason=reason.strip(),
        )

    async def convert_feedback_candidate(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        candidate_id: str,
        expected_revision: int,
        dataset_id: str,
        expected_dataset_revision: int,
        dataset_name: str,
        scene_version_id: str,
        pass_criteria: tuple[str, ...],
        redaction_status: RedactionStatus = RedactionStatus.PENDING,
    ) -> tuple[FeedbackCandidateVersion, DatasetDraft]:
        self._require_manager(actor)
        current = await self._feedback_at_revision(
            agent_id, candidate_id, expected_revision
        )
        if current.decision is not FeedbackDecision.REVIEWED:
            raise ScenarioInvalidTransition(
                "Feedback must be reviewed before it can become a case."
            )
        await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.SCENE_VERSION,
            record_id=scene_version_id,
            model_type=SceneVersion,
        )
        if not pass_criteria or any(not item.strip() for item in pass_criteria):
            raise ScenarioInvalidTransition(
                "Feedback Case requires explicit pass criteria."
            )
        existing_cases: tuple[DatasetCase, ...] = ()
        if expected_dataset_revision:
            existing = await self._draft_at_revision(
                agent_id=agent_id,
                record_type=ScenarioRecordType.DATASET_DRAFT,
                asset_id=dataset_id,
                revision=expected_dataset_revision,
                model_type=DatasetDraft,
            )
            existing_cases = existing.cases
        source_candidate_ids = await self._merged_feedback_lineage(
            agent_id=agent_id,
            target_candidate_id=candidate_id,
        )
        case = DatasetCase(
            case_id=self._id_factory("case"),
            scene_version_id=scene_version_id,
            input=current.reviewed_input,
            expected_output=current.expected_output,
            pass_criteria=tuple(item.strip() for item in pass_criteria),
            labels=current.labels,
            source_feedback_candidate_ids=source_candidate_ids,
            source_type=DatasetCaseSource.FEEDBACK,
            source_refs=source_candidate_ids,
            redaction_status=redaction_status,
        )
        dataset = await self.save_dataset_draft(
            actor,
            agent_id=agent_id,
            dataset_id=dataset_id,
            expected_revision=expected_dataset_revision,
            name=dataset_name,
            cases=(*existing_cases, case),
        )
        converted = await self._append_feedback_revision(
            actor,
            current,
            decision=FeedbackDecision.CONVERTED,
            target_dataset_id=dataset_id,
        )
        return converted, dataset

    async def save_scene_draft(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        scene_id: str,
        expected_revision: int,
        name: str,
        description: str,
        user_task: str,
        pass_criteria: tuple[str, ...],
        hard_failure_conditions: tuple[str, ...],
        owner_id: str,
        requirement: EvaluationRequirement,
        linked_dataset_ids: tuple[str, ...] = (),
        enabled: bool = True,
    ) -> SceneDraft:
        self._require_manager(actor)
        draft = SceneDraft(
            scene_id=scene_id,
            agent_id=agent_id,
            revision=expected_revision + 1,
            name=name,
            description=description,
            user_task=user_task,
            pass_criteria=pass_criteria,
            hard_failure_conditions=hard_failure_conditions,
            owner_id=owner_id,
            linked_dataset_ids=linked_dataset_ids,
            enabled=enabled,
            requirement=requirement,
            updated_at=self._now(),
            updated_by=actor.owner_id,
        )
        await self._append_draft_model(
            draft,
            agent_id=agent_id,
            owner_id=actor.owner_id,
            record_type=ScenarioRecordType.SCENE_DRAFT,
            asset_id=scene_id,
            revision=draft.revision,
            expected_revision=expected_revision,
        )
        return draft

    async def publish_scene_version(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        scene_id: str,
        draft_revision: int,
    ) -> SceneVersion:
        self._require_admin(actor)
        draft = await self._draft_at_revision(
            agent_id=agent_id,
            record_type=ScenarioRecordType.SCENE_DRAFT,
            asset_id=scene_id,
            revision=draft_revision,
            model_type=SceneDraft,
        )
        missing: list[str] = []
        if not draft.user_task.strip():
            missing.append("user task")
        if not draft.pass_criteria or any(
            not item.strip() for item in draft.pass_criteria
        ):
            missing.append("pass criteria")
        if not draft.hard_failure_conditions or any(
            not item.strip() for item in draft.hard_failure_conditions
        ):
            missing.append("hard failure conditions")
        if not draft.owner_id.strip():
            missing.append("owner")
        if missing:
            raise ScenarioInvalidTransition(
                "Scene cannot be published without " + ", ".join(missing) + "."
            )
        version = await self._next_version(
            agent_id, ScenarioRecordType.SCENE_VERSION, scene_id
        )
        model = SceneVersion(
            scene_version_id=f"{scene_id}:v{version}",
            scene_id=scene_id,
            agent_id=agent_id,
            version=version,
            source_draft_revision=draft_revision,
            name=draft.name,
            description=draft.description,
            user_task=draft.user_task.strip(),
            pass_criteria=tuple(item.strip() for item in draft.pass_criteria),
            hard_failure_conditions=tuple(
                item.strip() for item in draft.hard_failure_conditions
            ),
            owner_id=draft.owner_id.strip(),
            linked_dataset_ids=draft.linked_dataset_ids,
            enabled=draft.enabled,
            requirement=draft.requirement,
            created_at=self._now(),
            created_by=actor.owner_id,
        )
        await self._append_published_model(
            model,
            record_id=model.scene_version_id,
            actor=actor,
            agent_id=agent_id,
            record_type=ScenarioRecordType.SCENE_VERSION,
            asset_id=scene_id,
            version=version,
        )
        return model

    async def save_dataset_draft(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        dataset_id: str,
        expected_revision: int,
        name: str,
        cases: tuple[DatasetCase, ...],
    ) -> DatasetDraft:
        self._require_manager(actor)
        draft = DatasetDraft(
            dataset_id=dataset_id,
            agent_id=agent_id,
            revision=expected_revision + 1,
            name=name,
            cases=cases,
            updated_at=self._now(),
            updated_by=actor.owner_id,
        )
        await self._append_draft_model(
            draft,
            agent_id=agent_id,
            owner_id=actor.owner_id,
            record_type=ScenarioRecordType.DATASET_DRAFT,
            asset_id=dataset_id,
            revision=draft.revision,
            expected_revision=expected_revision,
        )
        return draft

    async def publish_dataset_version(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        dataset_id: str,
        draft_revision: int,
    ) -> DatasetVersion:
        self._require_admin(actor)
        draft = await self._draft_at_revision(
            agent_id=agent_id,
            record_type=ScenarioRecordType.DATASET_DRAFT,
            asset_id=dataset_id,
            revision=draft_revision,
            model_type=DatasetDraft,
        )
        if any(
            case.redaction_status is RedactionStatus.PENDING for case in draft.cases
        ):
            raise ScenarioInvalidTransition(
                "Dataset contains a Case with pending redaction review."
            )
        incomplete = [
            case.case_id
            for case in draft.cases
            if not case.scene_version_id.strip()
            or not case.pass_criteria
            or any(not item.strip() for item in case.pass_criteria)
            or not case.source_refs
            or any(not item.strip() for item in case.source_refs)
        ]
        if incomplete:
            raise ScenarioInvalidTransition(
                "Dataset Case requires a published Scene, pass criteria, and source: "
                + ", ".join(incomplete)
            )
        case_ids = [case.case_id for case in draft.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ScenarioInvalidTransition("Dataset contains duplicate Case ids.")
        semantic_keys = [
            (
                case.scene_version_id,
                case.input.strip().casefold(),
                case.expected_output.strip().casefold(),
            )
            for case in draft.cases
        ]
        if len(semantic_keys) != len(set(semantic_keys)):
            raise ScenarioInvalidTransition("Dataset contains duplicate Cases.")
        for scene_version_id in dict.fromkeys(
            case.scene_version_id for case in draft.cases
        ):
            await self._record_model(
                agent_id=agent_id,
                record_type=ScenarioRecordType.SCENE_VERSION,
                record_id=scene_version_id,
                model_type=SceneVersion,
            )
        version = await self._next_version(
            agent_id, ScenarioRecordType.DATASET_VERSION, dataset_id
        )
        model = DatasetVersion(
            dataset_version_id=f"{dataset_id}:v{version}",
            dataset_id=dataset_id,
            agent_id=agent_id,
            version=version,
            source_draft_revision=draft_revision,
            name=draft.name,
            cases=draft.cases,
            created_at=self._now(),
            created_by=actor.owner_id,
        )
        await self._append_published_model(
            model,
            record_id=model.dataset_version_id,
            actor=actor,
            agent_id=agent_id,
            record_type=ScenarioRecordType.DATASET_VERSION,
            asset_id=dataset_id,
            version=version,
        )
        return model

    async def save_evaluator_draft(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        evaluator_id: str,
        expected_revision: int,
        name: str,
        scene_version_id: str,
        kind: EvaluatorKind,
        rule: str,
        rubric: str,
        regex_pattern: str = "",
        hard_failure: bool = False,
    ) -> EvaluatorDraft:
        self._require_manager(actor)
        await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.SCENE_VERSION,
            record_id=scene_version_id,
            model_type=SceneVersion,
        )
        draft = EvaluatorDraft(
            evaluator_id=evaluator_id,
            agent_id=agent_id,
            revision=expected_revision + 1,
            name=name,
            scene_version_id=scene_version_id,
            kind=kind,
            rule=DeterministicRule(rule) if rule else None,
            rubric=rubric,
            regex_pattern=regex_pattern,
            hard_failure=hard_failure,
            updated_at=self._now(),
            updated_by=actor.owner_id,
        )
        await self._append_draft_model(
            draft,
            agent_id=agent_id,
            owner_id=actor.owner_id,
            record_type=ScenarioRecordType.EVALUATOR_DRAFT,
            asset_id=evaluator_id,
            revision=draft.revision,
            expected_revision=expected_revision,
        )
        return draft

    async def recommend_evaluator_drafts(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        scene_version_id: str,
    ) -> EvaluatorDraftRecommendation:
        self._require_manager(actor)
        scene = await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.SCENE_VERSION,
            record_id=scene_version_id,
            model_type=SceneVersion,
        )
        controlled_rule = DeterministicRule.OUTPUT_EXCLUDES_FORBIDDEN
        deterministic_id = self._id_factory("evaluator")
        rubric_id = self._id_factory("evaluator")
        deterministic = await self.save_evaluator_draft(
            actor,
            agent_id=agent_id,
            evaluator_id=deterministic_id,
            expected_revision=0,
            name=f"{scene.name}·确定性检查",
            scene_version_id=scene.scene_version_id,
            kind=EvaluatorKind.DETERMINISTIC,
            rule=controlled_rule.value,
            rubric="",
            regex_pattern="",
            hard_failure=True,
        )
        rubric = await self.save_evaluator_draft(
            actor,
            agent_id=agent_id,
            evaluator_id=rubric_id,
            expected_revision=0,
            name=f"{scene.name}·语义标准",
            scene_version_id=scene.scene_version_id,
            kind=EvaluatorKind.LLM_RUBRIC,
            rule="",
            rubric="",
            regex_pattern="",
            hard_failure=False,
        )
        return EvaluatorDraftRecommendation(
            scene_version_id=scene_version_id,
            drafts=(deterministic, rubric),
            items=(
                EvaluatorRecommendationItem(
                    evaluator_id=deterministic_id,
                    rationale="用受控规则检查可确定执行证据，不开放自定义代码。",
                    scene_standard="；".join(scene.hard_failure_conditions),
                ),
                EvaluatorRecommendationItem(
                    evaluator_id=rubric_id,
                    rationale="用结构化 Rubric 判断语义标准，并要求给出对应依据。",
                    scene_standard="；".join(scene.pass_criteria),
                ),
            ),
        )

    async def trial_evaluator_draft(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        evaluator_id: str,
        expected_revision: int,
        dataset_version_id: str,
        samples: tuple[EvaluatorTrialSample, ...],
        evaluator: EvidenceEvaluator,
    ) -> EvaluatorTrialReport:
        self._require_manager(actor)
        if not samples:
            raise ScenarioInvalidTransition("Evaluator trial requires samples.")
        draft = await self._draft_at_revision(
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATOR_DRAFT,
            asset_id=evaluator_id,
            revision=expected_revision,
            model_type=EvaluatorDraft,
        )
        scene = await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.SCENE_VERSION,
            record_id=draft.scene_version_id,
            model_type=SceneVersion,
        )
        dataset = await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.DATASET_VERSION,
            record_id=dataset_version_id,
            model_type=DatasetVersion,
        )
        available_cases = {case.case_id: case for case in dataset.cases}
        for sample in samples:
            source_case = available_cases.get(sample.sample_id)
            if source_case is None:
                raise ScenarioInvalidTransition(
                    f"Evaluator trial sample {sample.sample_id!r} is not in the Dataset."
                )
            if source_case.scene_version_id != draft.scene_version_id:
                raise ScenarioInvalidTransition(
                    "Evaluator trial sample belongs to another Scene."
                )
            if (
                source_case.input != sample.input
                or source_case.expected_output != sample.expected_output
                or source_case.forbidden_output != sample.forbidden_output
            ):
                raise ScenarioInvalidTransition(
                    "Evaluator trial sample must preserve the published Dataset Case."
                )
        synthetic = EvaluatorVersion(
            evaluator_version_id=f"{evaluator_id}:draft-r{draft.revision}",
            evaluator_id=evaluator_id,
            agent_id=agent_id,
            version=1,
            source_draft_revision=draft.revision,
            name=draft.name,
            scene_version_id=draft.scene_version_id,
            kind=draft.kind,
            rule=draft.rule,
            rubric=draft.rubric,
            regex_pattern=draft.regex_pattern,
            hard_failure=draft.hard_failure,
            scene_name=scene.name,
            scene_user_task=scene.user_task,
            scene_pass_criteria=scene.pass_criteria,
            scene_hard_failure_conditions=scene.hard_failure_conditions,
            created_at=self._now(),
            created_by=actor.owner_id,
        )
        results: list[EvaluatorTrialResult] = []
        for index, sample in enumerate(samples, start=1):
            case = available_cases[sample.sample_id]
            try:
                evidence = await evaluator.evaluate(
                    synthetic,
                    case,
                    RuntimeEvidence(
                        output=sample.agent_output,
                        trace_ref=f"trial:{sample.sample_id}",
                        trace_json=sample.trace_json,
                    ),
                    attempt_index=index,
                )
            except EvaluationInfrastructureError as error:
                results.append(
                    EvaluatorTrialResult(
                        sample_id=sample.sample_id,
                        expected_outcome=sample.expected_outcome,
                        outcome=AttemptOutcome.INFRA_ERROR,
                        matches_expectation=False,
                        error_message=str(error),
                    )
                )
            else:
                results.append(
                    EvaluatorTrialResult(
                        sample_id=sample.sample_id,
                        expected_outcome=sample.expected_outcome,
                        outcome=evidence.outcome,
                        matches_expectation=evidence.outcome is sample.expected_outcome,
                        hard_failure=evidence.hard_failure,
                        reason=evidence.reason,
                    )
                )
        report_id = self._id_factory("evaluator-trial")
        report = EvaluatorTrialReport(
            report_id=report_id,
            agent_id=agent_id,
            evaluator_id=evaluator_id,
            evaluator_revision=draft.revision,
            dataset_version_id=dataset_version_id,
            results=tuple(results),
            created_at=self._now(),
            created_by=actor.owner_id,
        )
        await self._append_model(
            report,
            record_id=report_id,
            agent_id=agent_id,
            owner_id=actor.owner_id,
            record_type=ScenarioRecordType.EVALUATOR_TRIAL,
            asset_id=evaluator_id,
            version=draft.revision,
        )
        return report

    async def publish_evaluator_version(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        evaluator_id: str,
        draft_revision: int,
    ) -> EvaluatorVersion:
        self._require_admin(actor)
        draft = await self._draft_at_revision(
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATOR_DRAFT,
            asset_id=evaluator_id,
            revision=draft_revision,
            model_type=EvaluatorDraft,
        )
        trial_records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATOR_TRIAL,
        )
        trials = [
            EvaluatorTrialReport.model_validate_json(record.payload_json)
            for record in trial_records
            if record.asset_id == evaluator_id and record.version == draft_revision
        ]
        if not trials:
            raise ScenarioInvalidTransition(
                "Evaluator draft requires a persisted trial before publication."
            )
        trial = max(trials, key=lambda item: item.created_at)
        if any(
            not result.matches_expectation
            or result.outcome in {AttemptOutcome.INFRA_ERROR, AttemptOutcome.CANCELLED}
            for result in trial.results
        ):
            raise ScenarioInvalidTransition(
                "Evaluator trial contains a mismatch or execution error."
            )
        version = await self._next_version(
            agent_id, ScenarioRecordType.EVALUATOR_VERSION, evaluator_id
        )
        scene = await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.SCENE_VERSION,
            record_id=draft.scene_version_id,
            model_type=SceneVersion,
        )
        model = EvaluatorVersion(
            evaluator_version_id=f"{evaluator_id}:v{version}",
            evaluator_id=evaluator_id,
            agent_id=agent_id,
            version=version,
            source_draft_revision=draft_revision,
            name=draft.name,
            scene_version_id=draft.scene_version_id,
            kind=draft.kind,
            rule=draft.rule,
            rubric=draft.rubric,
            regex_pattern=draft.regex_pattern,
            hard_failure=draft.hard_failure,
            scene_name=scene.name,
            scene_user_task=scene.user_task,
            scene_pass_criteria=scene.pass_criteria,
            scene_hard_failure_conditions=scene.hard_failure_conditions,
            trial_report_id=trial.report_id,
            trial_dataset_version_id=trial.dataset_version_id,
            created_at=self._now(),
            created_by=actor.owner_id,
        )
        await self._append_published_model(
            model,
            record_id=model.evaluator_version_id,
            actor=actor,
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATOR_VERSION,
            asset_id=evaluator_id,
            version=version,
        )
        return model

    async def publish_evaluator_group(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        scene_version_id: str,
        draft_revisions: Mapping[str, int],
    ) -> EvaluatorGroupPublicationResult:
        self._require_admin(actor)
        scene = await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.SCENE_VERSION,
            record_id=scene_version_id,
            model_type=SceneVersion,
        )
        draft_records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATOR_DRAFT,
        )
        latest_drafts: dict[str, EvaluatorDraft] = {}
        for record in draft_records:
            draft = EvaluatorDraft.model_validate_json(record.payload_json)
            current = latest_drafts.get(draft.evaluator_id)
            if current is None or draft.revision > current.revision:
                latest_drafts[draft.evaluator_id] = draft
        drafts = sorted(
            (
                draft
                for draft in latest_drafts.values()
                if draft.scene_version_id == scene_version_id
            ),
            key=lambda item: item.evaluator_id,
        )
        current_revisions = {draft.evaluator_id: draft.revision for draft in drafts}
        if not drafts or current_revisions != dict(draft_revisions):
            raise ScenarioInvalidTransition(
                "Evaluator group request must include every current check revision."
            )

        trial_records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATOR_TRIAL,
        )
        latest_trials: dict[str, EvaluatorTrialReport] = {}
        for record in trial_records:
            if record.asset_id not in current_revisions:
                continue
            trial = EvaluatorTrialReport.model_validate_json(record.payload_json)
            if trial.evaluator_revision != current_revisions[record.asset_id]:
                continue
            current = latest_trials.get(record.asset_id)
            if current is None or trial.created_at > current.created_at:
                latest_trials[record.asset_id] = trial
        if set(latest_trials) != set(current_revisions):
            raise ScenarioInvalidTransition(
                "Every current evaluator check requires a current trial before publication."
            )

        dataset_ids = {trial.dataset_version_id for trial in latest_trials.values()}
        if len(dataset_ids) != 1:
            raise ScenarioInvalidTransition(
                "Evaluator group trials must use the same Dataset version."
            )
        sample_ids = [
            {result.sample_id for result in trial.results}
            for trial in latest_trials.values()
        ]
        if not sample_ids or any(items != sample_ids[0] for items in sample_ids[1:]):
            raise ScenarioInvalidTransition(
                "Evaluator group trials must use the same calibration samples."
            )
        for sample_id in sorted(sample_ids[0]):
            results = [
                next(
                    result
                    for result in latest_trials[draft.evaluator_id].results
                    if result.sample_id == sample_id
                )
                for draft in drafts
            ]
            if any(
                result.outcome in {AttemptOutcome.INFRA_ERROR, AttemptOutcome.CANCELLED}
                for result in results
            ):
                raise ScenarioInvalidTransition(
                    "Evaluator group trial contains an execution error."
                )
            expected_outcomes = {result.expected_outcome for result in results}
            if len(expected_outcomes) != 1:
                raise ScenarioInvalidTransition(
                    "Evaluator group trials must use the same human judgment."
                )
            combined_outcome = (
                AttemptOutcome.FAIL
                if any(result.outcome is AttemptOutcome.FAIL for result in results)
                else AttemptOutcome.PASS
            )
            if combined_outcome is not next(iter(expected_outcomes)):
                raise ScenarioInvalidTransition(
                    "Evaluator group combined judgment does not match human judgment."
                )

        version_records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATOR_VERSION,
        )
        existing_versions = [
            EvaluatorVersion.model_validate_json(record.payload_json)
            for record in version_records
        ]
        published: list[EvaluatorVersion] = []
        for draft in drafts:
            existing = next(
                (
                    version
                    for version in reversed(existing_versions)
                    if version.evaluator_id == draft.evaluator_id
                    and version.source_draft_revision == draft.revision
                ),
                None,
            )
            if existing is not None:
                published.append(existing)
                continue
            trial = latest_trials[draft.evaluator_id]
            version = await self._next_version(
                agent_id,
                ScenarioRecordType.EVALUATOR_VERSION,
                draft.evaluator_id,
            )
            model = EvaluatorVersion(
                evaluator_version_id=f"{draft.evaluator_id}:v{version}",
                evaluator_id=draft.evaluator_id,
                agent_id=agent_id,
                version=version,
                source_draft_revision=draft.revision,
                name=draft.name,
                scene_version_id=draft.scene_version_id,
                kind=draft.kind,
                rule=draft.rule,
                rubric=draft.rubric,
                regex_pattern=draft.regex_pattern,
                hard_failure=draft.hard_failure,
                scene_name=scene.name,
                scene_user_task=scene.user_task,
                scene_pass_criteria=scene.pass_criteria,
                scene_hard_failure_conditions=scene.hard_failure_conditions,
                trial_report_id=trial.report_id,
                trial_dataset_version_id=trial.dataset_version_id,
                created_at=self._now(),
                created_by=actor.owner_id,
            )
            await self._append_published_model(
                model,
                record_id=model.evaluator_version_id,
                actor=actor,
                agent_id=agent_id,
                record_type=ScenarioRecordType.EVALUATOR_VERSION,
                asset_id=draft.evaluator_id,
                version=version,
            )
            published.append(model)

        return EvaluatorGroupPublicationResult(
            scene_version_id=scene_version_id,
            evaluator_versions=tuple(published),
            check_count=len(published),
        )

    async def save_policy_draft(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        policy_id: str,
        expected_revision: int,
        name: str,
        bindings: tuple[PolicySceneBinding, ...],
    ) -> EvaluationPolicyDraft:
        self._require_manager(actor)
        draft = EvaluationPolicyDraft(
            policy_id=policy_id,
            agent_id=agent_id,
            revision=expected_revision + 1,
            name=name,
            bindings=bindings,
            updated_at=self._now(),
            updated_by=actor.owner_id,
        )
        await self._append_draft_model(
            draft,
            agent_id=agent_id,
            owner_id=actor.owner_id,
            record_type=ScenarioRecordType.POLICY_DRAFT,
            asset_id=policy_id,
            revision=draft.revision,
            expected_revision=expected_revision,
        )
        return draft

    async def publish_policy_version(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        policy_id: str,
        draft_revision: int,
    ) -> EvaluationPolicyVersion:
        self._require_admin(actor)
        draft = await self._draft_at_revision(
            agent_id=agent_id,
            record_type=ScenarioRecordType.POLICY_DRAFT,
            asset_id=policy_id,
            revision=draft_revision,
            model_type=EvaluationPolicyDraft,
        )
        await self._validate_policy_bindings(agent_id, draft.bindings)
        version = await self._next_version(
            agent_id, ScenarioRecordType.POLICY_VERSION, policy_id
        )
        model = EvaluationPolicyVersion(
            policy_version_id=f"{policy_id}:v{version}",
            policy_id=policy_id,
            agent_id=agent_id,
            version=version,
            source_draft_revision=draft_revision,
            name=draft.name,
            bindings=draft.bindings,
            created_at=self._now(),
            created_by=actor.owner_id,
        )
        await self._append_published_model(
            model,
            record_id=model.policy_version_id,
            actor=actor,
            agent_id=agent_id,
            record_type=ScenarioRecordType.POLICY_VERSION,
            asset_id=policy_id,
            version=version,
        )
        return model

    async def create_candidate_version(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        artifact: CandidateArtifact,
        runtime_project: CandidateProjectSource | None = None,
    ) -> CandidateVersion:
        self._require_manager(actor)
        if artifact.runtime_project_ref is not None:
            raise ScenarioInvalidTransition(
                "runtimeProjectRef is assigned by the server."
            )
        if runtime_project is not None:
            if not runtime_project.deployment_profile:
                raise ScenarioInvalidTransition(
                    "runtimeProject requires a frozen deploymentProfile."
                )
            try:
                generated_project = GeneratedProject(
                    name=runtime_project.name,
                    files=[
                        GeneratedFile(path=item.path, content=item.content)
                        for item in runtime_project.files
                    ],
                )
                validate_generated_project(generated_project)
                if self._project_attestation_verifier is None:
                    raise GeneratedAgentRuntimeError(
                        422,
                        "Formal evaluation requires a trusted server-generated project.",
                    )
                self._project_attestation_verifier(
                    generated_project,
                    actor.owner_id,
                    runtime_project.attestation,
                )
                if self._agent_identity_verifier is None:
                    raise GeneratedAgentRuntimeError(
                        422,
                        "Formal evaluation requires a trusted Agent identity.",
                    )
                await self._agent_identity_verifier(
                    actor,
                    agent_id,
                    runtime_project.deployment_profile,
                    runtime_project.agent_identity_attestation,
                )
                authorize_repository_agent_claim(agent_id)
            except GeneratedAgentRuntimeError as error:
                raise ScenarioInvalidTransition(error.detail) from error
        transaction_agent_id = ""
        if runtime_project is not None:
            await self._ensure_candidate_source(
                actor=actor,
                files=runtime_project.files,
            )
            transaction_agent_id = _candidate_transaction_agent_id(
                actor.owner_id,
                agent_id,
                artifact,
                runtime_project,
            )
            existing_transaction = await self._repository.get(
                agent_id=transaction_agent_id,
                record_type=ScenarioRecordType.CANDIDATE_TRANSACTION,
                record_id="transaction",
            )
            if existing_transaction is not None:
                candidate, snapshot = self._candidate_transaction_models(
                    existing_transaction
                )
                await self._materialize_candidate_transaction(
                    actor=actor,
                    candidate=candidate,
                    snapshot=snapshot,
                )
                return candidate
        candidate_id = self._id_factory("candidate")
        snapshot: CandidateProjectSnapshot | None = None
        if runtime_project is not None:
            project_snapshot_id = f"{candidate_id}:runtime-project"
            snapshot = CandidateProjectSnapshot(
                project_snapshot_id=project_snapshot_id,
                candidate_id=candidate_id,
                agent_id=agent_id,
                name=runtime_project.name,
                files=runtime_project.files,
                deployment_profile=runtime_project.deployment_profile,
                created_at=self._now(),
                created_by=actor.owner_id,
            )
            artifact = artifact.model_copy(
                update={"runtime_project_ref": project_snapshot_id}
            )
        existing_candidates = await self.list_models(
            agent_id=agent_id,
            record_type=ScenarioRecordType.CANDIDATE_VERSION,
            model_type=CandidateVersion,
            latest_by_asset=False,
        )
        environment_fingerprint = ""
        if runtime_project is not None:
            profile_json = json.dumps(
                runtime_project.deployment_profile,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            environment_fingerprint = (
                f"sha256:{hashlib.sha256(profile_json.encode('utf-8')).hexdigest()}"
            )
        model = CandidateVersion(
            candidate_id=candidate_id,
            agent_id=agent_id,
            version=max((item.version for item in existing_candidates), default=0) + 1,
            artifact=artifact,
            environment_fingerprint=environment_fingerprint,
            created_at=self._now(),
            created_by=actor.owner_id,
        )
        if snapshot is None:
            await self._append_model(
                model,
                record_id=candidate_id,
                agent_id=agent_id,
                owner_id=actor.owner_id,
                record_type=ScenarioRecordType.CANDIDATE_VERSION,
                asset_id=candidate_id,
                version=1,
            )
            return model

        authorize_repository_agent_claim(transaction_agent_id)
        transaction = ScenarioRecord(
            record_id="transaction",
            agent_id=transaction_agent_id,
            owner_id=actor.owner_id,
            record_type=ScenarioRecordType.CANDIDATE_TRANSACTION,
            asset_id="transaction",
            version=1,
            created_at=model.created_at,
            payload_json=json.dumps(
                {
                    "candidate": model.model_dump(mode="json", by_alias=True),
                    "projectSnapshot": snapshot.model_dump(
                        mode="json",
                        by_alias=True,
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        try:
            await self._repository.append(transaction)
        except ScenarioRecordConflict:
            existing_transaction = await self._repository.get(
                agent_id=transaction_agent_id,
                record_type=ScenarioRecordType.CANDIDATE_TRANSACTION,
                record_id="transaction",
            )
            if existing_transaction is None:
                raise
            winning_candidate, winning_snapshot = self._candidate_transaction_models(
                existing_transaction
            )
            await self._materialize_candidate_transaction(
                actor=actor,
                candidate=winning_candidate,
                snapshot=winning_snapshot,
            )
            return winning_candidate
        await self._materialize_candidate_transaction(
            actor=actor,
            candidate=model,
            snapshot=snapshot,
        )
        return model

    async def _ensure_candidate_source(
        self,
        *,
        actor: ScenarioActor,
        files: tuple[CandidateProjectFile, ...],
    ) -> None:
        marker_agent_id = _candidate_source_agent_id(actor.owner_id, files)
        existing = await self._repository.get(
            agent_id=marker_agent_id,
            record_type=ScenarioRecordType.CANDIDATE_SOURCE,
            record_id="governed",
        )
        if existing is not None:
            return
        authorize_repository_agent_claim(marker_agent_id)
        marker = ScenarioRecord(
            record_id="governed",
            agent_id=marker_agent_id,
            owner_id=actor.owner_id,
            record_type=ScenarioRecordType.CANDIDATE_SOURCE,
            asset_id="governed",
            version=1,
            created_at=self._now(),
            payload_json=json.dumps(
                {"sourceDigest": _candidate_source_digest(files)},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        try:
            await self._repository.append(marker)
        except ScenarioRecordConflict:
            # A concurrent identical request may have won the source sentinel.
            pass

    async def has_candidate_source(
        self,
        *,
        owner_id: str,
        files: tuple[CandidateProjectFile, ...],
    ) -> bool:
        """Return whether this actor previously governed the exact source."""

        record = await self._repository.get(
            agent_id=_candidate_source_agent_id(owner_id, files),
            record_type=ScenarioRecordType.CANDIDATE_SOURCE,
            record_id="governed",
        )
        return record is not None

    @staticmethod
    def _candidate_transaction_models(
        transaction: ScenarioRecord,
    ) -> tuple[CandidateVersion, CandidateProjectSnapshot]:
        try:
            value = json.loads(transaction.payload_json)
            return (
                CandidateVersion.model_validate(value["candidate"]),
                CandidateProjectSnapshot.model_validate(value["projectSnapshot"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ScenarioRecordConflict("Candidate transaction is invalid.") from error

    async def _materialize_candidate_transaction(
        self,
        *,
        actor: ScenarioActor,
        candidate: CandidateVersion,
        snapshot: CandidateProjectSnapshot,
    ) -> None:
        snapshot_record = ScenarioRecord(
            record_id=snapshot.project_snapshot_id,
            agent_id=candidate.agent_id,
            owner_id=actor.owner_id,
            record_type=ScenarioRecordType.CANDIDATE_PROJECT,
            asset_id=candidate.candidate_id,
            version=1,
            created_at=snapshot.created_at,
            payload_json=snapshot.model_dump_json(by_alias=True),
        )
        candidate_record = ScenarioRecord(
            record_id=candidate.candidate_id,
            agent_id=candidate.agent_id,
            owner_id=actor.owner_id,
            record_type=ScenarioRecordType.CANDIDATE_VERSION,
            asset_id=candidate.candidate_id,
            version=1,
            created_at=candidate.created_at,
            payload_json=candidate.model_dump_json(by_alias=True),
        )
        await self._repository.append(snapshot_record)
        await self._repository.append(candidate_record)

    async def get_candidate_runtime_project(
        self,
        *,
        agent_id: str,
        project_snapshot_id: str,
    ) -> CandidateProjectSnapshot:
        return await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.CANDIDATE_PROJECT,
            record_id=project_snapshot_id,
            model_type=CandidateProjectSnapshot,
        )

    async def get_candidate_version(
        self,
        *,
        agent_id: str,
        candidate_id: str,
    ) -> CandidateVersion:
        return await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.CANDIDATE_VERSION,
            record_id=candidate_id,
            model_type=CandidateVersion,
        )

    async def candidate_environment_fingerprint(
        self,
        *,
        agent_id: str,
        candidate_id: str,
    ) -> str:
        candidate = await self.get_candidate_version(
            agent_id=agent_id,
            candidate_id=candidate_id,
        )
        if candidate.environment_fingerprint:
            return candidate.environment_fingerprint
        project_ref = candidate.artifact.runtime_project_ref
        if not project_ref:
            return ""
        snapshot = await self.get_candidate_runtime_project(
            agent_id=agent_id,
            project_snapshot_id=project_ref,
        )
        if not snapshot.deployment_profile:
            return ""
        payload = json.dumps(
            snapshot.deployment_profile,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"

    async def get_scene_version(
        self,
        *,
        agent_id: str,
        scene_version_id: str,
    ) -> SceneVersion:
        return await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.SCENE_VERSION,
            record_id=scene_version_id,
            model_type=SceneVersion,
        )

    async def get_dataset_version(
        self,
        *,
        agent_id: str,
        dataset_version_id: str,
    ) -> DatasetVersion:
        return await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.DATASET_VERSION,
            record_id=dataset_version_id,
            model_type=DatasetVersion,
        )

    async def get_evaluator_version(
        self,
        *,
        agent_id: str,
        evaluator_version_id: str,
    ) -> EvaluatorVersion:
        evaluator = await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATOR_VERSION,
            record_id=evaluator_version_id,
            model_type=EvaluatorVersion,
        )
        scene = await self.get_scene_version(
            agent_id=agent_id,
            scene_version_id=evaluator.scene_version_id,
        )
        return evaluator.model_copy(
            update={
                "scene_name": scene.name,
                "scene_user_task": scene.user_task,
                "scene_pass_criteria": scene.pass_criteria,
                "scene_hard_failure_conditions": scene.hard_failure_conditions,
            }
        )

    async def get_policy_version(
        self,
        *,
        agent_id: str,
        policy_version_id: str,
    ) -> EvaluationPolicyVersion:
        return await self._record_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.POLICY_VERSION,
            record_id=policy_version_id,
            model_type=EvaluationPolicyVersion,
        )

    async def list_models(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        model_type: type[_ModelT],
        latest_by_asset: bool,
    ) -> tuple[_ModelT, ...]:
        records = await self._repository.list(
            agent_id=agent_id,
            record_type=record_type,
        )
        if not latest_by_asset:
            return tuple(
                model_type.model_validate_json(record.payload_json)
                for record in records
            )
        latest: dict[str, tuple[int, _ModelT]] = {}
        for record in records:
            current = latest.get(record.asset_id)
            if current is None or record.version > current[0]:
                latest[record.asset_id] = (
                    record.version,
                    model_type.model_validate_json(record.payload_json),
                )
        return tuple(
            item[1] for item in sorted(latest.values(), key=lambda item: item[0])
        )

    async def _validate_policy_bindings(
        self,
        agent_id: str,
        bindings: tuple[PolicySceneBinding, ...],
    ) -> None:
        latest_scenes = await self.list_models(
            agent_id=agent_id,
            record_type=ScenarioRecordType.SCENE_VERSION,
            model_type=SceneVersion,
            latest_by_asset=True,
        )
        enabled_scene_ids = {
            scene.scene_version_id for scene in latest_scenes if scene.enabled
        }
        bound_scene_ids = {binding.scene_version_id for binding in bindings}
        if bound_scene_ids != enabled_scene_ids:
            missing = sorted(enabled_scene_ids - bound_scene_ids)
            extra = sorted(bound_scene_ids - enabled_scene_ids)
            raise ScenarioInvalidTransition(
                "Policy must bind every enabled latest Scene exactly once; "
                f"missing={missing}, extra={extra}."
            )
        for binding in bindings:
            scene = await self._record_model(
                agent_id=agent_id,
                record_type=ScenarioRecordType.SCENE_VERSION,
                record_id=binding.scene_version_id,
                model_type=SceneVersion,
            )
            if scene.requirement is not binding.requirement:
                raise ScenarioInvalidTransition(
                    "Policy requirement must match the published scene."
                )
            dataset = await self._record_model(
                agent_id=agent_id,
                record_type=ScenarioRecordType.DATASET_VERSION,
                record_id=binding.dataset_version_id,
                model_type=DatasetVersion,
            )
            if scene.linked_dataset_ids and dataset.dataset_id not in set(
                scene.linked_dataset_ids
            ):
                raise ScenarioInvalidTransition(
                    "Policy Dataset is not linked by the published Scene."
                )
            if not any(
                case.scene_version_id == binding.scene_version_id
                for case in dataset.cases
            ):
                raise ScenarioInvalidTransition(
                    "Policy Dataset has no Case for the bound Scene."
                )
            evaluators: list[EvaluatorVersion] = []
            for evaluator_version_id in binding.evaluator_version_ids:
                evaluator = await self._record_model(
                    agent_id=agent_id,
                    record_type=ScenarioRecordType.EVALUATOR_VERSION,
                    record_id=evaluator_version_id,
                    model_type=EvaluatorVersion,
                )
                if evaluator.scene_version_id != binding.scene_version_id:
                    raise ScenarioInvalidTransition(
                        "Policy Evaluator belongs to another Scene."
                    )
                evaluators.append(evaluator)
            if not any(
                evaluator.hard_failure or evaluator.kind is EvaluatorKind.LLM_RUBRIC
                for evaluator in evaluators
            ):
                raise ScenarioInvalidTransition(
                    "Policy Scene requires an Evaluator for hard failure conditions."
                )

    async def _append_feedback_revision(
        self,
        actor: ScenarioActor,
        current: FeedbackCandidateVersion,
        **updates: object,
    ) -> FeedbackCandidateVersion:
        revision = current.revision + 1
        model = current.model_copy(
            update={
                **updates,
                "revision": revision,
                "created_at": self._now(),
                "created_by": actor.owner_id,
            }
        )
        await self._append_model(
            model,
            record_id=f"{model.candidate_id}:{revision}",
            agent_id=model.agent_id,
            owner_id=actor.owner_id,
            record_type=ScenarioRecordType.FEEDBACK_CANDIDATE,
            asset_id=model.candidate_id,
            version=revision,
        )
        return model

    async def _merged_feedback_lineage(
        self,
        *,
        agent_id: str,
        target_candidate_id: str,
    ) -> tuple[str, ...]:
        records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.FEEDBACK_CANDIDATE,
        )
        latest: dict[str, FeedbackCandidateVersion] = {}
        for record in records:
            item = FeedbackCandidateVersion.model_validate_json(record.payload_json)
            current = latest.get(item.candidate_id)
            if current is None or item.revision > current.revision:
                latest[item.candidate_id] = item
        lineage = {target_candidate_id}
        changed = True
        while changed:
            changed = False
            for item in latest.values():
                if (
                    item.decision is FeedbackDecision.MERGED
                    and item.target_candidate_id in lineage
                    and item.candidate_id not in lineage
                ):
                    lineage.add(item.candidate_id)
                    changed = True
        return tuple(sorted(lineage))

    async def _feedback_at_revision(
        self,
        agent_id: str,
        candidate_id: str,
        revision: int,
    ) -> FeedbackCandidateVersion:
        latest = await self._latest_model(
            agent_id=agent_id,
            record_type=ScenarioRecordType.FEEDBACK_CANDIDATE,
            asset_id=candidate_id,
            model_type=FeedbackCandidateVersion,
        )
        if latest.revision != revision:
            raise ScenarioRecordConflict(
                f"Feedback candidate is at revision {latest.revision}, not {revision}."
            )
        return latest

    @staticmethod
    def _require_feedback_open(candidate: FeedbackCandidateVersion) -> None:
        if candidate.decision in {
            FeedbackDecision.REJECTED,
            FeedbackDecision.MERGED,
            FeedbackDecision.CONVERTED,
        }:
            raise ScenarioInvalidTransition("Feedback candidate is already closed.")

    async def _draft_at_revision(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
        revision: int,
        model_type: type[_ModelT],
    ) -> _ModelT:
        return await self._record_model(
            agent_id=agent_id,
            record_type=record_type,
            record_id=f"{asset_id}:{revision}",
            model_type=model_type,
        )

    async def _record_model(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        record_id: str,
        model_type: type[_ModelT],
    ) -> _ModelT:
        record = await self._repository.get(
            agent_id=agent_id,
            record_type=record_type,
            record_id=record_id,
        )
        if record is None:
            raise ScenarioNotFound(f"Record {record_id!r} was not found.")
        return model_type.model_validate_json(record.payload_json)

    async def _latest_model(
        self,
        *,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
        model_type: type[_ModelT],
    ) -> _ModelT:
        record = await self._repository.latest_version(
            agent_id=agent_id,
            record_type=record_type,
            asset_id=asset_id,
        )
        if record is None:
            raise ScenarioNotFound(f"Asset {asset_id!r} was not found.")
        return model_type.model_validate_json(record.payload_json)

    async def _next_version(
        self,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
    ) -> int:
        latest = await self._repository.latest_version(
            agent_id=agent_id,
            record_type=record_type,
            asset_id=asset_id,
        )
        return 1 if latest is None else latest.version + 1

    async def _append_draft_model(
        self,
        model: BaseModel,
        *,
        agent_id: str,
        owner_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
        revision: int,
        expected_revision: int,
    ) -> None:
        record = self._record(
            model,
            record_id=f"{asset_id}:{revision}",
            agent_id=agent_id,
            owner_id=owner_id,
            record_type=record_type,
            asset_id=asset_id,
            version=revision,
        )
        await self._repository.append_draft(
            record,
            expected_revision=expected_revision,
        )

    async def _append_published_model(
        self,
        model: BaseModel,
        *,
        record_id: str,
        actor: ScenarioActor,
        agent_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
        version: int,
    ) -> None:
        await self._append_model(
            model,
            record_id=record_id,
            agent_id=agent_id,
            owner_id=actor.owner_id,
            record_type=record_type,
            asset_id=asset_id,
            version=version,
        )

    async def _append_model(
        self,
        model: BaseModel,
        *,
        record_id: str,
        agent_id: str,
        owner_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
        version: int,
    ) -> None:
        await self._repository.append(
            self._record(
                model,
                record_id=record_id,
                agent_id=agent_id,
                owner_id=owner_id,
                record_type=record_type,
                asset_id=asset_id,
                version=version,
            )
        )

    def _record(
        self,
        model: BaseModel,
        *,
        record_id: str,
        agent_id: str,
        owner_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
        version: int,
    ) -> ScenarioRecord:
        return ScenarioRecord(
            record_id=record_id,
            agent_id=agent_id,
            owner_id=owner_id,
            record_type=record_type,
            asset_id=asset_id,
            version=version,
            created_at=self._now(),
            payload_json=model.model_dump_json(by_alias=True),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Scenario evaluation clock must return an aware timestamp."
            )
        return value

    @staticmethod
    def _require_manager(actor: ScenarioActor) -> None:
        if actor.role not in {StudioRole.ADMIN, StudioRole.DEVELOPER}:
            raise ScenarioForbidden("Developer or Admin role is required.")

    @staticmethod
    def _require_admin(actor: ScenarioActor) -> None:
        if actor.role is not StudioRole.ADMIN:
            raise ScenarioForbidden("Admin role is required to publish standards.")
