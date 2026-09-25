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

"""Agent-facing tool for asking the configured decision model for a judgement."""

from __future__ import annotations

from typing import Any, Literal

from veadk.extensions.decisions.errors import DecisionModelError
from veadk.extensions.decisions.extension import (
    DecisionExtension,
    get_default_decision_extension,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

DecisionKind = Literal["noul", "choice", "score"]


async def decision_evaluate(
    state: str,
    question: str,
    kind: DecisionKind = "noul",
    options: list[str] | None = None,
    levels: list[str] | None = None,
) -> dict[str, Any]:
    """Ask the configured decision model for one typed judgement about a text.

    Use this instead of guessing when a decision is small, repeatable, and
    needs a calibrated answer rather than prose: routing, ranking, extraction,
    or checking whether a statement holds. The answer is a typed value
    (an option, a rating, or a probability), not generated text.

    Args:
        state: The text to judge, for example a user message or a document
            excerpt.
        question: One narrow, self-contained judgement in English, for example
            "Which team should handle this ticket?".
        kind: The judgement type: "noul" for a yes/no probability, "choice" to
            pick one option, "score" to rate on ordered levels.
        options: Candidate options for kind="choice". Write options as the
            values you want back.
        levels: Ordered level descriptions for kind="score", lowest first.

    Returns:
        The answer as ``{"kind", "answer", "confidence", ...}``, plus the model
        that answered. Returns ``{"error": ...}`` when the judgement cannot be
        made, so the caller can continue.
    """
    try:
        return await _evaluate(
            get_default_decision_extension(), state, question, kind, options, levels
        )
    except DecisionModelError as exc:
        logger.warning("decision_evaluate failed: %s", exc)
        return {"error": str(exc)}
    except ValueError as exc:
        return {"error": str(exc)}


async def _evaluate(
    extension: DecisionExtension,
    state: str,
    question: str,
    kind: DecisionKind,
    options: list[str] | None,
    levels: list[str] | None,
) -> dict[str, Any]:
    """Run the requested judgement and flatten it into a tool result."""
    if kind == "noul":
        answer = await extension.anoul(state, question)
        return {
            "kind": "noul",
            "answer": round(answer.noul, 4),
            "probability": round(answer.noul, 4),
        }
    if kind == "choice":
        if not options:
            raise ValueError('kind="choice" requires options')
        choice = await extension.achoose(state, question, options)
        return {
            "kind": "choice",
            "answer": choice.choice,
            "confidence": choice.confidence,
            "probabilities": choice.probabilities,
        }
    if not levels:
        raise ValueError('kind="score" requires levels')
    score = await extension.ascore(state, question, levels)
    return {
        "kind": "score",
        "answer": score.score,
        "confidence": score.confidence,
        "legend": score.legend,
        "probabilities": score.probabilities,
    }
