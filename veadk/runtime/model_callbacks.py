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

"""ADK-compatible model callback bridge for non-ADK runtimes."""

from __future__ import annotations

import copy
import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.events.event import Event
from google.adk.flows.llm_flows import functions
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from veadk.runtime.base_runtime import resolve_system_append

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.tools.base_tool import BaseTool

    from veadk.agent import Agent


_INTERNAL_TOOL_NAMES = {
    "adk_framework",
    "adk_request_confirmation",
    "adk_request_credential",
    "adk_request_input",
}


@dataclass
class RuntimeLlmCall:
    """The callback-visible request plus ADK response event shell."""

    llm_request: LlmRequest
    model_response_event: Event
    base_instructions: str = ""


async def build_runtime_llm_request(
    agent: "Agent",
    ctx: "InvocationContext",
    *,
    model: str,
    tools_dict: dict[str, "BaseTool"] | None = None,
) -> RuntimeLlmCall:
    """Build the minimal LlmRequest used by external runtimes.

    This intentionally does not call ADK's full ``_preprocess_async`` pipeline.
    It only exposes the stable request fields model callbacks need in phase 1.
    """

    base_instructions, developer_instructions = await resolve_system_append(agent, ctx)
    llm_request = LlmRequest(model=model)
    if generate_content_config := getattr(agent, "generate_content_config", None):
        llm_request.config = generate_content_config.model_copy(deep=True)
    if developer_instructions:
        llm_request.config.system_instruction = developer_instructions

    if output_schema := getattr(agent, "output_schema", None):
        try:
            llm_request.set_output_schema(output_schema)
        except Exception:
            # Keep callback construction side-effect free across ADK/model
            # versions that reject output_schema with the current config.
            pass

    llm_request.contents = _build_request_contents(agent, ctx)
    if tools_dict:
        llm_request.tools_dict.update(tools_dict)

    model_response_event = Event(
        id=Event.new_id(),
        invocation_id=ctx.invocation_id,
        author=agent.name,
        branch=getattr(ctx, "branch", None),
    )
    return RuntimeLlmCall(
        llm_request=llm_request,
        model_response_event=model_response_event,
        base_instructions=base_instructions,
    )


async def run_before_model_callbacks(
    agent: "Agent",
    ctx: "InvocationContext",
    llm_request: LlmRequest,
    model_response_event: Event,
) -> LlmResponse | None:
    """Run plugin and agent before-model callbacks in ADK order."""

    callback_context = CallbackContext(ctx, event_actions=model_response_event.actions)
    plugin_manager = getattr(ctx, "plugin_manager", None)
    if plugin_manager is not None:
        plugin_response = await plugin_manager.run_before_model_callback(
            callback_context=callback_context,
            llm_request=llm_request,
        )
        if plugin_response is not None:
            return plugin_response

    for callback in getattr(agent, "canonical_before_model_callbacks", []) or []:
        response = callback(
            callback_context=callback_context,
            llm_request=llm_request,
        )
        if inspect.isawaitable(response):
            response = await response
        if response is not None:
            return response
    return None


async def run_after_model_callbacks(
    agent: "Agent",
    ctx: "InvocationContext",
    llm_response: LlmResponse,
    model_response_event: Event,
) -> LlmResponse:
    """Run plugin and agent after-model callbacks in ADK order."""

    plugin_manager = getattr(ctx, "plugin_manager", None)
    if plugin_manager is not None:
        plugin_response = await plugin_manager.run_after_model_callback(
            callback_context=CallbackContext(ctx),
            llm_response=llm_response,
        )
        if plugin_response is not None:
            return plugin_response

    callback_context = CallbackContext(ctx, event_actions=model_response_event.actions)
    for callback in getattr(agent, "canonical_after_model_callbacks", []) or []:
        response = callback(
            callback_context=callback_context,
            llm_response=llm_response,
        )
        if inspect.isawaitable(response):
            response = await response
        if response is not None:
            return response
    return llm_response


async def run_on_model_error_callbacks(
    agent: "Agent",
    ctx: "InvocationContext",
    error: BaseException,
    llm_request: LlmRequest,
    model_response_event: Event,
) -> LlmResponse | None:
    """Run model-error callbacks, probing agent support across ADK versions."""

    callback_context = CallbackContext(ctx, event_actions=model_response_event.actions)
    plugin_manager = getattr(ctx, "plugin_manager", None)
    if plugin_manager is not None:
        plugin_response = await plugin_manager.run_on_model_error_callback(
            callback_context=callback_context,
            llm_request=llm_request,
            error=error,
        )
        if plugin_response is not None:
            return plugin_response

    callbacks = list(getattr(agent, "canonical_on_model_error_callbacks", []) or [])
    if not callbacks:
        raw_callback = getattr(agent, "on_model_error_callback", None)
        if raw_callback:
            callbacks = (
                raw_callback if isinstance(raw_callback, list) else [raw_callback]
            )

    for callback in callbacks:
        response = callback(
            callback_context=callback_context,
            llm_request=llm_request,
            error=error,
        )
        if inspect.isawaitable(response):
            response = await response
        if response is not None:
            return response
    return None


