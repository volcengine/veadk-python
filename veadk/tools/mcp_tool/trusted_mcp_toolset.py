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
from typing import Union

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from mcp import StdioServerParameters

from .trusted_mcp_session_manager import TrustedMcpSessionManager

from veadk.utils.logger import get_logger

logger = get_logger("veadk." + __name__)


class TrustedMcpToolset(McpToolset):
    """Connects to a TrustedMCP Server, and retrieves MCP Tools into ADK Tools.

    This toolset manages the connection to an TrustedMCP server and provides tools
    that can be used by an agent. It properly implements the BaseToolset
    interface for easy integration with the agent framework.

    Usage::

      toolset = TrustedMcpToolset(
          connection_params=StdioServerParameters(
              command='npx',
              args=["-y", "@modelcontextprotocol/server-filesystem"],
          ),
          tool_filter=['read_file', 'list_directory']  # Optional: filter specific tools
      )

      # Use in an agent
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
        connection_params: Union[
            StdioServerParameters,
            StdioConnectionParams,
            SseConnectionParams,
            StreamableHTTPConnectionParams,
        ],
        # tool_filter: Optional[Union[ToolPredicate, List[str]]] = None,
        # tool_name_prefix: Optional[str] = None,
        # errlog: TextIO = sys.stderr,
        # auth_scheme: Optional[AuthScheme] = None,
        # auth_credential: Optional[AuthCredential] = None,
        # require_confirmation: Union[bool, Callable[..., bool]] = False,
        # header_provider: Optional[Callable[[ReadonlyContext], Dict[str, str]]] = None,
        **kwargs,  # other kwargs for super class (i.e., McpToolset.__init__)
    ):
        """Initializes the TrustedMcpToolset.

        Args: ref McpToolset.__init__
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
          auth_scheme: The auth scheme of the tool for tool calling
          auth_credential: The auth credential of the tool for tool calling
          require_confirmation: Whether tools in this toolset require
            confirmation. Can be a single boolean or a callable to apply to all
            tools.
          header_provider: A callable that takes a ReadonlyContext and returns a
            dictionary of headers to be used for the MCP session.
        """
        # Filter out the kwargs that are not allowed by the super class
        sig = inspect.signature(McpToolset.__init__)
        allowed = set(sig.parameters.keys())
        allowed.discard("self")
        # Filter out args already used in this class
        allowed.discard("connection_params")
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        super().__init__(
            connection_params=connection_params,
            **filtered_kwargs,
        )

        # Create the session manager that will handle the TrustedMCP connection
        logger.info(
            f"TrustedMcpToolset initialized with connection_params: {self._connection_params}"
        )
        self._mcp_session_manager = TrustedMcpSessionManager(
            connection_params=self._connection_params,
            errlog=self._errlog,
        )
