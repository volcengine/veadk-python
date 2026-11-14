# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

import asyncio
from contextlib import asynccontextmanager
from functools import partial
from types import SimpleNamespace

import anyio
import pytest
from google.adk.tools.mcp_tool import mcp_session_manager as adk_sessions
from google.auth.exceptions import DefaultCredentialsError
from mcp import StdioServerParameters
from mcp.server.lowlevel import Server
from mcp.types import TextContent, Tool

from veadk.tools.mcp_tool import trusted_mcp_session_manager as trusted_sessions
from veadk.tools.mcp_tool.trusted_mcp_session_manager import TrustedMcpSessionManager
from veadk.tools.mcp_tool.trusted_mcp_toolset import TrustedMcpToolset

try:
    from asyncio import timeout
except ImportError:  # Python 3.10
    from async_timeout import timeout

SESSION_TIMEOUT = 2


@pytest.fixture
def memory_transports(monkeypatch):
    """Replace external transports, retaining real ADK and MCP sessions."""
    state = SimpleNamespace(opened=[], closed=0, failure=None)
    server = Server("session-routing-test")

    def no_credentials(**kwargs):
        raise DefaultCredentialsError("Credentials are disabled in this test")

    monkeypatch.setattr(adk_sessions.google.auth, "default", no_credentials)

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="echo",
                inputSchema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            )
        ]

    @server.call_tool()
    async def call_tool(name, arguments):
        return [TextContent(type="text", text=arguments["value"])]

    @asynccontextmanager
    async def transport(**kwargs):
        state.opened.append(kwargs)
        try:
            if state.failure is not None:
                raise state.failure
            server_write, client_read = anyio.create_memory_object_stream(10)
            client_write, server_read = anyio.create_memory_object_stream(10)
            async with (
                client_read,
                client_write,
                server_read,
                server_write,
                anyio.create_task_group() as tasks,
            ):
                tasks.start_soon(
                    server.run,
                    server_read,
                    server_write,
                    server.create_initialization_options(),
                )
                try:
                    yield client_read, client_write, lambda: "test-session"
                finally:
                    tasks.cancel_scope.cancel()
        finally:
            state.closed += 1
            if "http_client" in kwargs:
                await kwargs["http_client"].aclose()

    def trusted_client(**kwargs):
        return adk_sessions.SessionContext(
            client=transport(kind="trusted", **kwargs),
            timeout=SESSION_TIMEOUT,
            sse_read_timeout=SESSION_TIMEOUT,
        )

    monkeypatch.setattr(
        adk_sessions, "_StreamableHttpClientWrapper", partial(transport, kind="http")
    )
    monkeypatch.setattr(adk_sessions, "sse_client", partial(transport, kind="sse"))
    monkeypatch.setattr(adk_sessions, "stdio_client", partial(transport, kind="stdio"))
    monkeypatch.setattr(trusted_sessions, "trusted_mcp_client", trusted_client)
    return state


@asynccontextmanager
async def managed_manager(params):
    manager = TrustedMcpSessionManager(params)
    try:
        yield manager
    finally:
        if any(len(entry) == 2 for entry in manager._sessions.values()):
            # Trusted entries retain their existing two-element pool shape.
            for entry in list(manager._sessions.values()):
                await entry[1].aclose()
            manager._sessions.clear()
        else:
            await manager.close()


async def create_session(manager, headers=None):
    async with timeout(SESSION_TIMEOUT):
        return await manager.create_session(headers)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers", [None, {"Authorization": "Bearer test-placeholder"}]
)
async def test_standard_first_session(memory_transports, headers):
    toolset = TrustedMcpToolset(
        connection_params=adk_sessions.StreamableHTTPConnectionParams(
            url="http://mcp.example.test/mcp", headers=headers
        )
    )
    manager = toolset._mcp_session_manager
    try:
        session = await asyncio.wait_for(
            manager.create_session(), timeout=SESSION_TIMEOUT
        )
        assert not manager._is_session_disconnected(session)
        assert len(memory_transports.opened) == 1
    finally:
        await manager.close()
    assert memory_transports.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["http", "sse", "stdio"])
