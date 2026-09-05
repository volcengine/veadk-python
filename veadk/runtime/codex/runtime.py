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

"""OpenAI Codex runtime for VeADK.

Drives an agent invocation through the Codex SDK (``codex_app_server``) instead
of ADK's built-in LLM flow, while the surrounding ``Runner`` keeps owning
session, memory and tracing.

Key guarantees (mirroring the ``cc`` runtime):

- The model is always the one configured on the agent (or via ``ANTHROPIC_MODEL`` /
  settings); if none resolves, the runtime fails fast.
- Codex is isolated from the host's ``~/.codex`` via a dedicated ``CODEX_HOME`` with
  a generated ``config.toml``; the backend credential is injected through the
  provider's ``env_key`` env var. A wrong key fails loudly.
- Codex only speaks the Responses API, so requests are routed through an
  in-process Responses→chat shim (see :mod:`veadk.runtime.codex.proxy`).

Note: this requires the ``openai-codex`` SDK (``pip install openai-codex``),
which bundles the Codex CLI binary via its ``openai-codex-cli-bin`` dependency.
"""

from __future__ import annotations

import asyncio
import atexit
import enum
import hashlib
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator

from openai_codex import (  # type: ignore[import-not-found]
    ApprovalMode,
    AsyncCodex,
    CodexConfig,
    ImageInput,
    LocalImageInput,
    MentionInput,
    Sandbox,
    TextInput,
)
from openai_codex.generated.v2_all import (  # type: ignore[import-not-found]
    Personality,
    ReasoningEffort,
)

from veadk.runtime.base_runtime import BaseRuntime
from veadk.runtime.agent_transfer import append_transfer_instructions
from veadk.runtime.agent_transfer import build_transfer_tool
from veadk.runtime.agent_transfer import get_transfer_targets
from veadk.runtime.agent_transfer import run_transferred_agent
from veadk.runtime.agent_transfer import transfer_agent_name
from veadk.runtime.codex.config import CodexRuntimeConfig
from veadk.runtime.codex.config import codex_subprocess_env
from veadk.runtime.codex.config import toml_string
from veadk.runtime.codex.proxy import get_shim
from veadk.runtime.codex.skills import sync_skills_to_codex_home
from veadk.runtime.codex.tools_bridge import (
    add_tool_to_bundle,
    build_executable_tools,
    close_toolsets,
    resume_authenticated_tools,
    resume_confirmed_tools,
    sync_bundle_to_tools_dict,
)
from veadk.runtime.codex.translate import (
    build_input_attachments_from_llm_request,
    build_prompt_from_llm_request,
    build_turn_usage_metadata,
    is_codex_final_text_event,
    notification_to_events,
)
from veadk.runtime.codex.workspace import (
    bind_workspace,
    bind_workspace_to_executors,
)
from veadk.runtime.model_callbacks import (
    merge_turn_bookkeeping,
    RuntimeLlmCall,
    build_runtime_llm_request,
    final_events_to_llm_response,
    llm_response_to_event,
    run_after_model_callbacks,
    run_before_model_callbacks,
    run_on_model_error_callbacks,
    system_instruction_to_text,
)
from veadk.utils.adk_compat import is_adk_gte
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events.event import Event
    from google.adk.models.llm_request import LlmRequest
    from google.adk.models.llm_response import LlmResponse
    from opentelemetry.trace import Span

    from veadk.agent import Agent

logger = get_logger(__name__)

_PROVIDER_ID = "veadk"
_KEY_ENV = "VEADK_CODEX_API_KEY"


class _QueueSentinel(enum.Enum):
    """Single-member enum used as the event queue's end-of-stream marker.

    An `enum` member rather than a bare `object()` so that `is _QUEUE_DONE`
    narrows the queue's `Event | BaseException | _QueueSentinel` union: the
    queue multiplexes three kinds of payload onto one channel.
    """

    DONE = enum.auto()


_QUEUE_DONE = _QueueSentinel.DONE
_WORKSPACE_ROOT_PREFIX = "veadk-codex-workspaces-"
# The process-owned root that holds every session workspace, created on first
# use by `_ensure_session_workspace_root`. `None` until then.
_session_workspace_root: str | None = None
_session_workspace_root_lock = threading.Lock()
# Session workspaces are shared by every invocation of the same session, so
# they must outlive a turn. They are instead reaped once idle for this long,
# which bounds disk growth inside a long-lived server process.
_WORKSPACE_IDLE_TTL_SECONDS = 6 * 3600
# The reaper walks a directory and removes trees, both of which are blocking
# syscalls. It runs off the event loop (a worker thread) *and* no more often
# than this, so a server handling many concurrent turns does not re-scan the
# root once per invocation.
_WORKSPACE_REAP_INTERVAL_SECONDS = 600.0
# Upper bound on trees removed in one pass, so a root that accumulated
# thousands of stale sessions is drained over several passes instead of
# occupying a worker thread for an unbounded time.
_WORKSPACE_REAP_MAX_PER_PASS = 16
_last_workspace_reap_at = 0.0
_workspace_reap_lock = threading.Lock()


