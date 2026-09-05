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

"""Pluggable routing for individual tool executions.

Agent runtimes replace an agent's complete reasoning loop. Runtime providers
operate at a narrower layer: they decide where each tool call executes while
the Google ADK agent loop remains unchanged.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from google.adk.plugins import BasePlugin

if TYPE_CHECKING:
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.tool_context import ToolContext


@dataclass(slots=True)
class ToolCall:
    """One ADK tool invocation routed through a :class:`RuntimeProvider`."""

    name: str
    arguments: dict[str, Any]
    tool: "BaseTool"
    context: "ToolContext"

    @property
    def id(self) -> str:
        """Return the ADK function-call identifier when available."""
        return str(getattr(self.context, "function_call_id", "") or "")

    @property
    def session_id(self) -> str:
        """Return the current VeADK session identifier when available."""
        invocation = getattr(self.context, "_invocation_context", None)
        session = getattr(invocation, "session", None)
        return str(getattr(session, "id", "") or "")


class RuntimeProvider(BasePlugin, ABC):
    """ADK plugin that routes every tool call through ``execute``.

    Returning a response from ``before_tool_callback`` prevents Google ADK
    from invoking the original tool a second time. Subclasses may therefore
    execute locally, dispatch remotely, or combine both strategies.
    """

    def __init__(self, *, name: str) -> None:
        super().__init__(name=name)

    @abstractmethod
    async def execute(self, tool_call: ToolCall) -> Any:
        """Execute one tool call and return its result."""
        raise NotImplementedError

    async def before_tool_callback(
        self,
        *,
        tool: "BaseTool",
        tool_args: dict[str, Any] | None = None,
        args: dict[str, Any] | None = None,
        tool_context: "ToolContext",
    ) -> dict[str, Any]:
        """Route the call before ADK invokes the tool implementation.

        ADK plugin callbacks pass tool arguments as ``tool_args``, while
        canonical agent callbacks pass the same value as ``args``. Runtime
        providers support both callback paths.
        """
        if tool_args is not None and args is not None and tool_args != args:
            raise ValueError("tool_args and args must match when both are provided")
        resolved_args = tool_args if tool_args is not None else (args or {})
        result = await self.execute(
            ToolCall(
                name=tool.name,
                arguments=resolved_args,
                tool=tool,
                context=tool_context,
            )
        )
        if isinstance(result, dict):
            return result
        return {"result": result}


class LocalRuntimeProvider(RuntimeProvider):
    """Execute tools through their original ADK implementation."""

    def __init__(self, *, name: str = "veadk_local_runtime_provider") -> None:
        super().__init__(name=name)

    async def execute(self, tool_call: ToolCall) -> Any:
        return await tool_call.tool.run_async(
            args=tool_call.arguments,
            tool_context=tool_call.context,
        )


DispatchCallable = Callable[[ToolCall], Any | Awaitable[Any]]


def _is_mcp_tool(tool: "BaseTool") -> bool:
    """Return whether a resolved ADK tool is backed by MCP."""
    tool_type = type(tool)
    module_name = tool_type.__module__.lower()
    type_name = tool_type.__name__.lower()
    return (
        ".mcp_tool" in module_name
        or "mcptool" in type_name
        or hasattr(tool, "_mcp_tool")
        or hasattr(tool, "_mcp_session_manager")
    )


class DispatchRuntimeProvider(RuntimeProvider):
    """Dispatch selected tools remotely and execute all others locally.

    Pass ``dispatchable_tools=None`` to dispatch every non-MCP tool. Resolved
    MCP tools always retain their original ADK implementation.
    """

    def __init__(
        self,
        dispatch_task: DispatchCallable,
        *,
        dispatchable_tools: Collection[str] | None = ("bash",),
        local_runtime: RuntimeProvider | None = None,
        name: str = "veadk_dispatch_runtime_provider",
    ) -> None:
        super().__init__(name=name)
        self.dispatch_task = dispatch_task
        self.dispatchable_tools = (
            None if dispatchable_tools is None else frozenset(dispatchable_tools)
        )
        self.local_runtime = local_runtime or LocalRuntimeProvider()

    async def execute(self, tool_call: ToolCall) -> Any:
        dispatch_all = self.dispatchable_tools is None
        should_dispatch = dispatch_all or tool_call.name in self.dispatchable_tools
        if should_dispatch and not _is_mcp_tool(tool_call.tool):
            result = self.dispatch_task(tool_call)
            if inspect.isawaitable(result):
                return await result
            return result
        return await self.local_runtime.execute(tool_call)


__all__ = [
    "DispatchCallable",
    "DispatchRuntimeProvider",
    "LocalRuntimeProvider",
    "RuntimeProvider",
    "ToolCall",
]
