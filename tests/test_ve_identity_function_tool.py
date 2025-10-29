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

"""Unit tests for VeIdentityFunctionTool."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from veadk.integrations.ve_identity.function_tool import VeIdentityFunctionTool
from veadk.integrations.ve_identity.auth_config import (
    api_key_auth,
    oauth2_auth,
    workload_auth,
)


class TestVeIdentityFunctionToolInit:
    """Tests for VeIdentityFunctionTool initialization."""

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_init_with_api_key_auth(self, mock_identity_client):
        """Test initializing with API key auth config."""

        async def test_func(api_key: str):
            return f"Called with {api_key}"

        # Create auth config - IdentityClient will be mocked
        config = api_key_auth("test-provider")
        tool = VeIdentityFunctionTool(func=test_func, auth_config=config)

        assert tool.func == test_func
        assert tool._auth_config == config
        assert tool._into == "api_key"

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_init_with_oauth2_auth(self, mock_identity_client):
        """Test initializing with OAuth2 auth config."""

        async def test_func(access_token: str):
            return f"Called with {access_token}"

        config = oauth2_auth(provider_name="github", scopes=["repo"], auth_flow="M2M")
        tool = VeIdentityFunctionTool(func=test_func, auth_config=config)

        assert tool.func == test_func
        assert tool._auth_config == config
        assert tool._into == "access_token"

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_init_with_workload_auth(self, mock_identity_client):
        """Test initializing with workload auth config."""

        async def test_func(access_token: str):
            return f"Called with {access_token}"

        config = workload_auth("test-provider")
        tool = VeIdentityFunctionTool(func=test_func, auth_config=config)

        assert tool.func == test_func
        assert tool._auth_config == config
        assert tool._into == "access_token"

    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    def test_init_with_custom_into_parameter(self, mock_identity_client):
        """Test initializing with custom 'into' parameter."""

        async def test_func(custom_token: str):
            return f"Called with {custom_token}"

        config = api_key_auth("test-provider")
        tool = VeIdentityFunctionTool(
            func=test_func, auth_config=config, into="custom_token"
        )

        assert tool._into == "custom_token"

    def test_init_with_unsupported_auth_config(self):
        """Test that unsupported auth config raises ValueError."""

        async def test_func(token: str):
            return f"Called with {token}"

        # Create an invalid auth config
        invalid_config = Mock()
        invalid_config.__class__.__name__ = "InvalidAuthConfig"

        with pytest.raises(ValueError, match="Unsupported auth config type"):
            VeIdentityFunctionTool(func=test_func, auth_config=invalid_config)


class TestVeIdentityFunctionToolRunAsync:
    """Tests for VeIdentityFunctionTool.run_async method."""

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    async def test_run_async_with_api_key(self, mock_identity_client):
        """Test run_async with API key authentication."""

        async def test_func(api_key: str):
            return f"Result: {api_key}"

        config = api_key_auth("test-provider")
        tool = VeIdentityFunctionTool(func=test_func, auth_config=config)

        # Mock the run_with_identity_auth method
        tool.run_with_identity_auth = AsyncMock(return_value="Result: test-key")

        tool_context = Mock()
        result = await tool.run_async(args={}, tool_context=tool_context)

        assert result == "Result: test-key"
        tool.run_with_identity_auth.assert_called_once()

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    async def test_run_async_with_oauth2(self, mock_identity_client):
        """Test run_async with OAuth2 authentication."""

        async def test_func(access_token: str):
            return f"Result: {access_token}"

        config = oauth2_auth(provider_name="github", scopes=["repo"], auth_flow="M2M")
        tool = VeIdentityFunctionTool(func=test_func, auth_config=config)

        # Mock the run_with_identity_auth method
        tool.run_with_identity_auth = AsyncMock(return_value="Result: test-token")

        tool_context = Mock()
        result = await tool.run_async(args={}, tool_context=tool_context)

        assert result == "Result: test-token"
        tool.run_with_identity_auth.assert_called_once()

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    async def test_run_async_handles_auth_required_exception(
        self, mock_identity_client
    ):
        """Test that run_async handles AuthRequiredException."""
        from veadk.integrations.ve_identity.auth_mixins import AuthRequiredException

        async def test_func(access_token: str):
            return f"Result: {access_token}"

        config = oauth2_auth(
            provider_name="github", scopes=["repo"], auth_flow="USER_FEDERATION"
        )
        tool = VeIdentityFunctionTool(func=test_func, auth_config=config)

        # Mock the run_with_identity_auth to raise AuthRequiredException
        auth_exception = AuthRequiredException("Please authorize")
        tool.run_with_identity_auth = AsyncMock(side_effect=auth_exception)

        tool_context = Mock()
        result = await tool.run_async(args={}, tool_context=tool_context)

        assert result == "Please authorize"


class TestVeIdentityFunctionToolExecuteWithCredential:
    """Tests for VeIdentityFunctionTool._execute_with_credential method."""

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    async def test_execute_with_credential_injects_api_key(self, mock_identity_client):
        """Test that _execute_with_credential injects API key."""

        async def test_func(api_key: str):
            return f"Result: {api_key}"

        config = api_key_auth("test-provider")
        tool = VeIdentityFunctionTool(func=test_func, auth_config=config)

        # Mock credential
        credential = Mock()
        credential.api_key = "test-api-key"

        # Mock parent's run_async
        with patch.object(
            tool.__class__.__bases__[1], "run_async", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = "Result: test-api-key"

            tool_context = Mock()
            await tool._execute_with_credential(
                args={}, tool_context=tool_context, credential=credential
            )

            # Verify that run_async was called with injected api_key
            call_args = mock_run.call_args
            assert call_args[1]["args"]["api_key"] == "test-api-key"

    @pytest.mark.asyncio
    @patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient")
    async def test_execute_with_credential_injects_oauth2_token(
        self, mock_identity_client
    ):
        """Test that _execute_with_credential injects OAuth2 access token."""

        async def test_func(access_token: str):
            return f"Result: {access_token}"

        config = oauth2_auth(provider_name="github", scopes=["repo"], auth_flow="M2M")
        tool = VeIdentityFunctionTool(func=test_func, auth_config=config)

        # Mock credential
        credential = Mock()
        credential.oauth2 = Mock()
        credential.oauth2.access_token = "test-oauth2-token"

        # Mock parent's run_async
        with patch.object(
            tool.__class__.__bases__[1], "run_async", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = "Result: test-oauth2-token"

            tool_context = Mock()
            await tool._execute_with_credential(
                args={}, tool_context=tool_context, credential=credential
            )

            # Verify that run_async was called with injected access_token
            call_args = mock_run.call_args
            assert call_args[1]["args"]["access_token"] == "test-oauth2-token"
