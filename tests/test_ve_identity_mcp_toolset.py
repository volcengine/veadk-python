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

"""Unit tests for VeIdentityMcpToolset."""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from veadk.integrations.ve_identity.mcp_toolset import VeIdentityMcpToolset
from veadk.integrations.ve_identity.auth_config import api_key_auth, oauth2_auth


class TestVeIdentityMcpToolsetInit:
    """Tests for VeIdentityMcpToolset initialization."""

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_init_with_api_key_auth(self, mock_identity_client):
        """Test initializing with API key auth config."""
        connection_params = Mock()
        config = api_key_auth("test-provider")

        toolset = VeIdentityMcpToolset(
            auth_config=config, connection_params=connection_params
        )

        assert toolset._auth_config == config
        assert toolset._connection_params == connection_params
        assert toolset.tool_filter is None
        assert toolset.tool_name_prefix is None

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_init_with_oauth2_auth(self, mock_identity_client):
        """Test initializing with OAuth2 auth config."""
        connection_params = Mock()
        config = oauth2_auth(provider_name="github", scopes=["repo"], auth_flow="M2M")

        toolset = VeIdentityMcpToolset(
            auth_config=config, connection_params=connection_params
        )

        assert toolset._auth_config == config

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_init_with_tool_filter_list(self, mock_identity_client):
        """Test initializing with tool filter as list."""
        connection_params = Mock()
        config = api_key_auth("test-provider")
        tool_filter = ["tool1", "tool2"]

        toolset = VeIdentityMcpToolset(
            auth_config=config,
            connection_params=connection_params,
            tool_filter=tool_filter,
        )

        assert toolset.tool_filter == tool_filter

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_init_with_tool_name_prefix(self, mock_identity_client):
        """Test initializing with tool name prefix."""
        connection_params = Mock()
        config = api_key_auth("test-provider")
        prefix = "github_"

        toolset = VeIdentityMcpToolset(
            auth_config=config,
            connection_params=connection_params,
            tool_name_prefix=prefix,
        )

        assert toolset.tool_name_prefix == prefix

    def test_init_with_none_connection_params(self):
        """Test that initialization fails with None connection_params."""
        config = api_key_auth("test-provider")

        with pytest.raises(ValueError, match="Missing connection params"):
            VeIdentityMcpToolset(auth_config=config, connection_params=None)


class TestVeIdentityMcpToolsetIsToolSelected:
    """Tests for VeIdentityMcpToolset._is_tool_selected method."""

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_is_tool_selected_no_filter(self, mock_identity_client):
        """Test tool selection with no filter."""
        connection_params = Mock()
        config = api_key_auth("test-provider")

        toolset = VeIdentityMcpToolset(
            auth_config=config, connection_params=connection_params
        )

        tool = Mock()
        tool.name = "test_tool"

        assert toolset._is_tool_selected(tool, None) is True

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_is_tool_selected_with_list_filter_match(self, mock_identity_client):
        """Test tool selection with list filter that matches."""
        connection_params = Mock()
        config = api_key_auth("test-provider")
        tool_filter = ["tool1", "tool2"]

        toolset = VeIdentityMcpToolset(
            auth_config=config,
            connection_params=connection_params,
            tool_filter=tool_filter,
        )

        tool = Mock()
        tool.name = "tool1"

        assert toolset._is_tool_selected(tool, None) is True

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_is_tool_selected_with_list_filter_no_match(self, mock_identity_client):
        """Test tool selection with list filter that doesn't match."""
        connection_params = Mock()
        config = api_key_auth("test-provider")
        tool_filter = ["tool1", "tool2"]

        toolset = VeIdentityMcpToolset(
            auth_config=config,
            connection_params=connection_params,
            tool_filter=tool_filter,
        )

        tool = Mock()
        tool.name = "tool3"

        assert toolset._is_tool_selected(tool, None) is False

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_is_tool_selected_with_predicate_filter(self, mock_identity_client):
        """Test tool selection with predicate filter."""
        connection_params = Mock()
        config = api_key_auth("test-provider")

        # Predicate that only selects tools starting with "test_"
        def tool_predicate(tool, context):
            return tool.name.startswith("test_")

        toolset = VeIdentityMcpToolset(
            auth_config=config,
            connection_params=connection_params,
            tool_filter=tool_predicate,
        )

        tool1 = Mock()
        tool1.name = "test_tool"

        tool2 = Mock()
        tool2.name = "other_tool"

        assert toolset._is_tool_selected(tool1, None) is True
        assert toolset._is_tool_selected(tool2, None) is False


