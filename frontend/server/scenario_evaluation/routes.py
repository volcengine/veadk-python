"""FastAPI routes for the scenario-evaluation bounded context."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypeVar

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from frontend.server.scenario_evaluation.errors import (
    ScenarioEvaluationRunning,
    ScenarioForbidden,
    ScenarioInvalidTransition,
    ScenarioNotFound,
    ScenarioUnavailable,
)
from frontend.server.scenario_evaluation.models import (
    CandidateArtifact,
    CandidateProjectSource,
    CandidateVersion,
    DatasetCase,
    DatasetDraft,
    DatasetVersion,
    EvaluationPolicyDraft,
    EvaluationPolicyVersion,
    EvaluationRequirement,
    EvaluatorDraft,
    EvaluatorKind,
    EvaluatorTrialReport,
    EvaluatorTrialSample,
    EvaluatorVersion,
    FeedbackCandidateVersion,
    FeedbackSource,
    PolicySceneBinding,
    RedactionStatus,
    ScenarioActor,
    ScenarioRecordType,
    SceneDraft,
    SceneVersion,
)
from frontend.server.scenario_evaluation.executor import EvidenceEvaluator
from frontend.server.scenario_evaluation.publishing import PublishCandidateService
from frontend.server.scenario_evaluation.repository import ScenarioRecordConflict
from frontend.server.scenario_evaluation.run_service import FormalEvaluationManager
from frontend.server.scenario_evaluation.service import ScenarioEvaluationService

_ResultT = TypeVar("_ResultT")


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class _RequestModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class _CreateCandidateRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    artifact: CandidateArtifact
    runtime_project: CandidateProjectSource | None = None


class _ReviewFeedbackRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    input: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)
    comment: str = ""
    labels: tuple[str, ...] = ()


class _RejectFeedbackRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1)


class _MergeFeedbackRequest(_RejectFeedbackRequest):
    target_candidate_id: str = Field(min_length=1)


class _ConvertFeedbackRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    dataset_id: str = Field(min_length=1)
    expected_dataset_revision: int = Field(ge=0)
    dataset_name: str = Field(min_length=1)
    scene_version_id: str = Field(min_length=1)
    pass_criteria: tuple[str, ...] = Field(min_length=1)
    redaction_status: RedactionStatus = RedactionStatus.PENDING


class _SaveSceneRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    user_task: str
    pass_criteria: tuple[str, ...]
    hard_failure_conditions: tuple[str, ...]
    owner_id: str
    linked_dataset_ids: tuple[str, ...] = ()
    enabled: bool = True
    requirement: EvaluationRequirement


class _PublishDraftRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    draft_revision: int = Field(ge=1)


class _SaveDatasetRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    name: str = Field(min_length=1)
    cases: tuple[DatasetCase, ...] = Field(min_length=1)


class _SaveEvaluatorRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    evaluator_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    name: str = Field(min_length=1)
    scene_version_id: str = Field(min_length=1)
    kind: EvaluatorKind
    rule: str = ""
    rubric: str = ""
    hard_failure: bool = False


class _RecommendEvaluatorRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    scene_version_id: str = Field(min_length=1)


class _TrialEvaluatorRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    dataset_version_id: str = Field(min_length=1)
    samples: tuple[EvaluatorTrialSample, ...] = Field(min_length=1)


class _EvaluatorGroupDraftRef(_RequestModel):
    evaluator_id: str = Field(min_length=1)
    draft_revision: int = Field(ge=1)


class _PublishEvaluatorGroupRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    scene_version_id: str = Field(min_length=1)
    drafts: tuple[_EvaluatorGroupDraftRef, ...] = Field(min_length=1)


class _SavePolicyRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    name: str = Field(min_length=1)
    bindings: tuple[PolicySceneBinding, ...] = Field(min_length=1)


class _StartRunRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    policy_version_id: str = Field(min_length=1)
    environment_fingerprint: str = Field(min_length=1)


class _RetryAttemptRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    scene_version_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    target: Literal["candidate", "baseline"]
    attempt_index: int = Field(ge=1, le=3)


class _AgentRequest(_RequestModel):
    agent_id: str = Field(min_length=1)


class _PreparePublishRequest(_RequestModel):
    agent_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    policy_version_id: str | None = None
    environment_fingerprint: str = Field(min_length=1)
    permission_fingerprint: str | None = None
    second_confirmation: bool = False
    reason: str = ""
    idempotency_key: str = Field(min_length=1)


def _dump(model: Any) -> Any:
    if isinstance(model, BaseModel):
        return model.model_dump(mode="json", by_alias=True)
    if isinstance(model, tuple):
        return [_dump(item) for item in model]
    if isinstance(model, list):
        return [_dump(item) for item in model]
    if isinstance(model, dict):
        return {key: _dump(value) for key, value in model.items()}
    return model


async def _domain_call(awaitable: Awaitable[_ResultT]) -> _ResultT:
    try:
        return await awaitable
    except ScenarioForbidden as error:
        raise _http_error(403, "forbidden", error) from error
    except ScenarioNotFound as error:
        raise _http_error(404, "not_found", error) from error
    except ScenarioEvaluationRunning as error:
        raise _http_error(409, "evaluation_running", error) from error
    except ScenarioRecordConflict as error:
        raise _http_error(409, "conflict", error) from error
    except ScenarioInvalidTransition as error:
        raise _http_error(422, "invalid_transition", error) from error
    except ScenarioUnavailable as error:
        raise _http_error(503, "unavailable", error) from error


def _http_error(status_code: int, code: str, error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(error)},
    )


def mount_routes(
    app: Any,
    *,
    service: ScenarioEvaluationService,
    run_manager: FormalEvaluationManager,
    publisher: PublishCandidateService,
    actor_resolver: Callable[[Request], ScenarioActor],
    evidence_evaluator: EvidenceEvaluator | None = None,
) -> None:
    router = APIRouter(prefix="/web/scenario-evaluation")

    @router.get("/workspace")
    async def workspace(
        request: Request,
        agentId: str = Query(..., min_length=1),
    ) -> dict[str, Any]:
        actor_resolver(request)
        feedback = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.FEEDBACK_CANDIDATE,
                model_type=FeedbackCandidateVersion,
                latest_by_asset=True,
            )
        )
        scene_drafts = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.SCENE_DRAFT,
                model_type=SceneDraft,
                latest_by_asset=True,
            )
        )
        scenes = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.SCENE_VERSION,
                model_type=SceneVersion,
                latest_by_asset=False,
            )
        )
        dataset_drafts = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.DATASET_DRAFT,
                model_type=DatasetDraft,
                latest_by_asset=True,
            )
        )
        datasets = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.DATASET_VERSION,
                model_type=DatasetVersion,
                latest_by_asset=False,
            )
        )
        evaluator_drafts = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.EVALUATOR_DRAFT,
                model_type=EvaluatorDraft,
                latest_by_asset=True,
            )
        )
        evaluator_trials = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.EVALUATOR_TRIAL,
                model_type=EvaluatorTrialReport,
                latest_by_asset=False,
            )
        )
        evaluators = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.EVALUATOR_VERSION,
                model_type=EvaluatorVersion,
                latest_by_asset=False,
            )
        )
        policy_drafts = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.POLICY_DRAFT,
                model_type=EvaluationPolicyDraft,
                latest_by_asset=True,
            )
        )
        policies = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.POLICY_VERSION,
                model_type=EvaluationPolicyVersion,
                latest_by_asset=False,
            )
        )
        candidates = await _domain_call(
            service.list_models(
                agent_id=agentId,
                record_type=ScenarioRecordType.CANDIDATE_VERSION,
                model_type=CandidateVersion,
                latest_by_asset=False,
            )
        )
        runs = await _domain_call(run_manager.list_runs(agent_id=agentId))
        badcases = await _domain_call(run_manager.list_badcases(agent_id=agentId))
        published = await _domain_call(publisher.latest_published(agent_id=agentId))
        recovery_issues = await _domain_call(
            publisher.list_recovery_issues(agent_id=agentId)
        )
        return _dump(
            {
                "agentId": agentId,
                "feedbackCandidates": feedback,
                "sceneDrafts": scene_drafts,
                "scenes": scenes,
                "datasetDrafts": dataset_drafts,
                "datasets": datasets,
                "evaluatorDrafts": evaluator_drafts,
                "evaluatorTrials": evaluator_trials,
                "evaluators": evaluators,
                "policyDrafts": policy_drafts,
                "policies": policies,
                "candidates": candidates,
                "runs": runs,
                "badcases": badcases,
                "publishRecoveryIssues": recovery_issues,
                "publishedVersion": published,
            }
        )

    @router.post("/feedback-candidates")
    async def create_feedback(source: FeedbackSource, request: Request) -> Any:
        return _dump(
            await _domain_call(
                service.create_feedback_candidate(actor_resolver(request), source)
            )
        )

    @router.post("/feedback-candidates/{candidate_id}/review")
    async def review_feedback(
        candidate_id: str,
        body: _ReviewFeedbackRequest,
        request: Request,
    ) -> Any:
        return _dump(
            await _domain_call(
                service.review_feedback_candidate(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    candidate_id=candidate_id,
                    expected_revision=body.expected_revision,
                    input=body.input,
                    expected_output=body.expected_output,
                    comment=body.comment,
                    labels=body.labels,
                )
            )
        )

    @router.post("/feedback-candidates/{candidate_id}/reject")
    async def reject_feedback(
        candidate_id: str,
        body: _RejectFeedbackRequest,
        request: Request,
    ) -> Any:
        return _dump(
            await _domain_call(
                service.reject_feedback_candidate(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    candidate_id=candidate_id,
                    expected_revision=body.expected_revision,
                    reason=body.reason,
                )
            )
        )

    @router.post("/feedback-candidates/{candidate_id}/merge")
    async def merge_feedback(
        candidate_id: str,
        body: _MergeFeedbackRequest,
        request: Request,
    ) -> Any:
        return _dump(
            await _domain_call(
                service.merge_feedback_candidate(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    candidate_id=candidate_id,
                    expected_revision=body.expected_revision,
                    target_candidate_id=body.target_candidate_id,
                    reason=body.reason,
                )
            )
        )

    @router.post("/feedback-candidates/{candidate_id}/convert")
    async def convert_feedback(
        candidate_id: str,
        body: _ConvertFeedbackRequest,
        request: Request,
    ) -> Any:
        converted, dataset = await _domain_call(
            service.convert_feedback_candidate(
                actor_resolver(request),
                agent_id=body.agent_id,
                candidate_id=candidate_id,
                expected_revision=body.expected_revision,
                dataset_id=body.dataset_id,
                expected_dataset_revision=body.expected_dataset_revision,
                dataset_name=body.dataset_name,
                scene_version_id=body.scene_version_id,
                pass_criteria=body.pass_criteria,
                redaction_status=body.redaction_status,
            )
        )
        return _dump({"feedbackCandidate": converted, "datasetDraft": dataset})

    @router.post("/scene-drafts")
    async def save_scene(body: _SaveSceneRequest, request: Request) -> Any:
        return _dump(
            await _domain_call(
                service.save_scene_draft(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    scene_id=body.scene_id,
                    expected_revision=body.expected_revision,
                    name=body.name,
                    description=body.description,
                    user_task=body.user_task,
                    pass_criteria=body.pass_criteria,
                    hard_failure_conditions=body.hard_failure_conditions,
                    owner_id=body.owner_id,
                    requirement=body.requirement,
                    linked_dataset_ids=body.linked_dataset_ids,
                    enabled=body.enabled,
                )
            )
        )

    @router.post("/scene-versions/publish")
    async def publish_scene(body: _PublishDraftRequest, request: Request) -> Any:
        return _dump(
            await _domain_call(
                service.publish_scene_version(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    scene_id=body.asset_id,
                    draft_revision=body.draft_revision,
                )
            )
        )

    @router.post("/dataset-drafts")
    async def save_dataset(body: _SaveDatasetRequest, request: Request) -> Any:
        return _dump(
            await _domain_call(
                service.save_dataset_draft(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    dataset_id=body.dataset_id,
                    expected_revision=body.expected_revision,
                    name=body.name,
                    cases=body.cases,
                )
            )
        )

    @router.post("/dataset-versions/publish")
    async def publish_dataset(body: _PublishDraftRequest, request: Request) -> Any:
        return _dump(
            await _domain_call(
                service.publish_dataset_version(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    dataset_id=body.asset_id,
                    draft_revision=body.draft_revision,
                )
            )
        )

    @router.post("/evaluator-drafts")
    async def save_evaluator(body: _SaveEvaluatorRequest, request: Request) -> Any:
        return _dump(
            await _domain_call(
                service.save_evaluator_draft(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    evaluator_id=body.evaluator_id,
                    expected_revision=body.expected_revision,
                    name=body.name,
                    scene_version_id=body.scene_version_id,
                    kind=body.kind,
                    rule=body.rule,
                    rubric=body.rubric,
                    hard_failure=body.hard_failure,
                )
            )
        )

    @router.post("/evaluator-drafts/recommend")
    async def recommend_evaluators(
        body: _RecommendEvaluatorRequest,
        request: Request,
    ) -> Any:
        return _dump(
            await _domain_call(
                service.recommend_evaluator_drafts(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    scene_version_id=body.scene_version_id,
                )
            )
        )

    @router.post("/evaluator-drafts/{evaluator_id}/trial")
    async def trial_evaluator(
        evaluator_id: str,
        body: _TrialEvaluatorRequest,
        request: Request,
    ) -> Any:
        if evidence_evaluator is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "unavailable",
                    "message": "Evaluator trial service is unavailable.",
                },
            )
        return _dump(
            await _domain_call(
                service.trial_evaluator_draft(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    evaluator_id=evaluator_id,
                    expected_revision=body.expected_revision,
                    dataset_version_id=body.dataset_version_id,
                    samples=body.samples,
                    evaluator=evidence_evaluator,
                )
            )
        )

    @router.post("/evaluator-versions/publish")
    async def publish_evaluator(
        body: _PublishDraftRequest,
        request: Request,
    ) -> Any:
        return _dump(
            await _domain_call(
                service.publish_evaluator_version(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    evaluator_id=body.asset_id,
                    draft_revision=body.draft_revision,
                )
            )
        )

    @router.post("/evaluator-groups/publish")
    async def publish_evaluator_group(
        body: _PublishEvaluatorGroupRequest,
        request: Request,
    ) -> Any:
        draft_revisions = {
            item.evaluator_id: item.draft_revision for item in body.drafts
        }
        if len(draft_revisions) != len(body.drafts):
            raise HTTPException(status_code=422, detail="Duplicate evaluator id.")
        return _dump(
            await _domain_call(
                service.publish_evaluator_group(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    scene_version_id=body.scene_version_id,
                    draft_revisions=draft_revisions,
                )
            )
        )

    @router.post("/policy-drafts")
    async def save_policy(body: _SavePolicyRequest, request: Request) -> Any:
        return _dump(
            await _domain_call(
                service.save_policy_draft(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    policy_id=body.policy_id,
                    expected_revision=body.expected_revision,
                    name=body.name,
                    bindings=body.bindings,
                )
            )
        )

    @router.post("/policy-versions/publish")
    async def publish_policy(body: _PublishDraftRequest, request: Request) -> Any:
        return _dump(
            await _domain_call(
                service.publish_policy_version(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    policy_id=body.asset_id,
                    draft_revision=body.draft_revision,
                )
            )
        )

    @router.post("/candidates")
    async def create_candidate(
        body: _CreateCandidateRequest,
        request: Request,
    ) -> Any:
        return _dump(
            await _domain_call(
                service.create_candidate_version(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    artifact=body.artifact,
                    runtime_project=body.runtime_project,
                )
            )
        )

    @router.post("/runs")
    async def start_run(body: _StartRunRequest, request: Request) -> Any:
        return _dump(
            await _domain_call(
                run_manager.start(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    candidate_id=body.candidate_id,
                    policy_version_id=body.policy_version_id,
                    environment_fingerprint=body.environment_fingerprint,
                )
            )
        )

    @router.get("/runs/{evaluation_id}")
    async def get_run(
        evaluation_id: str,
        request: Request,
        agentId: str = Query(..., min_length=1),
    ) -> Any:
        actor_resolver(request)
        return _dump(
            await _domain_call(
                run_manager.get(agent_id=agentId, evaluation_id=evaluation_id)
            )
        )

    @router.post("/runs/{evaluation_id}/cancel")
    async def cancel_run(
        evaluation_id: str,
        body: _AgentRequest,
        request: Request,
    ) -> Any:
        return _dump(
            await _domain_call(
                run_manager.cancel(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    evaluation_id=evaluation_id,
                )
            )
        )

    @router.post("/runs/{evaluation_id}/attempts/retry")
    async def retry_invalid_attempt(
        evaluation_id: str,
        body: _RetryAttemptRequest,
        request: Request,
    ) -> Any:
        return _dump(
            await _domain_call(
                run_manager.retry_invalid_attempt(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    evaluation_id=evaluation_id,
                    scene_version_id=body.scene_version_id,
                    case_id=body.case_id,
                    target=body.target,
                    attempt_index=body.attempt_index,
                )
            )
        )

    @router.post("/publish-intents/prepare")
    async def prepare_publish(
        body: _PreparePublishRequest,
        request: Request,
    ) -> Any:
        return _dump(
            await _domain_call(
                publisher.prepare(
                    actor_resolver(request),
                    agent_id=body.agent_id,
                    candidate_id=body.candidate_id,
                    policy_version_id=body.policy_version_id,
                    environment_fingerprint=body.environment_fingerprint,
                    second_confirmation=body.second_confirmation,
                    reason=body.reason,
                    idempotency_key=body.idempotency_key,
                )
            )
        )

    @router.post("/publish-intents/{intent_id}/reconcile")
    async def reconcile_publish(
        intent_id: str,
        body: _AgentRequest,
        request: Request,
    ) -> Any:
        intent, published = await _domain_call(
            publisher.reconcile_succeeded(
                actor_resolver(request),
                agent_id=body.agent_id,
                intent_id=intent_id,
            )
        )
        return _dump({"intent": intent, "publishedVersion": published})

    @router.get("/publish-audits")
    async def publish_audits(
        request: Request,
        agentId: str = Query(..., min_length=1),
        intentId: str | None = Query(default=None),
    ) -> Any:
        actor_resolver(request)
        return _dump(
            await _domain_call(
                publisher.list_audits(agent_id=agentId, intent_id=intentId)
            )
        )

    @router.get("/publish-recovery-issues")
    async def publish_recovery_issues(
        request: Request,
        agentId: str = Query(..., min_length=1),
    ) -> Any:
        actor_resolver(request)
        return _dump(
            await _domain_call(publisher.list_recovery_issues(agent_id=agentId))
        )

    app.include_router(router)