def has_after_model_callbacks(agent: "Agent", ctx: "InvocationContext") -> bool:
    """Return whether final model text must be buffered for after callbacks."""

    if (
        getattr(agent, "canonical_after_model_callbacks", None)
        and agent.canonical_after_model_callbacks
    ):
        return True
    plugin_manager = getattr(ctx, "plugin_manager", None)
    return any(
        _plugin_overrides_callback(plugin, "after_model_callback")
        for plugin in getattr(plugin_manager, "plugins", None) or []
    )


def _plugin_overrides_callback(plugin: Any, callback_name: str) -> bool:
    try:
        from google.adk.plugins.base_plugin import BasePlugin
    except ImportError:
        return hasattr(plugin, callback_name)

    plugin_method = getattr(type(plugin), callback_name, None)
    base_method = getattr(BasePlugin, callback_name, None)
    return plugin_method is not None and plugin_method is not base_method


def llm_response_to_event(
    llm_request: LlmRequest,
    llm_response: LlmResponse,
    model_response_event: Event,
) -> Event:
    """Finalize an LlmResponse into an ADK Event like BaseLlmFlow does."""

    event = Event.model_validate(
        {
            **model_response_event.model_dump(exclude_none=True),
            **llm_response.model_dump(exclude_none=True),
        }
    )

    if event.content:
        function_calls = event.get_function_calls()
        if function_calls:
            functions.populate_client_function_call_id(event)
            event.long_running_tool_ids = functions.get_long_running_function_calls(
                function_calls,
                llm_request.tools_dict,
            )
    return event


def is_final_model_text_event(event: Event, agent_name: str) -> bool:
    """Whether an event is the narrow final text answer eligible for after."""

    if event.author != agent_name or not event.is_final_response():
        return False
    if not event.content or not event.content.parts:
        return False
    return any(
        part.text is not None and not getattr(part, "thought", False)
        for part in event.content.parts
    )


def event_to_llm_response(event: Event) -> LlmResponse:
    """Copy the LlmResponse-facing fields out of an Event."""

    data = event.model_dump(exclude_none=True)
    data = {
        key: value for key, value in data.items() if key in LlmResponse.model_fields
    }
    return LlmResponse.model_validate(data)


def final_events_to_llm_response(events: list[Event]) -> LlmResponse:
    """Merge one external-runtime turn's final text events into one response."""

    if not events:
        return LlmResponse()
    if len(events) == 1:
        return event_to_llm_response(events[0])

    parts: list[types.Part] = []
    for event in events:
        if event.content and event.content.parts:
            parts.extend(copy.deepcopy(event.content.parts))
    response = event_to_llm_response(events[-1])
    response.content = types.Content(role="model", parts=parts)
    return response


def system_instruction_to_text(value: Any) -> str:
    """Render GenerateContentConfig.system_instruction to plain text."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    parts = getattr(value, "parts", None)
    if parts is not None:
        return "\n".join(
            part.text for part in parts if getattr(part, "text", None)
        ).strip()
    return str(value)


def _build_request_contents(
    agent: "Agent", ctx: "InvocationContext"
) -> list[types.Content]:
    current = getattr(ctx, "user_content", None)
    events = _get_context_events(ctx)
    if (
        events
        and getattr(events[-1], "author", None) == "user"
        and _same_content(getattr(events[-1], "content", None), current)
    ):
        events = events[:-1]

    contents: list[types.Content] = []
    for event in events:
        if getattr(event, "partial", False):
            continue
        content = _copy_visible_content(getattr(event, "content", None))
        if content is not None:
            contents.append(content)

    current_content = _copy_visible_content(current)
    if current_content is not None:
        contents.append(current_content)
    return contents


def _get_context_events(ctx: "InvocationContext") -> list[Any]:
    get_events = getattr(ctx, "_get_events", None)
    if callable(get_events):
        try:
            return list(get_events(current_branch=True))
        except TypeError:
            return list(get_events())
    return list(getattr(getattr(ctx, "session", None), "events", None) or [])


def _copy_visible_content(content: Any) -> types.Content | None:
    if content is None or not getattr(content, "parts", None):
        return None
    copied = (
        content.model_copy(deep=True)
        if hasattr(content, "model_copy")
        else copy.deepcopy(content)
    )
    copied.parts = [part for part in copied.parts if not _is_internal_tool_part(part)]
    return copied if copied.parts else None


def _is_internal_tool_part(part: Any) -> bool:
    call = getattr(part, "function_call", None)
    if call is not None and getattr(call, "name", None) in _INTERNAL_TOOL_NAMES:
        return True
    response = getattr(part, "function_response", None)
    return (
        response is not None and getattr(response, "name", None) in _INTERNAL_TOOL_NAMES
    )


def _same_content(left: Any, right: Any) -> bool:
    if left is right:
        return True
    if left is None or right is None:
        return False
    if hasattr(left, "model_dump") and hasattr(right, "model_dump"):
        return left.model_dump(mode="json", exclude_none=True) == right.model_dump(
            mode="json", exclude_none=True
        )
    return left == right
