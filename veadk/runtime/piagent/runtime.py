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

from google.adk.agents.invocation_context import LlmCallsLimitExceededError

from veadk.runtime.base_runtime import BaseRuntime
from veadk.runtime.model_callbacks import (
    RuntimeLlmCall,
    build_runtime_llm_request,
    final_events_to_llm_response,
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
    counts_as_model_call,
)
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events.event import Event
    from google.adk.models.llm_response import LlmResponse
    from opentelemetry.trace import Span

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
        # ADK's `call_llm` span is opened by its own LLM flow, which this
        # runtime replaces. Open it here so VeADK's telemetry chain (the
        # in-memory exporter's session index, the evaluator, portal metrics and
        # the common model-span attributes) sees a Pi invocation at all.
        call_llm_span = _start_call_llm_span()
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
                _emit_call_llm_telemetry(
                    ctx, runtime_call, short_circuit, call_llm_span
                )
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
            # Buffered unconditionally: gating this on a registered after-model
            # callback made otherwise identical agents produce different event
            # streams, and let an intermediate assistant message read as the
            # turn's final response.
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
                        async for pi_event in client.prompt(prompt):
                            if counts_as_model_call(pi_event):
                                _charge_llm_call(ctx)
                            for event in translator.event_to_adk_events(pi_event):
                                if is_final_model_text_event(event, agent.name):
                                    final_text_events.append(event)
                                    continue
                                yield event
                    except LlmCallsLimitExceededError as e:
                        # ADK raises this outside its on_model_error handling,
                        # so it must propagate rather than be turned into a
                        # model-error fallback. Leaving the `async with` blocks
                        # terminates the Pi subprocess, stopping the overrun.
                        _emit_call_llm_telemetry(
                            ctx, runtime_call, _error_llm_response(e), call_llm_span
                        )
                        raise
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
                            _emit_call_llm_telemetry(
                                ctx,
                                runtime_call,
                                _error_llm_response(e),
                                call_llm_span,
                            )
                            raise
                        _emit_call_llm_telemetry(
                            ctx, runtime_call, fallback, call_llm_span
                        )
                        yield llm_response_to_event(
                            runtime_call.llm_request,
                            fallback,
                            runtime_call.model_response_event,
                        )
                        return

            # One merged response per turn, always: after-model callbacks must
            # run on every turn (ADK does, and the harness collects token usage
            # only through them), so this is not gated on there being text.
            llm_response = final_events_to_llm_response(final_text_events)
            # Exactly one usage carrier per turn: consumers sum
            # `usage_metadata` across events without deduplicating.
            usage_metadata = translator.build_turn_usage_metadata()
            if usage_metadata is not None:
                llm_response.usage_metadata = usage_metadata
            llm_response = await run_after_model_callbacks(
                agent,
                ctx,
                llm_response,
                runtime_call.model_response_event,
            )
            _emit_call_llm_telemetry(ctx, runtime_call, llm_response, call_llm_span)
            event = llm_response_to_event(
                runtime_call.llm_request,
                llm_response,
                runtime_call.model_response_event,
            )
            # A tool-only turn produces no text; emitting a contentless final
            # response would make an empty event read as the turn's answer.
            if event.content and event.content.parts:
                yield event
        finally:
            if tool_bundle is not None:
                await close_toolsets(tool_bundle.opened_toolsets)
            skill_bundle.close()
            _end_span(call_llm_span)


def _start_call_llm_span() -> "Span | None":
    """Open the ADK-shaped ``call_llm`` span for one Pi invocation.

    VeADK keys its whole model-telemetry chain off a span literally named
    ``call_llm`` in ADK's tracer scope: the in-memory exporter indexes sessions
    by it, the evaluator reads its prompt/completion attributes, and portal
    metrics and the common model-span attributes are written from
    :func:`veadk.tracing.telemetry.telemetry.trace_call_llm`. ADK opens that
    span inside the LLM flow this runtime replaces, so the runtime must open it
    itself.

    ``start_span`` is used rather than ``start_as_current_span``: ``run_async``
    is an async generator, so a context manager spanning its ``yield`` points
    would attach the OTel context in one task resumption and detach it in
    another, corrupting the context stack. Keeping the span non-current also
    leaves tool spans as siblings of ``call_llm`` under ``invoke_agent``, which
    is ADK's own shape.

    Returns:
        Span | None: The started span, or ``None`` when tracing is unavailable.
    """
    try:
        from google.adk.telemetry.tracing import tracer

        return tracer.start_span("call_llm")
    except Exception:  # noqa: BLE001
        logger.warning("piagent_trace_span_start_failed")
        return None


def _end_span(span: "Span | None") -> None:
    """End a span without ever failing the turn."""
    if span is None:
        return
    try:
        span.end()
    except Exception:  # noqa: BLE001
        logger.warning("piagent_trace_span_end_failed")


def _emit_call_llm_telemetry(
    ctx: "InvocationContext",
    runtime_call: RuntimeLlmCall,
    llm_response: "LlmResponse",
    span: "Span | None",
) -> None:
    """Write one turn's model telemetry onto the ``call_llm`` span.

    Emitted exactly once per invocation, because the evaluator reads the first
    span's prompt as the user input and the last span's completion as the final
    answer, and the telemetry layer accumulates tokens per span.

    The span is made current only for this synchronous call, since portal
    metrics derive the call duration from the current span's start time.

    Args:
        ctx (InvocationContext): The invocation being served.
        runtime_call (RuntimeLlmCall): The request built for this invocation.
        llm_response (LlmResponse): The merged response for this turn.
        span (Span | None): The owning ``call_llm`` span, if tracing is active.
    """
    if span is None:
        return
    try:
        from opentelemetry import trace as otel_trace

        from veadk.tracing.telemetry.telemetry import trace_call_llm

        with otel_trace.use_span(span, end_on_exit=False):
            trace_call_llm(
                ctx,
                runtime_call.model_response_event.id,
                runtime_call.llm_request,
                llm_response,
                span,
            )
    except Exception:  # noqa: BLE001
        logger.warning(
            "piagent_trace_call_llm_failed invocation_id=%s",
            getattr(ctx, "invocation_id", ""),
        )


def _charge_llm_call(ctx: "InvocationContext") -> None:
    """Charge one backend model call to the invocation's ADK call budget.

    ADK enforces ``RunConfig.max_llm_calls`` solely from
    ``InvocationContext.increment_llm_call_count``, which only its own
    ``BaseLlmFlow`` calls. This runtime replaces that flow, so without this hook
    ``max_llm_calls`` never fires for ``runtime="piagent"``.

    Pi owns its agent loop inside the binary, so unlike ADK -- which charges
    *before* dispatching a call and therefore prevents the overrunning call --
    this can only charge a call Pi has already completed and reported. The
    budget is therefore enforced one call late: the invocation is aborted once
    the limit is passed, rather than stopped just short of it.

    Args:
        ctx (InvocationContext): The invocation being served.

    Raises:
        google.adk.agents.invocation_context.LlmCallsLimitExceededError: When
            the invocation exceeds ``RunConfig.max_llm_calls``.
    """
    increment = getattr(ctx, "increment_llm_call_count", None)
    if callable(increment):
        increment()


def _error_llm_response(error: BaseException) -> "LlmResponse":
    """Build the response recorded on the span when a turn fails."""
    from google.adk.models.llm_response import LlmResponse

    return LlmResponse(
        error_code=type(error).__name__,
        error_message=str(error) or type(error).__name__,
    )
