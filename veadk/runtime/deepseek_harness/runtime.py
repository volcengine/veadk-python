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

"""DeepSeek Harness runtime for VeADK."""

from __future__ import annotations

import asyncio
import atexit
import hashlib
import json
import shutil
import tempfile
import threading
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from deepseek_harness import (  # type: ignore[import-not-found]
    DeepSeekHarness,
    DeepSeekHarnessConfig,
    RunResult,
)
from google.adk.events.event import Event

from veadk.runtime.agent_transfer import (
    append_transfer_instructions,
    build_transfer_tool,
    get_transfer_targets,
    run_transferred_agent,
    transfer_agent_name,
)
from veadk.runtime.base_runtime import BaseRuntime
from veadk.runtime.deepseek_harness.config import DeepSeekHarnessRuntimeConfig
from veadk.runtime.deepseek_harness.events import DeepSeekHarnessEventTranslator
from veadk.runtime.deepseek_harness.skills import (
    DeepSeekHarnessSkillPatch,
    DeepSeekHarnessSkillRegistration,
)
from veadk.runtime.deepseek_harness.tool_runtime import (
    DeepSeekHarnessToolRegistration,
    DeepSeekHarnessToolServer,
)
from veadk.runtime.deepseek_harness.translate import (
    build_prompt,
    response_to_llm_response,
)
from veadk.runtime.model_callbacks import (
    build_runtime_llm_request,
    llm_response_to_event,
    run_after_model_callbacks,
    run_before_model_callbacks,
    run_on_model_error_callbacks,
)
from veadk.runtime.piagent.tools_bridge import (
    PiToolBundle,
    add_tool_to_bundle,
    build_executable_tools,
    close_toolsets,
    sync_bundle_to_tools_dict,
)
from veadk.consts import DEFAULT_MODEL_AGENT_NAME
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.models.llm_response import LlmResponse
    from opentelemetry.trace import Span

    from veadk.agent import Agent
    from veadk.runtime.model_callbacks import RuntimeLlmCall

logger = get_logger(__name__)

_MANAGERS: dict[_ManagerKey, _HarnessManager] = {}
_MANAGERS_LOCK = threading.Lock()
_cleanup_registered = False
_DSH_HOME_ROOT_PREFIX = "veadk-dsh-homes-"
_dsh_home_root: str | None = None
_dsh_home_root_lock = threading.Lock()
_DSH_PROVIDER_ALIASES = {
    "ark": "deepseek-official",
    "openai": "deepseek-official",
    "openai-compatible": "deepseek-official",
    "third-party": "deepseek-official",
    "volcengine": "deepseek-official",
    "volcengine-ark": "deepseek-official",
}


