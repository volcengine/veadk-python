"""Execution-local views for native ADK AgentTool children.

The tool, original agents and their sessions remain independently owned.
Only the view used for this call inherits the root's model binding.
"""

from __future__ import annotations

import copy
from contextlib import aclosing
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool

from veadk.routing.context import get_turn_context
from veadk.routing.execution import (
    bind_request,
    prepare_flow,
    run_routed,
    routing_owner,
)


class RoutedLlmAgent(LlmAgent):
    @property
    def canonical_model(self):
        turn = get_turn_context()
        return turn.model if turn else super().canonical_model

    @property
    def canonical_before_model_callbacks(self):
        callbacks = super().canonical_before_model_callbacks
        return [*callbacks, bind_request] if get_turn_context() else callbacks

    @property
    def _llm_flow(self):
        return prepare_flow(super()._llm_flow)

    async def _run_async_impl(self, ctx):
        execute = super()._run_async_impl
        stream = (
            run_routed(self, ctx, execute)
            if get_turn_context() or routing_owner(self)
            else execute(ctx)
        )
        async with aclosing(stream) as events:
            async for event in events:
                yield event


def _view(agent: Any) -> Any:
    from veadk.agent import Agent

    if isinstance(agent, Agent):
        result = agent.clone(update={"sub_agents": []})
    elif isinstance(agent, LlmAgent):
        if type(agent) is not LlmAgent:
            raise ValueError(
                "custom ADK agents must implement turn-scoped model binding"
            )
        values = {name: getattr(agent, name) for name in type(agent).model_fields}
        result = RoutedLlmAgent.model_construct(**values)
        result.__pydantic_private__ = copy.copy(agent.__pydantic_private__)
    else:
        result = agent.clone(update={"sub_agents": []})
    result.sub_agents = [_view(child) for child in agent.sub_agents]
    for child in result.sub_agents:
        child.parent_agent = result
    return result


def inherit_tool(tool: Any) -> Any:
    if not isinstance(tool, AgentTool) or get_turn_context() is None:
        return tool
    result = copy.copy(tool)
    result.agent = _view(tool.agent)
    return result


def bind_sub_agents(agent: Any) -> None:
    """Own adapted copies so direct transfers also retain the root router."""
    agent.sub_agents = [_view(child) for child in agent.sub_agents]
    for child in agent.sub_agents:
        child.parent_agent = agent
