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
"""Pure threshold arbitration for one decision response."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .config import QuestionConfig
from .types import (
    AuditResult,
    Checkpoint,
    Provider,
    QuestionResult,
)

_MISSING = object()


class ThresholdDecider:
    """Turn a raw response into an :class:`AuditResult`.

    Rules, in order:

    1. Any valid probability at or above its threshold is a ``risk_hit`` and
       blocks, even if another question is malformed.
    2. Otherwise, any malformed/missing answer is an ``error`` and follows
       ``on_error``.
    3. Otherwise every answer is valid and below its threshold: ``passed``.
    """

    def decide(
        self,
        *,
        provider: Provider,
        checkpoint: Checkpoint,
        raw: Any,
        questions: Mapping[str, QuestionConfig],
        on_error: str = "allow",
    ) -> AuditResult:
        if not questions:
            return AuditResult.error(
                provider=provider,
                checkpoint=checkpoint,
                on_error=on_error,
                error_type="no_questions",
                reason="no questions configured",
            )
        if not isinstance(raw, dict):
            return AuditResult.error(
                provider=provider,
                checkpoint=checkpoint,
                on_error=on_error,
                error_type="invalid_response",
                reason="response must be a JSON object",
            )
        answers = raw.get("answers")
        if not isinstance(answers, dict):
            return AuditResult.error(
                provider=provider,
                checkpoint=checkpoint,
                on_error=on_error,
                error_type="invalid_response",
                reason="response is missing an `answers` object",
            )

        results = tuple(
            self._question_result(name, question, answers.get(name, _MISSING))
            for name, question in questions.items()
        )
        hits = tuple(item.question for item in results if item.hit)
        if hits:
            return AuditResult.block(
                provider=provider,
                checkpoint=checkpoint,
                matched_questions=hits,
                question_results=results,
                reason=f"threshold exceeded: {', '.join(hits)}",
            )

        invalid = tuple(item for item in results if not item.valid)
        if invalid:
            error_types = {
                item.error_type for item in invalid if item.error_type is not None
            }
            error_type = (
                next(iter(error_types)) if len(error_types) == 1 else "question_error"
            )
            detail = ", ".join(f"{item.question}:{item.error_type}" for item in invalid)
            return AuditResult.error(
                provider=provider,
                checkpoint=checkpoint,
                on_error=on_error,
                error_type=error_type,
                reason=detail,
                question_results=results,
            )

        return AuditResult.allow(
            provider=provider,
            checkpoint=checkpoint,
            question_results=results,
            reason="all probabilities below threshold",
        )

    def _question_result(
        self,
        name: str,
        question: QuestionConfig,
        entry: Any,
    ) -> QuestionResult:
        if entry is _MISSING:
            return self._invalid(name, question, "missing_question")
        if not isinstance(entry, dict):
            return self._invalid(name, question, "invalid_type")
        if entry.get("type") != "noul":
            return self._invalid(name, question, "invalid_type")
        if "noul" not in entry:
            return self._invalid(name, question, "missing_value")

        value = entry["noul"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return self._invalid(name, question, "invalid_type")
        try:
            probability = float(value)
        except (OverflowError, TypeError, ValueError):
            return self._invalid(name, question, "invalid_type")
        if not math.isfinite(probability):
            return self._invalid(name, question, "not_finite", probability)
        if probability < 0.0 or probability > 1.0:
            return self._invalid(name, question, "out_of_range", probability)

        return QuestionResult(
            question=name,
            threshold=question.threshold,
            probability=probability,
            valid=True,
            hit=probability >= question.threshold,
        )

    @staticmethod
    def _invalid(
        name: str,
        question: QuestionConfig,
        error_type: str,
        probability: float | None = None,
    ) -> QuestionResult:
        return QuestionResult(
            question=name,
            threshold=question.threshold,
            probability=probability,
            valid=False,
            hit=False,
            error_type=error_type,
        )
