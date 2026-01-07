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

import json
import os

from v2.nacos import ClientConfig, NacosConfigService
from v2.nacos.config.model.config_param import ConfigParam

from veadk.agent import Agent
from veadk.auth.veauth.mse_veauth import get_mse_cridential
from veadk.consts import DEFAULT_NACOS_GROUP, DEFAULT_NACOS_INSTANCE_NAME
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class DynamicConfigManager:
    """
    DynamicConfigManager is responsible for creating and publishing dynamic config to nacos.
    """

    def __init__(
        self,
        agents: list[Agent] | Agent,
    ):
        """
        Initialize DynamicConfigManager with agents and app_name.

        Args:
            agents (list[Agent] | Agent): The agent(s) to be included in the dynamic config.
        """
        if isinstance(agents, list):
            self.agents = agents
        else:
            self.agents = [agents]

        logger.debug(f"DynamicConfigManager init with {len(self.agents)} agent(s).")

    async def create_config(
        self,
        configs: dict = {},
        instance_name: str = "",
        group_id: str = "",
    ):
        if not instance_name:
            logger.warning(
                f"instance_name is not provided, use default value `{DEFAULT_NACOS_INSTANCE_NAME}`. This may lead to unexpected behavior such as configuration override."
            )
            instance_name = DEFAULT_NACOS_INSTANCE_NAME

        if not group_id:
            logger.warning(
                f"group_id is not provided, use default value `{DEFAULT_NACOS_GROUP}`. This may lead to unexpected behavior such as configuration override."
            )
            group_id = group_id or DEFAULT_NACOS_GROUP

        nacos_endpoint = os.getenv("NACOS_ENDPOINT")
        nacos_port = os.getenv("NACOS_PORT", "8848")
        nacos_username = os.getenv("NACOS_USERNAME", "nacos")
        nacos_password = os.getenv("NACOS_PASSWORD")

        if not all([nacos_endpoint, nacos_port, nacos_username, nacos_password]):
            logger.warning(
                "fetch NACOS_ENDPOINT, NACOS_PORT, NACOS_USERNAME, and NACOS_PASSWORD from env failed, try to get by volcengine AK/SK."
            )

            nacos_credentials = get_mse_cridential(instance_name=instance_name)
            nacos_endpoint = nacos_credentials.endpoint
            nacos_port = nacos_credentials.port
            nacos_username = nacos_credentials.username
            nacos_password = nacos_credentials.password

        client_config = ClientConfig(
            server_addresses=f"{nacos_endpoint}:{nacos_port}",
            namespace_id="",
            username=nacos_username,
            password=nacos_password,
        )

        config_client = await NacosConfigService.create_config_service(
            client_config=client_config
        )

        if not configs:
            logger.info("user config_dict is empty, use default config instead.")
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
                group=group_id,
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
