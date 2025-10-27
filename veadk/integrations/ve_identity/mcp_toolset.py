# Copyright 2025 Google LLC
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

import logging
import sys
from typing import List, Dict, Any
from typing import Optional
from typing import TextIO
from typing import Union


from pydantic import model_validator, field_validator
from typing_extensions import override

from veadk.integrations.ve_identity.auth_config import VeIdentityAuthConfig
from veadk.integrations.ve_identity.auth_mixins import VeIdentityAuthMixin
from veadk.integrations.ve_identity.mcp_tool import VeIdentityMcpTool
from veadk.integrations.ve_identity.utils import generate_headers

# Attempt to import MCP Tool from the MCP library, and hints user to upgrade
# their Python version to 3.10 if it fails.
try:
    from mcp import StdioServerParameters, ClientSession
    from mcp.types import ListToolsResult
except ImportError as e:
    import sys

    if sys.version_info < (3, 10):
        raise ImportError(
            "MCP Tool requires Python 3.10 or above. Please upgrade your Python"
            " version."
        ) from e
    else:
        raise e

from google.adk.tools.mcp_tool.mcp_session_manager import (
    retry_on_closed_resource,
    SseConnectionParams,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
    MCPSessionManager,
)
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset, ToolPredicate
from google.adk.tools.tool_configs import ToolArgsConfig, BaseToolConfig
from google.adk.agents.readonly_context import ReadonlyContext

logger = logging.getLogger(__name__)


