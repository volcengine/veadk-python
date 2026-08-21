"""Generated Agent runtime adapter for formal scenario evaluation."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from frontend.server.scenario_evaluation.executor import (
    EvaluationInfrastructureError,
    RuntimeEvidence,
    RuntimeHandle,
)
from frontend.server.scenario_evaluation.models import (
    CandidateProjectSnapshot,
    CandidateVersion,
    DatasetCase,
)
from veadk.cli.generated_agent_codegen import GeneratedFile, GeneratedProject
from veadk.cli.generated_agent_runtime import (
    GeneratedAgentRunEvidence,
    GeneratedAgentRuntimeError,
    GeneratedAgentRuntimeHandle,
)


@dataclass(frozen=True)
class CandidateRuntimeMaterialization:
    project: GeneratedProject
    environment: Mapping[str, str]


class CandidateRuntimeMaterializer(Protocol):
    async def materialize(
        self,
        candidate: CandidateVersion,
    ) -> CandidateRuntimeMaterialization: ...


class CandidateProjectService(Protocol):
    async def get_candidate_runtime_project(
        self,
        *,
        agent_id: str,
        project_snapshot_id: str,
    ) -> CandidateProjectSnapshot: ...


class CredentialReferenceResolver(Protocol):
    async def resolve(self, reference: str) -> str: ...


class AllowlistedCredentialReferenceResolver:
    """Resolve only explicit environment keys or server-side Ark key IDs."""

    _ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")

    def __init__(
        self,
        *,
        environment: Callable[[], Mapping[str, str]],
        ark_api_key_resolver: Callable[[str], str],
    ) -> None:
        self._environment = environment
        self._ark_api_key_resolver = ark_api_key_resolver

    async def resolve(self, reference: str) -> str:
        if reference.startswith("env://"):
            name = reference.removeprefix("env://")
            if not self._ENV_NAME.fullmatch(name):
                raise EvaluationInfrastructureError(
                    "Candidate credential reference is not supported."
                )
            value = str(self._environment().get(name) or "")
        elif reference.startswith("ark-api-key://"):
            key_id = reference.removeprefix("ark-api-key://").strip()
            if not key_id or "/" in key_id:
                raise EvaluationInfrastructureError(
                    "Candidate credential reference is not supported."
                )
            try:
                value = await asyncio.to_thread(
                    self._ark_api_key_resolver,
                    key_id,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                raise EvaluationInfrastructureError(
                    "Candidate credential reference is unavailable."
                ) from error
        else:
            raise EvaluationInfrastructureError(
                "Candidate credential reference is not supported."
            )
        if not value:
            raise EvaluationInfrastructureError(
                "Candidate credential reference is unavailable."
            )
        return value


class ServiceCandidateRuntimeMaterializer:
    def __init__(
        self,
        service: CandidateProjectService,
        credential_resolver: CredentialReferenceResolver,
        *,
        base_environment: Callable[[], Mapping[str, str]],
    ) -> None:
        self._service = service
        self._credential_resolver = credential_resolver
        self._base_environment = base_environment

    async def materialize(
        self,
        candidate: CandidateVersion,
    ) -> CandidateRuntimeMaterialization:
        project_ref = candidate.artifact.runtime_project_ref
        if not project_ref:
            raise EvaluationInfrastructureError(
                "Candidate has no generated runtime project snapshot."
            )
        snapshot = await self._service.get_candidate_runtime_project(
            agent_id=candidate.agent_id,
            project_snapshot_id=project_ref,
        )
        if (
            snapshot.candidate_id != candidate.candidate_id
            or snapshot.agent_id != candidate.agent_id
        ):
            raise EvaluationInfrastructureError(
                "Candidate runtime project snapshot does not match the Candidate."
            )
        harness_sidecar = snapshot.deployment_profile.get("harnessSidecar")
        if isinstance(harness_sidecar, Mapping) and harness_sidecar.get("enabled"):
            raise EvaluationInfrastructureError(
                "Formal evaluation cannot attest Harness Sidecar locally; "
                "use the explicit risk publication path until an isolated "
                "Sidecar evaluation Runtime is configured."
            )
        environment = dict(self._base_environment())
        names: set[str] = set()
        for item in candidate.artifact.environment_refs:
            if item.name in names:
                raise EvaluationInfrastructureError(
                    f"Candidate environment reference {item.name!r} is duplicated."
                )
            names.add(item.name)
            value = await self._credential_resolver.resolve(item.reference)
            if not value:
                raise EvaluationInfrastructureError(
                    f"Candidate environment reference {item.name!r} is unavailable."
                )
            environment[item.name] = value
        return CandidateRuntimeMaterialization(
            project=GeneratedProject(
                name=snapshot.name,
                files=[
                    GeneratedFile(path=item.path, content=item.content)
                    for item in snapshot.files
                ],
            ),
            environment=environment,
        )


class GeneratedRuntimeManager(Protocol):
    async def create(
        self,
        project: GeneratedProject,
        *,
        environment: Mapping[str, str],
        owner_id: str,
    ) -> GeneratedAgentRuntimeHandle: ...

    async def create_session(
        self,
        handle: GeneratedAgentRuntimeHandle,
        *,
        user_id: str,
    ) -> str: ...

    async def run_case(
        self,
        handle: GeneratedAgentRuntimeHandle,
        *,
        user_id: str,
        session_id: str,
        prompt: str,
    ) -> GeneratedAgentRunEvidence: ...

    async def close(self, handle: GeneratedAgentRuntimeHandle) -> None: ...


class GeneratedAgentEvaluationRuntime:
    def __init__(
        self,
        manager: GeneratedRuntimeManager,
        materializer: CandidateRuntimeMaterializer,
        *,
        evaluation_user_id: str = "scenario-evaluation",
    ) -> None:
        self._manager = manager
        self._materializer = materializer
        self._evaluation_user_id = evaluation_user_id
        self._handles: dict[str, GeneratedAgentRuntimeHandle] = {}
        self._lock = asyncio.Lock()

    async def create(self, candidate: CandidateVersion) -> RuntimeHandle:
        try:
            materialization = await self._materializer.materialize(candidate)
            generated = await self._manager.create(
                materialization.project,
                environment=materialization.environment,
                owner_id=candidate.created_by,
            )
        except GeneratedAgentRuntimeError as error:
            raise EvaluationInfrastructureError(error.detail) from error
        async with self._lock:
            duplicate = generated.runtime_id in self._handles
            if not duplicate:
                self._handles[generated.runtime_id] = generated
        if duplicate:
            await self._manager.close(generated)
            raise EvaluationInfrastructureError(
                "Generated Agent runtime identifier already exists."
            )
        return RuntimeHandle(
            runtime_id=generated.runtime_id,
            candidate_id=candidate.candidate_id,
        )

    async def run_case(
        self,
        handle: RuntimeHandle,
        case: DatasetCase,
        *,
        session_id: str,
        attempt_index: int,
    ) -> RuntimeEvidence:
        del attempt_index
        del session_id
        async with self._lock:
            generated = self._handles.get(handle.runtime_id)
        if generated is None:
            raise EvaluationInfrastructureError(
                "Generated Agent evaluation runtime is unavailable."
            )
        try:
            runtime_session_id = await self._manager.create_session(
                generated,
                user_id=self._evaluation_user_id,
            )
            evidence = await self._manager.run_case(
                generated,
                user_id=self._evaluation_user_id,
                session_id=runtime_session_id,
                prompt=case.input,
            )
        except GeneratedAgentRuntimeError as error:
            raise EvaluationInfrastructureError(error.detail) from error
        return RuntimeEvidence(
            output=evidence.output,
            trace_ref=evidence.trace_ref,
            session_id=runtime_session_id,
            trace_json=json.dumps(
                evidence.trace,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )

    async def close(self, handle: RuntimeHandle) -> None:
        async with self._lock:
            generated = self._handles.pop(handle.runtime_id, None)
        if generated is None:
            return
        try:
            await self._manager.close(generated)
        except GeneratedAgentRuntimeError as error:
            raise EvaluationInfrastructureError(error.detail) from error
