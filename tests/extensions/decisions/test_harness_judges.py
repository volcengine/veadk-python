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

"""Harness judges against a real HTTP System One endpoint."""

from __future__ import annotations

import asyncio

import pytest

from veadk.extensions.decisions import (
    DecisionModelConfig,
    DecisionModelResponseError,
    DecisionExtension,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    DecisionCompactionJudge,
    ToolResultCompactor,
    ToolResultCompactorConfig,
)
from veadk.extensions.harness.modules.agent_routing import DecisionAgentRouter
from veadk.extensions.harness.modules.skill_prefilter import DecisionSkillJudge
from veadk.extensions.harness.schemas import CompressionRequest, ConversationMessage

from .fake_system_one import fake_system_one

_ROUTING_AGENTS = {
    "billing_agent": "handles invoices and refunds",
    "docs_agent": "answers product questions",
}


def _extension(base_url: str) -> DecisionExtension:
    return DecisionExtension(
        DecisionModelConfig(enabled=True, api_base=base_url, api_key="test-key")
    )


def _scripted(
    probabilities: dict[int, float],
) -> tuple[int, dict[str, str], dict[str, object]]:
    """Build a response answering ``item_<index>`` with the given values."""
    answers = {
        f"item_{index}": {"type": "noul", "noul": value}
        for index, value in probabilities.items()
    }
    return 200, {}, {"model": "fake-system-one", "answers": answers, "usage": {}}


def test_compaction_judge_batches_one_question_per_candidate() -> None:
    with fake_system_one() as server:
        judge = DecisionCompactionJudge(_extension(server.base_url))
        probabilities = asyncio.run(
            judge.aprotect(
                goal="rank the candidates by score",
                evidence={1: "x" * 5000, 3: "y" * 5000},
            )
        )

    assert set(probabilities) == {1, 3}
    assert len(server.calls) == 1
    call = server.calls[0]
    assert call.model == "jev-latest"
    assert call.authorization == "Bearer test-key"
    assert sorted(call.questions) == ["item_1", "item_3"]
    assert call.questions["item_1"]["type"] == "noul"
    assert "rank the candidates by score" in call.state
    assert "item 1" in call.state and "item 3" in call.state


def test_compaction_judge_parses_scripted_probabilities() -> None:
    with fake_system_one([_scripted({0: 0.95, 1: 0.05})]) as server:
        judge = DecisionCompactionJudge(_extension(server.base_url))
        probabilities = asyncio.run(
            judge.aprotect(goal="g", evidence={0: "a" * 4000, 1: "b" * 4000})
        )

    assert probabilities[0] == pytest.approx(0.95)
    assert probabilities[1] == pytest.approx(0.05)


def test_compaction_judge_rejects_a_partial_judgement() -> None:
    partial = (
        200,
        {},
        {"model": "fake", "answers": {"item_0": {"type": "noul", "noul": 0.9}}},
    )
    with fake_system_one([partial]) as server:
        judge = DecisionCompactionJudge(_extension(server.base_url))
        with pytest.raises(DecisionModelResponseError, match="no usable answer"):
            asyncio.run(
                judge.aprotect(goal="g", evidence={0: "a" * 4000, 1: "b" * 4000})
            )


def test_compaction_judge_bounds_the_state_and_keeps_every_item() -> None:
    evidence = {index: "z" * 20000 for index in range(12)}
    with fake_system_one() as server:
        judge = DecisionCompactionJudge(
            _extension(server.base_url),
            max_state_chars=2400,
            max_evidence_chars=800,
        )
        asyncio.run(judge.aprotect(goal="g", evidence=evidence))

    state = server.calls[0].state
    assert len(state) < 4000
    for index in evidence:
        assert f"item {index} (" in state


