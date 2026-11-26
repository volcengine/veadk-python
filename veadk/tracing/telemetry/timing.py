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

"""Native request spans and standard per-SDK-request streaming telemetry."""

from __future__ import annotations

import asyncio
import functools
import math
import time
from collections.abc import AsyncGenerator, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import TracebackType
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, StatusCode
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from veadk.tracing.telemetry import portal_metrics
from veadk.utils.logger import get_logger, safe_info

logger = get_logger(__name__)
_REQUEST_SPAN: ContextVar[Span | None] = ContextVar("veadk_request_span", default=None)


def current_request_span() -> Span | None:
    return _REQUEST_SPAN.get()


@contextmanager
def bind_request_span(span: Span) -> Iterator[Span]:
    token = _REQUEST_SPAN.set(span)
    try:
        with trace.use_span(
            span, record_exception=False, set_status_on_exception=False
        ):
            yield span
    finally:
        _REQUEST_SPAN.reset(token)


def _record_error(span: Span, error: BaseException, fallback: str) -> None:
    if isinstance(error, GeneratorExit):
        return
    error_type = (
        "timeout"
        if isinstance(error, TimeoutError)
        else "cancelled"
        if isinstance(error, asyncio.CancelledError)
        else fallback
    )
    span.set_attribute("error.type", error_type)
    span.set_status(StatusCode.ERROR)


async def with_request_timing(events: AsyncGenerator, span: Span) -> AsyncGenerator:
    """Attach request context only while advancing or closing the producer."""
    try:
        while True:
            with bind_request_span(span):
                try:
                    event = await anext(events)
                except StopAsyncIteration:
                    return
            yield event
    finally:
        with bind_request_span(span):
            await events.aclose()


