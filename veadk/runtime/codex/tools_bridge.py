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
- ``executors``: ``{name: async (args, call_id) -> str}`` to run a tool when
  the model calls it and emit matching ADK lifecycle events.

Both are derived from ADK itself — tool declarations via ``BaseTool._get_declaration``
(+ ADK's own ``_function_declaration_to_tool_param`` schema conversion) and
execution via ADK's function-call flow — so MCP tools, function tools and any
other ``BaseTool`` retain callbacks, state/actions, auth, confirmations, and
telemetry without reimplementing dispatch.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

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
Executor = Callable[[dict[str, Any], str], Awaitable[str]]


@dataclass
class CodexToolBundle:
    """Tool declarations and invocation-scoped executors for one Codex turn."""

    specs: list[dict[str, Any]] = field(default_factory=list)
    executors: dict[str, Executor] = field(default_factory=dict)
    tools: dict[str, "BaseTool"] = field(default_factory=dict)
    opened_toolsets: list["BaseToolset"] = field(default_factory=list)


async def build_executable_tools(
    agent: "Agent",
    ctx: "InvocationContext",
    *,
    event_sink: EventSink | None = None,
    timeout_seconds: float | None = None,
) -> CodexToolBundle:
    """Collect the agent's ADK tools as shim-executable functions.

    Python callables are wrapped as ``FunctionTool`` and toolsets (including
    MCP) are resolved with a readonly invocation context. Execution is routed
    through ADK's function-call flow so callbacks, confirmations, state/action
    deltas, long-running markers, and telemetry retain their normal semantics.
    """
    from google.adk.models.lite_llm import _function_declaration_to_tool_param
    from google.adk.agents.readonly_context import ReadonlyContext
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.base_toolset import BaseToolset
    from google.adk.tools.function_tool import FunctionTool

    bundle = CodexToolBundle()
    readonly = ReadonlyContext(ctx)

    def _add(tool: "BaseTool") -> None:
        try:
            declaration = tool._get_declaration()
        except Exception as e:  # noqa: BLE001 - one tool must not break the turn
            logger.warning(
                "codex_tool_skipped reason=missing_declaration error_type=%s",
                type(e).__name__,
            )
            return
        if declaration is None or not declaration.name:
            return
        name = str(declaration.name)
        if name in bundle.tools:
            raise ValueError(f"codex: duplicate tool name {name!r}")
        # ADK builds the OpenAI (chat) tool param, incl. genai->JSON schema
        # normalization; lift its `function` body up to the Responses flat shape.
        chat_param = _function_declaration_to_tool_param(declaration)
        bundle.specs.append({"type": "function", **chat_param["function"]})
        bundle.tools[name] = tool
        bundle.executors[name] = _make_executor(
            tool,
            ctx,
            event_sink=event_sink,
            timeout_seconds=timeout_seconds,
        )

    try:
        for entry in getattr(agent, "tools", None) or []:
            # Skill toolsets are handled by materializing SKILL.md resources.
            if type(entry).__name__ in ("SkillToolset", "SkillsToolset"):
                continue
            if isinstance(entry, BaseToolset):
                try:
                    resolver = getattr(entry, "get_tools_with_prefix", None)
                    if callable(resolver):
                        tools = await resolver(readonly)
                    else:
                        try:
                            tools = await entry.get_tools(readonly_context=readonly)
                        except TypeError:
                            tools = await entry.get_tools()
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "codex_toolset_list_failed toolset_type=%s error_type=%s",
                        type(entry).__name__,
                        type(e).__name__,
                    )
                    continue
                bundle.opened_toolsets.append(entry)
                for tool in tools:
                    _add(tool)
            elif isinstance(entry, BaseTool):
                _add(entry)
            elif callable(entry):
                _add(FunctionTool(entry))
            else:
                logger.warning(
                    "codex_tool_skipped reason=unsupported_entry entry_type=%s",
                    type(entry).__name__,
                )
    except Exception:
        await close_toolsets(bundle.opened_toolsets)
        bundle.opened_toolsets.clear()
        raise

    if bundle.executors:
        logger.debug(
            "codex_tools_ready invocation_id=%s tool_count=%d tools=%s",
            ctx.invocation_id,
            len(bundle.executors),
            ",".join(bundle.executors),
        )
    return bundle


