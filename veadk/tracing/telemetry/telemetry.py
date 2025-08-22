from typing import Any

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool
from opentelemetry import trace
from opentelemetry.sdk.trace import _Span

from veadk.tracing.telemetry.attributes.attributes import ATTRIBUTES
from veadk.tracing.telemetry.attributes.extractors.llm_attributes_extractors import (
    LLMAttributesParams,
)
from veadk.tracing.telemetry.attributes.extractors.tool_attributes_extractors import (
    ToolAttributesParams,
)
from veadk.tracing.telemetry.exporters import inmemory_exporter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def trace_send_data(): ...


def set_common_attributes(current_span: _Span, **kwargs) -> None:
    if current_span.context:
        current_span_id = current_span.context.trace_id

    spans = inmemory_exporter.inmemory_span_processor.spans

    spans_in_current_trace = [
        span
        for span in spans
        if span.context and span.context.trace_id == current_span_id
    ]

    common_attributes = ATTRIBUTES.get("common", {})
    for span in spans_in_current_trace:
        for attr_name, attr_extractor in common_attributes.items():
            value = attr_extractor(**kwargs)
            span.set_attribute(attr_name, value)


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

    set_common_attributes(
        current_span=span,  # type: ignore
        agent_name=invocation_context.agent.name,
        app_name=invocation_context.app_name,
        user_id=invocation_context.user_id,
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
