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


def trace_send_data(): ...


def set_common_attributes(
    invocation_context: InvocationContext, current_span: _Span, **kwargs
) -> None:
    from veadk.agent import Agent

    if current_span.context:
        current_span_id = current_span.context.trace_id
    else:
        logger.warning(
            "Current span context is missing, failed to get `trace_id` to set common attributes."
        )
        return

    if isinstance(invocation_context.agent, Agent):
        try:
            spans = _INMEMORY_EXPORTER_INSTANCE.processor.spans  #  # type: ignore

            spans_in_current_trace = [
                span
                for span in spans
                if span.context and span.context.trace_id == current_span_id
            ]

            common_attributes = ATTRIBUTES.get("common", {})
            for span in spans_in_current_trace:
                if span.name.startswith("invocation"):
                    span.set_attribute("gen_ai.operation.name", "chain")
                elif span.name.startswith("agent_run"):
                    span.set_attribute("gen_ai.operation.name", "agent")
                for attr_name, attr_extractor in common_attributes.items():
                    value = attr_extractor(**kwargs)
                    span.set_attribute(attr_name, value)
        except Exception as e:
            logger.error(f"Failed to set common attributes for spans: {e}")
    else:
        logger.warning(
            "Failed to set common attributes for spans as your agent is not VeADK Agent. Skip this."
        )


def trace_tool_call(
    tool: BaseTool,
    args: dict[str, Any],
    function_response_event: Event,
) -> None:
    span = trace.get_current_span()

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

    set_common_attributes(
        invocation_context=invocation_context,
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
