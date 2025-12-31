from typing import AsyncGenerator

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.flows.llm_flows.single_flow import SingleFlow
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from typing_extensions import override

from veadk import Agent
from veadk.agents.supervise_agent import build_supervisor


class SupervisorSingleFlow(SingleFlow):
    def __init__(self, supervised_agent: Agent):
        self._supervisor = build_supervisor(supervised_agent)

        super().__init__()

    @override
    async def _call_llm_async(
        self,
        invocation_context: InvocationContext,
        llm_request: LlmRequest,
        model_response_event: Event,
    ) -> AsyncGenerator[LlmResponse, None]:
        async for llm_response in super()._call_llm_async(
            invocation_context, llm_request, model_response_event
        ):
            yield llm_response
