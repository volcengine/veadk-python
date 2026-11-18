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

"""Keep VeADK trace contracts across ADK telemetry generations."""

import functools
import sys
from contextlib import (
    AbstractAsyncContextManager,
    AsyncExitStack,
    ExitStack,
    asynccontextmanager,
    contextmanager,
)
from contextvars import ContextVar
from typing import Callable, cast

from opentelemetry import context as context_api
from opentelemetry import trace
from packaging.version import Version

from veadk.tracing.telemetry.telemetry import (
    trace_call_llm,
    trace_send_data,
    trace_tool_call,
)
from veadk.utils.adk_compat import get_adk_version
from veadk.utils.logger import get_logger

logger = get_logger(__name__)
_SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION = "suppress_language_model_instrumentation"
_opening_adk_scope = ContextVar("veadk_opening_adk_scope", default=False)


@contextmanager
def _scope_creation():
    token = _opening_adk_scope.set(True)
    try:
        yield
    finally:
        _opening_adk_scope.reset(token)


def _scope_context(otel_context, key):
    # ADK resumes each generator under this value, not on_start's ambient context.
    span = trace.get_current_span(otel_context)
    otel_context = context_api.set_value(key, span, context=otel_context)
    return context_api.set_value(
        _SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION, True, context=otel_context
    )


@contextmanager
def _legacy_scope(key):
    # Restore before ADK closes its span; processor on_end runs too late.
    token = context_api.attach(_scope_context(context_api.get_current(), key))
    try:
        yield
    finally:
        context_api.detach(token)


def _patch_scope_contexts() -> None:
    from google.adk.telemetry import _instrumentation, tracing

    original_invocation = _instrumentation.record_invocation
    if getattr(original_invocation, "_veadk_scope_patch", False):
        return
    original_agent = _instrumentation.record_agent_invocation
    original_model = getattr(tracing, "_start_call_llm_span", None)
    explicit_context = get_adk_version() >= Version("2.12.0")

    @contextmanager
    @functools.wraps(original_invocation)
    def record_invocation(*args, **kwargs):
        with ExitStack() as stack:
            with _scope_creation():
                result = stack.enter_context(original_invocation(*args, **kwargs))
            if result is None:
                stack.enter_context(_legacy_scope("invocation_span_instance"))
                yield result
                return
            # ADK 2.14 also returns the workflow entrypoint's scope.
            otel_context = result[0] if isinstance(result, tuple) else result
            otel_context = _scope_context(otel_context, "invocation_span_instance")
            yield (
                (otel_context, *result[1:])
                if isinstance(result, tuple)
                else otel_context
            )

    @asynccontextmanager
    @functools.wraps(original_agent)
    async def record_agent_invocation(*args, **kwargs):
        async with AsyncExitStack() as stack:
            with _scope_creation():
                scope = await stack.enter_async_context(original_agent(*args, **kwargs))
            if explicit_context:
                scope.otel_context = _scope_context(
                    scope.otel_context, "agent_run_span_instance"
                )
            else:
                stack.enter_context(_legacy_scope("agent_run_span_instance"))
            yield scope

    setattr(record_invocation, "_veadk_scope_patch", True)
    _instrumentation.record_invocation = record_invocation
    _instrumentation.record_agent_invocation = record_agent_invocation
    if callable(original_model):
        from google.adk.flows.llm_flows.core import _model_call

        @functools.wraps(original_model)
        def start_call_llm_span(caller_context):
            span = original_model(caller_context)
            if span is None and context_api.get_value(
                _SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION, context=caller_context
            ):
                # VeADK exporters index model calls even under ADK schema v2.
                span = tracing.tracer.start_span("call_llm", context=caller_context)
            return span

        tracing._start_call_llm_span = start_call_llm_span
        setattr(_model_call, "_start_call_llm_span", start_call_llm_span)


def patch_google_adk_telemetry() -> None:
    from veadk.utils.patches import _iter_loaded_attrs

    trace_functions = {
        "trace_tool_call": trace_tool_call,
        "trace_call_llm": trace_call_llm,
        "trace_send_data": trace_send_data,
    }

    for mod_name, mod in tuple(sys.modules.items()):
        if mod_name.startswith("google.adk"):
            for var_name, var in _iter_loaded_attrs(mod):
                if var_name in trace_functions and isinstance(var, Callable):
                    setattr(mod, var_name, trace_functions[var_name])
                    logger.debug(
                        f"Patch {mod_name} {var_name} with {trace_functions[var_name]}"
                    )

    # Supported ADK releases emit a nested ``generate_content`` span in
    # addition to ``call_llm``. Newer releases also record the standard GenAI
    # token metrics from the same path. VeADK owns both while its invocation
    # context is active, so suppress them through the capability exposed by
    # each ADK generation. Keep native telemetry unchanged outside VeADK.
    try:
        from google.adk.telemetry import tracing as adk_tracing
        from opentelemetry import context as context_api

        telemetry_gate = getattr(adk_tracing, "_should_emit_native_telemetry", None)
        if callable(telemetry_gate) and not getattr(
            telemetry_gate, "_veadk_suppression_wrapped", False
        ):

            def should_emit_native_telemetry(agent, *args, **kwargs):
                if context_api.get_value(_SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION):
                    return False
                return telemetry_gate(agent, *args, **kwargs)

            setattr(should_emit_native_telemetry, "_veadk_suppression_wrapped", True)
            adk_tracing._should_emit_native_telemetry = should_emit_native_telemetry
            logger.debug("Patch ADK native telemetry suppression for VeADK runs.")
        elif not callable(telemetry_gate):
            # ADK 1.34-2.1 has no native-telemetry gate. Its LLM flow enters
            # this context manager directly, so suppress that span only while
            # VeADK owns the surrounding call_llm telemetry.
            use_inference_span = getattr(adk_tracing, "use_inference_span", None)
            if callable(use_inference_span) and not getattr(
                use_inference_span, "_veadk_suppression_wrapped", False
            ):
                inference_scope = cast(
                    Callable[..., AbstractAsyncContextManager], use_inference_span
                )

                @asynccontextmanager
                async def veadk_use_inference_span(*args, **kwargs):
                    if context_api.get_value(_SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION):
                        yield None
                        return
                    async with inference_scope(*args, **kwargs) as span:
                        yield span

                setattr(veadk_use_inference_span, "_veadk_suppression_wrapped", True)
                adk_tracing.use_inference_span = veadk_use_inference_span
                logger.debug(
                    "Patch legacy ADK inference span suppression for VeADK runs."
                )
    except (ImportError, AttributeError) as e:
        # Older ADK releases do not expose native inference telemetry.
        logger.debug(f"Skip ADK native telemetry suppression patch: {e}")

    if get_adk_version() >= Version("2.7.0"):
        _patch_scope_contexts()
