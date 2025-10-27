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
Authentication mixins for Identity integration.

These mixins provide reusable authentication logic that can be mixed into
different tool classes to avoid code duplication.
"""

from __future__ import annotations

import urllib.parse
import asyncio
from typing import Any, Callable, List, Literal, Optional, Union
from abc import ABC, abstractmethod

from google.adk.auth.auth_credential import (
    AuthCredential,
    AuthCredentialTypes,
    OAuth2Auth,
)
from google.adk.auth.auth_tool import AuthConfig
from google.adk.auth.auth_handler import AuthHandler
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.openapi_tool.auth.auth_helpers import dict_to_auth_scheme
from google.adk.agents.readonly_context import ReadonlyContext

from veadk.integrations.ve_identity.models import OAuth2AuthPoller, OAuth2TokenResponse
from veadk.integrations.ve_identity.identity_client import IdentityClient
from veadk.integrations.ve_identity.auth_config import (
    VeIdentityAuthConfig,
    ApiKeyAuthConfig,
    OAuth2AuthConfig,
    WorkloadAuthConfig,
)
from veadk.integrations.ve_identity.token_manager import get_workload_token

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


# OAuth2 scheme definition (shared across all OAuth2 tools)
oauth2_scheme = dict_to_auth_scheme(
    {
        "type": "oauth2",
        "flows": {
            "authorizationCode": {
                "authorizationUrl": "__EMPTY__",
                "tokenUrl": "__EMPTY__",
            }
        },
    }
)


class AuthRequiredException(Exception):
    """Exception raised when user authorization is required for OAuth2 flow."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class BaseAuthMixin(ABC):
    """Base mixin for Identity authentication.

    This mixin provides common functionality for all Identity authentication types.
    Specific authentication implementations should inherit from this class.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        identity_client: Optional[IdentityClient] = None,
        region: str = "cn-beijing",
        **kwargs,
    ):
        """Initialize the Identity authentication mixin.

        Args:
            provider_name: Name of the credential provider configured in identity service.
            identity_client: Optional IdentityClient instance. If not provided, creates a new one.
            region: VolcEngine region for the identity client. Defaults to "cn-beijing".
            **kwargs: Additional arguments passed to parent classes.
        """
        # Only pass kwargs to super() if we're in a multiple inheritance scenario
        # and the next class in MRO expects them
        try:
            super().__init__(**kwargs)
        except TypeError:
            # If super().__init__() doesn't accept kwargs (e.g., object.__init__),
            # call it without arguments
            super().__init__()

        self._identity_client = identity_client or IdentityClient(region=region)
        self._provider_name = provider_name

    @abstractmethod
    async def _get_credential(
        self, *, tool_context: Union[ToolContext | ReadonlyContext]
    ) -> AuthCredential:
        """Get or create authentication credential.

        Args:
            tool_context: The tool context for accessing session state.

        Returns:
            The authentication credential.
        """
        pass

    @abstractmethod
    async def _execute_with_credential(
        self,
        *,
        args: dict[str, Any],
        tool_context: Union[ToolContext | ReadonlyContext],
        credential: AuthCredential,
    ) -> Any:
        """Execute the tool with the provided credential.

        Args:
            args: Arguments to pass to the tool.
            tool_context: The tool context.
            credential: The authentication credential.

        Returns:
            The result from the tool execution.
        """
        pass

    async def run_with_identity_auth(
        self,
        *,
        args: dict[str, Any],
        tool_context: Union[ToolContext | ReadonlyContext],
    ) -> Any:
        """Execute the tool with Identity authentication.

        This is the main entry point that handles the authentication flow
        and delegates to the specific implementation.

        Args:
            args: Arguments to pass to the tool.
            tool_context: The tool context.

        Returns:
            The result from the tool execution.
        """
        credential = await self._get_credential(tool_context=tool_context)
        return await self._execute_with_credential(
            args=args, tool_context=tool_context, credential=credential
        )


class ApiKeyAuthMixin(BaseAuthMixin):
    """Mixin for API key authentication via Identity Service.

    This mixin handles:
    1. Retrieving workload access tokens for the agent
    2. Fetching API keys from the identity service
    3. Caching API keys in session state
    """

    async def _get_credential(
        self, *, tool_context: Union[ToolContext | ReadonlyContext]
    ) -> AuthCredential:
        """Get or create API key credential.

        Args:
            tool_context: The tool context for accessing session state.

        Returns:
            The API key credential.
        """
        # Build cache key for the API key
        credential_key = (
            f"api_key:{tool_context.agent_name}:"
            f"{tool_context._invocation_context.user_id}:{self._provider_name}"
        )

        # Try to get cached API key
        credential: AuthCredential = tool_context._invocation_context.session.state.get(
            credential_key
        )

        # Fetch API key if not cached
        if not credential or credential.api_key is None:
            # Get workload access token for the agent
            workload_token = await get_workload_token(
                tool_context=tool_context,
                identity_client=self._identity_client,
            )

            # Fetch API key from identity service
            api_key = await self._identity_client.get_api_key(
                provider_name=self._provider_name,
                agent_identity_token=workload_token,
            )

            # Create and cache the credential
            credential = AuthCredential(
                auth_type=AuthCredentialTypes.API_KEY,
                api_key=api_key,
            )
            tool_context._invocation_context.session.state[credential_key] = credential

        return credential

    async def _execute_with_credential(
        self,
        *,
        args: dict[str, Any],
        tool_context: Union[ToolContext | ReadonlyContext],
        credential: AuthCredential,
    ) -> Any:
        """Default implementation - should be overridden by concrete tool classes.

        This provides a base implementation to satisfy the abstract method requirement.
        Concrete tool classes should override this method with their specific logic.

        Args:
            args: Arguments to pass to the tool.
            tool_context: The tool context.
            credential: The authentication credential.

        Returns:
            The result from the tool execution.

        Raises:
            NotImplementedError: Always, as this should be overridden.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must override _execute_with_credential method"
        )


