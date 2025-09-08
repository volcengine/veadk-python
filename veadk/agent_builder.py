from google.adk.agents import BaseAgent
from google.adk.agents.llm_agent import ToolUnion
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

        agent_cls = AGENT_TYPES[agent_config["type"]]
        agent = agent_cls(**agent_config, sub_agents=sub_agents)

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
        tools: list[ToolUnion] | None = None,
    ) -> BaseAgent:
        config = self._read_config(path)

        agent_config = config[root_agent_identifier]
        agent = self._build(agent_config)

        if tools and isinstance(agent, Agent):
            agent.tools = tools

        return agent