async def resume_confirmed_tools(
    bundle: CodexToolBundle,
    ctx: "InvocationContext",
) -> list[Event]:
    """Resume tool calls answered through ADK's confirmation protocol.

    The standard ADK LLM flow normally performs this step in a request
    processor. Codex bypasses that flow, so the runtime must consume the latest
    ``adk_request_confirmation`` responses itself. The implementation mirrors
    ADK's processor, but reuses the invocation's already-opened tool bundle
    instead of resolving toolsets (and MCP sessions) a second time.
    """
    from google.adk.flows.llm_flows import functions
    from google.adk.tools.tool_confirmation import ToolConfirmation

    get_events = getattr(ctx, "_get_events", None)
    events = (
        get_events(current_branch=True)
        if callable(get_events)
        else list(getattr(ctx.session, "events", None) or [])
    )
    if not events:
        return []

    confirmations_by_id: dict[str, ToolConfirmation] = {}
    confirmation_event_index = -1
    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        if getattr(event, "author", None) != "user":
            continue
        responses = get_event_function_responses(event)
        if not responses:
            return []
        for response in responses:
            if response.name != functions.REQUEST_CONFIRMATION_FUNCTION_CALL_NAME:
                continue
            value = response.response
            if (
                isinstance(value, dict)
                and set(value) == {"response"}
                and isinstance(value["response"], str)
            ):
                value = json.loads(value["response"])
            confirmations_by_id[str(response.id)] = ToolConfirmation.model_validate(
                value
            )
        confirmation_event_index = index
        break

    if not confirmations_by_id:
        return []

    confirmations: dict[str, ToolConfirmation] = {}
    original_calls: dict[str, types.FunctionCall] = {}
    for event in events:
        for call in event.get_function_calls():
            if str(call.id) not in confirmations_by_id:
                continue
            args = call.args or {}
            original = args.get("originalFunctionCall")
            if not original:
                continue
            original_call = types.FunctionCall(**original)
            original_id = str(original_call.id)
            confirmations[original_id] = confirmations_by_id[str(call.id)]
            original_calls[original_id] = original_call

    if not confirmations:
        return []

    # A Runner can retry an invocation after persisting its response. Never
    # repeat a side effect if the original call already has a later response.
    for event in events[confirmation_event_index + 1 :]:
        for response in get_event_function_responses(event):
            original_id = str(response.id)
            confirmations.pop(original_id, None)
            original_calls.pop(original_id, None)
    if not confirmations:
        return []

    response_event = await functions.handle_function_call_list_async(
        ctx,
        list(original_calls.values()),
        bundle.tools,
        set(confirmations),
        confirmations,
    )
    if response_event is None:
        return []

    result: list[Event] = []
    auth_event = functions.generate_auth_event(ctx, response_event)
    if auth_event is not None:
        result.append(auth_event)
    result.append(response_event)
    return result


async def resume_authenticated_tools(
    bundle: CodexToolBundle,
    ctx: "InvocationContext",
) -> list[Event]:
    """Store an ADK credential response and resume its original tool call."""
    try:
        from google.adk.auth.auth_handler import AuthHandler
        from google.adk.auth.auth_tool import AuthConfig, AuthToolArguments
        from google.adk.flows.llm_flows import functions
    except (ImportError, AttributeError):
        return []

    events = list(getattr(ctx.session, "events", None) or [])
    if not events:
        return []

    latest_content_event = next(
        (event for event in reversed(events) if event.content is not None),
        None,
    )
    if latest_content_event is None or latest_content_event.author != "user":
        return []

    auth_responses = {
        str(response.id): response.response
        for response in get_event_function_responses(latest_content_event)
        if response.name == functions.REQUEST_EUC_FUNCTION_CALL_NAME
    }
    if not auth_responses:
        return []

    auth_requests: dict[str, Any] = {}
    for event in events:
        for call in event.get_function_calls():
            call_id = str(call.id)
            if (
                call_id in auth_responses
                and call.name == functions.REQUEST_EUC_FUNCTION_CALL_NAME
            ):
                auth_requests[call_id] = AuthToolArguments.model_validate(call.args)

    resume_ids: set[str] = set()
    for call_id, response in auth_responses.items():
        request = auth_requests.get(call_id)
        if request is None:
            continue
        auth_config = AuthConfig.model_validate(response)
        if request.auth_config.credential_key is not None:
            auth_config.credential_key = request.auth_config.credential_key
        await AuthHandler(auth_config).parse_and_store_auth_response(
            state=ctx.session.state
        )
        if not request.function_call_id.startswith("_adk_toolset_auth_"):
            resume_ids.add(request.function_call_id)

    if not resume_ids:
        return []

    # Locate the original event, preserving parallel calls while filtering
    # execution to just the calls that requested this credential.
    call_event = next(
        (
            event
            for event in reversed(events[:-1])
            if any(str(call.id) in resume_ids for call in event.get_function_calls())
        ),
        None,
    )
    if call_event is None:
        return []

    response_event = await functions.handle_function_calls_async(
        ctx,
        call_event,
        bundle.tools,
        resume_ids,
    )
    if response_event is None:
        return []

    result: list[Event] = []
    auth_event = functions.generate_auth_event(ctx, response_event)
    if auth_event is not None:
        result.append(auth_event)
    confirmation_event = functions.generate_request_confirmation_event(
        ctx, call_event, response_event
    )
    if confirmation_event is not None:
        result.append(confirmation_event)
    result.append(response_event)
    return result


