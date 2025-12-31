from typing import AsyncGenerator

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai.types import Content, Part
from typing_extensions import override

from veadk import Agent
from veadk.agents.supervise_agent import generate_advice
from veadk.flows.supervisor_single_flow import SupervisorSingleFlow
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class SupervisorAutoFlow(SupervisorSingleFlow):
    def __init__(self, supervised_agent: Agent):
        super().__init__(supervised_agent)

    @override
    async def _call_llm_async(
        self,
        invocation_context: InvocationContext,
        llm_request: LlmRequest,
        model_response_event: Event,
    ) -> AsyncGenerator[LlmResponse, None]:
        advice = await generate_advice(self._supervisor, llm_request)
        logger.debug(f"Advice from supervisor: {advice}")

        llm_request.contents.append(
            Content(
                parts=[Part(text=f"Message from your supervisor: {advice}")],
                role="user",
            )
        )

        print("====")
        print(llm_request)

        async for llm_response in super()._call_llm_async(
            invocation_context, llm_request, model_response_event
        ):
            yield llm_response
