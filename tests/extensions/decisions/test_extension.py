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

"""Tests for DecisionExtension: opt-out, typed answers, default instance."""

from __future__ import annotations

import pytest

from veadk.extensions.decisions import (
    ChoiceAnswer,
    DecisionModelConfig,
    DecisionModelDisabledError,
    DecisionExtension,
    ScoreAnswer,
    SystemOneClient,
    configure_default_decision_extension,
    get_default_decision_extension,
)

from .fake_system_one import fake_system_one


def _extension(server_url: str) -> DecisionExtension:
    return DecisionExtension(
        DecisionModelConfig(enabled=True, api_base=server_url, api_key="test-key")
    )


def test_disabled_extension_is_opt_out() -> None:
    extension = DecisionExtension()
    assert extension.enabled is False
    with pytest.raises(DecisionModelDisabledError, match="not configured"):
        extension.evaluate("hi", {"q": {"type": "noul", "instructions": "Is it hi?"}})


def test_enabled_requires_both_flag_and_key() -> None:
    assert DecisionExtension(DecisionModelConfig(enabled=True)).enabled is False
    assert _extension("http://127.0.0.1:1").enabled is True


def test_injected_client_marks_extension_enabled() -> None:
    with fake_system_one() as server:
        client = SystemOneClient(
            DecisionModelConfig(enabled=True, api_base=server.base_url, api_key="k")
        )
        extension = DecisionExtension(DecisionModelConfig.disabled(), client=client)
        assert extension.enabled is True
        assert extension.noul("hi", "Is this a greeting?").noul == pytest.approx(0.9)


def test_choose_passes_options_and_returns_typed_answer() -> None:
    with fake_system_one() as server:
        answer = _extension(server.base_url).choose(
            "Where is my order?",
            "Which team should handle this?",
            ["shipping", "billing"],
        )
    assert isinstance(answer, ChoiceAnswer)
    assert answer.choice == "shipping"
    sent = server.calls[0].questions["q"]
    assert sent["type"] == "choice"
    assert list(sent["criteria"]) == ["shipping", "billing"]


def test_score_returns_typed_answer() -> None:
    with fake_system_one() as server:
        answer = _extension(server.base_url).score(
            "This is unacceptable!",
            "How frustrated is the customer?",
            ["Calm", "Angry"],
        )
    assert isinstance(answer, ScoreAnswer)
    assert answer.score == pytest.approx(1.0)
    assert answer.legend == {"0": "Calm", "1": "Angry"}


def test_noul_returns_probability() -> None:
    with fake_system_one() as server:
        answer = _extension(server.base_url).noul("hi", "Is this a greeting?")
    assert answer.noul == pytest.approx(0.9)
    assert answer.probability == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_async_helpers() -> None:
    with fake_system_one() as server:
        extension = _extension(server.base_url)
        choice = await extension.achoose("hi", "Which team?", ["billing", "returns"])
        noul = await extension.anoul("hi", "Is this a greeting?")
    assert choice.choice == "billing"
    assert noul.noul == pytest.approx(0.9)


def test_default_extension_is_built_from_env_and_replaceable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECISION_MODEL_ENABLED", "true")
    monkeypatch.setenv("DECISION_MODEL_API_KEY", "env-key")
    configure_default_decision_extension(None)
    try:
        extension = get_default_decision_extension()
        assert extension.enabled is True
        assert extension.config.api_key == "env-key"
        assert get_default_decision_extension() is extension

        replacement = DecisionExtension()
        configure_default_decision_extension(replacement)
        assert get_default_decision_extension() is replacement
    finally:
        configure_default_decision_extension(None)
