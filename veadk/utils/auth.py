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

"""Authentication utilities for VeADK.

This module provides utilities for authentication, including:
- JWT token parsing and delegation chain extraction
- AuthConfig building for various authentication methods
- TIP (Trust Identity Propagation) token management
- Workload token caching for middleware
"""

import base64
import json
from typing import Literal, Optional

from google.adk.auth.auth_credential import (
    AuthCredential,
    AuthCredentialTypes,
    HttpAuth,
    HttpCredentials,
)
from fastapi.openapi.models import APIKey, HTTPBearer, APIKeyIn
from google.adk.auth.auth_tool import AuthConfig

# TIP Token Header is used for Trust Identity Propagation (TIP) tokens
VE_TIP_TOKEN_HEADER = "X-Ve-TIP-Token"
VE_TIP_TOKEN_CREDENTIAL_KEY = "ve_tip_token"


def strip_bearer_prefix(token: str) -> str:
    """Remove 'Bearer ' prefix from token if present.

    Args:
        token: Token string that may contain "Bearer " prefix

    Returns:
        Token without "Bearer " prefix
    """
    return token[7:] if token.lower().startswith("bearer ") else token


def extract_delegation_chain_from_jwt(token: str) -> tuple[Optional[str], list[str]]:
    """Extract subject and delegation chain from JWT token.

    Parses JWT tokens containing delegation information per RFC 8693.
    Returns the primary subject and the chain of actors who acted on behalf.

    Args:
        token: JWT token string (with or without "Bearer " prefix)

    Returns:
        A tuple of (subject, actors) where:
        - subject: The end user or resource owner (from `sub` field)
        - actors: Chain of intermediaries who acted on behalf (from nested `act` claims)

    Examples:
        ```python
        # User → Agent1 → Agent2
        subject, actors = extract_delegation_chain_from_jwt(token)
        # Returns: ("user1", ["agent2", "agent1"])
        # Meaning: user1 delegated to agent1, who delegated to agent2
        ```
    """
    try:
        # Remove "Bearer " prefix if present
        token = strip_bearer_prefix(token)

        # JWT token has 3 parts separated by dots: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            return None, []

        # Decode payload (second part)
        payload_part = parts[1]

        # Add padding for base64url decoding (JWT doesn't use padding)
        missing_padding = len(payload_part) % 4
        if missing_padding:
            payload_part += "=" * (4 - missing_padding)

        # Decode base64 and parse JSON
        decoded_bytes = base64.urlsafe_b64decode(payload_part)
        payload: dict = json.loads(decoded_bytes.decode("utf-8"))

        # Extract subject from JWT
        subject = payload.get("sub")
        if not subject:
            return None, []

        # Extract actor chain from nested "act" claims
        actors = []
        current_act = payload.get("act")
        while current_act and isinstance(current_act, dict):
            actor_sub = current_act.get("sub")
            if actor_sub:
                actors.append(str(actor_sub))
            # Move to next level in the chain
            current_act = current_act.get("act")

        return str(subject), actors

    except (ValueError, json.JSONDecodeError, Exception):
        return None, []


def _build_http_bearer_auth(
    token: Optional[str], scheme: str
) -> tuple[HTTPBearer, Optional[AuthCredential]]:
    """Build HTTP Bearer authentication scheme and credential.

    Args:
        token: The authentication token
        scheme: HTTP authentication scheme (e.g., "bearer", "basic")

    Returns:
        Tuple of (auth_scheme, auth_credential)
    """
    auth_scheme = HTTPBearer()

    auth_credential = None
    if token:
        auth_credential = AuthCredential(
            auth_type=AuthCredentialTypes.HTTP,
            http=HttpAuth(
                scheme=scheme.lower(),
                credentials=HttpCredentials(token=token),
            ),
        )

    return auth_scheme, auth_credential


def _build_api_key_header_auth(
    token: Optional[str], header_name: str
) -> tuple[APIKey, Optional[AuthCredential]]:
    """Build API Key in header authentication scheme and credential.

    Args:
        token: The authentication token
        header_name: Name of the HTTP header

    Returns:
        Tuple of (auth_scheme, auth_credential)
    """
    auth_scheme = APIKey(**{"in": APIKeyIn.header, "name": header_name})

    auth_credential = None
    if token:
        auth_credential = AuthCredential(
            auth_type=AuthCredentialTypes.API_KEY,
            api_key=token,
        )

    return auth_scheme, auth_credential