def _ensure_session_workspace_root() -> str:
    """Return the process-owned session-workspace root, creating it on demand.

    Created on first use rather than at import time. As a module-level
    ``tempfile.mkdtemp`` it ran for anything that merely *imported* this module
    — a CLI listing runtimes, a test collecting, a worker that never served a
    turn — and left a ``veadk-codex-workspaces-*`` directory in ``$TMPDIR``
    that the ``atexit`` hook can only reclaim on a clean exit. A ``SIGKILL``
    (an OOM kill, a torn-down ``pytest -xdist`` worker, a container stop)
    orphans it, which is why a smoke run found several roots predating it.
    Nothing but a real invocation needs the directory now, so nothing else
    creates one.

    Returns:
        str: Absolute path to the (existing) root directory.
    """
    global _session_workspace_root
    with _session_workspace_root_lock:
        if _session_workspace_root is None:
            root = tempfile.mkdtemp(prefix=_WORKSPACE_ROOT_PREFIX)
            # Registered alongside creation, not at import: a hook over a
            # directory that was never created is pure noise, and
            # `ignore_errors=True` would have hidden that it did nothing.
            atexit.register(shutil.rmtree, root, ignore_errors=True)
            _session_workspace_root = root
        return _session_workspace_root


def __getattr__(name: str) -> Any:
    """Keep ``_SESSION_WORKSPACE_ROOT`` readable as a module attribute.

    PEP 562 module hook. The root is created lazily now, so it can no longer be
    a module-level constant, but reading it must keep working (the smoke test
    reads it to assert a turn left exactly one workspace behind). Access
    materializes the root, because a caller that wants the path is about to
    look inside it.
    """
    if name == "_SESSION_WORKSPACE_ROOT":
        return _ensure_session_workspace_root()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


#: Appended to every turn's developer instructions, because two things Codex's
#: own (deliberately preserved) system prompt tells the model are not true
#: here:
#:
#: - ``apply_patch`` never reaches the backend. Codex offers it as a non-
#:   ``function`` tool and the shim forwards only ``function`` tools, so the
#:   model is told to use a tool it was never given, and spends a round
#:   discovering that.
#: - ``request_user_input`` *is* advertised, but nothing can answer it: an ADK
#:   invocation has no interactive channel, so calling it ends the turn with
#:   the work undone.
#:
#: Kept to the two facts and what to do instead. Both example agents had to
#: counter-instruct this in their own prompts, which is a workaround no user
#: should have to discover. This rides `developer_instructions` (additive)
#: rather than `base_instructions`, which would *replace* Codex's ~21KB
#: system prompt.
_TOOL_AVAILABILITY_NOTE = (
    "Tools available on this run:\n"
    "- `apply_patch` is not one of them. Create and edit files with "
    "`exec_command` instead (for example a `cat > file <<'EOF'` heredoc).\n"
    "- Nobody can answer `request_user_input` during this run, and calling it "
    "ends your turn with the work undone. Decide with what you have, and say "
    "what was missing in your final message."
)


