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

import requests
from a2a.types import AgentCard


class A2AHubClient:
    def __init__(self, server_host: str, server_port: int):
        self.server_host = server_host
        self.server_port = server_port
        self.health_check()

    def health_check(self) -> None:
        """Check the health of the server."""
        response = requests.get(f"http://{self.server_host}:{self.server_port}/ping")
        assert response.status_code == 200, (
            f"unexpected status code from A2A hub server: {response.status_code}"
        )

    def get_agent_cards(
        self, group_id: str, target_agents: list[str] = []
    ) -> list[dict]:
        """Get the agent cards of the agents in the group."""
        ret = []

        response = requests.get(
            f"http://{self.server_host}:{self.server_port}/group/{group_id}/agents"
        ).json()
        agent_infos = response["agent_infos"]
        for agent_info in agent_infos:
            agent_id = agent_info["agent_id"]
            if target_agents:
                if agent_id in target_agents:
                    ret.append(agent_info)
            else:
                ret.append(agent_info)

        return ret

    def register_agent(self, group_id: str, agent_id: str, agent_card: AgentCard):
        response = requests.post(
            f"http://{self.server_host}:{self.server_port}/register_agent",
            json={
                "group_id": group_id,
                "agent_id": agent_id,
                "agent_card": agent_card.model_dump(),
            },
        )

        assert response.status_code == 200, (
            f"unexpected status code from A2A hub server: {response.status_code}"
        )

    def create_group(self, group_id: str):
        response = requests.post(
            f"http://{self.server_host}:{self.server_port}/create_group",
            params={
                "group_id": group_id,
            },
        )

        assert response.status_code == 200, (
            f"unexpected status code from A2A hub server: {response.status_code}"
        )
