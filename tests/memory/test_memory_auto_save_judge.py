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

"""The memory save judgement: thresholds by default, opt-in judgement."""

from __future__ import annotations

import pytest
from google.adk.events import Event
from google.genai import types

from veadk.extensions.decisions import (
    DecisionModelConfig,
    DecisionModelDisabledError,
    DecisionExtension,
)
from veadk.memory import save_session_callback
from veadk.memory.auto_save_judge import build_memory_save_judge, events_text
from veadk.memory.save_session_callback import _should_persist


def _user_text_event(text: str) -> Event:
    return Event(
        author="user",
        content=types.Content(role="user", parts=[types.Part(text=text)]),
    )


class _FakeJudge:
    """Record the states it judged and return a fixed probability."""

    def __init__(
        self, probability: float = 0.9, error: Exception | None = None
    ) -> None:
        self.probability = probability
        self.error = error
        self.states: list[str] = []

    async def aworth_saving(self, *, events_text: str) -> float:
        self.states.append(events_text)
        if self.error is not None:
            raise self.error
        return self.probability


@pytest.fixture
def install_judge(monkeypatch):
    """Replace the process-wide memory save judge for one test."""

    def _install(judge) -> None:
        monkeypatch.setattr(save_session_callback, "_memory_save_judge", lambda: judge)

    return _install


def _events() -> list[Event]:
    return [_user_text_event("remember that I prefer dark mode")]


@pytest.mark.asyncio
async def test_thresholds_decide_without_a_judge(install_judge) -> None:
    install_judge(None)

    assert await _should_persist(events=_events(), throttled=True) is False
    assert await _should_persist(events=_events(), throttled=False) is True


@pytest.mark.asyncio
async def test_judgement_overrides_the_thresholds(install_judge) -> None:
    install_judge(_FakeJudge(0.9))
    assert await _should_persist(events=_events(), throttled=True) is True

    install_judge(_FakeJudge(0.05))
    assert await _should_persist(events=_events(), throttled=False) is False


@pytest.mark.asyncio
async def test_judgement_uses_the_configured_threshold(
    monkeypatch, install_judge
) -> None:
    monkeypatch.setattr(save_session_callback, "MEMORY_SAVE_WORTH_THRESHOLD", 0.9)

    install_judge(_FakeJudge(0.7))
    assert await _should_persist(events=_events(), throttled=False) is False

    install_judge(_FakeJudge(0.95))
    assert await _should_persist(events=_events(), throttled=False) is True


@pytest.mark.asyncio
async def test_failing_judge_falls_back_to_the_thresholds(install_judge) -> None:
    install_judge(_FakeJudge(error=DecisionModelDisabledError("not configured")))

    assert await _should_persist(events=_events(), throttled=True) is False
    assert await _should_persist(events=_events(), throttled=False) is True


@pytest.mark.asyncio
async def test_judge_receives_the_event_text(install_judge) -> None:
    judge = _FakeJudge()
    install_judge(judge)

    await _should_persist(events=_events(), throttled=True)

    assert judge.states == ["user: remember that I prefer dark mode"]


def test_events_text_splits_the_budget_between_the_newest_events() -> None:
    events = [_user_text_event(f"message {index}: " + "x" * 500) for index in range(30)]

    text = events_text(events, max_events=5, max_chars=1000)

    for index in range(25, 30):
        assert f"message {index}" in text
    assert "message 24" not in text
    assert len(text) < 1200


def test_events_text_names_tool_calls_and_skips_empty_events() -> None:
    tool_event = Event(
        author="agent",
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_function_call(name="run_code", args={"x": 1}),
            ],
        ),
    )
    empty_event = Event(author="agent", content=types.Content(role="model", parts=[]))

    text = events_text([tool_event, empty_event])

    assert text == "agent: [tool_call run_code]"


def test_build_memory_save_judge_is_opt_in() -> None:
    disabled = DecisionExtension(DecisionModelConfig.disabled())

    assert build_memory_save_judge("threshold", extension=disabled) is None
    assert build_memory_save_judge("decision", extension=disabled) is None
    assert (
        build_memory_save_judge(
            "decision",
            extension=DecisionExtension(DecisionModelConfig(enabled=True, api_key="k")),
        )
        is not None
    )


def test_the_worth_threshold_is_sanitized_at_import(monkeypatch) -> None:
    """An unusable setting must not turn saves silently on or off.

    The threshold is read once, when the module is imported. Values outside
    ``[0, 1]`` used to make every save fail or succeed without a trace, so the
    import must clamp them and fall back for ``NaN``.
    """
    import importlib

    monkeypatch.setenv("MEMORY_SAVE_WORTH_THRESHOLD", "1.5")
    assert importlib.reload(save_session_callback).MEMORY_SAVE_WORTH_THRESHOLD == 1.0

    # NaN 的比较恒为 False，等于"永不写入"——必须回到默认值。
    monkeypatch.setenv("MEMORY_SAVE_WORTH_THRESHOLD", "nan")
    assert importlib.reload(save_session_callback).MEMORY_SAVE_WORTH_THRESHOLD == 0.5

    # 空值按未配置处理，而不是在 import 期抛错。
    monkeypatch.setenv("MEMORY_SAVE_WORTH_THRESHOLD", "")
    assert importlib.reload(save_session_callback).MEMORY_SAVE_WORTH_THRESHOLD == 0.5

    monkeypatch.delenv("MEMORY_SAVE_WORTH_THRESHOLD")
    assert importlib.reload(save_session_callback).MEMORY_SAVE_WORTH_THRESHOLD == 0.5