class CodexRuntime(BaseRuntime):
    """Run an agent invocation via the Codex SDK."""

    name = "codex"

    async def run_async(
        self, agent: "Agent", ctx: "InvocationContext"
    ) -> AsyncGenerator["Event", None]:
        model = self._resolve_model(agent)
        runtime_config = CodexRuntimeConfig.from_agent(agent)
        api_base = agent.model_api_base or os.getenv("OPENAI_BASE_URL")
        api_key = agent.model_api_key or os.getenv("OPENAI_API_KEY")
        if not api_base or not api_key:
            raise ValueError(
                "codex runtime requires model_api_base and model_api_key "
                "(the chat endpoint Codex is bridged onto)."
            )

        shim = await get_shim(api_base, api_key)
        shim_url = shim.url or ""
        workspace = _prepare_workspace(runtime_config, ctx)
        await _maybe_reap_workspaces(runtime_config)
        codex_home = _prepare_codex_home(shim_url, model, runtime_config)
        # Expose the agent's skills to Codex by materializing them under
        # `$CODEX_HOME/skills/`, where Codex's native skill system discovers
        # them. Best-effort: a skill failure must not abort the turn.
        try:
            sync_skills_to_codex_home(
                agent, codex_home, invocation_id=ctx.invocation_id
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "codex_skill_sync_failed invocation_id=%s error_type=%s",
                ctx.invocation_id,
                type(e).__name__,
            )

        event_queue: asyncio.Queue["Event | BaseException | _QueueSentinel"] = (
            asyncio.Queue()
        )
        use_adk_transfer_scheduler = _uses_adk_transfer_scheduler(ctx)
        turn_token: str | None = None
        run_started_at = time.monotonic()
        run_status = "failed"

        async def _emit_tool_event(event: "Event") -> None:
            await event_queue.put(event)

        # Bound to None up front so the `except` below can tell "tools were
        # built" from "setup failed before that" without inspecting locals().
        tool_bundle = None
        try:
            tool_bundle = await build_executable_tools(
                agent,
                ctx,
                event_sink=_emit_tool_event,
                timeout_seconds=runtime_config.tool_timeout_seconds,
            )
            transfer_targets = get_transfer_targets(agent)
            if transfer_targets:
                add_tool_to_bundle(
                    tool_bundle,
                    build_transfer_tool(transfer_targets),
                    ctx,
                    event_sink=_emit_tool_event,
                    timeout_seconds=runtime_config.tool_timeout_seconds,
                )
            # These resume paths execute real tools on *this* task, so the
            # workspace is bound around them too: a tool must see the same
            # directory whether the shim called it or a resumed confirmation
            # did.
            with bind_workspace(workspace):
                resumed_events = [
                    *await resume_authenticated_tools(tool_bundle, ctx),
                    *await resume_confirmed_tools(tool_bundle, ctx),
                ]
        except BaseException as e:
            logger.error(
                "codex_runtime_setup_failed invocation_id=%s stage=tools error_type=%s",
                ctx.invocation_id,
                type(e).__name__,
            )
            if tool_bundle is not None:
                await close_toolsets(tool_bundle.opened_toolsets)
            shutil.rmtree(codex_home, ignore_errors=True)
            raise

        # ADK's `call_llm` span is opened by its own LLM flow, which this
        # runtime replaces. Open it here so VeADK's telemetry chain (the
        # in-memory exporter's session index, the evaluator, portal metrics and
        # the common model-span attributes) sees a Codex invocation at all.
        call_llm_span = _start_call_llm_span()

        # One-shot, order-preserving teardown. Three paths reach it (the
        # before-model short circuit, the input-setup failure handler and the
        # `finally`), and a consumer that stops iterating at the short circuit's
        # `yield` raises `GeneratorExit` into the enclosing handler, which then
        # runs the `finally` as well. Without the latch that ran `_end_span`
        # twice ("Calling end() on an ended span") and closed every MCP toolset
        # twice.
        cleanup_done = False

        async def _cleanup() -> None:
            nonlocal cleanup_done
            if cleanup_done:
                return
            cleanup_done = True
            if turn_token is not None:
                shim.unregister_turn(turn_token)
            await close_toolsets(tool_bundle.opened_toolsets)
            # `workspace` is deliberately kept: it is session-scoped and the
            # next invocation of this session must see the files this turn
            # wrote. See `_prepare_workspace` for its lifetime.
            shutil.rmtree(codex_home, ignore_errors=True)
            _end_span(call_llm_span)

        # `_emit_call_llm_telemetry`'s contract is one record per invocation:
        # the evaluator reads the first span's prompt as the user input and the
        # last span's completion as the final answer, and the telemetry layer
        # accumulates tokens per span. The normal path emits on completion and
        # then yields, so an abandoned consumer used to re-enter the failure
        # handler and *overwrite* that record with a `GeneratorExit` error.
        telemetry_emitted = False

        def _emit_telemetry_once(llm_response: "LlmResponse") -> None:
            nonlocal telemetry_emitted
            if telemetry_emitted:
                return
            telemetry_emitted = True
            _emit_call_llm_telemetry(ctx, runtime_call, llm_response, call_llm_span)

        try:
            # Persist resumed confirmation responses before constructing history,
            # so Codex sees the completed/rejected tool result exactly once.
            for event in resumed_events:
                transfer_target = transfer_agent_name(event)
                if transfer_target and use_adk_transfer_scheduler:
                    run_status = "transferred"
                    yield event
                    await _cleanup()
                    return
                yield event
                if transfer_target:
                    async for transferred_event in run_transferred_agent(ctx, event):
                        _scope_event(transferred_event, ctx)
                        yield transferred_event
                    run_status = "transferred"
                    await _cleanup()
                    return

            runtime_call = await build_runtime_llm_request(
                agent,
                ctx,
                model=model,
                tools_dict=tool_bundle.tools,
            )
            short_circuit = await run_before_model_callbacks(
                agent,
                ctx,
                runtime_call.llm_request,
                runtime_call.model_response_event,
            )
            if short_circuit is not None:
                event = llm_response_to_event(
                    runtime_call.llm_request,
                    short_circuit,
                    runtime_call.model_response_event,
                )
                _scope_event(event, ctx)
                _emit_telemetry_once(short_circuit)
                await _cleanup()
                yield event
                return

            sync_bundle_to_tools_dict(
                tool_bundle,
                runtime_call.llm_request.tools_dict,
                ctx,
                event_sink=_emit_tool_event,
                timeout_seconds=runtime_config.tool_timeout_seconds,
            )
            if "transfer_to_agent" in runtime_call.llm_request.tools_dict:
                append_transfer_instructions(
                    agent,
                    runtime_call.llm_request,
                    transfer_targets,
                )
            turn_token = shim.register_turn(
                tool_bundle.specs,
                # Bound here rather than by a ContextVar set for the turn: the
                # shim runs executors on a task descended from its uvicorn
                # server task, which snapshotted its context when the *first*
                # invocation in the process started the shim, so an ambient
                # value would be that invocation's - a silent cross-tenant
                # leak. See `veadk.runtime.codex.workspace`.
                bind_workspace_to_executors(tool_bundle.executors, workspace),
                max_tool_iterations=runtime_config.max_tool_iterations,
                invocation_id=ctx.invocation_id,
                model_extra_config=agent.model_extra_config,
                on_model_call=lambda: _charge_llm_call(ctx),
            )
            # Keep privileged instructions out of the user transcript. The SDK
            # exposes a native developer-instruction channel for them.
            #
            # `base_instructions` is deliberately NOT used: Codex *replaces*
            # its built-in system prompt when it is set (models-manager
            # overwrites `instructions_template` and nulls
            # `instructions_variables`; nothing concatenates), which would
            # delete ~20KB of shipped guidance covering AGENTS.md, planning,
            # `update_plan`, `apply_patch` and shell-tool usage. Codex's own
            # docs call the equivalent config key strongly discouraged.
            # `developer_instructions` is purely additive - Codex renders it as
            # its own `developer` message alongside AGENTS.md, skills and
            # environment context - so the agent identity block is folded in
            # there, ahead of the agent instruction to preserve ordering.
            prompt = build_prompt_from_llm_request(runtime_call.llm_request)
            developer_instructions = "\n\n".join(
                block
                for block in (
                    (runtime_call.base_instructions or "").strip(),
                    system_instruction_to_text(
                        runtime_call.llm_request.config.system_instruction
                    ).strip(),
                    _TOOL_AVAILABILITY_NOTE,
                )
                if block
            )
            # Tag the turn's own user message so the shim can tell this turn's
            # sampling requests from Codex-internal passes that reuse the same
            # provider block and bearer token. Codex re-sends the whole history
            # when it auto-compacts, so an untagged shim would advertise the
            # agent's ADK tools to the summarizer and replay the turn's tool
            # transcript into it - and would then execute a real tool a second
            # time if the summarizer asked for one. The tag rides in the prompt
            # text rather than a separate input item precisely because Codex
            # preserves user-message text verbatim across compaction and
            # reordering, where a side-channel item would be dropped.
            input_items = _build_codex_input(
                prompt,
                runtime_call.llm_request,
                workspace,
                turn_marker=shim.turn_marker(turn_token),
            )
            logger.info(
                "codex_runtime_start invocation_id=%s agent=%s model=%s "
                "sandbox=%s approval_mode=%s network_access=%s tool_count=%d",
                ctx.invocation_id,
                agent.name,
                model,
                runtime_config.sandbox,
                runtime_config.approval_mode,
                runtime_config.network_access,
                len(tool_bundle.executors),
            )
            logger.info(
                "codex_base_instructions_preserved invocation_id=%s "
                "identity_chars=%d developer_chars=%d "
                "detail=Codex keeps its built-in system prompt; the agent "
                "identity and instruction are sent as developer instructions.",
                ctx.invocation_id,
                len(runtime_call.base_instructions or ""),
                len(developer_instructions),
            )
            if runtime_config.approval_mode == "auto_review":
                logger.warning(
                    "codex_approval_auto_accept invocation_id=%s approval_mode=%s "
                    "detail=Every Codex sandbox escalation and file-change "
                    "approval request is auto-accepted by the SDK's default "
                    "approval handler; no human and no ADK confirmation is "
                    "consulted. Use approval_mode='deny_all' to keep Codex "
                    "inside the sandbox.",
                    ctx.invocation_id,
                    runtime_config.approval_mode,
                )
            # CodexConfig.env is copied into only this subprocess. Never mutate
            # process-wide CODEX_HOME or credential variables.
            sdk_config = CodexConfig(
                cwd=workspace,
                env=codex_subprocess_env(codex_home, turn_token),
            )
        except BaseException as e:
            logger.error(
                "codex_runtime_setup_failed invocation_id=%s stage=input error_type=%s",
                ctx.invocation_id,
                type(e).__name__,
            )
            await _cleanup()
            raise
        turn = None
        pump: asyncio.Task[None] | None = None
        # Lookahead for the tool-only turn. That turn's merged response carries
        # the turn's `usage_metadata` and any `state_delta` a model callback
        # wrote, but it has no content, and a contentless, tool-free,
        # non-partial event reads as the invocation's final response
        # (`Event.is_final_response()`) - so it cannot simply be emitted. The
        # last *durable* event is therefore held back to give that bookkeeping
        # somewhere real to land; see `_merge_turn_bookkeeping`. Partial events
        # are no use as a target (they are never persisted), so any that follow
        # the held-back one are buffered behind it rather than overtaking it.
        merge_target: "Event | None" = None
        try:
            async with AsyncCodex(config=sdk_config) as codex:
                thread = await codex.thread_start(
                    model=model,
                    model_provider=_PROVIDER_ID,
                    developer_instructions=developer_instructions or None,
                    cwd=workspace,
                    ephemeral=True,
                    approval_mode=_approval_mode(runtime_config),
                    sandbox=_sandbox(runtime_config),
                    personality=Personality(runtime_config.personality),
                )
                turn = await thread.turn(
                    input_items,
                    cwd=workspace,
                    approval_mode=_approval_mode(runtime_config),
                    sandbox=_sandbox(runtime_config),
                    effort=ReasoningEffort(runtime_config.reasoning_effort),
                )
                stream = turn.stream()
                # Latest `ThreadTokenUsageUpdatedNotification` payload. The
                # thread is created fresh and ephemeral for this invocation, so
                # its `total` breakdown is this invocation's complete usage.
                latest_token_usage: dict[str, Any] = {}

                async def _pump_codex() -> None:
                    active_tool_items: set[str] = set()
                    try:
                        # No turn-id filtering here: `AsyncTurnHandle.stream()`
                        # reads a per-turn queue that `MessageRouter` already
                        # fills strictly by turn id, so every notification on
                        # this stream belongs to `turn`. The previous filter was
                        # both redundant and wrong - `TurnStartedNotification`
                        # carries no `turn_id`, so it was only ever skipped by
                        # accident of the attribute being absent.
                        async for note in stream:
                            payload = note.payload
                            for event in notification_to_events(
                                payload,
                                agent.name,
                                ctx.invocation_id,
                                active_tool_items=active_tool_items,
                            ):
                                _scope_event(event, ctx)
                                if (
                                    event.custom_metadata
                                    and event.custom_metadata.get("codex_event_type")
                                    == "token_usage"
                                ):
                                    usage = event.custom_metadata.get("token_usage")
                                    if isinstance(usage, dict):
                                        latest_token_usage.clear()
                                        latest_token_usage.update(usage)
                                    logger.info(
                                        "codex_token_usage invocation_id=%s usage=%s",
                                        ctx.invocation_id,
                                        usage,
                                    )
                                await event_queue.put(event)
                    except BaseException as e:
                        await event_queue.put(e)
                    finally:
                        aclose = getattr(stream, "aclose", None)
                        if aclose is not None:
                            await aclose()
                        await event_queue.put(_QUEUE_DONE)

                pump = asyncio.create_task(_pump_codex())
                # Buffer unconditionally. Codex emits one durable `agentMessage`
                # per intermediate model reply, so streaming them straight
                # through would produce several `is_final_response()` events and
                # make `output_key`, evaluation and the A2A reply
                # last-writer-wins on whichever preamble arrived last. Buffering
                # only when an after-model callback happens to be registered
                # also made the event shape depend on plugin installation.
                final_text_events: list[Event] = []
                transfer_requested = False
                deferred_transfer_event: Event | None = None
                while True:
                    queued = await event_queue.get()
                    if queued is _QUEUE_DONE:
                        break
                    if isinstance(queued, BaseException):
                        raise queued
                    event = queued
                    transfer_target = transfer_agent_name(event)
                    if transfer_target and use_adk_transfer_scheduler:
                        transfer_requested = True
                        run_status = "transferred"
                        final_text_events.clear()
                        deferred_transfer_event = event
                        continue
                    if is_codex_final_text_event(event):
                        final_text_events.append(event)
                        continue
                    # Partials go out immediately, even while a durable event
                    # is held back as the merge target. Parking them behind it
                    # stalled the live stream for the rest of the turn: the
                    # final answer's deltas and a command's output both arrive
                    # after the last durable event, so they were delivered only
                    # once the Codex stream had already ended. Overtaking is
                    # safe because partials are never persisted
                    # (`BaseSessionService.append_event` returns early on them),
                    # so only the order among durable events is observable in
                    # session history, and that order is unchanged.
                    if event.partial:
                        yield event
                        continue
                    if merge_target is not None:
                        yield merge_target
                        merge_target = None
                    if transfer_target:
                        transfer_requested = True
                        final_text_events.clear()
                        yield event
                        async for transferred_event in run_transferred_agent(
                            ctx, event
                        ):
                            _scope_event(transferred_event, ctx)
                            yield transferred_event
                        run_status = "transferred"
                        break
                    merge_target = event
                if transfer_requested:
                    await pump
                    if deferred_transfer_event is not None:
                        yield deferred_transfer_event
                    return
                await pump

                # The shim serves backend calls on the server's task, so an
                # exception it raised (an exhausted `max_llm_calls` budget) got
                # relayed to Codex as a 429 and recorded rather than propagated.
                # Re-raise it here so Runner's normal handling still applies,
                # instead of returning whatever partial answer Codex salvaged.
                shim_error = shim.turn_error(turn_token)
                if shim_error is not None:
                    raise shim_error

                # One merged response per turn, always: after-model callbacks
                # must run on every turn (ADK does, and the harness collects
                # token usage only through them), so this is not gated on there
                # being text to emit.
                llm_response = final_events_to_llm_response(final_text_events)
                usage_metadata = build_turn_usage_metadata(latest_token_usage)
                if usage_metadata is not None:
                    llm_response.usage_metadata = usage_metadata
                llm_response = await run_after_model_callbacks(
                    agent,
                    ctx,
                    llm_response,
                    runtime_call.model_response_event,
                )
                _emit_telemetry_once(llm_response)
                event = llm_response_to_event(
                    runtime_call.llm_request,
                    llm_response,
                    runtime_call.model_response_event,
                )
                _scope_event(event, ctx)
                if event.content and event.content.parts:
                    if merge_target is not None:
                        yield merge_target
                        merge_target = None
                    yield event
                elif merge_target is not None:
                    # A tool-only turn: the merged event has no text, and a
                    # contentless, tool-free, non-partial event satisfies
                    # `Event.is_final_response()` - a spurious "the agent
                    # answered" marker for any consumer keying on that alone,
                    # including upstream ADK code that stops at the first final
                    # response. (VeADK's own readers of the final answer -
                    # `runtime/output_state.py`, `evaluation/base_evaluator.py`,
                    # `runner.py`'s A2A path - all guard on content as well, so
                    # they are not what is at risk here.) Dropping it whole,
                    # however, also threw away the
                    # `state_delta` model callbacks wrote through
                    # `CallbackContext(ctx, event_actions=model_response_event.actions)`
                    # and the turn's `usage_metadata`. Marking it partial does
                    # not rescue either: partial events are never persisted
                    # (`google/adk/sessions/base_session_service.py`). So the
                    # bookkeeping is folded onto the last tool event instead -
                    # an event that is emitted, persisted, and is not a final
                    # response.
                    merge_turn_bookkeeping(merge_target, event)
                    yield merge_target
                    merge_target = None
                else:
                    # Nothing durable was emitted this turn: there is nowhere
                    # else for the bookkeeping to go, and no earlier event that
                    # this one's final-response marker could displace.
                    yield event
                run_status = "completed"
        except asyncio.CancelledError:
            run_status = "cancelled"
            # A recorded shim error is deliberately *not* substituted here.
            # `CancelledError` must reach the awaiting task unchanged or the
            # cancellation is swallowed and asyncio's contract is broken; the
            # budget error is logged instead so the cause is still visible.
            if shim.turn_error(turn_token) is not None:
                logger.warning(
                    "codex_shim_turn_error_dropped_on_cancel invocation_id=%s "
                    "error_type=%s",
                    ctx.invocation_id,
                    type(shim.turn_error(turn_token)).__name__,
                )
            if turn is not None:
                try:
                    await turn.interrupt()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "codex_interrupt_failed invocation_id=%s",
                        ctx.invocation_id,
                    )
            raise
        except BaseException as e:
            # Read the shim's recorded error *before* the `finally`'s
            # `unregister_turn` drops the turn state. The shim serves backend
            # calls on the server's task, so an exhausted `max_llm_calls` budget
            # cannot propagate from there: it is recorded, relayed to Codex as a
            # failed response, and re-read once the turn ends. That read used to
            # live on the success path only, so any transport failure arriving
            # afterwards - the pump re-raising, the Codex SDK erroring - jumped
            # straight here and the budget error was silently discarded, taking
            # the whole `max_llm_calls` feature with it and handing the
            # `on_model_error` callbacks the wrong exception. The shim error is
            # the *cause* and wins; the transport failure is chained onto it.
            shim_error = shim.turn_error(turn_token)
            if shim_error is not None and shim_error is not e:
                logger.warning(
                    "codex_shim_turn_error_preferred invocation_id=%s "
                    "shim_error_type=%s transport_error_type=%s",
                    ctx.invocation_id,
                    type(shim_error).__name__,
                    type(e).__name__,
                )
                if shim_error.__cause__ is None:
                    shim_error.__cause__ = e
                e = shim_error
            logger.error(
                "codex_runtime_failed invocation_id=%s error_type=%s",
                ctx.invocation_id,
                type(e).__name__,
            )
            # Nothing already streamed may be lost to the failure. Never on a
            # `GeneratorExit`: the consumer has stopped reading, and yielding
            # while it propagates is a hard `RuntimeError`.
            if not isinstance(e, GeneratorExit):
                held, merge_target = merge_target, None
                if held is not None:
                    yield held
            # `runtime_call` is always bound here: it is assigned in the
            # preceding block, whose handler re-raises on failure.
            if isinstance(e, Exception):
                fallback = await run_on_model_error_callbacks(
                    agent,
                    ctx,
                    e,
                    runtime_call.llm_request,
                    runtime_call.model_response_event,
                )
                if fallback is not None:
                    event = llm_response_to_event(
                        runtime_call.llm_request,
                        fallback,
                        runtime_call.model_response_event,
                    )
                    _scope_event(event, ctx)
                    _emit_telemetry_once(fallback)
                    yield event
                    run_status = "completed"
                    return
            # A `GeneratorExit` means the consumer stopped iterating, not that
            # the model failed: recording it would overwrite a completed span's
            # attributes with an error that never happened.
            if not isinstance(e, GeneratorExit):
                _emit_telemetry_once(_error_llm_response(e))
            raise e
        finally:
            if pump is not None and not pump.done():
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
            await _cleanup()
            logger.info(
                "codex_runtime_complete invocation_id=%s status=%s duration_ms=%d",
                ctx.invocation_id,
                run_status,
                round((time.monotonic() - run_started_at) * 1000),
            )

    def _resolve_model(self, agent: "Agent") -> str:
        name = agent.model_name
        if isinstance(name, list):
            name = name[0] if name else ""
        name = name or os.getenv("OPENAI_MODEL", "")
        if not name:
            raise ValueError(
                "codex runtime requires a model: set Agent(model_name=...) "
                "or the OPENAI_MODEL environment variable."
            )
        return name


