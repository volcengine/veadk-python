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

"""Identity integration for ADK.

This module provides integration with VolcEngine Identity Service for managing
authentication and credentials in ADK agents.

Main components:
- IdentityClient: Low-level client for identity service API calls
- WorkloadTokenManager: Manages workload access tokens with caching
- AuthRequestProcessor: Handles OAuth2 flows in agent conversations

Examples:
    from veadk.integrations.ve_identity import (
        VeIdentityFunctionTool,
        oauth2_auth,
    )

    async def get_github_repos(access_token: str):
        # Tool implementation
        pass

    tool = VeIdentityFunctionTool(
        func=get_github_repos,
        auth_config=oauth2_auth(
            provider_name="github",
            scopes=["repo", "user"],
            auth_flow="USER_FEDERATION",
        ),
        into="access_token",
    )
"""

from veadk.integrations.ve_identity.auth_processor import (
    AuthRequestConfig,
    AuthRequestProcessor,
    MockOauth2AuthPoller,
    get_function_call_auth_config,
    get_function_call_id,
    is_pending_auth_event,
)

# New unified tools
from veadk.integrations.ve_identity.auth_config import (
    api_key_auth,
    oauth2_auth,
    workload_auth,
    ApiKeyAuthConfig,
    OAuth2AuthConfig,
    WorkloadAuthConfig,
    VeIdentityAuthConfig,
    get_default_identity_client,
)
from veadk.integrations.ve_identity.function_tool import VeIdentityFunctionTool
from veadk.integrations.ve_identity.mcp_tool import VeIdentityMcpTool
from veadk.integrations.ve_identity.mcp_toolset import VeIdentityMcpToolset
from veadk.integrations.ve_identity.identity_client import IdentityClient
from veadk.integrations.ve_identity.models import (
    OAuth2TokenResponse,
    OAuth2AuthPoller,
    WorkloadToken,
)
from veadk.integrations.ve_identity.token_manager import (
    WorkloadTokenManager,
    get_workload_token,
)

__all__ = [
    # Client
    "IdentityClient",
    # Token management
    "WorkloadTokenManager",
    "get_workload_token",
    "VeIdentityFunctionTool",
    "VeIdentityMcpTool",
    "VeIdentityMcpToolset",
    # Auth configurations
    "api_key_auth",
    "oauth2_auth",
    "workload_auth",
    "ApiKeyAuthConfig",
    "OAuth2AuthConfig",
    "WorkloadAuthConfig",
    "VeIdentityAuthConfig",
    # Auth processor
    "AuthRequestProcessor",
    "AuthRequestConfig",
    "is_pending_auth_event",
    "get_function_call_id",
    "get_function_call_auth_config",
    # Models
    "OAuth2TokenResponse",
    "WorkloadToken",
    "OAuth2AuthPoller",
    "MockOauth2AuthPoller",
    # Utils
    "get_default_identity_client",
]
