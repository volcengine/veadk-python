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

"""Data models for veIdentity integration."""

from __future__ import annotations

from typing import Any, Callable, Optional, TYPE_CHECKING, List

from pydantic import BaseModel, model_validator, field_validator
from google.adk.auth.auth_credential import OAuth2Auth

if TYPE_CHECKING:
    from veadk.integrations.ve_identity.identity_client import IdentityClient
else:
    # For runtime, use Any to avoid circular import issues
    IdentityClient = Any


# Forward declaration for type hints
class OAuth2AuthPoller:
    """Abstract base class for OAuth2 authentication polling implementations.

    OAuth2 auth pollers are used to retrieve complete OAuth2 authentication data
    after user authorization. Implementations should poll the identity service
    until the authentication becomes available or a timeout occurs.
    """

    async def poll_for_auth(self) -> OAuth2Auth:
        """Poll for OAuth2 authentication data and return it when available.

        Returns:
            The complete OAuth2Auth object containing tokens and metadata.

        Raises:
            asyncio.TimeoutError: If polling times out before auth data is available.
        """
        raise NotImplementedError("Subclasses must implement poll_for_auth")


class AuthRequestConfig(BaseModel):
    """Configuration for authentication request processing.

    Attributes:
        on_auth_url: Optional callback function invoked when an authorization URL is generated.
                     Can be sync or async. Receives the auth URL as a parameter.
        oauth2_auth_poller: Optional custom token poller implementation for retrieving tokens
                      after user authorization. If None, a default poller will be used.
    """

    model_config = {"arbitrary_types_allowed": True}

    on_auth_url: Optional[Callable[[str], Any]] = None
    # Currently we only use auth_uri to initialize poller, may extend to support other fields like exchanged_auth_credential.
    oauth2_auth_poller: Optional[Callable[[Any], OAuth2AuthPoller]] = None
    max_auth_cycles: Optional[int] = None
    identity_client: Optional[IdentityClient] = None
    region: Optional[str] = None


class OAuth2TokenResponse(BaseModel):
    """Response from OAuth2 token request.

    Attributes:
        response_type: Type of response - either "token" or "auth_url".
        access_token: The OAuth2 access token (present when response_type is "token").
        authorization_url: The authorization URL for user consent (present when response_type is "auth_url").
        resource_ref: When response_type is "auth_url", this field contains the serialized request parameters
                      needed to poll for the final OAuth2 tokens after user authorization.

    """

    response_type: str
    access_token: Optional[str] = None
    authorization_url: Optional[str] = None
    resource_ref: Optional[str] = None

    @field_validator("response_type")
    @classmethod
    def validate_response_type(cls, v: str) -> str:
        """Validate that response_type is either 'token' or 'auth_url'."""
        if v not in ("token", "auth_url"):
            raise ValueError("response_type must be either 'token' or 'auth_url'")
        return v

    @model_validator(mode="after")
    def validate_response_fields(self):
        """Validate that required fields are present based on response_type."""
        if self.response_type == "token":
            if not self.access_token:
                raise ValueError(
                    "access_token is required when response_type is 'token'"
                )
        elif self.response_type == "auth_url":
            if not self.authorization_url:
                raise ValueError(
                    "authorization_url is required when response_type is 'auth_url'"
                )
        return self


class DCRRegistrationRequest(BaseModel):
    """Dynamic Client Registration (DCR) request model.

    Based on RFC 7591 - OAuth 2.0 Dynamic Client Registration Protocol.
    """

    client_name: str = "VeADK Framework"
    redirect_uris: Optional[List[str]] = None
    scope: Optional[str] = None
    grant_types: Optional[List[str]] = None
    response_types: Optional[List[str]] = None
    token_endpoint_auth_method: Optional[str] = None

    @field_validator("client_name")
    @classmethod
    def validate_client_name_not_empty(cls, v: str) -> str:
        """Validate that client_name is not empty."""
        if not v or not v.strip():
            raise ValueError("client_name cannot be empty")
        return v.strip()


class DCRRegistrationResponse(BaseModel):
    """Dynamic Client Registration (DCR) response model.

    Based on RFC 7591 - OAuth 2.0 Dynamic Client Registration Protocol.
    """

    client_id: str
    client_secret: Optional[str] = None
    client_id_issued_at: Optional[int] = None
    client_secret_expires_at: Optional[int] = None
    redirect_uris: Optional[List[str]] = None
    grant_types: Optional[List[str]] = None
    response_types: Optional[List[str]] = None
    scope: Optional[str] = None
    token_endpoint_auth_method: Optional[str] = None

    @field_validator("client_id")
    @classmethod
    def validate_client_id_not_empty(cls, v: str) -> str:
        """Validate that client_id is not empty."""
        if not v or not v.strip():
            raise ValueError("client_id cannot be empty")
        return v.strip()


class AuthorizationServerMetadata(BaseModel):
    """Extended Authorization Server Metadata with DCR support.

    Based on RFC 8414 - OAuth 2.0 Authorization Server Metadata
    and RFC 7591 - OAuth 2.0 Dynamic Client Registration Protocol.
    """

    authorization_endpoint: str
    token_endpoint: str
    issuer: str
    register_endpoint: Optional[str] = None  # DCR endpoint
    response_types: Optional[List[str]] = None

    @field_validator("authorization_endpoint", "token_endpoint", "issuer")
    @classmethod
    def validate_url_not_empty(cls, v: str) -> str:
        """Validate that URL fields are not empty."""
        if not v or not v.strip():
            raise ValueError("URL fields cannot be empty")
        return v.strip()


class OAuth2Discovery(BaseModel):
    """OAuth2 Discovery configuration with DCR support."""

    authorization_server_metadata: AuthorizationServerMetadata
    discovery_url: Optional[str] = None

    @field_validator("discovery_url")
    @classmethod
    def validate_discovery_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate discovery URL if provided."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("discovery_url cannot be empty string")
        return v.strip() if v else None


class WorkloadToken(BaseModel):
    """Workload access token and expiration time.

    Attributes:
        workload_access_token: The workload access token.
        expires_at: Unix timestamp (in seconds) when the token expires.
    """

    workload_access_token: str
    expires_at: int

    @field_validator("workload_access_token")
    @classmethod
    def validate_token_not_empty(cls, v: str) -> str:
        """Validate that the workload access token is not empty."""
        if not v or not v.strip():
            raise ValueError("workload_access_token cannot be empty")
        return v.strip()

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at_positive(cls, v: int) -> int:
        """Validate that expires_at is a positive timestamp."""
        if v <= 0:
            raise ValueError("expires_at must be a positive Unix timestamp")
        return v


class AssumeRoleCredential(BaseModel):
    access_key_id: str
    secret_access_key: str
    session_token: str
