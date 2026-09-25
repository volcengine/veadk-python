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

"""Long-run control: call-count default, judged steering, fail-safe."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from google.adk.models import LlmRequest
from google.genai import types

from veadk.extensions.decisions import (
    ChoiceAnswer,
    DecisionModelConfig,
    DecisionModelDisabledError,
    DecisionExtension,
    DecisionResult,
    NoulAnswer,
)
from veadk.extensions.harness.modules.long_run_control import (
    FORCE_FINISH_ACTION,
    NARROW_SCOPE_ACTION,
    DecisionConvergenceJudge,
    LongRunJudgement,
    build_convergence_judge,
    trajectory_text,
)
from veadk.extensions.harness.modules.long_run_control.judge import (
    ACTION_QUESTION_ID,
)
from veadk.extensions.harness.plugins.long_run_control import (
    HarnessLongRunControlPlugin,
)
from veadk.extensions.harness.schemas import ConversationMessage
from veadk.extensions.harness.stores import InMemoryHarnessStore

_STEERING_MARKER = "[Harness Long Run Control]"


class _FakeJudge:
    """Record the trajectories it judged and return fixed judgements."""

    def __init__(
        self,
        ready: float = 0.1,
        error: Exception | None = None,
        action: str | None = None,
        confidence: float = 0.0,
    ) -> None:
        self.ready = ready
        self.error = error
        self.action = action
        self.confidence = confidence
        self.calls: list[dict[str, str]] = []

    async def ajudge(self, *, goal: str, trajectory: str) -> LongRunJudgement:
        self.calls.append({"goal": goal, "trajectory": trajectory})
        if self.error is not None:
            raise self.error
        return LongRunJudgement(
            ready=self.ready,
            action=self.action,
            confidence=self.confidence,
        )


class _StubExtension:
    """Answer with fixed payloads, without a decision model behind them."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.questions: dict[str, Any] = {}

    async def aevaluate(self, state: Any, questions: dict[str, Any]) -> DecisionResult:
        self.state = state
        self.questions = questions
        return DecisionResult(answers=self.answers)


def _callback_context(invocation_id: str = "r1") -> SimpleNamespace:
    return SimpleNamespace(
        session=SimpleNamespace(id="s1", app_name="app", user_id="u1"),
        user_id="u1",
        invocation_id=invocation_id,
        user_content=types.Content(
            role="user", parts=[types.Part(text="Summarize the dataset")]
        ),
    )


def _request() -> LlmRequest:
    return LlmRequest(
        contents=[
            types.Content(role="user", parts=[types.Part(text="Summarize the dataset")])
        ]
    )


def _run(plugin, request: LlmRequest, calls: int) -> None:
    for _ in range(calls):
        asyncio.run(
            plugin.before_model_callback(
                callback_context=_callback_context(),
                llm_request=request,
            )
        )


def _instruction_text(request: LlmRequest) -> str:
    return str(request.config.system_instruction or "")


def _event_types(store) -> list[str]:
    return [event.event_type for event in store.events]


def test_counter_strategy_keeps_the_call_count_behaviour() -> None:
    store = InMemoryHarnessStore()
    plugin = HarnessLongRunControlPlugin(store=store)
    request = _request()

    assert plugin.convergence_judge is None
    _run(plugin, request, 7)
    assert _STEERING_MARKER not in _instruction_text(request)

    _run(plugin, request, 2)
    assert _STEERING_MARKER in _instruction_text(request)
    assert _event_types(store) == [
        "long_run_control.guidance_injected",
        "long_run_control.guidance_injected",
    ]
    assert "decision_ready" not in store.events[0].payload


def test_decision_strategy_skips_a_still_productive_run() -> None:
    store = InMemoryHarnessStore()
    judge = _FakeJudge(ready=0.1)
    plugin = HarnessLongRunControlPlugin(store=store, convergence_judge=judge)
    request = _request()

    _run(plugin, request, 8)

    assert _STEERING_MARKER not in _instruction_text(request)
    assert _event_types(store) == ["long_run_control.guidance_skipped"]
    assert store.events[0].payload["decision_ready"] == 0.1
    assert len(judge.calls) == 1


