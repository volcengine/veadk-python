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
        pass_criteria=("说明当前物流状态", "说明预计送达时间"),
        forbidden_output=("已经签收",),
    )


def _evaluator(
    rule: DeterministicRule | None,
    *,
    kind: EvaluatorKind = EvaluatorKind.DETERMINISTIC,
    rubric: str = "",
    regex_pattern: str = "",
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
        regex_pattern=regex_pattern,
        hard_failure=hard_failure,
        scene_name="物流查询",
        scene_user_task="查询订单物流并解释预计送达时间",
        scene_pass_criteria=("先查询真实物流状态", "不得虚构预计时间"),
        scene_hard_failure_conditions=("不得声称未查询的订单已经签收",),
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
        self.calls: list[dict[str, object]] = []

    async def evaluate(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        if isinstance(self.decision, Exception):
            raise self.decision
        return self.decision


@pytest.mark.asyncio
async def test_llm_rubric_requires_structured_decision() -> None:
    runner = _RubricRunner(
        RubricDecision(
            passed=False,
            hard_failure=False,
            reason="没有引用查询结果",
        )
    )
    evaluator = ControlledEvidenceEvaluator(runner)

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
    assert runner.calls[0]["rubric"] == "回答必须引用物流查询结果"
    criteria = runner.calls[0]["criteria"]
    assert criteria.__class__.__name__ == "EvaluationCriteriaContext"
    assert criteria.model_dump(by_alias=True) == {
        "sceneVersionId": "",
        "sceneName": "物流查询",
        "sceneUserTask": "查询订单物流并解释预计送达时间",
        "scenePassCriteria": ("先查询真实物流状态", "不得虚构预计时间"),
        "sceneHardFailureConditions": ("不得声称未查询的订单已经签收",),
        "caseId": "case-1",
        "userInput": "订单为什么还没到？",
        "expectedOutput": "预计今天送达",
        "casePassCriteria": ("说明当前物流状态", "说明预计送达时间"),
        "forbiddenOutput": ("已经签收",),
    }


@pytest.mark.asyncio
async def test_llm_rubric_propagates_automatic_scene_hard_failure() -> None:
    evaluator = ControlledEvidenceEvaluator(
        _RubricRunner(
            RubricDecision(
                passed=False,
                hard_failure=True,
                reason="命中场景硬失败条件：不得声称未查询的订单已经签收",
            )
        )
    )

    result = await evaluator.evaluate(
        _evaluator(None, kind=EvaluatorKind.LLM_RUBRIC),
        _case(),
        RuntimeEvidence(output="订单已经签收", trace_ref="trace:1"),
        attempt_index=1,
    )

    assert result.outcome is AttemptOutcome.FAIL
    assert result.hard_failure is True


def test_llm_rubric_rejects_a_passing_hard_failure_decision() -> None:
    with pytest.raises(ValueError, match="hard failure decision cannot pass"):
        RubricDecision(passed=True, hard_failure=True, reason="contradictory")


def test_llm_rubric_requires_an_explicit_hard_failure_decision() -> None:
    with pytest.raises(ValueError, match="hard_failure"):
        RubricDecision(passed=False, reason="missing classification")


@pytest.mark.asyncio
async def test_regex_rules_are_deterministic_and_do_not_require_an_llm() -> None:
    evaluator = ControlledEvidenceEvaluator()
    evidence = RuntimeEvidence(
        output="订单号：AB123，预计今天送达",
        trace_ref="trace:1",
    )

    required = await evaluator.evaluate(
        _evaluator(
            DeterministicRule.OUTPUT_MATCHES_REGEX,
            regex_pattern=r"订单号[:：]\s*[A-Z]{2}\d+",
        ),
        _case(),
        evidence,
        attempt_index=1,
    )
    forbidden = await evaluator.evaluate(
        _evaluator(
            DeterministicRule.OUTPUT_EXCLUDES_REGEX,
            regex_pattern=r"保证.{0,8}到账|百分之百成功",
            hard_failure=True,
        ),
        _case(),
        evidence,
        attempt_index=1,
    )

    assert required.outcome is AttemptOutcome.PASS
    assert forbidden.outcome is AttemptOutcome.PASS


@pytest.mark.asyncio
async def test_regex_timeout_is_reported_as_evaluator_infrastructure_error() -> None:
    evaluator = ControlledEvidenceEvaluator()

    with pytest.raises(
        EvaluationInfrastructureError, match="regular expression timed out"
    ):
        await evaluator.evaluate(
            _evaluator(
                DeterministicRule.OUTPUT_MATCHES_REGEX,
                regex_pattern=r"(a+)+$",
            ),
            _case(),
            RuntimeEvidence(output="a" * 50_000 + "!", trace_ref="trace:1"),
            attempt_index=1,
        )


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
