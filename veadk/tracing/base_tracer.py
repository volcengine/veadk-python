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
from typing import Any, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from opentelemetry import trace

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class UserMessagePlugin(BasePlugin):
    def __init__(self, name: str):
        super().__init__(name)

    async def on_user_message_callback(
        self,
        *,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> Optional[types.Content]:
        """Callback executed when a user message is received before an invocation starts.

        This callback helps logging and modifying the user message before the
        runner starts the invocation.

        Args:
        invocation_context: The context for the entire invocation.
        user_message: The message content input by user.

        Returns:
        An optional `types.Content` to be returned to the ADK. Returning a
        value to replace the user message. Returning `None` to proceed
        normally.
        """
        trace.get_tracer("gcp.vertex.agent")
        span = trace.get_current_span()

        logger.debug(f"User message plugin works, catch {span}")
        span_name = getattr(span, "name", None)
        if span_name and span_name.startswith("invocation"):
            agent_name = invocation_context.agent.name
            invoke_branch = (
                invocation_context.branch if invocation_context.branch else agent_name
            )
            span.set_attribute("agent_name", agent_name)
            span.set_attribute("invoke_branch", invoke_branch)

            logger.debug(
                f"Add attributes to {span_name}: agent_name={agent_name}, invoke_branch={invoke_branch}"
            )

        return None


def replace_bytes_with_empty(data):
    """
    Recursively traverse the data structure and replace all bytes types with empty strings.
    Supports handling any nested structure of lists and dictionaries.
    """
    if isinstance(data, dict):
        # Handle dictionary: Recursively process each value
        return {k: replace_bytes_with_empty(v) for k, v in data.items()}
    elif isinstance(data, list):
        # Handle list: Recursively process each element
        return [replace_bytes_with_empty(item) for item in data]
    elif isinstance(data, bytes):
        # When encountering the bytes type, replace it with an empty string
        return "<image data>"
    else:
        # Keep other types unchanged
        return data


class BaseTracer(ABC):
    def __init__(self, name: str):
        self.app_name = "veadk_app_name"
        pass

    @abstractmethod
    def dump(self, user_id: str, session_id: str, path: str = "/tmp") -> str: ...

    def tracer_hook_before_model(
        self, callback_context: CallbackContext, llm_request: LlmRequest
    ) -> Optional[LlmResponse]:
        """agent run stage"""
        trace.get_tracer("gcp.vertex.agent")
        span = trace.get_current_span()
        # logger.debug(f"llm_request: {llm_request}")

        req = llm_request.model_dump()

        app_name = getattr(self, "app_name", "veadk_app")
        agent_name = callback_context.agent_name
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
        attributes["agent.name"] = agent_name
        attributes["app.name"] = app_name
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

    def tracer_hook_after_model(
        self, callback_context: CallbackContext, llm_response: LlmResponse
    ) -> Optional[LlmResponse]:
        """call llm stage"""
        trace.get_tracer("gcp.vertex.agent")
        span = trace.get_current_span()
        # logger.debug(f"llm_response: {llm_response}")
        # logger.debug(f"callback_context: {callback_context}")

        # Refined: collect all attributes, use set_attributes, print for debugging
        attributes = {}

        app_name = getattr(self, "app_name", "veadk_app")
        agent_name = callback_context.agent_name
        attributes["agent.name"] = agent_name
        attributes["app.name"] = app_name

        # prompt
        user_content = callback_context.user_content
        role = None
        content = None
        if getattr(user_content, "role", None):
            role = getattr(user_content, "role", None)

        if user_content and getattr(user_content, "parts", None):
            # content = user_content.model_dump_json(exclude_none=True)
            content = user_content.model_dump(exclude_none=True).get("parts", None)
            if content:
                content = replace_bytes_with_empty(content)
            content = json.dumps(content, ensure_ascii=False) if content else None

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

    def tracer_hook_after_tool(
        self,
        tool: BaseTool,
        args: dict[str, Any],
        tool_context: ToolContext,
        tool_response: dict,
    ):
        trace.get_tracer("gcp.vertex.agent")
        span = trace.get_current_span()
        agent_name = tool_context.agent_name
        tool_name = tool.name
        app_name = getattr(self, "app_name", "veadk_app")
        attributes = {
            "agent.name": agent_name,
            "app.name": app_name,
            "tool.name": tool_name,
        }

        # Set all attributes at once if possible, else fallback to individual
        if hasattr(span, "set_attributes"):
            span.set_attributes(attributes)
        else:
            # Fallback for OpenTelemetry versions without set_attributes
            for k, v in attributes.items():
                span.set_attribute(k, v)

    def set_app_name(self, app_name):
        self.app_name = app_name

    def do_hooks(self, agent) -> None:
        if not getattr(agent, "before_model_callback", None):
            agent.before_model_callback = []
        if not getattr(agent, "after_model_callback", None):
            agent.after_model_callback = []
        if not getattr(agent, "after_tool_callback", None):
            agent.after_tool_callback = []

        if self.tracer_hook_before_model not in agent.before_model_callback:
            agent.before_model_callback.append(self.tracer_hook_before_model)
        if self.tracer_hook_after_model not in agent.after_model_callback:
            agent.after_model_callback.append(self.tracer_hook_after_model)
        if self.tracer_hook_after_tool not in agent.after_tool_callback:
            agent.after_tool_callback.append(self.tracer_hook_after_tool)
