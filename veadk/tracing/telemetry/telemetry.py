from typing import Any

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool
from opentelemetry import trace
from opentelemetry.trace.span import Span

from veadk.tracing.telemetry.attributes.attributes import ATTRIBUTES
from veadk.tracing.telemetry.attributes.extractors.llm_attributes_extractors import (
    LLMAttributesParams,
)
from veadk.tracing.telemetry.attributes.extractors.tool_attributes_extractors import (
    ToolAttributesParams,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _set_common_attributes(
    span: Span, app_name: str, user_id: str, session_id: str
) -> None:
    common_attributes = ATTRIBUTES.get("common", {})
    for attr_name, attr_extractor in common_attributes.items():
        value = attr_extractor(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        span.set_attribute(attr_name, value)


def trace_send_data(): ...


def trace_tool_call(
    tool: BaseTool,
    args: dict[str, Any],
    function_response_event: Event,
) -> None:
    span = trace.get_current_span()

    tool_attributes = ATTRIBUTES.get("tool", {})
    for attr_name, attr_extractor in tool_attributes.items():
        params = ToolAttributesParams(tool, args, function_response_event)
        # set attribute anyway
        value = attr_extractor(params)
        if isinstance(value, list):
            for _value in value:
                for key, val in _value.items():
                    # gen_ai. and gen_ai_
                    span.set_attribute(f"{attr_name}{key}", val)
        else:
            span.set_attribute(attr_name, value)


def trace_call_llm(
    invocation_context: InvocationContext,
    event_id: str,
    llm_request: LlmRequest,
    llm_response: LlmResponse,
) -> None:
    span = trace.get_current_span()

    _set_common_attributes(
        span=span,
        app_name=invocation_context.session.app_name,
        user_id=invocation_context.session.user_id,
        session_id=invocation_context.session.id,
    )

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
                    span.set_attribute(f"{attr_name}{key}", val)
        else:
            span.set_attribute(attr_name, value)
