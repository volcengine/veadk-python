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

"""Contract tests for VeADK's workflow-agent wrappers."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from google.adk.agents import BaseAgent

from veadk.agents.loop_agent import LoopAgent
from veadk.agents.parallel_agent import ParallelAgent
from veadk.agents.sequential_agent import SequentialAgent


WorkflowFactory = Callable[..., SequentialAgent | ParallelAgent | LoopAgent]


@pytest.mark.parametrize(
    ("workflow_factory", "default_name"),
    (
        (SequentialAgent, "veSequentialAgent"),
        (ParallelAgent, "veParallelAgent"),
        (LoopAgent, "veLoopAgent"),
    ),
)
def test_workflow_agent_initializes_children_in_order(
    workflow_factory: WorkflowFactory,
    default_name: str,
) -> None:
    first = BaseAgent(name="first")
    second = BaseAgent(name="second")

    workflow = workflow_factory(sub_agents=[first, second])

    assert workflow.name == default_name
    assert workflow.sub_agents == [first, second]
    assert first.parent_agent is workflow
    assert second.parent_agent is workflow


@pytest.mark.parametrize(
    "workflow_factory",
    (SequentialAgent, ParallelAgent, LoopAgent),
)
def test_workflow_agent_mutable_defaults_are_isolated(
    workflow_factory: WorkflowFactory,
) -> None:
    first = workflow_factory()
    second = workflow_factory()

    assert first.sub_agents is not second.sub_agents
    assert first.tracers is not second.tracers


def test_loop_agent_preserves_iteration_limit() -> None:
    workflow = LoopAgent(max_iterations=3)

    assert workflow.max_iterations == 3
