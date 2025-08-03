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

from a2a.types import AgentCapabilities, AgentCard, AgentProvider, AgentSkill

from veadk import Agent
from veadk.version import VERSION


def get_agent_card(
    agent: Agent, url: str, version: str = VERSION, provider: str = "veadk"
) -> AgentCard:
    agent_provider = AgentProvider(organization=provider, url="")
    agent_capabilities = AgentCapabilities()
    agent_skills = [
        AgentSkill(
            id="0",
            name="chat",
            description="Basically chat with user.",
            tags=["chat", "talk"],
        )
    ]
    agent_card = AgentCard(
        capabilities=agent_capabilities,
        description=agent.description,
        name=agent.name,
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        provider=agent_provider,
        skills=agent_skills,
        url=url,
        version=version,
    )
    return agent_card
