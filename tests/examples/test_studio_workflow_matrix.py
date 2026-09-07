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

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from veadk import Agent
from veadk.agents.loop_agent import LoopAgent
from veadk.agents.parallel_agent import ParallelAgent
from veadk.agents.sequential_agent import SequentialAgent

AGENTS_DIR = Path(__file__).parents[2] / "examples" / "studio_workflow_matrix"
sys.path.insert(0, str(AGENTS_DIR))


@pytest.mark.parametrize(
    ("module_name", "agent_type", "agent_name"),
    [
        ("llm_agent", Agent, "llm_agent"),
        ("sequential_agent", SequentialAgent, "sequential_agent"),
        ("parallel_agent", ParallelAgent, "parallel_agent"),
        ("loop_agent", LoopAgent, "loop_agent"),
        ("mixed_agent", SequentialAgent, "mixed_agent"),
        (
            "all_agent_types_agent",
            SequentialAgent,
            "all_agent_types_agent",
        ),
    ],
)
def test_workflow_app_wiring(
    module_name: str, agent_type: type, agent_name: str
) -> None:
    module = importlib.import_module(f"{module_name}.agent")

    assert isinstance(module.root_agent, agent_type)
    assert module.root_agent.name == agent_name


def test_parallel_fixture_has_three_tool_free_specialists() -> None:
    module = importlib.import_module("parallel_agent.agent")

    assert [agent.name for agent in module.root_agent.sub_agents] == [
        "parallel_alpha",
        "parallel_beta",
        "parallel_gamma",
    ]
    assert all(not agent.tools for agent in module.root_agent.sub_agents)


def test_loop_fixtures_are_bounded() -> None:
    loop = importlib.import_module("loop_agent.agent").root_agent
    mixed = importlib.import_module("mixed_agent.agent").root_agent
    all_types = importlib.import_module("all_agent_types_agent.agent").root_agent

    assert loop.max_iterations == 3
    assert mixed.sub_agents[2].max_iterations == 2
    assert all_types.sub_agents[3].max_iterations == 2


def test_mixed_fixture_contains_every_workflow_kind() -> None:
    root = importlib.import_module("mixed_agent.agent").root_agent

    assert isinstance(root, SequentialAgent)
    assert isinstance(root.sub_agents[0], Agent)
    assert isinstance(root.sub_agents[1], ParallelAgent)
    assert isinstance(root.sub_agents[2], LoopAgent)
    assert isinstance(root.sub_agents[3], Agent)


def test_all_agent_types_fixture_contains_every_workflow_kind() -> None:
    module = importlib.import_module("all_agent_types_agent.agent")
    root = module.root_agent

    assert isinstance(root, SequentialAgent)
    assert isinstance(root.sub_agents[0], Agent)
    assert isinstance(root.sub_agents[1], SequentialAgent)
    assert isinstance(root.sub_agents[2], ParallelAgent)
    assert isinstance(root.sub_agents[3], LoopAgent)
    assert isinstance(root.sub_agents[4], Agent)
    assert [agent.name for agent in root.sub_agents[2].sub_agents] == [
        "all_types_evidence",
        "all_types_risks",
        "all_types_options",
        "all_types_rollout",
    ]

    agents = [
        root.sub_agents[0],
        *root.sub_agents[1].sub_agents,
        *root.sub_agents[2].sub_agents,
        *root.sub_agents[3].sub_agents,
        root.sub_agents[4],
    ]
    forbidden_markers = ("[PAR-", "[SEQ-", "[LOOP", "[MIX-")
    assert all(
        not any(marker in agent.instruction for marker in forbidden_markers)
        for agent in agents
    )


def test_all_workflow_fixtures_hide_internal_test_markers() -> None:
    roots = [
        importlib.import_module(f"{module_name}.agent").root_agent
        for module_name in (
            "llm_agent",
            "sequential_agent",
            "parallel_agent",
            "loop_agent",
            "mixed_agent",
            "all_agent_types_agent",
        )
    ]
    forbidden_markers = ("[PAR-", "[SEQ-", "[LOOP", "[MIX-", "[LLM")

    def walk(agent: Agent) -> list[Agent]:
        return [agent, *(child for item in agent.sub_agents for child in walk(item))]

    assert all(
        not any(marker in agent.instruction for marker in forbidden_markers)
        for root in roots
        for agent in walk(root)
    )