def _prepare_codex_home(
    shim_url: str, model: str, runtime_config: CodexRuntimeConfig
) -> str:
    """Create an invocation-isolated CODEX_HOME with a config.toml.

    The config points Codex at the local Responses shim using a dedicated
    ``veadk`` provider, so the run never touches the host's ``~/.codex``.
    """
    home = tempfile.mkdtemp(prefix="veadk-codex-")
    os.chmod(home, 0o700)
    approval_policy = (
        "on-request" if runtime_config.approval_mode == "auto_review" else "never"
    )
    sandbox_mode = {
        "read_only": "read-only",
        "workspace_write": "workspace-write",
        "full_access": "danger-full-access",
    }[runtime_config.sandbox]
    config = (
        f"model = {toml_string(model)}\n"
        f"model_provider = {toml_string(_PROVIDER_ID)}\n"
        f"review_model = {toml_string(model)}\n"
        f"approval_policy = {toml_string(approval_policy)}\n"
        f"sandbox_mode = {toml_string(sandbox_mode)}\n"
        # `disable_response_storage` is intentionally absent: it was removed
        # upstream (absent from config.schema.json and from the pinned CLI
        # binary) and `store: false` is now unconditional in Codex's client,
        # so writing it here only produced a silently ignored key.
        f"model_reasoning_effort = {toml_string(runtime_config.reasoning_effort)}\n"
        f"personality = {toml_string(runtime_config.personality)}\n\n"
        f"[model_providers.{_PROVIDER_ID}]\n"
        f"name = {toml_string(_PROVIDER_ID)}\n"
        f"base_url = {toml_string(f'{shim_url}/v1')}\n"
        f"env_key = {toml_string(_KEY_ENV)}\n"
        f'wire_api = "responses"\n\n'
        f"[sandbox_workspace_write]\n"
        f"network_access = {str(runtime_config.network_access).lower()}\n"
    )
    with open(os.path.join(home, "config.toml"), "w", encoding="utf-8") as f:
        f.write(config)

    return home


