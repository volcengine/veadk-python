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

"""Unit tests for AuthenticatedA2ARequestConverter."""

import base64
import json

import pytest

from a2a.server.agent_execution import RequestContext
from a2a.server.context import ServerCallContext
from a2a.types import Message, TextPart, Role, Part, MessageSendParams

from veadk.a2a.credentials import VeCredentialStore
from veadk.a2a.ve_request_converter import AuthenticatedA2ARequestConverter


def create_test_message_params(text: str) -> MessageSendParams:
    """Helper function to create a test MessageSendParams object."""
    return MessageSendParams(
        message=Message(
            message_id="test-msg",
            role=Role.agent,
            parts=[Part(root=TextPart(text=text))],
        )
    )


class TestAuthenticatedA2ARequestConverter:
    """Test suite for AuthenticatedA2ARequestConverter."""

    def test_build_converter_without_credential_service(self):
        """Test building converter raises error without credential service."""
        with pytest.raises(ValueError, match="Credential service must be provided"):
            AuthenticatedA2ARequestConverter(credential_service=None)

    def test_build_converter_with_credential_service(self):
        """Test building converter with credential service."""
        credential_service = VeCredentialStore()
        converter_builder = AuthenticatedA2ARequestConverter(
            credential_service=credential_service,
        )

        converter = converter_builder.build_converter()
        assert converter is not None
        assert callable(converter)

    def test_extract_user_id_from_jwt(self):
        """Test extracting user_id from JWT token."""
        # Create a mock JWT token with user_id in payload
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"sub": "user_from_jwt", "exp": 9999999999}
        signature = "mock_signature"

        # Encode JWT parts
        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        jwt_token = f"{header_b64}.{payload_b64}.{signature}"

        credential_service = VeCredentialStore()
        converter_builder = AuthenticatedA2ARequestConverter(
            credential_service=credential_service,
        )

        # Create request context with JWT token
        request = RequestContext(
            request=create_test_message_params("test message"),
            context_id="test_context",
            call_context=ServerCallContext(
                state={"headers": {"authorization": f"Bearer {jwt_token}"}}
            ),
        )

        converter = converter_builder.build_converter()
        agent_run_request = converter(request)

        # Verify user_id was extracted from JWT
        assert agent_run_request.user_id == "user_from_jwt"

    def test_fallback_to_default_user_id(self):
        """Test fallback to default user_id when no JWT is provided."""
        credential_service = VeCredentialStore()
        converter_builder = AuthenticatedA2ARequestConverter(
            credential_service=credential_service,
        )

        # Create request context without authorization header
        request = RequestContext(
            request=create_test_message_params("test message"),
            context_id="test_context",
            call_context=ServerCallContext(state={}),
        )

        converter = converter_builder.build_converter()
        agent_run_request = converter(request)

        # Verify default user_id is used
        assert agent_run_request.user_id == "A2A_USER_test_context"

    def test_credential_caching_by_user_id(self):
        """Test that credentials are cached by user ID when extracted from JWT."""
        credential_service = VeCredentialStore()
        converter_builder = AuthenticatedA2ARequestConverter(
            credential_service=credential_service,
        )

        # Create a mock JWT token
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"sub": "user_from_jwt", "exp": 9999999999}
        signature = "mock_signature"

        header_b64 = (
            base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        )
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        jwt_token = f"{header_b64}.{payload_b64}.{signature}"

        # Create request context with JWT token
        request = RequestContext(
            request=create_test_message_params("test message"),
            context_id="test_session_456",
            call_context=ServerCallContext(
                state={"headers": {"authorization": f"Bearer {jwt_token}"}}
            ),
        )

        converter = converter_builder.build_converter()
        converter(request)

        # Verify credential was cached by user ID
        cached_by_user = credential_service._store.get("user_from_jwt", {}).get(
            "inbound_auth"
        )

        assert cached_by_user == jwt_token

    def test_no_credential_caching_without_service(self):
        """Test that no caching occurs when credential_service is not provided."""
        # This test is no longer valid since credential_service is required
        # Instead, test that ValueError is raised
        with pytest.raises(ValueError, match="Credential service must be provided"):
            AuthenticatedA2ARequestConverter(credential_service=None)

    def test_case_insensitive_authorization_header(self):
        """Test that authorization header is case-insensitive."""
        credential_service = VeCredentialStore()
        converter_builder = AuthenticatedA2ARequestConverter(
            credential_service=credential_service,
        )

        # Test with different case variations
        test_cases = [
            "authorization",
            "Authorization",
        ]

        for header_name in test_cases:
            bearer_token = f"token_for_{header_name}"
            request = RequestContext(
                request=create_test_message_params("test message"),
                context_id=f"session_{header_name}",
                call_context=ServerCallContext(
                    state={"headers": {header_name: f"Bearer {bearer_token}"}}
                ),
            )

            converter = converter_builder.build_converter()
            converter(request)

            # Verify credential was cached
            cached_token = credential_service._store.get(
                f"A2A_USER_session_{header_name}", {}
            ).get("inbound_auth")
            assert cached_token == bearer_token

    def test_invalid_jwt_fallback(self):
        """Test that invalid JWT falls back to default user_id."""
        credential_service = VeCredentialStore()
        converter_builder = AuthenticatedA2ARequestConverter(
            credential_service=credential_service,
        )

        # Create request context with invalid JWT (only 2 parts instead of 3)
        invalid_jwt = "invalid.jwt"
        request = RequestContext(
            request=create_test_message_params("test message"),
            context_id="test_session_invalid",
            call_context=ServerCallContext(
                state={"headers": {"authorization": f"Bearer {invalid_jwt}"}}
            ),
        )

        converter = converter_builder.build_converter()
        agent_run_request = converter(request)

        # Verify default user_id is used
        assert agent_run_request.user_id == "A2A_USER_test_session_invalid"

        # Verify credential was still cached (even though JWT is invalid)
        cached_token = credential_service._store.get(
            "A2A_USER_test_session_invalid", {}
        ).get("inbound_auth")
        assert cached_token == invalid_jwt
