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

"""Token manager for agent identity tokens with caching and expiration handling."""

from __future__ import annotations

import time
from typing import Optional, Union

from google.adk.tools.tool_context import ToolContext
from google.adk.agents.readonly_context import ReadonlyContext

from veadk.utils.logger import get_logger

from veadk.integrations.ve_identity.identity_client import IdentityClient
from veadk.integrations.ve_identity.models import WorkloadToken

logger = get_logger(__name__)

# Token expiration buffer in seconds - tokens will be refreshed this many seconds before actual expiration
TOKEN_EXPIRATION_BUFFER_SECONDS = 60


class WorkloadTokenManager:
    """Manager for workload access tokens with automatic caching and expiration handling.

    This class manages the lifecycle of workload access tokens, including:
    - Caching tokens in session state
    - Automatic token refresh when expired
    - Support for different authentication modes (JWT, user ID, workload-only)

    Attributes:
        identity_client: The IdentityClient instance for making API requests.
        region: VolcEngine region for the identity client. Defaults to "cn-beijing".
    """

    def __init__(
        self,
        identity_client: IdentityClient = None,
        region: Optional[str] = "cn-beijing",
    ):
        """Initialize the token manager.

        Args:
            identity_client: The IdentityClient instance to use for token requests.
        """
        self._identity_client = identity_client or IdentityClient(region=region)

    def _build_cache_key(self, tool_context: Union[ToolContext|ReadonlyContext]) -> str:
        """Build a unique cache key for storing the workload token.

        The cache key is composed of the agent name and user ID to ensure
        tokens are properly scoped per agent and user.

        Args:
            tool_context: The tool context containing agent and user information.

        Returns:
            A unique cache key string in the format "workload_token:{agent}:{user}".
        """
        return f"workload_token:{tool_context.agent_name}:{tool_context._invocation_context.user_id}"

    def _is_token_expired(self, expires_at: int) -> bool:
        """Check if a token has expired or will expire soon.

        Args:
            expires_at: The expiration timestamp in seconds since Unix epoch.

        Returns:
            True if the token has expired or will expire within the buffer period,
            False otherwise.
        """
        current_time = int(time.time())
        return current_time >= (expires_at - TOKEN_EXPIRATION_BUFFER_SECONDS)

    async def get_workload_token(
        self,
        tool_context: Union[ToolContext|ReadonlyContext],
        workload_name: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> str:
        """Get or refresh the workload access token.

        This method implements intelligent token caching:
        1. Checks if a valid cached token exists in session state
        2. Returns cached token if not expired
        3. Fetches and caches a new token if expired or not found

        Args:
            tool_context: The tool context containing session state and user information.
            workload_name: Optional workload name. If not provided, uses tool_context.agent_name.
            user_token: Optional JWT token for user-scoped authentication.

        Returns:
            The workload access token string.

        Raises:
            ValueError: If the identity service response is missing required fields.
        """
        cache_key = self._build_cache_key(tool_context)

        # Attempt to retrieve cached token from session state
        cached_data: Optional[WorkloadToken | None] = (
            tool_context._invocation_context.session.state.get(cache_key)
        )

        # Validate and return cached token if still valid, and type check
        if cached_data and isinstance(cached_data, WorkloadToken):
            if cached_data.workload_access_token and cached_data.expires_at:
                if not self._is_token_expired(cached_data.expires_at):
                    logger.info(
                        f"Using cached workload token for agent '{tool_context.agent_name}'"
                    )
                    return cached_data.workload_access_token
                else:
                    logger.info(
                        f"Cached workload token expired for agent '{tool_context.agent_name}', refreshing..."
                    )

        # Token not cached or expired - fetch a new one
        logger.info(
            f"Fetching new workload token for agent '{tool_context.agent_name}'..."
        )

        # Default to agent_name if workload_name not specified
        if not workload_name:
            workload_name = tool_context.agent_name

        # Determine user_id based on authentication mode
        user_id = None if user_token else tool_context._invocation_context.user_id

        # Request new token from identity service
        workload_token: WorkloadToken = await self._identity_client.get_workload_access_token(
            workload_name=workload_name,
            user_token=user_token,
            user_id=user_id,
        )

        tool_context._invocation_context.session.state[cache_key] = workload_token

        logger.info(
            f"Successfully cached new workload token for agent '{tool_context.agent_name}'",
        )

        return workload_token.workload_access_token


async def get_workload_token(
    tool_context: Union[ToolContext|ReadonlyContext],
    identity_client: Optional[IdentityClient] = None,
    workload_name: Optional[str] = None,
    user_token: Optional[str] = None,
    region: str = "cn-beijing",
) -> str:
    """Convenience function to get a workload access token.

    This function creates a token manager and retrieves the token with automatic
    caching and expiration handling. It's a simplified interface for common use cases.

    Args:
        tool_context: The tool context containing session state and user information.
        identity_client: Optional IdentityClient instance. If not provided, creates a new one.
        workload_name: Optional workload name. If not provided, uses tool_context.agent_name.
        user_token: Optional JWT token for user-scoped authentication.
        region: The VolcEngine region for the identity client. Defaults to "cn-beijing".

    Returns:
        The workload access token string.

    Raises:
        ValueError: If the identity service response is missing required fields.
    """
    return await WorkloadTokenManager(
        identity_client=identity_client, region=region
    ).get_workload_token(
        tool_context=tool_context,
        workload_name=workload_name,
        user_token=user_token,
    )
