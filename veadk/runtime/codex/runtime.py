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
import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator

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
    TurnCompletedNotification,
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
    notification_to_events,
)
from veadk.runtime.model_callbacks import (
    build_runtime_llm_request,
    final_events_to_llm_response,
    has_after_model_callbacks,
    is_final_model_text_event,
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

    from veadk.agent import Agent

logger = get_logger(__name__)

_PROVIDER_ID = "veadk"
_KEY_ENV = "VEADK_CODEX_API_KEY"
_QUEUE_DONE = object()
_SESSION_WORKSPACE_ROOT = tempfile.mkdtemp(prefix="veadk-codex-workspaces-")
atexit.register(shutil.rmtree, _SESSION_WORKSPACE_ROOT, ignore_errors=True)


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
        workspace, cleanup_workspace = _prepare_workspace(runtime_config, ctx)
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

        event_queue: asyncio.Queue[object] = asyncio.Queue()
        turn_token: str | None = None
        run_started_at = time.monotonic()
        run_status = "failed"
        use_adk_transfer_scheduler = _uses_adk_transfer_scheduler(ctx)

        async def _emit_tool_event(event: "Event") -> None:
            await event_queue.put(event)

        def _raise_shim_turn_error() -> None:
            if turn_token is None:
                return
            turn_error = shim.pop_turn_error(turn_token)
            if turn_error is not None:
                raise turn_error

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
            if "tool_bundle" in locals():
                await close_toolsets(tool_bundle.opened_toolsets)
            shutil.rmtree(codex_home, ignore_errors=True)
            if cleanup_workspace:
                shutil.rmtree(workspace, ignore_errors=True)
            raise

        try:
            # Persist resumed confirmation responses before constructing history,
            # so Codex sees the completed/rejected tool result exactly once.
            for event in resumed_events:
                _scope_event(event, ctx)
                run_status = "transferred" if transfer_agent_name(event) else run_status
                yield event
                if transfer_agent_name(event):
                    if not use_adk_transfer_scheduler:
                        async for transferred_event in run_transferred_agent(
                            ctx, event
                        ):
                            _scope_event(transferred_event, ctx)
                            yield transferred_event
                    run_status = "transferred"
                    await close_toolsets(tool_bundle.opened_toolsets)
                    shutil.rmtree(codex_home, ignore_errors=True)
                    if cleanup_workspace:
                        shutil.rmtree(workspace, ignore_errors=True)
                    logger.info(
                        "codex_runtime_complete invocation_id=%s status=%s duration_ms=%d",
                        ctx.invocation_id,
                        run_status,
                        round((time.monotonic() - run_started_at) * 1000),
                    )
                    return

            runtime_call = await build_runtime_llm_request(
                agent,
                ctx,
                model=model,
                tools_dict=tool_bundle.tools,
            )
            append_transfer_instructions(
                agent,
                runtime_call.llm_request,
                transfer_targets,
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
                await close_toolsets(tool_bundle.opened_toolsets)
                shutil.rmtree(codex_home, ignore_errors=True)
                if cleanup_workspace:
                    shutil.rmtree(workspace, ignore_errors=True)
                run_status = "completed"
                logger.info(
                    "codex_runtime_complete invocation_id=%s status=%s duration_ms=%d",
                    ctx.invocation_id,
                    run_status,
                    round((time.monotonic() - run_started_at) * 1000),
                )
                yield event
                return

            sync_bundle_to_tools_dict(
                tool_bundle,
                runtime_call.llm_request.tools_dict,
                ctx,
                event_sink=_emit_tool_event,
                timeout_seconds=runtime_config.tool_timeout_seconds,
            )
            turn_token = shim.register_turn(
                tool_bundle.specs,
                tool_bundle.executors,
                max_tool_iterations=runtime_config.max_tool_iterations,
                invocation_id=ctx.invocation_id,
                before_model_call=ctx.increment_llm_call_count,
            )

            # Keep privileged instructions out of the user transcript. The SDK
            # exposes native base/developer instruction channels.
            prompt = build_prompt_from_llm_request(runtime_call.llm_request)
            developer_instructions = system_instruction_to_text(
                runtime_call.llm_request.config.system_instruction
            )
            input_items = _build_codex_input(
                prompt, runtime_call.llm_request, workspace
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
            if turn_token is not None:
                shim.unregister_turn(turn_token)
            await close_toolsets(tool_bundle.opened_toolsets)
            shutil.rmtree(codex_home, ignore_errors=True)
            if cleanup_workspace:
                shutil.rmtree(workspace, ignore_errors=True)
            raise
        turn = None
        pump: asyncio.Task[None] | None = None
        try:
            async with AsyncCodex(config=sdk_config) as codex:
                thread = await codex.thread_start(
                    model=model,
                    model_provider=_PROVIDER_ID,
                    base_instructions=runtime_call.base_instructions or None,
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

                async def _pump_codex() -> None:
                    active_tool_items: set[str] = set()
                    try:
                        async for note in stream:
                            payload = note.payload
                            payload_turn_id = getattr(payload, "turn_id", None)
                            if isinstance(payload, TurnCompletedNotification):
                                payload_turn_id = payload.turn.id
                            if payload_turn_id and payload_turn_id != turn.id:
                                continue
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
                                    logger.info(
                                        "codex_token_usage invocation_id=%s usage=%s",
                                        ctx.invocation_id,
                                        event.custom_metadata.get("token_usage"),
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
                buffer_final_text = has_after_model_callbacks(agent, ctx)
                final_text_events: list[Event] = []
                transfer_requested = False
                deferred_transfer_event: Event | None = None
                while True:
                    queued = await event_queue.get()
                    if queued is _QUEUE_DONE:
                        break
                    if isinstance(queued, BaseException):
                        raise queued
                    event = queued  # type: ignore[assignment]
                    transfer_target = transfer_agent_name(event)
                    if transfer_target and use_adk_transfer_scheduler:
                        transfer_requested = True
                        run_status = "transferred"
                        final_text_events.clear()
                        deferred_transfer_event = event
                        continue
                    if buffer_final_text and is_final_model_text_event(
                        event, agent.name
                    ):
                        final_text_events.append(event)
                        continue
                    yield event
                    if transfer_target:
                        transfer_requested = True
                        final_text_events.clear()
                        async for transferred_event in run_transferred_agent(
                            ctx, event
                        ):
                            _scope_event(transferred_event, ctx)
                            yield transferred_event
                        run_status = "transferred"
                        break
                if transfer_requested:
                    await pump
                    _raise_shim_turn_error()
                    if deferred_transfer_event is not None:
                        yield deferred_transfer_event
                    return
                await pump
                _raise_shim_turn_error()
                if final_text_events:
                    llm_response = final_events_to_llm_response(final_text_events)
                    llm_response = await run_after_model_callbacks(
                        agent,
                        ctx,
                        llm_response,
                        runtime_call.model_response_event,
                    )
                    event = llm_response_to_event(
                        runtime_call.llm_request,
                        llm_response,
                        runtime_call.model_response_event,
                    )
                    _scope_event(event, ctx)
                    yield event
                run_status = "completed"
        except asyncio.CancelledError:
            if run_status != "transferred":
                run_status = "cancelled"
            if turn is not None and run_status != "transferred":
                try:
                    await turn.interrupt()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "codex_interrupt_failed invocation_id=%s",
                        ctx.invocation_id,
                    )
            raise
        except BaseException as e:
            logger.error(
                "codex_runtime_failed invocation_id=%s error_type=%s",
                ctx.invocation_id,
                type(e).__name__,
            )
            _raise_shim_turn_error()
            if isinstance(e, Exception) and "runtime_call" in locals():
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
                    yield event
                    run_status = "completed"
                    return
            raise
        finally:
            if pump is not None and not pump.done():
                pump.cancel()
                await asyncio.gather(pump, return_exceptions=True)
            if turn_token is not None:
                shim.unregister_turn(turn_token)
            await close_toolsets(tool_bundle.opened_toolsets)
            shutil.rmtree(codex_home, ignore_errors=True)
            if cleanup_workspace:
                shutil.rmtree(workspace, ignore_errors=True)
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
        f"disable_response_storage = true\n"
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
) -> tuple[str, bool]:
    root = runtime_config.workspace_root
    if root and runtime_config.reuse_workspace:
        Path(root).mkdir(parents=True, exist_ok=True)
        return root, False

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
    base = Path(root or _SESSION_WORKSPACE_ROOT)
    base.mkdir(parents=True, exist_ok=True)
    workspace = base / f"{safe_id or 'session'}-{digest}"
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(workspace, 0o700)
    return str(workspace), False


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
    prompt: str, llm_request: "LlmRequest", workspace: str
) -> list[object]:
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
