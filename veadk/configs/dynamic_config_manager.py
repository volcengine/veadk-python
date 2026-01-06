import json
import os

from v2.nacos import ClientConfig, NacosConfigService
from v2.nacos.config.model.config_param import ConfigParam

from veadk.agent import Agent
from veadk.consts import DEFAULT_NACOS_GROUP
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class DynamicConfigManager:
    """
    DynamicConfigManager is responsible for creating and publishing dynamic config to nacos.
    """

    def __init__(self, agents: list[Agent] | Agent, app_name: str):
        """
        Initialize DynamicConfigManager with agents and app_name.

        Args:
            agents (list[Agent] | Agent): The agent(s) to be included in the dynamic config.
            app_name (str): The name of the application, used as the Nacos group id. Defaults to DEFAULT_NACOS_GROUP.
        """
        if isinstance(agents, list):
            self.agents = agents
        else:
            self.agents = [agents]

        if not app_name:
            logger.warning(
                f"app_name is not provided, use default value {DEFAULT_NACOS_GROUP}. This may lead to unexpected behavior such as configuration override."
            )
        self.app_name = app_name or DEFAULT_NACOS_GROUP

        logger.debug(
            f"DynamicConfigManager init with {len(self.agents)} agent(s) for app {self.app_name}"
        )

    async def create_config(self, config: dict = {}):
        client_config = ClientConfig(
            server_addresses=os.getenv("NACOS_SERVER_ADDRESSES"),
            namespace_id="",
            username=os.getenv("NACOS_USERNAME"),
            password=os.getenv("NACOS_PASSWORD"),
        )

        config_client = await NacosConfigService.create_config_service(
            client_config=client_config
        )

        configs = {
            "agent": [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "description": agent.description,
                    "model_name": agent.model_name,
                    "instruction": agent.instruction,
                }
                for agent in self.agents
            ]
        }
        response = await config_client.publish_config(
            param=ConfigParam(
                data_id="veadk",
                group=self.app_name,
                type="json",
                content=json.dumps(configs),
            )
        )
        assert response, "publish config to nacos failed"
        logger.info("Publish config to nacos success")

        await config_client.add_listener(
            data_id="veadk",
            group="VEADK_GROUP",
            listener=self.handle_config_update,
        )
        logger.info("Add config listener to nacos success")

        return config_client

    def register_agent(self, agent: list[Agent] | Agent):
        if isinstance(agent, list):
            self.agents.extend(agent)
        else:
            self.agents.append(agent)

    def update_agent(self, configs: dict):
        for agent in self.agents:
            for config in configs["agent"]:
                if agent.id == config["id"]:
                    logger.info(f"Update agent {agent.id} with config {config}")
                    name = config["name"]
                    description = config["description"]
                    model_name = config["model_name"]
                    instruction = config["instruction"]

                    agent.name = name
                    agent.description = description
                    if model_name != agent.model_name:
                        agent.update_model(model_name=model_name)
                    agent.instruction = instruction

    async def handle_config_update(self, tenant, data_id, group, content) -> None:
        logger.debug(
            "listen, tenant:{} data_id:{} group:{} content:{}".format(
                tenant, data_id, group, content
            )
        )
        content = json.loads(content)
        self.update_agent(content)
