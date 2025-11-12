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

"""Client for interacting with VolcEngine Identity Service."""

from __future__ import annotations

import json
import os
import uuid
from functools import wraps
from typing import Any, Dict, List, Literal, Optional

import aiohttp
import volcenginesdkid
import volcenginesdkcore
import volcenginesdksts

from veadk.integrations.ve_identity.models import (
    AssumeRoleCredential,
    DCRRegistrationRequest,
    DCRRegistrationResponse,
    OAuth2TokenResponse,
    WorkloadToken,
)
from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.configs.auth_configs import VeIdentityConfig

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def refresh_credentials(func):
    """Decorator to refresh credentials from environment variables or VeFaaS IAM before API calls.

    This decorator attempts to refresh VolcEngine credentials in the following order:
    1. Use initial credentials passed to the constructor
    2. Try to get credentials from environment variables
    3. Fall back to VeFaaS IAM file if available

    Works with both sync and async functions.
    """
    import asyncio

    @wraps(func)
    def _refresh_creds(self: IdentityClient):
        """Helper to refresh credentials."""
        # Try to get credentials from environment variables first
        ak = self._initial_access_key or os.getenv("VOLCENGINE_ACCESS_KEY", "")
        sk = self._initial_secret_key or os.getenv("VOLCENGINE_SECRET_KEY", "")
        session_token = self._initial_session_token or os.getenv(
            "VOLCENGINE_SESSION_TOKEN", ""
        )

        # If credentials are not available, try to get from VeFaaS IAM
        if not (ak and sk):
            try:
                logger.info(
                    "Credentials not found in environment, attempting to fetch from VeFaaS IAM..."
                )
                ve_iam_cred = get_credential_from_vefaas_iam()
                ak = ve_iam_cred.access_key_id
                sk = ve_iam_cred.secret_access_key
                session_token = ve_iam_cred.session_token
                logger.info("Successfully retrieved credentials from VeFaaS IAM")
            except FileNotFoundError as e:
                logger.warning(f"VeFaaS IAM credentials not available: {e}")
            except Exception as e:
                logger.warning(f"Failed to retrieve credentials from VeFaaS IAM: {e}")

        # If there is no session_token and role_trn is configured, execute AssumeRole
        if not session_token and self._identity_config.role_trn and ak and sk:
            try:
                logger.info(
                    f"No session token found, attempting AssumeRole with role: {self._identity_config.role_trn}"
                )
                sts_credentials = self._assume_role(ak, sk)
                ak = sts_credentials.access_key_id
                sk = sts_credentials.secret_access_key
                session_token = sts_credentials.session_token
                logger.info("Successfully assumed role and obtained STS credentials")
            except Exception as e:
                logger.warning(f"Failed to assume role: {e}")

        # Update configuration with the credentials
        self._api_client.api_client.configuration.ak = ak
        self._api_client.api_client.configuration.sk = sk
        self._api_client.api_client.configuration.session_token = session_token

    # Check if the function is async
    if asyncio.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(self: IdentityClient, *args, **kwargs):
            _refresh_creds(self)
            return await func(self, *args, **kwargs)

        return async_wrapper
    else:

        @wraps(func)
        def sync_wrapper(self: IdentityClient, *args, **kwargs):
            _refresh_creds(self)
            return func(self, *args, **kwargs)

        return sync_wrapper


