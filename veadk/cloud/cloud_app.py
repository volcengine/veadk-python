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
import time
from typing import Any
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import AgentCard, Message, MessageSendParams, SendMessageRequest

from veadk.config import getenv
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class CloudApp:
    """Represents a deployed cloud agent application on Volcengine FaaS platform.

    This class facilitates interaction with the deployed agent via A2A protocol,
    supports self-management like update and delete, and handles endpoint resolution.

    It uses HTTP client for async communications.

    Attributes:
        vefaas_application_name (str): Name of the VeFaaS application. Defaults to "".
        vefaas_endpoint (str): URL for accessing the application. Resolved if not provided.
        vefaas_application_id (str): Unique identifier of the application. Defaults to "".
        use_agent_card (bool): Flag to resolve endpoint via agent card. Defaults to False.
        httpx_client (httpx.AsyncClient): Async HTTP client for requests.

    Note:
        At least one of name, endpoint, or ID must be provided during init.
        Agent card mode fetches card from the endpoint's public path.

    Examples:
        ```python
        from veadk.cloud.cloud_app import CloudApp
        app = CloudApp(vefaas_endpoint="https://my-agent.volcengine.com")
        response = await app.message_send("Query", "session-1", "user-123")
        print(response.message_id)
        ```
    """

    def __init__(
        self,
        vefaas_application_name: str = "",
        vefaas_endpoint: str = "",
        vefaas_application_id: str = "",
        use_agent_card: bool = False,
    ):
        """Initializes the CloudApp with VeFaaS application details.

        Sets attributes, validates inputs, resolves endpoint if missing, and creates HTTP client.

        Args:
            vefaas_application_name (str, optional): Application name for lookup. Defaults to "".
            vefaas_endpoint (str, optional): Direct endpoint URL. Defaults to "".
            vefaas_application_id (str, optional): Application ID for lookup. Defaults to "".
            use_agent_card (bool): Use agent card to determine invocation URL. Defaults to False.

        Returns:
            None

        Raises:
            ValueError: If no app identifiers provided or endpoint lacks http/https prefix.

        Note:
            Logs info if agent card mode enabled.
            Endpoint is fetched via _get_vefaas_endpoint if not set.

        Examples:
            ```python
            app = CloudApp(vefaas_application_id="app-123", use_agent_card=True)
            ```
        """
        self.vefaas_endpoint = vefaas_endpoint
        self.vefaas_application_id = vefaas_application_id
        self.vefaas_application_name = vefaas_application_name
        self.use_agent_card = use_agent_card

        # vefaas must be set one of three
        if (
            not vefaas_endpoint
            and not vefaas_application_id
            and not vefaas_application_name
        ):
            raise ValueError(
                "VeFaaS CloudAPP must be set one of endpoint, application_id, or application_name."
            )

        if not vefaas_endpoint:
            self.vefaas_endpoint = self._get_vefaas_endpoint()

        if (
            self.vefaas_endpoint
            and not self.vefaas_endpoint.startswith("http")
            and not self.vefaas_endpoint.startswith("https")
        ):
            raise ValueError(
                f"Invalid endpoint: {vefaas_endpoint}. The endpoint must start with `http` or `https`."
            )

        if use_agent_card:
            logger.info(
                "Use agent card to invoke agent. The agent endpoint will use the `url` in agent card."
            )

        self.httpx_client = httpx.AsyncClient()

    def _get_vefaas_endpoint(
        self,
        volcengine_ak: str = getenv("VOLCENGINE_ACCESS_KEY"),
        volcengine_sk: str = getenv("VOLCENGINE_SECRET_KEY"),
    ) -> str:
        """Fetches the application endpoint from VeFaaS details if not directly provided.

        Uses VeFaaS client to get app info and parse CloudResource JSON for URL.

        Args:
            volcengine_ak (str, optional): Volcengine access key. Defaults to env var.
            volcengine_sk (str, optional): Volcengine secret key. Defaults to env var.

        Returns:
            str: The system URL from CloudResource or empty string on failure.

        Raises:
            ValueError: If application not found by ID or name.

        Note:
            Logs warning if JSON parsing fails; returns empty on error.
            Called during init if endpoint missing.

        Examples:
            ```python
            endpoint = app._get_vefaas_endpoint("custom-ak", "custom-sk")
            ```
        """
        from veadk.integrations.ve_faas.ve_faas import VeFaaS

        vefaas_client = VeFaaS(access_key=volcengine_ak, secret_key=volcengine_sk)

        app = vefaas_client.get_application_details(
            app_id=self.vefaas_application_id,
            app_name=self.vefaas_application_name,
        )

        if not app:
            raise ValueError(
                f"VeFaaS CloudAPP with application_id `{self.vefaas_application_id}` or application_name `{self.vefaas_application_name}` not found."
            )

        try:
            cloud_resource = json.loads(app["CloudResource"])
            vefaas_endpoint = cloud_resource["framework"]["url"]["system_url"]
        except Exception as e:
            logger.warning(f"VeFaaS cloudAPP could not get endpoint. Error: {e}")
            vefaas_endpoint = ""
        return vefaas_endpoint

    def _get_vefaas_application_id_by_name(self) -> str:
        """Retrieves the application ID using the configured name.

        Instantiates VeFaaS client and queries by name.

        Returns:
            str: The found application ID.

        Raises:
            ValueError: If vefaas_application_name is not set.

        Note:
            Uses default environment credentials.
            Internal method for ID resolution.

        Examples:
            ```python
            app.vefaas_application_name = "my-app"
            id = app._get_vefaas_application_id_by_name()
            ```
        """
        if not self.vefaas_application_name:
            raise ValueError(
                "VeFaaS CloudAPP must be set application_name to get application_id."
            )
        from veadk.integrations.ve_faas.ve_faas import VeFaaS

        vefaas_client = VeFaaS(
            access_key=getenv("VOLCENGINE_ACCESS_KEY"),
            secret_key=getenv("VOLCENGINE_SECRET_KEY"),
        )
        vefaas_application_id = vefaas_client.find_app_id_by_name(
            self.vefaas_application_name
        )
        return vefaas_application_id

    async def _get_a2a_client(self) -> A2AClient:
        """Constructs an A2A client configured for this cloud app.

        If use_agent_card, resolves agent card and uses its URL; otherwise uses direct endpoint.

        Args:
            self: The CloudApp instance.

        Returns:
            A2AClient: Ready-to-use A2A client.

        Note:
            Manages httpx_client context.
            For card mode, fetches from base_url/ (public card).
        """
        if self.use_agent_card:
            async with self.httpx_client as httpx_client:
                resolver = A2ACardResolver(
                    httpx_client=httpx_client, base_url=self.vefaas_endpoint
                )

                final_agent_card_to_use: AgentCard | None = None
                _public_card = (
                    await resolver.get_agent_card()
                )  # Fetches from default public path
                final_agent_card_to_use = _public_card

                return A2AClient(
                    httpx_client=self.httpx_client, agent_card=final_agent_card_to_use
                )
        else:
            return A2AClient(httpx_client=self.httpx_client, url=self.vefaas_endpoint)

    def update_self(
        self,
        volcengine_ak: str = getenv("VOLCENGINE_ACCESS_KEY"),
        volcengine_sk: str = getenv("VOLCENGINE_SECRET_KEY"),
    ):
        """Updates the configuration of this cloud application.

        Currently a placeholder; implementation pending.

        Args:
            volcengine_ak (str, optional): Access key for VeFaaS. Defaults to env var.
            volcengine_sk (str, optional): Secret key for VeFaaS. Defaults to env var.

        Returns:
            None

        Raises:
            ValueError: If access key or secret key missing.

        Examples:
            ```python
            app.update_self("ak", "sk")
            ```
        """
        if not volcengine_ak or not volcengine_sk:
            raise ValueError("Volcengine access key and secret key must be set.")

        # TODO(floritange): support update cloud app

    def delete_self(
        self,
        volcengine_ak: str = getenv("VOLCENGINE_ACCESS_KEY"),
        volcengine_sk: str = getenv("VOLCENGINE_SECRET_KEY"),
    ):
        """Deletes this cloud application after interactive confirmation.

        Issues delete to VeFaaS and polls for completion.

        Args:
            volcengine_ak (str, optional): Access key. Defaults to env var.
            volcengine_sk (str, optional): Secret key. Defaults to env var.

        Returns:
            None

        Raises:
            ValueError: If credentials not provided.

        Note:
            Fetches ID if not set using name.
            Polls every 3 seconds until app no longer exists.
            Prints status messages.

        Examples:
            ```python
            app.delete_self()
            ```
        """
        if not volcengine_ak or not volcengine_sk:
            raise ValueError("Volcengine access key and secret key must be set.")

        if not self.vefaas_application_id:
            self.vefaas_application_id = self._get_vefaas_application_id_by_name()

        confirm = input(
            f"Confirm delete cloud app {self.vefaas_application_id}? (y/N): "
        )
        if confirm.lower() != "y":
            print("Delete cancelled.")
            return
        else:
            from veadk.integrations.ve_faas.ve_faas import VeFaaS

            vefaas_client = VeFaaS(access_key=volcengine_ak, secret_key=volcengine_sk)
            vefaas_client.delete(self.vefaas_application_id)
            print(
                f"Cloud app {self.vefaas_application_id} delete request has been sent to VeFaaS"
            )
            while True:
                try:
                    id = self._get_vefaas_application_id_by_name()
                    if not id:
                        break
                    time.sleep(3)
                except Exception as _:
                    break
            print("Delete application done.")

    async def message_send(
        self, message: str, session_id: str, user_id: str, timeout: float = 600.0
    ) -> Message | None:
        """Sends a user message to the cloud agent and retrieves the response.

        Constructs A2A SendMessageRequest and executes via client.

        Args:
            message (str): Text content of the user message.
            session_id (str): Identifier for the conversation session.
            user_id (str): Identifier for the user.
            timeout (float): Maximum wait time in seconds. Defaults to 600.0.

        Returns:
            Message | None: Assistant response message or None if error occurs.

        Raises:
            Exception: Communication or processing errors; error is printed.

        Note:
            Uses UUID for message and request IDs.
            Payload includes role 'user' and text part.
            Debug logs the full response.
            Ignores type checks for result as it may not be Task.

        Examples:
            ```python
            response = await app.message_send("What is AI?", "chat-1", "user-1", timeout=300)
            print(response.content)
            ```
        """
        a2a_client = await self._get_a2a_client()

        async with self.httpx_client:
            send_message_payload: dict[str, Any] = {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                    "messageId": uuid4().hex,
                },
                "metadata": {
                    "user_id": user_id,
                    "session_id": session_id,
                },
            }
            try:
                message_send_request = SendMessageRequest(
                    id=uuid4().hex,
                    params=MessageSendParams(**send_message_payload),
                )

                res = await a2a_client.send_message(
                    message_send_request,
                    http_kwargs={"timeout": httpx.Timeout(timeout)},
                )

                logger.debug(
                    f"Message sent to cloud app {self.vefaas_application_name} with response: {res}"
                )

                # we ignore type checking here, because the response
                # from CloudApp will not be `Task` type
                return res.root.result  # type: ignore
            except Exception as e:
                # TODO(floritange): show error log on VeFaaS function
                print(e)
                return None


def get_message_id(message: Message):
    """Extracts the unique ID from an A2A Message object.

    Checks for both legacy 'messageId' and current 'message_id' attributes.

    Args:
        message (Message): The A2A message instance.

    Returns:
        str: The message identifier.

    Note:
        Ensures compatibility with a2a-python versions before and after 0.3.0.
        Prefers 'message_id' if available, falls back to 'messageId'.

    Examples:
        ```python
        mid = get_message_id(response_message)
        print(mid)
        ```
    """
    if getattr(message, "messageId", None):
        # Compatible with the messageId of the old a2a-python version (<0.3.0) in cloud app
        return message.messageId  # type: ignore
    else:
        return message.message_id
