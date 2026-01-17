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
from typing import AsyncGenerator

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai.types import Content, Part

from veadk import Agent
from veadk.agents.supervise_agent import generate_advice
from veadk.flows.supervise_single_flow import SupervisorSingleFlow
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class SupervisorAutoFlow(SupervisorSingleFlow):
    def __init__(self, supervised_agent: Agent):
        super().__init__(supervised_agent)

    async def _call_llm_async(
        self,
        invocation_context: InvocationContext,
        llm_request: LlmRequest,
        model_response_event: Event,
    ) -> AsyncGenerator[LlmResponse, None]:
        supervisor_response = await generate_advice(self._supervisor, llm_request)
        logger.debug(f"Advice from supervisor: {supervisor_response}")

        advice_and_reason = json.loads(supervisor_response)

        if advice_and_reason["advice"]:
            logger.debug("Add supervisor advice to llm request.")
            llm_request.contents.append(
                Content(
                    parts=[
                        Part(
                            text=f"""Message from your supervisor (not user): {advice_and_reason["advice"]}, the corresponding reason is {advice_and_reason["reason"]}

    Please follow the advice and reason above to optimize your actions.
    """
                        )
                    ],
                    role="user",
                )
            )
        else:
            logger.info(
                f"Supervisor advice is empty, reason: {advice_and_reason['reason']}. Skip adding to llm request."
            )

        async for llm_response in super()._call_llm_async(
            invocation_context, llm_request, model_response_event
        ):
            yield llm_response