class IdentityClient:
    """High-level client for VolcEngine Identity Service.

    This client provides methods to interact with the VolcEngine Identity Service,
    including creating credential providers, managing workload identities, and
    retrieving OAuth2 tokens and API keys.
    """

    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        session_token: Optional[str] = None,
        region: str = "cn-beijing",
        identity_config: Optional[VeIdentityConfig] = None,
    ):
        """Initialize the identity client.

        Args:
            access_key: VolcEngine access key. Defaults to VOLCENGINE_ACCESS_KEY env var.
            secret_key: VolcEngine secret key. Defaults to VOLCENGINE_SECRET_KEY env var.
            session_token: VolcEngine session token. Defaults to VOLCENGINE_SESSION_TOKEN env var.
            region: The VolcEngine region. Defaults to "cn-beijing".

        Raises:
            KeyError: If required environment variables are not set.
        """
        self.region = region
        self._identity_config = identity_config or VeIdentityConfig()

        # Store initial credentials for fallback
        self._initial_access_key = access_key or os.getenv("VOLCENGINE_ACCESS_KEY", "")
        self._initial_secret_key = secret_key or os.getenv("VOLCENGINE_SECRET_KEY", "")
        self._initial_session_token = session_token or os.getenv(
            "VOLCENGINE_SESSION_TOKEN", ""
        )

        # Initialize configuration and API client
        configuration = volcenginesdkcore.Configuration()
        configuration.region = region
        configuration.ak = self._initial_access_key
        configuration.sk = self._initial_secret_key
        configuration.session_token = self._initial_session_token

        self._api_client = volcenginesdkid.IDApi(
            volcenginesdkcore.ApiClient(configuration)
        )

    def _assume_role(self, access_key: str, secret_key: str) -> AssumeRoleCredential:
        """Execute AssumeRole to get STS temporary credentials.

        Args:
            access_key: VolcEngine access key
            secret_key: VolcEngine secret key

        Returns:
            AssumeRoleCredential containing temporary credentials

        Raises:
            Exception: If AssumeRole fails
        """
        # Create STS client configuration
        sts_config = volcenginesdkcore.Configuration()
        sts_config.region = self.region
        sts_config.ak = access_key
        sts_config.sk = secret_key

        # Create an STS API client
        sts_client = volcenginesdksts.STSApi(volcenginesdkcore.ApiClient(sts_config))

        # Construct an AssumeRole request
        assume_role_request = volcenginesdksts.AssumeRoleRequest(
            role_trn=self._identity_config.role_trn,
            role_session_name=self._identity_config.role_session_name,
        )

        logger.info(
            f"Executing AssumeRole for role: {self._identity_config.role_trn}, "
            f"session: {self._identity_config.role_session_name}"
        )

        response: volcenginesdksts.AssumeRoleResponse = sts_client.assume_role(
            assume_role_request
        )

        if not response.credentials:
            raise Exception("AssumeRole returned no credentials")

        access_key = response["access_key_id"]
        secret_key = response["secret_access_key"]
        session_token = response["session_token"]

        return AssumeRoleCredential(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=session_token,
        )

    @refresh_credentials
    def create_oauth2_credential_provider(
        self, request_params: Dict[str, Any]
    ) -> volcenginesdkid.CreateOauth2CredentialProviderResponse:
        """Create an OAuth2 credential provider in the identity service.

        Args:
            request_params: Dictionary containing provider configuration parameters.

        Returns:
            Response object containing the created provider information.
        """
        logger.info("Creating OAuth2 credential provider...")

        return self._api_client.create_oauth2_credential_provider(
            volcenginesdkid.CreateOauth2CredentialProviderRequest(**request_params),
        )

    @refresh_credentials
    def create_api_key_credential_provider(
        self, request_params: Dict[str, Any]
    ) -> volcenginesdkid.CreateApiKeyCredentialProviderResponse:
        """Create an API key credential provider in the identity service.

        Args:
            request_params: Dictionary containing provider configuration parameters.

        Returns:
            Response object containing the created provider information.
        """
        logger.info("Creating API key credential provider...")

        return self._api_client.create_api_key_credential_provider(
            volcenginesdkid.CreateApiKeyCredentialProviderRequest(**request_params),
        )

    @refresh_credentials
    def get_workload_access_token(
        self,
        workload_name: str,
        user_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> WorkloadToken:
        """Retrieve a workload access token for the specified workload.

        This method supports three authentication modes:
        1. JWT-based: When user_token is provided
        2. User ID-based: When user_id is provided
        3. Workload-only: When neither is provided

        Args:
            workload_name: Name of the workload identity.
            user_token: Optional JWT token for user authentication.
            user_id: Optional user ID for user-scoped authentication.

        Returns:
            WorkloadToken containing workload_access_token and expires_at fields.

        Note:
            If both user_token and user_id are provided, user_token takes precedence.
        """

        def convert_response(
            response: (
                volcenginesdkid.GetWorkloadAccessTokenForUserIdResponse
                | volcenginesdkid.GetWorkloadAccessTokenResponse
                | volcenginesdkid.GetWorkloadAccessTokenForJWTResponse
            ),
        ) -> WorkloadToken:
            if response.expires_at is None or response.workload_access_token is None:
                raise Exception("Invalid response from identity service")

            # Convert ISO 8601 timestamp string to Unix timestamp (seconds)
            from datetime import datetime
            import calendar

            dt = datetime.strptime(response.expires_at, "%Y-%m-%dT%H:%M:%SZ")
            expires_at_timestamp = calendar.timegm(dt.timetuple())

            return WorkloadToken(
                workload_access_token=response.workload_access_token,
                expires_at=expires_at_timestamp,
            )

        if user_token:
            if user_id is not None:
                logger.warning("Both user_token and user_id provided, using user_token")
            resp: volcenginesdkid.GetWorkloadAccessTokenForJWTResponse = (
                self._api_client.get_workload_access_token_for_jwt(
                    volcenginesdkid.GetWorkloadAccessTokenForJWTRequest(
                        name=workload_name, user_token=user_token
                    ),
                )
            )

        elif user_id:
            resp: volcenginesdkid.GetWorkloadAccessTokenForUserIdResponse = (
                self._api_client.get_workload_access_token_for_user_id(
                    volcenginesdkid.GetWorkloadAccessTokenForUserIdRequest(
                        name=workload_name, user_id=user_id
                    ),
                )
            )
        else:
            resp: volcenginesdkid.GetWorkloadAccessTokenResponse = (
                self._api_client.get_workload_access_token(
                    volcenginesdkid.GetWorkloadAccessTokenRequest(name=workload_name),
                )
            )

        return convert_response(resp)

    @refresh_credentials
    def create_workload_identity(
        self, name: Optional[str] = None
    ) -> volcenginesdkid.CreateWorkloadIdentityResponse:
        """Create a new workload identity.

        Args:
            name: Optional name for the workload identity. If not provided,
                  a random name will be generated.

        Returns:
            Dictionary containing the created workload identity information.
        """
        logger.info("Creating workload identity...")
        if not name:
            name = f"workload-{uuid.uuid4().hex[:8]}"

        return self._api_client.create_workload_identity(
            volcenginesdkid.CreateWorkloadIdentityRequest(name=name),
        )

    @refresh_credentials
    def get_oauth2_token_or_auth_url(
        self,
        *,
        provider_name: str,
        agent_identity_token: str,
        auth_flow: Optional[Literal["M2M", "USER_FEDERATION"]] = None,
        scopes: Optional[List[str]] = None,
        callback_url: Optional[str] = None,
        force_authentication: bool = False,
        custom_parameters: Optional[Dict[str, str]] = None,
    ) -> OAuth2TokenResponse:
        """Retrieve an OAuth2 access token or authorization URL.

        This method handles OAuth2 authentication flows. Depending on the flow type
        and current authentication state, it either returns a ready-to-use access token
        or an authorization URL that requires user interaction.

        Args:
            provider_name: Name of the credential provider configured in the identity service.
            agent_identity_token: Agent's workload access token for authentication.
            auth_flow: Optional OAuth2 flow type - "M2M" for machine-to-machine or
                      "USER_FEDERATION" for user-delegated access. If not provided,
                      the control plane will use the default configured value.
            scopes: Optional list of OAuth2 scopes to request. If not provided,
                   the control plane will use the default configured scopes.
            callback_url: OAuth2 redirect URL (must be pre-registered with the provider).
            force_authentication: If True, forces re-authentication even if a valid
                                 token exists in the token vault.
            custom_parameters: Optional additional parameters to pass to the OAuth2 provider.

        Returns:
            Dictionary with one of two formats:
            - {"type": "token", "access_token": str} - Ready-to-use access token
            - {"type": "auth_url", "authorization_url": str} - URL for user authorization

        Raises:
            RuntimeError: If the identity service returns neither a token nor an auth URL.
        """
        # Build request parameters
        request = volcenginesdkid.GetResourceOauth2TokenRequest(
            provider_name=provider_name,
            scopes=scopes,
            flow=auth_flow,
            identity_token=agent_identity_token,
        )

        # Add optional parameters
        if callback_url:
            request.redirect_url = callback_url
        if force_authentication:
            request.force_authentication = force_authentication
        if custom_parameters:
            request.custom_parameters = {
                "entries": [
                    {"key": k, "value": v} for k, v in custom_parameters.items()
                ]
            }

        response: volcenginesdkid.GetResourceOauth2TokenResponse = (
            self._api_client.get_resource_oauth2_token(request)
        )

        # Return token if available
        if response.access_token:
            return OAuth2TokenResponse(
                response_type="token", access_token=response.access_token
            )

        # Return authorization URL if token not available
        if response.authorization_url:
            return OAuth2TokenResponse(
                response_type="auth_url",
                authorization_url=response.authorization_url,
                resource_ref=json.dumps(
                    {
                        "provider_name": request.provider_name,
                        "agent_identity_token": request.identity_token,
                        "auth_flow": request.flow,
                        "scopes": getattr(request, "scopes", None),
                        "callback_url": getattr(request, "redirect_url", None),
                        "force_authentication": False,
                        "custom_parameters": getattr(
                            request, "custom_parameters", None
                        ),
                    }
                ),
            )

        raise RuntimeError(
            "Identity service returned neither access token nor authorization URL"
        )

    @refresh_credentials
    def get_api_key(self, *, provider_name: str, agent_identity_token: str) -> str:
        """Retrieve an API key from the identity service.

        Args:
            provider_name: Name of the API key credential provider.
            agent_identity_token: Agent's workload access token for authentication.

        Returns:
            The API key string.
        """
        logger.info("Retrieving API key from identity service...")
        request = volcenginesdkid.GetResourceApiKeyRequest(
            provider_name=provider_name,
            identity_token=agent_identity_token,
        )

        response: volcenginesdkid.GetResourceApiKeyResponse = (
            self._api_client.get_resource_api_key(request)
        )

        logger.info("Successfully retrieved API key")
        return response.api_key

    async def register_oauth2_client(
        self,
        *,
        register_endpoint: str,
        redirect_uris: Optional[List[str]] = None,
        scopes: Optional[List[str]] = None,
        client_name: str = "VeADK Framework",
    ) -> DCRRegistrationResponse:
        """Register a new OAuth2 client using Dynamic Client Registration (DCR).

        This method implements RFC 7591 - OAuth 2.0 Dynamic Client Registration Protocol.

        Args:
            register_endpoint: The DCR registration endpoint URL.
            redirect_uris: List of redirect URIs for the client.
            scopes: List of OAuth2 scopes to request.
            client_name: Human-readable name for the client.

        Returns:
            DCRRegistrationResponse containing client_id and client_secret.

        Raises:
            aiohttp.ClientError: If the registration request fails.
            ValueError: If the response is invalid.
        """
        logger.info(f"Registering OAuth2 client at {register_endpoint}...")

        # Prepare registration request
        registration_request = DCRRegistrationRequest(
            client_name=client_name,
            redirect_uris=redirect_uris,
            scope=" ".join(scopes) if scopes else None,
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="client_secret_post",
        )

        # Make DCR request
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                register_endpoint,
                json=registration_request.model_dump(exclude_none=True),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                # Check for errors
                response.raise_for_status()

                # Parse response
                try:
                    response_data = await response.json()
                    dcr_response = DCRRegistrationResponse.model_validate(response_data)

                    logger.info(
                        f"Successfully registered OAuth2 client: {dcr_response.client_id}"
                    )
                    return dcr_response

                except Exception as e:
                    logger.error(f"Failed to parse DCR response: {e}")
                    raise ValueError(f"Invalid DCR response: {e}") from e

    @refresh_credentials
    async def create_oauth2_credential_provider_with_dcr(
        self, request_params: Dict[str, Any]
    ) -> volcenginesdkid.CreateOauth2CredentialProviderResponse:
        """Create an OAuth2 credential provider with DCR support.

        This method checks if DCR is needed (RegisterEndpoint exists but no client_id/client_secret),
        performs DCR registration if needed, then creates the credential provider.

        Args:
            request_params: Dictionary containing provider configuration parameters.
                          Should include 'config' with OAuth2Discovery containing RegisterEndpoint.

        Returns:
            Response object containing the created provider information.

        Raises:
            ValueError: If DCR is required but fails, or if configuration is invalid.
        """
        logger.info("Creating OAuth2 credential provider with DCR support...")

        # Extract config from request params
        config = request_params.get("config", {})
        oauth2_discovery = config.get("Oauth2Discovery", {})
        auth_server_metadata = oauth2_discovery.get("AuthorizationServerMetadata", {})

        # Check if DCR is needed
        register_endpoint = auth_server_metadata.get("RegisterEndpoint")
        client_id = config.get("ClientId")
        client_secret = config.get("ClientSecret")

        if register_endpoint and (not client_id or not client_secret):
            logger.info(
                "DCR registration required - missing client_id or client_secret"
            )

            # Perform DCR registration
            try:
                dcr_response = await self.register_oauth2_client(
                    register_endpoint=register_endpoint,
                    redirect_uris=(
                        [config.get("RedirectUrl")]
                        if config.get("RedirectUrl")
                        else None
                    ),
                    scopes=config.get("Scopes", []),
                    client_name="VeADK Framework",
                )

                # Update config with DCR results
                config["ClientId"] = dcr_response.client_id
                if dcr_response.client_secret:
                    config["ClientSecret"] = dcr_response.client_secret
                else:
                    config["ClientSecret"] = "__EMPTY__"

                # Update request params
                request_params["config"] = config

                print(request_params)
                logger.info(
                    f"DCR registration successful, using client_id: {dcr_response.client_id}"
                )

            except Exception as e:
                logger.error(f"DCR registration failed: {e}")
                raise ValueError(f"DCR registration failed: {e}") from e

        # Create the credential provider with updated config
        return self.create_oauth2_credential_provider(request_params)

    @refresh_credentials
    def check_permission(
        self, principal_id, operation, resource_id, namespace="default"
    ) -> bool:
        """Check if the principal has permission to perform the operation on the resource.

        Args:
            principal_id: The ID of the principal (user or service).
            operation: The operation to check permission for.
            resource_id: The ID of the resource.
            namespace: The namespace of the resource. Defaults to "default".

        Returns:
            True if the principal has permission, False otherwise.
        """
        logger.info(
            f"Checking permission for principal {principal_id} on resource {resource_id} for operation {operation}..."
        )

        request = volcenginesdkid.CheckPermissionRequest(
            principal_id=principal_id,
            operation=operation,
            resource_id=resource_id,
            namespace=namespace,
        )

        response: volcenginesdkid.CheckPermissionResponse = (
            self._api_client.check_permission(request)
        )

        logger.info(
            f"Permission check result for principal {principal_id} on resource {resource_id}: {response.allowed}"
        )
        return response.allowed