def timed_runner(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> AsyncGenerator:
        inherited = current_request_span()
        span = (
            inherited
            if inherited is not None
            else trace.get_tracer(__name__).start_span("runner_request")
        )
        events = with_request_timing(func(*args, **kwargs), span)
        try:
            try:
                async for event in events:
                    yield event
            finally:
                await events.aclose()
        except BaseException as error:
            if inherited is None:
                _record_error(span, error, "request_error")
            raise
        finally:
            if inherited is None:
                span.end()

    return wrapper


class RequestTimingMiddleware:
    """Represent the HTTP execution boundary using a native server span."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        span = trace.get_tracer(__name__).start_span(
            "http_request", kind=SpanKind.SERVER
        )

        async def traced_send(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] >= 500:
                span.set_attribute("error.type", "http_error")
                span.set_status(StatusCode.ERROR)
            await send(message)

        try:
            with bind_request_span(span):
                await self.app(scope, receive, traced_send)
        except BaseException as error:
            _record_error(span, error, "request_error")
            raise
        finally:
            span.end()


def install_request_timing(app: Any) -> None:
    if getattr(app.state, "_veadk_request_timing_installed", False):
        return
    app.add_middleware(RequestTimingMiddleware)
    app.state._veadk_request_timing_installed = True


class ModelTiming:
    """One SDK request, with its own native interval and first-output latch."""

    def __init__(self, *, streaming: bool, model: str) -> None:
        self.streaming = streaming
        self.model = str(model)
        self.first_token_time: int | None = None
        self._first_output_ns: int | None = None
        self._last_output_ns: int | None = None
        self._output_count = 0
        self._output_tokens: int | None = None
        self._output_types: set[str] = set()
        self._completed = False
        self._tpot_disabled = False
        self._ended = False
        self.start_time = time.time_ns()
        self._log_start_monotonic = time.monotonic()
        self.span = trace.get_tracer(__name__).start_span(
            "model_request",
            kind=SpanKind.CLIENT,
            start_time=self.start_time,
            attributes={
                "gen_ai.request.model": self.model,
                "gen_ai.span.kind": "llm",
                "gen_ai.request.stream": streaming,
            },
        )

    def __enter__(self) -> ModelTiming:
        return self

    def observe(self, output_type: str | None) -> None:
        if self._ended or not self.streaming or not output_type:
            return
        self._observe_tpot(output_type)
        if self.first_token_time is not None:
            return
        self.first_token_time = time.time_ns()
        duration = (self.first_token_time - self.start_time) / 1e9
        if duration < 0:
            logger.warning("Skipping TTFT because the wall clock moved backwards")
            return
        safe_info(
            logger,
            f"[llm-dispatch] first output model={self.model} "
            f"ttft_ms={round(duration * 1000.0, 3)} output_type={output_type}",
        )
        if self.span.is_recording():
            self.span.set_attribute(
                portal_metrics.Meters.LLM_STREAMING_TIME_TO_FIRST_TOKEN, duration
            )
        portal_metrics.portal_metric_recorder.record_model_ttft(
            duration, model=self.model
        )

    def _observe_tpot(self, output_type: str) -> None:
        try:
            if self._completed:
                self.disable_tpot()
            now = time.monotonic_ns()
            if self._first_output_ns is None:
                self._first_output_ns = now
            if self._last_output_ns is not None and now < self._last_output_ns:
                self.disable_tpot()
            self._last_output_ns = now
            self._output_count += 1
            self._output_types.add(output_type)
        except Exception:
            self.disable_tpot()
            logger.warning("Skipping TPOT because output timing is unavailable")

    def disable_tpot(self) -> None:
        """Omit an unreliable sample without changing TTFT or model behavior."""
        self._tpot_disabled = True

    def complete(self, output_tokens: int | None) -> None:
        """Latch trusted usage; emission still requires a clean context exit."""
        if self._completed or self._ended:
            self.disable_tpot()
        self._completed = True
        self._output_tokens = output_tokens

    def observe_ark(self, event: Any) -> None:
        """Inspect raw Responses metadata without interrupting model output."""
        output_type = ark_output_type(event)
        self.observe(output_type)
        try:
            event_type = response_field(event, "type", "")
            if event_type == "response.reasoning_summary_text.delta" or (
                event_type.endswith(".delta")
                and response_field(event, "delta")
                and not output_type
            ):
                self.disable_tpot()
            if event_type in {"response.incomplete", "response.failed", "error"}:
                self.disable_tpot()
            if event_type == "response.completed":
                response = response_field(event, "response")
                tokens = (
                    output_tokens_for_tpot(
                        response_field(response, "usage"),
                        "output_tokens",
                        "reasoning" in self._output_types,
                    )
                    if response_field(response, "status") == "completed"
                    else None
                )
                self.complete(tokens)
        except Exception:
            self.disable_tpot()
            logger.warning("Skipping TPOT because Responses metadata is unavailable")

    def _record_tpot(self) -> None:
        try:
            tokens = self._output_tokens
            if (
                not self.streaming
                or self._tpot_disabled
                or not self._completed
                or self._output_count < 2
                or type(tokens) is not int
                or tokens <= 1
                or self._first_output_ns is None
                or self._last_output_ns is None
            ):
                return
            duration = (
                (self._last_output_ns - self._first_output_ns) / 1e9 / (tokens - 1)
            )
            if duration < 0 or not math.isfinite(duration):
                return
            if self.span.is_recording():
                self.span.set_attribute(
                    portal_metrics.Meters.LLM_STREAMING_TIME_PER_OUTPUT_TOKEN, duration
                )
            portal_metrics.portal_metric_recorder.record_model_tpot(
                duration, model=self.model
            )
        except Exception:
            logger.warning("Failed to record model TPOT")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._ended:
            return
        self._ended = True
        if exc_value is not None:
            _record_error(self.span, exc_value, "llm_error")
        if exc_type is None and exc_value is None:
            self._record_tpot()
        error_type = type(exc_value).__name__ if exc_value is not None else "none"
        elapsed_ms = round((time.monotonic() - self._log_start_monotonic) * 1000.0, 3)
        safe_info(
            logger,
            f"[llm-dispatch] model request end model={self.model} "
            f"streaming={self.streaming} outputs={self._output_count} "
            f"elapsed_ms={elapsed_ms} error={error_type}",
        )
        self.span.end()


def response_field(value: Any, name: str, default=None):
    """Read an SDK response field from a mapping or attribute-based object."""
    return (
        value.get(name, default)
        if isinstance(value, Mapping)
        else getattr(value, name, default)
    )


def output_tokens_for_tpot(usage: Any, field: str, reasoning_seen: bool) -> int | None:
    """Require an output count whose known components match the observed stream."""
    tokens = response_field(usage, field)
    if type(tokens) is not int or tokens <= 1:
        return None
    details = response_field(usage, f"{field}_details")
    reasoning = response_field(details, "reasoning_tokens", 0)
    if reasoning is not None and (
        type(reasoning) is not int
        or not 0 <= reasoning <= tokens
        or (reasoning > 0 and not reasoning_seen)
    ):
        return None
    if response_field(details, "audio_tokens", 0):
        return None
    return tokens


def litellm_output_type(chunk: Any) -> str | None:
    """Recognize generated deltas before ADK buffers tool/reasoning content."""
    for choice in response_field(chunk, "choices", []) or []:
        delta = response_field(choice, "delta")
        if response_field(delta, "content"):
            return "text"
        if response_field(delta, "reasoning_content") or response_field(
            delta, "reasoning"
        ):
            return "reasoning"
        for block in response_field(delta, "thinking_blocks", []) or []:
            if response_field(block, "thinking"):
                return "reasoning"
        functions = [
            response_field(tool, "function")
            for tool in response_field(delta, "tool_calls", []) or []
        ]
        functions.append(response_field(delta, "function_call"))
        if any(
            response_field(function, "name") or response_field(function, "arguments")
            for function in functions
        ):
            return "tool_call"
    return None


def ark_output_type(event: Any) -> str | None:
    if not response_field(event, "delta"):
        return None
    return {
        "response.output_text.delta": "text",
        "response.reasoning_summary_text.delta": "reasoning",
        "response.reasoning_text.delta": "reasoning",
        "response.function_call_arguments.delta": "tool_call",
    }.get(response_field(event, "type"))
