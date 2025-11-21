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

"""Unit tests for A2A authentication middleware."""

import pytest
from unittest.mock import Mock, patch
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

from veadk.a2a.ve_middlewares import A2AAuthMiddleware, build_a2a_auth_middleware
from veadk.auth.ve_credential_service import VeCredentialService
from veadk.utils.auth import VE_TIP_TOKEN_HEADER


@pytest.fixture
def credential_service():
    """Create a VeCredentialService instance for testing."""
    return VeCredentialService()


@pytest.fixture
def mock_identity_client():
    """Create a mock IdentityClient."""
    mock_client = Mock()
    mock_client.get_workload_access_token = Mock()
    return mock_client


@pytest.fixture
def sample_jwt_token():
    """Sample JWT token for testing."""
    # This is a sample JWT with sub="user123" and act claim
    # Header: {"alg": "HS256", "typ": "JWT"}
    # Payload: {"sub": "user123", "act": {"sub": "agent1"}}
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIiwiYWN0Ijp7InN1YiI6ImFnZW50MSJ9fQ.signature"


class TestA2AAuthMiddleware:
    """Tests for A2AAuthMiddleware class."""

    def test_middleware_initialization(self, credential_service, mock_identity_client):
        """Test middleware initialization with all parameters."""
        app = Starlette()
        middleware = A2AAuthMiddleware(
            app=app,
            app_name="test_app",
            credential_service=credential_service,
            auth_method="header",
            token_param="token",
            credential_key="test_key",
            identity_client=mock_identity_client,
        )

        assert middleware.app_name == "test_app"
        assert middleware.credential_service == credential_service
        assert middleware.auth_method == "header"
        assert middleware.token_param == "token"
        assert middleware.credential_key == "test_key"
        assert middleware.identity_client == mock_identity_client

    def test_middleware_default_identity_client(self, credential_service):
        """Test middleware uses global identity client when not provided."""
        app = Starlette()

        with patch(
            "veadk.a2a.ve_middlewares.get_default_identity_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client

            middleware = A2AAuthMiddleware(
                app=app,
                app_name="test_app",
                credential_service=credential_service,
            )

            mock_get_client.assert_called_once()
            assert middleware.identity_client == mock_client

    def test_extract_token_from_header_with_bearer(self, credential_service):
        """Test extracting token from Authorization header with Bearer prefix."""
        app = Starlette()
        middleware = A2AAuthMiddleware(
            app=app,
            app_name="test_app",
            credential_service=credential_service,
            auth_method="header",
        )

        # Create mock request
        mock_request = Mock(spec=Request)
        mock_request.headers = {"Authorization": "Bearer test_token_123"}

        token, has_prefix = middleware._extract_token(mock_request)

        assert token == "test_token_123"
        assert has_prefix is True

    def test_extract_token_from_header_without_bearer(self, credential_service):
        """Test extracting token from Authorization header without Bearer prefix."""
        app = Starlette()
        middleware = A2AAuthMiddleware(
            app=app,
            app_name="test_app",
            credential_service=credential_service,
            auth_method="header",
        )

        mock_request = Mock(spec=Request)
        mock_request.headers = {"Authorization": "test_token_123"}

        token, has_prefix = middleware._extract_token(mock_request)

        assert token == "test_token_123"
        assert has_prefix is False

    def test_extract_token_from_query_string(self, credential_service):
        """Test extracting token from query string."""
        app = Starlette()
        middleware = A2AAuthMiddleware(
            app=app,
            app_name="test_app",
            credential_service=credential_service,
            auth_method="querystring",
            token_param="access_token",
        )

        mock_request = Mock(spec=Request)
        mock_request.query_params = {"access_token": "test_token_123"}

        token, has_prefix = middleware._extract_token(mock_request)

        assert token == "test_token_123"
        assert has_prefix is False

    def test_extract_token_no_token_found(self, credential_service):
        """Test extracting token when no token is present."""
        app = Starlette()
        middleware = A2AAuthMiddleware(
            app=app,
            app_name="test_app",
            credential_service=credential_service,
            auth_method="header",
        )

        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        token, has_prefix = middleware._extract_token(mock_request)

        assert token is None
        assert has_prefix is False

    @pytest.mark.asyncio
    async def test_dispatch_with_valid_jwt_token(
        self, credential_service, mock_identity_client, sample_jwt_token
    ):
        """Test dispatch with valid JWT token."""
        app = Starlette()

        # Mock WorkloadToken
        mock_workload_token = Mock()
        mock_workload_token.workload_access_token = "workload_token_123"
        mock_workload_token.expires_at = 1234567890
        mock_identity_client.get_workload_access_token.return_value = (
            mock_workload_token
        )

        middleware = A2AAuthMiddleware(
            app=app,
            app_name="test_app",
            credential_service=credential_service,
            auth_method="header",
            identity_client=mock_identity_client,
        )

        # Create mock request with JWT token
        mock_request = Mock(spec=Request)
        mock_request.headers = {
            "Authorization": f"Bearer {sample_jwt_token}",
        }
        mock_request.scope = {}

        # Mock call_next
        async def mock_call_next(request):
            return Response("OK", status_code=200)

        # Execute dispatch
        with patch(
            "veadk.a2a.ve_middlewares.extract_delegation_chain_from_jwt"
        ) as mock_extract:
            mock_extract.return_value = ("user123", ["agent1"])

            with patch(
                "veadk.a2a.ve_middlewares.build_auth_config"
            ) as mock_build_config:
                mock_auth_config = Mock()
                mock_auth_config.exchanged_auth_credential = Mock()
                mock_build_config.return_value = mock_auth_config

                response = await middleware.dispatch(mock_request, mock_call_next)

        # Verify response
        assert response.status_code == 200

        # Verify user was set in request scope
        assert "user" in mock_request.scope
        assert mock_request.scope["user"].username == "user123"

        # Verify workload token was set
        assert "auth" in mock_request.scope
        assert mock_request.scope["auth"] == mock_workload_token

    @pytest.mark.asyncio
    async def test_dispatch_with_tip_token(
        self, credential_service, mock_identity_client, sample_jwt_token
    ):
        """Test dispatch with TIP token in header."""
        app = Starlette()

        # Mock WorkloadToken
        mock_workload_token = Mock()
        mock_workload_token.workload_access_token = "workload_token_from_tip"
        mock_workload_token.expires_at = 1234567890
        mock_identity_client.get_workload_access_token.return_value = (
            mock_workload_token
        )

        middleware = A2AAuthMiddleware(
            app=app,
            app_name="test_app",
            credential_service=credential_service,
            auth_method="header",
            identity_client=mock_identity_client,
        )

        # Create mock request with both JWT and TIP token
        tip_token = "tip_token_123"
        mock_request = Mock(spec=Request)
        mock_request.headers = {
            "Authorization": f"Bearer {sample_jwt_token}",
            VE_TIP_TOKEN_HEADER: tip_token,
        }
        mock_request.scope = {}

        # Mock call_next
        async def mock_call_next(request):
            return Response("OK", status_code=200)

        # Execute dispatch
        with patch(
            "veadk.a2a.ve_middlewares.extract_delegation_chain_from_jwt"
        ) as mock_extract:
            mock_extract.return_value = ("user123", ["agent1"])

            with patch(
                "veadk.a2a.ve_middlewares.build_auth_config"
            ) as mock_build_config:
                mock_auth_config = Mock()
                mock_auth_config.exchanged_auth_credential = Mock()
                mock_build_config.return_value = mock_auth_config

                _ = await middleware.dispatch(mock_request, mock_call_next)

        # Verify TIP token was used for workload token exchange
        mock_identity_client.get_workload_access_token.assert_called_once_with(
            user_token=tip_token, user_id="user123"
        )

        # Verify workload token was set
        assert mock_request.scope["auth"] == mock_workload_token


class TestBuildA2AAuthMiddleware:
    """Tests for build_a2a_auth_middleware factory function."""

    def test_build_middleware_basic(self, credential_service):
        """Test building middleware with basic parameters."""
        middleware_class = build_a2a_auth_middleware(
            app_name="test_app",
            credential_service=credential_service,
        )

        assert middleware_class is not None
        assert issubclass(middleware_class, A2AAuthMiddleware)

    def test_build_middleware_with_all_params(
        self, credential_service, mock_identity_client
    ):
        """Test building middleware with all parameters."""
        middleware_class = build_a2a_auth_middleware(
            app_name="test_app",
            credential_service=credential_service,
            auth_method="querystring",
            token_param="access_token",
            credential_key="custom_key",
            identity_client=mock_identity_client,
        )

        # Create instance to verify parameters
        app = Starlette()
        instance = middleware_class(app)

        assert instance.app_name == "test_app"
        assert instance.auth_method == "querystring"
        assert instance.token_param == "access_token"
        assert instance.credential_key == "custom_key"
        assert instance.identity_client == mock_identity_client
