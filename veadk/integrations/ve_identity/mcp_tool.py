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

from typing import Any

from typing_extensions import override

from google.genai.types import FunctionDeclaration
from google.adk.auth.auth_credential import AuthCredential
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.adk.tools._gemini_schema_util import _to_gemini_schema

# Attempt to import MCP Tool from the MCP library
try:
    from mcp.types import Tool as McpBaseTool
except ImportError as e:
    import sys
    if sys.version_info < (3, 10):
        raise ImportError(
            "MCP Tool requires Python 3.10 or above. Please upgrade your Python"
            " version."
        ) from e
    else:
        raise e

from google.adk.tools.mcp_tool.mcp_session_manager import MCPSessionManager
from google.adk.tools.mcp_tool.mcp_session_manager import retry_on_closed_resource

from .auth_config import VeIdentityAuthConfig
from .auth_mixins import VeIdentityAuthMixin, AuthRequiredException
from .utils import generate_headers

from veadk.utils.logger import get_logger

logger = get_logger("veadk." + __name__)


class VeIdentityMcpTool(VeIdentityAuthMixin, BaseTool):
    """Unified MCP tool with automatic VeIdentity authentication.

    This tool wraps an MCP Tool interface and automatically handles authentication
    based on the provided auth configuration. It supports both API Key and OAuth2 authentication.

    Examples:
        # API Key authentication
        api_key_tool = VeIdentityMcpTool(
            mcp_tool=mcp_tool,
            mcp_session_manager=session_manager,
            auth_config=api_key_auth("my-provider")
        )

        # OAuth2 authentication
        oauth2_tool = VeIdentityMcpTool(
            mcp_tool=mcp_tool,
            mcp_session_manager=session_manager,
            auth_config=oauth2_auth(
                provider_name="my-provider",
                scopes=["read", "write"],
                auth_flow="M2M"
            )
        )

    Note: For API key authentication, only header-based API keys are supported.
    Query and cookie-based API keys will result in authentication errors.
    """

    def __init__(
        self,
        *,
        mcp_tool: McpBaseTool,
        mcp_session_manager: MCPSessionManager,
        auth_config: VeIdentityAuthConfig,
    ):
        """Initialize the unified Identity MCP tool.

        Args:
            mcp_tool: The MCP tool to wrap.
            mcp_session_manager: The MCP session manager to use for communication.
            auth_config: Authentication configuration (ApiKeyAuthConfig, WorkloadAuthConfig, or OAuth2AuthConfig).

        Raises:
            ValueError: If mcp_tool or mcp_session_manager is None.
        """
        if mcp_tool is None:
            raise ValueError("mcp_tool cannot be None")
        if mcp_session_manager is None:
            raise ValueError("mcp_session_manager cannot be None")

        # Initialize mixins first
        super().__init__(
            name=mcp_tool.name,
            description=mcp_tool.description if mcp_tool.description else "",
            auth_config=auth_config,
        )
        self._mcp_tool = mcp_tool
        self._mcp_session_manager = mcp_session_manager

    @override
    def _get_declaration(self) -> FunctionDeclaration:
        """Gets the function declaration for the tool.

        Returns:
            FunctionDeclaration: The Gemini function declaration for the tool.
        """
        schema_dict = self._mcp_tool.inputSchema
        schema = _to_gemini_schema(schema_dict)

        return FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=schema,
        )

    @override
    async def run_async(
        self, *, args: dict[str, Any], tool_context: ToolContext
    ) -> Any:
        """Execute the wrapped MCP tool with Identity authentication.

        This method handles authentication based on the configured auth type.

        Args:
            args: Arguments to pass to the wrapped tool.
            tool_context: The tool context for accessing session state and auth.

        Returns:
            The result from the wrapped tool, or an auth pending message for OAuth2.
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
        credential: AuthCredential
    ) -> Any:
        """Execute the MCP tool with the provided credential.

        Args:
            args: Arguments to pass to the tool.
            tool_context: The tool context.
            credential: The authentication credential (API key or OAuth2).

        Returns:
            The result from the tool execution.
        """
        return await self._run_async_impl(
            args=args, tool_context=tool_context, credential=credential
        )

    @retry_on_closed_resource
    async def _run_async_impl(
        self, *, args, tool_context: ToolContext, credential: AuthCredential
    ):
        """Runs the tool asynchronously.

        Args:
            args: The arguments as a dict to pass to the tool.
            tool_context: The tool context of the current invocation.
            credential: The authentication credential.

        Returns:
            Any: The response from the tool.
        """
        # Extract headers from credential for session pooling
        headers = generate_headers(credential)

        # Get the session from the session manager
        session = await self._mcp_session_manager.create_session(headers=headers)

        response = await session.call_tool(self._mcp_tool.name, arguments=args)
        return response