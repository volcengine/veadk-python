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

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool
from opentelemetry import trace
from opentelemetry.context import get_value
from opentelemetry.sdk.trace import Span, _Span

from veadk.tracing.telemetry.attributes.attributes import ATTRIBUTES
from veadk.tracing.telemetry.attributes.extractors.types import (
    ExtractorResponse,
    LLMAttributesParams,
    ToolAttributesParams,
)
from veadk.utils.logger import get_logger
from veadk.utils.misc import safe_json_serialize

logger = get_logger(__name__)

meter_uploader = None


def _upload_call_llm_metrics(
    invocation_context: InvocationContext,
    event_id: str,
    llm_request: LlmRequest,
    llm_response: LlmResponse,
) -> None:
    """Upload LLM call metrics to configured meter uploaders.

    This function extracts meter uploaders from agent tracers and records
    LLM call metrics including token usage, latency, and request/response details.

    Args:
        invocation_context: Context containing agent, session, and user information
        event_id: Unique identifier for this LLM call event
        llm_request: The request sent to the language model
        llm_response: The response received from the language model
    """
    from veadk.agent import Agent

    if isinstance(invocation_context.agent, Agent):
        tracers = invocation_context.agent.tracers
        for tracer in tracers:
            for exporter in getattr(tracer, "exporters", []):
                if getattr(exporter, "meter_uploader", None):
                    global meter_uploader
                    meter_uploader = exporter.meter_uploader
                    exporter.meter_uploader.record_call_llm(
                        invocation_context, event_id, llm_request, llm_response
                    )


def _upload_tool_call_metrics(
    tool: BaseTool,
    args: dict[str, Any],
    function_response_event: Event,
):
    """Upload tool call metrics to the global meter uploader.

    Records tool execution metrics including function name, arguments,
    execution time, and response details for observability and debugging.

    Args:
        tool: The tool instance that was executed
        args: Arguments passed to the tool function
        function_response_event: Event containing the tool's response data

    Note:
        - Requires global meter_uploader to be initialized
    """
    global meter_uploader
    if meter_uploader:
        meter_uploader.record_tool_call(tool, args, function_response_event)
    else:
        logger.warning(
            "Meter uploader is not initialized yet. Skip recording tool call metrics."
        )


def _set_agent_input_attribute(
    span: Span, invocation_context: InvocationContext
) -> None:
    """Set agent input attributes and events on the given span.

    This function captures the original user input and adds it as span attributes
    and events in OpenTelemetry format. It handles both text and image content
    while avoiding duplicate entries for the same input.

    Args:
        span: The OpenTelemetry span to annotate with input data
        invocation_context: Context containing user input and session information

    Note:
        - Only sets input once per span to avoid duplication
        - Supports multimodal content (text and images)
        - Follows gen_ai attribute conventions
    """
    event_names = [event.name for event in span.events]
    if "gen_ai.user.message" in event_names:
        return

    # input = {
    #     "agent_name": invocation_context.agent.name,
    #     "app_name": invocation_context.session.app_name,
    #     "user_id": invocation_context.user_id,
    #     "session_id": invocation_context.session.id,
    #     "input": invocation_context.user_content.model_dump(exclude_none=True)
    #     if invocation_context.user_content
    #     else None,
    # }

    user_content = invocation_context.user_content
    if user_content and user_content.parts:
        # set gen_ai.input attribute required by APMPlus
        span.set_attribute(
            "gen_ai.input",
            safe_json_serialize(user_content.model_dump(exclude_none=True)),
        )
        span.add_event(
            "gen_ai.user.message",
            {
                "agent_name": invocation_context.agent.name,
                "app_name": invocation_context.session.app_name,
                "user_id": invocation_context.user_id,
                "session_id": invocation_context.session.id,
            },
        )
        for idx, part in enumerate(user_content.parts):
            if part.text:
                span.add_event(
                    "gen_ai.user.message",
                    {
                        f"parts.{idx}.type": "text",
                        f"parts.{idx}.content": part.text,
                    },
                )
            if part.inline_data:
                span.add_event(
                    "gen_ai.user.message",
                    {
                        f"parts.{idx}.type": "image_url",
                        f"parts.{idx}.image_url.name": (
                            part.inline_data.display_name.split("/")[-1]
                            if part.inline_data.display_name
                            else "<unknown_image_name>"
                        ),
                        f"parts.{idx}.image_url.url": (
                            part.inline_data.display_name
                            if part.inline_data.display_name
                            else "<unknown_image_url>"
                        ),
                    },
                )