def _prepare_workspace(
    runtime_config: CodexRuntimeConfig, ctx: "InvocationContext"
) -> str:
    """Resolve the filesystem Codex is given as its ``cwd``.

    The workspace is keyed by app/user/session/agent, so successive
    invocations of one session share it and it is never deleted at the end of
    a turn. Process-owned workspaces are removed by the ``atexit`` hook
    :func:`_ensure_session_workspace_root` registers and, while the process
    runs, by :func:`_reap_idle_workspaces`.

    An ADK tool that needs to write into this directory reads it back with
    :func:`veadk.runtime.codex.current_workspace`; see
    :mod:`veadk.runtime.codex.workspace` for why that is bound per tool call.

    A caller-supplied ``workspace_root`` is never reaped, because this runtime
    cannot tell its own session directories from whatever else the caller keeps
    there. **Cleaning it is therefore the caller's responsibility**: a
    long-lived server that sets ``workspace_root`` accumulates one directory
    per session indefinitely. Leave ``workspace_root`` unset to get the
    reaped, process-owned root instead.

    Args:
        runtime_config (CodexRuntimeConfig): Resolved runtime configuration.
        ctx (InvocationContext): The invocation being served.

    Returns:
        str: Absolute path to the workspace directory.
    """
    root = runtime_config.workspace_root
    if root and runtime_config.reuse_workspace:
        Path(root).mkdir(parents=True, exist_ok=True)
        return root

    session = getattr(ctx, "session", None)
    session_id = str(getattr(session, "id", "session"))
    scope = "\0".join(
        (
            str(getattr(session, "app_name", "")),
            str(getattr(session, "user_id", "")),
            session_id,
            str(getattr(getattr(ctx, "agent", None), "name", "")),
        )
    )
    digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:16]
    safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")[:32]
    base = Path(root or _ensure_session_workspace_root())
    base.mkdir(parents=True, exist_ok=True)
    workspace = base / f"{safe_id or 'session'}-{digest}"
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(workspace, 0o700)
    # Mark the session active so the reaper keeps it for another TTL window.
    os.utime(workspace)
    return str(workspace)


