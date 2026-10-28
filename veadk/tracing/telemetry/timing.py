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

"""SDK-observed model timestamps and isolated request start propagation."""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span


@dataclass(frozen=True)
class RequestStart:
    time_ns: int
    source: str


_REQUEST_START: ContextVar[RequestStart | None] = ContextVar(
    "veadk_request_start", default=None
)


def current_request_start() -> RequestStart | None:
    return _REQUEST_START.get()


@contextmanager
def bind_request_start(start: RequestStart):
    token = _REQUEST_START.set(start)
    try:
        yield start
    finally:
        _REQUEST_START.reset(token)


async def with_request_timing(
    events: AsyncGenerator, start: RequestStart
) -> AsyncGenerator:
    """Bind only while advancing/closing; never retain context across yields."""
    try:
        while True:
            with bind_request_start(start):
                try:
                    event = await anext(events)
                except StopAsyncIteration:
                    return
            yield event
    finally:
        with bind_request_start(start):
            await events.aclose()


def timed_runner(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = current_request_start() or RequestStart(time.time_ns(), "runner")
        events = with_request_timing(func(*args, **kwargs), start)
        try:
            async for event in events:
                yield event
        finally:
            await events.aclose()

    return wrapper


class RequestTimingMiddleware:
    """Capture ASGI ingress without inspecting or buffering request bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with bind_request_start(RequestStart(time.time_ns(), "http")):
            await self.app(scope, receive, send)


def install_request_timing(app) -> None:
    if getattr(app.state, "_veadk_request_timing_installed", False):
        return
    app.add_middleware(RequestTimingMiddleware)
    app.state._veadk_request_timing_installed = True


def annotate_request_start(span: Span) -> None:
    start = current_request_start()
    if start is not None and span.is_recording():
        span.set_attribute("veadk.request.start_time_unix_ns", start.time_ns)
        span.set_attribute("veadk.request.start_source", start.source)


class ModelTiming:
    """One SDK request; this context manager never attaches OTel context."""

    def __init__(self, *, streaming: bool, model: str):
        self.streaming = streaming
        self.first_token_time: int | None = None
        self.owner = trace.get_current_span()
        self.span = trace.get_tracer(__name__).start_span(
            "model_request", attributes={"gen_ai.request.model": str(model)}
        )
        self._spans = (self.span, self.owner)
        for span in self._spans:
            annotate_request_start(span)
        self._set("veadk.model.start_time_unix_ns", time.time_ns())
        self._set("veadk.model.streaming", streaming)
        self._set("veadk.model.request_scope", "sdk_request")
        self._set(
            "veadk.model.first_token_status",
            "no_output" if streaming else "non_streaming",
        )

    def _set(self, name: str, value: Any) -> None:
        for span in self._spans:
            if span.is_recording():
                span.set_attribute(name, value)

    def __enter__(self) -> ModelTiming:
        return self

    def observe(self, output_type: str | None) -> None:
        if not self.streaming or self.first_token_time is not None or not output_type:
            return
        self.first_token_time = time.time_ns()
        self._set("veadk.model.first_token_time_unix_ns", self.first_token_time)
        self._set("veadk.model.first_token_type", output_type)
        self._set("veadk.model.first_token_status", "observed")
        for span in self._spans:
            if span.is_recording():
                span.add_event(
                    "veadk.model.first_token",
                    {"veadk.model.first_token_type": output_type},
                    timestamp=self.first_token_time,
                )

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        outcome = "completed"
        if exc_type is not None:
            outcome = (
                "cancelled"
                if issubclass(exc_type, (asyncio.CancelledError, GeneratorExit))
                else "error"
            )
        self._set("veadk.model.outcome", outcome)
        self.span.end()


def mark_uninstrumented_model(span: Span, *, streaming: bool) -> None:
    annotate_request_start(span)
    attributes = getattr(span, "attributes", None) or {}
    if "veadk.model.start_time_unix_ns" in attributes or not span.is_recording():
        return
    span.set_attribute("veadk.model.streaming", streaming)
    span.set_attribute(
        "veadk.model.first_token_status",
        "unsupported" if streaming else "non_streaming",
    )


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