class VeIdentityMcpToolset(VeIdentityAuthMixin, BaseToolset):
    """Connects to a MCP Server, and retrieves MCP Tools into ADK Tools.

    Unified MCP toolset with automatic Identity authentication.

    This toolset manages the connection to an MCP server and provides tools
    that can be used by an agent. It properly implements the BaseToolset
    interface for easy integration with the agent framework.

    Examples:
        With API Key authentication:

            from veadk.integrations.ve_identity import VeIdentityMcpToolset, api_key_auth
            from mcp import StdioServerParameters

            toolset = VeIdentityMcpToolset(
                auth_config=api_key_auth("my-provider"),
                connection_params=StdioServerParameters(
                    command='npx',
                    args=["-y", "@modelcontextprotocol/server-filesystem"],
                ),
                tool_filter=['read_file', 'list_directory']
            )

        With OAuth2 authentication:

            from veadk.integrations.ve_identity import VeIdentityMcpToolset, oauth2_auth
            from mcp import StdioServerParameters

            toolset = VeIdentityMcpToolset(
                auth_config=oauth2_auth(
                    provider_name="github",
                    scopes=["repo", "user"],
                    auth_flow="M2M"
                ),
                connection_params=StdioServerParameters(
                    command='npx',
                    args=["-y", "@modelcontextprotocol/server-filesystem"],
                ),
                tool_filter=['read_file', 'list_directory']
            )

        Using in an agent:

            agent = LlmAgent(
                model='gemini-2.0-flash',
                name='enterprise_assistant',
                instruction='Help user accessing their file systems',
                tools=[toolset],
            )

            # Cleanup is handled automatically by the agent framework
            # But you can also manually close if needed:
            # await toolset.close()
    """

    def __init__(
        self,
        *,
        auth_config: VeIdentityAuthConfig,
        connection_params: Union[
            StdioServerParameters,
            StdioConnectionParams,
            SseConnectionParams,
            StreamableHTTPConnectionParams,
        ],
        tool_filter: Optional[Union[ToolPredicate, List[str]]] = None,
        tool_name_prefix: Optional[str] = None,
        errlog: TextIO = sys.stderr,
    ):
        """Initializes the MCPToolset.

        Args:
          auth_config: Authentication configuration (ApiKeyAuthConfig, WorkloadAuthConfig, or OAuth2AuthConfig).
          connection_params: The connection parameters to the MCP server. Can be:
            ``StdioConnectionParams`` for using local mcp server (e.g. using ``npx`` or
            ``python3``); or ``SseConnectionParams`` for a local/remote SSE server; or
            ``StreamableHTTPConnectionParams`` for local/remote Streamable http
            server. Note, ``StdioServerParameters`` is also supported for using local
            mcp server (e.g. using ``npx`` or ``python3`` ), but it does not support
            timeout, and we recommend to use ``StdioConnectionParams`` instead when
            timeout is needed.
          tool_filter: Optional filter to select specific tools. Can be either: - A
            list of tool names to include - A ToolPredicate function for custom
            filtering logic
          tool_name_prefix: A prefix to be added to the name of each tool in this
            toolset.
          errlog: TextIO stream for error logging.
        """
        if not connection_params:
            raise ValueError("Missing connection params in VeIdentityMcpToolset.")

        # Initialize mixins first
        super().__init__(
            auth_config=auth_config,
        )

        # Store Identity specific configuration
        self._auth_config = auth_config
        self._connection_params = connection_params
        self._tool_filter = tool_filter
        self._tool_name_prefix = tool_name_prefix
        self._errlog = errlog

        # Create MCP session manager
        self._mcp_session_manager = MCPSessionManager(
            connection_params=connection_params,
            errlog=errlog,
        )

    @retry_on_closed_resource
    @override
    async def get_tools(
        self,
        readonly_context: Optional[ReadonlyContext] = None,
    ) -> List[BaseTool]:
        """Return all tools in the toolset based on the provided context.

        Args:
            readonly_context: Context used to filter tools available to the agent.
                If None, all tools in the toolset are returned.

        Returns:
            List[BaseTool]: A list of tools available under the specified context.
        """
        if readonly_context is None:
            raise ValueError("Readonly context is required for VeIdentityMcpToolset.")

        # Get credential for authentication
        credential = await self._get_credential(tool_context=readonly_context)

        headers = generate_headers(credential)
        # Get session from session manager
        session: ClientSession = await self._mcp_session_manager.create_session(
            headers=headers
        )

        # Fetch available tools from the MCP server
        tools_response: ListToolsResult = await session.list_tools()

        # Apply filtering based on context and tool_filter
        tools = []
        for tool in tools_response.tools:
            mcp_tool = VeIdentityMcpTool(
                mcp_tool=tool,
                mcp_session_manager=self._mcp_session_manager,
                auth_config=self._auth_config,
            )

            # Apply tool name prefix if specified
            if self._tool_name_prefix:
                mcp_tool._name = f"{self._tool_name_prefix}{mcp_tool.name}"

            if self._is_tool_selected(mcp_tool, readonly_context):
                tools.append(mcp_tool)
        return tools

    def _is_tool_selected(
        self, tool: BaseTool, readonly_context: Optional[ReadonlyContext]
    ) -> bool:
        """Check if a tool should be included based on filters and context."""
        # Apply tool filter if specified
        if self._tool_filter is not None:
            if callable(self._tool_filter):
                # ToolPredicate function
                if not self._tool_filter(tool, readonly_context):
                    return False
            elif isinstance(self._tool_filter, list):
                # List of tool names
                if tool.name not in self._tool_filter:
                    return False

        return True

    async def close(self) -> None:
        """Performs cleanup and releases resources held by the toolset.

        This method closes the MCP session and cleans up all associated resources.
        It's designed to be safe to call multiple times and handles cleanup errors
        gracefully to avoid blocking application shutdown.
        """
        try:
            await self._mcp_session_manager.close()
        except Exception as e:
            # Log the error but don't re-raise to avoid blocking shutdown
            print(f"Warning: Error during MCPToolset cleanup: {e}", file=self._errlog)

    @override
    @classmethod
    def from_config(
        cls, config: ToolArgsConfig, config_abs_path: str
    ) -> "VeIdentityMcpToolset":
        """Create VeIdentityMcpToolset from configuration.

        Priority order:
        1. If config_abs_path points to an existing file, load configuration from that file
        2. Otherwise, use the provided config object directly

        Args:
            config: Configuration object (used as fallback).
            config_abs_path: Absolute path to the config file. If this file exists,
                           it will be loaded as the primary configuration source.

        Returns:
            VeIdentityMcpToolset instance.
        """
        import os

        # Priority 1: Try to load from config_abs_path if it exists
        if config_abs_path and os.path.exists(config_abs_path):
            try:
                file_config_dict = cls._load_config_from_file(config_abs_path)
                # Let Pydantic handle the validation and conversion
                ve_identity_config = VeIdentityMcpToolsetConfig.model_validate(
                    file_config_dict
                )

            except Exception as e:
                # If file loading fails, fall back to config parameter
                print(f"Warning: Failed to load config from {config_abs_path}: {e}")
                print("Falling back to provided config parameter")
                ve_identity_config = VeIdentityMcpToolsetConfig.model_validate(
                    config.model_dump()
                )
        else:
            # Priority 2: Use provided config object
            ve_identity_config = VeIdentityMcpToolsetConfig.model_validate(
                config.model_dump()
            )

        # Determine which connection params to use
        if ve_identity_config.stdio_server_params:
            connection_params = ve_identity_config.stdio_server_params
        elif ve_identity_config.stdio_connection_params:
            connection_params = ve_identity_config.stdio_connection_params
        elif ve_identity_config.sse_connection_params:
            connection_params = ve_identity_config.sse_connection_params
        elif ve_identity_config.streamable_http_connection_params:
            connection_params = ve_identity_config.streamable_http_connection_params
        else:
            raise ValueError(
                "No connection params found in VeIdentityMcpToolsetConfig."
            )

        return cls(
            auth_config=ve_identity_config.auth_config,
            connection_params=connection_params,
            tool_filter=ve_identity_config.tool_filter,
            tool_name_prefix=ve_identity_config.tool_name_prefix,
        )

    @classmethod
    def _load_config_from_file(cls, file_path: str) -> dict:
        """Load configuration from JSON or YAML file.

        Args:
            file_path: Path to the configuration file.

        Returns:
            Configuration dictionary.

        Raises:
            FileNotFoundError: If the config file doesn't exist.
            ValueError: If the file format is not supported or invalid.
        """
        import os
        import json
        import yaml
        from pathlib import Path

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        file_ext = Path(file_path).suffix.lower()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if file_ext in [".json"]:
                    return json.load(f)
                elif file_ext in [".yaml", ".yml"]:
                    return yaml.safe_load(f)
                else:
                    # Try to detect format by content
                    content = f.read()
                    f.seek(0)

                    # Try JSON first
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        # Try YAML
                        try:
                            return yaml.safe_load(content)
                        except yaml.YAMLError:
                            raise ValueError(
                                f"Unsupported configuration file format: {file_ext}"
                            )

        except Exception as e:
            if isinstance(e, (FileNotFoundError, ValueError)):
                raise
            raise ValueError(f"Failed to load configuration from {file_path}: {e}")


