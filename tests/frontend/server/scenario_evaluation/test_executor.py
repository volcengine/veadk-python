from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone

import pytest

from frontend.server.scenario_evaluation.executor import (
    EvaluationExecutionPlan,
    EvaluationInfrastructureError,
    FormalEvaluationExecutor,
    RuntimeEvidence,
    RuntimeHandle,
    SceneExecutionPlan,
)
from frontend.server.scenario_evaluation.models import (
    AttemptOutcome,
    CandidateArtifact,
    CandidateVersion,
    DatasetCase,
    DeterministicRule,
    EvaluationRequirement,
    EvaluatorEvidence,
    EvaluatorKind,
    EvaluatorVersion,
)


def _candidate(candidate_id: str) -> CandidateVersion:
    return CandidateVersion(
        candidate_id=candidate_id,
        agent_id="agent-1",
        version=1,
        artifact=CandidateArtifact(
            code_digest=f"sha256:{candidate_id}",
            topology_digest="sha256:topology",
        ),
        created_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        created_by="developer-1",
    )


def _case(case_id: str = "case-1") -> DatasetCase:
    return DatasetCase(
        case_id=case_id,
        input="订单为什么还没到？",
        expected_output="先查询物流状态，再回答预计送达时间。",
    )


def _evaluator(*, hard_failure: bool = False) -> EvaluatorVersion:
    return EvaluatorVersion(
        evaluator_version_id="evaluator:v1",
        evaluator_id="evaluator",
        agent_id="agent-1",
        version=1,
        source_draft_revision=1,
        name="事实依据检查",
        kind=EvaluatorKind.DETERMINISTIC,
        rule=DeterministicRule.OUTPUT_CONTAINS_TOOL_EVIDENCE,
        hard_failure=hard_failure,
        created_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        created_by="admin-1",
    )


def _plan(*, baseline: CandidateVersion | None = None) -> EvaluationExecutionPlan:
    return EvaluationExecutionPlan(
        candidate=_candidate("candidate"),
        baseline=baseline,
        scenes=(
            SceneExecutionPlan(
                scene_version_id="scene:v1",
                requirement=EvaluationRequirement.MUST_PASS,
                cases=(_case(),),
                evaluators=(_evaluator(),),
            ),
        ),
    )


