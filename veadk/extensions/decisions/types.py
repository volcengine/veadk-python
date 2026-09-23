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

"""Typed answers returned by a decision model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

from veadk.extensions.decisions.errors import DecisionModelResponseError


class DecisionUsage(BaseModel):
    """Token usage reported by one decision-model request."""

    input_tokens: int = 0
    output_tokens: int = 0


class ChoiceAnswer(BaseModel):
    """Answer to a Choice question: one option plus its full distribution."""

    kind: Literal["choice"] = "choice"
    choice: str
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0


class ScoreAnswer(BaseModel):
    """Answer to a Score question: a probability-weighted position."""

    kind: Literal["score"] = "score"
    score: float = 0.0
    legend: dict[str, str] = Field(default_factory=dict)
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0


class NoulAnswer(BaseModel):
    """Answer to a Noul question: the probability that the statement is true."""

    kind: Literal["noul"] = "noul"
    noul: float = 0.0

    @property
    def probability(self) -> float:
        """Alias for ``noul``, the probability of "yes"."""
        return self.noul


DecisionAnswer = Annotated[
    Union[ChoiceAnswer, ScoreAnswer, NoulAnswer], Field(discriminator="kind")
]


class DecisionResult(BaseModel):
    """One evaluated request: the model that answered, its answers, and usage."""

    model: str = ""
    answers: dict[str, DecisionAnswer] = Field(default_factory=dict)
    usage: DecisionUsage = Field(default_factory=DecisionUsage)
    latency_ms: float = 0.0


def parse_answers(raw: Mapping[str, Any]) -> dict[str, DecisionAnswer]:
    """Convert a raw ``answers`` payload into typed answers.

    Args:
        raw: The ``answers`` object from a System One response.

    Returns:
        One typed answer per question id.

    Raises:
        DecisionModelResponseError: If an answer is missing its type or an
            unknown question type is returned.
    """
    answers: dict[str, DecisionAnswer] = {}
    for question_id, payload in raw.items():
        if not isinstance(payload, Mapping):
            raise DecisionModelResponseError(
                f"answer {question_id!r} is not an object: {payload!r}"
            )
        kind = payload.get("type")
        if kind == "choice":
            answers[question_id] = ChoiceAnswer.model_validate(payload)
        elif kind == "score":
            answers[question_id] = ScoreAnswer.model_validate(payload)
        elif kind == "noul":
            answers[question_id] = NoulAnswer.model_validate(payload)
        else:
            raise DecisionModelResponseError(
                f"answer {question_id!r} has unknown type {kind!r}"
            )
    return answers
