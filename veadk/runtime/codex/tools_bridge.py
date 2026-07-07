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

"""Bridge an agent's ADK tools to Codex's Responses shim.

Codex presents MCP/function tools to the model as a ``type:"namespace"`` object
that a chat backend (Ark) rejects, and it will not route a plain ``function_call``
back to a namespaced tool. So instead of configuring the tools on the Codex side,
the shim advertises them to the backend as plain ``function`` tools and executes
them itself (see :mod:`veadk.runtime.codex.proxy`), invisibly to Codex.

This module produces, for an agent's tools, the two things the shim needs:

- ``specs``: flat Responses ``function`` tool specs to advertise to the backend.
- ``executors``: ``{name: async (args) -> str}`` to run a tool when the model
  calls it.

Both are derived from ADK itself — tool declarations via ``BaseTool._get_declaration``
(+ ADK's own ``_function_declaration_to_tool_param`` schema conversion) and
execution via ``BaseTool.run_async`` — so MCP tools, function tools and any other
``BaseTool`` are handled uniformly without reimplementing schema or dispatch.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.base_toolset import BaseToolset

    from veadk.agent import Agent

logger = get_logger(__name__)

Executor = Callable[[dict[str, Any]], Awaitable[str]]


async def build_executable_tools(
    agent: "Agent", ctx: "InvocationContext"
) -> tuple[list[dict[str, Any]], dict[str, Executor], list["BaseToolset"]]:
    """Collect the agent's ADK tools as shim-executable functions.

    Returns ``(specs, executors, opened_toolsets)`` where ``opened_toolsets`` are
    the toolsets whose sessions were opened by ``get_tools`` (e.g. MCP); the
    caller must ``close()`` them when the turn ends.
    """
    from google.adk.models.lite_llm import _function_declaration_to_tool_param
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.base_toolset import BaseToolset
    from google.adk.tools.tool_context import ToolContext

    specs: list[dict[str, Any]] = []
    executors: dict[str, Executor] = {}
    opened: list[BaseToolset] = []

    def _add(tool: "BaseTool") -> None:
        try:
            declaration = tool._get_declaration()
        except Exception as e:  # noqa: BLE001 - one tool must not break the turn
            logger.warning(f"codex: skipping tool with no declaration: {e}")
            return
        if declaration is None or not declaration.name:
            return
        name = declaration.name
        # ADK builds the OpenAI (chat) tool param, incl. genai->JSON schema
        # normalization; lift its `function` body up to the Responses flat shape.
        chat_param = _function_declaration_to_tool_param(declaration)
        specs.append({"type": "function", **chat_param["function"]})
        executors[name] = _make_executor(tool, ctx, ToolContext)

    for entry in getattr(agent, "tools", None) or []:
        # Skill toolsets are handled by the skill materialization path
        # (veadk.runtime.codex.skills → $CODEX_HOME/skills), driven by Codex's
        # own skill system. Skip them here so their internal tools
        # (list_skills / load_skill / ...) aren't also exposed via the shim.
        if type(entry).__name__ in ("SkillToolset", "SkillsToolset"):
            continue
        if isinstance(entry, BaseToolset):
            try:
                tools = await entry.get_tools()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"codex: failed to list toolset {entry!r}: {e}")
                continue
            opened.append(entry)
            for tool in tools:
                _add(tool)
        elif isinstance(entry, BaseTool):
            _add(entry)

    if executors:
        logger.info(
            f"codex: bridging {len(executors)} agent tool(s): {list(executors)}"
        )
    return specs, executors, opened


def _make_executor(
    tool: "BaseTool", ctx: "InvocationContext", tool_context_cls: Any
) -> Executor:
    async def _run(args: dict[str, Any]) -> str:
        try:
            result = await tool.run_async(args=args, tool_context=tool_context_cls(ctx))
        except Exception as e:  # noqa: BLE001 - surfaced to the model, not raised
            return json.dumps({"error": str(e)})
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            return str(result)

    return _run


async def close_toolsets(toolsets: list["BaseToolset"]) -> None:
    """Best-effort close of toolset sessions opened during the turn."""
    for toolset in toolsets:
        close = getattr(toolset, "close", None)
        if close is None:
            continue
        try:
            await close()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"codex: failed to close toolset {toolset!r}: {e}")
