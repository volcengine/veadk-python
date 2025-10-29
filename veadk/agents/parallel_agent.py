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

from google.adk.agents import ParallelAgent as GoogleADKParallelAgent
from google.adk.agents.base_agent import BaseAgent
from pydantic import ConfigDict, Field
from typing_extensions import Any

from veadk.prompts.agent_default_prompt import DEFAULT_DESCRIPTION, DEFAULT_INSTRUCTION
from veadk.tracing.base_tracer import BaseTracer
from veadk.utils.logger import get_logger
from veadk.utils.patches import patch_asyncio

patch_asyncio()
logger = get_logger(__name__)


class ParallelAgent(GoogleADKParallelAgent):
    """LLM-based Agent that can execute sub-agents in parallel.

    This agent is capable of executing multiple sub-agents concurrently, making it suitable
    for scenarios that require parallel execution of multiple tasks or operations. By leveraging
    parallelism, the agent can handle more complex workflows and improve efficiency by performing
    independent tasks simultaneously. This design is ideal for scenarios where tasks are independent
    and can benefit from reduced execution time.

    Attributes:
        model_config (ConfigDict): Configuration dictionary for the model.
        name (str): The name of the agent, default is "veParallelAgent".
        description (str): A description of the agent, useful in A2A scenarios.
        instruction (str): Instructions or principles for function calling and agent execution.
        sub_agents (list[BaseAgent]): A list of sub-agents managed by the parallel agent.
            Each sub-agent is executed concurrently.
        tracers (list[BaseTracer]): A list of tracers used for monitoring the agent's performance
            and behavior during parallel execution.

    Examples:

    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = "veParallelAgent"
    description: str = DEFAULT_DESCRIPTION
    instruction: str = DEFAULT_INSTRUCTION

    sub_agents: list[BaseAgent] = Field(default_factory=list, exclude=True)

    tracers: list[BaseTracer] = []

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(None)  # for sub_agents init

        if self.tracers:
            logger.warning(
                "Enable tracing in ParallelAgent may cause OpenTelemetry context error. Issue see https://github.com/google/adk-python/issues/1670"
            )

        logger.info(f"{self.__class__.__name__} `{self.name}` init done.")
