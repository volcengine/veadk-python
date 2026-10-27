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


"""Agent-native binding scopes using ordinary ADK McpToolset connections."""

from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from veadk.sandbox.manager import SandboxError, SandboxManager, SessionKey


@dataclass
class _Binding:
    key: SessionKey
    invocation_id: str
    agent_name: str
    toolset: McpToolset = field(repr=False)
    active: bool = True


_current: ContextVar[_Binding | None] = ContextVar(
    "veadk_sandbox_binding", default=None
)


def validate_sandbox_agent(agent):
    """Also called at execution time: Agent.clone bypasses model_post_init."""
    if not isinstance(agent.sandbox, SandboxManager):
        raise TypeError("Agent.sandbox must be a SandboxManager instance")
    if (
        agent.runtime != "adk"
        or agent.tools
        or agent.sub_agents
        or agent.parent_agent is not None
        or agent.code_executor is not None
    ):
        raise ValueError(
            "Agent(sandbox=...) requires a standalone ADK agent with empty tools, "
            "no sub_agents, no parent_agent and no code_executor"
        )


@asynccontextmanager
async def sandbox_scope(agent, ctx):
    """Own MCP inside the Agent's model/tool loop, independent of its Runner."""
    session = ctx.session
    key = SessionKey(session.app_name, session.user_id, session.id)
    async with agent.sandbox.acquire(key) as lease:
        toolset = McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=lease.mcp_url, timeout=30, sse_read_timeout=180
            )
        )
        binding = _Binding(key, ctx.invocation_id, agent.name, toolset)
        token = _current.set(binding)
        try:
            yield
        finally:
            binding.active = False
            try:
                await toolset.close()
            finally:
                _current.reset(token)


async def bind_tools(callback_context, llm_request):
    """Prepend to canonical callbacks without modifying user callback fields."""
    session = callback_context.session
    key = SessionKey(session.app_name, session.user_id, session.id)
    binding = _current.get()
    if (
        binding is None
        or not binding.active
        or binding.key != key
        or binding.invocation_id != callback_context.invocation_id
        or binding.agent_name != callback_context.agent_name
    ):
        raise SandboxError("No sandbox connection bound to this Agent invocation")
    if llm_request.tools_dict or llm_request.config.tools:
        raise SandboxError("Sandbox execution requires no other model tools")
    tools = await binding.toolset.get_tools(callback_context)
    # Register both declarations and execution objects in this request only.
    llm_request.append_tools(tools)
