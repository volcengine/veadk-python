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

import asyncio
import hashlib
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from google.adk.events.event import Event
from google.genai import types

from veadk.utils.adk_compat import get_event_function_responses
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.base_toolset import BaseToolset

    from veadk.agent import Agent

logger = get_logger(__name__)

EventSink = Callable[[Event], Awaitable[None]]
Executor = Callable[[dict[str, Any], str], Awaitable[Any]]

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
    tools: dict[str, Any] = field(default_factory=dict)
    skipped: list[SkippedTool] = field(default_factory=list)
    opened_toolsets: list[BaseToolset] = field(default_factory=list)

    @property
    def has_tools(self) -> bool:
        return bool(self.specs and self.executors)


async def build_executable_tools(
    agent: Agent,
    ctx: InvocationContext,
    *,
    event_sink: EventSink | None = None,
    timeout_seconds: float | None = None,
) -> PiToolBundle:
    """Collect ADK tools and toolsets as Pi custom tools.

    Ordinary ``BaseTool`` entries are bridged directly. ``BaseToolset`` entries,
    including MCP toolsets, are expanded with ``get_tools()`` and each returned
    ``BaseTool`` is bridged through the same Pi custom tool path. Skill toolsets
    are still skipped because skills need a separate materialization strategy.
    """
    from google.adk.agents.readonly_context import ReadonlyContext
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.base_toolset import BaseToolset
    from google.adk.tools.function_tool import FunctionTool

    bundle = PiToolBundle()
    seen: set[str] = set()
    readonly_context = ReadonlyContext(ctx)

    _ensure_invocation_context_defaults(ctx, agent)

    def _skip(name: str, reason: str) -> None:
        logger.warning(f"piagent: skipping tool {name!r}: {reason}")
        bundle.skipped.append(SkippedTool(name=name, reason=reason))

    def _add(tool: BaseTool) -> None:
        add_tool_to_bundle(
            bundle,
            tool,
            ctx,
            seen=seen,
            event_sink=event_sink,
            timeout_seconds=timeout_seconds,
            skip=_skip,
        )

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


def add_tool_to_bundle(
    bundle: PiToolBundle,
    tool: BaseTool,
    ctx: InvocationContext,
    *,
    seen: set[str],
    event_sink: EventSink | None = None,
    timeout_seconds: float | None = None,
    skip: Callable[[str, str], None] | None = None,
) -> None:
    """Add one ADK tool to an existing Pi tool bundle."""

    from google.adk.models.lite_llm import _function_declaration_to_tool_param

    def _skip(name: str, reason: str) -> None:
        if skip is not None:
            skip(name, reason)
        else:
            logger.warning(f"piagent: skipping tool {name!r}: {reason}")
            bundle.skipped.append(SkippedTool(name=name, reason=reason))

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
    bundle.tools[original_name] = tool
    bundle.executors[name] = _make_executor(
        tool,
        ctx,
        event_sink=event_sink,
        timeout_seconds=timeout_seconds,
    )
    seen.add(name)


def sync_bundle_to_tools_dict(
    bundle: PiToolBundle,
    tools_dict: dict[str, BaseTool],
    ctx: InvocationContext,
    *,
    event_sink: EventSink | None = None,
    timeout_seconds: float | None = None,
) -> None:
    """Rebuild Pi tool specs and executors from callback-mutated tools."""

    bundle.specs = []
    bundle.executors = {}
    bundle.tools = {}
    seen: set[str] = set()
    for tool in tools_dict.values():
        add_tool_to_bundle(
            bundle,
            tool,
            ctx,
            seen=seen,
            event_sink=event_sink,
            timeout_seconds=timeout_seconds,
        )


