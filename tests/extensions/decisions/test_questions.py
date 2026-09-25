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

"""Question-builder tests for the decision-model extension."""

from __future__ import annotations

import pytest

from veadk.extensions.decisions import (
    choice_question,
    noul_question,
    score_question,
)


def test_noul_question_without_criteria() -> None:
    assert noul_question("Does this convey urgency?") == {
        "type": "noul",
        "instructions": "Does this convey urgency?",
    }


def test_noul_question_with_criteria() -> None:
    question = noul_question("Is the customer angry?", yes="Uses strong language")
    assert question["criteria"] == {"true": "Uses strong language"}


def test_choice_question_from_names() -> None:
    question = choice_question("Which team?", ["billing", "returns"])
    assert question["type"] == "choice"
    assert question["criteria"] == {"billing": None, "returns": None}


def test_choice_question_from_descriptions() -> None:
    question = choice_question(
        "Which team?",
        {"billing": "Charges and invoices", "returns": "Exchanges"},
    )
    assert question["criteria"]["billing"] == "Charges and invoices"


def test_choice_question_needs_two_options() -> None:
    with pytest.raises(ValueError, match="at least two options"):
        choice_question("Which team?", ["billing"])


def test_score_question_keeps_level_order() -> None:
    question = score_question(
        "How frustrated is the customer?", ["Calm", "Frustrated", "Very angry"]
    )
    assert question["type"] == "score"
    assert question["criteria"] == ["Calm", "Frustrated", "Very angry"]


def test_score_question_needs_two_levels() -> None:
    with pytest.raises(ValueError, match="at least two levels"):
        score_question("How frustrated is the customer?", ["Calm"])