async def _maybe_reap_workspaces(runtime_config: CodexRuntimeConfig) -> None:
    """Run the idle-workspace reaper off the event loop, at most periodically.

    The reaper is all blocking syscalls — ``iterdir``, ``stat`` and recursive
    ``rmtree`` — and it used to run inline in :func:`_prepare_workspace`, before
    the invocation's first ``await``. In a server that stalled *every* other
    in-flight turn once per invocation. It now runs in a worker thread, no more
    than once per :data:`_WORKSPACE_REAP_INTERVAL_SECONDS`, and removes at most
    :data:`_WORKSPACE_REAP_MAX_PER_PASS` trees per pass.

    Only the process-owned root is ever reaped: a caller-supplied
    ``workspace_root`` may hold data this runtime does not own.

    Args:
        runtime_config (CodexRuntimeConfig): Resolved runtime configuration.
    """
    global _last_workspace_reap_at
    if runtime_config.workspace_root:
        return
    # Read, never create: with no root yet there is nothing to reap, and
    # materializing one here would reintroduce exactly the stray directory the
    # lazy root exists to avoid.
    root = _session_workspace_root
    if root is None:
        return
    now = time.monotonic()
    with _workspace_reap_lock:
        if now - _last_workspace_reap_at < _WORKSPACE_REAP_INTERVAL_SECONDS:
            return
        _last_workspace_reap_at = now
    try:
        await asyncio.to_thread(_reap_idle_workspaces, Path(root))
    except Exception:  # noqa: BLE001 - housekeeping must never fail a turn
        logger.warning("codex_workspace_reap_failed")


