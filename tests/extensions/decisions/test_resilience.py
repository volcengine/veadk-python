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

"""Failure handling, degradation, and availability tests.

The decision model is optional and sits in hot paths, so every failure has to
reach callers as a ``DecisionModelError`` they can fall back from, and a
down endpoint must stop costing the retry and timeout budget.
"""

from __future__ import annotations

import logging
import time

import httpx
import pytest

from veadk.extensions.decisions import (
    DecisionExtension,
    DecisionModelConfig,
    DecisionModelRequestError,
    DecisionModelResponseError,
    DecisionModelUnavailableError,
    SystemOneClient,
    noul_question,
)
from veadk.extensions.decisions.types import parse_answers

from .fake_system_one import FakeSystemOneServer, fake_system_one

QUESTION = {"q": noul_question("Is this a greeting?")}


def _config(
    server_url: str,
    *,
    timeout: float = 5.0,
    max_retries: int = 0,
    failure_threshold: int = 3,
    cooldown_seconds: float = 30.0,
) -> DecisionModelConfig:
    return DecisionModelConfig(
        enabled=True,
        api_base=server_url,
        api_key="test-key",
        name="jev-latest",
        timeout=timeout,
        max_retries=max_retries,
        failure_threshold=failure_threshold,
        cooldown_seconds=cooldown_seconds,
    )


def _extension(server_url: str, **settings: float | int) -> DecisionExtension:
    return DecisionExtension(_config(server_url, **settings))


def _schedule_outage(server: FakeSystemOneServer, count: int = 1) -> None:
    """Make the next ``count`` requests fail like a down endpoint."""
    server.script.extend([(503, {}, {"detail": "unavailable"})] * count)


def _judge(extension: DecisionExtension) -> float:
    """Ask one noul question and return the probability."""
    return extension.noul("state", "Is this a greeting?").noul


# -- every failure is a decision-model error -------------------------------


def test_a_malformed_answer_is_a_response_error() -> None:
    """A payload that fails pydantic validation must not escape as itself."""
    with pytest.raises(DecisionModelResponseError, match="not a valid choice"):
        parse_answers({"q": {"type": "choice"}})
    with pytest.raises(DecisionModelResponseError, match="not a valid noul"):
        parse_answers({"q": {"type": "noul", "noul": "certainly"}})


def test_a_broken_answer_payload_reaches_callers_as_a_decision_error() -> None:
    script = [(200, {}, {"model": "fake", "answers": {"q": {"type": "choice"}}})]
    with fake_system_one(script) as server:
        with pytest.raises(DecisionModelResponseError):
            _judge(_extension(server.base_url))


def test_a_send_failure_that_is_not_an_http_error_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``httpx.InvalidURL`` is not an ``httpx.HTTPError``, so it needs our own."""
    assert not issubclass(httpx.InvalidURL, httpx.HTTPError)

    def _raise_invalid_url(*_args: object, **_kwargs: object) -> None:
        raise httpx.InvalidURL("Invalid port: ':1'")

    monkeypatch.setattr(httpx.Client, "post", _raise_invalid_url)
    client = SystemOneClient(_config("https://api.example.com"))
    with pytest.raises(DecisionModelRequestError, match="could not be sent"):
        client.evaluate(state="state", questions=QUESTION)


def test_a_transport_outage_is_a_request_error() -> None:
    with fake_system_one() as server:
        base_url = server.base_url
    with pytest.raises(DecisionModelRequestError):
        SystemOneClient(_config(base_url)).evaluate(state="state", questions=QUESTION)


# -- the endpoint stops being called once it is known to be down -----------


def test_repeated_failures_open_the_circuit_and_skip_the_endpoint() -> None:
    with fake_system_one() as server:
        extension = _extension(server.base_url, failure_threshold=2)
        _schedule_outage(server, 2)
        for _ in range(2):
            with pytest.raises(DecisionModelRequestError):
                _judge(extension)
        assert len(server.calls) == 2

        with pytest.raises(DecisionModelUnavailableError, match="marked down"):
            _judge(extension)
    assert len(server.calls) == 2


def test_a_successful_probe_resumes_judgements() -> None:
    with fake_system_one() as server:
        extension = _extension(
            server.base_url, failure_threshold=1, cooldown_seconds=0.05
        )
        _schedule_outage(server)
        with pytest.raises(DecisionModelRequestError):
            _judge(extension)
        with pytest.raises(DecisionModelUnavailableError):
            _judge(extension)

        time.sleep(0.06)
        assert _judge(extension) == pytest.approx(0.9)
        assert _judge(extension) == pytest.approx(0.9)


def test_a_failed_probe_keeps_the_circuit_open() -> None:
    with fake_system_one() as server:
        extension = _extension(
            server.base_url, failure_threshold=1, cooldown_seconds=0.05
        )
        _schedule_outage(server)
        with pytest.raises(DecisionModelRequestError):
            _judge(extension)

        time.sleep(0.06)
        _schedule_outage(server)
        with pytest.raises(DecisionModelRequestError):
            _judge(extension)
        with pytest.raises(DecisionModelUnavailableError):
            _judge(extension)
    # 三次失败里只有两次真的打了上游：冷却期内的那次被拦下了
    assert len(server.calls) == 2


def test_the_circuit_closes_after_isolated_failures() -> None:
    with fake_system_one() as server:
        extension = _extension(server.base_url, failure_threshold=2)
        _schedule_outage(server)
        with pytest.raises(DecisionModelRequestError):
            _judge(extension)
        assert _judge(extension) == pytest.approx(0.9)

        _schedule_outage(server)
        with pytest.raises(DecisionModelRequestError):
            _judge(extension)
        assert _judge(extension) == pytest.approx(0.9)


def test_the_circuit_can_be_disabled() -> None:
    with fake_system_one() as server:
        extension = _extension(server.base_url, failure_threshold=0)
        _schedule_outage(server, 3)
        for _ in range(3):
            with pytest.raises(DecisionModelRequestError):
                _judge(extension)
    assert len(server.calls) == 3


# -- the timeout is a budget for the whole judgement -----------------------


def test_one_judgement_stays_within_its_time_budget() -> None:
    """Retries and backoff cannot outlive the configured budget."""
    script = [(503, {"retry-after": "5"}, {"detail": "unavailable"})] * 4
    with fake_system_one(script) as server:
        client = SystemOneClient(_config(server.base_url, timeout=0.3, max_retries=3))
        started = time.perf_counter()
        with pytest.raises(DecisionModelRequestError, match="time budget"):
            client.evaluate(state="state", questions=QUESTION)
        elapsed = time.perf_counter() - started
    assert elapsed < 0.6
    assert len(server.calls) == 1


# -- what ends up in the log ----------------------------------------------


def test_retries_and_outages_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    script = [(503, {"retry-after": "0"}, {"detail": "unavailable"})] * 2
    with fake_system_one(script) as server:
        extension = _extension(server.base_url, max_retries=1, failure_threshold=1)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(DecisionModelRequestError):
                _judge(extension)

    messages = [record.getMessage() for record in caplog.records]
    assert any("retrying" in message for message in messages)
    assert any("in a row" in message for message in messages)
    assert all("test-key" not in message for message in messages)


def test_the_judged_state_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    with fake_system_one() as server:
        extension = _extension(server.base_url)
        with caplog.at_level(logging.DEBUG):
            extension.noul("SECRET-USER-TEXT", "Is this a greeting?")

    assert caplog.records, "a successful judgement should be observable"
    assert all(
        "SECRET-USER-TEXT" not in record.getMessage() for record in caplog.records
    )
