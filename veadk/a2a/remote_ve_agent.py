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
import functools
from typing import AsyncGenerator, Literal, Optional

from a2a.client.base_client import BaseClient
import httpx
import requests
from a2a.types import AgentCard
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

from veadk.integrations.ve_identity.utils import generate_headers
from veadk.utils.auth import VE_TIP_TOKEN_CREDENTIAL_KEY, VE_TIP_TOKEN_HEADER
from veadk.utils.logger import get_logger
from google.adk.utils.context_utils import Aclosing
from google.adk.events.event import Event
from google.adk.agents.invocation_context import InvocationContext


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
            Optional authentication token used for secure access during initialization.
            If not provided, the agent will be accessed without authentication.
            Note: For runtime authentication, use the credential service in InvocationContext.
        auth_method (Literal["header", "querystring"] | None):
            The method of attaching the authentication token at runtime.
            - `"header"`: Token is retrieved from credential service and passed via HTTP `Authorization` header.
            - `"querystring"`: Token is retrieved from credential service and passed as a query parameter.
            - `None`: No runtime authentication injection (default).
            The credential is loaded from `InvocationContext.credential_service` using the
            app_name and user_id from the context.
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
        # Example 1: Connect using a URL (no authentication)
        agent = RemoteVeAgent(
            name="public_agent",
            url="https://vefaas.example.com/agents/public"
        )

        # Example 2: Using static Bearer token in header for initialization
        agent = RemoteVeAgent(
            name="secured_agent",
            url="https://vefaas.example.com/agents/secure",
            auth_token="my_secret_token",
            auth_method="header"
        )

        # Example 3: Using runtime authentication with credential service
        # The auth token will be automatically injected from InvocationContext.credential_service
        agent = RemoteVeAgent(
            name="dynamic_auth_agent",
            url="https://vefaas.example.com/agents/secure",
            auth_method="header"  # Will load credential at runtime
        )

        # Example 4: Using a pre-configured httpx_client
        import httpx
        client = httpx.AsyncClient(
            base_url="https://vefaas.example.com/agents/query",
            timeout=600
        )
        agent = RemoteVeAgent(
            name="query_agent",
            auth_method="querystring",  # Will load credential at runtime
            httpx_client=client
        )
        ```
    """

    auth_method: Literal["header", "querystring"] | None = None

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

        # Set auth_method if provided
        if auth_method:
            self.auth_method = auth_method

        # Wrap _run_async_impl with pre-run hook to ensure initialization
        # and authentication logic always executes, even if users override _run_async_impl
        self._wrap_run_async_impl()

    def _wrap_run_async_impl(self) -> None:
        """Wrap _run_async_impl with a decorator that ensures pre-run logic executes.

        This method wraps the _run_async_impl method with a decorator that:
        1. Executes _pre_run before the actual implementation
        2. Handles errors from _pre_run and yields error events
        3. Ensures the wrapper works even if users override _run_async_impl

        The wrapper is applied by replacing the bound method on the instance.
        """
        # Store the original _run_async_impl method
        original_run_async_impl = self._run_async_impl

        @functools.wraps(original_run_async_impl)
        async def wrapped_run_async_impl(
            ctx: InvocationContext,
        ) -> AsyncGenerator[Event, None]:
            """Wrapped version of _run_async_impl with pre-run hook."""
            # Execute pre-run initialization
            try:
                await self._pre_run(ctx)
            except Exception as e:
                yield Event(
                    author=self.name,
                    error_message=f"Failed to initialize remote A2A agent: {e}",
                    invocation_id=ctx.invocation_id,
                    branch=ctx.branch,
                )
                return

            # Call the original (or overridden) _run_async_impl
            async with Aclosing(original_run_async_impl(ctx)) as agen:
                async for event in agen:
                    yield event

        # Replace the instance method with the wrapped version
        self._run_async_impl = wrapped_run_async_impl

    async def _pre_run(self, ctx: InvocationContext) -> None:
        """Pre-run initialization and authentication setup.

        This method is called before the actual agent execution to:
        1. Ensure the agent is resolved (agent card fetched, client initialized)
        2. Inject authentication token from credential service if available

        This method is separated from _run_async_impl to ensure these critical
        initialization steps are always executed, even if users override _run_async_impl.

        Args:
            ctx: Invocation context containing session and user information

        Raises:
            Exception: If agent initialization fails
        """
        # Ensure agent is resolved
        await self._ensure_resolved()

        # Inject auth token if credential service is available
        await self._inject_auth_token(ctx)

        # Inject session_id to http headers
        if hasattr(self, "_a2a_client") and isinstance(self._a2a_client, BaseClient):
            if hasattr(self._a2a_client, "_transport") and hasattr(
                self._a2a_client._transport, "httpx_client"
            ):
                # get session_id from InvocationContext
                import uuid

                parent_name = (
                    ctx.agent.parent_agent.name
                    if hasattr(ctx.agent, "parent_agent") and ctx.agent.parent_agent
                    else self.name
                )
                user_id = (
                    ctx.session.user_id
                    if hasattr(ctx, "session")
                    and hasattr(ctx.session, "user_id")
                    and ctx.session.user_id
                    else "unknown"
                )
                session_id = (
                    ctx.session.id
                    if hasattr(ctx, "session")
                    and hasattr(ctx.session, "id")
                    and ctx.session.id
                    else str(uuid.uuid4())
                )
                x_session_id = f"{parent_name}_{user_id}_{session_id}"
                self._a2a_client._transport.httpx_client.headers.update(
                    {"x-session-id": x_session_id}
                )
                logger.debug(f"Auto-injected session_id header: {x_session_id}")

    async def _inject_auth_token(self, ctx: InvocationContext) -> None:
        """Inject authentication token from credential service into the HTTP client.

        This method retrieves the authentication token from the credential service
        in the InvocationContext and updates the HTTP client headers or query params
        based on the configured auth_method.

        Args:
            ctx: Invocation context containing credential service and user information
        """
        # Skip if no credential service in context
        if not ctx.credential_service:
            logger.debug(
                "No credential service in InvocationContext, skipping auth token injection"
            )
            return

        # Skip if client is not initialized or not a BaseClient
        if not hasattr(self, "_a2a_client") or not isinstance(
            self._a2a_client, BaseClient
        ):
            logger.debug(
                "A2A client not initialized or not a BaseClient, skipping auth token injection"
            )
            return

        # Skip if transport is not available
        if not hasattr(self._a2a_client, "_transport"):
            logger.debug(
                "A2A client transport not available, skipping auth token injection"
            )
            return

        # Skip if httpx_client is not available
        if not hasattr(self._a2a_client._transport, "httpx_client"):
            logger.debug(
                "A2A client httpx_client not available, skipping auth token injection"
            )
            return

        try:
            from veadk.utils.auth import build_auth_config
            from google.adk.agents.callback_context import CallbackContext

            # Inject TIP token via header
            workload_auth_config = build_auth_config(
                auth_method="apikey",
                credential_key=VE_TIP_TOKEN_CREDENTIAL_KEY,
                header_name=VE_TIP_TOKEN_HEADER,
            )

            tip_credential = await ctx.credential_service.load_credential(
                auth_config=workload_auth_config,
                callback_context=CallbackContext(ctx),
            )

            if tip_credential:
                self._a2a_client._transport.httpx_client.headers.update(
                    {VE_TIP_TOKEN_HEADER: tip_credential.api_key}
                )
                logger.debug(
                    f"Injected TIP token via header for app={ctx.app_name}, user={ctx.user_id}"
                )

            # Build auth config based on auth_method
            auth_config = build_auth_config(
                credential_key="inbound_auth",
                auth_method=self.auth_method or "header",
                header_scheme="bearer",
            )

            # Load credential from credential service
            credential = await ctx.credential_service.load_credential(
                auth_config=auth_config,
                callback_context=CallbackContext(ctx),
            )

            if not credential:
                logger.debug(
                    f"No credential loaded, skipping auth token injection for app={ctx.app_name}, user={ctx.user_id}"
                )
                return

            # Inject credential based on auth_method
            if self.auth_method == "querystring":
                # Extract API key
                api_key = credential.api_key
                new_params = dict(self._a2a_client._transport.httpx_client.params)
                new_params.update({"token": api_key})
                self._a2a_client._transport.httpx_client.params = new_params
                logger.debug(
                    f"Injected auth token via querystring for app={ctx.app_name}, user={ctx.user_id}"
                )
            else:
                if headers := generate_headers(credential):
                    self._a2a_client._transport.httpx_client.headers.update(headers)
                    logger.debug(
                        f"Injected auth token via header for app={ctx.app_name}, user={ctx.user_id}"
                    )

        except Exception as e:
            logger.warning(f"Failed to inject auth token: {e}", exc_info=True)
