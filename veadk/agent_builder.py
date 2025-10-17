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

import importlib

from google.adk.agents import BaseAgent
from omegaconf import OmegaConf

from veadk.a2a.remote_ve_agent import RemoteVeAgent
from veadk.agent import Agent
from veadk.agents.loop_agent import LoopAgent
from veadk.agents.parallel_agent import ParallelAgent
from veadk.agents.sequential_agent import SequentialAgent
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

AGENT_TYPES = {
    "Agent": Agent,
    "SequentialAgent": SequentialAgent,
    "ParallelAgent": ParallelAgent,
    "LoopAgent": LoopAgent,
    "RemoteVeAgent": RemoteVeAgent,
}


class AgentBuilder:
    def __init__(self) -> None:
        pass

    def _build(self, agent_config: dict) -> BaseAgent:
        logger.info(f"Building agent with config: {agent_config}")

        sub_agents = []
        if agent_config.get("sub_agents", None):
            for sub_agent_config in agent_config["sub_agents"]:
                agent = self._build(sub_agent_config)
                sub_agents.append(agent)
            agent_config.pop("sub_agents")

        tools = []
        if agent_config.get("tools", []):
            for tool in agent_config["tools"]:
                name = tool["name"]
                module_name, func_name = name.rsplit(".", 1)
                module = importlib.import_module(module_name)
                func = getattr(module, func_name)

                tools.append(func)
            agent_config.pop("tools")

        agent_cls = AGENT_TYPES[agent_config["type"]]
        agent = agent_cls(**agent_config, sub_agents=sub_agents, tools=tools)

        logger.debug("Build agent done.")

        return agent

    def _read_config(self, path: str) -> dict:
        """Read config file (from `path`) to a in-memory dict."""
        assert path.endswith(".yaml"), "Agent config file must be a `.yaml` file."

        config = OmegaConf.load(path)
        config_dict = OmegaConf.to_container(config, resolve=True)

        assert isinstance(config_dict, dict), (
            "Parsed config must in `dict` format. Pls check your building file format."
        )

        return config_dict

    def build(
        self,
        path: str,
        root_agent_identifier: str = "root_agent",
    ) -> BaseAgent:
        config = self._read_config(path)

        agent_config = config[root_agent_identifier]
        agent = self._build(agent_config)

        return agent
