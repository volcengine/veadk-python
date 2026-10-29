"""Agent-owned MCP instrumentation preserves native instances and execution."""

import asyncio
import copy
import io
from types import SimpleNamespace

import pytest
from google.adk.tools.mcp_tool.mcp_session_manager import (
    MCPSessionManager,
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from veadk.tools.mcp_tool.preparation_adapter import instrument_mcp_toolsets
from veadk.tools.mcp_tool.trusted_mcp_toolset import TrustedMcpToolset


@pytest.fixture
def tracing(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)
    yield provider.get_tracer("adapter.test"), exporter
    provider.shutdown()


def native(cls=McpToolset):
    return cls(
        connection_params=StreamableHTTPConnectionParams(url="https://mcp.invalid"),
        errlog=io.StringIO(),
    )


@pytest.fixture
def native_work(monkeypatch):
    async def acquire(self, headers=None):
        return self

    async def prepare(self, readonly_context=None):
        return await self._mcp_session_manager.create_session(headers=readonly_context)

    monkeypatch.setattr(MCPSessionManager, "create_session", acquire)
    monkeypatch.setattr(McpToolset, "get_tools", prepare)


@pytest.mark.asyncio
async def test_native_identity_idempotence_and_context(native_work, tracing):
    tracer, exporter = tracing
    toolset = native()
    manager = toolset._mcp_session_manager
    unchanged = native()
    original_class_method = McpToolset.get_tools
    instrument_mcp_toolsets([toolset])
    instrument_mcp_toolsets([toolset])
    assert toolset._mcp_session_manager is manager
    assert McpToolset.get_tools is original_class_method
    assert "get_tools" not in unchanged.__dict__
    with tracer.start_as_current_span("caller") as caller:
        assert (
            await toolset.get_tools({"Authorization": "synthetic-private"}) is manager
        )
        assert trace.get_current_span() is caller
    spans = exporter.get_finished_spans()
    prepared = [s for s in spans if s.name == "mcp.tools.prepare"]
    acquired = [s for s in spans if s.name == "mcp.session.acquire"]
    assert len(prepared) == len(acquired) == 1
    assert prepared[0].parent.span_id == caller.get_span_context().span_id
    assert acquired[0].parent.span_id == prepared[0].context.span_id
    assert "synthetic-private" not in repr([(s.attributes, s.events) for s in spans])


@pytest.mark.asyncio
async def test_copied_toolset_methods_use_copied_owner(native_work, tracing):
    original = native()
    instrument_mcp_toolsets([original])
    cloned = copy.deepcopy(original)
    assert cloned._mcp_session_manager is not original._mcp_session_manager
    assert await cloned.get_tools() is cloned._mcp_session_manager
    assert await original.get_tools() is original._mcp_session_manager


@pytest.mark.asyncio
async def test_trusted_is_not_double_instrumented(native_work, tracing):
    _, exporter = tracing
    toolset = native(TrustedMcpToolset)
    instrument_mcp_toolsets([toolset])
    await toolset.get_tools()
    assert [s.name for s in exporter.get_finished_spans()] == [
        "mcp.session.acquire",
        "mcp.tools.prepare",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [ValueError("synthetic-private"), asyncio.CancelledError()]
)
async def test_original_failure_and_cancellation_propagate(monkeypatch, tracing, error):
    calls = []

    async def fail(self, readonly_context=None):
        calls.append(readonly_context)
        raise error

    monkeypatch.setattr(McpToolset, "get_tools", fail)
    toolset = native()
    instrument_mcp_toolsets([toolset])
    with pytest.raises(type(error)) as caught:
        await toolset.get_tools("test-context")
    assert caught.value is error
    assert calls == ["test-context"]
    assert "synthetic-private" not in repr(
        tracing[1].get_finished_spans()[0].attributes
    )


@pytest.mark.asyncio
async def test_concurrent_callers_keep_their_parent(native_work, tracing):
    tracer, exporter = tracing
    toolset = native()
    instrument_mcp_toolsets([toolset])

    async def run(name):
        with tracer.start_as_current_span(name) as caller:
            await asyncio.sleep(0)
            await toolset.get_tools()
            assert trace.get_current_span() is caller

    await asyncio.gather(run("left"), run("right"))
    spans = exporter.get_finished_spans()
    callers = {s.context.span_id for s in spans if s.name in {"left", "right"}}
    assert {s.parent.span_id for s in spans if s.name == "mcp.tools.prepare"} == callers


def test_unknown_tools_are_untouched():
    tool = SimpleNamespace(get_tools=lambda: None)
    original = dict(tool.__dict__)
    instrument_mcp_toolsets([tool, lambda: None])
    assert tool.__dict__ == original


@pytest.mark.asyncio
async def test_agent_assembly_instruments_native_toolsets(native_work, tracing):
    from veadk import Agent

    toolset = native()
    agent = Agent(name="mcp_test", model_api_key="synthetic", tools=[toolset])
    assert agent.tools[0] is toolset
    assert await agent.tools[0].get_tools() is toolset._mcp_session_manager
    assert len(tracing[1].get_finished_spans()) == 2


@pytest.mark.asyncio
async def test_identity_preserves_credential_and_session_flow(monkeypatch, tracing):
    from veadk.integrations.ve_identity.auth_config import api_key_auth
    from veadk.integrations.ve_identity.mcp_toolset import VeIdentityMcpToolset
    from mcp.types import ListToolsResult

    calls = []

    async def credential(self, tool_context):
        calls.append(("credential", tool_context))
        return SimpleNamespace(api_key="synthetic-private")

    async def acquire(self, headers=None):
        calls.append(("acquire", headers))
        return SimpleNamespace(list_tools=list_tools)

    async def list_tools():
        return ListToolsResult(tools=[])

    monkeypatch.setattr(VeIdentityMcpToolset, "_get_credential", credential)
    monkeypatch.setattr(MCPSessionManager, "create_session", acquire)
    import veadk.integrations.ve_identity.mcp_toolset as identity_module

    monkeypatch.setattr(
        identity_module,
        "generate_headers",
        lambda credential: {"X-Test": credential.api_key},
    )
    toolset = VeIdentityMcpToolset(
        auth_config=api_key_auth("synthetic-provider"),
        connection_params=StreamableHTTPConnectionParams(url="https://mcp.invalid"),
        errlog=io.StringIO(),
    )
    manager = toolset._mcp_session_manager
    instrument_mcp_toolsets([toolset])
    request = object()
    assert await toolset.get_tools(request) == []
    assert toolset._mcp_session_manager is manager
    assert calls == [
        ("credential", request),
        ("acquire", {"X-Test": "synthetic-private"}),
    ]
    assert {s.name for s in tracing[1].get_finished_spans()} == {
        "mcp.tools.prepare",
        "mcp.session.acquire",
    }


@pytest.mark.asyncio
async def test_native_header_provider_and_transport_callbacks_are_preserved(
    monkeypatch, tracing
):
    from unittest.mock import AsyncMock
    from mcp.types import ListToolsResult

    headers = {"X-Test": "synthetic-private"}
    header_provider = AsyncMock(return_value=headers)
    session = SimpleNamespace(
        list_tools=AsyncMock(return_value=ListToolsResult(tools=[]))
    )
    calls = []

    async def acquire(self, headers=None):
        calls.append(headers)
        return session

    async def callback(*args, **kwargs):
        pass

    monkeypatch.setattr(MCPSessionManager, "create_session", acquire)
    toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(url="https://mcp.invalid"),
        header_provider=header_provider,
        sampling_callback=callback,
        elicitation_callback=callback,
        errlog=io.StringIO(),
    )
    manager = toolset._mcp_session_manager
    original_state = dict(manager.__dict__)
    instrument_mcp_toolsets([toolset])
    for name, value in original_state.items():
        assert manager.__dict__[name] is value
    request = object()
    assert await toolset.get_tools(request) == []
    header_provider.assert_awaited_once_with(request)
    assert calls == [headers]
    session.list_tools.assert_awaited_once()
