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
from typing import Literal

import httpx
import requests
from a2a.types import AgentCard
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

AGENT_CARD_WELL_KNOWN_PATH = "/.well-known/agent-card.json"


def _convert_agent_card_dict_to_obj(agent_card_dict: dict) -> AgentCard:
    agent_card_json_str = json.dumps(agent_card_dict, ensure_ascii=False, indent=2)
    agent_card_object = AgentCard.model_validate_json(str(agent_card_json_str))
    return agent_card_object


class RemoteVeAgent(RemoteA2aAgent):
    """Connect to remote agent on VeFaaS platform."""

    def __init__(
        self,
        name: str,
        url: str,
        auth_token: str | None = None,
        auth_method: Literal["header", "querystring"] | None = None,
    ):
        if not auth_token:
            agent_card_dict = requests.get(url + AGENT_CARD_WELL_KNOWN_PATH).json()
            # replace agent_card_url with actual host
            agent_card_dict["url"] = url

            agent_card_object = _convert_agent_card_dict_to_obj(agent_card_dict)

            logger.debug(f"Agent card of {name}: {agent_card_object}")
            super().__init__(name=name, agent_card=agent_card_object)
        else:
            if auth_method == "header":
                headers = {"Authorization": f"Bearer {auth_token}"}
                agent_card_dict = requests.get(
                    url + AGENT_CARD_WELL_KNOWN_PATH, headers=headers
                ).json()
                agent_card_dict["url"] = url

                agent_card_object = _convert_agent_card_dict_to_obj(agent_card_dict)
                httpx_client = httpx.AsyncClient(
                    base_url=url, headers=headers, timeout=600
                )

                logger.debug(f"Agent card of {name}: {agent_card_object}")
                super().__init__(
                    name=name, agent_card=agent_card_object, httpx_client=httpx_client
                )
            elif auth_method == "querystring":
                agent_card_dict = requests.get(
                    url + AGENT_CARD_WELL_KNOWN_PATH + f"?token={auth_token}"
                ).json()
                agent_card_dict["url"] = url

                agent_card_object = _convert_agent_card_dict_to_obj(agent_card_dict)
                httpx_client = httpx.AsyncClient(
                    base_url=url, params={"token": auth_token}, timeout=600
                )

                logger.debug(f"Agent card of {name}: {agent_card_object}")
                super().__init__(
                    name=name, agent_card=agent_card_object, httpx_client=httpx_client
                )
            else:
                raise ValueError(
                    f"Unsupported auth method {auth_method}, use `header` or `querystring` instead."
                )
