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

from typing import TYPE_CHECKING, Optional, Any
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from veadk.integrations.ve_identity.identity_client import IdentityClient
else:
    # For runtime, use Any to avoid circular import issues
    IdentityClient = Any


class VeIdentityConfig(BaseSettings):
    """Configuration for VolcEngine Identity Service.

    This configuration class manages settings for Agent Identity service,
    including region and endpoint information.

    It also provides a global singleton IdentityClient instance to ensure:
    - Credential caching is shared across the application
    - HTTP connection pooling is reused
    - Consistent configuration throughout the application

    Attributes:
        region: The VolcEngine region for Identity service.
        endpoint: The endpoint URL for Identity service API.
                  If not provided, will be auto-generated based on region.
    """

    model_config = SettingsConfigDict(env_prefix="VEIDENTITY_")

    region: str = "cn-beijing"
    """The VolcEngine region for Identity service.
    """

    endpoint: str = ""
    """The endpoint URL for Identity service API.

    If not provided, the endpoint will be auto-generated based on the region.
    """

    role_session_name: str = "veadk_default_assume_role_session"
    """Role session name, used to distinguish different sessions in audit logs.
    """

    # Global singleton IdentityClient instance
    _identity_client: "IdentityClient|None" = None

    def get_endpoint(self) -> str:
        """Get the endpoint URL for Identity service.

        Returns the configured endpoint if provided, otherwise generates
        the endpoint based on the region.

        Returns:
            The endpoint URL for Identity service API.

        Raises:
            ValueError: If region is not supported.
        """
        if self.endpoint:
            return self.endpoint

        return f"id.{self.region}.volces.com"

    def get_identity_client(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        session_token: Optional[str] = None,
    ) -> IdentityClient:
        """Get or create the global IdentityClient instance.

        This method implements a singleton pattern to ensure only one IdentityClient
        instance is created per configuration. This allows:
        - Credential caching to be shared across the application
        - HTTP connection pooling to be reused
        - Consistent configuration throughout the application

        Args:
            access_key: Optional VolcEngine access key. If not provided, uses env vars.
            secret_key: Optional VolcEngine secret key. If not provided, uses env vars.
            session_token: Optional VolcEngine session token. If not provided, uses env vars.

        Returns:
            The global IdentityClient instance.

        Examples:
            ```python
            from veadk.config import settings

            # Get the global identity client
            identity_client = settings.veidentity.get_identity_client()

            # Use it to get workload tokens
            token = identity_client.get_workload_access_token(
                workload_name="my_workload",
                user_id="user123"
            )
            ```
        """
        # Lazy initialization: create client only when first requested
        if self._identity_client is None:
            from veadk.integrations.ve_identity import IdentityClient

            self._identity_client = IdentityClient(
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token,
                region=self.region,
            )

        return self._identity_client

    def reset_identity_client(self) -> None:
        """Reset the global IdentityClient instance.

        This forces the next call to get_identity_client() to create a new instance.
        Useful for testing or when credentials need to be refreshed.
        """
        self._identity_client = None