class DeepSeekHarnessRuntime(BaseRuntime):
    """Run an agent invocation through the DeepSeek Harness SDK."""

    name = "dsh"

    async def run_async(
        self, agent: Agent, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        config = DeepSeekHarnessRuntimeConfig.from_agent(agent)
        model = _resolve_model(agent, config)
        api_base = config.base_url or getattr(agent, "model_api_base", None)
        api_key = config.api_key or getattr(agent, "model_api_key", None)

        tool_bundle = None
        event_queue: asyncio.Queue[object] = asyncio.Queue()
        call_llm_span = None
        telemetry_emitted = False
        turn_started = time.monotonic()

        def _emit_telemetry_once(
            llm_response: LlmResponse,
            *,
            status: str,
        ) -> None:
            nonlocal telemetry_emitted
            if telemetry_emitted:
                return
            telemetry_emitted = True
            _emit_call_llm_telemetry(
                ctx,
                runtime_call,
                llm_response,
                call_llm_span,
                status=status,
                duration_ms=(time.monotonic() - turn_started) * 1000,
            )

        async def _emit_tool_event(event: Event) -> None:
            await event_queue.put(event)

        try:
            tool_bundle = await build_executable_tools(
                agent,
                ctx,
                event_sink=_emit_tool_event,
                runtime_label="dsh",
            )
            transfer_targets = get_transfer_targets(agent)
            if transfer_targets:
                add_tool_to_bundle(
                    tool_bundle,
                    build_transfer_tool(transfer_targets),
                    ctx,
                    seen={spec.name for spec in tool_bundle.specs},
                    event_sink=_emit_tool_event,
                    runtime_label="dsh",
                )

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
            call_llm_span = _start_call_llm_span()
            if short_circuit is not None:
                _emit_telemetry_once(short_circuit, status="short_circuit")
                yield llm_response_to_event(
                    runtime_call.llm_request,
                    short_circuit,
                    runtime_call.model_response_event,
                )
                return
            callback_model = runtime_call.llm_request.model
            if not isinstance(callback_model, str) or not callback_model.strip():
                raise ValueError(
                    "DeepSeek Harness before_model_callback must select a "
                    "non-empty model name."
                )
            model = callback_model.strip()

            sync_bundle_to_tools_dict(
                tool_bundle,
                runtime_call.llm_request.tools_dict,
                ctx,
                event_sink=_emit_tool_event,
                runtime_label="dsh",
            )
            if "transfer_to_agent" in runtime_call.llm_request.tools_dict:
                append_transfer_instructions(
                    agent,
                    runtime_call.llm_request,
                    transfer_targets,
                )

            effective = _EffectiveConfig.from_config(
                config,
                model=model,
                base_url=api_base,
                api_key=api_key,
            )
            tool_registration = DeepSeekHarnessToolRegistration.from_bundle(tool_bundle)
            skill_registration = DeepSeekHarnessSkillRegistration.from_agent(agent)
            manager = await _get_manager(
                effective,
                tool_registration,
                skill_registration,
            )
            prompt = build_prompt(runtime_call)
            session_id = _dsh_session_id(agent, ctx)
            logger.info(
                "deepseek_harness_runtime_start invocation_id=%s model=%s provider=%s "
                "dsh_provider=%s session_id=%s tools=%s",
                ctx.invocation_id,
                model,
                config.provider,
                effective.provider,
                session_id,
                [spec.name for spec in tool_registration.specs],
            )

            loop = asyncio.get_running_loop()

            def _on_notification(notification: object) -> None:
                loop.call_soon_threadsafe(event_queue.put_nowait, notification)

            translator = DeepSeekHarnessEventTranslator(
                author=agent.name,
                invocation_id=ctx.invocation_id,
                bridged_tool_names=set(tool_bundle.executors),
            )
            run_task = asyncio.create_task(
                manager.run(
                    prompt,
                    session_id=session_id,
                    tool_bundle=tool_bundle,
                    on_notification=_on_notification,
                )
            )
            transfer_requested = False
            transfer_event = None
            while not run_task.done() or not event_queue.empty():
                try:
                    queued = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                async for emitted in _events_from_queued(queued, translator):
                    yield emitted
                    if transfer_agent_name(emitted):
                        transfer_requested = True
                        transfer_event = emitted

            result = await run_task
            for event in translator.result_events_to_adk_events(result.events or []):
                yield event
                if transfer_agent_name(event):
                    transfer_requested = True
                    transfer_event = event

            # Drain any Python-side tool events that arrived between the last
            # queue check and the SDK result settlement.
            while not event_queue.empty():
                queued = event_queue.get_nowait()
                async for emitted in _events_from_queued(queued, translator):
                    yield emitted
                    if transfer_agent_name(emitted):
                        transfer_requested = True
                        transfer_event = emitted

            if transfer_requested:
                if transfer_event is not None:
                    async for transferred_event in run_transferred_agent(
                        ctx, transfer_event
                    ):
                        yield transferred_event
                return

            _charge_llm_call(ctx)

            llm_response = response_to_llm_response(result.final_response)
            llm_response = await run_after_model_callbacks(
                agent,
                ctx,
                llm_response,
                runtime_call.model_response_event,
            )
            _emit_telemetry_once(llm_response, status="completed")
            yield llm_response_to_event(
                runtime_call.llm_request,
                llm_response,
                runtime_call.model_response_event,
            )
        except asyncio.CancelledError:
            if "run_task" in locals():
                run_task.cancel()
                await asyncio.gather(run_task, return_exceptions=True)
            raise
        except Exception as e:
            if "runtime_call" not in locals():
                raise
            fallback = await run_on_model_error_callbacks(
                agent,
                ctx,
                e,
                runtime_call.llm_request,
                runtime_call.model_response_event,
            )
            if fallback is not None:
                _emit_telemetry_once(fallback, status="error_callback")
                yield llm_response_to_event(
                    runtime_call.llm_request,
                    fallback,
                    runtime_call.model_response_event,
                )
                return
            _emit_telemetry_once(_error_llm_response(e), status="failed")
            raise
        finally:
            _end_span(call_llm_span)
            if tool_bundle is not None:
                await close_toolsets(
                    tool_bundle.opened_toolsets,
                    runtime_label="dsh",
                )


async def _events_from_queued(
    queued: object,
    translator: DeepSeekHarnessEventTranslator,
) -> AsyncGenerator[Event, None]:
    if isinstance(queued, Event):
        yield queued
        return
    for event in translator.notification_to_adk_events(queued):
        yield event


@dataclass(frozen=True)
class _EffectiveConfig:
    provider: str
    model: str
    reasoning_effort: str | None
    max_tokens: int | None
    cwd: str | None
    runtime_cwd: str | None
    dsh_bin: str | None
    profile: str
    patches: tuple[str, ...]
    dsh_home: str | None
    env_items: tuple[tuple[str, str], ...]
    initialize_timeout_seconds: float
    request_timeout_seconds: float | None
    shutdown_timeout_seconds: float | None
    base_url: str | None
    api_key: str | None

    @classmethod
    def from_config(
        cls,
        config: DeepSeekHarnessRuntimeConfig,
        *,
        model: str,
        base_url: str | None,
        api_key: str | None,
    ) -> _EffectiveConfig:
        return cls(
            provider=_dsh_provider(config.provider),
            model=model,
            reasoning_effort=config.reasoning_effort,
            max_tokens=config.max_tokens,
            cwd=config.cwd,
            runtime_cwd=config.runtime_cwd,
            dsh_bin=config.dsh_bin,
            profile=config.profile,
            patches=config.patches,
            dsh_home=config.dsh_home,
            env_items=tuple(sorted(config.env.items())),
            initialize_timeout_seconds=config.initialize_timeout_seconds,
            request_timeout_seconds=config.request_timeout_seconds,
            shutdown_timeout_seconds=config.shutdown_timeout_seconds,
            base_url=base_url,
            api_key=api_key,
        )


@dataclass(frozen=True)
class _ManagerKey:
    digest: str


class _HarnessManager:
    def __init__(
        self,
        effective: _EffectiveConfig,
        dsh_home: str,
        tool_server: DeepSeekHarnessToolServer | None,
        skill_patch: DeepSeekHarnessSkillPatch | None,
    ) -> None:
        self.effective = effective
        self.dsh_home = dsh_home
        self._tool_server = tool_server
        self._skill_patch = skill_patch
        self._harness = DeepSeekHarness(
            _sdk_config(effective, dsh_home, tool_server, skill_patch)
        )
        self._lock = asyncio.Lock()
        self._closed = False

    async def run(
        self,
        prompt: str,
        *,
        session_id: str,
        tool_bundle: PiToolBundle | None = None,
        on_notification: Callable[[object], None] | None = None,
    ) -> RunResult:
        async with self._lock:
            if self._closed:
                self._harness = DeepSeekHarness(
                    _sdk_config(
                        self.effective,
                        self.dsh_home,
                        self._tool_server,
                        self._skill_patch,
                    )
                )
                self._closed = False
            if self._tool_server is not None and tool_bundle is not None:
                self._tool_server.activate(tool_bundle)
            thread_task = asyncio.create_task(
                asyncio.to_thread(
                    self._harness.run,
                    prompt,
                    session_id=session_id,
                    on_notification=on_notification,
                )
            )
            try:
                return await asyncio.shield(thread_task)
            except asyncio.CancelledError:
                try:
                    await asyncio.shield(thread_task)
                except Exception:  # noqa: BLE001 - preserve caller cancellation
                    pass
                raise
            finally:
                if self._tool_server is not None:
                    self._tool_server.deactivate()

    def close(self, *, dispose_tools: bool = False) -> None:
        self._closed = True
        self._harness.close()
        if dispose_tools and self._tool_server is not None:
            self._tool_server.close_now()
        if dispose_tools and self._skill_patch is not None:
            self._skill_patch.close()


async def _get_manager(
    effective: _EffectiveConfig,
    tool_registration: DeepSeekHarnessToolRegistration,
    skill_registration: DeepSeekHarnessSkillRegistration,
) -> _HarnessManager:
    _ensure_cleanup_registered()
    key = _manager_key(effective, tool_registration, skill_registration)
    with _MANAGERS_LOCK:
        manager = _MANAGERS.get(key)
        if manager is not None:
            skill_registration.close()
            return manager

    dsh_home = effective.dsh_home or _generated_dsh_home(key)
    tool_server = await DeepSeekHarnessToolServer.create(
        tool_registration,
        dsh_home=dsh_home,
    )
    skill_patch = DeepSeekHarnessSkillPatch.create(
        skill_registration,
        profile=effective.profile,
    )
    manager = _HarnessManager(effective, dsh_home, tool_server, skill_patch)

    with _MANAGERS_LOCK:
        existing = _MANAGERS.get(key)
        if existing is not None:
            manager.close(dispose_tools=True)
            return existing
        _MANAGERS[key] = manager
        return manager


def _manager_key(
    effective: _EffectiveConfig,
    tool_registration: DeepSeekHarnessToolRegistration,
    skill_registration: DeepSeekHarnessSkillRegistration,
) -> _ManagerKey:
    data = json.dumps(
        {
            "provider": effective.provider,
            "model": effective.model,
            "reasoning_effort": effective.reasoning_effort,
            "max_tokens": effective.max_tokens,
            "cwd": effective.cwd,
            "runtime_cwd": effective.runtime_cwd,
            "dsh_bin": effective.dsh_bin,
            "profile": effective.profile,
            "patches": effective.patches,
            "dsh_home": effective.dsh_home,
            "env_items": effective.env_items,
            "initialize_timeout_seconds": effective.initialize_timeout_seconds,
            "request_timeout_seconds": effective.request_timeout_seconds,
            "shutdown_timeout_seconds": effective.shutdown_timeout_seconds,
            "base_url": effective.base_url,
            "api_key_digest": _secret_digest(effective.api_key),
            "tool_registration_digest": tool_registration.digest,
            "skill_registration_digest": skill_registration.digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return _ManagerKey(hashlib.sha256(data.encode("utf-8")).hexdigest())


def _secret_digest(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sdk_config(
    effective: _EffectiveConfig,
    dsh_home: str,
    tool_server: DeepSeekHarnessToolServer | None,
    skill_patch: DeepSeekHarnessSkillPatch | None,
) -> DeepSeekHarnessConfig:
    patches = effective.patches
    if tool_server is not None:
        patches = (*patches, tool_server.patch_path)
    if skill_patch is not None:
        patches = (*patches, skill_patch.patch_path)
    return DeepSeekHarnessConfig(
        provider=effective.provider,
        model=effective.model,
        reasoning_effort=effective.reasoning_effort,
        max_tokens=effective.max_tokens,
        cwd=effective.cwd,
        runtime_cwd=effective.runtime_cwd,
        dsh_bin=effective.dsh_bin,
        profile=effective.profile,
        patches=patches,
        dsh_home=dsh_home,
        env=dict(effective.env_items),
        initialize_timeout_seconds=effective.initialize_timeout_seconds,
        request_timeout_seconds=effective.request_timeout_seconds,
        shutdown_timeout_seconds=effective.shutdown_timeout_seconds,
        base_url=effective.base_url,
        api_key=effective.api_key,
    )


def _generated_dsh_home(key: _ManagerKey) -> str:
    root = _ensure_dsh_home_root()
    path = Path(root) / key.digest[:16]
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _ensure_dsh_home_root() -> str:
    global _dsh_home_root
    with _dsh_home_root_lock:
        if _dsh_home_root is None:
            root = tempfile.mkdtemp(prefix=_DSH_HOME_ROOT_PREFIX)
            _dsh_home_root = root
        return _dsh_home_root


def _ensure_cleanup_registered() -> None:
    global _cleanup_registered
    with _MANAGERS_LOCK:
        if _cleanup_registered:
            return
        atexit.register(_cleanup_runtime_state)
        _cleanup_registered = True


def _cleanup_runtime_state() -> None:
    global _cleanup_registered
    with _MANAGERS_LOCK:
        managers = list(_MANAGERS.values())
        _MANAGERS.clear()
        _cleanup_registered = False
    for manager in managers:
        try:
            manager.close(dispose_tools=True)
        except Exception:  # noqa: BLE001, S110 - best-effort shutdown
            pass
    if _dsh_home_root:
        shutil.rmtree(_dsh_home_root, ignore_errors=True)


def _resolve_model(agent: Agent, config: DeepSeekHarnessRuntimeConfig) -> str:
    if config.model:
        return config.model
    model_name = getattr(agent, "model_name", None)
    if isinstance(model_name, list):
        if model_name:
            return str(model_name[0])
    elif model_name:
        return str(model_name)
    model = getattr(getattr(agent, "model", None), "model", None)
    if isinstance(model, str) and "/" in model:
        return model.split("/", 1)[1]
    if isinstance(model, str) and model:
        return model
    return DEFAULT_MODEL_AGENT_NAME


def _dsh_provider(provider: str) -> str:
    normalized = provider.strip()
    if not normalized:
        return "deepseek-official"
    return _DSH_PROVIDER_ALIASES.get(normalized.lower(), normalized)


def _dsh_session_id(agent: Agent, ctx: InvocationContext) -> str:
    session = getattr(ctx, "session", None)
    payload = {
        "app_name": getattr(session, "app_name", None)
        or getattr(session, "appName", None)
        or "",
        "user_id": getattr(session, "user_id", None)
        or getattr(session, "userId", None)
        or "",
        "session_id": getattr(session, "id", None) or "",
        "agent": getattr(agent, "name", None) or "",
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "veadk-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _start_call_llm_span() -> Span | None:
    """Open the ADK-shaped ``call_llm`` span for one DSH invocation."""
    try:
        from google.adk.telemetry.tracing import tracer

        return tracer.start_span("call_llm")
    except Exception:  # noqa: BLE001
        logger.warning("deepseek_harness_trace_span_start_failed")
        return None


def _end_span(span: Span | None) -> None:
    if span is None:
        return
    try:
        span.end()
    except Exception:  # noqa: BLE001
        logger.warning("deepseek_harness_trace_span_end_failed")


def _emit_call_llm_telemetry(
    ctx: InvocationContext,
    runtime_call: RuntimeLlmCall,
    llm_response: LlmResponse,
    span: Span | None,
    *,
    status: str,
    duration_ms: float,
) -> None:
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
                span,  # type: ignore[arg-type]
            )
        span.set_attribute("veadk.deepseek_harness.runtime", "dsh")
        span.set_attribute("veadk.deepseek_harness.status", status)
        span.set_attribute("veadk.deepseek_harness.duration_ms", duration_ms)
    except Exception:  # noqa: BLE001
        logger.warning(
            "deepseek_harness_trace_call_llm_failed invocation_id=%s",
            getattr(ctx, "invocation_id", ""),
        )


def _error_llm_response(error: BaseException) -> LlmResponse:
    from google.adk.models.llm_response import LlmResponse

    return LlmResponse(
        error_code=type(error).__name__,
        error_message=str(error) or type(error).__name__,
    )


def _charge_llm_call(ctx: InvocationContext) -> None:
    increment = getattr(ctx, "increment_llm_call_count", None)
    if callable(increment):
        increment()


__all__ = ["DeepSeekHarnessRuntime"]