def test_decision_strategy_end_to_end_keeps_evidence_and_fits() -> None:
    """A real round trip through the client, the judge, and the policy."""

    messages = [
        ConversationMessage(role="user", content="goal: rank the candidates"),
        ConversationMessage(role="user", content="tool_result: " + "x" * 9000),
        ConversationMessage(role="model", content="I inspected the table."),
        ConversationMessage(role="user", content="tool_result: " + "y" * 9000),
        ConversationMessage(role="model", content="One more check needed."),
        ConversationMessage(role="model", content="Now I will summarize."),
        ConversationMessage(role="user", content="go on"),
    ]
    with fake_system_one([_scripted({1: 0.99, 3: 0.01})]) as server:
        compactor = ToolResultCompactor(
            ToolResultCompactorConfig(
                strategy="decision",
                max_context_chars=12000,
                summary_chars=400,
            ),
            compaction_judge=DecisionCompactionJudge(_extension(server.base_url)),
        )
        result = asyncio.run(
            compactor.acompress_messages(
                CompressionRequest(messages=messages, max_context_chars=12000),
                goal="rank the candidates",
            )
        )

    assert len(server.calls) == 1
    assert result.report.omitted_messages == 0
    assert result.report.compressed_chars <= 12000
    assert result.messages[1] == messages[1]
    assert result.messages[3] != messages[3]


def _noul_script(
    values: dict[str, float],
) -> tuple[int, dict[str, str], dict[str, object]]:
    """Build a response answering ``skill_<index>`` questions."""
    return (
        200,
        {},
        {
            "model": "fake-system-one",
            "answers": {
                name: {"type": "noul", "noul": value} for name, value in values.items()
            },
        },
    )


def test_skill_judge_asks_about_every_candidate_in_one_request() -> None:
    with fake_system_one([_noul_script({"skill_0": 0.92, "skill_1": 0.08})]) as server:
        judge = DecisionSkillJudge(_extension(server.base_url))
        probabilities = asyncio.run(
            judge.aprobabilities(
                user_input="render the chart",
                skills={"chart_skill": "draws charts", "mail_skill": "sends mail"},
            )
        )

    assert len(server.calls) == 1
    call = server.calls[0]
    assert sorted(call.questions) == ["skill_0", "skill_1"]
    assert call.questions["skill_1"]["type"] == "noul"
    assert probabilities["chart_skill"] == pytest.approx(0.92)
    assert probabilities["mail_skill"] == pytest.approx(0.08)
    # 候选只出现在问题里：状态没有技能描述，问题之间互相看不见
    assert "render the chart" in call.state
    assert "draws charts" not in call.state
    assert "draws charts" in call.questions["skill_0"]["instructions"]


def test_agent_router_returns_a_target_above_its_threshold() -> None:
    scripted = (
        200,
        {},
        {
            "model": "fake-system-one",
            "answers": {
                "target": {
                    "type": "choice",
                    "choice": "docs_agent",
                    "confidence": 0.83,
                    "probabilities": {"docs_agent": 0.83, "billing_agent": 0.1},
                }
            },
        },
    )
    with fake_system_one([scripted]) as server:
        router = DecisionAgentRouter(
            _extension(server.base_url), confidence_threshold=0.8
        )
        target = asyncio.run(
            router.aroute(user_input="how do I rotate a key?", agents=_ROUTING_AGENTS)
        )

    assert target == "docs_agent"
    assert len(server.calls) == 1
    call = server.calls[0]
    assert call.questions["target"]["criteria"] == _ROUTING_AGENTS
    assert "how do I rotate a key?" in call.state


def test_agent_router_leaves_a_low_confidence_choice_to_the_model() -> None:
    scripted = (
        200,
        {},
        {
            "model": "fake-system-one",
            "answers": {
                "target": {
                    "type": "choice",
                    "choice": "docs_agent",
                    "confidence": 0.55,
                    "probabilities": {"docs_agent": 0.55, "billing_agent": 0.45},
                }
            },
        },
    )
    with fake_system_one([scripted]) as server:
        router = DecisionAgentRouter(
            _extension(server.base_url), confidence_threshold=0.8
        )
        target = asyncio.run(router.aroute(user_input="hello", agents=_ROUTING_AGENTS))

    assert target is None