def _set_agent_output_attribute(span: Span, llm_response: LlmResponse) -> None:
    """Set agent output attributes and events on the given span.

    Captures the LLM response content and adds it as span attributes and events
    in OpenTelemetry format for tracing and observability purposes.

    Args:
        span: The OpenTelemetry span to annotate with output data
        llm_response: The language model response containing generated content

    Note:
        - Follows gen_ai attribute conventions
        - Handles multipart responses with proper indexing
    """
    content = llm_response.content
    if content and content.parts:
        # set gen_ai.output attribute required by APMPlus
        span.set_attribute(
            "gen_ai.output",
            safe_json_serialize(content.model_dump(exclude_none=True)),
        )

        for idx, part in enumerate(content.parts):
            if part.text:
                span.add_event(
                    "gen_ai.choice",
                    {
                        f"message.parts.{idx}.type": "text",
                        f"message.parts.{idx}.text": part.text,
                    },
                )


def set_common_attributes_on_model_span(
    invocation_context: InvocationContext,
    llm_response: LlmResponse,
    current_span: _Span,
    **kwargs,
) -> None:
    """Set common attributes on model-related spans including invocation and agent run spans.

    This function applies standardized attributes across multiple span types to ensure
    consistent telemetry data. It handles token usage accumulation, input/output
    annotation, and hierarchical span attribute propagation.

    Key Operations:
    - Sets agent input/output on invocation and agent run spans
    - Accumulates token usage across multiple LLM calls
    - Applies common attributes from the ATTRIBUTES mapping
    - Handles span hierarchy and context propagation

    Args:
        invocation_context: Context containing agent, session, and user information
        llm_response: The language model response with usage metadata
        current_span: The current OpenTelemetry span being processed
        **kwargs: Additional keyword arguments for attribute extraction
    """
    common_attributes = ATTRIBUTES.get("common", {})
    try:
        invocation_span: Span = get_value("invocation_span_instance")  # type: ignore
        agent_run_span: Span = get_value("agent_run_span_instance")  # type: ignore

        if invocation_span and invocation_span.name.startswith("invocation"):
            _set_agent_input_attribute(invocation_span, invocation_context)
            _set_agent_output_attribute(invocation_span, llm_response)
            for attr_name, attr_extractor in common_attributes.items():
                value = attr_extractor(**kwargs)
                invocation_span.set_attribute(attr_name, value)

            # Calculate the token usage for the whole invocation span
            current_step_token_usage = (
                llm_response.usage_metadata.total_token_count
                if llm_response.usage_metadata
                and llm_response.usage_metadata.total_token_count
                else 0
            )
            prev_total_token_usage = (
                invocation_span.attributes["gen_ai.usage.total_tokens"]
                if invocation_span.attributes
                else 0
            )
            accumulated_total_token_usage = (
                current_step_token_usage + int(prev_total_token_usage)  # type: ignore
            )  # we can ignore this warning, cause we manually set the attribute to int before
            invocation_span.set_attribute(
                # record input/output token usage?
                "gen_ai.usage.total_tokens",
                accumulated_total_token_usage,
            )

        if agent_run_span and (
            agent_run_span.name.startswith("agent_run")
            or agent_run_span.name.startswith("invoke_agent")
        ):
            _set_agent_input_attribute(agent_run_span, invocation_context)
            _set_agent_output_attribute(agent_run_span, llm_response)
            for attr_name, attr_extractor in common_attributes.items():
                value = attr_extractor(**kwargs)
                agent_run_span.set_attribute(attr_name, value)

        for attr_name, attr_extractor in common_attributes.items():
            value = attr_extractor(**kwargs)
            current_span.set_attribute(attr_name, value)
    except Exception as e:
        logger.error(f"Failed to set common attributes for spans: {e}")