class TestVeIdentityMcpToolsetClose:
    """Tests for VeIdentityMcpToolset.close method."""

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    async def test_close_success(self, mock_identity_client):
        """Test successful close."""
        connection_params = Mock()
        config = api_key_auth("test-provider")

        toolset = VeIdentityMcpToolset(
            auth_config=config, connection_params=connection_params
        )

        # Mock the session manager's close method
        toolset._mcp_session_manager.close = AsyncMock()

        await toolset.close()

        toolset._mcp_session_manager.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    async def test_close_handles_exception(self, mock_identity_client):
        """Test that close handles exceptions gracefully."""
        connection_params = Mock()
        config = api_key_auth("test-provider")

        toolset = VeIdentityMcpToolset(
            auth_config=config, connection_params=connection_params
        )

        # Mock the session manager's close method to raise an exception
        toolset._mcp_session_manager.close = AsyncMock(
            side_effect=Exception("Close failed")
        )

        # Should not raise, just log the error
        await toolset.close()


class TestVeIdentityMcpToolsetGetToolsWithFilter:
    """Tests for VeIdentityMcpToolset.get_tools with tool_filter applied."""

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    @patch("veadk.integrations.ve_identity.mcp_toolset.MCPSessionManager")
    @patch("veadk.integrations.ve_identity.mcp_toolset.VeIdentityMcpTool")
    async def test_get_tools_with_list_filter(
        self, mock_mcp_tool_class, mock_session_manager_class, mock_identity_client
    ):
        """Test that get_tools correctly filters tools using list filter."""
        from google.adk.agents.readonly_context import ReadonlyContext

        # Setup mocks
        mock_session_manager = Mock()
        mock_session_manager_class.return_value = mock_session_manager
        mock_session = AsyncMock()
        mock_session_manager.create_session = AsyncMock(return_value=mock_session)

        # Create mock tools returned by MCP server
        mock_tool1 = Mock()
        mock_tool1.name = "read_file"
        mock_tool2 = Mock()
        mock_tool2.name = "write_file"
        mock_tool3 = Mock()
        mock_tool3.name = "delete_file"

        mock_list_tools_result = Mock()
        mock_list_tools_result.tools = [mock_tool1, mock_tool2, mock_tool3]
        mock_session.list_tools = AsyncMock(return_value=mock_list_tools_result)

        # Create mock VeIdentityMcpTool instances
        mock_mcp_tool1 = Mock()
        mock_mcp_tool1.name = "read_file"
        mock_mcp_tool2 = Mock()
        mock_mcp_tool2.name = "write_file"
        mock_mcp_tool3 = Mock()
        mock_mcp_tool3.name = "delete_file"

        mock_mcp_tool_class.side_effect = [
            mock_mcp_tool1,
            mock_mcp_tool2,
            mock_mcp_tool3,
        ]

        # Create toolset with filter for only read_file and write_file
        connection_params = Mock()
        config = api_key_auth("test-provider")
        tool_filter = ["read_file", "write_file"]

        toolset = VeIdentityMcpToolset(
            auth_config=config,
            connection_params=connection_params,
            tool_filter=tool_filter,
        )

        # Mock the credential
        toolset._get_credential = AsyncMock(return_value=Mock())

        # Create readonly context
        mock_invocation_ctx = Mock()
        mock_invocation_ctx.session = Mock()
        mock_invocation_ctx.session.state = {}
        mock_invocation_ctx.user_id = "test_user"
        mock_invocation_ctx.agent = Mock()
        mock_invocation_ctx.agent.name = "test_agent"
        readonly_context = ReadonlyContext(
            invocation_context=mock_invocation_ctx,
        )

        # Get tools
        tools = await toolset.get_tools(readonly_context)

        # Verify only filtered tools are returned
        assert len(tools) == 2
        assert mock_mcp_tool1 in tools
        assert mock_mcp_tool2 in tools
        assert mock_mcp_tool3 not in tools

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    @patch("veadk.integrations.ve_identity.mcp_toolset.MCPSessionManager")
    @patch("veadk.integrations.ve_identity.mcp_toolset.VeIdentityMcpTool")
    async def test_get_tools_with_predicate_filter(
        self, mock_mcp_tool_class, mock_session_manager_class, mock_identity_client
    ):
        """Test that get_tools correctly filters tools using predicate filter."""
        from google.adk.agents.readonly_context import ReadonlyContext

        # Setup mocks
        mock_session_manager = Mock()
        mock_session_manager_class.return_value = mock_session_manager
        mock_session = AsyncMock()
        mock_session_manager.create_session = AsyncMock(return_value=mock_session)

        # Create mock tools returned by MCP server
        mock_tool1 = Mock()
        mock_tool1.name = "test_read"
        mock_tool2 = Mock()
        mock_tool2.name = "prod_write"
        mock_tool3 = Mock()
        mock_tool3.name = "test_delete"

        mock_list_tools_result = Mock()
        mock_list_tools_result.tools = [mock_tool1, mock_tool2, mock_tool3]
        mock_session.list_tools = AsyncMock(return_value=mock_list_tools_result)

        # Create mock VeIdentityMcpTool instances
        mock_mcp_tool1 = Mock()
        mock_mcp_tool1.name = "test_read"
        mock_mcp_tool2 = Mock()
        mock_mcp_tool2.name = "prod_write"
        mock_mcp_tool3 = Mock()
        mock_mcp_tool3.name = "test_delete"

        mock_mcp_tool_class.side_effect = [
            mock_mcp_tool1,
            mock_mcp_tool2,
            mock_mcp_tool3,
        ]

        # Create toolset with predicate filter (only tools starting with "test_")
        connection_params = Mock()
        config = api_key_auth("test-provider")

        def test_only_filter(tool, context):
            return tool.name.startswith("test_")

        toolset = VeIdentityMcpToolset(
            auth_config=config,
            connection_params=connection_params,
            tool_filter=test_only_filter,
        )

        # Mock the credential
        toolset._get_credential = AsyncMock(return_value=Mock())

        # Create readonly context
        mock_invocation_ctx = Mock()
        mock_invocation_ctx.session = Mock()
        mock_invocation_ctx.session.state = {}
        mock_invocation_ctx.user_id = "test_user"
        mock_invocation_ctx.agent = Mock()
        mock_invocation_ctx.agent.name = "test_agent"
        readonly_context = ReadonlyContext(
            invocation_context=mock_invocation_ctx,
        )

        # Get tools
        tools = await toolset.get_tools(readonly_context)

        # Verify only tools matching predicate are returned
        assert len(tools) == 2
        assert mock_mcp_tool1 in tools
        assert mock_mcp_tool3 in tools
        assert mock_mcp_tool2 not in tools


