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

logger = get_logger(__name__)


def _upload_metrics(
    invocation_context: InvocationContext,
    event_id: str,
    llm_request: LlmRequest,
    llm_response: LlmResponse,
) -> None:
    from veadk.agent import Agent

    if isinstance(invocation_context.agent, Agent):
        tracers = invocation_context.agent.tracers
        for tracer in tracers:
            for exporter in getattr(tracer, "exporters", []):
                if getattr(exporter, "meter_uploader", None):
                    exporter.meter_uploader.record(
                        invocation_context, event_id, llm_request, llm_response
                    )


def _set_agent_input_attribute(
    span: Span, invocation_context: InvocationContext
) -> None:
    # We only save the original user input as the agent input
    # hence once the `agent.input` has been set, we don't overwrite it
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
                    {f"parts.{idx}.type": "text", f"parts.{idx}.content": part.text},
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
    content = llm_response.content
    if content and content.parts:
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
                "gen_ai.usage.total_tokens", accumulated_total_token_usage
            )

        if agent_run_span and agent_run_span.name.startswith("agent_run"):
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
) -> None:
    span = trace.get_current_span()

    set_common_attributes_on_tool_span(current_span=span)  # type: ignore

    tool_attributes_mapping = ATTRIBUTES.get("tool", {})
    params = ToolAttributesParams(tool, args, function_response_event)

    for attr_name, attr_extractor in tool_attributes_mapping.items():
        response: ExtractorResponse = attr_extractor(params)
        ExtractorResponse.update_span(span, attr_name, response)


def trace_call_llm(
    invocation_context: InvocationContext,
    event_id: str,
    llm_request: LlmRequest,
    llm_response: LlmResponse,
) -> None:
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

    _upload_metrics(invocation_context, event_id, llm_request, llm_response)


# Do not modify this function
def trace_send_data(): ...