def set_common_attributes_on_tool_span(current_span: _Span) -> None:
    """Set common attributes on tool execution spans.

    Propagates common attributes from the parent invocation span to tool spans
    to maintain consistent context across the execution trace hierarchy.

    Args:
        current_span: The tool execution span to annotate with common attributes
    """
    common_attributes = ATTRIBUTES.get("common", {})

    invocation_span: Span = get_value("invocation_span_instance")  # type: ignore

    for attr_name in common_attributes.keys():
        if (
            invocation_span
            and invocation_span.name.startswith("invocation")
            and invocation_span.attributes
            and attr_name in invocation_span.attributes
        ):
            current_span.set_attribute(attr_name, invocation_span.attributes[attr_name])


def trace_tool_call(
    tool: BaseTool,
    args: dict[str, Any],
    function_response_event: Event,
    **kwargs,
) -> None:
    """Trace a tool function call with comprehensive telemetry data.

    This function is the main entry point for tool call tracing, capturing
    execution details, arguments, responses, and performance metrics for
    debugging and observability purposes.

    Tracing Data Captured:
    - Tool name and function signature
    - Input arguments and parameter values
    - Execution timing and performance metrics
    - Response data and return values
    - Error information if execution fails
    - Common context attributes (user, session, agent)

    Args:
        tool: The tool instance being executed
        args: Dictionary of arguments passed to the tool function
        function_response_event: Event containing the tool's execution response
    """
    span = trace.get_current_span()

    set_common_attributes_on_tool_span(current_span=span)  # type: ignore

    tool_attributes_mapping = ATTRIBUTES.get("tool", {})
    params = ToolAttributesParams(tool, args, function_response_event)

    for attr_name, attr_extractor in tool_attributes_mapping.items():
        response: ExtractorResponse = attr_extractor(params)
        ExtractorResponse.update_span(span, attr_name, response)

    _upload_tool_call_metrics(tool, args, function_response_event)


def trace_call_llm(
    invocation_context: InvocationContext,
    event_id: str,
    llm_request: LlmRequest,
    llm_response: LlmResponse,
    *args,
    **kwargs,
) -> None:
    """Trace a language model call with comprehensive telemetry data.

    This function is the main entry point for LLM call tracing, capturing
    request/response details, token usage, timing, and context information
    for cost tracking, performance analysis, and debugging.

    Tracing Data Captured:
    - Model name and provider information
    - Request parameters and prompt content
    - Response content and metadata
    - Token usage (input, output, total)
    - Execution timing and latency
    - Context information (user, session, agent)
    - Error information if the call fails

    Args:
        invocation_context: Context containing agent, session, and user information
        event_id: Unique identifier for this LLM call event
        llm_request: The request object sent to the language model
        llm_response: The response object received from the language model
    """
    span: Span = trace.get_current_span()  # type: ignore

    from veadk.agent import Agent

    set_common_attributes_on_model_span(
        invocation_context=invocation_context,
        llm_response=llm_response,
        current_span=span,  # type: ignore
        agent_name=invocation_context.agent.name,
        user_id=invocation_context.user_id,
        app_name=invocation_context.app_name,
        session_id=invocation_context.session.id,
        invocation_id=invocation_context.invocation_id,
        model_provider=invocation_context.agent.model_provider
        if isinstance(invocation_context.agent, Agent)
        else "",
        model_name=invocation_context.agent.model_name
        if isinstance(invocation_context.agent, Agent)
        else "",
        call_type=(
            span.context.trace_state.get("call_type", "")
            if (
                hasattr(span, "context")
                and span.context
                and hasattr(span.context, "trace_state")
                and hasattr(span.context.trace_state, "get")
            )
            else ""
        ),
    )

    llm_attributes_mapping = ATTRIBUTES.get("llm", {})
    params = LLMAttributesParams(
        invocation_context=invocation_context,
        event_id=event_id,
        llm_request=llm_request,
        llm_response=llm_response,
    )

    for attr_name, attr_extractor in llm_attributes_mapping.items():
        response: ExtractorResponse = attr_extractor(params)
        ExtractorResponse.update_span(span, attr_name, response)

    _upload_call_llm_metrics(invocation_context, event_id, llm_request, llm_response)


# Do not modify this function
def trace_send_data(**kwargs): ...