def test_decision_strategy_judge_is_not_called_before_the_trigger() -> None:
    judge = _FakeJudge()
    plugin = HarnessLongRunControlPlugin(
        store=InMemoryHarnessStore(), convergence_judge=judge
    )

    _run(plugin, _request(), 7)

    assert judge.calls == []


def test_decision_strategy_steers_a_converged_run() -> None:
    store = InMemoryHarnessStore()
    plugin = HarnessLongRunControlPlugin(
        store=store, convergence_judge=_FakeJudge(ready=0.9)
    )
    request = _request()

    _run(plugin, request, 8)

    assert _STEERING_MARKER in _instruction_text(request)
    assert _event_types(store) == ["long_run_control.guidance_injected"]
    assert store.events[0].payload["decision_ready"] == 0.9
    assert store.events[0].payload["forced"] is False


def test_decision_strategy_threshold_is_respected() -> None:
    plugin = HarnessLongRunControlPlugin(
        store=InMemoryHarnessStore(),
        convergence_judge=_FakeJudge(ready=0.6),
        ready_threshold=0.8,
    )
    request = _request()

    _run(plugin, request, 8)

    assert _STEERING_MARKER not in _instruction_text(request)


def test_unconditional_floor_keeps_steering_guaranteed() -> None:
    store = InMemoryHarnessStore()
    plugin = HarnessLongRunControlPlugin(
        store=store,
        convergence_judge=_FakeJudge(ready=0.01),
        unconditional_after_model_calls=16,
    )
    request = _request()

    _run(plugin, request, 15)
    assert _STEERING_MARKER not in _instruction_text(request)

    _run(plugin, request, 1)
    assert _STEERING_MARKER in _instruction_text(request)
    injected = store.events[-1]
    assert injected.event_type == "long_run_control.guidance_injected"
    assert injected.payload["forced"] is True


def test_failing_judge_keeps_the_original_steering() -> None:
    store = InMemoryHarnessStore()
    plugin = HarnessLongRunControlPlugin(
        store=store,
        convergence_judge=_FakeJudge(
            error=DecisionModelDisabledError("not configured")
        ),
    )
    request = _request()

    _run(plugin, request, 8)

    assert _STEERING_MARKER in _instruction_text(request)
    assert store.events[-1].payload["decision_ready"] == 1.0


def test_build_convergence_judge_is_opt_in() -> None:
    disabled = DecisionExtension(DecisionModelConfig.disabled())

    assert build_convergence_judge("counter", extension=disabled) is None
    assert build_convergence_judge("decision", extension=disabled) is None
    assert (
        build_convergence_judge(
            "decision",
            extension=DecisionExtension(DecisionModelConfig(enabled=True, api_key="k")),
        )
        is not None
    )


def test_trajectory_text_keeps_the_tail_within_budget() -> None:
    messages = [
        ConversationMessage(role="user", content=f"step {index}: " + "x" * 2000)
        for index in range(30)
    ]

    text = trajectory_text(messages, max_chars=3000, max_messages=20)

    assert "step 29" in text
    assert "step 0:" not in text
    assert len(text) < 5000


def test_decision_strategy_injects_the_judged_action_guidance() -> None:
    store = InMemoryHarnessStore()
    plugin = HarnessLongRunControlPlugin(
        store=store,
        convergence_judge=_FakeJudge(
            ready=0.9, action=FORCE_FINISH_ACTION, confidence=0.71
        ),
    )
    request = _request()

    _run(plugin, request, 8)

    assert "Stop calling tools." in _instruction_text(request)
    injected = store.events[-1]
    assert injected.payload["decision_action"] == FORCE_FINISH_ACTION
    assert injected.payload["decision_confidence"] == 0.71


