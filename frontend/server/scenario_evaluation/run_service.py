"""Formal evaluation task lifecycle and Badcase reconciliation."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from frontend.server.scenario_evaluation.errors import (
    ScenarioForbidden,
    ScenarioInvalidTransition,
    ScenarioNotFound,
)
from frontend.server.scenario_evaluation.executor import (
    EvaluationExecutionPlan,
    FormalEvaluationExecutor,
    SceneExecutionPlan,
)
from frontend.server.scenario_evaluation.models import (
    AttemptOutcome,
    BadcaseStatus,
    BadcaseVersion,
    CandidateVersion,
    CaseOutcome,
    EvaluationDependencies,
    EvaluationPolicyVersion,
    EvaluationRunStatus,
    EvaluationRunVersion,
    InvalidAttemptEvidence,
    PolicySceneBinding,
    PublishedVersion,
    QualityRecommendationRecord,
    ScenarioActor,
    ScenarioRecord,
    ScenarioRecordType,
)
from frontend.server.scenario_evaluation.recommendation import (
    aggregate_case,
    aggregate_quality_recommendation,
    dependency_fingerprint,
)
from frontend.server.scenario_evaluation.repository import (
    ScenarioEvaluationRepository,
)
from frontend.server.scenario_evaluation.service import ScenarioEvaluationService
from veadk.cli.studio_rbac import StudioRole


def _default_id_factory(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


@dataclass(frozen=True)
class _RunContext:
    run: EvaluationRunVersion
    plan: EvaluationExecutionPlan
    policy: EvaluationPolicyVersion


class FormalEvaluationManager:
    def __init__(
        self,
        repository: ScenarioEvaluationRepository,
        asset_service: ScenarioEvaluationService,
        executor: FormalEvaluationExecutor,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._repository = repository
        self._assets = asset_service
        self._executor = executor
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or _default_id_factory
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._owned_run_ids: set[str] = set()
        self._cancel_requested: set[str] = set()
        self._retry_locks: dict[str, asyncio.Lock] = {}

    async def start(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        candidate_id: str,
        policy_version_id: str,
        environment_fingerprint: str,
        selected_case_ids: tuple[str, ...] | None = None,
    ) -> EvaluationRunVersion:
        self._require_admin(actor)
        candidate = await self._assets.get_candidate_version(
            agent_id=agent_id,
            candidate_id=candidate_id,
        )
        expected_environment_fingerprint = (
            await self._assets.candidate_environment_fingerprint(
                agent_id=agent_id,
                candidate_id=candidate_id,
            )
        )
        if (
            expected_environment_fingerprint
            and environment_fingerprint != expected_environment_fingerprint
        ):
            raise ScenarioInvalidTransition(
                "Evaluation environment does not match the frozen Candidate."
            )
        published_record = await self._repository.latest_version(
            agent_id=agent_id,
            record_type=ScenarioRecordType.PUBLISHED_VERSION,
            asset_id="online",
        )
        published = (
            PublishedVersion.model_validate_json(published_record.payload_json)
            if published_record is not None
            else None
        )
        baseline = (
            await self._assets.get_candidate_version(
                agent_id=agent_id,
                candidate_id=published.candidate_id,
            )
            if published is not None
            else None
        )
        policy = await self._assets.get_policy_version(
            agent_id=agent_id,
            policy_version_id=policy_version_id,
        )
        scenes: list[SceneExecutionPlan] = []
        all_case_ids: list[str] = []
        for binding in policy.bindings:
            dataset = await self._assets.get_dataset_version(
                agent_id=agent_id,
                dataset_version_id=binding.dataset_version_id,
            )
            evaluators = tuple(
                [
                    await self._assets.get_evaluator_version(
                        agent_id=agent_id,
                        evaluator_version_id=evaluator_version_id,
                    )
                    for evaluator_version_id in binding.evaluator_version_ids
                ]
            )
            scene_cases = tuple(
                item
                for item in dataset.cases
                if item.scene_version_id == binding.scene_version_id
            )
            all_case_ids.extend(item.case_id for item in scene_cases)
            scenes.append(
                SceneExecutionPlan(
                    scene_version_id=binding.scene_version_id,
                    requirement=binding.requirement,
                    cases=scene_cases,
                    evaluators=evaluators,
                )
            )
        if selected_case_ids is not None and (
            len(selected_case_ids) != len(all_case_ids)
            or set(selected_case_ids) != set(all_case_ids)
        ):
            raise ScenarioInvalidTransition(
                "Formal evaluation must run the complete published policy."
            )

        dependencies = EvaluationDependencies(
            candidate_id=candidate_id,
            baseline_version_id=(
                published.published_version_id if published is not None else None
            ),
            scene_version_ids=tuple(item.scene_version_id for item in scenes),
            dataset_version_ids=tuple(
                item.dataset_version_id for item in policy.bindings
            ),
            evaluator_version_ids=tuple(
                evaluator_id
                for item in policy.bindings
                for evaluator_id in item.evaluator_version_ids
            ),
            policy_version_id=policy_version_id,
            environment_fingerprint=environment_fingerprint,
        )
        evaluation_id = self._id_factory("evaluation")
        now = self._now()
        queued = EvaluationRunVersion(
            evaluation_id=evaluation_id,
            agent_id=agent_id,
            revision=1,
            status=EvaluationRunStatus.QUEUED,
            candidate_id=candidate_id,
            baseline_version_id=(
                published.published_version_id if published is not None else None
            ),
            policy_version_id=policy_version_id,
            dependencies=dependencies,
            created_at=now,
            updated_at=now,
            created_by=actor.owner_id,
        )
        await self._append_run(queued)
        context = _RunContext(
            run=queued,
            plan=EvaluationExecutionPlan(
                candidate=candidate,
                baseline=baseline,
                scenes=tuple(scenes),
            ),
            policy=policy,
        )
        await self._mark_badcases_verifying(context)
        task = asyncio.create_task(
            self._execute(context),
            name=f"scenario-evaluation-{evaluation_id}",
        )
        self._tasks[evaluation_id] = task
        self._owned_run_ids.add(evaluation_id)
        task.add_done_callback(
            lambda completed, run_id=evaluation_id: self._discard_task(
                run_id, completed
            )
        )
        return queued

    async def wait(
        self,
        *,
        agent_id: str,
        evaluation_id: str,
    ) -> EvaluationRunVersion:
        task = self._tasks.get(evaluation_id)
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
        return await self.get(agent_id=agent_id, evaluation_id=evaluation_id)

    async def cancel(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        evaluation_id: str,
    ) -> EvaluationRunVersion:
        self._require_manager(actor)
        current = await self.get(
            agent_id=agent_id,
            evaluation_id=evaluation_id,
        )
        if current.status in {
            EvaluationRunStatus.SUCCEEDED,
            EvaluationRunStatus.FAILED,
            EvaluationRunStatus.CANCELLED,
        }:
            return current
        self._cancel_requested.add(evaluation_id)
        task = self._tasks.get(evaluation_id)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return await self.get(agent_id=agent_id, evaluation_id=evaluation_id)

    async def retry_invalid_attempt(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        evaluation_id: str,
        scene_version_id: str,
        case_id: str,
        target: Literal["candidate", "baseline"],
        attempt_index: int,
    ) -> EvaluationRunVersion:
        self._require_manager(actor)
        if evaluation_id in self._tasks:
            raise ScenarioInvalidTransition(
                "Wait for the formal evaluation to finish before retrying."
            )
        lock = self._retry_locks.setdefault(evaluation_id, asyncio.Lock())
        try:
            async with lock:
                current = await self.get(
                    agent_id=agent_id,
                    evaluation_id=evaluation_id,
                )
                if current.status is not EvaluationRunStatus.SUCCEEDED:
                    raise ScenarioInvalidTransition(
                        "Only a completed evaluation can retry invalid evidence."
                    )
                scene_evidence = next(
                    (
                        scene
                        for scene in current.scenes
                        if scene.scene_version_id == scene_version_id
                    ),
                    None,
                )
                if scene_evidence is None:
                    raise ScenarioNotFound(
                        f"Scene evidence {scene_version_id!r} was not found."
                    )
                case_evidence = next(
                    (
                        case
                        for case in scene_evidence.cases
                        if case.case_version_id == case_id
                    ),
                    None,
                )
                if case_evidence is None:
                    raise ScenarioNotFound(f"Case evidence {case_id!r} was not found.")
                attempts = (
                    case_evidence.candidate_attempts
                    if target == "candidate"
                    else case_evidence.baseline_attempts
                )
                old_attempt = next(
                    (
                        attempt
                        for attempt in attempts
                        if attempt.attempt_index == attempt_index
                    ),
                    None,
                )
                if old_attempt is None:
                    raise ScenarioNotFound(
                        f"Attempt {target}:{attempt_index} was not found."
                    )
                if old_attempt.outcome is not AttemptOutcome.INFRA_ERROR:
                    raise ScenarioInvalidTransition(
                        "Only infrastructure-invalid evidence can be retried."
                    )

                policy = await self._assets.get_policy_version(
                    agent_id=agent_id,
                    policy_version_id=current.policy_version_id,
                )
                binding = next(
                    (
                        item
                        for item in policy.bindings
                        if item.scene_version_id == scene_version_id
                    ),
                    None,
                )
                if binding is None:
                    raise ScenarioInvalidTransition(
                        "Evaluation Policy no longer contains the evidence Scene."
                    )
                dataset = await self._assets.get_dataset_version(
                    agent_id=agent_id,
                    dataset_version_id=binding.dataset_version_id,
                )
                case = next(
                    (item for item in dataset.cases if item.case_id == case_id),
                    None,
                )
                if case is None or case.scene_version_id != scene_version_id:
                    raise ScenarioInvalidTransition(
                        "Published Dataset no longer matches the evidence Case."
                    )
                evaluators = tuple(
                    [
                        await self._assets.get_evaluator_version(
                            agent_id=agent_id,
                            evaluator_version_id=evaluator_version_id,
                        )
                        for evaluator_version_id in binding.evaluator_version_ids
                    ]
                )
                candidate = await self._retry_candidate(
                    agent_id=agent_id,
                    run=current,
                    target=target,
                )
                retried = await self._executor.retry_invalid_attempt(
                    candidate=candidate,
                    case=case,
                    evaluators=evaluators,
                    attempt_index=attempt_index,
                )
                replacement = retried.model_copy(
                    update={
                        "manual_retry_count": old_attempt.manual_retry_count + 1,
                        "superseded_invalid_attempts": (
                            *old_attempt.superseded_invalid_attempts,
                            InvalidAttemptEvidence(
                                session_id=old_attempt.session_id,
                                retry_count=old_attempt.retry_count,
                                trace_ref=old_attempt.trace_ref,
                                error_message=old_attempt.error_message,
                            ),
                        ),
                    }
                )
                updated_attempts = tuple(
                    replacement if item.attempt_index == attempt_index else item
                    for item in attempts
                )
                case_update = (
                    {"candidate_attempts": updated_attempts}
                    if target == "candidate"
                    else {"baseline_attempts": updated_attempts}
                )
                updated_case = case_evidence.model_copy(update=case_update)
                updated_scene = scene_evidence.model_copy(
                    update={
                        "cases": tuple(
                            updated_case if item.case_version_id == case_id else item
                            for item in scene_evidence.cases
                        )
                    }
                )
                updated_scenes = tuple(
                    updated_scene if item.scene_version_id == scene_version_id else item
                    for item in current.scenes
                )
                recommendation = aggregate_quality_recommendation(
                    updated_scenes,
                    dependency_fingerprint=dependency_fingerprint(current.dependencies),
                )
                updated_run = current.model_copy(
                    update={
                        "revision": current.revision + 1,
                        "scenes": updated_scenes,
                        "recommendation": recommendation,
                        "updated_at": self._now(),
                    }
                )
                await self._append_run(updated_run)
                recommendation_record = QualityRecommendationRecord(
                    recommendation_id=(
                        f"recommendation:{evaluation_id}:{updated_run.revision}"
                    ),
                    evaluation_id=evaluation_id,
                    agent_id=agent_id,
                    candidate_id=current.candidate_id,
                    dependencies=current.dependencies,
                    recommendation=recommendation,
                    created_at=self._now(),
                )
                await self._append_model(
                    recommendation_record,
                    record_id=recommendation_record.recommendation_id,
                    agent_id=agent_id,
                    owner_id=actor.owner_id,
                    record_type=ScenarioRecordType.QUALITY_RECOMMENDATION,
                    asset_id=current.candidate_id,
                    version=updated_run.revision,
                )
                await self._reconcile_badcases(policy, updated_run)
                return updated_run
        finally:
            # Keep one stable lock per persisted evaluation so queued retries
            # cannot split across different locks after the first caller exits.
            self._retry_locks[evaluation_id] = lock

    async def _retry_candidate(
        self,
        *,
        agent_id: str,
        run: EvaluationRunVersion,
        target: Literal["candidate", "baseline"],
    ) -> CandidateVersion:
        if target == "candidate":
            return await self._assets.get_candidate_version(
                agent_id=agent_id,
                candidate_id=run.candidate_id,
            )
        if run.baseline_version_id is None:
            raise ScenarioInvalidTransition("This evaluation has no baseline evidence.")
        record = await self._repository.get(
            agent_id=agent_id,
            record_type=ScenarioRecordType.PUBLISHED_VERSION,
            record_id=run.baseline_version_id,
        )
        if record is None:
            raise ScenarioNotFound(
                f"Published baseline {run.baseline_version_id!r} was not found."
            )
        published = PublishedVersion.model_validate_json(record.payload_json)
        return await self._assets.get_candidate_version(
            agent_id=agent_id,
            candidate_id=published.candidate_id,
        )

    async def get(
        self,
        *,
        agent_id: str,
        evaluation_id: str,
    ) -> EvaluationRunVersion:
        record = await self._repository.latest_version(
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATION_RUN,
            asset_id=evaluation_id,
        )
        if record is None:
            raise ScenarioNotFound(f"Evaluation {evaluation_id!r} was not found.")
        run = EvaluationRunVersion.model_validate_json(record.payload_json)
        return await self._fail_orphaned_run(run)

    async def list_badcases(
        self,
        *,
        agent_id: str,
    ) -> tuple[BadcaseVersion, ...]:
        records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.BADCASE,
        )
        latest: dict[str, BadcaseVersion] = {}
        for record in records:
            model = BadcaseVersion.model_validate_json(record.payload_json)
            current = latest.get(model.badcase_id)
            if current is None or model.revision > current.revision:
                latest[model.badcase_id] = model
        return tuple(sorted(latest.values(), key=lambda item: item.badcase_id))

    async def list_runs(
        self,
        *,
        agent_id: str,
    ) -> tuple[EvaluationRunVersion, ...]:
        records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATION_RUN,
        )
        latest: dict[str, EvaluationRunVersion] = {}
        for record in records:
            run = EvaluationRunVersion.model_validate_json(record.payload_json)
            current = latest.get(run.evaluation_id)
            if current is None or run.revision > current.revision:
                latest[run.evaluation_id] = run
        reconciled = [await self._fail_orphaned_run(run) for run in latest.values()]
        return tuple(
            sorted(
                reconciled,
                key=lambda item: (item.created_at, item.evaluation_id),
            )
        )

    async def _fail_orphaned_run(
        self,
        run: EvaluationRunVersion,
    ) -> EvaluationRunVersion:
        if run.status not in {
            EvaluationRunStatus.QUEUED,
            EvaluationRunStatus.RUNNING,
        }:
            return run
        task = self._tasks.get(run.evaluation_id)
        if task is not None and not task.done():
            return run
        owned_here = run.evaluation_id in self._owned_run_ids
        stale = self._now() - run.updated_at >= timedelta(hours=4, minutes=5)
        if not owned_here and not stale:
            return run
        failed = run.model_copy(
            update={
                "revision": run.revision + 1,
                "status": EvaluationRunStatus.FAILED,
                "error_message": (
                    "Evaluation worker is no longer available; start a new run."
                ),
                "updated_at": self._now(),
            }
        )
        await self._append_run(failed)
        for badcase in await self.list_badcases(agent_id=run.agent_id):
            if (
                badcase.status is BadcaseStatus.VERIFYING
                and badcase.verification_evaluation_id == run.evaluation_id
            ):
                await self._append_badcase(
                    badcase.model_copy(
                        update={
                            "revision": badcase.revision + 1,
                            "status": BadcaseStatus.OPEN,
                            "updated_at": self._now(),
                        }
                    )
                )
        return failed

    async def _execute(self, context: _RunContext) -> None:
        running = context.run.model_copy(
            update={
                "revision": 2,
                "status": EvaluationRunStatus.RUNNING,
                "updated_at": self._now(),
            }
        )
        await self._append_run(running)
        try:
            result = await self._executor.execute(context.plan)
        except asyncio.CancelledError:
            await self._append_terminal(
                running,
                status=EvaluationRunStatus.CANCELLED,
                error_message="Evaluation cancelled.",
            )
            await self._restore_verifying_badcases(context)
            raise
        except Exception as error:  # noqa: BLE001 - persist terminal task failure
            await self._append_terminal(
                running,
                status=EvaluationRunStatus.FAILED,
                error_message=str(error),
            )
            await self._restore_verifying_badcases(context)
            return

        if context.run.evaluation_id in self._cancel_requested:
            await self._append_terminal(
                running,
                status=EvaluationRunStatus.CANCELLED,
                error_message="Evaluation cancelled.",
            )
            await self._restore_verifying_badcases(context)
            return

        fingerprint = dependency_fingerprint(context.run.dependencies)
        recommendation = aggregate_quality_recommendation(
            result.scenes,
            dependency_fingerprint=fingerprint,
        )
        succeeded = running.model_copy(
            update={
                "revision": running.revision + 1,
                "status": EvaluationRunStatus.SUCCEEDED,
                "scenes": result.scenes,
                "recommendation": recommendation,
                "updated_at": self._now(),
            }
        )
        await self._append_run(succeeded)
        recommendation_record = QualityRecommendationRecord(
            recommendation_id=f"recommendation:{context.run.evaluation_id}",
            evaluation_id=context.run.evaluation_id,
            agent_id=context.run.agent_id,
            candidate_id=context.run.candidate_id,
            dependencies=context.run.dependencies,
            recommendation=recommendation,
            created_at=self._now(),
        )
        await self._append_model(
            recommendation_record,
            record_id=recommendation_record.recommendation_id,
            agent_id=context.run.agent_id,
            owner_id=context.run.created_by,
            record_type=ScenarioRecordType.QUALITY_RECOMMENDATION,
            asset_id=context.run.candidate_id,
            version=1,
        )
        await self._reconcile_badcases(context.policy, succeeded)

    async def _append_terminal(
        self,
        running: EvaluationRunVersion,
        *,
        status: EvaluationRunStatus,
        error_message: str,
    ) -> None:
        await self._append_run(
            running.model_copy(
                update={
                    "revision": running.revision + 1,
                    "status": status,
                    "error_message": error_message,
                    "updated_at": self._now(),
                }
            )
        )

    async def _mark_badcases_verifying(self, context: _RunContext) -> None:
        for binding, scene in zip(
            context.policy.bindings,
            context.plan.scenes,
            strict=True,
        ):
            for case in scene.cases:
                existing = await self._badcase_for(
                    agent_id=context.run.agent_id,
                    binding=binding,
                    case_id=case.case_id,
                )
                if (
                    existing is None
                    or existing.status is not BadcaseStatus.OPEN
                    or existing.source_candidate_id == context.run.candidate_id
                ):
                    continue
                await self._append_badcase(
                    existing.model_copy(
                        update={
                            "revision": existing.revision + 1,
                            "status": BadcaseStatus.VERIFYING,
                            "verification_evaluation_id": context.run.evaluation_id,
                            "verification_candidate_id": context.run.candidate_id,
                            "updated_at": self._now(),
                        }
                    )
                )

    async def _restore_verifying_badcases(self, context: _RunContext) -> None:
        for badcase in await self.list_badcases(agent_id=context.run.agent_id):
            if (
                badcase.status is BadcaseStatus.VERIFYING
                and badcase.verification_evaluation_id == context.run.evaluation_id
            ):
                await self._append_badcase(
                    badcase.model_copy(
                        update={
                            "revision": badcase.revision + 1,
                            "status": BadcaseStatus.OPEN,
                            "updated_at": self._now(),
                        }
                    )
                )

    async def _reconcile_badcases(
        self,
        policy: EvaluationPolicyVersion,
        run: EvaluationRunVersion,
    ) -> None:
        for binding, scene in zip(
            policy.bindings,
            run.scenes,
            strict=True,
        ):
            for case in scene.cases:
                outcome = aggregate_case(case).outcome
                existing = await self._badcase_for(
                    agent_id=run.agent_id,
                    binding=binding,
                    case_id=case.case_version_id,
                )
                if outcome is CaseOutcome.FAIL:
                    if existing is None:
                        now = self._now()
                        await self._append_badcase(
                            BadcaseVersion(
                                badcase_id=self._badcase_id(
                                    run.agent_id,
                                    binding,
                                    case.case_version_id,
                                ),
                                agent_id=run.agent_id,
                                revision=1,
                                status=BadcaseStatus.OPEN,
                                scene_version_id=binding.scene_version_id,
                                case_id=case.case_version_id,
                                dataset_version_id=binding.dataset_version_id,
                                evaluator_version_ids=binding.evaluator_version_ids,
                                source_evaluation_id=run.evaluation_id,
                                source_candidate_id=run.candidate_id,
                                created_at=now,
                                updated_at=now,
                            )
                        )
                    elif existing.status is not BadcaseStatus.OPEN:
                        await self._append_badcase(
                            existing.model_copy(
                                update={
                                    "revision": existing.revision + 1,
                                    "status": BadcaseStatus.OPEN,
                                    "source_evaluation_id": run.evaluation_id,
                                    "source_candidate_id": run.candidate_id,
                                    "resolution_evaluation_id": None,
                                    "resolution_candidate_id": None,
                                    "updated_at": self._now(),
                                }
                            )
                        )
                elif (
                    outcome is CaseOutcome.PASS
                    and existing is not None
                    and existing.status is BadcaseStatus.VERIFYING
                    and existing.source_candidate_id != run.candidate_id
                ):
                    await self._append_badcase(
                        existing.model_copy(
                            update={
                                "revision": existing.revision + 1,
                                "status": BadcaseStatus.CLOSED,
                                "resolution_evaluation_id": run.evaluation_id,
                                "resolution_candidate_id": run.candidate_id,
                                "updated_at": self._now(),
                            }
                        )
                    )
                elif (
                    existing is not None and existing.status is BadcaseStatus.VERIFYING
                ):
                    await self._append_badcase(
                        existing.model_copy(
                            update={
                                "revision": existing.revision + 1,
                                "status": BadcaseStatus.OPEN,
                                "updated_at": self._now(),
                            }
                        )
                    )

    async def _badcase_for(
        self,
        *,
        agent_id: str,
        binding: PolicySceneBinding,
        case_id: str,
    ) -> BadcaseVersion | None:
        badcase_id = self._badcase_id(agent_id, binding, case_id)
        record = await self._repository.latest_version(
            agent_id=agent_id,
            record_type=ScenarioRecordType.BADCASE,
            asset_id=badcase_id,
        )
        return (
            BadcaseVersion.model_validate_json(record.payload_json)
            if record is not None
            else None
        )

    async def _append_badcase(self, badcase: BadcaseVersion) -> None:
        await self._append_model(
            badcase,
            record_id=f"{badcase.badcase_id}:{badcase.revision}",
            agent_id=badcase.agent_id,
            owner_id="system",
            record_type=ScenarioRecordType.BADCASE,
            asset_id=badcase.badcase_id,
            version=badcase.revision,
        )

    async def _append_run(self, run: EvaluationRunVersion) -> None:
        await self._append_model(
            run,
            record_id=f"{run.evaluation_id}:{run.revision}",
            agent_id=run.agent_id,
            owner_id=run.created_by,
            record_type=ScenarioRecordType.EVALUATION_RUN,
            asset_id=run.evaluation_id,
            version=run.revision,
        )

    async def _append_model(
        self,
        model: object,
        *,
        record_id: str,
        agent_id: str,
        owner_id: str,
        record_type: ScenarioRecordType,
        asset_id: str,
        version: int,
    ) -> None:
        payload_json = model.model_dump_json(by_alias=True)  # type: ignore[attr-defined]
        await self._repository.append(
            ScenarioRecord(
                record_id=record_id,
                agent_id=agent_id,
                owner_id=owner_id,
                record_type=record_type,
                asset_id=asset_id,
                version=version,
                created_at=self._now(),
                payload_json=payload_json,
            )
        )

    @staticmethod
    def _badcase_id(
        agent_id: str,
        binding: PolicySceneBinding,
        case_id: str,
    ) -> str:
        payload = json.dumps(
            {
                "agentId": agent_id,
                "sceneVersionId": binding.scene_version_id,
                "caseId": case_id,
                "datasetVersionId": binding.dataset_version_id,
                "evaluatorVersionIds": binding.evaluator_version_ids,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return f"badcase-{hashlib.sha256(payload).hexdigest()}"

    def _discard_task(
        self,
        evaluation_id: str,
        task: asyncio.Task[None],
    ) -> None:
        if self._tasks.get(evaluation_id) is task:
            self._tasks.pop(evaluation_id, None)
        self._cancel_requested.discard(evaluation_id)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Formal evaluation clock must return an aware timestamp.")
        return value

    @staticmethod
    def _require_manager(actor: ScenarioActor) -> None:
        if actor.role not in {StudioRole.ADMIN, StudioRole.DEVELOPER}:
            raise ScenarioForbidden("Developer or Admin role is required.")

    @staticmethod
    def _require_admin(actor: ScenarioActor) -> None:
        if actor.role != StudioRole.ADMIN:
            raise ScenarioForbidden(
                "Formal evaluation executes frozen Agent code and requires Admin role."
            )
