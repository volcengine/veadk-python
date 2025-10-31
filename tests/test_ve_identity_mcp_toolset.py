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
        assert toolset._tool_filter is None
        assert toolset._tool_name_prefix is None

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

        assert toolset._tool_filter == tool_filter

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

        assert toolset._tool_name_prefix == prefix

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
