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

from typing import Any, Literal

from attr import dataclass
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool
from opentelemetry.sdk.trace import _Span
from opentelemetry.trace.span import Span


@dataclass
class ExtractorResponse:
    """Response container for telemetry attribute extractors.

    ExtractorResponse encapsulates the output from attribute extraction functions
    and provides metadata about how the extracted data should be applied to
    OpenTelemetry spans. It supports different response types for flexible
    span annotation patterns.

    The response system enables extractors to return various data formats
    including simple attributes, structured events, and event collections,
    allowing for rich telemetry data capture and organization.

    Attributes:
        content: The extracted data to be applied to the span. Can be any type
            depending on the response type and extractor implementation.
        type: Specification of how the content should be applied to spans.
            Controls the span annotation method used.

    Response Types:
        - "attribute": Sets span attributes using set_attribute()
        - "event": Adds span events using add_event()
        - "event_list": Adds multiple events from a structured list
    """

    content: Any

    type: Literal["attribute", "event", "event_list"] = "attribute"
    """Type of extractor response.
    
    `attribute`: span.add_attribute(attr_name, attr_value)
    `event`: span.add_event(...)
    `event_list`: span.add_event(...) for each event in the list
    """

    @staticmethod
    def update_span(
        span: _Span | Span, attr_name: str, response: "ExtractorResponse"
    ) -> None:
        """Apply extractor response content to an OpenTelemetry span.

        This method interprets the ExtractorResponse and applies its content
        to the given span using the appropriate OpenTelemetry API method
        based on the response type.

        Processing Logic:
        - attribute: Sets span attributes, supporting both single values and lists
        - event: Adds span events, handling both single events and event lists
        - event_list: Processes structured event lists with key-value pairs

        Args:
            span: OpenTelemetry span to annotate with extracted data
            attr_name: Attribute name or event name for span annotation
            response: ExtractorResponse containing the data and type information

        Note:
            - Gracefully handles unsupported response types by discarding them
            - Type checking ensures safe attribute and event operations
            - List processing supports nested dictionary structures
        """
        if response.type == "attribute":
            res = response.content
            if isinstance(res, list):
                for _res in res:
                    if isinstance(_res, dict):
                        for k, v in _res.items():
                            span.set_attribute(k, v)
            else:
                # set anyway
                span.set_attribute(attr_name, res)  # type: ignore
        elif response.type == "event":
            if isinstance(response.content, dict):
                span.add_event(attr_name, response.content)
            elif isinstance(response.content, list):
                for event in response.content:
                    span.add_event(attr_name, event)  # type: ignore
        elif response.type == "event_list":
            if isinstance(response.content, list):
                for event in response.content:
                    if isinstance(event, dict):
                        # we ensure this dict only have one key-value pair
                        key, value = next(iter(event.items()))
                        span.add_event(key, value)
                    else:
                        # Unsupported response type, discard it.
                        pass
        else:
            # Unsupported response type, discard it.
            pass


@dataclass
class LLMAttributesParams:
    """Parameter container for LLM attribute extractors.

    LLMAttributesParams packages all the contextual information needed by
    LLM attribute extraction functions. It provides access to the complete
    LLM call context including request parameters, response data, and
    execution environment details.

    Attributes:
        invocation_context: Complete context of the agent invocation including
            agent instance, session information, user details, and execution state
        event_id: Unique identifier for this specific LLM call event within
            the broader agent execution trace
        llm_request: Request object containing model name, parameters, prompt
            content, and configuration settings sent to the language model
        llm_response: Response object containing generated content, usage metadata,
            token counts, timing information, and any error details
    """

    invocation_context: InvocationContext
    event_id: str
    llm_request: LlmRequest
    llm_response: LlmResponse


@dataclass
class ToolAttributesParams:
    """Parameter container for tool attribute extractors.

    ToolAttributesParams packages all the contextual information needed by
    tool attribute extraction functions. It provides access to tool execution
    details including tool metadata, input arguments, and execution results
    for comprehensive tool usage telemetry.

    Attributes:
        tool: Tool instance that was executed, containing metadata such as
            name, description, function signature, and custom metadata
        args: Dictionary of arguments that were passed to the tool function
            during execution, including parameter names and values
        function_response_event: Event object containing the tool's execution
            results, return values, timing information, and any error details
    """

    tool: BaseTool
    args: dict[str, Any]
    function_response_event: Event
