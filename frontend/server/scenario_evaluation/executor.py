"""Asynchronous execution of immutable scenario-evaluation plans."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from frontend.server.scenario_evaluation.models import (
    AttemptEvidence,
    AttemptOutcome,
    CandidateVersion,
    CaseEvidence,
    DatasetCase,
    EvaluationRequirement,
    EvaluatorEvidence,
    EvaluatorVersion,
    SceneEvidence,
)


class EvaluationInfrastructureError(RuntimeError):
    """A retryable Runtime or evaluator infrastructure failure."""


@dataclass(frozen=True)
class RuntimeHandle:
    runtime_id: str
    candidate_id: str


@dataclass(frozen=True)
class RuntimeEvidence:
    output: str
    trace_ref: str
    session_id: str = ""
    trace_json: str = ""


@dataclass(frozen=True)
class SceneExecutionPlan:
    scene_version_id: str
    requirement: EvaluationRequirement
    cases: tuple[DatasetCase, ...]
    evaluators: tuple[EvaluatorVersion, ...]

    def __post_init__(self) -> None:
        if not self.cases:
            raise ValueError("scene execution plan requires at least one case")
        if not self.evaluators:
            raise ValueError("scene execution plan requires at least one evaluator")


@dataclass(frozen=True)
class EvaluationExecutionPlan:
    candidate: CandidateVersion
    scenes: tuple[SceneExecutionPlan, ...]
    baseline: CandidateVersion | None = None

    def __post_init__(self) -> None:
        if not self.scenes:
            raise ValueError("evaluation execution plan requires at least one scene")


@dataclass(frozen=True)
class EvaluationExecutionResult:
    scenes: tuple[SceneEvidence, ...]


class EvaluationRuntime(Protocol):
    async def create(self, candidate: CandidateVersion) -> RuntimeHandle: ...

    async def run_case(
        self,
        handle: RuntimeHandle,
        case: DatasetCase,
        *,
        session_id: str,
        attempt_index: int,
    ) -> RuntimeEvidence: ...

    async def close(self, handle: RuntimeHandle) -> None: ...


class EvidenceEvaluator(Protocol):
    async def evaluate(
        self,
        evaluator: EvaluatorVersion,
        case: DatasetCase,
        evidence: RuntimeEvidence,
        *,
        attempt_index: int,
    ) -> EvaluatorEvidence: ...


def _default_session_id() -> str:
    return f"evaluation-{uuid4().hex}"


class FormalEvaluationExecutor:
    def __init__(
        self,
        runtime: EvaluationRuntime,
        evaluator: EvidenceEvaluator,
        *,
        session_id_factory: Callable[[], str] | None = None,
        max_concurrency: int = 3,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        self._runtime = runtime
        self._evaluator = evaluator
        self._session_id_factory = session_id_factory or _default_session_id
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute(
        self,
        plan: EvaluationExecutionPlan,
    ) -> EvaluationExecutionResult:
        handles: list[RuntimeHandle] = []
        try:
            candidate_handle = await self._runtime.create(plan.candidate)
            handles.append(candidate_handle)
            baseline_handle: RuntimeHandle | None = None
            if plan.baseline is not None:
                baseline_handle = await self._runtime.create(plan.baseline)
                handles.append(baseline_handle)

            scenes = await asyncio.gather(
                *(
                    self._execute_scene(
                        scene,
                        candidate_handle=candidate_handle,
                        baseline_handle=baseline_handle,
                    )
                    for scene in plan.scenes
                )
            )
            return EvaluationExecutionResult(scenes=tuple(scenes))
        finally:
            active_exception = sys.exc_info()[0] is not None
            close_errors: list[Exception] = []
            for handle in reversed(handles):
                try:
                    await self._runtime.close(handle)
                except Exception as error:  # noqa: BLE001 - close every owned handle
                    close_errors.append(error)
            if close_errors and not active_exception:
                raise close_errors[0]

    async def retry_invalid_attempt(
        self,
        *,
        candidate: CandidateVersion,
        case: DatasetCase,
        evaluators: tuple[EvaluatorVersion, ...],
        attempt_index: int,
    ) -> AttemptEvidence:
        handle: RuntimeHandle | None = None
        try:
            handle = await self._runtime.create(candidate)
            async with self._semaphore:
                return await self._execute_attempt(
                    handle,
                    case,
                    evaluators,
                    attempt_index=attempt_index,
                )
        finally:
            if handle is not None:
                await self._runtime.close(handle)

    async def _execute_scene(
        self,
        scene: SceneExecutionPlan,
        *,
        candidate_handle: RuntimeHandle,
        baseline_handle: RuntimeHandle | None,
    ) -> SceneEvidence:
        cases = await asyncio.gather(
            *(
                self._execute_case(
                    case,
                    scene=scene,
                    candidate_handle=candidate_handle,
                    baseline_handle=baseline_handle,
                )
                for case in scene.cases
            )
        )
        return SceneEvidence(
            scene_version_id=scene.scene_version_id,
            requirement=scene.requirement,
            cases=tuple(cases),
        )

    async def _execute_case(
        self,
        case: DatasetCase,
        *,
        scene: SceneExecutionPlan,
        candidate_handle: RuntimeHandle,
        baseline_handle: RuntimeHandle | None,
    ) -> CaseEvidence:
        async with self._semaphore:
            candidate_attempts = await self._execute_attempts(
                candidate_handle,
                case,
                scene.evaluators,
            )
            baseline_attempts: tuple[AttemptEvidence, ...] = ()
            if baseline_handle is not None:
                baseline_attempts = await self._execute_attempts(
                    baseline_handle,
                    case,
                    scene.evaluators,
                )
        return CaseEvidence(
            case_version_id=case.case_id,
            scene_version_id=scene.scene_version_id,
            requirement=scene.requirement,
            candidate_attempts=candidate_attempts,
            baseline_attempts=baseline_attempts,
        )

    async def _execute_attempts(
        self,
        handle: RuntimeHandle,
        case: DatasetCase,
        evaluators: tuple[EvaluatorVersion, ...],
    ) -> tuple[AttemptEvidence, ...]:
        results: list[AttemptEvidence] = []
        for attempt_index in range(1, 4):
            results.append(
                await self._execute_attempt(
                    handle,
                    case,
                    evaluators,
                    attempt_index=attempt_index,
                )
            )
        return tuple(results)

    async def _execute_attempt(
        self,
        handle: RuntimeHandle,
        case: DatasetCase,
        evaluators: tuple[EvaluatorVersion, ...],
        *,
        attempt_index: int,
    ) -> AttemptEvidence:
        last_session_id = ""
        for retry_count in range(2):
            last_session_id = self._session_id_factory()
            try:
                runtime_evidence = await self._runtime.run_case(
                    handle,
                    case,
                    session_id=last_session_id,
                    attempt_index=attempt_index,
                )
                evaluator_results = tuple(
                    await asyncio.gather(
                        *(
                            self._evaluator.evaluate(
                                evaluator,
                                case,
                                runtime_evidence,
                                attempt_index=attempt_index,
                            )
                            for evaluator in evaluators
                        )
                    )
                )
            except EvaluationInfrastructureError as error:
                if retry_count == 0:
                    continue
                return AttemptEvidence(
                    attempt_index=attempt_index,
                    outcome=AttemptOutcome.INFRA_ERROR,
                    retry_count=1,
                    session_id=last_session_id,
                    error_message=str(error),
                )

            outcome = (
                AttemptOutcome.PASS
                if all(
                    item.outcome is AttemptOutcome.PASS for item in evaluator_results
                )
                else AttemptOutcome.FAIL
            )
            return AttemptEvidence(
                attempt_index=attempt_index,
                outcome=outcome,
                retry_count=retry_count,
                evaluator_results=evaluator_results,
                session_id=last_session_id,
                output=runtime_evidence.output,
                trace_ref=runtime_evidence.trace_ref,
                trace_json=runtime_evidence.trace_json,
            )
        raise AssertionError("evaluation attempt retry loop did not return")
