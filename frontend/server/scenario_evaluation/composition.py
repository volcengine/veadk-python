"""Production composition for scenario-evaluation services."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from frontend.server.scenario_evaluation.evaluators import (
    ControlledEvidenceEvaluator,
    StructuredRubricRunner,
)
from frontend.server.scenario_evaluation.executor import FormalEvaluationExecutor
from frontend.server.scenario_evaluation.executor import EvidenceEvaluator
from frontend.server.scenario_evaluation.publishing import PublishCandidateService
from frontend.server.scenario_evaluation.repository import (
    AgentAccessVerifier,
    InMemoryScenarioEvaluationRepository,
    OwnerScopedScenarioEvaluationRepository,
    ScenarioEvaluationRepository,
    TosScenarioEvaluationRepository,
    UnavailableScenarioEvaluationRepository,
)
from frontend.server.scenario_evaluation.run_service import FormalEvaluationManager
from frontend.server.scenario_evaluation.runtime import (
    CredentialReferenceResolver,
    GeneratedAgentEvaluationRuntime,
    GeneratedRuntimeManager,
    ServiceCandidateRuntimeMaterializer,
)
from frontend.server.scenario_evaluation.service import (
    AgentIdentityVerifier,
    ProjectAttestationVerifier,
    ScenarioEvaluationService,
)
from frontend.server.storage import StudioProvider, StudioStorageConfig
from frontend.server.storage.tos import (
    CredentialResolver,
    TosClientFactory,
    create_tos_client_factory,
)

SCENARIO_STORAGE_CREDENTIALS_UNAVAILABLE = "管理员未配置场景评测持久化存储访问凭据"


@dataclass(frozen=True)
class ScenarioEvaluationComponents:
    repository: ScenarioEvaluationRepository
    service: ScenarioEvaluationService
    run_manager: FormalEvaluationManager
    publisher: PublishCandidateService
    evidence_evaluator: EvidenceEvaluator


def create_components(
    *,
    studio: bool,
    provider: StudioProvider,
    generated_runtime_manager: GeneratedRuntimeManager,
    credential_resolver: CredentialReferenceResolver,
    base_environment: Callable[[], Mapping[str, str]],
    resolve_storage_credentials: CredentialResolver | None = None,
    storage_client_factory: TosClientFactory | None = None,
    storage_environment: Mapping[str, str] | None = None,
    owner_scoped: bool = False,
    project_attestation_verifier: ProjectAttestationVerifier | None = None,
    agent_identity_verifier: AgentIdentityVerifier | None = None,
    agent_access_verifier: AgentAccessVerifier | None = None,
) -> ScenarioEvaluationComponents:
    """Compose one shared, fail-closed scenario-evaluation dependency graph."""
    repository = _create_repository(
        studio=studio,
        provider=provider,
        resolve_storage_credentials=resolve_storage_credentials,
        storage_client_factory=storage_client_factory,
        storage_environment=storage_environment,
    )
    if owner_scoped:
        repository = OwnerScopedScenarioEvaluationRepository(
            repository,
            agent_access_verifier=agent_access_verifier,
        )
    service = ScenarioEvaluationService(
        repository,
        project_attestation_verifier=project_attestation_verifier,
        agent_identity_verifier=agent_identity_verifier,
    )
    runtime = GeneratedAgentEvaluationRuntime(
        generated_runtime_manager,
        ServiceCandidateRuntimeMaterializer(
            service,
            credential_resolver,
            base_environment=base_environment,
        ),
    )
    evidence_evaluator = ControlledEvidenceEvaluator(StructuredRubricRunner())
    executor = FormalEvaluationExecutor(runtime, evidence_evaluator)
    return ScenarioEvaluationComponents(
        repository=repository,
        service=service,
        run_manager=FormalEvaluationManager(repository, service, executor),
        publisher=PublishCandidateService(repository, service),
        evidence_evaluator=evidence_evaluator,
    )


def _create_repository(
    *,
    studio: bool,
    provider: StudioProvider,
    resolve_storage_credentials: CredentialResolver | None,
    storage_client_factory: TosClientFactory | None,
    storage_environment: Mapping[str, str] | None,
) -> ScenarioEvaluationRepository:
    if not studio:
        return InMemoryScenarioEvaluationRepository()

    storage = StudioStorageConfig.from_env(provider, storage_environment)
    if not storage.configured:
        return UnavailableScenarioEvaluationRepository(storage.unavailable_reason)

    client_factory: Callable[[], Any] | None = storage_client_factory
    if client_factory is None and resolve_storage_credentials is not None:
        client_factory = create_tos_client_factory(
            storage,
            resolve_storage_credentials,
        )
    if client_factory is None:
        return UnavailableScenarioEvaluationRepository(
            SCENARIO_STORAGE_CREDENTIALS_UNAVAILABLE
        )
    return TosScenarioEvaluationRepository(
        bucket=storage.bucket,
        client_factory=client_factory,
    )


__all__ = [
    "SCENARIO_STORAGE_CREDENTIALS_UNAVAILABLE",
    "ScenarioEvaluationComponents",
    "create_components",
]