class WorkloadAuthMixin(BaseAuthMixin):
    """Mixin for Workload Access Token authentication via Identity Service.

    This mixin handles:
    1. Retrieving workload access tokens for the agent
    2. Fetching API keys from the identity service
    3. Caching API keys in session state
    """

    async def _get_credential(
        self, *, tool_context: Union[ToolContext | ReadonlyContext]
    ) -> AuthCredential:
        """Get or create Workload Access Token credential.

        Args:
            tool_context: The tool context for accessing session state.

        Returns:
            The Workload Access Token credential.
        """
        # Build cache key for the Workload Access Token
        credential_key = (
            f"workload_access_token:{tool_context.agent_name}:"
            f"{tool_context._invocation_context.user_id}:{self._provider_name}"
        )

        # Try to get cached Workload Access Token
        credential: AuthCredential = tool_context._invocation_context.session.state.get(
            credential_key
        )

        # Fetch Workload Access Token if not cached
        if not credential or credential.api_key is None:
            # Get workload access token for the agent
            workload_access_token = await get_workload_token(
                tool_context=tool_context,
                identity_client=self._identity_client,
            )

            # Create and cache the credential
            credential = AuthCredential(
                auth_type=AuthCredentialTypes.OAUTH2,
                oauth2=OAuth2Auth(access_token=workload_access_token),
            )
            tool_context._invocation_context.session.state[credential_key] = credential

        return credential

    async def _execute_with_credential(
        self,
        *,
        args: dict[str, Any],
        tool_context: Union[ToolContext | ReadonlyContext],
        credential: AuthCredential,
    ) -> Any:
        """Default implementation - should be overridden by concrete tool classes.

        This provides a base implementation to satisfy the abstract method requirement.
        Concrete tool classes should override this method with their specific logic.

        Args:
            args: Arguments to pass to the tool.
            tool_context: The tool context.
            credential: The authentication credential.

        Returns:
            The result from the tool execution.

        Raises:
            NotImplementedError: Always, as this should be overridden.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must override _execute_with_credential method"
        )


class OAuth2AuthMixin(BaseAuthMixin):
    """Mixin for OAuth2 authentication via Identity Service.

    This mixin handles:
    1. Retrieving workload access tokens for the agent
    2. Requesting OAuth2 tokens from the identity service
    3. Handling user authorization flows when needed
    """

    def __init__(
        self,
        *,
        scopes: List[str],
        auth_flow: Literal["M2M", "USER_FEDERATION"],
        callback_url: Optional[str] = None,
        force_authentication: bool = False,
        response_for_auth_required: Optional[str] = None,
        on_auth_url: Optional[Callable[[str], Any]] = None,
        # Currently we only use auth_uri to initialize poller, may extend to support other fields like exchanged_auth_credential.
        oauth2_auth_poller: Optional[Callable[[Any], OAuth2AuthPoller]] = None,
        **kwargs,
    ):
        """Initialize the OAuth2 authentication mixin.

        Args:
            scopes: List of OAuth2 scopes to request.
            auth_flow: Authentication flow type - "M2M" for machine-to-machine or
                      "USER_FEDERATION" for user-delegated access.
            callback_url: OAuth2 redirect URL (must be pre-registered).
            force_authentication: If True, forces re-authentication even if cached token exists.
            response_for_auth_required: Custom response to return when user authorization is needed.
                                       If None, returns "Pending User Authorization.".
            **kwargs: Additional arguments passed to parent classes.
        """
        super().__init__(**kwargs)
        self._scopes = scopes
        self._auth_flow = auth_flow
        self._callback_url = callback_url
        self._force_authentication = force_authentication
        self._response_for_auth_required = response_for_auth_required
        self._on_auth_url = on_auth_url
        self._oauth2_auth_poller = oauth2_auth_poller

    async def _get_oauth2_token_or_auth_url(
        self, *, tool_context: Union[ToolContext | ReadonlyContext]
    ) -> OAuth2TokenResponse:
        """Retrieve OAuth2 token or authorization URL from identity service.

        Args:
            tool_context: The tool context for accessing session state and user info.

        Returns:
            Dictionary with either a token or authorization URL.
        """
        # Get workload access token for the agent
        workload_token = await get_workload_token(
            tool_context=tool_context,
            identity_client=self._identity_client,
        )

        # Request OAuth2 token or auth URL
        return await self._identity_client.get_oauth2_token_or_auth_url(
            provider_name=self._provider_name,
            agent_identity_token=workload_token,
            auth_flow=self._auth_flow,
            scopes=self._scopes,
            callback_url=self._callback_url,
            force_authentication=self._force_authentication,
        )

    async def _get_credential(
        self, *, tool_context: Union[ToolContext | ReadonlyContext]
    ) -> AuthCredential:
        """Get or create OAuth2 credential.

        This method handles the OAuth2 flow and may raise an exception
        if user authorization is required.

        Args:
            tool_context: The tool context for accessing session state.

        Returns:
            The OAuth2 credential.

        Raises:
            AuthRequiredException: If user authorization is required.
        """
        auth_config = AuthConfig(
            auth_scheme=oauth2_scheme,
            credential_key=f"oauth_access_token:{tool_context.agent_name}:{tool_context._invocation_context.user_id}:{self._provider_name}",
        )

        # Check if we already have a credential from previous auth
        if credential := AuthHandler(auth_config).get_auth_response(tool_context.state):
            # Use existing credential
            return credential

        # No credential yet - request token or auth URL
        response = await self._get_oauth2_token_or_auth_url(tool_context=tool_context)

        if response.response_type == "auth_url":
            # Need user authorization
            auth_uri = urllib.parse.unquote(response.authorization_url)
            if isinstance(tool_context, ToolContext):
                # For ToolContext, use the standard request_credential flow
                auth_config.raw_auth_credential = AuthCredential(
                    auth_type=AuthCredentialTypes.OAUTH2,
                    oauth2=OAuth2Auth(auth_uri=auth_uri),
                    resource_ref=response.resource_ref,
                )
                tool_context.request_credential(auth_config=auth_config)  # type: ignore

                # Raise a special exception to indicate auth is required
                raise AuthRequiredException(
                    self._response_for_auth_required or "Pending User Authorization."
                )
            else:
                # For ReadonlyContext (e.g., in get_tools), handle OAuth2 flow directly
                return await self._handle_oauth2_flow_for_readonly_context(
                    auth_uri=auth_uri,
                    resource_ref=response.resource_ref,
                    readonly_context=tool_context,
                )
        else:
            # Got token directly - create credential
            return AuthCredential(
                auth_type=AuthCredentialTypes.OAUTH2,
                oauth2=OAuth2Auth(access_token=response.access_token),
            )

    async def _handle_oauth2_flow_for_readonly_context(
        self,
        *,
        auth_uri: str,
        resource_ref: Optional[str],
        readonly_context: ReadonlyContext,
    ) -> AuthCredential:
        """Handle OAuth2 flow for ReadonlyContext (e.g., during get_tools).

        This method implements a direct OAuth2 flow similar to auth_processor.py
        but adapted for ReadonlyContext scenarios.

        Args:
            auth_uri: The OAuth2 authorization URI
            resource_ref: Resource reference for the OAuth2 request
            tool_context: The readonly context

        Returns:
            AuthCredential with OAuth2 access token
        """
        import json

        # Parse resource_ref if available
        request_dict = json.loads(resource_ref) if resource_ref else {}

        # Use custom on_auth_url callback if provided
        if on_auth_url := self._on_auth_url:
            if asyncio.iscoroutinefunction(on_auth_url):
                await on_auth_url(auth_uri)
            else:
                on_auth_url(auth_uri)
        else:
            logger.info(f"Authorization required: {auth_uri}")

            # Use custom oauth2_auth_poller if provided
        if oauth2_auth_poller := self._oauth2_auth_poller:
            active_poller = oauth2_auth_poller(auth_uri, request_dict)
        else:
            # Use default poller
            active_poller = self._create_default_oauth2_poller(auth_uri, request_dict)

        # Poll for the OAuth2 auth
        updated_oauth2_auth = await active_poller.poll_for_auth()

        if not updated_oauth2_auth or not updated_oauth2_auth.access_token:
            raise AuthRequiredException("Failed to obtain OAuth2 access token")

        return AuthCredential(
            auth_type=AuthCredentialTypes.OAUTH2,
            oauth2=updated_oauth2_auth,
        )

    def _create_default_oauth2_poller(self, auth_uri: str, request_dict: dict):
        """Create a default OAuth2 poller for ReadonlyContext scenarios."""
        from veadk.integrations.ve_identity.auth_processor import _DefaultOauth2AuthPoller

        async def async_token_fetcher():
            response = await self._identity_client.get_oauth2_token_or_auth_url(
                **request_dict
            )
            return (
                OAuth2Auth(access_token=response.access_token)
                if response.access_token and response.access_token.strip()
                else None
            )

        return _DefaultOauth2AuthPoller(auth_uri, async_token_fetcher)

    async def _execute_with_credential(
        self,
        *,
        args: dict[str, Any],
        tool_context: Union[ToolContext | ReadonlyContext],
        credential: AuthCredential,
    ) -> Any:
        """Default implementation - should be overridden by concrete tool classes.

        This provides a base implementation to satisfy the abstract method requirement.
        Concrete tool classes should override this method with their specific logic.

        Args:
            args: Arguments to pass to the tool.
            tool_context: The tool context.
            credential: The authentication credential.

        Returns:
            The result from the tool execution.

        Raises:
            NotImplementedError: Always, as this should be overridden.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must override _execute_with_credential method"
        )


