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
from typing import Literal, Optional

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

    This class provides an interface to remotely connect with an agent deployed on the
    VeFaaS platform. It automatically fetches the agent card (metadata) and configures
    an HTTP client for secure communication.

    The class extends `RemoteA2aAgent` to provide compatibility with the A2A
    (Agent-to-Agent) communication layer.

    This constructor handles agent discovery and HTTP client setup. It determines the
    agent's URL, fetches its metadata (`agent_card`), and prepares an
    `httpx.AsyncClient` for subsequent communication. You can either provide a URL
    directly, or pass a pre-configured `httpx.AsyncClient` with a `base_url`.

    Authentication can be handled via a bearer token in the HTTP header or via a
    query string parameter. If a custom `httpx_client` is provided, authentication
    details will be added to it.

    Attributes:
        name (str):
            A unique name identifying this remote agent instance.
        url (Optional[str]):
            The base URL of the remote agent. This is optional if an `httpx_client`
            with a configured `base_url` is provided. If both are given, they must
            not conflict.
        auth_token (Optional[str]):
            Optional authentication token used for secure access. If not provided,
            the agent will be accessed without authentication.
        auth_method (Literal["header", "querystring"] | None):
            The method of attaching the authentication token.
            - `"header"`: Token is passed via HTTP `Authorization` header.
            - `"querystring"`: Token is passed as a query parameter.
        httpx_client (Optional[httpx.AsyncClient]):
            An optional, pre-configured `httpx.AsyncClient` to use for communication.
            This allows for client sharing and advanced configurations (e.g., proxies).
            If its `base_url` is set, it will be used as the agent's location.

    Raises:
        ValueError:
            - If `url` and `httpx_client.base_url` are both provided and conflict.
            - If neither `url` nor an `httpx_client` with a `base_url` is provided.
            - If an unsupported `auth_method` is provided when `auth_token` is set.
        requests.RequestException:
            If fetching the agent card from the remote URL fails.

    Examples:
        ```python
        # Example 1: Connect using a URL
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

        # Example 3: Using a pre-configured httpx_client
        import httpx
        client = httpx.AsyncClient(
            base_url="https://vefaas.example.com/agents/query",
            timeout=600
        )
        agent = RemoteVeAgent(
            name="query_agent",
            auth_token="my_secret_token",
            auth_method="querystring",
            httpx_client=client
        )
        ```
    """

    def __init__(
        self,
        name: str,
        url: Optional[str] = None,
        auth_token: Optional[str] = None,
        auth_method: Literal["header", "querystring"] | None = None,
        httpx_client: Optional[httpx.AsyncClient] = None,
    ):
        # Determine the effective URL for the agent and handle conflicts.
        effective_url = url
        if httpx_client and httpx_client.base_url:
            client_url_str = str(httpx_client.base_url).rstrip("/")
            if url and url.rstrip("/") != client_url_str:
                raise ValueError(
                    f"The `url` parameter ('{url}') conflicts with the `base_url` of the provided "
                    f"httpx_client ('{client_url_str}'). Please provide only one or ensure they match."
                )
            effective_url = client_url_str

        if not effective_url:
            raise ValueError(
                "Could not determine agent URL. Please provide the `url` parameter or an `httpx_client` with a configured `base_url`."
            )

        req_headers = {}
        req_params = {}

        if auth_token:
            if auth_method == "header":
                req_headers = {"Authorization": f"Bearer {auth_token}"}
            elif auth_method == "querystring":
                req_params = {"token": auth_token}
            elif auth_method:
                raise ValueError(
                    f"Unsupported auth method {auth_method}, use `header` or `querystring` instead."
                )

        agent_card_dict = requests.get(
            effective_url + AGENT_CARD_WELL_KNOWN_PATH,
            headers=req_headers,
            params=req_params,
        ).json()
        # replace agent_card_url with actual host
        agent_card_dict["url"] = effective_url

        agent_card_object = _convert_agent_card_dict_to_obj(agent_card_dict)

        logger.debug(f"Agent card of {name}: {agent_card_object}")

        client_was_provided = httpx_client is not None
        client_to_use = httpx_client

        if client_was_provided:
            # If a client was provided, update it with auth info
            if auth_token:
                if auth_method == "header":
                    client_to_use.headers.update(req_headers)
                elif auth_method == "querystring":
                    new_params = dict(client_to_use.params)
                    new_params.update(req_params)
                    client_to_use.params = new_params
        else:
            # If no client was provided, create a new one with auth info
            if auth_token:
                if auth_method == "header":
                    client_to_use = httpx.AsyncClient(
                        base_url=effective_url, headers=req_headers, timeout=600
                    )
                elif auth_method == "querystring":
                    client_to_use = httpx.AsyncClient(
                        base_url=effective_url, params=req_params, timeout=600
                    )
            else:  # No auth, no client provided
                client_to_use = httpx.AsyncClient(base_url=effective_url, timeout=600)

        super().__init__(
            name=name, agent_card=agent_card_object, httpx_client=client_to_use
        )

        # The parent class sets _httpx_client_needs_cleanup based on whether
        # the httpx_client it received was None. Since we always pass a
        # client (either the user's or one we create), it will always set
        # it to False. We must override this to ensure clients we create
        # are properly cleaned up.
        if not client_was_provided:
            self._httpx_client_needs_cleanup = True
