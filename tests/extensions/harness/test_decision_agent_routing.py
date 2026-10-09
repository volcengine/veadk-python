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

"""Agent routing: the judgement, the transfer it produces, and the fallbacks."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models import LlmRequest
from google.adk.tools.transfer_to_agent_tool import TransferToAgentTool
from google.genai import types

from veadk.extensions.decisions import (
    ChoiceAnswer,
    DecisionModelConfig,
    DecisionExtension,
    DecisionModelDisabledError,
    DecisionModelResponseError,
    DecisionResult,
    NoulAnswer,
)
from veadk.extensions.harness.modules.agent_routing import (
    DecisionAgentRouter,
    build_agent_router,
    build_route_question,
)
from veadk.extensions.harness.plugins import HarnessAgentRoutingPlugin
from veadk.extensions.harness.plugins.agent_routing import transfer_response
from veadk.extensions.harness.stores import InMemoryHarnessStore
from veadk.runtime.agent_transfer import TRANSFER_TOOL_NAME

_AGENTS = {"billing_agent": "handles invoices and refunds", "docs_agent": ""}
_USER_INPUT = "my invoice was charged twice"


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


class _FakeRouter:
    """Record what it was asked and return a fixed target."""

    def __init__(self, target: str | None = None, error: Exception | None = None):
        self.target = target
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def aroute(self, *, user_input: str, agents: dict[str, str]):
        self.calls.append({"user_input": user_input, "agents": dict(agents)})
        if self.error is not None:
            raise self.error
        return self.target


def _choice(target: str, probability: float) -> ChoiceAnswer:
    return ChoiceAnswer(
        choice=target,
        confidence=probability,
        probabilities={target: probability},
    )


def _agent_tree() -> LlmAgent:
    """Build the smallest tree whose parent can transfer to two children."""

    return LlmAgent(
        name="router_agent",
        model="gemini-2.0-flash",
        sub_agents=[
            LlmAgent(
                name="billing_agent",
                model="gemini-2.0-flash",
                description="handles invoices and refunds",
            ),
            LlmAgent(
                name="docs_agent",
                model="gemini-2.0-flash",
                description="answers product questions",
            ),
        ],
    )


_EXPOSED_AGENTS = ["billing_agent", "docs_agent"]


def _request(
    with_transfer_tool: bool = True, agent_names: list[str] | None = None
) -> LlmRequest:
    request = LlmRequest(contents=[])
    if with_transfer_tool:
        request.tools_dict[TRANSFER_TOOL_NAME] = TransferToAgentTool(
            agent_names=agent_names or _EXPOSED_AGENTS
        )
    return request


def _callback_context(agent: Any, invocation_id: str = "r1") -> SimpleNamespace:
    return SimpleNamespace(
        agent=agent,
        session=SimpleNamespace(id="s1", app_name="app", user_id="u1"),
        user_id="u1",
        invocation_id=invocation_id,
        user_content=types.Content(role="user", parts=[types.Part(text=_USER_INPUT)]),
    )


def _plugin(router: _FakeRouter | None, **kwargs: Any) -> HarnessAgentRoutingPlugin:
    return HarnessAgentRoutingPlugin(
        router=router,
        store=InMemoryHarnessStore(),
        **kwargs,
    )


def test_the_route_question_carries_the_agent_descriptions() -> None:
    question = build_route_question(_AGENTS)

    assert question["type"] == "choice"
    assert question["criteria"] == {
        "billing_agent": "handles invoices and refunds",
        "docs_agent": "this agent has no description",
    }


def test_router_returns_a_confident_target() -> None:
    extension = _StubExtension({"target": _choice("billing_agent", 0.88)})
    router = DecisionAgentRouter(extension, confidence_threshold=0.5)

    target = asyncio.run(router.aroute(user_input=_USER_INPUT, agents=_AGENTS))

    assert target == "billing_agent"
    assert "my invoice was charged twice" in extension.state
    assert sorted(extension.questions) == ["target"]


def test_router_leaves_an_uncertain_choice_to_the_model() -> None:
    extension = _StubExtension({"target": _choice("billing_agent", 0.4)})

    target = asyncio.run(
        DecisionAgentRouter(extension, confidence_threshold=0.5).aroute(
            user_input=_USER_INPUT, agents=_AGENTS
        )
    )

    assert target is None


def test_router_leaves_a_choice_without_a_probability_to_the_model() -> None:
    extension = _StubExtension({"target": ChoiceAnswer(choice="billing_agent")})

    target = asyncio.run(
        DecisionAgentRouter(extension, confidence_threshold=0.5).aroute(
            user_input=_USER_INPUT, agents=_AGENTS
        )
    )

    assert target is None


def test_router_ignores_a_target_that_is_not_offered() -> None:
    extension = _StubExtension({"target": _choice("sales_agent", 0.99)})

    target = asyncio.run(
        DecisionAgentRouter(extension, confidence_threshold=0.5).aroute(
            user_input=_USER_INPUT, agents=_AGENTS
        )
    )

    assert target is None


def test_router_rejects_an_unusable_answer() -> None:
    """A rating where a choice belongs is a broken judgement, not a "no"."""

    extension = _StubExtension({"target": NoulAnswer(noul=0.5)})

    with pytest.raises(DecisionModelResponseError):
        asyncio.run(
            DecisionAgentRouter(extension).aroute(
                user_input=_USER_INPUT, agents=_AGENTS
            )
        )


def test_router_asks_nothing_without_candidates() -> None:
    extension = _StubExtension()

    assert (
        asyncio.run(
            DecisionAgentRouter(extension).aroute(user_input=_USER_INPUT, agents={})
        )
        is None
    )
    assert extension.questions == {}


def test_transfer_response_asks_adk_for_the_target() -> None:
    response = transfer_response("billing_agent")

    assert response.content is not None
    call = response.content.parts[0].function_call
    assert call is not None
    assert call.name == TRANSFER_TOOL_NAME
    assert call.args == {"agent_name": "billing_agent"}


def test_plugin_returns_the_transfer_the_judgement_picked() -> None:
    store = InMemoryHarnessStore()
    plugin = HarnessAgentRoutingPlugin(
        router=_FakeRouter("billing_agent"),
        store=store,
    )
    context = _callback_context(_agent_tree())

    response = asyncio.run(
        plugin.before_model_callback(
            callback_context=context,
            llm_request=_request(),
        )
    )

    assert response is not None
    call = response.content.parts[0].function_call
    assert call is not None and call.args == {"agent_name": "billing_agent"}
    assert [event.event_type for event in store.events] == ["agent_routing.transfer"]
    assert store.events[0].payload["target"] == "billing_agent"
    assert store.events[0].payload["candidates"] == ["billing_agent", "docs_agent"]


def test_plugin_leaves_the_model_in_charge_without_the_transfer_tool() -> None:
    router = _FakeRouter("billing_agent")
    response = asyncio.run(
        _plugin(router).before_model_callback(
            callback_context=_callback_context(_agent_tree()),
            llm_request=_request(with_transfer_tool=False),
        )
    )

    assert response is None
    assert router.calls == []


def test_plugin_asks_once_per_invocation() -> None:
    router = _FakeRouter(None)
    plugin = _plugin(router)

    def _invoke(invocation_id: str) -> None:
        asyncio.run(
            plugin.before_model_callback(
                callback_context=_callback_context(_agent_tree(), invocation_id),
                llm_request=_request(),
            )
        )

    _invoke("r1")
    _invoke("r1")
    _invoke("r2")

    assert len(router.calls) == 2


def test_plugin_leaves_a_single_target_with_the_model() -> None:
    parent = LlmAgent(
        name="router_agent",
        model="gemini-2.0-flash",
        sub_agents=[
            LlmAgent(
                name="billing_agent",
                model="gemini-2.0-flash",
                description="handles invoices",
            )
        ],
    )
    router = _FakeRouter("billing_agent")
    response = asyncio.run(
        _plugin(router).before_model_callback(
            callback_context=_callback_context(parent),
            llm_request=_request(),
        )
    )

    assert response is None
    assert router.calls == []


def test_plugin_ignores_a_target_the_transfer_tool_does_not_expose() -> None:
    """A judgement must not name a target ADK would refuse to resolve."""

    router = _FakeRouter("docs_agent")
    response = asyncio.run(
        _plugin(router).before_model_callback(
            callback_context=_callback_context(_agent_tree()),
            llm_request=_request(agent_names=["billing_agent"]),
        )
    )

    assert response is None
    assert router.calls == []


def test_plugin_leaves_the_model_in_charge_when_the_judgement_fails() -> None:
    router = _FakeRouter(error=DecisionModelDisabledError("not configured"))
    response = asyncio.run(
        _plugin(router).before_model_callback(
            callback_context=_callback_context(_agent_tree()),
            llm_request=_request(),
        )
    )

    assert response is None


def test_plugin_without_a_router_does_nothing() -> None:
    plugin = _plugin(None)

    assert plugin.uses_judgement is False
    assert (
        asyncio.run(
            plugin.before_model_callback(
                callback_context=_callback_context(_agent_tree()),
                llm_request=_request(),
            )
        )
        is None
    )


def test_the_router_is_opt_in() -> None:
    disabled = DecisionExtension(DecisionModelConfig.disabled())

    assert build_agent_router("model", extension=disabled) is None
    assert build_agent_router("decision", extension=disabled) is None
    assert (
        build_agent_router(
            "decision",
            extension=DecisionExtension(DecisionModelConfig(enabled=True, api_key="k")),
        )
        is not None
    )
