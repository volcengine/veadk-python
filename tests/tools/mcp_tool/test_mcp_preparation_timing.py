"""MCP preparation spans observe native work without changing its lifecycle."""

import asyncio
import io

import pytest
from google.adk.tools.mcp_tool.mcp_session_manager import (
    MCPSessionManager,
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from opentelemetry import context, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from veadk.tools.mcp_tool.trusted_mcp_toolset import TrustedMcpToolset
from veadk.tools.mcp_tool.preparation_adapter import instrument_mcp_toolsets


@pytest.fixture
def tracing(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)
    yield provider.get_tracer("test.mcp.preparation"), exporter
    provider.shutdown()


def toolset():
    return TrustedMcpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url="https://mcp.invalid/synthetic-private-path",
            headers={"X-Test-Secret": "synthetic-private-header"},
        ),
        errlog=io.StringIO(),
    )


@pytest.mark.asyncio
async def test_preparation_and_acquisition_are_nested_observed_boundaries(
    monkeypatch, tracing
):
    tracer, exporter = tracing
    calls = []
    result = [object()]
    session = object()
    headers = {"X-Test-Secret": "synthetic-private-dynamic"}

    async def acquire(self, headers=None):
        calls.append(("acquire", headers))
        return session

    async def prepare(self, readonly_context=None):
        assert await self._mcp_session_manager.create_session(headers) is session
        calls.append(("prepare", readonly_context))
        return result

    monkeypatch.setattr(MCPSessionManager, "create_session", acquire)
    monkeypatch.setattr(McpToolset, "get_tools", prepare)
    tools = toolset()
    request_context = object()
    with tracer.start_as_current_span("caller") as caller:
        assert await tools.get_tools(request_context) is result
        assert trace.get_current_span() is caller
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert set(spans) == {"caller", "mcp.tools.prepare", "mcp.session.acquire"}
    prepared = spans["mcp.tools.prepare"]
    acquired = spans["mcp.session.acquire"]
    assert prepared.parent.span_id == caller.get_span_context().span_id
    assert acquired.parent.span_id == prepared.context.span_id
    assert acquired.start_time >= prepared.start_time
    assert acquired.end_time <= prepared.end_time
    assert calls == [("acquire", headers), ("prepare", request_context)]
    for span in [prepared, acquired]:
        assert span.attributes["mcp.transport"] == "streamable_http"
        assert "synthetic-private" not in repr(span.attributes)
        assert not span.events


@pytest.mark.asyncio
async def test_reused_session_records_acquisition_without_recreating_it(
    monkeypatch, tracing
):
    _, exporter = tracing
    session = object()
    calls = []

    async def acquire(self, headers=None):
        calls.append(headers)
        return session

    monkeypatch.setattr(MCPSessionManager, "create_session", acquire)
    manager = toolset()._mcp_session_manager
    assert await manager.create_session() is session
    assert await manager.create_session() is session
    assert calls == [None, None]
    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    assert all(span.name == "mcp.session.acquire" for span in spans)
    assert all("mcp.session.created" not in span.attributes for span in spans)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["prepare", "acquire"])
async def test_native_errors_are_preserved_without_recording_messages(
    monkeypatch, tracing, operation
):
    _, exporter = tracing
    error = ValueError("synthetic-private-error")
    calls = []

    async def fail(*args, **kwargs):
        calls.append(None)
        raise error

    monkeypatch.setattr(
        McpToolset if operation == "prepare" else MCPSessionManager,
        "get_tools" if operation == "prepare" else "create_session",
        fail,
    )
    tools = toolset()
    with pytest.raises(ValueError) as caught:
        await (
            tools.get_tools()
            if operation == "prepare"
            else tools._mcp_session_manager.create_session()
        )
    assert caught.value is error
    assert len(calls) == 1
    (span,) = exporter.get_finished_spans()
    assert span.status.status_code == trace.StatusCode.ERROR
    assert span.attributes["error.type"] == "ValueError"
    assert span.status.description is None
    assert not span.events
    assert "synthetic-private" not in repr(span.attributes)


@pytest.mark.asyncio
async def test_cancellation_ends_phase_and_restores_context(monkeypatch, tracing):
    tracer, exporter = tracing
    entered = asyncio.Event()
    pending = asyncio.Event()

    async def acquire(self, headers=None):
        entered.set()
        await pending.wait()

    monkeypatch.setattr(MCPSessionManager, "create_session", acquire)
    manager = toolset()._mcp_session_manager
    with tracer.start_as_current_span("caller") as caller:
        task = asyncio.create_task(manager.create_session())
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert trace.get_current_span() is caller
    spans = [
        span
        for span in exporter.get_finished_spans()
        if span.name == "mcp.session.acquire"
    ]
    assert len(spans) == 1
    assert spans[0].attributes["error.type"] == "CancelledError"
    assert spans[0].status.status_code == trace.StatusCode.ERROR


