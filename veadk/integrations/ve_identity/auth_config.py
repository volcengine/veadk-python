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

from pydantic import BaseModel, model_validator, field_validator

from .models import OAuth2AuthPoller
from .identity_client import IdentityClient


class AuthConfig(BaseModel, ABC):
    """Base authentication configuration."""

    model_config = {"arbitrary_types_allowed": True}

    provider_name: str
    identity_client: Optional[IdentityClient] = None
    region: str = "cn-beijing"

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

    # Required fields
    scopes: List[str]
    auth_flow: Literal["M2M", "USER_FEDERATION"]
    # Optional fields
    callback_url: Optional[str] = None
    force_authentication: bool = False
    response_for_auth_required: Optional[Union[dict, str]] = None
    on_auth_url: Optional[Callable[[str], Any]] = None
    oauth2_auth_poller: Optional[Callable[[Any], OAuth2AuthPoller]] = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes_not_empty(cls, v: List[str]) -> List[str]:
        """Validate that scopes list is not empty and contains valid scope strings."""
        if not v:
            raise ValueError("scopes cannot be empty")

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

    @model_validator(mode="after")
    def _validate_required_fields(self):
        """Validate required fields."""
        if not self.scopes:
            raise ValueError("scopes is required for OAuth2AuthConfig")
        if not self.auth_flow:
            raise ValueError("auth_flow is required for OAuth2AuthConfig")
        return self

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
    region: str = "cn-beijing",
) -> ApiKeyAuthConfig:
    """Create an API key authentication configuration."""
    return ApiKeyAuthConfig(
        provider_name=provider_name, identity_client=identity_client, region=region
    )

def workload_auth(
    provider_name: str,
    identity_client: Optional[IdentityClient] = None,
    region: str = "cn-beijing",
) -> WorkloadAuthConfig:
    """Create a workload authentication configuration."""
    return WorkloadAuthConfig(
        provider_name=provider_name, identity_client=identity_client, region=region
    )

def oauth2_auth(
    provider_name: str,
    scopes: List[str],
    auth_flow: Literal["M2M", "USER_FEDERATION"],
    callback_url: Optional[str] = None,
    force_authentication: bool = False,
    response_for_auth_required: Optional[Union[dict, str]] = None,
    on_auth_url: Optional[Callable[[str], Any]] = None,
    oauth2_auth_poller: Optional[Callable[[Any], OAuth2AuthPoller]] = None,
    identity_client: Optional[IdentityClient] = None,
    region: str = "cn-beijing",
) -> OAuth2AuthConfig:
    """Create an OAuth2 authentication configuration."""
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
