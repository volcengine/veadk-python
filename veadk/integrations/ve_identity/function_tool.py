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

from __future__ import annotations

import inspect
from typing import Any, Callable

from typing_extensions import override

from google.adk.auth.auth_credential import AuthCredential
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext

from veadk.integrations.ve_identity.auth_config import (
    VeIdentityAuthConfig,
    ApiKeyAuthConfig,
    OAuth2AuthConfig,
    WorkloadAuthConfig,
)
from veadk.integrations.ve_identity.auth_mixins import (
    VeIdentityAuthMixin,
    AuthRequiredException,
)

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VeIdentityFunctionTool(VeIdentityAuthMixin, FunctionTool):
    """Unified function tool with automatic VeIdentity authentication.

    This tool wraps a function and automatically handles authentication based on the
    provided auth configuration. It supports both API Key and OAuth2 authentication.

    Examples:
        # API Key authentication
        api_key_tool = VeIdentityFunctionTool(
            func=my_function,
            auth_config=api_key_auth("my-provider"),
            into="api_key"
        )

        # OAuth2 authentication
        oauth2_tool = VeIdentityFunctionTool(
            func=my_function,
            auth_config=oauth2_auth(
                provider_name="my-provider",
                scopes=["read", "write"],
                auth_flow="USER_FEDERATION"
            ),
            into="access_token"
        )
    """

    def __init__(
        self,
        *,
        func: Callable[..., Any],
        auth_config: VeIdentityAuthConfig,
        into: str = None,
    ):
        """Initialize the unified Identity function tool.

        Args:
            func: The function to wrap with Identity authentication.
            auth_config: Authentication configuration (ApiKeyAuthConfig or OAuth2AuthConfig).
            into: Parameter name to inject the credential into. If None, uses default
                 based on auth type ("api_key" for API key, "access_token" for OAuth2).
        """
        # Determine default parameter name based on auth type
        if into is None:
            if isinstance(auth_config, ApiKeyAuthConfig):
                into = "api_key"
            elif isinstance(auth_config, OAuth2AuthConfig):
                into = "access_token"
            elif isinstance(auth_config, WorkloadAuthConfig):
                into = "access_token"
            else:
                raise ValueError(f"Unsupported auth config type: {type(auth_config)}")

        # Initialize mixins first
        super().__init__(
            func=func,
            auth_config=auth_config,
        )
        self._ignore_params.append(into)
        self._into = into

    @override
    async def run_async(
        self, *, args: dict[str, Any], tool_context: ToolContext
    ) -> Any:
        """Execute the wrapped function with Identity authentication.

        This method handles authentication based on the configured auth type.

        Args:
            args: Arguments to pass to the wrapped function.
            tool_context: The tool context for accessing session state and auth.

        Returns:
            The result from the wrapped function, or an auth pending message for OAuth2.
        """
        try:
            return await self.run_with_identity_auth(
                args=args, tool_context=tool_context
            )
        except AuthRequiredException as e:
            # Only OAuth2 can raise this exception
            return e.message

    async def _execute_with_credential(
        self,
        *,
        args: dict[str, Any],
        tool_context: ToolContext,
        credential: AuthCredential,
    ) -> Any:
        """Execute the wrapped function with the provided credential.

        Args:
            args: Arguments for the wrapped function.
            tool_context: The tool context.
            credential: The authentication credential (API key or OAuth2).

        Returns:
            The result from the wrapped function.
        """
        args_to_call = args.copy()
        signature = inspect.signature(self.func)

        # Inject the appropriate credential based on type
        if self._into in signature.parameters:
            if isinstance(self._auth_config, ApiKeyAuthConfig):
                args_to_call[self._into] = credential.api_key
            elif isinstance(self._auth_config, OAuth2AuthConfig):
                args_to_call[self._into] = credential.oauth2.access_token
            elif isinstance(self._auth_config, WorkloadAuthConfig):
                args_to_call[self._into] = credential.oauth2.access_token
            else:
                raise ValueError(
                    f"Unsupported auth config type: {type(self._auth_config)}"
                )

        return await super().run_async(args=args_to_call, tool_context=tool_context)