@pytest.mark.asyncio
async def test_concurrent_preparation_keeps_parent_contexts_separate(
    monkeypatch, tracing
):
    tracer, exporter = tracing
    session = object()

    async def acquire(self, headers=None):
        await asyncio.sleep(0)
        return session

    async def prepare(self, readonly_context=None):
        return await self._mcp_session_manager.create_session()

    monkeypatch.setattr(MCPSessionManager, "create_session", acquire)
    monkeypatch.setattr(McpToolset, "get_tools", prepare)
    tools = toolset()

    async def call(index):
        with tracer.start_as_current_span(
            f"caller{index}", context=context.Context()
        ) as caller:
            assert await tools.get_tools() is session
            assert trace.get_current_span() is caller

    await asyncio.gather(call(1), call(2))
    spans = exporter.get_finished_spans()
    prepared = [span for span in spans if span.name == "mcp.tools.prepare"]
    acquired = [span for span in spans if span.name == "mcp.session.acquire"]
    assert len(prepared) == len(acquired) == 2
    assert len({span.context.trace_id for span in prepared}) == 2
    assert {span.parent.span_id for span in acquired} == {
        span.context.span_id for span in prepared
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["tracer", "start", "attach", "attribute", "end"])
@pytest.mark.parametrize("failure", [False, True])
async def test_telemetry_failure_does_not_repeat_or_change_native_work(
    monkeypatch, stage, failure
):
    calls = []
    sentinel = object()
    error = ValueError("synthetic-private-error")

    def maybe_fail(actual):
        if stage == actual:
            raise RuntimeError("synthetic telemetry failure")

    class Span:
        def set_attribute(self, *args):
            maybe_fail("attribute")

        def set_status(self, *args):
            pass

        def end(self):
            maybe_fail("end")

    class Tracer:
        def start_span(self, *args, **kwargs):
            maybe_fail("start")
            return Span()

    def get_tracer(*args, **kwargs):
        maybe_fail("tracer")
        return Tracer()

    async def acquire(self, headers=None):
        calls.append(headers)
        if failure:
            raise error
        return sentinel

    monkeypatch.setattr(trace, "get_tracer", get_tracer)
    if stage == "attach":
        monkeypatch.setattr(context, "attach", lambda *args: maybe_fail("attach"))
    monkeypatch.setattr(MCPSessionManager, "create_session", acquire)
    manager = toolset()._mcp_session_manager
    before = trace.get_current_span()
    if failure:
        with pytest.raises(ValueError) as caught:
            await manager.create_session()
        assert caught.value is error
    else:
        assert await manager.create_session() is sentinel
    assert calls == [None]
    assert trace.get_current_span() is before


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["trusted", "native"])
async def test_native_retry_is_one_preparation_with_each_acquisition_attempt(
    monkeypatch, tracing, kind
):
    from unittest.mock import AsyncMock
    from mcp.types import ListToolsResult, Tool

    _, exporter = tracing
    session = type("Session", (), {})()
    session.list_tools = AsyncMock(
        return_value=ListToolsResult(
            tools=[Tool(name="synthetic_tool", inputSchema={"type": "object"})]
        )
    )
    attempts = []

    async def acquire(self, headers=None):
        attempts.append(None)
        if len(attempts) == 1:
            raise ConnectionError("synthetic connection failure")
        return session

    monkeypatch.setattr(MCPSessionManager, "create_session", acquire)
    tools = (
        toolset()
        if kind == "trusted"
        else McpToolset(
            connection_params=StreamableHTTPConnectionParams(url="https://mcp.invalid"),
            errlog=io.StringIO(),
        )
    )
    instrument_mcp_toolsets([tools])
    result = await tools.get_tools()
    assert [tool.name for tool in result] == ["synthetic_tool"]
    assert len(attempts) == 2
    session.list_tools.assert_awaited_once()
    spans = exporter.get_finished_spans()
    prepared = [span for span in spans if span.name == "mcp.tools.prepare"]
    acquired = [span for span in spans if span.name == "mcp.session.acquire"]
    assert len(prepared) == 1
    assert len(acquired) == 2
    assert acquired[0].attributes["error.type"] == "ConnectionError"
    assert "error.type" not in acquired[1].attributes
    assert {span.parent.span_id for span in acquired} == {prepared[0].context.span_id}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["trusted", "native"])
async def test_native_tool_list_cache_does_not_create_extra_acquisition(
    monkeypatch, tracing, kind
):
    from unittest.mock import AsyncMock
    from mcp.types import ListToolsResult, Tool

    _, exporter = tracing
    session = type("Session", (), {})()
    session.list_tools = AsyncMock(
        return_value=ListToolsResult(
            tools=[Tool(name="synthetic_tool", inputSchema={"type": "object"})]
        )
    )
    acquire = AsyncMock(return_value=session)

    async def native_acquire(self, headers=None):
        return await acquire(headers=headers)

    monkeypatch.setattr(MCPSessionManager, "create_session", native_acquire)
    toolset_class = TrustedMcpToolset if kind == "trusted" else McpToolset
    tools = toolset_class(
        connection_params=StreamableHTTPConnectionParams(url="https://mcp.invalid/mcp"),
        tool_list_cache_ttl_seconds=60,
        errlog=io.StringIO(),
    )
    instrument_mcp_toolsets([tools])
    assert [tool.name for tool in await tools.get_tools()] == ["synthetic_tool"]
    assert [tool.name for tool in await tools.get_tools()] == ["synthetic_tool"]
    acquire.assert_awaited_once()
    session.list_tools.assert_awaited_once()
    spans = exporter.get_finished_spans()
    assert sum(span.name == "mcp.tools.prepare" for span in spans) == 2
    assert sum(span.name == "mcp.session.acquire" for span in spans) == 1
