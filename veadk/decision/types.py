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
"""Typed request and response models for the Decision API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DecisionState = str | list[dict[str, Any]]


@dataclass(frozen=True)
class DecisionQuestion:
    """One question in a Decision API request."""

    type: str
    instructions: str


@dataclass(frozen=True)
class DecisionRequest:
    """A batched Decision API request."""

    model: str
    state: DecisionState
    questions: Mapping[str, DecisionQuestion]

    def to_payload(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "state": self.state,
            "questions": {
                name: {
                    "type": question.type,
                    "instructions": question.instructions,
                }
                for name, question in self.questions.items()
            },
        }


@dataclass(frozen=True)
class DecisionResponse:
    """A validated Decision API response.

    ``answers`` contains the per-question answer mappings. Individual answer
    values are intentionally left untyped because the Decision API owns that
    schema and may add question types in the future.
    """

    answers: Mapping[str, Any]
    raw: Mapping[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DecisionResponse":
        answers = payload.get("answers")
        if not isinstance(answers, Mapping):
            raise ValueError("decision API response must contain an `answers` object")
        return cls(answers=answers, raw=payload)
