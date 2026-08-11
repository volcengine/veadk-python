# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Orchestration from Studio session completion to optimization suggestions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import quote

from veadk.integrations.agentkit.evaluation.feedback import extract_feedback_sample
from veadk.utils.logger import get_logger

from .model_gateway import EVALUATOR_VERSION, OPTIMIZER_VERSION
from .models import (
    AutoEvaluationCase,
    AutoEvaluationOutput,
    AutomaticEvaluationStatus,
    OptimizationOutput,
    OptimizationSnapshot,
    RunSseActivity,
)
from .repository import auto_item_key
from .scheduler import QuietSessionScheduler

logger = get_logger(__name__)
GOOD_SCORE_THRESHOLD = 0.6
MINIMUM_RUNNING_STATUS_SECONDS = 10.0


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


class OptimizationRepository(Protocol):
    async def put(self, snapshot: OptimizationSnapshot) -> None: ...

    async def get(
        self,
        runtime_id: str,
        app_name: str,
    ) -> OptimizationSnapshot | None: ...


RuntimeGet = Callable[[RunSseActivity, str], Awaitable[dict[str, Any]]]
CaseRepositoryFactory = Callable[[RunSseActivity], Awaitable[CaseRepository]]


class EvaluationAutomationService:
    def __init__(
        self,
        *,
        evaluator: Evaluator,
        optimizer: Optimizer,
        optimization_repository: OptimizationRepository,
        runtime_get: RuntimeGet,
        case_repository: CaseRepositoryFactory,
        quiet_seconds: float = 300,
        minimum_running_seconds: float = MINIMUM_RUNNING_STATUS_SECONDS,
    ) -> None:
        self._evaluator = evaluator
        self._optimizer = optimizer
        self._optimizations = optimization_repository
        self._runtime_get = runtime_get
        self._case_repository = case_repository
        self._quiet_seconds = quiet_seconds
        self._minimum_running_seconds = minimum_running_seconds
        self._statuses: dict[tuple[str, str, str, str], AutomaticEvaluationStatus] = {}
        self.scheduler = QuietSessionScheduler(
            quiet_seconds,
            self.evaluate_now,
        )

    def session_started(self, activity: RunSseActivity) -> None:
        self.scheduler.invalidate(activity.key)
        self._statuses.pop(activity.key, None)

    def session_completed(self, activity: RunSseActivity) -> None:
        self.scheduler.schedule(activity)
        scheduled_at = datetime.now(timezone.utc)
        self._statuses[activity.key] = AutomaticEvaluationStatus(
            runtimeId=activity.runtime_id,
            appName=activity.app_name,
            userId=activity.user_id,
            sessionId=activity.session_id,
            state="pending",
            scheduledAt=scheduled_at,
            dueAt=scheduled_at + timedelta(seconds=self._quiet_seconds),
        )

    async def evaluate_now(self, activity: RunSseActivity) -> None:
        started_at = datetime.now(timezone.utc)
        pending = self._statuses.get(activity.key)
        running = AutomaticEvaluationStatus(
            runtimeId=activity.runtime_id,
            appName=activity.app_name,
            userId=activity.user_id,
            sessionId=activity.session_id,
            state="running",
            scheduledAt=pending.scheduled_at if pending else started_at,
            dueAt=pending.due_at if pending else started_at,
            startedAt=started_at,
        )
        self._statuses[activity.key] = running
        try:
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
                cases = await repository.list_cases(
                    agent_name=agent_name,
                    page_size=100,
                )
                output = await self._optimizer.optimize(
                    agent_info=agent_info,
                    cases=cases,
                )
                await self._optimizations.put(
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
        finally:
            remaining = (
                self._minimum_running_seconds
                - (datetime.now(timezone.utc) - started_at).total_seconds()
            )
            if remaining > 0:
                await asyncio.sleep(remaining)
            if self._statuses.get(activity.key) is running:
                self._statuses.pop(activity.key, None)

    def list_statuses(
        self,
        *,
        runtime_id: str,
        app_name: str,
        user_id: str,
    ) -> list[AutomaticEvaluationStatus]:
        return sorted(
            (
                status
                for status in self._statuses.values()
                if status.runtime_id == runtime_id
                and status.app_name == app_name
                and status.user_id == user_id
            ),
            key=lambda status: status.scheduled_at,
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

    async def get_optimizations(
        self,
        runtime_id: str,
        app_name: str,
    ) -> OptimizationSnapshot | None:
        return await self._optimizations.get(runtime_id, app_name)

    async def close(self) -> None:
        await self.scheduler.close()
        self._statuses.clear()

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