def _build_api_key_query_auth(
    token: Optional[str], query_param_name: str
) -> tuple[APIKey, Optional[AuthCredential]]:
    """Build API Key in query string authentication scheme and credential.

    Args:
        token: The authentication token
        query_param_name: Name of the query parameter

    Returns:
        Tuple of (auth_scheme, auth_credential)
    """
    auth_scheme = APIKey(**{"in": APIKeyIn.query, "name": query_param_name})

    auth_credential = None
    if token:
        auth_credential = AuthCredential(
            auth_type=AuthCredentialTypes.API_KEY,
            api_key=token,
        )

    return auth_scheme, auth_credential


def build_auth_config(
    *,
    credential_key: str,
    token: Optional[str] = None,
    auth_method: Literal["header", "querystring", "bearer", "apikey"] = "header",
    # Header-specific options
    header_name: str = "Authorization",
    header_scheme: Optional[str] = None,
    # Query string-specific options
    query_param_name: str = "token",
) -> AuthConfig:
    """Build AuthConfig for various authentication methods.

    This is a general-purpose utility function for constructing AuthConfig objects
    that can be used with ADK's credential service. It supports multiple authentication
    methods and provides flexible configuration options.

    Args:
        token: The authentication token/credential value. If None, only the auth scheme
            will be configured without credentials.
        auth_method: The authentication method to use:
            - "header": Generic header-based authentication (API Key in header)
            - "bearer": HTTP Bearer token authentication (Authorization: Bearer <token>)
            - "querystring" or "apikey": API Key in query string parameter
        credential_key: Key to identify this credential in the credential service.
            Default is "inbound_auth".
        header_name: Name of the HTTP header for header-based auth. Default is "Authorization".
        header_scheme: HTTP authentication scheme (e.g., "bearer", "basic"). If provided,
            uses HTTP auth; otherwise uses API Key auth for headers.
        query_param_name: Name of the query parameter for query string auth. Default is "token".

    Returns:
        AuthConfig object with the appropriate auth scheme and credential.

    Raises:
        ValueError: If an unsupported auth_method is provided.

    Examples:
        ```python
        # Example 1: HTTP Bearer token
        config = build_auth_config(
            token="eyJhbGc...",
            auth_method="bearer",
            credential_key="my_auth"
        )

        # Example 2: API Key in header
        config = build_auth_config(
            token="sk-1234567890",
            auth_method="header",
            header_name="X-API-Key",
            credential_key="api_key_auth"
        )

        # Example 3: API Key in query string
        config = build_auth_config(
            token="abc123",
            auth_method="querystring",
            query_param_name="api_key",
            credential_key="query_auth"
        )

        # Example 4: Only auth scheme (no credential)
        config = build_auth_config(
            auth_method="bearer",
            credential_key="bearer_auth"
        )
        # Returns AuthConfig with scheme but no credential
        ```
    """
    # Determine which builder function to use based on auth_method
    if auth_method == "bearer":
        # Bearer is a special case of HTTP auth with bearer scheme
        auth_scheme, auth_credential = _build_http_bearer_auth(token, "bearer")

    elif auth_method == "header":
        if header_scheme:
            # HTTP authentication (e.g., Bearer, Basic)
            auth_scheme, auth_credential = _build_http_bearer_auth(token, header_scheme)
        else:
            # API Key in header
            auth_scheme, auth_credential = _build_api_key_header_auth(
                token, header_name
            )

    elif auth_method in ("querystring", "apikey"):
        # API Key in query string
        auth_scheme, auth_credential = _build_api_key_query_auth(
            token, query_param_name
        )

    else:
        raise ValueError(
            f"Unsupported auth_method: {auth_method}. "
            f"Supported methods: 'header', 'bearer', 'querystring', 'apikey'"
        )

    return AuthConfig(
        auth_scheme=auth_scheme,
        exchanged_auth_credential=auth_credential,
        credential_key=credential_key,
    )
