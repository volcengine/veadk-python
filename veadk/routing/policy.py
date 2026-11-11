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
"""Conservative gate applied to Decision API answers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from veadk.configs.routing_configs import RoutingQuestion


@dataclass(frozen=True)
class RoutingDecision:
    """The outcome of the conservative gate."""

    route: Literal["simple", "strong"]
    reason: str
    probabilities: dict[str, float] = field(default_factory=dict)
    upgrade_session: bool = False


class ConservativePolicy:
    """Require every question to stay at or below its threshold.

    A missing, malformed, or non-``noul`` answer fails closed: the request goes
    to the strong model instead of guessing.
    """

    def __init__(self, questions: list[RoutingQuestion]):
        if not questions:
            raise ValueError("at least one routing question is required")
        self._questions = tuple(questions)

    @property
    def questions(self) -> tuple[RoutingQuestion, ...]:
        return self._questions

    def evaluate(self, answers: Any) -> RoutingDecision:
        probabilities: dict[str, float] = {}

        if not isinstance(answers, Mapping):
            return RoutingDecision(
                route="strong",
                reason="invalid_answers",
                probabilities={},
            )

        for question in self._questions:
            answer = answers.get(question.id)
            value = self._probability(answer)
            if value is None:
                return RoutingDecision(
                    route="strong",
                    reason=f"invalid_answer:{question.id}",
                    probabilities=probabilities,
                )
            probabilities[question.id] = value
            if value > question.threshold:
                return RoutingDecision(
                    route="strong",
                    reason=f"{question.id}_above_threshold",
                    probabilities=probabilities,
                    upgrade_session=True,
                )

        return RoutingDecision(
            route="simple",
            reason="all_thresholds_passed",
            probabilities=probabilities,
        )

    @staticmethod
    def _probability(answer: Any) -> float | None:
        if not isinstance(answer, Mapping):
            return None
        if answer.get("type") != "noul":
            return None
        value = answer.get("noul")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        probability = float(value)
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            return None
        return probability