def _make_executor(
    tool: Any,
    ctx: InvocationContext,
    *,
    event_sink: EventSink | None,
    timeout_seconds: float | None,
) -> Executor:
    async def _emit(event: Event) -> None:
        if event_sink is not None:
            await event_sink(event)

    async def _run(args: dict[str, Any], call_id: str = "") -> Any:
        started_at = time.monotonic()
        call_id = call_id or f"piagent-{time.time_ns()}"
        logger.debug(
            "piagent_tool_start invocation_id=%s call_id=%s tool=%s",
            ctx.invocation_id,
            call_id,
            tool.name,
        )

        def _log_complete(status: str) -> None:
            logger.info(
                "piagent_tool_complete invocation_id=%s call_id=%s tool=%s "
                "status=%s duration_ms=%d",
                ctx.invocation_id,
                call_id,
                tool.name,
                status,
                round((time.monotonic() - started_at) * 1000),
            )

        call_event = Event(
            invocation_id=ctx.invocation_id,
            author=ctx.agent.name,
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id=call_id,
                            name=tool.name,
                            args=args,
                        )
                    )
                ],
            ),
            branch=getattr(ctx, "branch", None),
        )
        if getattr(tool, "is_long_running", False) or getattr(
            tool, "_defers_response", False
        ):
            call_event.long_running_tool_ids = {call_id}
        await _emit(call_event)

        try:
            from google.adk.flows.llm_flows import functions

            execution = functions.handle_function_calls_async(
                ctx,
                call_event,
                {tool.name: tool},
            )
            response_event = (
                await asyncio.wait_for(execution, timeout_seconds)
                if timeout_seconds
                else await execution
            )
        except asyncio.TimeoutError:
            logger.warning(
                "piagent_tool_timeout invocation_id=%s call_id=%s tool=%s "
                "timeout_seconds=%s",
                ctx.invocation_id,
                call_id,
                tool.name,
                timeout_seconds,
            )
            response_event = _error_response_event(
                ctx,
                tool.name,
                call_id,
                f"Tool timed out after {timeout_seconds}s",
            )
        except asyncio.CancelledError:
            _log_complete("cancelled")
            raise
        except Exception as e:  # noqa: BLE001 - surface tool failure to Pi
            logger.warning(
                "piagent_tool_failed invocation_id=%s call_id=%s tool=%s error_type=%s",
                ctx.invocation_id,
                call_id,
                tool.name,
                type(e).__name__,
            )
            response_event = _error_response_event(ctx, tool.name, call_id, str(e))

        if response_event is None:
            _log_complete("pending")
            return {"status": "pending", "call_id": call_id}

        try:
            from google.adk.flows.llm_flows import functions

            auth_event = functions.generate_auth_event(ctx, response_event)
            if auth_event is not None:
                await _emit(auth_event)
            confirmation_event = functions.generate_request_confirmation_event(
                ctx,
                call_event,
                response_event,
            )
            if confirmation_event is not None:
                await _emit(confirmation_event)
        except (AttributeError, ImportError):
            pass

        await _emit(response_event)
        responses = get_event_function_responses(response_event)
        payload: Any = responses[0].response if responses else {"status": "completed"}
        actions = response_event.actions
        if getattr(actions, "requested_auth_configs", None):
            status = "authentication_required"
            payload = {"status": status, "call_id": call_id, "response": payload}
        elif getattr(actions, "requested_tool_confirmations", None):
            status = "confirmation_required"
            payload = {"status": status, "call_id": call_id, "response": payload}
        else:
            response = responses[0].response if responses else {}
            status = (
                "failed"
                if isinstance(response, dict) and response.get("status") == "failed"
                else "completed"
            )
        _log_complete(status)
        return _coerce_tool_result(payload)

    return _run


def _error_response_event(
    ctx: InvocationContext, tool_name: str, call_id: str, message: str
) -> Event:
    return Event(
        invocation_id=ctx.invocation_id,
        author=ctx.agent.name,
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=call_id,
                        name=tool_name,
                        response={"error": message, "status": "failed"},
                    )
                )
            ],
        ),
        branch=getattr(ctx, "branch", None),
    )


class _NoopPluginManager:
    plugins: ClassVar[list[Any]] = []

    async def run_before_model_callback(self, **_: Any) -> Any:
        return None

    async def run_after_model_callback(self, **_: Any) -> Any:
        return None

    async def run_on_model_error_callback(self, **_: Any) -> Any:
        return None

    async def run_before_tool_callback(self, **_: Any) -> Any:
        return None

    async def run_after_tool_callback(self, **_: Any) -> Any:
        return None

    async def run_on_tool_error_callback(self, **_: Any) -> Any:
        return None


def _ensure_invocation_context_defaults(ctx: InvocationContext, agent: Agent) -> None:
    if getattr(agent, "name", None) is None:
        _set_default_attr(agent, "name", "assistant")
    for callback_name in (
        "canonical_before_tool_callbacks",
        "canonical_after_tool_callbacks",
        "canonical_on_tool_error_callbacks",
    ):
        if getattr(agent, callback_name, None) is None:
            _set_default_attr(agent, callback_name, [])
    if getattr(ctx, "agent", None) is None:
        _set_default_attr(ctx, "agent", agent)
    if getattr(ctx, "plugin_manager", None) is None:
        _set_default_attr(ctx, "plugin_manager", _NoopPluginManager())


def _set_default_attr(target: Any, name: str, value: Any) -> None:
    try:
        setattr(target, name, value)
    except Exception as e:  # noqa: BLE001
        logger.debug(
            "piagent: failed to set default %s on %s: %s",
            name,
            type(target).__name__,
            type(e).__name__,
        )


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


async def close_toolsets(toolsets: list[BaseToolset]) -> None:
    """Best-effort close of toolsets opened during Pi tool collection."""
    for toolset in toolsets:
        close = getattr(toolset, "close", None)
        if close is None:
            continue
        try:
            await close()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"piagent: failed to close toolset {toolset!r}: {e}")
