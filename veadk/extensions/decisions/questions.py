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

"""Builders for the three decision question types.

Question ``instructions`` and option descriptions are written in English on
purpose: decision models are trained mainly on English text, so English
questions keep judgements more reliable even when the evaluated state is in
another language.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def noul_question(
    instructions: str,
    *,
    yes: str | None = None,
    no: str | None = None,
) -> dict[str, Any]:
    """Build a yes/no question.

    Args:
        instructions: The yes/no question to evaluate.
        yes: Optional description of what "yes" means.
        no: Optional description of what "no" means.

    Returns:
        A question payload for the ``questions`` map.
    """
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    criteria = {key: value for key, value in (("true", yes), ("false", no)) if value}
    if criteria:
        question["criteria"] = criteria
    return question


def choice_question(
    instructions: str,
    options: Sequence[str] | Mapping[str, str | None],
) -> dict[str, Any]:
    """Build a pick-one question.

    Args:
        instructions: The question to evaluate.
        options: Either option names, or a map of option name to description.
            Descriptions separate similar options and are worth writing when
            two options are easy to confuse.

    Returns:
        A question payload for the ``questions`` map.

    Raises:
        ValueError: If fewer than two options are given.
    """
    criteria = (
        dict(options)
        if isinstance(options, Mapping)
        else {option: None for option in options}
    )
    if len(criteria) < 2:
        raise ValueError("a choice question needs at least two options")
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score_question(instructions: str, levels: Sequence[str]) -> dict[str, Any]:
    """Build an ordered-rating question.

    Args:
        instructions: The dimension to rate the state on.
        levels: Ordered level descriptions, from lowest to highest.

    Returns:
        A question payload for the ``questions`` map.

    Raises:
        ValueError: If fewer than two levels are given.
    """
    if len(levels) < 2:
        raise ValueError("a score question needs at least two levels")
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}
