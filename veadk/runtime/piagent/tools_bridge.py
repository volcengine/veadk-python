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

"""Bridge VeADK/ADK tools into Pi custom tool definitions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.tools.base_toolset import BaseToolset

    from veadk.agent import Agent

logger = get_logger(__name__)

Executor = Callable[[dict[str, Any]], Awaitable[Any]]

_TOOL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_MAX_TOOL_RESULT_CHARS = 20000
_PI_RESERVED_TOOL_NAMES = {"read", "bash", "edit", "write", "grep", "find", "ls"}


@dataclass(frozen=True)
class PiToolSpec:
    """Pi custom tool metadata generated from an ADK tool declaration."""

    name: str
    label: str
    description: str
    parameters: dict[str, Any]
    original_name: str


@dataclass(frozen=True)
class SkippedTool:
    """Tool skipped while collecting Pi-executable tools."""

    name: str
    reason: str


@dataclass
class PiToolBundle:
    """Pi tool specs plus Python executors for one ADK invocation."""

    specs: list[PiToolSpec] = field(default_factory=list)
    executors: dict[str, Executor] = field(default_factory=dict)
    skipped: list[SkippedTool] = field(default_factory=list)
    opened_toolsets: list["BaseToolset"] = field(default_factory=list)

    @property
    def has_tools(self) -> bool:
        return bool(self.specs and self.executors)


async def build_executable_tools(
    agent: "Agent", ctx: "InvocationContext"
) -> PiToolBundle:
    """Collect ADK tools and toolsets as Pi custom tools.

    Ordinary ``BaseTool`` entries are bridged directly. ``BaseToolset`` entries,
    including MCP toolsets, are expanded with ``get_tools()`` and each returned
    ``BaseTool`` is bridged through the same Pi custom tool path. Skill toolsets
    are still skipped because skills need a separate materialization strategy.
    """
    from google.adk.models.lite_llm import _function_declaration_to_tool_param
    from google.adk.agents.readonly_context import ReadonlyContext
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.base_toolset import BaseToolset
    from google.adk.tools.function_tool import FunctionTool
    from google.adk.tools.tool_context import ToolContext

    bundle = PiToolBundle()
    seen: set[str] = set()
    readonly_context = ReadonlyContext(ctx)

    def _skip(name: str, reason: str) -> None:
        logger.warning(f"piagent: skipping tool {name!r}: {reason}")
        bundle.skipped.append(SkippedTool(name=name, reason=reason))

    def _add(tool: "BaseTool") -> None:
        try:
            declaration = tool._get_declaration()
        except Exception as e:  # noqa: BLE001 - one tool must not break the turn
            _skip(repr(tool), f"failed to build declaration: {e}")
            return
        if declaration is None or not declaration.name:
            return

        original_name = str(declaration.name)
        name = _pi_tool_name(original_name, seen)
        if name != original_name:
            logger.info(f"piagent: exposing tool {original_name!r} to Pi as {name!r}")

        chat_param = _function_declaration_to_tool_param(declaration)
        function = chat_param.get("function") or {}
        parameters = function.get("parameters") or {"type": "object", "properties": {}}
        if not isinstance(parameters, dict):
            parameters = {"type": "object", "properties": {}}

        spec = PiToolSpec(
            name=name,
            label=original_name,
            description=str(function.get("description") or ""),
            parameters=parameters,
            original_name=original_name,
        )
        bundle.specs.append(spec)
        bundle.executors[name] = _make_executor(tool, ctx, ToolContext)
        seen.add(name)

    try:
        for entry in getattr(agent, "tools", None) or []:
            if type(entry).__name__ in ("SkillToolset", "SkillsToolset"):
                _skip(
                    type(entry).__name__,
                    "skills are not supported by piagent tools yet",
                )
                continue
            if isinstance(entry, BaseToolset):
                try:
                    tools = await entry.get_tools(readonly_context=readonly_context)
                except Exception as e:  # noqa: BLE001
                    await close_toolsets([entry])
                    _skip(
                        type(entry).__name__,
                        f"failed to list toolset tools: {e}",
                    )
                    continue
                bundle.opened_toolsets.append(entry)
                for tool in tools:
                    _add(tool)
                continue
            if isinstance(entry, BaseTool):
                _add(entry)
                continue
            if callable(entry):
                _add(FunctionTool(entry))
                continue
            _skip(type(entry).__name__, "tool type is not supported by piagent")
    except Exception:
        await close_toolsets(bundle.opened_toolsets)
        bundle.opened_toolsets.clear()
        raise

    if bundle.executors:
        logger.info(
            f"piagent: bridging {len(bundle.executors)} agent tool(s): "
            f"{list(bundle.executors)}"
        )
    return bundle


def _make_executor(
    tool: Any, ctx: "InvocationContext", tool_context_cls: Any
) -> Executor:
    async def _run(args: dict[str, Any]) -> Any:
        try:
            result = await tool.run_async(args=args, tool_context=tool_context_cls(ctx))
        except Exception as e:  # noqa: BLE001 - surface tool failure to Pi
            return {"error": str(e), "isError": True}
        return _coerce_tool_result(result)

    return _run


def _coerce_tool_result(result: Any) -> Any:
    if isinstance(result, str):
        return _truncate(result)
    try:
        if hasattr(result, "model_dump"):
            result = result.model_dump()
    except Exception:  # noqa: BLE001
        return _truncate(str(result))
    return result


def _truncate(text: str) -> str:
    if len(text) <= _MAX_TOOL_RESULT_CHARS:
        return text
    return text[:_MAX_TOOL_RESULT_CHARS] + "\n...[truncated]"


def _pi_tool_name(original_name: str, seen: set[str]) -> str:
    """Return a stable Pi-compatible tool name, deduped within one turn."""

    base = _sanitize_tool_name(original_name)
    if not base:
        base = f"tool_{_short_hash(original_name)}"
    if base in _PI_RESERVED_TOOL_NAMES:
        base = f"veadk_{base}"
    if len(base) > 64:
        base = f"{base[:55]}_{_short_hash(original_name)}"

    candidate = base
    suffix = 2
    while candidate in seen:
        suffix_text = f"_{suffix}"
        max_base = 64 - len(suffix_text)
        candidate = f"{base[:max_base]}{suffix_text}"
        suffix += 1
    return candidate


def _sanitize_tool_name(name: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_")
    candidate = re.sub(r"_+", "_", candidate)
    if not candidate:
        return ""
    if not (candidate[0].isalpha() or candidate[0] == "_"):
        candidate = f"tool_{candidate}"
    if _TOOL_NAME_RE.fullmatch(candidate):
        return candidate
    return candidate[:64]


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


async def close_toolsets(toolsets: list["BaseToolset"]) -> None:
    """Best-effort close of toolsets opened during Pi tool collection."""
    for toolset in toolsets:
        close = getattr(toolset, "close", None)
        if close is None:
            continue
        try:
            await close()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"piagent: failed to close toolset {toolset!r}: {e}")
