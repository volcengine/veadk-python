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

from pydantic import BaseModel, Field


class BaseResponse(BaseModel):
    err_code: int = 0

    msg: str = ""
    """The message of the response."""


class RegisterGroupResponse(BaseResponse):
    group_id: str = ""
    """The id of the group."""


class RegisterAgentRequest(BaseResponse):
    group_id: str
    """Target group id."""

    agent_id: str
    """The id of the agent."""

    agent_card: dict
    """The agent card of the agent in json format."""


class RegisterAgentResponse(BaseResponse):
    group_id: str = ""
    """Target group id."""

    agent_id: str = ""
    """The id of the agent."""

    agent_card: dict = Field(default_factory=dict)
    """The agent card of the agent in json format."""


class AgentInformation(BaseModel):
    agent_id: str = ""
    """The id of the agent."""

    agent_card: dict = Field(default_factory=dict)
    """The agent card of the agent in json format."""


class GetAgentsResponse(BaseResponse):
    group_id: str = ""
    """Target group id."""

    agent_infos: list[AgentInformation] = Field(default_factory=list)
    """The agent cards of the agents in json format."""


class GetAgentResponse(BaseResponse):
    agent_id: str = ""
    """The id of the agent."""

    agent_card: dict = Field(default_factory=dict)
    """The agent card of the agent in json format."""


class GetGroupsResponse(BaseResponse):
    group_ids: list[str] = Field(default_factory=list)
    """The ids of the groups."""
