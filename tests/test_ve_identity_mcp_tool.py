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


"""Unit tests for VeIdentityMcpTool."""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from veadk.integrations.ve_identity.mcp_tool import VeIdentityMcpTool
from veadk.integrations.ve_identity.auth_config import api_key_auth, oauth2_auth
from veadk.integrations.ve_identity.auth_mixins import AuthRequiredException


class TestVeIdentityMcpToolInit:
    """Tests for VeIdentityMcpTool initialization."""

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_init_with_api_key_auth(self, mock_identity_client):
        """Test initializing with API key auth config."""
        mcp_tool = Mock()
        mcp_tool.name = "test_tool"
        mcp_tool.description = "Test tool description"

        mcp_session_manager = Mock()
        config = api_key_auth("test-provider")

        tool = VeIdentityMcpTool(
            mcp_tool=mcp_tool,
            mcp_session_manager=mcp_session_manager,
            auth_config=config,
        )

        assert tool.name == "test_tool"
        assert tool.description == "Test tool description"
        assert tool._mcp_tool == mcp_tool
        assert tool._mcp_session_manager == mcp_session_manager

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_init_with_oauth2_auth(self, mock_identity_client):
        """Test initializing with OAuth2 auth config."""
        mcp_tool = Mock()
        mcp_tool.name = "github_tool"
        mcp_tool.description = "GitHub tool"

        mcp_session_manager = Mock()
        config = oauth2_auth(provider_name="github", scopes=["repo"], auth_flow="M2M")

        tool = VeIdentityMcpTool(
            mcp_tool=mcp_tool,
            mcp_session_manager=mcp_session_manager,
            auth_config=config,
        )

        assert tool.name == "github_tool"
        assert tool._auth_config == config

    def test_init_with_none_mcp_tool(self):
        """Test that initialization fails with None mcp_tool."""
        mcp_session_manager = Mock()
        config = api_key_auth("test-provider")

        with pytest.raises(ValueError, match="mcp_tool cannot be None"):
            VeIdentityMcpTool(
                mcp_tool=None,
                mcp_session_manager=mcp_session_manager,
                auth_config=config,
            )

    def test_init_with_none_mcp_session_manager(self):
        """Test that initialization fails with None mcp_session_manager."""
        mcp_tool = Mock()
        mcp_tool.name = "test_tool"
        mcp_tool.description = "Test"
        config = api_key_auth("test-provider")

        with pytest.raises(ValueError, match="mcp_session_manager cannot be None"):
            VeIdentityMcpTool(
                mcp_tool=mcp_tool, mcp_session_manager=None, auth_config=config
            )


class TestVeIdentityMcpToolRunAsync:
    """Tests for VeIdentityMcpTool.run_async method."""

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    async def test_run_async_with_api_key(self, mock_identity_client):
        """Test run_async with API key authentication."""
        mcp_tool = Mock()
        mcp_tool.name = "test_tool"
        mcp_tool.description = "Test"

        mcp_session_manager = Mock()
        config = api_key_auth("test-provider")

        tool = VeIdentityMcpTool(
            mcp_tool=mcp_tool,
            mcp_session_manager=mcp_session_manager,
            auth_config=config,
        )

        # Mock the run_with_identity_auth method
        tool.run_with_identity_auth = AsyncMock(return_value="Result: test-key")

        tool_context = Mock()
        result = await tool.run_async(args={}, tool_context=tool_context)

        assert result == "Result: test-key"
        tool.run_with_identity_auth.assert_called_once()

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    async def test_run_async_handles_auth_required_exception(
        self, mock_identity_client
    ):
        """Test that run_async handles AuthRequiredException."""
        mcp_tool = Mock()
        mcp_tool.name = "test_tool"
        mcp_tool.description = "Test"

        mcp_session_manager = Mock()
        config = oauth2_auth(
            provider_name="github", scopes=["repo"], auth_flow="USER_FEDERATION"
        )

        tool = VeIdentityMcpTool(
            mcp_tool=mcp_tool,
            mcp_session_manager=mcp_session_manager,
            auth_config=config,
        )

        # Mock the run_with_identity_auth to raise AuthRequiredException
        auth_exception = AuthRequiredException("Please authorize")
        tool.run_with_identity_auth = AsyncMock(side_effect=auth_exception)

        tool_context = Mock()
        result = await tool.run_async(args={}, tool_context=tool_context)

        assert result == "Please authorize"
