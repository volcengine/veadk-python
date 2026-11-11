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

import math

import pytest

from veadk.configs.routing_configs import QueryRoutingConfig, RoutingQuestion
from veadk.routing.policy import ConservativePolicy


def answers(**values):
    return {name: {"type": "noul", "noul": value} for name, value in values.items()}


def policy():
    return ConservativePolicy(QueryRoutingConfig(simple_models=["cheap"]).questions)


def all_low(**overrides):
    values = {
        "is_complex": 0.01,
        "needs_tools": 0.01,
        "needs_long_context": 0.01,
        "is_high_stakes": 0.01,
    }
    values.update(overrides)
    return answers(**values)


def test_questions_property_returns_the_gates():
    gates = policy().questions
    assert [question.id for question in gates] == [
        "is_complex",
        "needs_tools",
        "needs_long_context",
        "is_high_stakes",
    ]


def test_all_questions_below_threshold_routes_simple():
    decision = policy().evaluate(all_low())
    assert decision.route == "simple"
    assert decision.reason == "all_thresholds_passed"
    assert decision.probabilities["is_complex"] == 0.01


@pytest.mark.parametrize(
    ("question", "value"),
    [
        ("is_complex", 0.16),
        ("needs_tools", 0.16),
        ("needs_long_context", 0.16),
        ("is_high_stakes", 0.06),
    ],
)
def test_any_question_above_threshold_routes_strong(question, value):
    decision = policy().evaluate(all_low(**{question: value}))
    assert decision.route == "strong"
    assert decision.reason == f"{question}_above_threshold"


def test_threshold_is_inclusive():
    decision = policy().evaluate(all_low(is_complex=0.15))
    assert decision.route == "simple"


@pytest.mark.parametrize(
    ("threshold", "value", "route"),
    [
        (0.0, 0.0, "simple"),
        (0.0, 0.000001, "strong"),
        (1.0, 1.0, "simple"),
        (0.5, 0.5, "simple"),
    ],
)
def test_threshold_extremes(threshold, value, route):
    gate = ConservativePolicy(
        [RoutingQuestion(id="gate", instructions="是否复杂？", threshold=threshold)]
    )
    decision = gate.evaluate({"gate": {"type": "noul", "noul": value}})
    assert decision.route == route
    if route == "strong":
        assert decision.reason == "gate_above_threshold"


def test_empty_answers_fail_closed():
    decision = policy().evaluate({})
    assert decision.route == "strong"
    assert decision.reason == "invalid_answer:is_complex"


def test_missing_answer_fails_closed():
    values = all_low()
    values.pop("needs_tools")
    decision = policy().evaluate(values)
    assert decision.route == "strong"
    assert decision.reason == "invalid_answer:needs_tools"


def test_non_noul_type_fails_closed():
    values = all_low()
    values["is_complex"] = {"type": "score", "score": 0.1}
    decision = policy().evaluate(values)
    assert decision.route == "strong"
    assert decision.reason == "invalid_answer:is_complex"


@pytest.mark.parametrize("value", [-0.01, 1.01, math.nan, math.inf, True, "0.1"])
def test_invalid_probability_fails_closed(value):
    values = all_low()
    values["is_complex"] = {"type": "noul", "noul": value}
    decision = policy().evaluate(values)
    assert decision.route == "strong"
    assert decision.reason == "invalid_answer:is_complex"


def test_non_mapping_answers_fail_closed():
    decision = policy().evaluate([])
    assert decision.route == "strong"
    assert decision.reason == "invalid_answers"


def test_empty_question_set_is_rejected():
    with pytest.raises(ValueError, match="at least one"):
        ConservativePolicy([])