def _reap_idle_workspaces(base: Path) -> None:
    """Delete session workspaces untouched for the idle TTL.

    Best-effort: a workspace that cannot be inspected or removed is left in
    place rather than failing the invocation. Runs on a worker thread; see
    :func:`_maybe_reap_workspaces`.

    Args:
        base (Path): The process-owned session workspace root to scan.
    """
    cutoff = time.time() - _WORKSPACE_IDLE_TTL_SECONDS
    try:
        entries = list(base.iterdir())
    except OSError:
        return
    reaped = 0
    for entry in entries:
        if reaped >= _WORKSPACE_REAP_MAX_PER_PASS:
            logger.info(
                "codex_workspace_reap_truncated limit=%d", _WORKSPACE_REAP_MAX_PER_PASS
            )
            return
        try:
            if not entry.is_dir() or entry.stat().st_mtime >= cutoff:
                continue
        except OSError:
            continue
        shutil.rmtree(entry, ignore_errors=True)
        reaped += 1
        logger.info("codex_workspace_reaped workspace=%s", entry.name)


def _start_call_llm_span() -> "Span | None":
    """Open the ADK-shaped ``call_llm`` span for one Codex invocation.

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
        logger.warning("codex_trace_span_start_failed")
        return None


def _end_span(span: "Span | None") -> None:
    """End a span without ever failing the turn."""
    if span is None:
        return
    try:
        span.end()
    except Exception:  # noqa: BLE001
        logger.warning("codex_trace_span_end_failed")


def _emit_call_llm_telemetry(
    ctx: "InvocationContext",
    runtime_call: RuntimeLlmCall,
    llm_response: "LlmResponse",
    span: "Span | None",
) -> None:
    """Write one turn's model telemetry onto the ``call_llm`` span.

    Emitted exactly once per invocation - not once per backend HTTP call -
    because the evaluator reads the first span's prompt as the user input and
    the last span's completion as the final answer, and the telemetry layer
    accumulates tokens per span. Several spans would therefore surface Codex's
    internally built prompt as the user input and double-count usage.

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
            # `trace_call_llm` annotates `span` as `opentelemetry.sdk.trace.Span`,
            # but it only ever uses the API-level surface on it (`set_attribute`,
            # `.context`) and assigns `trace.get_current_span()` - an API span -
            # into the same parameter on its own `span is None` path. The API
            # type is what actually arrives here: with no SDK TracerProvider
            # configured, ADK's tracer is a `ProxyTracer` returning a
            # `NonRecordingSpan`, which is not an SDK `Span`. Keep the accurate
            # annotation and ignore the over-narrow one upstream.
            trace_call_llm(
                ctx,
                runtime_call.model_response_event.id,
                runtime_call.llm_request,
                llm_response,
                span,  # type: ignore[arg-type]
            )
    except Exception:  # noqa: BLE001
        logger.warning(
            "codex_trace_call_llm_failed invocation_id=%s",
            getattr(ctx, "invocation_id", ""),
        )


