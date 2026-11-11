"""Offline checks for the live corpus and its independently specified oracles."""

from collections import Counter

import pytest
from query_routing_http_cases import answer_matches, conversations, single_turn_cases


def test_frozen_corpus_is_balanced_and_has_unique_case_ids():
    cases = single_turn_cases()
    assert len({case["id"] for case in cases}) == 132
    assert set(Counter(case["category"] for case in cases).values()) == {12}
    assert sum(len(dialogue["turns"]) for dialogue in conversations()) == 96
    assert all(
        case["expected"] is not None
        for case in cases
        if case["category"] != "high_stakes"
    )


@pytest.mark.parametrize(
    "answer,expected,category,correct",
    [
        ("H₂O", "H2O", "facts", True),
        ("H2O2", "H2O", "facts", False),
        ("133.0", "133", "tools", True),
        ("134", "133", "tools", False),
        ("5\n2\n7", "7", "code", False),
        ("BD", "bd", "code", False),
        ("hello world", "HELLO WORLD", "extraction", False),
        ("Four equally likely outcomes.\nProbability = 1/4", "1/4", "reasoning", True),
        ("Probability = 1/2", "1/4", "reasoning", False),
        ("The probability is 1/4.", "1/4", "reasoning", True),
        ("The probability is not 1/4.", "1/4", "reasoning", False),
        ("Probability = 1/0", "1/4", "reasoning", False),
        ('{"code":"A","quantity":7}', {"code": "A", "quantity": 7}, "schema", True),
        ('{"code":"A","quantity":"7"}', {"code": "A", "quantity": 7}, "schema", False),
    ],
)
def test_answer_oracles_accept_equivalent_values_and_reject_wrong_answers(
    answer, expected, category, correct
):
    assert answer_matches(answer, expected, category) is correct


def test_time_extraction_accepts_only_a_weekday_present_in_the_source():
    prompt = "周五 15:30 开会，会议室 302，只提取时间。"
    assert answer_matches("周五 15:30", "15:30", "extraction", prompt)
    assert not answer_matches("周四 15:30", "15:30", "extraction", prompt)
    assert not answer_matches("15:31", "15:30", "extraction", prompt)