def _make_executor(
    tool: "BaseTool",
    ctx: "InvocationContext",
    *,
    event_sink: EventSink | None,
    timeout_seconds: float | None,
) -> Executor:
    async def _emit(event: Event) -> None:
        if event_sink is not None:
            await event_sink(event)

    async def _run(args: dict[str, Any], call_id: str) -> str:
        started_at = time.monotonic()
        logger.debug(
            "codex_tool_start invocation_id=%s call_id=%s tool=%s",
            ctx.invocation_id,
            call_id,
            tool.name,
        )

        def _log_complete(status: str) -> None:
            logger.info(
                "codex_tool_complete invocation_id=%s call_id=%s tool=%s "
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
                            id=call_id, name=tool.name, args=args
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
                ctx, call_event, {tool.name: tool}
            )
            response_event = (
                await asyncio.wait_for(execution, timeout_seconds)
                if timeout_seconds
                else await execution
            )
        except asyncio.TimeoutError:
            logger.warning(
                "codex_tool_timeout invocation_id=%s call_id=%s tool=%s "
                "timeout_seconds=%s",
                ctx.invocation_id,
                call_id,
                tool.name,
                timeout_seconds,
            )
            response_event = _error_response_event(
                ctx, tool.name, call_id, f"Tool timed out after {timeout_seconds}s"
            )
        except asyncio.CancelledError:
            _log_complete("cancelled")
            raise
        except Exception as e:  # noqa: BLE001 - report failure to model + session
            logger.warning(
                "codex_tool_failed invocation_id=%s call_id=%s tool=%s "
                "error_type=%s",
                ctx.invocation_id,
                call_id,
                tool.name,
                type(e).__name__,
            )
            response_event = _error_response_event(ctx, tool.name, call_id, str(e))

        if response_event is None:
            _log_complete("pending")
            return json.dumps(
                {"status": "pending", "call_id": call_id}, ensure_ascii=False
            )

        # Mirror BaseLlmFlow's post-processing so clients receive the standard
        # ADK credential/confirmation function calls rather than having to
        # understand EventActions internals.
        try:
            from google.adk.flows.llm_flows import functions

            auth_event = functions.generate_auth_event(ctx, response_event)
            if auth_event is not None:
                await _emit(auth_event)
            confirmation_event = functions.generate_request_confirmation_event(
                ctx, call_event, response_event
            )
            if confirmation_event is not None:
                await _emit(confirmation_event)
        except (AttributeError, ImportError):
            # Compatibility with ADK versions predating these helpers: the
            # response EventActions still carry the request.
            pass

        await _emit(response_event)
        responses = get_event_function_responses(response_event)
        payload: Any = responses[0].response if responses else {"status": "completed"}
        actions = response_event.actions
        if getattr(actions, "requested_auth_configs", None):
            status = "authentication_required"
            payload = {
                "status": status,
                "call_id": call_id,
                "response": payload,
            }
        elif getattr(actions, "requested_tool_confirmations", None):
            status = "confirmation_required"
            payload = {
                "status": status,
                "call_id": call_id,
                "response": payload,
            }
        else:
            response = responses[0].response if responses else {}
            status = (
                "failed"
                if isinstance(response, dict) and response.get("status") == "failed"
                else "completed"
            )
        _log_complete(status)
        if isinstance(payload, str):
            return payload
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            return str(payload)

    return _run


def _error_response_event(
    ctx: "InvocationContext", name: str, call_id: str, message: str
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
                        name=name,
                        response={"error": message, "status": "failed"},
                    )
                )
            ],
        ),
        branch=getattr(ctx, "branch", None),
    )


async def close_toolsets(toolsets: list["BaseToolset"]) -> None:
    """Best-effort close of toolset sessions opened during the turn."""
    for toolset in toolsets:
        close = getattr(toolset, "close", None)
        if close is None:
            continue
        try:
            await close()
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "codex_toolset_close_failed toolset_type=%s error_type=%s",
                type(toolset).__name__,
                type(e).__name__,
            )
