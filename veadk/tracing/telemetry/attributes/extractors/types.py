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
    invocation_context: InvocationContext
    event_id: str
    llm_request: LlmRequest
    llm_response: LlmResponse


@dataclass
class ToolAttributesParams:
    tool: BaseTool
    args: dict[str, Any]
    function_response_event: Event
