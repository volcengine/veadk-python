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

"""Base class for pluggable agent runtimes.

A *runtime* replaces the inner reasoning + tool loop of an agent while VeADK's
``Runner`` keeps owning multi-tenancy, session, memory and tracing. The default
``adk`` runtime is Google ADK's own ``BaseLlmFlow``; alternative runtimes (e.g.
``cc`` backed by the Claude Code SDK) subclass :class:`BaseRuntime` and bridge an
external agent harness back into ADK's :class:`~google.adk.events.event.Event`
stream so the surrounding ``Runner`` is unaffected.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events.event import Event

    from veadk.agent import Agent


def build_system_append(agent: "Agent") -> str:
    """Build the text to append to a runtime's own system prompt.

    Combines the agent's identity and instruction (name, description,
    instruction) into one block. This is *appended* to the runtime's built-in
    system prompt, never replacing it. A non-string ``instruction`` (an
    ``InstructionProvider`` callable) is skipped, since it requires a context to
    resolve.

    Args:
        agent (veadk.agent.Agent): The agent being invoked.

    Returns:
        str: The append block, or an empty string if there is nothing to add.
    """
    parts: list[str] = []
    if agent.name:
        parts.append(f"Your name is {agent.name}.")
    if agent.description:
        parts.append(agent.description)
    if isinstance(agent.instruction, str) and agent.instruction.strip():
        parts.append(agent.instruction)
    return "\n\n".join(parts)


class BaseRuntime(ABC):
    """Abstract agent runtime.

    Implementations translate an incoming invocation into calls against an
    external agent harness and yield the results back as ADK ``Event`` objects.
    The contract mirrors ADK's ``BaseAgent._run_async_impl`` so that whatever a
    runtime yields can be persisted by the existing VeADK ``Runner`` without any
    special handling.

    Attributes:
        name (str): Stable identifier of the runtime, matching the value passed
            to ``Agent(runtime=...)`` (for example ``"cc"``).
    """

    name: str = "base"

    @abstractmethod
    def run_async(
        self, agent: "Agent", ctx: "InvocationContext"
    ) -> AsyncGenerator["Event", None]:
        """Run one invocation and stream ADK events.

        Args:
            agent (veadk.agent.Agent): The agent being invoked. Model, endpoint
                and instruction are read from it.
            ctx (google.adk.agents.invocation_context.InvocationContext): The
                invocation context, providing the new message
                (``ctx.user_content``) and session history (``ctx.session.events``).

        Yields:
            google.adk.events.event.Event: Events produced during the run.
        """
        raise NotImplementedError
