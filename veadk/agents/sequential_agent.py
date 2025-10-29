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

from google.adk.agents import SequentialAgent as GoogleADKSequentialAgent
from google.adk.agents.base_agent import BaseAgent
from pydantic import ConfigDict, Field
from typing_extensions import Any

from veadk.prompts.agent_default_prompt import DEFAULT_DESCRIPTION, DEFAULT_INSTRUCTION
from veadk.tracing.base_tracer import BaseTracer
from veadk.utils.logger import get_logger
from veadk.utils.patches import patch_asyncio

patch_asyncio()
logger = get_logger(__name__)


class SequentialAgent(GoogleADKSequentialAgent):
    """Sequential Agent that executes sub-agents sequentially.

    This agent is designed to execute multiple sub-agents in a predefined sequential order.
    It ensures that each sub-agent is executed one after the other, making it suitable for
    workflows where the output of one sub-agent is needed as input for the next. The agent
    is well-suited for tasks that require a linear progression of steps or operations, ensuring
    that the execution flow is maintained.

    Attributes:
        model_config (ConfigDict): Configuration dictionary for the model.
        name (str): The name of the agent, default is "veSequentialAgent".
        description (str): A description of the agent, useful in A2A scenarios.
        instruction (str): Instructions or principles for function calling and agent execution.
        sub_agents (list[BaseAgent]): A list of sub-agents managed by the sequential agent.
            Each sub-agent is executed in the order they are listed.
        tracers (list[BaseTracer]): A list of tracers used for monitoring the agent's performance
            and behavior during sequential execution.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = "veSequentialAgent"
    description: str = DEFAULT_DESCRIPTION
    instruction: str = DEFAULT_INSTRUCTION

    sub_agents: list[BaseAgent] = Field(default_factory=list, exclude=True)

    tracers: list[BaseTracer] = []

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(None)  # for sub_agents init

        logger.info(f"{self.__class__.__name__} `{self.name}` init done.")
