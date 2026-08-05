from __future__ import annotations

from typing import Any

import pytest

from frontend.server.evaluation_automation.models import (
    AutoEvaluationCase,
    AutoEvaluationOutput,
    OptimizationGroup,
    OptimizationOutput,
    OptimizationSuggestion,
    RunSseActivity,
)
from frontend.server.evaluation_automation.repository import (
    InMemoryOptimizationRepository,
)
from frontend.server.evaluation_automation.scheduler import QuietSessionScheduler
from frontend.server.evaluation_automation.service import EvaluationAutomationService


class _Evaluator:
    async def evaluate(self, **kwargs: Any) -> AutoEvaluationOutput:
        assert kwargs["user_input"] == "问题"
        assert kwargs["agent_output"] == "回答"
        return AutoEvaluationOutput(score=0.92, reason="回答准确且完整。")


class _Optimizer:
    async def optimize(self, **kwargs: Any) -> OptimizationOutput:
        assert kwargs["cases"][0].score == 0.92
        return OptimizationOutput(
            groups=[
                OptimizationGroup(
                    priority="medium",
                    module="prompt",
                    customModule=None,
                    items=[
                        OptimizationSuggestion(
                            suggestion="补充回答格式",
                            reason="让输出结构更加稳定。",
                        )
                    ],
                )
            ]
        )


class _CaseRepository:
    def __init__(self) -> None:
        self.items: dict[str, AutoEvaluationCase] = {}

    async def upsert(self, case: AutoEvaluationCase) -> AutoEvaluationCase:
        self.items[case.item_key] = case
        return case

    async def list_cases(
        self, *, agent_name: str, page_size: int = 100
    ) -> list[AutoEvaluationCase]:
        del agent_name, page_size
        return list(self.items.values())


def _activity() -> RunSseActivity:
    return RunSseActivity.from_proxy(
        {"app_name": "agent", "user_id": "user", "session_id": "session"},
        runtime_id="runtime",
        region="cn-beijing",
        project_name="support",
        runtime_endpoint="https://runtime.example",
        runtime_authorization="Bearer secret",
    )


@pytest.mark.asyncio
async def test_service_evaluates_latest_turn_and_updates_optimization_snapshot() -> (
    None
):
    cases = _CaseRepository()
    optimizations = InMemoryOptimizationRepository()

    async def runtime_get(activity: RunSseActivity, path: str) -> dict[str, Any]:
        del activity
        if path.endswith("/sessions/session"):
            return {
                "id": "session",
                "events": [
                    {
                        "id": "user-event",
                        "author": "user",
                        "content": {"parts": [{"text": "问题"}]},
                    },
                    {
                        "id": "assistant-event",
                        "author": "agent",
                        "timestamp": "2026-08-05T10:00:00+08:00",
                        "invocationId": "invocation",
                        "content": {"parts": [{"text": "回答"}]},
                    },
                ],
            }
        if path == "web/agent-info/agent":
            return {"name": "客服助手", "model": "test-model"}
        raise AssertionError(path)

    async def case_repository(activity: RunSseActivity) -> _CaseRepository:
        del activity
        return cases

    scheduler: QuietSessionScheduler | None = None
    service = EvaluationAutomationService(
        evaluator=_Evaluator(),
        optimizer=_Optimizer(),
        optimization_repository=optimizations,
        runtime_get=runtime_get,
        case_repository=case_repository,
        quiet_seconds=0,
    )
    scheduler = service.scheduler

    service.session_completed(_activity())
    await scheduler.wait_idle()

    assert len(cases.items) == 1
    case = next(iter(cases.items.values()))
    assert case.kind == "good"
    assert case.source == "auto"
    assert case.reason == "回答准确且完整。"
    snapshot = optimizations.get("runtime", "agent")
    assert snapshot is not None
    assert snapshot.groups[0].module == "prompt"
    await service.close()


@pytest.mark.asyncio
async def test_reprocessing_the_same_event_uses_the_same_item_key() -> None:
    cases = _CaseRepository()

    async def runtime_get(activity: RunSseActivity, path: str) -> dict[str, Any]:
        del activity
        if "sessions" in path:
            return {
                "id": "session",
                "events": [
                    {
                        "id": "user-event",
                        "author": "user",
                        "content": {"parts": [{"text": "问题"}]},
                    },
                    {
                        "id": "assistant-event",
                        "author": "agent",
                        "content": {"parts": [{"text": "回答"}]},
                    },
                ],
            }
        return {"name": "客服助手"}

    async def case_repository(activity: RunSseActivity) -> _CaseRepository:
        del activity
        return cases

    service = EvaluationAutomationService(
        evaluator=_Evaluator(),
        optimizer=_Optimizer(),
        optimization_repository=InMemoryOptimizationRepository(),
        runtime_get=runtime_get,
        case_repository=case_repository,
        quiet_seconds=0,
    )

    await service.evaluate_now(_activity())
    first_key = next(iter(cases.items))
    await service.evaluate_now(_activity())

    assert list(cases.items) == [first_key]
    await service.close()
