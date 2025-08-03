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

import json
from abc import ABC, abstractmethod
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from opentelemetry import trace

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class BaseTracer(ABC):
    def __init__(self, name: str):
        pass

    @abstractmethod
    def dump(self) -> str: ...

    def llm_metrics_hook(
        self, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> Optional[LlmResponse]:
        trace.get_tracer("gcp.vertex.agent")
        span = trace.get_current_span()
        # logger.debug(f"llm_request: {llm_request}")

        req = llm_request.model_dump()

        model_name = req.get("model", "unknown")
        max_tokens = (
            None
            if not req.get("live_connect_config")
            else req["live_connect_config"].get("max_output_tokens", None)
        )
        temperature = (
            None
            if not req.get("live_connect_config")
            else req["live_connect_config"].get("temperature", None)
        )
        top_p = (
            None
            if not req.get("live_connect_config")
            else req["live_connect_config"].get("top_p", None)
        )

        attributes = {}
        attributes["gen_ai.system"] = "veadk"
        if model_name:
            attributes["gen_ai.request.model"] = model_name
            attributes["gen_ai.response.model"] = (
                model_name  # The req model and the resp model should be consistent.
            )
        attributes["gen_ai.request.type"] = "completion"
        if max_tokens:
            attributes["gen_ai.request.max_tokens"] = max_tokens
        if temperature:
            attributes["gen_ai.request.temperature"] = temperature
        if top_p:
            attributes["gen_ai.request.top_p"] = top_p

        # Print attributes for debugging
        # print("Tracing attributes:", attributes)

        # Set all attributes at once if possible, else fallback to individual
        if hasattr(span, "set_attributes"):
            span.set_attributes(attributes)
        else:
            # Fallback for OpenTelemetry versions without set_attributes
            for k, v in attributes.items():
                span.set_attribute(k, v)

    def token_metrics_hook(
        self, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> Optional[LlmResponse]:
        trace.get_tracer("gcp.vertex.agent")
        span = trace.get_current_span()
        # logger.debug(f"llm_response: {llm_response}")
        # logger.debug(f"callback_context: {callback_context}")

        # Refined: collect all attributes, use set_attributes, print for debugging
        attributes = {}

        # prompt
        user_content = callback_context.user_content
        if getattr(user_content, "role", None):
            role = getattr(user_content, "role", None)
        else:
            role = None
        if getattr(user_content, "parts", None):
            content = callback_context.user_content.model_dump(exclude_none=True).get(
                "parts", None
            )
            if content:
                content = json.dumps(content)
            else:
                content = None
        else:
            content = None
        if role and content:
            attributes["gen_ai.prompt.0.role"] = role
            attributes["gen_ai.prompt.0.content"] = content

        # completion
        completion_content = getattr(llm_response, "content").model_dump(
            exclude_none=True
        )
        if completion_content:
            content = json.dumps(
                getattr(llm_response, "content").model_dump(exclude_none=True)["parts"]
            )
            role = getattr(llm_response, "content").model_dump(exclude_none=True)[
                "role"
            ]
            if role and content:
                attributes["gen_ai.completion.0.role"] = role
                attributes["gen_ai.completion.0.content"] = content

        if not llm_response.usage_metadata:
            return

        # tokens
        metadata = llm_response.usage_metadata.model_dump()
        if metadata:
            prompt_tokens = metadata.get("prompt_token_count", None)
            completion_tokens = metadata.get("candidates_token_count", None)
            total_tokens = metadata.get("total_token_count", None)
            cache_read_input_tokens = (
                metadata.get("cache_read_input_tokens") or 0
            )  # Might change, once openai introduces their equivalent.
            cache_create_input_tokens = (
                metadata.get("cache_create_input_tokens") or 0
            )  # Might change, once openai introduces their equivalent.
            if prompt_tokens:
                attributes["gen_ai.usage.prompt_tokens"] = prompt_tokens
            if completion_tokens:
                attributes["gen_ai.usage.completion_tokens"] = completion_tokens
            if total_tokens:
                attributes["gen_ai.usage.total_tokens"] = total_tokens
            if cache_read_input_tokens is not None:
                attributes["gen_ai.usage.cache_read_input_tokens"] = (
                    cache_read_input_tokens
                )
            if cache_create_input_tokens is not None:
                attributes["gen_ai.usage.cache_create_input_tokens"] = (
                    cache_create_input_tokens
                )

        # Print attributes for debugging
        # print("Tracing attributes:", attributes)

        # Set all attributes at once if possible, else fallback to individual
        if hasattr(span, "set_attributes"):
            span.set_attributes(attributes)
        else:
            # Fallback for OpenTelemetry versions without set_attributes
            for k, v in attributes.items():
                span.set_attribute(k, v)
