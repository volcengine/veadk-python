from __future__ import annotations

import pytest

from frontend.server.scenario_evaluation.evaluators import (
    ControlledEvidenceEvaluator,
    RubricDecision,
)
from frontend.server.scenario_evaluation.executor import (
    EvaluationInfrastructureError,
    RuntimeEvidence,
)
from frontend.server.scenario_evaluation.models import (
    AttemptOutcome,
    DatasetCase,
    DeterministicRule,
    EvaluatorKind,
    EvaluatorVersion,
)
from datetime import datetime, timezone


def _case() -> DatasetCase:
    return DatasetCase(
        case_id="case-1",
        input="订单为什么还没到？",
        expected_output="预计今天送达",
        forbidden_output=("已经签收",),
    )


def _evaluator(
    rule: DeterministicRule | None,
    *,
    kind: EvaluatorKind = EvaluatorKind.DETERMINISTIC,
    rubric: str = "",
    hard_failure: bool = False,
) -> EvaluatorVersion:
    return EvaluatorVersion(
        evaluator_version_id="evaluator:v1",
        evaluator_id="evaluator",
        agent_id="agent-1",
        version=1,
        source_draft_revision=1,
        name="检查器",
        kind=kind,
        rule=rule,
        rubric=rubric,
        hard_failure=hard_failure,
        created_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        created_by="admin-1",
    )


@pytest.mark.asyncio
async def test_controlled_rules_use_output_expected_and_persisted_trace() -> None:
    evaluator = ControlledEvidenceEvaluator()
    evidence = RuntimeEvidence(
        output="查询结果显示预计今天送达",
        trace_ref="trace:1",
        trace_json='[{"name":"call_tool logistics"}]',
    )

    expected = await evaluator.evaluate(
        _evaluator(DeterministicRule.OUTPUT_CONTAINS_EXPECTED),
        _case(),
        evidence,
        attempt_index=1,
    )
    tool = await evaluator.evaluate(
        _evaluator(DeterministicRule.OUTPUT_CONTAINS_TOOL_EVIDENCE),
        _case(),
        evidence,
        attempt_index=1,
    )
    forbidden = await evaluator.evaluate(
        _evaluator(DeterministicRule.OUTPUT_EXCLUDES_FORBIDDEN),
        _case(),
        evidence,
        attempt_index=1,
    )

    assert expected.outcome is AttemptOutcome.PASS
    assert tool.outcome is AttemptOutcome.PASS
    assert forbidden.outcome is AttemptOutcome.PASS


@pytest.mark.asyncio
async def test_hard_failure_is_set_only_when_the_controlled_check_fails() -> None:
    evaluator = ControlledEvidenceEvaluator()

    result = await evaluator.evaluate(
        _evaluator(
            DeterministicRule.OUTPUT_EXCLUDES_FORBIDDEN,
            hard_failure=True,
        ),
        _case(),
        RuntimeEvidence(output="订单已经签收", trace_ref="trace:1"),
        attempt_index=1,
    )

    assert result.outcome is AttemptOutcome.FAIL
    assert result.hard_failure is True
    assert result.reason


class _RubricRunner:
    def __init__(self, decision: RubricDecision | Exception) -> None:
        self.decision = decision

    async def evaluate(self, **kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["rubric"] == "回答必须引用物流查询结果"
        if isinstance(self.decision, Exception):
            raise self.decision
        return self.decision


@pytest.mark.asyncio
async def test_llm_rubric_requires_structured_decision() -> None:
    evaluator = ControlledEvidenceEvaluator(
        _RubricRunner(RubricDecision(passed=False, reason="没有引用查询结果"))
    )

    result = await evaluator.evaluate(
        _evaluator(
            None,
            kind=EvaluatorKind.LLM_RUBRIC,
            rubric="回答必须引用物流查询结果",
        ),
        _case(),
        RuntimeEvidence(output="稍后送达", trace_ref="trace:1"),
        attempt_index=1,
    )

    assert result.outcome is AttemptOutcome.FAIL
    assert result.reason == "没有引用查询结果"


@pytest.mark.asyncio
async def test_llm_rubric_failure_is_retryable_infrastructure_error() -> None:
    evaluator = ControlledEvidenceEvaluator(_RubricRunner(TimeoutError("timeout")))

    with pytest.raises(EvaluationInfrastructureError):
        await evaluator.evaluate(
            _evaluator(
                None,
                kind=EvaluatorKind.LLM_RUBRIC,
                rubric="回答必须引用物流查询结果",
            ),
            _case(),
            RuntimeEvidence(output="稍后送达", trace_ref="trace:1"),
            attempt_index=1,
        )
