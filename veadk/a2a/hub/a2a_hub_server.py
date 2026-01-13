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

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from veadk.a2a.hub.models import (
    AgentInformation,
    GetAgentResponse,
    GetAgentsResponse,
    GetGroupsResponse,
    RegisterAgentRequest,
    RegisterAgentResponse,
    RegisterGroupResponse,
)


class A2AHubServer:
    def __init__(self):
        self.app = FastAPI()

        self.groups: list[str] = []

        # group_id -> agent_id -> agent_card
        self.agent_cards: dict[str, dict[str, dict]] = {}

        @self.app.get("/ping")
        def ping() -> JSONResponse:
            return JSONResponse(content={"msg": "pong!"})

        @self.app.post("/create_group")
        def create_group(group_id: str) -> RegisterGroupResponse:
            """Create a group."""
            self.groups.append(group_id)
            self.agent_cards[group_id] = {}
            return RegisterGroupResponse(group_id=group_id)

        @self.app.post("/register_agent")
        def register_agent(
            request: RegisterAgentRequest,
        ) -> RegisterAgentResponse:
            """Register an agent to a specified group."""
            if request.group_id not in self.groups:
                return RegisterAgentResponse(
                    err_code=1, msg=f"group {request.group_id} not exist"
                )
            if request.agent_id in self.agent_cards[request.group_id]:
                return RegisterAgentResponse(
                    err_code=1, msg=f"agent {request.agent_id} already exist"
                )

            self.agent_cards[request.group_id][request.agent_id] = request.agent_card
            return RegisterAgentResponse(
                group_id=request.group_id,
                agent_id=request.agent_id,
                agent_card=self.agent_cards[request.group_id][request.agent_id],
            )

        @self.app.get("/group/{group_id}/agents")
        def agents(group_id: str) -> GetAgentsResponse:
            """Get all agents in a specified group."""
            if group_id not in self.groups:
                return GetAgentsResponse(err_code=1, msg=f"group {group_id} not exist")

            agent_infos = [
                AgentInformation(agent_id=agent_id, agent_card=agent_card)
                for agent_id, agent_card in self.agent_cards[group_id].items()
            ]
            return GetAgentsResponse(group_id=group_id, agent_infos=agent_infos)

        @self.app.get("/group/{group_id}/agent/{agent_id}")
        def agent(group_id: str, agent_id: str) -> GetAgentResponse:
            """Get the agent card of a specified agent in a specified group."""
            if group_id not in self.groups:
                return GetAgentResponse(err_code=1, msg=f"group {group_id} not exist")
            if agent_id not in self.agent_cards[group_id]:
                return GetAgentResponse(
                    err_code=1,
                    msg=f"agent {agent_id} in group {group_id} not exist",
                )
            return GetAgentResponse(
                agent_id=agent_id,
                agent_card=self.agent_cards[group_id][agent_id],
            )

        @self.app.get("/groups")
        def groups() -> GetGroupsResponse:
            """Get all registered groups."""
            return GetGroupsResponse(group_ids=self.groups)

    def serve(self, **kwargs):
        uvicorn.run(self.app, **kwargs)
