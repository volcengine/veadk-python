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
from opentelemetry.sdk.trace import _Span

from veadk.tracing.telemetry.attributes.attributes import ATTRIBUTES
from veadk.tracing.telemetry.attributes.extractors.types import (
    ExtractorResponse,
    LLMAttributesParams,
    ToolAttributesParams,
)
from veadk.tracing.telemetry.exporters.inmemory_exporter import (
    _INMEMORY_EXPORTER_INSTANCE,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def upload_metrics(
    invocation_context: InvocationContext,
    llm_request: LlmRequest,
    llm_response: LlmResponse,
) -> None:
    from veadk.agent import Agent

    if isinstance(invocation_context.agent, Agent):
        tracers = invocation_context.agent.tracers
        for tracer in tracers:
            for exporter in getattr(tracer, "exporters", []):
                if getattr(exporter, "meter_uploader", None):
                    exporter.meter_uploader.record(llm_request, llm_response)


def _set_agent_input_attribute(
    span: _Span, invocation_context: InvocationContext
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


def _set_agent_output_attribute(span: _Span, llm_response: LlmResponse) -> None:
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
    if current_span.context:
        current_span_id = current_span.context.trace_id
    else:
        logger.warning(
            "Current span context is missing, failed to get `trace_id` to set common attributes."
        )
        return

    try:
        spans = _INMEMORY_EXPORTER_INSTANCE.processor.spans  # type: ignore

        spans_in_current_trace = [
            span
            for span in spans
            if span.context and span.context.trace_id == current_span_id
        ]

        common_attributes = ATTRIBUTES.get("common", {})
        for span in spans_in_current_trace:
            if span.is_recording():
                if span.name.startswith("invocation"):
                    span.set_attribute("gen_ai.operation.name", "chain")
                    _set_agent_input_attribute(span, invocation_context)
                    _set_agent_output_attribute(span, llm_response)
                elif span.name.startswith("agent_run"):
                    span.set_attribute("gen_ai.operation.name", "agent")
                    _set_agent_input_attribute(span, invocation_context)
                    _set_agent_output_attribute(span, llm_response)
                for attr_name, attr_extractor in common_attributes.items():
                    value = attr_extractor(**kwargs)
                    span.set_attribute(attr_name, value)
    except Exception as e:
        logger.error(f"Failed to set common attributes for spans: {e}")


def set_common_attributes_on_tool_span(current_span: _Span) -> None:
    # find parent span (generally a llm span)
    if not current_span.context:
        logger.warning(
            f"Get tool span's context failed. Skip setting common attributes for span {current_span.name}"
        )
        return

    if not current_span.parent:
        logger.warning(
            f"Get tool span's parent failed. Skip setting common attributes for span {current_span.name}"
        )
        return

    parent_span_id = current_span.parent.span_id
    for span in _INMEMORY_EXPORTER_INSTANCE.processor.spans:  # type: ignore
        if span.context.span_id == parent_span_id:
            common_attributes = ATTRIBUTES.get("common", {})
            for attr_name in common_attributes.keys():
                current_span.set_attribute(attr_name, span.attributes[attr_name])


def trace_send_data(): ...


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
    span = trace.get_current_span()

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

    upload_metrics(invocation_context, llm_request, llm_response)
