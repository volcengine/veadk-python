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
"""Classify one model call and apply the conservative routing gates."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from veadk.configs.routing_configs import QueryRoutingConfig
from veadk.decision import DecisionClientError, DecisionQuestion
from veadk.routing.context import RouteSelection
from veadk.routing.policy import ConservativePolicy
from veadk.routing.registry import ModelRegistry
from veadk.routing.state import QueryStateBuilder
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class QueryClassifier:
    """Run local gates, call the Decision API, and return one route label.

    Any timeout, transport failure, malformed answer, or missing capability
    fails closed to the strong model. Classification never blocks or fails the
    user request.
    """

    def __init__(
        self,
        config: QueryRoutingConfig,
        judge: Any,
        registry: ModelRegistry,
        *,
        state_builder: QueryStateBuilder | None = None,
        policy: ConservativePolicy | None = None,
    ):
        self._config = config
        self._judge = judge
        self._registry = registry
        self._state_builder = state_builder or QueryStateBuilder()
        self._policy = policy or ConservativePolicy(config.questions)
        self._questions = {
            question.id: DecisionQuestion(
                type=question.type,
                instructions=question.instructions,
            )
            for question in config.questions
        }

    @property
    def registry(self) -> ModelRegistry:
        """The model pool this classifier selects from."""

        return self._registry

    async def classify(
        self,
        llm_request: Any,
        *,
        invocation_id: str,
        session_id: str = "",
    ) -> RouteSelection:
        started_at = time.monotonic()

        runtime = self._registry.first_available(llm_request)
        if runtime is None:
            return self._strong("no_capable_simple_model", invocation_id, session_id)

        state = self._state_builder.build_for_routing(llm_request)
        if not state:
            return self._strong("empty_state", invocation_id, session_id)

        try:
            response = await asyncio.wait_for(
                self._judge.judge(state=state, questions=self._questions),
                timeout=self._config.decision_timeout,
            )
        except asyncio.TimeoutError:
            return self._strong("decision_timeout", invocation_id, session_id)
        except DecisionClientError as exc:
            logger.info(
                "query routing decision failed: invocation_id=%s error_type=%s",
                invocation_id,
                exc.error_type,
            )
            return self._strong("decision_error", invocation_id, session_id)
        except Exception as exc:  # noqa: BLE001 - fail closed, never fail the turn
            logger.warning(
                "query routing decision raised: invocation_id=%s error=%s",
                invocation_id,
                type(exc).__name__,
            )
            return self._strong("decision_error", invocation_id, session_id)

        decision = self._policy.evaluate(getattr(response, "answers", None))
        elapsed_ms = round((time.monotonic() - started_at) * 1000, 2)

        if decision.route == "strong":
            logger.info(
                "query routing decision: invocation_id=%s route=strong reason=%s "
                "latency_ms=%s probabilities=%s",
                invocation_id,
                decision.reason,
                elapsed_ms,
                decision.probabilities,
            )
            return RouteSelection(
                route="strong",
                reason=decision.reason,
                invocation_id=invocation_id,
                session_id=session_id,
                upgrade_session=decision.upgrade_session,
            )

        if self._config.mode == "shadow":
            logger.info(
                "query routing decision: invocation_id=%s route=strong "
                "shadow_route=simple reason=shadow latency_ms=%s probabilities=%s",
                invocation_id,
                elapsed_ms,
                decision.probabilities,
            )
            return RouteSelection(
                route="strong",
                reason="shadow",
                invocation_id=invocation_id,
                session_id=session_id,
                model_name=runtime.config.name,
                shadow=True,
            )

        logger.info(
            "query routing decision: invocation_id=%s route=simple model=%s "
            "latency_ms=%s probabilities=%s",
            invocation_id,
            runtime.config.name,
            elapsed_ms,
            decision.probabilities,
        )
        return RouteSelection(
            route="simple",
            reason=decision.reason,
            invocation_id=invocation_id,
            session_id=session_id,
            model_name=runtime.config.name,
        )

    @staticmethod
    def _strong(reason: str, invocation_id: str, session_id: str) -> RouteSelection:
        return RouteSelection(
            route="strong",
            reason=reason,
            invocation_id=invocation_id,
            session_id=session_id,
        )
