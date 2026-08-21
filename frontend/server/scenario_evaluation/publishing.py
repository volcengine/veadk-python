"""Audited normal, skip, and risk publication paths."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from frontend.server.scenario_evaluation.errors import (
    ScenarioEvaluationRunning,
    ScenarioForbidden,
    ScenarioInvalidTransition,
    ScenarioNotFound,
)
from frontend.server.scenario_evaluation.models import (
    CandidateProjectFile,
    EvaluationDependencies,
    EvaluationRunStatus,
    EvaluationRunVersion,
    PublishAudit,
    PublishAuditEvent,
    PublishedVersion,
    PublishIntentStatus,
    PublishIntentVersion,
    PublishPath,
    PublishRecoveryIssue,
    QualityRecommendationValue,
    ScenarioActor,
    ScenarioRecord,
    ScenarioRecordType,
)
from frontend.server.scenario_evaluation.recommendation import (
    recommendation_is_current,
)
from frontend.server.scenario_evaluation.repository import (
    ScenarioEvaluationRepository,
    ScenarioRecordConflict,
)
from frontend.server.scenario_evaluation.service import ScenarioEvaluationService
from veadk.cli.studio_rbac import StudioRole


@dataclass(frozen=True)
class _QualityResolution:
    path: PublishPath
    quality_state: str
    quality_fingerprint: str
    evaluation_id: str | None
    recommendation_value: QualityRecommendationValue | None
    risk_items: tuple[str, ...]


def _default_id_factory(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class PublishCandidateService:
    def __init__(
        self,
        repository: ScenarioEvaluationRepository,
        asset_service: ScenarioEvaluationService,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[str], str] | None = None,
        confirmation_ttl: timedelta = timedelta(minutes=10),
    ) -> None:
        if confirmation_ttl <= timedelta(0):
            raise ValueError("confirmation_ttl must be positive")
        self._repository = repository
        self._assets = asset_service
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or _default_id_factory
        self._uses_default_id_factory = id_factory is None
        self._confirmation_ttl = confirmation_ttl

    async def prepare(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        candidate_id: str,
        policy_version_id: str | None,
        environment_fingerprint: str,
        permission_fingerprint: str | None = None,
        second_confirmation: bool,
        reason: str,
        idempotency_key: str,
    ) -> PublishIntentVersion:
        del permission_fingerprint
        self._require_manager(actor)
        if not environment_fingerprint.strip():
            raise ScenarioInvalidTransition("Environment fingerprint is required.")
        if not idempotency_key.strip():
            raise ScenarioInvalidTransition("Idempotency key is required.")
        permission_fingerprint = self._permission_fingerprint(actor, agent_id)
        await self._assets.get_candidate_version(
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
                "Publish environment does not match the frozen Candidate."
            )
        resolution = await self._resolve_quality(
            agent_id=agent_id,
            candidate_id=candidate_id,
            policy_version_id=policy_version_id,
            environment_fingerprint=environment_fingerprint,
        )
        reason = reason.strip()
        if resolution.path in {PublishPath.SKIP, PublishPath.RISK}:
            if not second_confirmation or not reason:
                raise ScenarioInvalidTransition(
                    "Skip and risk publication require confirmation and a reason."
                )

        existing = await self._intent_for_idempotency_key(
            agent_id=agent_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if (
                existing.actor_id == actor.owner_id
                and existing.candidate_id == candidate_id
                and existing.path is resolution.path
                and existing.quality_fingerprint == resolution.quality_fingerprint
                and existing.permission_fingerprint == permission_fingerprint
                and existing.reason == reason
            ):
                return existing
            raise ScenarioRecordConflict(
                "Idempotency key is already bound to another publish intent."
            )

        now = self._now()
        intent_id = self._id_factory("publish-intent")
        if self._uses_default_id_factory:
            identity = json.dumps(
                {
                    "actorId": actor.owner_id,
                    "agentId": agent_id,
                    "idempotencyKey": idempotency_key,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            intent_id = (
                "publish-intent-"
                f"{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}"
            )
        intent = PublishIntentVersion(
            intent_id=intent_id,
            agent_id=agent_id,
            revision=1,
            status=PublishIntentStatus.PREPARED,
            candidate_id=candidate_id,
            actor_id=actor.owner_id,
            path=resolution.path,
            quality_state=resolution.quality_state,
            quality_fingerprint=resolution.quality_fingerprint,
            evaluation_id=resolution.evaluation_id,
            recommendation_value=resolution.recommendation_value,
            risk_items=resolution.risk_items,
            policy_version_id=policy_version_id,
            environment_fingerprint=environment_fingerprint,
            permission_fingerprint=permission_fingerprint,
            second_confirmation=second_confirmation,
            reason=reason,
            idempotency_key=idempotency_key,
            expires_at=now + self._confirmation_ttl,
            created_at=now,
            updated_at=now,
        )
        try:
            await self._append_intent(intent)
        except ScenarioRecordConflict:
            winner = await self._intent_for_idempotency_key(
                agent_id=agent_id,
                idempotency_key=idempotency_key,
            )
            if (
                winner is not None
                and winner.actor_id == actor.owner_id
                and winner.candidate_id == candidate_id
                and winner.path is resolution.path
                and winner.quality_fingerprint == resolution.quality_fingerprint
                and winner.permission_fingerprint == permission_fingerprint
                and winner.reason == reason
            ):
                return winner
            raise
        await self._append_audit(intent, PublishAuditEvent.PREPARED)
        return intent

    async def record_started(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        intent_id: str,
        permission_fingerprint: str | None = None,
    ) -> PublishIntentVersion:
        del permission_fingerprint
        self._require_manager(actor)
        current = await self._get_intent(agent_id, intent_id)
        self._validate_bound_actor(current, actor)
        if current.permission_fingerprint != self._permission_fingerprint(
            actor, agent_id
        ):
            raise ScenarioInvalidTransition("Publish permission has changed.")
        if self._now() > current.expires_at:
            raise ScenarioInvalidTransition("Publish confirmation has expired.")
        if current.status not in {
            PublishIntentStatus.PREPARED,
            PublishIntentStatus.FAILED,
        }:
            raise ScenarioInvalidTransition(
                f"Publish intent cannot start from {current.status.value}."
            )
        resolution = await self._resolve_quality(
            agent_id=agent_id,
            candidate_id=current.candidate_id,
            policy_version_id=current.policy_version_id,
            environment_fingerprint=current.environment_fingerprint,
        )
        if (
            resolution.path is not current.path
            or resolution.quality_fingerprint != current.quality_fingerprint
        ):
            raise ScenarioInvalidTransition(
                "Publish quality state changed; prepare a new confirmation."
            )
        started = current.model_copy(
            update={
                "revision": current.revision + 1,
                "status": PublishIntentStatus.STARTED,
                "deployment_attempts": current.deployment_attempts + 1,
                "deployment_ref": None,
                "error_message": "",
                "updated_at": self._now(),
            }
        )
        await self._append_intent(started)
        await self._append_audit(started, PublishAuditEvent.STARTED)
        return started

    @staticmethod
    def _permission_fingerprint(actor: ScenarioActor, agent_id: str) -> str:
        payload = json.dumps(
            {
                "actorId": actor.owner_id,
                "agentId": agent_id,
                "role": actor.role.value,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"

    async def validate_deployment_source(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        intent_id: str,
        files: tuple[CandidateProjectFile, ...],
        deployment_profile: dict[str, object] | None = None,
    ) -> None:
        """Require governed deployment files to match the frozen Candidate."""
        self._require_manager(actor)
        intent = await self._get_intent(agent_id, intent_id)
        self._validate_bound_actor(intent, actor)
        candidate = await self._assets.get_candidate_version(
            agent_id=agent_id,
            candidate_id=intent.candidate_id,
        )
        project_ref = candidate.artifact.runtime_project_ref
        if not project_ref:
            raise ScenarioRecordConflict(
                "Governed deployment requires a frozen Candidate project."
            )
        snapshot = await self._assets.get_candidate_runtime_project(
            agent_id=agent_id,
            project_snapshot_id=project_ref,
        )
        expected = {item.path: item.content for item in snapshot.files}
        actual = {item.path: item.content for item in files}
        if len(actual) != len(files) or actual != expected:
            raise ScenarioRecordConflict(
                "Deployment files do not match the frozen Candidate project."
            )
        if snapshot.deployment_profile != (deployment_profile or {}):
            raise ScenarioRecordConflict(
                "Deployment configuration does not match the frozen Candidate."
            )

    async def record_failed(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        intent_id: str,
        deployment_ref: str,
        error_message: str,
    ) -> PublishIntentVersion:
        self._require_manager(actor)
        current = await self._get_intent(agent_id, intent_id)
        self._validate_bound_actor(current, actor)
        if current.status not in {
            PublishIntentStatus.STARTED,
            PublishIntentStatus.SUBMITTED,
        }:
            raise ScenarioInvalidTransition("Only an active publish can fail.")
        if not deployment_ref.strip() or not error_message.strip():
            raise ScenarioInvalidTransition(
                "Failed publication requires deployment reference and error."
            )
        failed = current.model_copy(
            update={
                "revision": current.revision + 1,
                "status": PublishIntentStatus.FAILED,
                "deployment_ref": deployment_ref,
                "error_message": error_message,
                "updated_at": self._now(),
            }
        )
        await self._append_intent(failed)
        await self._append_audit(failed, PublishAuditEvent.FAILED)
        return failed

    async def record_submitted(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        intent_id: str,
        deployment_ref: str,
    ) -> PublishIntentVersion:
        self._require_manager(actor)
        current = await self._get_intent(agent_id, intent_id)
        self._validate_bound_actor(current, actor)
        if current.status is not PublishIntentStatus.STARTED:
            raise ScenarioInvalidTransition("Only a started publish can be submitted.")
        if not deployment_ref.strip():
            raise ScenarioInvalidTransition(
                "Submitted publication requires a reference."
            )
        submitted = current.model_copy(
            update={
                "revision": current.revision + 1,
                "status": PublishIntentStatus.SUBMITTED,
                "deployment_ref": deployment_ref,
                "updated_at": self._now(),
            }
        )
        await self._append_intent(submitted)
        await self._append_audit(submitted, PublishAuditEvent.SUBMITTED)
        return submitted

    async def finalize_succeeded(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        intent_id: str,
        deployment_ref: str,
    ) -> tuple[PublishIntentVersion, PublishedVersion]:
        self._require_manager(actor)
        current = await self._get_intent(agent_id, intent_id)
        self._validate_bound_actor(current, actor)
        existing_published = await self._published_for_intent(
            agent_id=agent_id,
            intent_id=intent_id,
        )
        if current.status is PublishIntentStatus.SUCCEEDED:
            if existing_published is None:
                raise ScenarioInvalidTransition(
                    "Publish succeeded without a recoverable Published Version."
                )
            audits = await self.list_audits(agent_id=agent_id, intent_id=intent_id)
            if not any(audit.event is PublishAuditEvent.SUCCEEDED for audit in audits):
                await self._append_audit(current, PublishAuditEvent.SUCCEEDED)
            return current, existing_published
        if current.status not in {
            PublishIntentStatus.STARTED,
            PublishIntentStatus.SUBMITTED,
        }:
            raise ScenarioInvalidTransition("Only an active publish can succeed.")
        if not deployment_ref.strip():
            raise ScenarioInvalidTransition("Deployment reference is required.")

        published = existing_published
        if published is None:
            candidate = await self._assets.get_candidate_version(
                agent_id=agent_id,
                candidate_id=current.candidate_id,
            )
            latest = await self.latest_published(agent_id=agent_id)
            version = 1 if latest is None else latest.version + 1
            published = PublishedVersion(
                published_version_id=f"published-v{version}",
                agent_id=agent_id,
                version=version,
                candidate_id=current.candidate_id,
                candidate_artifact=candidate.artifact,
                publish_intent_id=intent_id,
                publish_path=current.path,
                deployment_ref=deployment_ref,
                created_at=self._now(),
                created_by=actor.owner_id,
            )
            await self._append_model(
                published,
                record_id=published.published_version_id,
                agent_id=agent_id,
                owner_id=actor.owner_id,
                record_type=ScenarioRecordType.PUBLISHED_VERSION,
                asset_id="online",
                version=version,
            )

        succeeded = current.model_copy(
            update={
                "revision": current.revision + 1,
                "status": PublishIntentStatus.SUCCEEDED,
                "deployment_ref": deployment_ref,
                "error_message": "",
                "updated_at": self._now(),
            }
        )
        await self._append_intent(succeeded)
        await self._append_audit(succeeded, PublishAuditEvent.SUCCEEDED)
        return succeeded, published

    async def reconcile_succeeded(
        self,
        actor: ScenarioActor,
        *,
        agent_id: str,
        intent_id: str,
    ) -> tuple[PublishIntentVersion, PublishedVersion]:
        """Repair only a success already proven by an internal PublishedVersion."""

        self._require_admin(actor)
        current = await self._get_intent(agent_id, intent_id)
        published = await self._published_for_intent(
            agent_id=agent_id,
            intent_id=intent_id,
        )
        if published is None:
            raise ScenarioInvalidTransition(
                "No internally verified Published Version is available to reconcile."
            )
        if current.status is PublishIntentStatus.SUCCEEDED:
            audits = await self.list_audits(agent_id=agent_id, intent_id=intent_id)
            if not any(audit.event is PublishAuditEvent.SUCCEEDED for audit in audits):
                await self._append_audit(current, PublishAuditEvent.SUCCEEDED)
            return current, published
        if current.status not in {
            PublishIntentStatus.STARTED,
            PublishIntentStatus.SUBMITTED,
        }:
            raise ScenarioInvalidTransition(
                "Only an internally published intent can be reconciled."
            )
        succeeded = current.model_copy(
            update={
                "revision": current.revision + 1,
                "status": PublishIntentStatus.SUCCEEDED,
                "deployment_ref": published.deployment_ref,
                "error_message": "",
                "updated_at": self._now(),
            }
        )
        await self._append_intent(succeeded)
        await self._append_audit(succeeded, PublishAuditEvent.SUCCEEDED)
        return succeeded, published

    async def latest_published(
        self,
        *,
        agent_id: str,
    ) -> PublishedVersion | None:
        record = await self._repository.latest_version(
            agent_id=agent_id,
            record_type=ScenarioRecordType.PUBLISHED_VERSION,
            asset_id="online",
        )
        return (
            PublishedVersion.model_validate_json(record.payload_json)
            if record is not None
            else None
        )

    async def list_audits(
        self,
        *,
        agent_id: str,
        intent_id: str | None = None,
    ) -> tuple[PublishAudit, ...]:
        records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.PUBLISH_AUDIT,
        )
        audits = [
            PublishAudit.model_validate_json(record.payload_json) for record in records
        ]
        if intent_id is not None:
            audits = [item for item in audits if item.intent_id == intent_id]
        return tuple(
            sorted(audits, key=lambda item: (item.intent_id, item.event_index))
        )

    async def list_recovery_issues(
        self,
        *,
        agent_id: str,
    ) -> tuple[PublishRecoveryIssue, ...]:
        intent_records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.PUBLISH_INTENT,
        )
        latest_intents: dict[str, PublishIntentVersion] = {}
        for record in intent_records:
            intent = PublishIntentVersion.model_validate_json(record.payload_json)
            current = latest_intents.get(intent.intent_id)
            if current is None or intent.revision > current.revision:
                latest_intents[intent.intent_id] = intent
        published_records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.PUBLISHED_VERSION,
        )
        published_by_intent = {
            published.publish_intent_id: published
            for published in (
                PublishedVersion.model_validate_json(record.payload_json)
                for record in published_records
            )
        }
        audits = await self.list_audits(agent_id=agent_id)
        succeeded_audit_ids = {
            audit.intent_id
            for audit in audits
            if audit.event is PublishAuditEvent.SUCCEEDED
        }
        issues: list[PublishRecoveryIssue] = []
        for intent_id, published in published_by_intent.items():
            intent = latest_intents.get(intent_id)
            if intent is None:
                continue
            if intent.status is PublishIntentStatus.STARTED:
                issue_type = "published_intent_not_finalized"
            elif (
                intent.status is PublishIntentStatus.SUCCEEDED
                and intent_id not in succeeded_audit_ids
            ):
                issue_type = "success_audit_missing"
            else:
                continue
            issues.append(
                PublishRecoveryIssue(
                    issue_type=issue_type,
                    intent=intent,
                    published_version=published,
                )
            )
        return tuple(sorted(issues, key=lambda item: item.intent.updated_at))

    async def _resolve_quality(
        self,
        *,
        agent_id: str,
        candidate_id: str,
        policy_version_id: str | None,
        environment_fingerprint: str,
    ) -> _QualityResolution:
        runs = await self._latest_runs(agent_id=agent_id, candidate_id=candidate_id)
        if any(
            run.status in {EvaluationRunStatus.QUEUED, EvaluationRunStatus.RUNNING}
            for run in runs
        ):
            raise ScenarioEvaluationRunning(
                "Wait for evaluation or cancel it before publishing."
            )
        current_dependencies = await self._current_dependencies(
            agent_id=agent_id,
            candidate_id=candidate_id,
            policy_version_id=policy_version_id,
            environment_fingerprint=environment_fingerprint,
        )
        latest = max(runs, key=lambda item: item.updated_at) if runs else None
        if latest is None:
            return self._resolution(
                PublishPath.SKIP,
                "unevaluated",
                current_dependencies,
                None,
                None,
                (),
            )
        if latest.status is EvaluationRunStatus.FAILED:
            return self._resolution(
                PublishPath.RISK,
                "indeterminate",
                current_dependencies,
                latest.evaluation_id,
                QualityRecommendationValue.INDETERMINATE,
                (latest.error_message or "formal evaluation failed",),
            )
        if latest.status is EvaluationRunStatus.CANCELLED:
            return self._resolution(
                PublishPath.SKIP,
                "unevaluated",
                current_dependencies,
                latest.evaluation_id,
                None,
                (),
            )
        if latest.recommendation is None:
            return self._resolution(
                PublishPath.RISK,
                "indeterminate",
                current_dependencies,
                latest.evaluation_id,
                QualityRecommendationValue.INDETERMINATE,
                ("formal evaluation produced no recommendation",),
            )
        if current_dependencies is None or not recommendation_is_current(
            latest.recommendation,
            current_dependencies,
        ):
            return self._resolution(
                PublishPath.SKIP,
                "stale",
                current_dependencies,
                latest.evaluation_id,
                latest.recommendation.value,
                (),
            )
        value = latest.recommendation.value
        if value is QualityRecommendationValue.RECOMMEND:
            return self._resolution(
                PublishPath.NORMAL,
                "valid_recommend",
                current_dependencies,
                latest.evaluation_id,
                value,
                (),
            )
        risks = tuple(
            [
                f"quality recommendation: {value.value}",
                *(
                    f"warning scene: {scene_id}"
                    for scene_id in latest.recommendation.warning_scene_version_ids
                ),
            ]
        )
        return self._resolution(
            PublishPath.RISK,
            (
                "valid_do_not_recommend"
                if value is QualityRecommendationValue.DO_NOT_RECOMMEND
                else "indeterminate"
            ),
            current_dependencies,
            latest.evaluation_id,
            value,
            risks,
        )

    async def _current_dependencies(
        self,
        *,
        agent_id: str,
        candidate_id: str,
        policy_version_id: str | None,
        environment_fingerprint: str,
    ) -> EvaluationDependencies | None:
        if policy_version_id is None:
            return None
        policy = await self._assets.get_policy_version(
            agent_id=agent_id,
            policy_version_id=policy_version_id,
        )
        published = await self.latest_published(agent_id=agent_id)
        return EvaluationDependencies(
            candidate_id=candidate_id,
            baseline_version_id=(
                published.published_version_id if published is not None else None
            ),
            scene_version_ids=tuple(item.scene_version_id for item in policy.bindings),
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

    async def _latest_runs(
        self,
        *,
        agent_id: str,
        candidate_id: str,
    ) -> tuple[EvaluationRunVersion, ...]:
        records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.EVALUATION_RUN,
        )
        latest: dict[str, EvaluationRunVersion] = {}
        for record in records:
            run = EvaluationRunVersion.model_validate_json(record.payload_json)
            if run.candidate_id != candidate_id:
                continue
            current = latest.get(run.evaluation_id)
            if current is None or run.revision > current.revision:
                latest[run.evaluation_id] = run
        return tuple(latest.values())

    def _resolution(
        self,
        path: PublishPath,
        quality_state: str,
        dependencies: EvaluationDependencies | None,
        evaluation_id: str | None,
        recommendation_value: QualityRecommendationValue | None,
        risk_items: tuple[str, ...],
    ) -> _QualityResolution:
        payload = {
            "path": path.value,
            "qualityState": quality_state,
            "dependencies": (
                dependencies.model_dump(mode="json", by_alias=True)
                if dependencies is not None
                else None
            ),
            "evaluationId": evaluation_id,
            "recommendationValue": (
                recommendation_value.value if recommendation_value is not None else None
            ),
            "riskItems": risk_items,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        return _QualityResolution(
            path=path,
            quality_state=quality_state,
            quality_fingerprint=f"sha256:{fingerprint}",
            evaluation_id=evaluation_id,
            recommendation_value=recommendation_value,
            risk_items=risk_items,
        )

    async def _get_intent(
        self,
        agent_id: str,
        intent_id: str,
    ) -> PublishIntentVersion:
        record = await self._repository.latest_version(
            agent_id=agent_id,
            record_type=ScenarioRecordType.PUBLISH_INTENT,
            asset_id=intent_id,
        )
        if record is None:
            raise ScenarioNotFound(f"Publish intent {intent_id!r} was not found.")
        return PublishIntentVersion.model_validate_json(record.payload_json)

    async def _intent_for_idempotency_key(
        self,
        *,
        agent_id: str,
        idempotency_key: str,
    ) -> PublishIntentVersion | None:
        records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.PUBLISH_INTENT,
        )
        matching = [
            PublishIntentVersion.model_validate_json(record.payload_json)
            for record in records
            if PublishIntentVersion.model_validate_json(
                record.payload_json
            ).idempotency_key
            == idempotency_key
        ]
        return max(matching, key=lambda item: item.revision) if matching else None

    async def _published_for_intent(
        self,
        *,
        agent_id: str,
        intent_id: str,
    ) -> PublishedVersion | None:
        records = await self._repository.list(
            agent_id=agent_id,
            record_type=ScenarioRecordType.PUBLISHED_VERSION,
        )
        for record in records:
            published = PublishedVersion.model_validate_json(record.payload_json)
            if published.publish_intent_id == intent_id:
                return published
        return None

    async def _append_intent(self, intent: PublishIntentVersion) -> None:
        await self._append_model(
            intent,
            record_id=f"{intent.intent_id}:{intent.revision}",
            agent_id=intent.agent_id,
            owner_id=intent.actor_id,
            record_type=ScenarioRecordType.PUBLISH_INTENT,
            asset_id=intent.intent_id,
            version=intent.revision,
        )

    async def _append_audit(
        self,
        intent: PublishIntentVersion,
        event: PublishAuditEvent,
    ) -> None:
        event_index = intent.revision
        audit = PublishAudit(
            audit_id=f"{intent.intent_id}:{intent.revision}:{event.value}",
            intent_id=intent.intent_id,
            event_index=event_index,
            event=event,
            agent_id=intent.agent_id,
            candidate_id=intent.candidate_id,
            actor_id=intent.actor_id,
            path=intent.path,
            quality_state=intent.quality_state,
            recommendation_value=intent.recommendation_value,
            risk_items=intent.risk_items,
            reason=intent.reason,
            deployment_ref=intent.deployment_ref,
            error_message=intent.error_message,
            created_at=intent.updated_at,
        )
        await self._append_model(
            audit,
            record_id=audit.audit_id,
            agent_id=intent.agent_id,
            owner_id=intent.actor_id,
            record_type=ScenarioRecordType.PUBLISH_AUDIT,
            asset_id=intent.intent_id,
            version=event_index,
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

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Publish clock must return an aware timestamp.")
        return value

    @staticmethod
    def _validate_bound_actor(
        intent: PublishIntentVersion,
        actor: ScenarioActor,
    ) -> None:
        if intent.actor_id != actor.owner_id:
            raise ScenarioInvalidTransition(
                "Publish confirmation belongs to another actor."
            )

    @staticmethod
    def _require_manager(actor: ScenarioActor) -> None:
        if actor.role not in {StudioRole.ADMIN, StudioRole.DEVELOPER}:
            raise ScenarioForbidden("Developer or Admin role is required.")