class VeIdentityAuthMixin(BaseAuthMixin):
    """Unified mixin that supports both API Key and OAuth2 authentication based on configuration.

    This mixin uses composition to delegate to specific authentication implementations
    while providing a unified interface for tools.
    """

    def __init__(self, *, auth_config: VeIdentityAuthConfig, **kwargs):
        """Initialize the unified authentication mixin.

        Args:
            auth_config: Authentication configuration (ApiKeyAuthConfig, WorkloadAuthConfig, or OAuth2AuthConfig).
            **kwargs: Additional arguments passed to parent classes.
        """
        # Initialize base class with common parameters
        super().__init__(
            provider_name=auth_config.provider_name,
            identity_client=auth_config.identity_client,
            region=auth_config.region,
            **kwargs,
        )
        self._auth_config = auth_config

        # Create the appropriate authentication delegate based on config type
        self._auth_delegate = self._create_auth_delegate(**kwargs)

    def _create_auth_delegate(self, **kwargs):
        """Create the appropriate authentication delegate based on config type."""
        if isinstance(self._auth_config, ApiKeyAuthConfig):
            return ApiKeyAuthMixin(
                provider_name=self._auth_config.provider_name,
                identity_client=self._auth_config.identity_client,
                region=self._auth_config.region,
                **kwargs,
            )
        elif isinstance(self._auth_config, WorkloadAuthConfig):
            return WorkloadAuthMixin(
                provider_name=self._auth_config.provider_name,
                identity_client=self._auth_config.identity_client,
                region=self._auth_config.region,
                **kwargs,
            )
        elif isinstance(self._auth_config, OAuth2AuthConfig):
            return OAuth2AuthMixin(
                provider_name=self._auth_config.provider_name,
                scopes=self._auth_config.scopes,
                auth_flow=self._auth_config.auth_flow,
                callback_url=self._auth_config.callback_url,
                force_authentication=self._auth_config.force_authentication,
                response_for_auth_required=self._auth_config.response_for_auth_required,
                on_auth_url=self._auth_config.on_auth_url,
                oauth2_auth_poller=self._auth_config.oauth2_auth_poller,
                identity_client=self._auth_config.identity_client,
                region=self._auth_config.region,
                **kwargs,
            )
        else:
            raise ValueError(f"Unsupported auth config type: {type(self._auth_config)}")

    async def _get_credential(
        self, *, tool_context: Union[ToolContext | ReadonlyContext]
    ) -> AuthCredential:
        """Get or create authentication credential using the configured auth type."""
        return await self._auth_delegate._get_credential(tool_context=tool_context)

    async def _execute_with_credential(
        self,
        *,
        args: dict[str, Any],
        tool_context: Union[ToolContext | ReadonlyContext],
        credential: AuthCredential,
    ) -> Any:
        """Default implementation - should be overridden by concrete tool classes.

        This provides a base implementation to satisfy the abstract method requirement.
        Concrete tool classes should override this method with their specific logic.

        Args:
            args: Arguments to pass to the tool.
            tool_context: The tool context.
            credential: The authentication credential.

        Returns:
            The result from the tool execution.

        Raises:
            NotImplementedError: Always, as this should be overridden.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must override _execute_with_credential method"
        )
