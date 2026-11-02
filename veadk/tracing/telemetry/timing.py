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
from veadk.utils.logger import get_logger

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
        self.start_time = time.time_ns()
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
        if not self.streaming or self.first_token_time is not None or not output_type:
            return
        self.first_token_time = time.time_ns()
        duration = (self.first_token_time - self.start_time) / 1e9
        if duration < 0:
            logger.warning("Skipping TTFT because the wall clock moved backwards")
            return
        if self.span.is_recording():
            self.span.set_attribute(
                portal_metrics.Meters.LLM_STREAMING_TIME_TO_FIRST_TOKEN, duration
            )
        portal_metrics.portal_metric_recorder.record_model_ttft(
            duration, model=self.model
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_value is not None:
            _record_error(self.span, exc_value, "llm_error")
        self.span.end()


def _field(value: Any, name: str, default=None):
    return (
        value.get(name, default)
        if isinstance(value, Mapping)
        else getattr(value, name, default)
    )


def litellm_output_type(chunk: Any) -> str | None:
    """Recognize generated deltas before ADK buffers tool/reasoning content."""
    for choice in _field(chunk, "choices", []) or []:
        delta = _field(choice, "delta")
        if _field(delta, "content"):
            return "text"
        if _field(delta, "reasoning_content") or _field(delta, "reasoning"):
            return "reasoning"
        for block in _field(delta, "thinking_blocks", []) or []:
            if _field(block, "thinking"):
                return "reasoning"
        functions = [
            _field(tool, "function") for tool in _field(delta, "tool_calls", []) or []
        ]
        functions.append(_field(delta, "function_call"))
        if any(
            _field(function, "name") or _field(function, "arguments")
            for function in functions
        ):
            return "tool_call"
    return None


def ark_output_type(event: Any) -> str | None:
    if not _field(event, "delta"):
        return None
    return {
        "response.output_text.delta": "text",
        "response.reasoning_summary_text.delta": "reasoning",
        "response.reasoning_text.delta": "reasoning",
        "response.function_call_arguments.delta": "tool_call",
    }.get(_field(event, "type"))
