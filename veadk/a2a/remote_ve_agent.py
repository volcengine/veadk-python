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
    """Connect to a remote agent on the VeFaaS platform.

    This class provides an interface to remotely connect with an agent deployed on the VeFaaS platform. It automatically fetches the agent card (metadata) and configures an HTTP client for secure communication. Authentication can be handled either via a bearer token in the HTTP header or via a query string parameter.

    The class extends `RemoteA2aAgent` to provide compatibility with the A2A (Agent-to-Agent) communication layer.

    This constructor connects to a remote VeFaaS agent endpoint, retrieves its metadata (`agent_card`), and sets up an asynchronous HTTP client (`httpx.AsyncClient`) for subsequent communication. Depending on the provided authentication parameters, it supports three connection modes:
    - **No authentication:** Directly fetches the agent card.
    - **Header authentication:** Sends a bearer token in the `Authorization` header.
    - **Query string authentication:** Appends the token to the URL query.

    Attributes:
        name (str):
            A unique name identifying this remote agent instance.
        url (str):
            The base URL of the remote agent on the VeFaaS platform.
        auth_token (str | None):
            Optional authentication token used for secure access.
            If not provided, the agent will be accessed without authentication.
        auth_method (Literal["header", "querystring"] | None):
            The method of attaching the authentication token.
            - `"header"`: Token is passed via HTTP `Authorization` header.
            - `"querystring"`: Token is passed as a query parameter.
            - `None`: No authentication used.

    Raises:
        ValueError:
            If an unsupported `auth_method` is provided when `auth_token` is set.
        requests.RequestException:
            If fetching the agent card from the remote URL fails.

    Examples:
        ```python
        # Example 1: No authentication
        agent = RemoteVeAgent(
            name="public_agent",
            url="https://vefaas.example.com/agents/public"
        )

        # Example 2: Using Bearer token in header
        agent = RemoteVeAgent(
            name="secured_agent",
            url="https://vefaas.example.com/agents/secure",
            auth_token="my_secret_token",
            auth_method="header"
        )

        # Example 3: Using token in query string
        agent = RemoteVeAgent(
            name="query_agent",
            url="https://vefaas.example.com/agents/query",
            auth_token="my_secret_token",
            auth_method="querystring"
        )
        ```
    """

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
