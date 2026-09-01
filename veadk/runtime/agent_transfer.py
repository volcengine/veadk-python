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

"""ADK-compatible transfer support for non-ADK runtimes."""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator, Sequence

from google.adk.tools.transfer_to_agent_tool import TransferToAgentTool
from google.adk.tools.transfer_to_agent_tool import transfer_to_agent
from google.adk.utils.context_utils import Aclosing

from veadk.runtime.output_state import maybe_save_output_to_state

if TYPE_CHECKING:
    from google.adk.agents.base_agent import BaseAgent
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events.event import Event
    from google.adk.models.llm_request import LlmRequest
    from google.adk.tools.base_tool import BaseTool


TRANSFER_TOOL_NAME = transfer_to_agent.__name__


def get_transfer_targets(agent: "BaseAgent") -> list["BaseAgent"]:
    """Return the agents ADK AutoFlow would expose as transfer targets."""

    try:
        from google.adk.agents.llm_agent import LlmAgent
    except ImportError:
        return []

    if not isinstance(agent, LlmAgent):
        return []

    targets: list[BaseAgent] = [
        sub_agent
        for sub_agent in getattr(agent, "sub_agents", None) or []
        if not _is_non_transferable_mode(sub_agent)
    ]
    parent = getattr(agent, "parent_agent", None)
    if parent is None or not hasattr(parent, "disallow_transfer_to_parent"):
        return targets

    if not getattr(agent, "disallow_transfer_to_parent", False):
        targets.append(parent)

    if not getattr(agent, "disallow_transfer_to_peers", False):
        targets.extend(
            peer
            for peer in getattr(parent, "sub_agents", None) or []
            if getattr(peer, "name", None) != getattr(agent, "name", None)
            and not _is_non_transferable_mode(peer)
        )

    return targets


def has_transfer_targets(agent: "BaseAgent") -> bool:
    """Whether transfer should be exposed for this agent."""

    return bool(get_transfer_targets(agent))


def build_transfer_tool(targets: Sequence["BaseAgent"] | None = None) -> "BaseTool":
    """Build the standard ADK transfer tool."""

    return TransferToAgentTool(agent_names=[agent.name for agent in targets or []])


def append_transfer_instructions(
    agent: "BaseAgent",
    llm_request: "LlmRequest",
    targets: list["BaseAgent"] | None = None,
) -> None:
    """Append ADK-compatible transfer target instructions to an LLM request."""

    targets = list(targets) if targets is not None else get_transfer_targets(agent)
    if not targets:
        return

    instructions = _build_target_agents_instructions(agent, targets)
    if instructions:
        llm_request.append_instructions([instructions])


def transfer_agent_name(event: "Event") -> str:
    """Return the transfer target requested by an event, if any."""

    return str(getattr(getattr(event, "actions", None), "transfer_to_agent", "") or "")


async def run_transferred_agent(
    ctx: "InvocationContext",
    event: "Event",
) -> AsyncGenerator["Event", None]:
    """Run the target agent requested by ``event.actions.transfer_to_agent``."""

    agent_name = transfer_agent_name(event)
    if not agent_name:
        return

    root_agent = getattr(getattr(ctx, "agent", None), "root_agent", None)
    if root_agent is None:
        root_agent = getattr(ctx, "agent", None)
    find_agent = getattr(root_agent, "find_agent", None)
    target_agent = find_agent(agent_name) if callable(find_agent) else None
    if target_agent is None:
        raise ValueError(f"Agent {agent_name} not found in the agent tree.")

    async with Aclosing(target_agent.run_async(ctx)) as agen:
        async for target_event in agen:
            maybe_save_output_to_state(target_agent, target_event)
            yield target_event


def _build_target_agents_info(target_agent: "BaseAgent") -> str:
    return f"""
Agent name: {target_agent.name}
Agent description: {target_agent.description}
"""


def _build_target_agents_instructions(
    agent: "BaseAgent",
    target_agents: list["BaseAgent"],
) -> str:
    if getattr(agent, "mode", None) in ("single_turn", "task"):
        return ""

    available_agent_names = sorted(target_agent.name for target_agent in target_agents)
    formatted_agent_names = ", ".join(f"`{name}`" for name in available_agent_names)
    target_agents_info = "\n".join(
        _build_target_agents_info(target_agent) for target_agent in target_agents
    )

    instructions = f"""
You have a list of other agents to transfer to:

{target_agents_info}

If you are the best to answer the question according to your description, you
can answer it.

If another agent is better for answering the question according to its
description, call `{TRANSFER_TOOL_NAME}` function to transfer the question to
that agent. When transferring, do not generate any text other than the function
call.

**NOTE**: the only available agents for `{TRANSFER_TOOL_NAME}` function are {formatted_agent_names}.
"""

    if getattr(agent, "parent_agent", None) and not getattr(
        agent, "disallow_transfer_to_parent", False
    ):
        instructions += f"""
If neither you nor the other agents are best for the question, transfer to your parent agent {agent.parent_agent.name}.
"""
    return instructions


def _is_non_transferable_mode(agent: "BaseAgent") -> bool:
    return getattr(agent, "mode", None) in ("single_turn", "task")
