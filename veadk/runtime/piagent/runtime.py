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

"""Pi coding agent runtime for VeADK."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from veadk.runtime.agent_transfer import (
    append_transfer_instructions,
    build_transfer_tool,
    get_transfer_targets,
    run_transferred_agent,
    transfer_agent_name,
)
from veadk.runtime.base_runtime import BaseRuntime
from veadk.runtime.model_callbacks import (
    build_runtime_llm_request,
    final_events_to_llm_response,
    has_after_model_callbacks,
    is_final_model_text_event,
    llm_response_to_event,
    run_after_model_callbacks,
    run_before_model_callbacks,
    run_on_model_error_callbacks,
)
from veadk.runtime.piagent.client import PiAgentRpcClient
from veadk.runtime.piagent.config import PiAgentConfig, prepare_piagent_home
from veadk.runtime.piagent.installer import resolve_or_install_piagent_binary
from veadk.runtime.piagent.skills import materialize_skills_for_pi
from veadk.runtime.piagent.tool_runtime import PiToolRuntime
from veadk.runtime.piagent.tools_bridge import (
    add_tool_to_bundle,
    build_executable_tools,
    close_toolsets,
    sync_bundle_to_tools_dict,
)
from veadk.runtime.piagent.translate import (
    PiEventTranslator,
    build_prompt_from_llm_request,
)
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events.event import Event

    from veadk.agent import Agent

logger = get_logger(__name__)
_QUEUE_DONE = object()


class PiAgentRuntime(BaseRuntime):
    """Run an agent invocation through a local Pi RPC process."""

    name = "piagent"

    async def run_async(
        self, agent: Agent, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        binary_path = resolve_or_install_piagent_binary()
        config = PiAgentConfig.from_agent(agent, binary_path)
        prepare_piagent_home(config)
        skill_bundle = materialize_skills_for_pi(agent)
        tool_bundle = None
        event_queue: asyncio.Queue[object] = asyncio.Queue()

        async def _emit_tool_event(event: Event) -> None:
            await event_queue.put(event)

        try:
            tool_bundle = await build_executable_tools(
                agent, ctx, event_sink=_emit_tool_event
            )
            transfer_targets = get_transfer_targets(agent)
            if transfer_targets:
                add_tool_to_bundle(
                    tool_bundle,
                    build_transfer_tool(transfer_targets),
                    ctx,
                    seen={spec.name for spec in tool_bundle.specs},
                    event_sink=_emit_tool_event,
                )

            runtime_call = await build_runtime_llm_request(
                agent,
                ctx,
                model=config.model.model,
                tools_dict=tool_bundle.tools,
            )
            short_circuit = await run_before_model_callbacks(
                agent,
                ctx,
                runtime_call.llm_request,
                runtime_call.model_response_event,
            )
            if short_circuit is not None:
                yield llm_response_to_event(
                    runtime_call.llm_request,
                    short_circuit,
                    runtime_call.model_response_event,
                )
                return

            sync_bundle_to_tools_dict(
                tool_bundle,
                runtime_call.llm_request.tools_dict,
                ctx,
                event_sink=_emit_tool_event,
            )
            if "transfer_to_agent" in runtime_call.llm_request.tools_dict:
                append_transfer_instructions(
                    agent,
                    runtime_call.llm_request,
                    transfer_targets,
                )
            prompt = build_prompt_from_llm_request(runtime_call.llm_request)

            logger.info(
                "piagent runtime: "
                f"model={config.model.model} provider={config.model.provider_id}"
            )
            translator = PiEventTranslator(
                author=agent.name,
                invocation_id=ctx.invocation_id,
                bridged_tool_names=set(tool_bundle.executors),
            )
            buffer_final_text = has_after_model_callbacks(agent, ctx)
            final_text_events: list[Event] = []
            async with PiToolRuntime(tool_bundle) as tools:
                run_config = (
                    config.with_skills(skill_paths=list(skill_bundle.paths))
                    if skill_bundle.paths
                    else config
                )
                run_config = (
                    run_config.with_tools(extensions=[tools.extension_path])
                    if tools.enabled
                    else run_config
                )
                async with PiAgentRpcClient(run_config) as client:
                    pump: asyncio.Task[None] | None = None

                    async def _pump_pi() -> None:
                        try:
                            async for pi_event in client.prompt(prompt):
                                for event in translator.event_to_adk_events(pi_event):
                                    await event_queue.put(event)
                        except Exception as e:  # noqa: BLE001 - forward pump errors
                            await event_queue.put(e)
                        finally:
                            await event_queue.put(_QUEUE_DONE)

                    try:
                        pump = asyncio.create_task(_pump_pi())
                        while True:
                            queued = await event_queue.get()
                            if queued is _QUEUE_DONE:
                                break
                            if isinstance(queued, BaseException):
                                raise queued
                            event = queued  # type: ignore[assignment]
                            transfer_target = transfer_agent_name(event)
                            if buffer_final_text and is_final_model_text_event(
                                event, agent.name
                            ):
                                final_text_events.append(event)
                                continue
                            yield event
                            if transfer_target:
                                final_text_events.clear()
                                async for transferred_event in run_transferred_agent(
                                    ctx,
                                    event,
                                ):
                                    _scope_event(transferred_event, ctx)
                                    yield transferred_event
                                if pump is not None and not pump.done():
                                    pump.cancel()
                                    await asyncio.gather(
                                        pump,
                                        return_exceptions=True,
                                    )
                                return
                        await pump
                    except Exception as e:
                        if pump is not None and not pump.done():
                            pump.cancel()
                            await asyncio.gather(pump, return_exceptions=True)
                        fallback = await run_on_model_error_callbacks(
                            agent,
                            ctx,
                            e,
                            runtime_call.llm_request,
                            runtime_call.model_response_event,
                        )
                        if fallback is None:
                            raise
                        yield llm_response_to_event(
                            runtime_call.llm_request,
                            fallback,
                            runtime_call.model_response_event,
                        )
                        return
            if final_text_events:
                llm_response = final_events_to_llm_response(final_text_events)
                llm_response = await run_after_model_callbacks(
                    agent,
                    ctx,
                    llm_response,
                    runtime_call.model_response_event,
                )
                yield llm_response_to_event(
                    runtime_call.llm_request,
                    llm_response,
                    runtime_call.model_response_event,
                )
        finally:
            if tool_bundle is not None:
                await close_toolsets(tool_bundle.opened_toolsets)
            skill_bundle.close()


def _scope_event(event: Event, ctx: InvocationContext) -> None:
    event.branch = getattr(ctx, "branch", None)
    event.isolation_scope = getattr(ctx, "isolation_scope", None)
