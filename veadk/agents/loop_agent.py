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

from google.adk.agents import LoopAgent as GoogleADKLoopAgent
from google.adk.agents.base_agent import BaseAgent
from pydantic import ConfigDict, Field
from typing_extensions import Any

from veadk.prompts.agent_default_prompt import DEFAULT_DESCRIPTION, DEFAULT_INSTRUCTION
from veadk.tracing.base_tracer import BaseTracer
from veadk.utils.logger import get_logger
from veadk.utils.patches import patch_asyncio

patch_asyncio()
logger = get_logger(__name__)


class LoopAgent(GoogleADKLoopAgent):
    """LLM-based Agent with Volcengine capabilities."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    """The model config"""

    name: str = "veLoopAgent"
    """The name of the agent."""

    description: str = DEFAULT_DESCRIPTION
    """The description of the agent. This will be helpful in A2A scenario."""

    instruction: str = DEFAULT_INSTRUCTION
    """The instruction for the agent, such as principles of function calling."""

    sub_agents: list[BaseAgent] = Field(default_factory=list, exclude=True)
    """The sub agents provided to agent."""

    tracers: list[BaseTracer] = []
    """The tracers provided to agent."""

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(None)  # for sub_agents init

        if self.tracers:
            for tracer in self.tracers:
                for sub_agent in self.sub_agents:
                    try:
                        tracer.do_hooks(sub_agent)
                    except Exception as e:
                        logger.warning(
                            f"Failed to add hooks for sub_agent `{sub_agent.name}`: {e}"
                        )

        logger.info(f"{self.__class__.__name__} `{self.name}` init done.")
