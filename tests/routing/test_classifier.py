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

import asyncio
from types import SimpleNamespace

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from veadk.configs.routing_configs import QueryRoutingConfig
from veadk.decision import DecisionClientError
from veadk.routing.classifier import QueryClassifier
from veadk.routing.registry import ModelRegistry, SimpleModelRuntime


class FakeOuterLlm:
    model = "simple"


def answers(**overrides):
    values = {
        "is_complex": 0.01,
        "needs_tools": 0.01,
        "needs_long_context": 0.01,
        "is_high_stakes": 0.01,
    }
    values.update(overrides)
    return {name: {"type": "noul", "noul": value} for name, value in values.items()}


class Judge:
    def __init__(self, result=None, error=None, delay=0.0):
        self.result = result or answers()
        self.error = error
        self.delay = delay
        self.calls = []

    async def judge(self, *, state, questions):
        self.calls.append((state, questions))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(answers=self.result)


def request(text="hello"):
    return LlmRequest(
        model="strong",
        contents=[types.Content(role="user", parts=[types.Part(text=text)])],
    )


def classifier(judge, *, mode="enforce", supports_tools=False):
    config = QueryRoutingConfig.model_validate(
        {
            "simple_models": [{"name": "simple", "supports_tools": supports_tools}],
            "mode": mode,
            "decision_timeout": 0.05,
        }
    )
    runtime = SimpleModelRuntime(config=config.simple_models[0], llm=FakeOuterLlm())
    return QueryClassifier(config, judge, ModelRegistry(runtimes=[runtime]))


@pytest.mark.asyncio
async def test_simple_route_returns_selected_model():
    judge = Judge()
    selection = await classifier(judge).classify(
        request(), invocation_id="inv", session_id="s"
    )
    assert selection.route == "simple"
    assert selection.model_name == "simple"
    assert selection.reason == "all_thresholds_passed"
    assert judge.calls


def test_registry_property_exposes_the_model_pool():
    router = classifier(Judge())
    assert router.registry is router._registry


@pytest.mark.asyncio
async def test_no_capable_model_skips_decision_call():
    judge = Judge()
    req = request()
    req.tools_dict = {"tool": object()}
    selection = await classifier(judge).classify(req, invocation_id="inv")
    assert selection.route == "strong"
    assert selection.reason == "no_capable_simple_model"
    assert judge.calls == []


@pytest.mark.asyncio
async def test_empty_state_routes_strong():
    judge = Judge()
    empty = LlmRequest(model="strong", contents=[])
    selection = await classifier(judge).classify(empty, invocation_id="inv")
    assert selection.route == "strong"
    assert selection.reason == "empty_state"
    assert judge.calls == []


@pytest.mark.asyncio
async def test_timeout_routes_strong():
    judge = Judge(delay=0.2)
    selection = await classifier(judge).classify(request(), invocation_id="inv")
    assert selection.route == "strong"
    assert selection.reason == "decision_timeout"


@pytest.mark.asyncio
async def test_client_error_routes_strong():
    judge = Judge(error=DecisionClientError("timeout", "slow"))
    selection = await classifier(judge).classify(request(), invocation_id="inv")
    assert selection.route == "strong"
    assert selection.reason == "decision_error"


@pytest.mark.asyncio
async def test_unexpected_error_routes_strong():
    judge = Judge(error=RuntimeError("boom"))
    selection = await classifier(judge).classify(request(), invocation_id="inv")
    assert selection.route == "strong"
    assert selection.reason == "decision_error"


@pytest.mark.asyncio
async def test_policy_rejection_routes_strong_and_upgrades_session():
    judge = Judge(result=answers(is_complex=0.9))
    selection = await classifier(judge).classify(request(), invocation_id="inv")
    assert selection.route == "strong"
    assert selection.reason == "is_complex_above_threshold"


@pytest.mark.asyncio
async def test_shadow_mode_records_simple_but_routes_strong():
    judge = Judge()
    selection = await classifier(judge, mode="shadow").classify(
        request(), invocation_id="inv"
    )
    assert selection.route == "strong"
    assert selection.reason == "shadow"
    assert selection.model_name == "simple"
    assert selection.shadow is True


@pytest.mark.asyncio
async def test_judge_receives_builtin_and_custom_questions():
    judge = Judge()
    config = QueryRoutingConfig.model_validate(
        {
            "simple_models": ["simple"],
            "mode": "enforce",
            "questions": [{"question": "是否需要最新信息？", "threshold": 0.2}],
        }
    )
    runtime = SimpleModelRuntime(config=config.simple_models[0], llm=FakeOuterLlm())
    router = QueryClassifier(config, judge, ModelRegistry(runtimes=[runtime]))
    await router.classify(request(), invocation_id="inv")
    _, questions = judge.calls[0]
    assert list(questions) == [
        "is_complex",
        "needs_tools",
        "needs_long_context",
        "is_high_stakes",
        "custom_1",
    ]
    assert all(question.type == "noul" for question in questions.values())
