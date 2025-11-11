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

"""A2A request converter with authentication credential caching support.

This module provides an A2A request converter that extracts authentication
tokens from incoming requests, caches them for downstream use, and converts
requests to the format expected by the ADK runner.

Key Features:
- Extracts auth tokens from request context (auth field or Authorization header)
- Caches credentials in credential service for use by downstream agents
- Supports JWT token parsing to extract user_id from 'sub' claim
- Falls back to default user_id generation if JWT parsing fails
"""

import base64
import json
import logging
from typing import Optional

from a2a.server.agent_execution import RequestContext
from google.adk.a2a.converters.part_converter import (
    A2APartToGenAIPartConverter,
    convert_a2a_part_to_genai_part,
)
from google.adk.a2a.converters.request_converter import (
    A2ARequestToAgentRunRequestConverter,
    AgentRunRequest,
    _get_user_id,
)
from google.adk.runners import RunConfig
from google.genai import types as genai_types

from veadk.a2a.credentials import VeCredentialStore

logger = logging.getLogger(__name__)


def _strip_bearer_prefix(token: str) -> str:
    """Remove 'Bearer ' prefix from token if present.

    Args:
        token: Token string that may contain "Bearer " prefix

    Returns:
        Token without "Bearer " prefix
    """
    return token[7:] if token.lower().startswith("bearer ") else token


def _extract_user_id_from_jwt(token: str) -> Optional[str]:
    """Extract user_id (sub field) from JWT token.

    Args:
        token: JWT token string (with or without "Bearer " prefix)

    Returns:
        User ID from sub field, or None if parsing fails
    """
    try:
        # Remove "Bearer " prefix if present
        token = _strip_bearer_prefix(token)

        # JWT token has 3 parts separated by dots: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            return None

        # Decode payload (second part)
        payload_part = parts[1]

        # Add padding for base64url decoding (JWT doesn't use padding)
        missing_padding = len(payload_part) % 4
        if missing_padding:
            payload_part += "=" * (4 - missing_padding)

        # Decode base64 and parse JSON
        decoded_bytes = base64.urlsafe_b64decode(payload_part)
        payload = json.loads(decoded_bytes.decode("utf-8"))

        # Extract sub field as user_id
        user_id = payload.get("sub")
        if user_id:
            return str(user_id)

        return None

    except (ValueError, json.JSONDecodeError, Exception):
        return None


def _extract_auth_token_from_context(request: RequestContext) -> Optional[str]:
    """Extract authentication token from request context.

    Args:
        request: A2A request context

    Returns:
        Authentication token string, or None if not found
    """
    if not request.call_context or not request.call_context.state:
        return None

    state = request.call_context.state

    # Check auth field first
    if "auth" in state:
        return state["auth"]

    # Check authorization header
    if "headers" in state:
        headers = state["headers"]
        if isinstance(headers, dict):
            return headers.get("authorization") or headers.get("Authorization")

    return None


def _get_user_id_from_auth_token(request: RequestContext) -> str:
    """Get user_id from request, preferring JWT sub field if available.

    Args:
        request: A2A request context

    Returns:
        User ID string
    """
    # Try to extract auth token from context
    auth_token = _extract_auth_token_from_context(request)

    if auth_token:
        # Try to parse JWT and extract user_id
        user_id = _extract_user_id_from_jwt(auth_token)
        if user_id:
            return user_id

    # Fallback to original _get_user_id logic
    return _get_user_id(request)


class AuthenticatedA2ARequestConverter:
    """Converts authenticated A2A requests to AgentRunRequest with credential caching.

    This converter implements the A2ARequestToAgentRunRequestConverter interface
    and provides additional functionality for extracting and caching authentication
    credentials from incoming A2A requests.

    The converter:
    1. Extracts auth tokens from request context (state["auth"] or headers)
    2. Caches credentials in the credential service for downstream use
    3. Attempts to extract user_id from JWT tokens (via 'sub' claim)
    4. Falls back to default user_id generation if JWT parsing fails
    5. Converts A2A RequestContext to AgentRunRequest for the ADK runner

    This follows the A2A SDK pattern of providing converter builders that
    return converter functions matching the A2ARequestToAgentRunRequestConverter
    type signature.
    """

    def __init__(self, credential_service: VeCredentialStore):
        """Initialize the converter with a credential service.

        Args:
            credential_service: Service for caching authentication credentials.
                This service will be used to store extracted tokens for use
                by downstream agents or services.

        Raises:
            ValueError: If credential_service is None
        """
        if credential_service is None:
            raise ValueError("Credential service must be provided")

        self.credential_service = credential_service

    def build_converter(self) -> A2ARequestToAgentRunRequestConverter:
        """Build and return a converter function for authenticated requests.

        Returns:
            A converter function matching the A2ARequestToAgentRunRequestConverter
            signature that:
            - Extracts auth tokens from request context
            - Caches credentials in the credential service
            - Extracts user_id from JWT if available
            - Converts RequestContext to AgentRunRequest
        """

        def converter(
            request: RequestContext,
            part_converter: A2APartToGenAIPartConverter = convert_a2a_part_to_genai_part,
        ) -> AgentRunRequest:
            """Converts an A2A RequestContext to an AgentRunRequest model.

            Args:
                request: The incoming request context from the A2A server.
                part_converter: A function to convert A2A content parts to GenAI parts.

            Returns:
                A AgentRunRequest object ready to be used as arguments for the ADK runner.

            Raises:
                ValueError: If the request message is None.
            """

            if not request.message:
                raise ValueError("Request message cannot be None")

            # Extract and cache credentials from request context
            auth_token = _extract_auth_token_from_context(request)
            user_id = _get_user_id_from_auth_token(request)

            if auth_token:
                # Strip "Bearer " prefix before storing
                credential = _strip_bearer_prefix(auth_token)

                self.credential_service.set_credentials(
                    session_id=request.context_id,
                    user_id=user_id,
                    security_scheme_name="inbound_auth",
                    credential=credential,
                )
                logger.debug(
                    f"Cached credential for session {request.context_id} and user {user_id}"
                )
            else:
                logger.debug(
                    f"No auth token found in request context for session {request.context_id}"
                )

            return AgentRunRequest(
                user_id=_get_user_id_from_auth_token(request),
                session_id=request.context_id,
                new_message=genai_types.Content(
                    role="user",
                    parts=[part_converter(part) for part in request.message.parts],
                ),
                run_config=RunConfig(),
            )

        return converter
