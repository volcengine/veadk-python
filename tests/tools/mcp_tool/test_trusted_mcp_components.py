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

import sys
import unittest
from unittest import mock
import asyncio

from veadk.tools.mcp_tool.trusted_mcp_toolset import TrustedMcpToolset
from veadk.tools.mcp_tool.trusted_mcp_session_manager import (
    TrustedMcpSessionManager,
)
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams


class TestTrustedMcpComponents(unittest.TestCase):
    def setUp(self):
        # Create simple mock objects
        self.mock_stdio_params = mock.MagicMock()
        # Add serializable headers to stdio_params
        mock_headers = mock.MagicMock()
        mock_headers.copy.return_value = {"Content-Type": "application/json"}
        self.mock_stdio_params.headers = mock_headers
        # Add getattr method that throws AttributeError by default to simulate non-HTTP connection
        self.mock_stdio_params.getattr = mock.MagicMock(side_effect=AttributeError)

        self.mock_http_params = mock.MagicMock(spec=StreamableHTTPConnectionParams)
        self.mock_http_params.url = "http://mock-url.com"
        self.mock_http_params.timeout = 30
        self.mock_http_params.sse_read_timeout = 60
        self.mock_http_params.terminate_on_close = False
        # Add serializable headers to http_params
        mock_http_headers = mock.MagicMock()
        mock_http_headers.copy.return_value = {
            "Content-Type": "application/json",
            "x-trusted-mcp": "true",
        }
        self.mock_http_params.headers = mock_http_headers

    def test_trusted_mcp_toolset_init(self):
        """Test the initialization of TrustedMcpToolset"""
        # Mock TrustedMcpSessionManager and logger
        with (
            mock.patch(
                "veadk.tools.mcp_tool.trusted_mcp_toolset.TrustedMcpSessionManager"
            ) as mock_session_manager,
            mock.patch("veadk.tools.mcp_tool.trusted_mcp_toolset.logger"),
        ):
            # Create instance directly without mocking parent initialization to automatically set necessary attributes
            toolset = TrustedMcpToolset(
                connection_params=self.mock_stdio_params, tool_filter=["read_file"]
            )

            # Verify TrustedMcpSessionManager was created
            mock_session_manager.assert_called_once()

            # Verify _trusted_mcp_session_manager attribute is set
            self.assertIsNotNone(toolset._mcp_session_manager)

    def test_trusted_mcp_session_manager_create_client_trusted(self):
        """Test TrustedMcpSessionManager._create_client method - TrustedMCP mode"""
        # Mock trusted_mcp_client_context
        with mock.patch(
            "veadk.tools.mcp_tool.trusted_mcp_session_manager.trusted_mcp_client_context"
        ) as mock_trusted_client:
            # Create manager instance directly
            manager = TrustedMcpSessionManager(
                connection_params=self.mock_http_params, errlog=sys.stderr
            )

            # Call _create_client with trusted_mcp header
            merged_headers = {"x-trusted-mcp": "true"}
            result = manager._create_client(merged_headers)

            # Verify trusted_mcp_client_context was called
            mock_trusted_client.assert_called_once()

            # Verify result
            self.assertEqual(result, mock_trusted_client.return_value)

    def test_trusted_mcp_session_manager_create_client_standard(self):
        """Test TrustedMcpSessionManager._create_client method - Standard mode"""
        # Mock parent class's _create_client method
        with mock.patch(
            "veadk.tools.mcp_tool.trusted_mcp_session_manager.MCPSessionManager._create_client"
        ) as mock_super_create:
            expected_client = mock.MagicMock()
            mock_super_create.return_value = expected_client

            # Create manager instance directly without mocking parent initialization to automatically set necessary attributes
            manager = TrustedMcpSessionManager(
                connection_params=self.mock_stdio_params, errlog=sys.stderr
            )

            # Call _create_client with normal headers
            merged_headers = {"content-type": "application/json"}
            result = manager._create_client(merged_headers)

            # Verify parent's _create_client was called
            mock_super_create.assert_called_once_with(merged_headers)

            # Verify result
            self.assertEqual(result, expected_client)

    def test_trusted_mcp_session_manager_trusted_create_session(self):
        """Test TrustedMcpSessionManager.create_session method - TrustedMCP mode"""

        # Use coroutine test helper to run async test
        async def run_test():
            # Create a mock async context manager
            class MockAsyncContext:
                def __init__(self):
                    self.session = mock.MagicMock()

                async def __aenter__(self):
                    return self.session

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return False

            # Create a mock AsyncExitStack that supports async methods
            class MockAsyncExitStack:
                def __init__(self):
                    self.entered_contexts = []

                async def enter_async_context(self, context):
                    self.entered_contexts.append(context)
                    return await context.__aenter__()

                async def aclose(self):
                    pass

            # Mock required functions and classes
            mock_trusted_context = MockAsyncContext()
            with (
                mock.patch(
                    "veadk.tools.mcp_tool.trusted_mcp_session_manager.trusted_mcp_client",
                    return_value=mock_trusted_context,
                ),
                mock.patch(
                    "veadk.tools.mcp_tool.trusted_mcp_session_manager.MCPSessionManager._merge_headers",
                    return_value={"x-trusted-mcp": "true"},
                ),
                mock.patch(
                    "veadk.tools.mcp_tool.trusted_mcp_session_manager.MCPSessionManager._generate_session_key",
                    return_value="session-key",
                ),
                mock.patch(
                    "veadk.tools.mcp_tool.trusted_mcp_session_manager.MCPSessionManager._is_session_disconnected",
                    return_value=False,
                ),
                mock.patch(
                    "veadk.tools.mcp_tool.trusted_mcp_session_manager.AsyncExitStack",
                    return_value=MockAsyncExitStack(),
                ),
            ):
                # Create manager instance and set necessary attributes
                manager = TrustedMcpSessionManager(
                    connection_params=self.mock_http_params, errlog=sys.stderr
                )
                manager._sessions = {}
                manager._session_lock = asyncio.Lock()

                # Call create_session
                headers = {"x-trusted-mcp": "true"}
                result = await manager.create_session(headers)

                # Verify result is the mock session
                self.assertEqual(result, mock_trusted_context.session)

        # Run async test
        asyncio.run(run_test())

    def test_trusted_mcp_session_manager_session_reuse(self):
        """Test TrustedMcpSessionManager.create_session method - Session reuse"""

        # Use coroutine test helper to run async test
        async def run_test():
            # Mock necessary methods
            with (
                mock.patch(
                    "veadk.tools.mcp_tool.trusted_mcp_session_manager.MCPSessionManager._merge_headers",
                    return_value={"header": "value"},
                ),
                mock.patch(
                    "veadk.tools.mcp_tool.trusted_mcp_session_manager.MCPSessionManager._generate_session_key",
                    return_value="session-key",
                ),
                mock.patch(
                    "veadk.tools.mcp_tool.trusted_mcp_session_manager.MCPSessionManager._is_session_disconnected",
                    return_value=False,
                ),
            ):
                # Create manager instance
                manager = TrustedMcpSessionManager(
                    connection_params=self.mock_http_params, errlog=sys.stderr
                )
                manager._sessions = {}
                manager._session_lock = asyncio.Lock()

                # Set up an existing session
                existing_session = mock.MagicMock()
                existing_exit_stack = mock.MagicMock()
                manager._sessions = {
                    "session-key": (existing_session, existing_exit_stack)
                }

                # Call create_session
                result = await manager.create_session({"header": "value"})

                # Verify existing session was returned
                self.assertEqual(result, existing_session)

        # Run async test
        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
