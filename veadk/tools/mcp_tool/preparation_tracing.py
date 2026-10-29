"""Observe MCP preparation through the existing provider with fixed metadata."""

from collections.abc import Iterator
from contextlib import contextmanager, suppress

from google.adk.tools.mcp_tool.mcp_session_manager import (
    SseConnectionParams,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters
from opentelemetry import context, trace
from opentelemetry.trace import SpanKind, Status, StatusCode


def _transport_name(params) -> str:
    if isinstance(params, StreamableHTTPConnectionParams):
        return "streamable_http"
    if isinstance(params, SseConnectionParams):
        return "sse"
    if isinstance(params, (StdioConnectionParams, StdioServerParameters)):
        return "stdio"
    return "unknown"


@contextmanager
def preparation_span(phase: str, params) -> Iterator[None]:
    # Only fixed categories are observable; connection objects may carry secrets.
    phase = phase if phase in {"tools.prepare", "session.acquire"} else "unknown"
    span = None
    token = None
    try:
        span = trace.get_tracer("veadk.mcp.preparation").start_span(
            "mcp." + phase, kind=SpanKind.INTERNAL
        )
        span.set_attribute("mcp.phase", phase)
        span.set_attribute("mcp.transport", _transport_name(params))
        token = context.attach(trace.set_span_in_context(span))
    except Exception:
        # Observability setup must not prevent or repeat the native operation.
        pass
    try:
        yield
    except BaseException as error:
        if span is not None:
            # Transport/auth errors may contain URLs, credentials or tool content.
            with suppress(Exception):
                span.set_attribute("error.type", type(error).__name__)
                span.set_status(Status(StatusCode.ERROR))
        raise
    finally:
        if token is not None:
            with suppress(Exception):
                context.detach(token)
        if span is not None:
            with suppress(Exception):
                span.end()