async def test_standard_transport_types(memory_transports, kind):
    if kind == "stdio":
        params = adk_sessions.StdioConnectionParams(
            server_params=StdioServerParameters(command="unused-test-command")
        )
    else:
        params_type = (
            adk_sessions.StreamableHTTPConnectionParams
            if kind == "http"
            else adk_sessions.SseConnectionParams
        )
        params = params_type(url="http://mcp.example.test/mcp")
    async with managed_manager(params) as manager:
        headers = {"x-trusted-mcp": "true"} if kind != "http" else None
        session = await create_session(manager, headers)
        assert not manager._is_session_disconnected(session)
        assert memory_transports.opened[0]["kind"] == kind
    assert memory_transports.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base_marker,call_marker,expected_kind",
    [
        (None, None, "http"),
        ("false", None, "http"),
        ("TRUE", None, "http"),
        ("true", None, "trusted"),
        (None, "true", "trusted"),
        ("true", "false", "http"),
        ("false", "true", "trusted"),
    ],
)
async def test_merged_headers_select_route(
    memory_transports, base_marker, call_marker, expected_kind
):
    base_headers = {"Authorization": "Bearer base-placeholder", "X-Base": "base"}
    call_headers = {"Authorization": "Bearer call-placeholder", "X-Call": "call"}
    if base_marker is not None:
        base_headers["x-trusted-mcp"] = base_marker
    if call_marker is not None:
        call_headers["x-trusted-mcp"] = call_marker
    original_base, original_call = base_headers.copy(), call_headers.copy()
    params = adk_sessions.StreamableHTTPConnectionParams(
        url="http://mcp.example.test/mcp", headers=base_headers
    )
    async with managed_manager(params) as manager:
        session = await create_session(manager, call_headers)
        assert await create_session(manager, call_headers) is session
        assert len(memory_transports.opened) == 1
        opened = memory_transports.opened[0]
        assert opened["kind"] == expected_kind
        transport_headers = (
            opened["headers"]
            if expected_kind == "trusted"
            else opened["http_client"].headers
        )
        assert transport_headers["Authorization"] == "Bearer call-placeholder"
        assert transport_headers["X-Base"] == "base"
        assert transport_headers["X-Call"] == "call"
        assert "x-trusted-mcp" not in transport_headers
        assert base_headers == original_base
        assert call_headers == original_call
        assert params.headers == original_base
        expected_key = manager._generate_session_key({**base_headers, **call_headers})
        assert manager._sessions[expected_key][0] is session
    assert memory_transports.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("trusted", [False, True])
async def test_authentication_headers_isolate_sessions(memory_transports, trusted):
    params = adk_sessions.StreamableHTTPConnectionParams(
        url="http://mcp.example.test/mcp",
        headers={"x-trusted-mcp": "true"} if trusted else None,
    )
    first_headers = {"Authorization": "Bearer first-placeholder"}
    second_headers = {"Authorization": "Bearer second-placeholder"}
    async with managed_manager(params) as manager:
        first = await create_session(manager, first_headers)
        second = await create_session(manager, second_headers)
        assert first is not second
        assert await create_session(manager, first_headers) is first
        assert await create_session(manager, second_headers) is second
        assert len(memory_transports.opened) == 2
    assert memory_transports.closed == 2


@pytest.mark.asyncio
async def test_standard_concurrent_requests_reuse_session(memory_transports):
    params = adk_sessions.StreamableHTTPConnectionParams(
        url="http://mcp.example.test/mcp"
    )
    async with managed_manager(params) as manager:
        sessions = await asyncio.wait_for(
            asyncio.gather(*(manager.create_session() for _ in range(4))),
            timeout=SESSION_TIMEOUT,
        )
        assert all(session is sessions[0] for session in sessions)
        assert len(memory_transports.opened) == 1
    assert memory_transports.closed == 1


@pytest.mark.asyncio
async def test_standard_disconnected_session_is_replaced(memory_transports):
    params = adk_sessions.StreamableHTTPConnectionParams(
        url="http://mcp.example.test/mcp"
    )
    async with managed_manager(params) as manager:
        first = await create_session(manager)
        await first._write_stream.aclose()
        second = await create_session(manager)
        assert second is not first
        assert not manager._is_session_disconnected(second)
        assert len(memory_transports.opened) == 2
        assert memory_transports.closed == 1
    assert memory_transports.closed == 2


@pytest.mark.asyncio
async def test_standard_failure_allows_retry(memory_transports):
    params = adk_sessions.StreamableHTTPConnectionParams(
        url="http://mcp.example.test/mcp"
    )
    async with managed_manager(params) as manager:
        memory_transports.failure = RuntimeError("test transport failed")
        with pytest.raises(ConnectionError, match="test transport failed"):
            await create_session(manager)
        assert not manager._sessions
        assert not manager._session_lock.locked()
        assert memory_transports.closed == 1
        memory_transports.failure = None
        session = await create_session(manager)
        assert not manager._is_session_disconnected(session)
        assert len(memory_transports.opened) == 2
    assert memory_transports.closed == 2


@pytest.mark.asyncio
async def test_standard_lock_wait_cancellation_allows_retry(memory_transports):
    params = adk_sessions.StreamableHTTPConnectionParams(
        url="http://mcp.example.test/mcp"
    )
    async with managed_manager(params) as manager:
        started = asyncio.Event()

        async def request_session():
            started.set()
            return await manager.create_session()

        async with manager._session_lock:
            task = asyncio.create_task(request_session())
            await asyncio.wait_for(started.wait(), timeout=SESSION_TIMEOUT)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not memory_transports.opened
            assert not manager._sessions
        assert not manager._session_lock.locked()
        session = await create_session(manager)
        assert not manager._is_session_disconnected(session)
    assert memory_transports.closed == 1


@pytest.mark.asyncio
async def test_toolset_discovers_and_calls_standard_tool(memory_transports):
    toolset = TrustedMcpToolset(
        connection_params=adk_sessions.StreamableHTTPConnectionParams(
            url="http://mcp.example.test/mcp"
        )
    )
    try:
        async with timeout(SESSION_TIMEOUT):
            tools = await toolset.get_tools()
            assert [tool.name for tool in tools] == ["echo"]
            result = await tools[0].run_async(
                args={"value": "test echo"}, tool_context=None
            )
        assert result["content"][0]["text"] == "test echo"
        assert len(memory_transports.opened) == 1
    finally:
        await toolset.close()
    assert memory_transports.closed == 1
