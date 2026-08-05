"""Orchestration from Studio session completion to optimization suggestions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from urllib.parse import quote

from veadk.integrations.agentkit.evaluation.feedback import extract_feedback_sample
from veadk.utils.logger import get_logger

from .model_gateway import EVALUATOR_VERSION, OPTIMIZER_VERSION
from .models import (
    AutoEvaluationCase,
    AutoEvaluationOutput,
    OptimizationOutput,
    OptimizationSnapshot,
    RunSseActivity,
)
from .repository import InMemoryOptimizationRepository, auto_item_key
from .scheduler import QuietSessionScheduler

logger = get_logger(__name__)
GOOD_SCORE_THRESHOLD = 0.6


class Evaluator(Protocol):
    async def evaluate(
        self, *, user_input: str, agent_output: str, agent_info: dict[str, Any]
    ) -> AutoEvaluationOutput: ...


class Optimizer(Protocol):
    async def optimize(
        self, *, agent_info: dict[str, Any], cases: list[AutoEvaluationCase]
    ) -> OptimizationOutput: ...


class CaseRepository(Protocol):
    async def upsert(self, case: AutoEvaluationCase) -> AutoEvaluationCase: ...

    async def list_cases(
        self, *, agent_name: str, page_size: int = 100
    ) -> list[AutoEvaluationCase]: ...


RuntimeGet = Callable[[RunSseActivity, str], Awaitable[dict[str, Any]]]
CaseRepositoryFactory = Callable[[RunSseActivity], Awaitable[CaseRepository]]


class EvaluationAutomationService:
    def __init__(
        self,
        *,
        evaluator: Evaluator,
        optimizer: Optimizer,
        optimization_repository: InMemoryOptimizationRepository,
        runtime_get: RuntimeGet,
        case_repository: CaseRepositoryFactory,
        quiet_seconds: float = 300,
    ) -> None:
        self._evaluator = evaluator
        self._optimizer = optimizer
        self._optimizations = optimization_repository
        self._runtime_get = runtime_get
        self._case_repository = case_repository
        self.scheduler = QuietSessionScheduler(
            quiet_seconds,
            self.evaluate_now,
        )

    def session_started(self, activity: RunSseActivity) -> None:
        self.scheduler.invalidate(activity.key)

    def session_completed(self, activity: RunSseActivity) -> None:
        self.scheduler.schedule(activity)

    async def evaluate_now(self, activity: RunSseActivity) -> None:
        session_path = (
            f"apps/{quote(activity.app_name, safe='')}/users/"
            f"{quote(activity.user_id, safe='')}/sessions/"
            f"{quote(activity.session_id, safe='')}"
        )
        session = await self._runtime_get(activity, session_path)
        event_id = _latest_assistant_event_id(session)
        agent_info = await self._agent_info(activity)
        agent_name = str(agent_info.get("name") or activity.app_name)
        sample = extract_feedback_sample(
            session,
            target_event_id=event_id,
            runtime_id=activity.runtime_id,
            agent_name=agent_name,
            user_id=activity.user_id,
        )
        evaluation = await self._evaluator.evaluate(
            user_input=sample.input,
            agent_output=sample.output,
            agent_info=agent_info,
        )
        kind = "good" if evaluation.score >= GOOD_SCORE_THRESHOLD else "bad"
        repository = await self._case_repository(activity)
        item_key = auto_item_key(
            project_name=activity.project_name,
            runtime_id=activity.runtime_id,
            session_id=activity.session_id,
            message_id=sample.message_id,
            evaluator_version=EVALUATOR_VERSION,
        )
        case = await repository.upsert(
            AutoEvaluationCase(
                itemKey=item_key,
                kind=kind,
                input=sample.input,
                output=sample.output,
                agentName=agent_name,
                sessionId=sample.session_id,
                messageId=sample.message_id,
                runtimeId=sample.runtime_id,
                invocationId=sample.invocation_id,
                userId=sample.user_id,
                createdAt=sample.created_at,
                score=evaluation.score,
                reason=evaluation.reason,
                evaluatorVersion=EVALUATOR_VERSION,
            )
        )
        try:
            cases = await repository.list_cases(agent_name=agent_name, page_size=100)
            output = await self._optimizer.optimize(
                agent_info=agent_info,
                cases=cases,
            )
            self._optimizations.put(
                OptimizationSnapshot(
                    runtimeId=activity.runtime_id,
                    appName=activity.app_name,
                    optimizerVersion=OPTIMIZER_VERSION,
                    sourceItemKeys=[item.item_key for item in cases],
                    groups=output.groups,
                )
            )
        except Exception:
            logger.exception(
                "optimization generation failed runtime_id=%s app=%s item=%s",
                activity.runtime_id,
                activity.app_name,
                case.item_key,
            )

    async def list_cases(
        self,
        activity: RunSseActivity,
        *,
        agent_name: str,
        page_size: int,
    ) -> list[AutoEvaluationCase]:
        repository = await self._case_repository(activity)
        return await repository.list_cases(agent_name=agent_name, page_size=page_size)

    def get_optimizations(
        self,
        runtime_id: str,
        app_name: str,
    ) -> OptimizationSnapshot | None:
        return self._optimizations.get(runtime_id, app_name)

    async def close(self) -> None:
        await self.scheduler.close()

    async def _agent_info(self, activity: RunSseActivity) -> dict[str, Any]:
        try:
            return await self._runtime_get(
                activity,
                f"web/agent-info/{quote(activity.app_name, safe='')}",
            )
        except Exception as error:  # noqa: BLE001 - old Runtime compatibility.
            logger.info(
                "automatic evaluation using app_name fallback runtime_id=%s app=%s "
                "error_type=%s",
                activity.runtime_id,
                activity.app_name,
                type(error).__name__,
            )
            return {"name": activity.app_name}


def _latest_assistant_event_id(session: dict[str, Any]) -> str:
    events = session.get("events")
    if not isinstance(events, list):
        raise TypeError("Session does not contain events")
    for event in reversed(events):
        if not isinstance(event, dict) or str(event.get("author") or "") == "user":
            continue
        event_id = str(event.get("id") or "")
        if event_id:
            return event_id
    raise ValueError("Session does not contain an assistant Event")