class TestVeIdentityMcpToolsetGetToolsWithPrefix:
    """Tests for VeIdentityMcpToolset.get_tools_with_prefix method."""

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    @patch("veadk.integrations.ve_identity.mcp_toolset.MCPSessionManager")
    @patch("veadk.integrations.ve_identity.mcp_toolset.VeIdentityMcpTool")
    async def test_get_tools_with_prefix_applies_correctly(
        self, mock_mcp_tool_class, mock_session_manager_class, mock_identity_client
    ):
        """Test that get_tools_with_prefix correctly adds prefix to tool names."""
        from google.adk.agents.readonly_context import ReadonlyContext

        # Setup mocks
        mock_session_manager = Mock()
        mock_session_manager_class.return_value = mock_session_manager
        mock_session = AsyncMock()
        mock_session_manager.create_session = AsyncMock(return_value=mock_session)

        # Create mock tools returned by MCP server
        mock_tool1 = Mock()
        mock_tool1.name = "read_file"
        mock_tool2 = Mock()
        mock_tool2.name = "write_file"

        mock_list_tools_result = Mock()
        mock_list_tools_result.tools = [mock_tool1, mock_tool2]
        mock_session.list_tools = AsyncMock(return_value=mock_list_tools_result)

        # Create mock VeIdentityMcpTool instances with proper name attributes
        mock_mcp_tool1 = Mock()
        mock_mcp_tool1.name = "read_file"
        mock_mcp_tool2 = Mock()
        mock_mcp_tool2.name = "write_file"

        mock_mcp_tool_class.side_effect = [mock_mcp_tool1, mock_mcp_tool2]

        # Create toolset with prefix
        connection_params = Mock()
        config = api_key_auth("test-provider")
        prefix = "github_"

        toolset = VeIdentityMcpToolset(
            auth_config=config,
            connection_params=connection_params,
            tool_name_prefix=prefix,
        )

        # Mock the credential
        toolset._get_credential = AsyncMock(return_value=Mock())

        # Create readonly context
        mock_invocation_ctx = Mock()
        mock_invocation_ctx.session = Mock()
        mock_invocation_ctx.session.state = {}
        mock_invocation_ctx.user_id = "test_user"
        mock_invocation_ctx.agent = Mock()
        mock_invocation_ctx.agent.name = "test_agent"
        readonly_context = ReadonlyContext(
            invocation_context=mock_invocation_ctx,
        )

        # Get tools with prefix via parent class method
        tools = await toolset.get_tools_with_prefix(readonly_context)

        # Verify tools have prefix applied (parent class adds underscore separator)
        assert len(tools) == 2
        assert tools[0].name == "github__read_file"
        assert tools[1].name == "github__write_file"

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    @patch("veadk.integrations.ve_identity.mcp_toolset.MCPSessionManager")
    @patch("veadk.integrations.ve_identity.mcp_toolset.VeIdentityMcpTool")
    async def test_get_tools_with_prefix_and_filter_combined(
        self, mock_mcp_tool_class, mock_session_manager_class, mock_identity_client
    ):
        """Test that get_tools_with_prefix works correctly with tool_filter combined."""
        from google.adk.agents.readonly_context import ReadonlyContext

        # Setup mocks
        mock_session_manager = Mock()
        mock_session_manager_class.return_value = mock_session_manager
        mock_session = AsyncMock()
        mock_session_manager.create_session = AsyncMock(return_value=mock_session)

        # Create mock tools returned by MCP server
        mock_tool1 = Mock()
        mock_tool1.name = "read_file"
        mock_tool2 = Mock()
        mock_tool2.name = "write_file"
        mock_tool3 = Mock()
        mock_tool3.name = "delete_file"

        mock_list_tools_result = Mock()
        mock_list_tools_result.tools = [mock_tool1, mock_tool2, mock_tool3]
        mock_session.list_tools = AsyncMock(return_value=mock_list_tools_result)

        # Create mock VeIdentityMcpTool instances
        mock_mcp_tool1 = Mock()
        mock_mcp_tool1.name = "read_file"
        mock_mcp_tool2 = Mock()
        mock_mcp_tool2.name = "write_file"
        mock_mcp_tool3 = Mock()
        mock_mcp_tool3.name = "delete_file"

        mock_mcp_tool_class.side_effect = [
            mock_mcp_tool1,
            mock_mcp_tool2,
            mock_mcp_tool3,
        ]

        # Create toolset with both prefix and filter
        connection_params = Mock()
        config = api_key_auth("test-provider")
        prefix = "github_"
        tool_filter = ["read_file", "write_file"]

        toolset = VeIdentityMcpToolset(
            auth_config=config,
            connection_params=connection_params,
            tool_name_prefix=prefix,
            tool_filter=tool_filter,
        )

        # Mock the credential
        toolset._get_credential = AsyncMock(return_value=Mock())

        # Create readonly context
        mock_invocation_ctx = Mock()
        mock_invocation_ctx.session = Mock()
        mock_invocation_ctx.session.state = {}
        mock_invocation_ctx.user_id = "test_user"
        mock_invocation_ctx.agent = Mock()
        mock_invocation_ctx.agent.name = "test_agent"
        readonly_context = ReadonlyContext(
            invocation_context=mock_invocation_ctx,
        )

        # Get tools with prefix via parent class method
        tools = await toolset.get_tools_with_prefix(readonly_context)

        # Verify only filtered tools have prefix applied (parent class adds underscore separator)
        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "github__read_file" in tool_names
        assert "github__write_file" in tool_names
        assert "github__delete_file" not in tool_names
