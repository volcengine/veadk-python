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
from pathlib import Path
import uuid
from functools import wraps
from typing import Any, Dict, List, Literal, Optional

import aiohttp
import volcenginesdkid
import volcenginesdkcore
import volcenginesdksts
from volcenginesdkcore.rest import ApiException

from veadk.consts import VEFAAS_IAM_CRIDENTIAL_PATH
from veadk.integrations.ve_identity.models import (
    AssumeRoleCredential,
    DCRRegistrationRequest,
    DCRRegistrationResponse,
    OAuth2TokenResponse,
    WorkloadToken,
)
from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.config import settings

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

        # Helper function to attempt VeFaaS IAM credential retrieval
        def try_get_vefaas_credentials():
            """Attempt to retrieve credentials from VeFaaS IAM."""
            try:
                logger.info("Attempting to fetch credentials from VeFaaS IAM...")
                ve_iam_cred = get_credential_from_vefaas_iam()
                return (
                    ve_iam_cred.access_key_id,
                    ve_iam_cred.secret_access_key,
                    ve_iam_cred.session_token,
                )
            except FileNotFoundError as e:
                logger.warning(f"VeFaaS IAM credentials not available: {e}")
            except Exception as e:
                logger.warning(f"Failed to retrieve credentials from VeFaaS IAM: {e}")
            return None

        # If no AK/SK, try to get from VeFaaS IAM
        if not (ak and sk):
            logger.info(
                "Credentials not found in environment, attempting to fetch from VeFaaS IAM..."
            )
            credentials = try_get_vefaas_credentials()
            if credentials:
                ak, sk, session_token = credentials

        # If we have AK/SK but no session token, try to get complete credentials
        if ak and sk and not session_token:
            # First attempt: try VeFaaS IAM
            credentials = try_get_vefaas_credentials()
            if credentials:
                ak, sk, session_token = credentials

            # Second attempt: if still no session token, try AssumeRole
            if not session_token:
                role_trn = self._get_iam_role_trn_from_vefaas_iam() or os.getenv(
                    "RUNTIME_IAM_ROLE_TRN", ""
                )

                if role_trn:
                    try:
                        logger.info(f"Attempting AssumeRole with role: {role_trn}")
                        sts_credentials = self._assume_role(ak, sk, role_trn)
                        ak = sts_credentials.access_key_id
                        sk = sts_credentials.secret_access_key
                        session_token = sts_credentials.session_token
                        logger.info("Successfully obtained credentials via AssumeRole")
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
        configuration.logger = {}

        self._api_client = volcenginesdkid.IDApi(
            volcenginesdkcore.ApiClient(configuration)
        )

        # STS credential cache
        self._cached_sts_credential: Optional[AssumeRoleCredential] = None
        self._sts_credential_expires_at: Optional[int] = None

    def _get_iam_role_trn_from_vefaas_iam(self) -> Optional[str]:
        logger.info(
            f"Try to get IAM Role TRN from VeFaaS IAM file (path={VEFAAS_IAM_CRIDENTIAL_PATH})."
        )

        path = Path(VEFAAS_IAM_CRIDENTIAL_PATH)

        if not path.exists():
            logger.error(
                f"Get IAM Role TRN from IAM file failed, and VeFaaS IAM file (path={VEFAAS_IAM_CRIDENTIAL_PATH}) not exists. Please check your configuration."
            )
            return None

        with open(VEFAAS_IAM_CRIDENTIAL_PATH, "r") as f:
            cred_dict = json.load(f)
            role_trn = cred_dict["role_trn"]

            logger.info("Get IAM Role TRN from IAM file successfully.")

            return role_trn

    def _is_sts_credential_expired(self) -> bool:
        """Check if cached STS credential is expired or will expire soon.

        Returns:
            True if credential is expired or will expire within 5 minutes, False otherwise.
        """
        if self._sts_credential_expires_at is None:
            return True

        import time

        current_time = int(time.time())
        # Refresh 5 minutes in advance to avoid expiration during use.
        buffer_seconds = 300
        return current_time >= (self._sts_credential_expires_at - buffer_seconds)

    def _assume_role(
        self, access_key: str, secret_key: str, role_trn: str
    ) -> AssumeRoleCredential:
        """Execute AssumeRole to get STS temporary credentials.

        Args:
            access_key: VolcEngine access key
            secret_key: VolcEngine secret key
            role_trn: The role TRN to assume

        Returns:
            AssumeRoleCredential containing temporary credentials

        Raises:
            Exception: If AssumeRole fails
        """
        # Check if the cached credentials are still valid
        if (
            self._cached_sts_credential is not None
            and not self._is_sts_credential_expired()
        ):
            logger.info("Using cached STS credentials")
            return self._cached_sts_credential

        logger.info(
            "Cached STS credentials expired or not found, requesting new credentials..."
        )

        # Create STS client configuration
        sts_config = volcenginesdkcore.Configuration()
        sts_config.region = self.region
        sts_config.ak = access_key
        sts_config.sk = secret_key
        sts_config.logger = {}

        # Create an STS API client
        sts_client = volcenginesdksts.STSApi(volcenginesdkcore.ApiClient(sts_config))

        # Construct an AssumeRole request
        assume_role_request = volcenginesdksts.AssumeRoleRequest(
            role_trn=role_trn,
            role_session_name=settings.veidentity.role_session_name,
        )

        logger.info(
            f"Executing AssumeRole for role: {role_trn}, "
            f"session: {settings.veidentity.role_session_name}"
        )

        response: volcenginesdksts.AssumeRoleResponse = sts_client.assume_role(
            assume_role_request
        )

        if not response.credentials:
            raise Exception("AssumeRole returned no credentials")

        credentials = response.credentials

        # Parse expiration time
        from datetime import datetime
        import calendar

        try:
            # ExpiredTime format: "2021-04-12T11:57:09+08:00"
            dt = datetime.strptime(
                credentials.expired_time.replace("+08:00", ""), "%Y-%m-%dT%H:%M:%S"
            )
            expires_at_timestamp = calendar.timegm(dt.timetuple())
        except Exception as e:
            logger.warning(f"Failed to parse STS credential expiration time: {e}")
            # Expires in 1 hour by default
            import time

            expires_at_timestamp = int(time.time()) + 3600

        sts_credential = AssumeRoleCredential(
            access_key_id=credentials.access_key_id,
            secret_access_key=credentials.secret_access_key,
            session_token=credentials.session_token,
        )

        # Cached credentials and expiration time
        self._cached_sts_credential = sts_credential
        self._sts_credential_expires_at = expires_at_timestamp

        logger.info(
            f"Successfully obtained and cached STS credentials, "
            f"expires at {datetime.fromtimestamp(expires_at_timestamp).isoformat()}"
        )

        return sts_credential

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
        workload_name: Optional[str] = None,
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
        self,
        principal: Dict[str, str],
        operation: Dict[str, str],
        resource: Dict[str, str],
        original_callers: Optional[List[Dict[str, str]]] = None,
        namespace: str = "default",
    ) -> bool:
        """Check if the principal has permission to perform the operation on the resource.

        Args:
            principal: Principal information, e.g., {"Type": "user", "Id": "user123"}
            operation: Operation to check, e.g., {"Type": "action", "Id": "invoke"}
            resource: Resource information, e.g., {"Type": "agent", "Id": "agent456"}
            original_callers: Optional list of original callers.
            namespace: Namespace of the resource. Defaults to "default".

        Returns:
            True if the principal has permission, False otherwise.

        Raises:
            ValueError: If input parameters are invalid
            RuntimeError: If the permission check API call fails
        """
        logger.info(
            f"Checking permission for principal {principal['Id']} on resource {resource['Id']} for operation {operation['Id']}..."
        )

        request = volcenginesdkid.CheckPermissionRequest(
            namespace_name=namespace,
            operation=operation,
            principal=principal,
            resource=resource,
            original_callers=original_callers,
        )

        response: volcenginesdkid.CheckPermissionResponse = (
            self._api_client.check_permission(request)
        )

        if not hasattr(response, "allowed"):
            logger.error("Permission check failed")
            return False

        logger.info(
            f"Permission check result for principal {principal['Id']} on resource {resource['Id']}: {response.allowed}"
        )
        return response.allowed

    def create_user_pool(self, name: str) -> str:
        from volcenginesdkid import CreateUserPoolRequest, CreateUserPoolResponse

        request = CreateUserPoolRequest(
            name=name,
        )
        response: CreateUserPoolResponse = self._api_client.create_user_pool(request)

        return response.uid

    def get_user_pool(self, name: str) -> str | None:
        from volcenginesdkid import (
            ListUserPoolsRequest,
            ListUserPoolsResponse,
            FilterForListUserPoolsInput,
            DataForListUsersOutput,
        )

        request = ListUserPoolsRequest(
            page_number=1,
            page_size=1,
            filter=FilterForListUserPoolsInput(
                name=name,
            ),
        )
        response: ListUserPoolsResponse = self._api_client.list_user_pools(request)
        if response.total_count == 0:
            return None

        user_pool: DataForListUsersOutput = response.data[0]
        return user_pool.uid

    def create_user_pool_client(
        self, user_pool_uid: str, name: str, client_type: str
    ) -> tuple[str, str]:
        from volcenginesdkid import (
            CreateUserPoolClientRequest,
            CreateUserPoolClientResponse,
        )

        request = CreateUserPoolClientRequest(
            user_pool_uid=user_pool_uid,
            name=name,
            client_type=client_type,
        )
        response: CreateUserPoolClientResponse = (
            self._api_client.create_user_pool_client(request)
        )
        return response.uid, response.client_secret

    def register_callback_for_user_pool_client(
        self,
        user_pool_uid: str,
        client_uid: str,
        callback_url: str,
        web_origin: str,
    ):
        from volcenginesdkid import (
            GetUserPoolClientRequest,
            GetUserPoolClientResponse,
            UpdateUserPoolClientRequest,
        )

        request = GetUserPoolClientRequest(
            user_pool_uid=user_pool_uid,
            client_uid=client_uid,
        )
        response: GetUserPoolClientResponse = self._api_client.get_user_pool_client(
            request
        )

        allowed_callback_urls = response.allowed_callback_urls
        if not allowed_callback_urls:
            allowed_callback_urls = []
        allowed_callback_urls.append(callback_url)
        allowed_web_origins = response.allowed_web_origins
        if not allowed_web_origins:
            allowed_web_origins = []
        allowed_web_origins.append(web_origin)

        request2 = UpdateUserPoolClientRequest(
            user_pool_uid=user_pool_uid,
            client_uid=client_uid,
            name=response.name,
            description=response.description,
            allowed_callback_urls=allowed_callback_urls,
            allowed_logout_urls=response.allowed_logout_urls,
            allowed_web_origins=allowed_web_origins,
            allowed_cors=response.allowed_cors,
            id_token=response.id_token,
            refresh_token=response.refresh_token,
        )
        self._api_client.update_user_pool_client(request2)

    def get_user_pool_client(
        self, user_pool_uid: str, name: str
    ) -> tuple[str, str] | None:
        from volcenginesdkid import (
            ListUserPoolClientsRequest,
            ListUserPoolClientsResponse,
            FilterForListUserPoolClientsInput,
            DataForListUserPoolClientsOutput,
            GetUserPoolClientRequest,
            GetUserPoolClientResponse,
        )

        request = ListUserPoolClientsRequest(
            user_pool_uid=user_pool_uid,
            page_number=1,
            page_size=1,
            filter=FilterForListUserPoolClientsInput(
                name=name,
            ),
        )
        response: ListUserPoolClientsResponse = self._api_client.list_user_pool_clients(
            request
        )
        if response.total_count == 0:
            return None

        client: DataForListUserPoolClientsOutput = response.data[0]
        request2 = GetUserPoolClientRequest(
            user_pool_uid=user_pool_uid,
            client_uid=client.uid,
        )
        response2: GetUserPoolClientResponse = self._api_client.get_user_pool_client(
            request2
        )
        return response2.uid, response2.client_secret
