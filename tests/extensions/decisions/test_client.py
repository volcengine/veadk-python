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

"""Client tests against a local fake System One endpoint."""

from __future__ import annotations

import pytest

from veadk.extensions.decisions import (
    ChoiceAnswer,
    DecisionModelConfig,
    DecisionModelRequestError,
    DecisionModelResponseError,
    DecisionResult,
    NoulAnswer,
    SystemOneClient,
    noul_question,
)

from .fake_system_one import fake_system_one


def _client(server_url: str, *, max_retries: int = 3) -> SystemOneClient:
    return SystemOneClient(
        DecisionModelConfig(
            enabled=True,
            api_base=server_url,
            api_key="test-key",
            name="jev-latest",
            max_retries=max_retries,
        )
    )


def test_request_shape_and_typed_answer() -> None:
    with fake_system_one() as server:
        result = _client(server.base_url).evaluate(
            state="My card was charged twice.",
            questions={"is_urgent": noul_question("Does this convey urgency?")},
        )

    assert isinstance(result, DecisionResult)
    assert result.model == "fake-system-one"
    assert result.usage.input_tokens == 12
    assert result.latency_ms > 0
    assert isinstance(result.answers["is_urgent"], NoulAnswer)
    assert result.answers["is_urgent"].noul == pytest.approx(0.9)
    assert result.usage.cost is None

    call = server.calls[0]
    assert call.path == "/v1/systemone"
    assert call.authorization == "Bearer test-key"
    assert call.model == "jev-latest"
    assert call.state == "My card was charged twice."
    assert call.questions["is_urgent"]["type"] == "noul"


def test_gateway_response_extras_are_tolerated() -> None:
    """OpenRouter adds ``id``, ``provider`` and ``usage.cost`` to the payload."""
    body = {
        "id": "gen-dec-1789738314-X5e5eKGQdvR9rblyX250",
        "model": "typesafe/jev-1.13-20260917",
        "provider": "TypeSafe",
        "answers": {"refund": {"type": "noul", "noul": 0.98}},
        "usage": {"input_tokens": 275, "output_tokens": 20, "cost": 0.00003},
    }
    with fake_system_one([(200, {}, body)]) as server:
        result = _client(server.base_url).evaluate(
            state="I was charged twice for my subscription.",
            questions={
                "refund": noul_question("Is the customer asking for money back?")
            },
        )

    assert result.model == "typesafe/jev-1.13-20260917"
    assert result.usage.input_tokens == 275
    assert result.usage.cost == pytest.approx(0.00003)
    assert result.answers["refund"].noul == pytest.approx(0.98)


def test_unusable_usage_cost_is_ignored() -> None:
    body = {
        "model": "fake-system-one",
        "answers": {"q": {"type": "noul", "noul": 0.5}},
        "usage": {"input_tokens": 1, "cost": "not-a-number"},
    }
    with fake_system_one([(200, {}, body)]) as server:
        result = _client(server.base_url).evaluate(
            state="hi", questions={"q": noul_question("Is this a greeting?")}
        )

    assert result.usage.cost is None


def test_choice_answer_is_typed() -> None:
    with fake_system_one() as server:
        result = _client(server.base_url).evaluate(
            state="Where is my order?",
            questions={
                "team": {
                    "type": "choice",
                    "instructions": "Which team?",
                    "criteria": {"shipping": None, "billing": None},
                }
            },
        )

    answer = result.answers["team"]
    assert isinstance(answer, ChoiceAnswer)
    assert answer.choice == "shipping"
    assert answer.confidence == pytest.approx(0.9)


def test_auth_failure_is_not_retried() -> None:
    script = [(401, {}, {"detail": {"error_type": "authentication_error"}})]
    with fake_system_one(script) as server:
        with pytest.raises(DecisionModelRequestError, match="401"):
            _client(server.base_url).evaluate(
                state="hi", questions={"q": noul_question("Is this a greeting?")}
            )
    assert len(server.calls) == 1


def test_rate_limit_is_retried_and_can_succeed() -> None:
    script = [(429, {"retry-after": "0"}, {"detail": "rate limited"})]
    with fake_system_one(script) as server:
        result = _client(server.base_url).evaluate(
            state="hi", questions={"q": noul_question("Is this a greeting?")}
        )
    assert result.answers["q"].noul == pytest.approx(0.9)
    assert len(server.calls) == 2


def test_retries_are_bounded() -> None:
    script = [(529, {"retry-after": "0"}, {"detail": "overloaded"})] * 3
    with fake_system_one(script) as server:
        with pytest.raises(DecisionModelRequestError, match="after 3 attempt"):
            _client(server.base_url, max_retries=2).evaluate(
                state="hi", questions={"q": noul_question("Is this a greeting?")}
            )
    assert len(server.calls) == 3


def test_missing_answers_object_is_rejected() -> None:
    script = [(200, {}, {"model": "fake-system-one"})]
    with fake_system_one(script) as server:
        with pytest.raises(DecisionModelResponseError, match="no answers object"):
            _client(server.base_url).evaluate(
                state="hi", questions={"q": noul_question("Is this a greeting?")}
            )


def test_unknown_answer_type_is_rejected() -> None:
    script = [(200, {}, {"answers": {"q": {"type": "verdict"}}})]
    with fake_system_one(script) as server:
        with pytest.raises(DecisionModelResponseError, match="unknown type"):
            _client(server.base_url).evaluate(
                state="hi", questions={"q": noul_question("Is this a greeting?")}
            )


def test_no_questions_is_rejected() -> None:
    with pytest.raises(DecisionModelRequestError, match="at least one question"):
        SystemOneClient(DecisionModelConfig(enabled=True, api_key="test-key")).evaluate(
            state="hi", questions={}
        )


def test_client_requires_an_api_key() -> None:
    with pytest.raises(DecisionModelRequestError, match="api_key is required"):
        SystemOneClient(DecisionModelConfig(enabled=True))


@pytest.mark.asyncio
async def test_async_evaluate_uses_the_same_contract() -> None:
    with fake_system_one() as server:
        result = await _client(server.base_url).aevaluate(
            state="hi", questions={"q": noul_question("Is this a greeting?")}
        )
    assert result.answers["q"].noul == pytest.approx(0.9)
    assert server.calls[0].path == "/v1/systemone"


@pytest.mark.asyncio
async def test_async_retry_path() -> None:
    script = [(429, {"retry-after": "0"}, {"detail": "rate limited"})]
    with fake_system_one(script) as server:
        result = await _client(server.base_url).aevaluate(
            state="hi", questions={"q": noul_question("Is this a greeting?")}
        )
    assert result.answers["q"].noul == pytest.approx(0.9)
    assert len(server.calls) == 2
