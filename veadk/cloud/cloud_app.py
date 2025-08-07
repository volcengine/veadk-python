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

from typing import Any
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import AgentCard, Message, MessageSendParams, SendMessageRequest

from veadk.config import getenv
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class CloudApp:
    """CloudApp class.

    Args:
        name (str): The name of the cloud app.
        endpoint (str): The endpoint of the cloud app.
        use_agent_card (bool): Whether to use agent card to invoke agent. If True, the client will post to the url in agent card. Otherwise, the client will post to the endpoint directly. Default False (cause the agent card and agent usually use the same endpoint).
    """

    def __init__(
        self,
        vefaas_application_name: str,
        vefaas_endpoint: str,
        vefaas_application_id: str,
        use_agent_card: bool = False,
    ):
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

        if not self.vefaas_endpoint.startswith(
            "http"
        ) and not self.vefaas_endpoint.startswith("https"):
            raise ValueError(
                f"Invalid endpoint: {vefaas_endpoint}. The endpoint must start with `http` or `https`."
            )

        if use_agent_card:
            logger.info(
                "Use agent card to invoke agent. The agent endpoint will use the `url` in agent card."
            )

        self.httpx_client = httpx.AsyncClient()

    def _get_vefaas_endpoint(self) -> str:
        vefaas_endpoint = ""

        if self.vefaas_application_id:
            # TODO(zakahan): get endpoint from vefaas
            vefaas_endpoint = ...
            return vefaas_endpoint

        if self.vefaas_application_name:
            # TODO(zakahan): get endpoint from vefaas
            vefaas_endpoint = ...
            return vefaas_endpoint

    def _get_vefaas_application_id_by_name(self) -> str:
        if not self.vefaas_application_name:
            raise ValueError(
                "VeFaaS CloudAPP must be set application_name to get application_id."
            )
        # TODO(zakahan): get application id from vefaas application name
        vefaas_application_id = ""
        return vefaas_application_id

    async def _get_a2a_client(self) -> A2AClient:
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
        if not volcengine_ak or not volcengine_sk:
            raise ValueError("Volcengine access key and secret key must be set.")

        # TODO(floritange): support update cloud app

    def delete_self(
        self,
        volcengine_ak: str = getenv("VOLCENGINE_ACCESS_KEY"),
        volcengine_sk: str = getenv("VOLCENGINE_SECRET_KEY"),
    ):
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
            from veadk.cli.services.vefaas.vefaas import VeFaaS

            vefaas_client = VeFaaS(access_key=volcengine_ak, secret_key=volcengine_sk)
            vefaas_client.delete(self.vefaas_application_id)
            print(f"Cloud app {self.vefaas_application_id} is deleting...")

    async def message_send(
        self, message: str, session_id: str, user_id: str, timeout: float = 600.0
    ) -> Message | None:
        """
        timeout is in seconds, default 600s (10 minutes)
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
                return res.root.result
            except Exception as e:
                # TODO(floritange): show error log on VeFaaS function
                print(e)
                return None
