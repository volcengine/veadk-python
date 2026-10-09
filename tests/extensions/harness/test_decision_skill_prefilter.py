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

"""Skill prefilter: the advertised list, the judgement, and the fallbacks."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.models import LlmRequest
from google.genai import types

from veadk.extensions.decisions import (
    DecisionModelConfig,
    DecisionExtension,
    DecisionModelDisabledError,
    DecisionModelResponseError,
    DecisionResult,
    NoulAnswer,
)
from veadk.extensions.harness.modules.skill_prefilter import (
    DecisionSkillJudge,
    HarnessSkillPrefilterConfig,
    apply_skill_selection,
    build_skill_judge,
    parse_advertised_skills,
    skill_selection,
)
from veadk.extensions.harness.plugins import HarnessSkillPrefilterPlugin
from veadk.extensions.harness.stores import InMemoryHarnessStore
from veadk.skills.check_skills_callback import _describe

_SKILL_NAMES = ("alpha", "beta", "gamma")


def _skill(name: str, *, checklist: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description=f"does {name}",
        checklist=["step one"] if checklist else None,
    )


def _instruction(*, checklist: bool = False) -> str:
    """Build the skill section exactly as the skills callback writes it."""
    skills = {name: _skill(name, checklist=checklist) for name in _SKILL_NAMES}
    return "Base instruction." + _describe(skills, "local")


class _StubExtension:
    """Answer with fixed payloads, without a decision model behind them."""

    def __init__(self, answers: dict[str, Any] | None = None) -> None:
        self.answers = answers or {}
        self.state = ""
        self.questions: dict[str, Any] = {}

    async def aevaluate(self, state: Any, questions: dict[str, Any]) -> DecisionResult:
        self.state = state
        self.questions = questions
        return DecisionResult(answers=self.answers)


class _FakeSkillJudge:
    """Record what the prefilter asked about and return fixed probabilities."""

    def __init__(
        self,
        probabilities: dict[str, float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.probabilities = dict(probabilities or {})
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def aprobabilities(self, *, user_input: str, skills: dict[str, str]):
        self.calls.append({"user_input": user_input, "skills": dict(skills)})
        if self.error is not None:
            raise self.error
        return dict(self.probabilities)


def _callback_context(
    invocation_id: str = "r1", user_input: str = "render the chart"
) -> SimpleNamespace:
    return SimpleNamespace(
        agent=SimpleNamespace(instruction=_instruction()),
        session=SimpleNamespace(id="s1", app_name="app", user_id="u1"),
        user_id="u1",
        invocation_id=invocation_id,
        user_content=types.Content(role="user", parts=[types.Part(text=user_input)]),
    )


def _request(instruction: str) -> LlmRequest:
    request = LlmRequest(contents=[])
    request.config.system_instruction = instruction
    return request


def _plugin(
    judge: _FakeSkillJudge | None, **config: Any
) -> HarnessSkillPrefilterPlugin:
    return HarnessSkillPrefilterPlugin(
        config=HarnessSkillPrefilterConfig(**config),
        judge=judge,
        store=InMemoryHarnessStore(),
    )


def test_the_callback_section_round_trips() -> None:
    """The parser has to read what the skills callback writes, byte for byte."""

    text = _instruction()
    advertised = parse_advertised_skills(text)

    assert advertised is not None
    assert advertised.names == _SKILL_NAMES
    assert advertised.descriptions["beta"] == "does beta"
    assert advertised.render() == text


def test_text_without_the_documented_section_is_left_alone() -> None:
    assert parse_advertised_skills("Answer with evidence from tool results.") is None
    assert parse_advertised_skills("You have the following skills:\n\nnone\n") is None


def test_selection_keeps_the_surrounding_instructions() -> None:
    text = _instruction(checklist=True)
    advertised = parse_advertised_skills(text)
    assert advertised is not None

    selection, dropped = apply_skill_selection(advertised, {"beta"})

    assert dropped == ("alpha", "gamma")
    assert selection.startswith("Base instruction.\nYou have the following skills:\n")
    assert "- name: beta" in selection
    assert "- name: alpha" not in selection
    # 列表之外的提示（checklist、工具名）必须原样留下
    assert "update_check_list" in selection
    assert "`skills_tool`" in selection
    assert "2 of 3 skills are not listed for this request" in selection


def test_an_empty_selection_keeps_every_skill() -> None:
    """Hiding the whole library is not a narrowing, so the list stays."""

    advertised = parse_advertised_skills(_instruction())
    assert advertised is not None

    text, dropped = apply_skill_selection(advertised, set())

    assert dropped == ()
    assert text == _instruction()


def test_a_selection_that_changes_nothing_keeps_the_text() -> None:
    advertised = parse_advertised_skills(_instruction())
    assert advertised is not None

    text, dropped = apply_skill_selection(advertised, set(advertised.names))

    assert (text, dropped) == (advertised.render(), ())


def test_skill_selection_keeps_a_skill_without_a_probability() -> None:
    """An unanswered skill is unknown, not irrelevant."""

    keep = skill_selection(
        {"alpha": 0.9, "beta": 0.1},
        ["alpha", "beta", "gamma"],
        threshold=0.5,
    )

    assert keep == frozenset({"alpha", "gamma"})


def test_judge_asks_one_question_per_candidate() -> None:
    extension = _StubExtension(
        {"skill_0": NoulAnswer(noul=0.9), "skill_1": NoulAnswer(noul=0.1)}
    )

    probabilities = asyncio.run(
        DecisionSkillJudge(extension).aprobabilities(
            user_input="render the chart",
            skills={"alpha": "does alpha", "beta": "does beta"},
        )
    )

    assert probabilities == {"alpha": 0.9, "beta": 0.1}
    assert sorted(extension.questions) == ["skill_0", "skill_1"]
    assert "render the chart" in extension.state
    assert "does beta" in extension.questions["skill_1"]["instructions"]


def test_judge_rejects_a_partial_answer() -> None:
    extension = _StubExtension({"skill_0": NoulAnswer(noul=0.9)})

    with pytest.raises(DecisionModelResponseError):
        asyncio.run(
            DecisionSkillJudge(extension).aprobabilities(
                user_input="render the chart",
                skills={"alpha": "does alpha", "beta": "does beta"},
            )
        )


def test_judge_is_not_asked_without_candidates() -> None:
    extension = _StubExtension()

    assert (
        asyncio.run(
            DecisionSkillJudge(extension).aprobabilities(user_input="hi", skills={})
        )
        == {}
    )
    assert extension.questions == {}


def test_plugin_advertises_only_the_judged_skills() -> None:
    judge = _FakeSkillJudge({"alpha": 0.9, "beta": 0.05, "gamma": 0.02})
    plugin = _plugin(judge, decision_threshold=0.5)
    context = _callback_context()
    request = _request(_instruction())

    asyncio.run(
        plugin.before_model_callback(callback_context=context, llm_request=request)
    )

    text = str(request.config.system_instruction)
    assert "- name: alpha" in text
    assert "- name: beta" not in text
    assert "2 of 3 skills are not listed for this request" in text
    # agent 指令不改写：下一次请求仍然从完整技能列表开始
    assert context.agent.instruction == _instruction()


def test_plugin_reports_what_it_dropped() -> None:
    store = InMemoryHarnessStore()
    plugin = HarnessSkillPrefilterPlugin(
        config=HarnessSkillPrefilterConfig(decision_threshold=0.5),
        judge=_FakeSkillJudge({"alpha": 0.9, "beta": 0.1, "gamma": 0.1}),
        store=store,
    )

    asyncio.run(
        plugin.before_model_callback(
            callback_context=_callback_context(),
            llm_request=_request(_instruction()),
        )
    )

    assert [event.event_type for event in store.events] == ["skill_prefilter.report"]
    payload = store.events[0].payload
    assert payload["advertised"] == 3
    assert payload["listed"] == 1
    assert payload["dropped"] == ["beta", "gamma"]


def test_plugin_judges_once_per_invocation() -> None:
    judge = _FakeSkillJudge({"alpha": 0.9})
    plugin = _plugin(judge)

    def _invoke(invocation_id: str) -> None:
        asyncio.run(
            plugin.before_model_callback(
                callback_context=_callback_context(invocation_id),
                llm_request=_request(_instruction()),
            )
        )

    _invoke("r1")
    _invoke("r1")
    _invoke("r2")

    assert len(judge.calls) == 2
    assert judge.calls[0]["user_input"] == "render the chart"
    assert sorted(judge.calls[0]["skills"]) == list(_SKILL_NAMES)


def test_a_failing_judgement_advertises_every_skill() -> None:
    plugin = _plugin(
        _FakeSkillJudge(error=DecisionModelDisabledError("not configured"))
    )
    request = _request(_instruction())

    asyncio.run(
        plugin.before_model_callback(
            callback_context=_callback_context(),
            llm_request=request,
        )
    )

    assert request.config.system_instruction == _instruction()


def test_more_candidates_than_one_judgement_covers_are_left_alone() -> None:
    judge = _FakeSkillJudge({"alpha": 0.9})
    plugin = _plugin(judge, max_candidates=2)
    request = _request(_instruction())

    asyncio.run(
        plugin.before_model_callback(
            callback_context=_callback_context(),
            llm_request=request,
        )
    )

    assert judge.calls == []
    assert request.config.system_instruction == _instruction()


def test_a_single_skill_is_not_judged() -> None:
    text = "Base instruction." + _describe({"alpha": _skill("alpha")}, "local")
    judge = _FakeSkillJudge({"alpha": 0.9})
    request = _request(text)

    asyncio.run(
        _plugin(judge).before_model_callback(
            callback_context=_callback_context(),
            llm_request=request,
        )
    )

    assert judge.calls == []
    assert request.config.system_instruction == text


def test_a_request_without_the_section_is_left_alone() -> None:
    judge = _FakeSkillJudge({"alpha": 0.9})
    request = _request("Answer with evidence from tool results.")

    asyncio.run(
        _plugin(judge).before_model_callback(
            callback_context=_callback_context(),
            llm_request=request,
        )
    )

    assert judge.calls == []
    assert (
        request.config.system_instruction == "Answer with evidence from tool results."
    )


def test_plugin_without_a_judge_does_nothing() -> None:
    plugin = _plugin(None)
    request = _request(_instruction())

    asyncio.run(
        plugin.before_model_callback(
            callback_context=_callback_context(),
            llm_request=request,
        )
    )

    assert plugin.uses_judgement is False
    assert request.config.system_instruction == _instruction()


def test_the_skill_judge_is_opt_in() -> None:
    disabled = DecisionExtension(DecisionModelConfig.disabled())

    assert build_skill_judge(HarnessSkillPrefilterConfig(), extension=disabled) is None
    assert (
        build_skill_judge(
            HarnessSkillPrefilterConfig(strategy="decision"), extension=disabled
        )
        is None
    )
    assert (
        build_skill_judge(
            HarnessSkillPrefilterConfig(strategy="decision"),
            extension=DecisionExtension(DecisionModelConfig(enabled=True, api_key="k")),
        )
        is not None
    )
