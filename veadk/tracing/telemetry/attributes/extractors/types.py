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
    content: list | dict | None | str | int | float

    type: Literal["attribute", "event"] = "attribute"
    """Type of extractor response.
    
    `attribute`: span.add_attribute(attr_name, attr_value)
    `event`: span.add_event(...)
    """

    @staticmethod
    def update_span(
        span: _Span | Span, attr_name: str, response: "ExtractorResponse"
    ) -> None:
        if response.type == "attribute":
            res = response.content
            if isinstance(res, list):  # list[dict]
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
                    span.add_event(attr_name, event)
        else:
            # Unsupported response type, discard it.
            pass


@dataclass
class LLMAttributesParams:
    invocation_context: InvocationContext
    event_id: str
    llm_request: LlmRequest
    llm_response: LlmResponse


@dataclass
class ToolAttributesParams:
    tool: BaseTool
    args: dict[str, Any]
    function_response_event: Event