def test_each_action_injects_its_own_guidance() -> None:
    narrow = _request()
    _run(
        HarnessLongRunControlPlugin(
            store=InMemoryHarnessStore(),
            convergence_judge=_FakeJudge(ready=0.9, action=NARROW_SCOPE_ACTION),
        ),
        narrow,
        8,
    )

    narrow_text = _instruction_text(narrow)
    assert "Drop optional or exploratory sub-goals" in narrow_text
    assert "Stop calling tools." not in narrow_text


def test_a_judgement_without_an_action_keeps_the_default_guidance() -> None:
    store = InMemoryHarnessStore()
    plugin = HarnessLongRunControlPlugin(
        store=store, convergence_judge=_FakeJudge(ready=0.9)
    )
    request = _request()

    _run(plugin, request, 8)

    assert "If the task has enough evidence" in _instruction_text(request)
    assert "decision_action" not in store.events[-1].payload


def test_the_judge_asks_about_the_action_in_the_same_request() -> None:
    extension = _StubExtension(
        {
            "ready": NoulAnswer(noul=0.2),
            "action": ChoiceAnswer(
                choice=FORCE_FINISH_ACTION,
                confidence=0.6,
                probabilities={FORCE_FINISH_ACTION: 0.6},
            ),
        }
    )
    judge = DecisionConvergenceJudge(extension)  # type: ignore[arg-type]

    judgement = asyncio.run(judge.ajudge(goal="ship it", trajectory="user: hi"))

    assert judgement.ready == 0.2
    assert judgement.action == FORCE_FINISH_ACTION
    assert set(extension.questions) == {"ready", ACTION_QUESTION_ID}
    assert extension.questions["ready"]["type"] == "noul"
    assert extension.questions[ACTION_QUESTION_ID]["type"] == "choice"


def test_an_unsure_action_keeps_the_default_wording() -> None:
    """引导动作会改行为，判定没把握时只保留「还没收敛」这个信号。"""
    extension = _StubExtension(
        {
            "ready": NoulAnswer(noul=0.2),
            "action": ChoiceAnswer(choice=NARROW_SCOPE_ACTION, confidence=0.4),
        }
    )
    judge = DecisionConvergenceJudge(extension, min_confidence=0.9)  # type: ignore[arg-type]

    judgement = asyncio.run(judge.ajudge(goal="ship it", trajectory="user: hi"))

    assert judgement.ready == 0.2
    assert judgement.action is None
    assert judgement.confidence == 0.4


def test_a_confident_action_is_used_above_the_min_confidence() -> None:
    extension = _StubExtension(
        {
            "ready": NoulAnswer(noul=0.2),
            "action": ChoiceAnswer(choice=NARROW_SCOPE_ACTION, confidence=0.95),
        }
    )
    judge = DecisionConvergenceJudge(extension, min_confidence=0.9)  # type: ignore[arg-type]

    judgement = asyncio.run(judge.ajudge(goal="ship it", trajectory="user: hi"))

    assert judgement.action == NARROW_SCOPE_ACTION


def test_the_action_cascade_is_off_by_default() -> None:
    """服务端可以不报 confidence，默认阈值一旦启用就会让引导动作永远失效。"""
    extension = _StubExtension(
        {
            "ready": NoulAnswer(noul=0.2),
            "action": ChoiceAnswer(choice=NARROW_SCOPE_ACTION, confidence=0.0),
        }
    )
    judge = DecisionConvergenceJudge(extension)  # type: ignore[arg-type]

    judgement = asyncio.run(judge.ajudge(goal="ship it", trajectory="user: hi"))

    assert judgement.action == NARROW_SCOPE_ACTION


def test_an_unknown_action_keeps_the_convergence_probability() -> None:
    extension = _StubExtension(
        {
            "ready": NoulAnswer(noul=0.4),
            "action": ChoiceAnswer(choice="do_something_else", confidence=0.3),
        }
    )
    judge = DecisionConvergenceJudge(extension)  # type: ignore[arg-type]

    judgement = asyncio.run(judge.ajudge(goal="ship it", trajectory="user: hi"))

    assert judgement.ready == 0.4
    assert judgement.action is None
