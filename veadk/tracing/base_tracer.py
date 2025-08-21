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

from abc import ABC, abstractmethod
from typing import Optional

from google.adk.agents.invocation_context import InvocationContext
from google.adk.plugins.base_plugin import BasePlugin
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
            current_session = invocation_context.session

            span.set_attribute("app.name", current_session.app_name)
            span.set_attribute("user.id", current_session.user_id)
            span.set_attribute("session.id", current_session.id)

            span.set_attribute("agent.name", agent_name)
            span.set_attribute("invoke.branch", invoke_branch)
            span.set_attribute("gen_ai.system", "veadk")

            logger.debug(
                f"Add attributes to {span_name}: app_name={current_session.app_name}, user_id={current_session.user_id}, session_id={current_session.id}, agent_name={agent_name}, invoke_branch={invoke_branch}"
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
        self.name = name
        self._trace_id = "<unknown_trace_id>"
        self._trace_file_path = "<unknown_trace_file_path>"

    @abstractmethod
    def dump(self, user_id: str, session_id: str, path: str = "/tmp") -> str: ...