class VeIdentityMcpToolsetConfig(BaseToolConfig):
    """Configuration for VeIdentityMcpToolset."""

    model_config = {"arbitrary_types_allowed": True}

    # Authentication configuration
    auth_config: Union[VeIdentityAuthConfig, Dict[str, Any]]

    # Connection parameters (exactly one must be set)
    stdio_server_params: Optional[StdioServerParameters] = None
    stdio_connection_params: Optional[StdioConnectionParams] = None
    sse_connection_params: Optional[SseConnectionParams] = None
    streamable_http_connection_params: Optional[StreamableHTTPConnectionParams] = None

    # Optional toolset configuration
    tool_filter: Optional[List[str]] = None
    tool_name_prefix: Optional[str] = None

    @field_validator("auth_config", mode="before")
    @classmethod
    def _validate_auth_config(cls, v):
        """Convert dict to proper auth config object."""
        if isinstance(v, dict):
            from veadk.integrations.ve_identity.auth_config import api_key_auth, oauth2_auth

            provider_name = v.get("provider_name")
            if not provider_name:
                raise ValueError("provider_name is required in auth_config")

            region = v.get("region", "cn-beijing")

            # Determine auth type based on presence of OAuth2-specific fields
            has_scopes = "scopes" in v
            has_auth_flow = "auth_flow" in v

            if has_scopes or has_auth_flow:
                # OAuth2 configuration
                scopes = v.get("scopes")
                auth_flow = v.get("auth_flow")
                callback_url = v.get("callback_url")
                force_authentication = v.get("force_authentication", False)
                response_for_auth_required = v.get("response_for_auth_required")

                return oauth2_auth(
                    provider_name=provider_name,
                    scopes=scopes,
                    auth_flow=auth_flow,
                    callback_url=callback_url,
                    force_authentication=force_authentication,
                    response_for_auth_required=response_for_auth_required,
                    region=region,
                )
            else:
                # API Key configuration
                return api_key_auth(provider_name=provider_name, region=region)
        return v

    @model_validator(mode="after")
    def _check_only_one_connection_param(self):
        """Ensure exactly one connection parameter is set."""
        connection_fields = [
            self.stdio_server_params,
            self.stdio_connection_params,
            self.sse_connection_params,
            self.streamable_http_connection_params,
        ]
        populated_fields = [f for f in connection_fields if f is not None]

        if len(populated_fields) != 1:
            raise ValueError(
                "Exactly one of stdio_server_params, stdio_connection_params, "
                "sse_connection_params, streamable_http_connection_params must be set."
            )
        return self