class _FakeRuntime:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.closed: list[str] = []
        self.calls: list[tuple[str, str, str]] = []
        self.failures: dict[tuple[str, int], int] = defaultdict(int)
        self.block = False
        self.started = asyncio.Event()

    async def create(self, candidate: CandidateVersion) -> RuntimeHandle:
        self.created.append(candidate.candidate_id)
        return RuntimeHandle(
            runtime_id=f"runtime-{candidate.candidate_id}",
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
        self.calls.append((handle.candidate_id, case.case_id, session_id))
        self.started.set()
        if self.block:
            await asyncio.Event().wait()
        key = (handle.candidate_id, attempt_index)
        if self.failures[key] > 0:
            self.failures[key] -= 1
            raise EvaluationInfrastructureError("runtime unavailable")
        return RuntimeEvidence(
            output=f"output:{handle.candidate_id}:{attempt_index}",
            trace_ref=f"trace:{session_id}",
        )

    async def close(self, handle: RuntimeHandle) -> None:
        self.closed.append(handle.candidate_id)


class _FakeEvaluator:
    def __init__(self, outcomes: tuple[AttemptOutcome, ...] | None = None) -> None:
        self.outcomes = outcomes or (AttemptOutcome.PASS,) * 3
        self.calls = 0

    async def evaluate(
        self,
        evaluator: EvaluatorVersion,
        case: DatasetCase,
        evidence: RuntimeEvidence,
        *,
        attempt_index: int,
    ) -> EvaluatorEvidence:
        del case, evidence
        self.calls += 1
        return EvaluatorEvidence(
            evaluator_version_id=evaluator.evaluator_version_id,
            outcome=self.outcomes[attempt_index - 1],
            hard_failure=(
                evaluator.hard_failure
                and self.outcomes[attempt_index - 1] is AttemptOutcome.FAIL
            ),
        )


class _SessionIds:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"session-{self.value}"


@pytest.mark.asyncio
async def test_candidate_and_baseline_each_run_three_independent_sessions() -> None:
    runtime = _FakeRuntime()
    executor = FormalEvaluationExecutor(
        runtime,
        _FakeEvaluator(),
        session_id_factory=_SessionIds(),
    )

    result = await executor.execute(_plan(baseline=_candidate("baseline")))

    case = result.scenes[0].cases[0]
    assert runtime.created == ["candidate", "baseline"]
    assert len(case.candidate_attempts) == 3
    assert len(case.baseline_attempts) == 3
    assert len({session_id for _, _, session_id in runtime.calls}) == 6
    assert runtime.closed == ["baseline", "candidate"]


@pytest.mark.asyncio
async def test_first_release_runs_only_absolute_candidate_evidence() -> None:
    runtime = _FakeRuntime()
    executor = FormalEvaluationExecutor(
        runtime,
        _FakeEvaluator(),
        session_id_factory=_SessionIds(),
    )

    result = await executor.execute(_plan())

    assert runtime.created == ["candidate"]
    assert result.scenes[0].cases[0].baseline_attempts == ()
    assert len(runtime.calls) == 3


@pytest.mark.asyncio
async def test_infrastructure_failure_retries_once_without_adding_business_attempt() -> (
    None
):
    runtime = _FakeRuntime()
    runtime.failures[("candidate", 2)] = 1
    executor = FormalEvaluationExecutor(
        runtime,
        _FakeEvaluator(),
        session_id_factory=_SessionIds(),
    )

    result = await executor.execute(_plan())

    attempts = result.scenes[0].cases[0].candidate_attempts
    assert len(attempts) == 3
    assert attempts[1].retry_count == 1
    assert len(runtime.calls) == 4
    assert len({session_id for _, _, session_id in runtime.calls}) == 4


@pytest.mark.asyncio
async def test_second_infrastructure_failure_becomes_indeterminate_evidence() -> None:
    runtime = _FakeRuntime()
    runtime.failures[("candidate", 2)] = 2
    executor = FormalEvaluationExecutor(
        runtime,
        _FakeEvaluator(),
        session_id_factory=_SessionIds(),
    )

    result = await executor.execute(_plan())

    attempt = result.scenes[0].cases[0].candidate_attempts[1]
    assert attempt.outcome is AttemptOutcome.INFRA_ERROR
    assert attempt.retry_count == 1
    assert attempt.evaluator_results == ()


@pytest.mark.asyncio
async def test_valid_business_failure_never_triggers_runtime_retry() -> None:
    runtime = _FakeRuntime()
    executor = FormalEvaluationExecutor(
        runtime,
        _FakeEvaluator((AttemptOutcome.PASS, AttemptOutcome.FAIL, AttemptOutcome.FAIL)),
        session_id_factory=_SessionIds(),
    )

    result = await executor.execute(_plan())

    assert [item.outcome for item in result.scenes[0].cases[0].candidate_attempts] == [
        AttemptOutcome.PASS,
        AttemptOutcome.FAIL,
        AttemptOutcome.FAIL,
    ]
    assert len(runtime.calls) == 3


@pytest.mark.asyncio
async def test_cancellation_closes_runtime_and_propagates_cancelled_error() -> None:
    runtime = _FakeRuntime()
    runtime.block = True
    executor = FormalEvaluationExecutor(
        runtime,
        _FakeEvaluator(),
        session_id_factory=_SessionIds(),
    )
    task = asyncio.create_task(executor.execute(_plan()))
    await runtime.started.wait()

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert runtime.closed == ["candidate"]
