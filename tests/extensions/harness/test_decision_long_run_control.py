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

from google.adk.models import LlmRequest
from google.genai import types

from veadk.extensions.decisions import (
    DecisionModelConfig,
    DecisionModelDisabledError,
    DecisionExtension,
)
from veadk.extensions.harness.modules.long_run_control import (
    build_convergence_judge,
    trajectory_text,
)
from veadk.extensions.harness.plugins.long_run_control import (
    HarnessLongRunControlPlugin,
)
from veadk.extensions.harness.schemas import ConversationMessage
from veadk.extensions.harness.stores import InMemoryHarnessStore

_STEERING_MARKER = "[Harness Long Run Control]"


class _FakeJudge:
    """Record the trajectories it judged and return fixed probabilities."""

    def __init__(self, ready: float = 0.1, error: Exception | None = None) -> None:
        self.ready = ready
        self.error = error
        self.calls: list[dict[str, str]] = []

    async def aready_probability(self, *, goal: str, trajectory: str) -> float:
        self.calls.append({"goal": goal, "trajectory": trajectory})
        if self.error is not None:
            raise self.error
        return self.ready


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
