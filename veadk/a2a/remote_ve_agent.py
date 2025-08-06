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

import requests
from a2a.types import AgentCard
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

AGENT_CARD_WELL_KNOWN_PATH = "/.well-known/agent.json"


class RemoteVeAgent(RemoteA2aAgent):
    def __init__(self, name: str, url: str):
        agent_card_dict = requests.get(url + AGENT_CARD_WELL_KNOWN_PATH).json()
        agent_card_dict["url"] = url

        agent_card_json_str = json.dumps(agent_card_dict, ensure_ascii=False, indent=2)

        agent_card_object = AgentCard.model_validate_json(str(agent_card_json_str))

        super().__init__(name=name, agent_card=agent_card_object)
