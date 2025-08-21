from typing import Any

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool
from google.genai import types
from opentelemetry import trace

from veadk.tracing.telemetry.attributes.attributes import ATTRIBUTES
from veadk.tracing.telemetry.attributes.extractors.llm_attributes_extrators import (
    LLMAttributesParams,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _set_common_attributes():
    pass


def trace_send_data(
    invocation_context: InvocationContext,
    event_id: str,
    data: list[types.Content],
) -> None: ...


def trace_tool_call(
    tool: BaseTool,
    args: dict[str, Any],
    function_response_event: Event,
) -> None:
    print("tool_call")


def trace_call_llm(
    invocation_context: InvocationContext,
    event_id: str,
    llm_request: LlmRequest,
    llm_response: LlmResponse,
) -> None:
    span = trace.get_current_span()

    llm_attributes = ATTRIBUTES.get("llm", {})

    for attr_name, attr_extractor in llm_attributes.items():
        params = LLMAttributesParams(
            invocation_context, event_id, llm_request, llm_response
        )
        # set attribute anyway
        value = attr_extractor(params)
        if isinstance(value, list):
            for _value in value:
                for key, val in _value.items():
                    # gen_ai. and gen_ai_
                    logger.debug(f"Set attribute {attr_name}{key} = {val}")
                    span.set_attribute(f"{attr_name}{key}", val)
        else:
            span.set_attribute(attr_name, value)
