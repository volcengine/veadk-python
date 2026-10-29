"""Ordinary MCP sessions must retain the parent's lock and lifecycle ownership."""

import asyncio
import io
from unittest.mock import Mock

import pytest
from google.adk.tools.mcp_tool.mcp_session_manager import (
    MCPSessionManager,
    SseConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters

from veadk.tools.mcp_tool.trusted_mcp_session_manager import TrustedMcpSessionManager
from veadk.tools.mcp_tool.trusted_mcp_toolset import TrustedMcpToolset


def connection(kind):
    if kind == "http":
        return StreamableHTTPConnectionParams(url="https://mcp.invalid/mcp")
    if kind == "sse":
        return SseConnectionParams(url="https://mcp.invalid/sse")
    return StdioServerParameters(command="synthetic-command-not-executed")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["http", "sse", "stdio"])
async def test_standard_transport_can_acquire_parent_lock(monkeypatch, kind):
    sentinel = object()
    headers = {"X-Test-Request": "synthetic"}
    received = []

    async def parent(self, headers=None):
        async with self._session_lock:
            received.append(headers)
            return sentinel

    monkeypatch.setattr(MCPSessionManager, "create_session", parent)
    manager = TrustedMcpSessionManager(
        connection_params=connection(kind), errlog=io.StringIO()
    )
    result = await asyncio.wait_for(manager.create_session(headers), timeout=0.3)
    assert result is sentinel
    assert received == [headers]
    assert received[0] is headers
    assert headers == {"X-Test-Request": "synthetic"}
    assert not manager._session_lock.locked()


@pytest.mark.asyncio
async def test_concurrent_standard_calls_reuse_parent_owned_session(monkeypatch):
    sessions = []

    async def parent(self, headers=None):
        async with self._session_lock:
            await asyncio.sleep(0)
            if not sessions:
                sessions.append(object())
            return sessions[0]

    monkeypatch.setattr(MCPSessionManager, "create_session", parent)
    manager = TrustedMcpSessionManager(
        connection_params=connection("http"), errlog=io.StringIO()
    )
    results = await asyncio.wait_for(
        asyncio.gather(manager.create_session(), manager.create_session()), timeout=0.3
    )
    assert len(sessions) == 1
    assert results[0] is results[1] is sessions[0]
    assert not manager._session_lock.locked()


@pytest.mark.asyncio
async def test_parent_error_is_preserved_and_lock_released(monkeypatch):
    boom = ValueError("synthetic parent failure")

    async def parent(self, headers=None):
        async with self._session_lock:
            raise boom

    monkeypatch.setattr(MCPSessionManager, "create_session", parent)
    manager = TrustedMcpSessionManager(
        connection_params=connection("http"), errlog=io.StringIO()
    )
    with pytest.raises(ValueError) as caught:
        await asyncio.wait_for(manager.create_session(), timeout=0.3)
    assert caught.value is boom
    assert not manager._session_lock.locked()


@pytest.mark.asyncio
async def test_parent_cancellation_is_preserved_and_lock_released(monkeypatch):
    entered = asyncio.Event()
    pending = asyncio.Event()

    async def parent(self, headers=None):
        async with self._session_lock:
            entered.set()
            await pending.wait()

    monkeypatch.setattr(MCPSessionManager, "create_session", parent)
    manager = TrustedMcpSessionManager(
        connection_params=connection("http"), errlog=io.StringIO()
    )
    task = asyncio.create_task(manager.create_session())
    try:
        await asyncio.wait_for(entered.wait(), timeout=0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not manager._session_lock.locked()


def test_toolset_initialization_logs_transport_without_connection_secrets(monkeypatch):
    logger = Mock()
    monkeypatch.setattr("veadk.tools.mcp_tool.trusted_mcp_toolset.logger", logger)
    monkeypatch.setattr(
        "veadk.tools.mcp_tool.trusted_mcp_toolset.TrustedMcpSessionManager", Mock()
    )
    params = StreamableHTTPConnectionParams(
        url="https://mcp.invalid/synthetic-private-path",
        headers={"X-Credential-Test": "synthetic-private-header"},
    )
    TrustedMcpToolset(connection_params=params)
    rendered = str(logger.info.call_args_list)
    assert "synthetic-private-header" not in rendered
    assert "synthetic-private-path" not in rendered
    assert "StreamableHTTPConnectionParams" in rendered


@pytest.mark.parametrize("kind", ["http", "sse", "stdio"])
def test_standard_client_forwards_native_transport_arguments(monkeypatch, kind):
    sentinel = object()
    transport = object()
    headers = {"X-Test-Request": "synthetic"}
    received = []

    def parent(self, merged_headers=None, *args, **kwargs):
        received.append((merged_headers, args, kwargs))
        return sentinel

    monkeypatch.setattr(MCPSessionManager, "_create_client", parent)
    manager = TrustedMcpSessionManager(
        connection_params=connection(kind), errlog=io.StringIO()
    )
    assert (
        manager._create_client(
            headers, mtls_transport=transport, session_key="synthetic-session"
        )
        is sentinel
    )
    assert received == [
        (headers, (), {"mtls_transport": transport, "session_key": "synthetic-session"})
    ]
    assert received[0][0] is headers
    assert headers == {"X-Test-Request": "synthetic"}


def test_non_vendor_marker_is_preserved_for_native_client(monkeypatch):
    headers = {"x-trusted-mcp": "false", "X-Test-Request": "synthetic"}
    received = []
    monkeypatch.setattr(
        MCPSessionManager,
        "_create_client",
        lambda self, value: received.append(dict(value)),
    )
    manager = TrustedMcpSessionManager(
        connection_params=connection("http"), errlog=io.StringIO()
    )
    manager._create_client(headers)
    assert received == [{"x-trusted-mcp": "false", "X-Test-Request": "synthetic"}]
    assert headers == received[0]