def _error_llm_response(error: BaseException) -> "LlmResponse":
    """Build the response recorded on the span when a turn fails."""
    from google.adk.models.llm_response import LlmResponse

    return LlmResponse(
        error_code=type(error).__name__,
        error_message=str(error) or type(error).__name__,
    )


def _charge_llm_call(ctx: "InvocationContext") -> None:
    """Charge one backend model call to the invocation's ADK call budget.

    ADK enforces ``RunConfig.max_llm_calls`` solely from
    ``InvocationContext.increment_llm_call_count``, which only its own
    ``BaseLlmFlow`` calls. The Codex runtime replaces that flow, so without
    this hook ``max_llm_calls`` - and ``Runner``'s ``LlmCallsLimitExceededError``
    handling - never fire for ``runtime="codex"``.

    It is handed to the shim as ``register_turn(on_model_call=...)`` so every
    backend call Codex's inner loop makes is charged, not just one per turn.
    The shim serves those calls on its own task, so a raise cannot propagate
    here: it is recorded on the turn state, returned to Codex as a ``429``, and
    re-raised by ``run_async`` once the turn ends.

    Args:
        ctx (InvocationContext): The invocation being served.

    Raises:
        google.adk.agents.invocation_context.LlmCallsLimitExceededError: When
            the invocation exceeds ``RunConfig.max_llm_calls``.
    """
    increment = getattr(ctx, "increment_llm_call_count", None)
    if callable(increment):
        increment()


def _approval_mode(config: CodexRuntimeConfig) -> ApprovalMode:
    return (
        ApprovalMode.auto_review
        if config.approval_mode == "auto_review"
        else ApprovalMode.deny_all
    )


def _sandbox(config: CodexRuntimeConfig) -> Sandbox:
    return {
        "read_only": Sandbox.read_only,
        "workspace_write": Sandbox.workspace_write,
        "full_access": Sandbox.full_access,
    }[config.sandbox]


def _build_codex_input(
    prompt: str,
    llm_request: "LlmRequest",
    workspace: str,
    *,
    turn_marker: str = "",
) -> list[object]:
    """Build the Codex turn input, tagging it with the shim's turn marker.

    The marker is appended to the prompt text (a single machine-shaped line, in
    the same register as Codex's own ``<environment_context>`` blocks) rather
    than sent as an extra item: the Codex prompt is the one channel guaranteed
    to reach the model request intact, and its text survives Codex's own
    compaction, which rebuilds history from user-message text alone.
    """
    if turn_marker:
        prompt = f"{prompt}\n\n<veadk_turn>{turn_marker}</veadk_turn>"
    items: list[object] = [TextInput(prompt)]
    for attachment in build_input_attachments_from_llm_request(llm_request, workspace):
        kind = attachment["kind"]
        value = attachment["value"]
        if kind == "local_image":
            items.append(LocalImageInput(value))
        elif kind == "remote_image":
            items.append(ImageInput(value))
        else:
            items.append(MentionInput(attachment["name"], value))
    return items


def _scope_event(event: "Event", ctx: "InvocationContext") -> None:
    event.branch = getattr(ctx, "branch", None)
    event.isolation_scope = getattr(ctx, "isolation_scope", None)


def _uses_adk_transfer_scheduler(ctx: "InvocationContext") -> bool:
    """Whether ADK's outer workflow scheduler should run transfer targets."""

    return is_adk_gte("2.0.0") and getattr(ctx, "_event_queue", None) is not None
