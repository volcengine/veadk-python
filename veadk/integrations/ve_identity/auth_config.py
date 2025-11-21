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

"""
Authentication configuration classes for Identity integration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, List, Literal, Optional, Union

from pydantic import BaseModel, field_validator

from veadk.integrations.ve_identity.models import OAuth2AuthPoller
from veadk.integrations.ve_identity.identity_client import IdentityClient


def _get_default_region() -> str:
    """Get the default region from VeADK configuration.

    Returns:
        The configured region from VeIdentityConfig, or "cn-beijing" as fallback.
    """
    try:
        from veadk.config import settings

        return settings.veidentity.region
    except Exception:
        # Fallback to default if config loading fails
        return "cn-beijing"


def get_default_identity_client(region: Optional[str] = None) -> IdentityClient:
    """Get the default IdentityClient from VeADK configuration.

    Returns:
        The configured IdentityClient from VeIdentityConfig, or a new instance as fallback.
    """
    try:
        from veadk.config import settings

        return settings.veidentity.get_identity_client()
    except Exception:
        # Fallback to new instance if config loading fails
        return IdentityClient(region=region or _get_default_region())


class AuthConfig(BaseModel, ABC):
    """Base authentication configuration."""

    model_config = {"arbitrary_types_allowed": True}

    provider_name: str
    identity_client: Optional[IdentityClient] = None
    region: str = None  # Will be set to default from config if not provided

    def __init__(self, **data):
        """Initialize AuthConfig with default region from VeADK config if not provided."""
        if "region" not in data or data["region"] is None:
            data["region"] = _get_default_region()
        super().__init__(**data)

    @field_validator("provider_name")
    @classmethod
    def validate_provider_name_not_empty(cls, v: str) -> str:
        """Validate that provider_name is not empty."""
        if not v or not v.strip():
            raise ValueError("provider_name cannot be empty")
        return v.strip()

    @property
    @abstractmethod
    def auth_type(self) -> str:
        """Return the authentication type identifier."""
        pass


class ApiKeyAuthConfig(AuthConfig):
    """API Key authentication configuration."""

    @property
    def auth_type(self) -> str:
        return "api_key"


class OAuth2AuthConfig(AuthConfig):
    """OAuth2 authentication configuration."""

    # Optional fields - control plane will use defaults if not provided
    scopes: Optional[List[str]] = None
    auth_flow: Optional[Literal["M2M", "USER_FEDERATION"]] = None
    # Additional optional fields
    callback_url: Optional[str] = None
    force_authentication: bool = False
    response_for_auth_required: Optional[Union[dict, str]] = None
    on_auth_url: Optional[Callable[[str], Any]] = None
    oauth2_auth_poller: Optional[Callable[[Any], OAuth2AuthPoller]] = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes_not_empty(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate that scopes list is not empty and contains valid scope strings.

        If scopes is None, the control plane will use default scopes.
        """
        if v is None:
            return None

        if not v:
            raise ValueError(
                "scopes cannot be an empty list; use None to use control plane defaults"
            )

        # Validate each scope is not empty
        for scope in v:
            if not scope or not scope.strip():
                raise ValueError("scope values cannot be empty")

        # Remove duplicates while preserving order
        seen = set()
        unique_scopes = []
        for scope in v:
            scope = scope.strip()
            if scope not in seen:
                seen.add(scope)
                unique_scopes.append(scope)

        return unique_scopes

    @field_validator("callback_url")
    @classmethod
    def validate_callback_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate callback URL format if provided."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            # Basic URL validation
            if not (v.startswith("http://") or v.startswith("https://")):
                raise ValueError("callback_url must be a valid HTTP/HTTPS URL")
        return v

    @property
    def auth_type(self) -> str:
        return "oauth2"


class WorkloadAuthConfig(AuthConfig):
    """Workload Access Token authentication configuration."""

    @property
    def auth_type(self) -> str:
        return "workload"


# Type alias for all auth configs
VeIdentityAuthConfig = Union[ApiKeyAuthConfig, OAuth2AuthConfig, WorkloadAuthConfig]


# Convenience factory functions
def api_key_auth(
    provider_name: str,
    identity_client: Optional[IdentityClient] = None,
    region: Optional[str] = None,
) -> ApiKeyAuthConfig:
    """Create an API key authentication configuration.

    Args:
        provider_name: Name of the credential provider.
        identity_client: Optional IdentityClient instance.
        region: VolcEngine region. If not provided, uses the region from VeADK config.

    Returns:
        ApiKeyAuthConfig instance.
    """
    if region is None:
        region = _get_default_region()
    return ApiKeyAuthConfig(
        provider_name=provider_name, identity_client=identity_client, region=region
    )


def workload_auth(
    provider_name: str,
    identity_client: Optional[IdentityClient] = None,
    region: Optional[str] = None,
) -> WorkloadAuthConfig:
    """Create a workload authentication configuration.

    Args:
        provider_name: Name of the credential provider.
        identity_client: Optional IdentityClient instance.
        region: VolcEngine region. If not provided, uses the region from VeADK config.

    Returns:
        WorkloadAuthConfig instance.
    """
    if region is None:
        region = _get_default_region()
    return WorkloadAuthConfig(
        provider_name=provider_name, identity_client=identity_client, region=region
    )


def oauth2_auth(
    provider_name: str,
    scopes: Optional[List[str]] = None,
    auth_flow: Optional[Literal["M2M", "USER_FEDERATION"]] = None,
    callback_url: Optional[str] = None,
    force_authentication: bool = False,
    response_for_auth_required: Optional[Union[dict, str]] = None,
    on_auth_url: Optional[Callable[[str], Any]] = None,
    oauth2_auth_poller: Optional[Callable[[Any], OAuth2AuthPoller]] = None,
    identity_client: Optional[IdentityClient] = None,
    region: Optional[str] = None,
) -> OAuth2AuthConfig:
    """Create an OAuth2 authentication configuration.

    Args:
        provider_name: Name of the credential provider.
        scopes: Optional list of OAuth2 scopes. If not provided, the control plane
               will use the default configured scopes for the provider.
        auth_flow: Optional authentication flow type ("M2M" or "USER_FEDERATION").
                  If not provided, the control plane will use the default configured flow.
        callback_url: Optional callback URL for OAuth2.
        force_authentication: Whether to force authentication.
        response_for_auth_required: Response to return when auth is required.
        on_auth_url: Callback function for auth URL.
        oauth2_auth_poller: Callback function for auth polling.
        identity_client: Optional IdentityClient instance.
        region: VolcEngine region. If not provided, uses the region from VeADK config.

    Returns:
        OAuth2AuthConfig instance.
    """
    if region is None:
        region = _get_default_region()
    return OAuth2AuthConfig(
        provider_name=provider_name,
        scopes=scopes,
        auth_flow=auth_flow,
        callback_url=callback_url,
        force_authentication=force_authentication,
        response_for_auth_required=response_for_auth_required,
        on_auth_url=on_auth_url,
        oauth2_auth_poller=oauth2_auth_poller,
        identity_client=identity_client,
        region=region,
    )
