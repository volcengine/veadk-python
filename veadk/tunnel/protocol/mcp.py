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

"""MCP protocol handler.

Exposes a tunneled MCP server as ADK tools by pointing a standard ADK
``MCPToolset`` at the in-process tunnel proxy (loopback). The proxy forwards the
streamable-HTTP MCP traffic over the connector's WebSocket to the real MCP
server, so from ADK's perspective it is just a normal streamable-HTTP MCP
server.
"""

from __future__ import annotations

from typing import Optional

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from veadk.tunnel.protocol.base import BaseProtocol
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class McpProtocol(BaseProtocol):
    """Handler for ``protocol="mcp"`` servers (streamable-HTTP MCP)."""

    type = "mcp"

    def __init__(self, descriptor, proxy_base_url: str) -> None:
        super().__init__(descriptor, proxy_base_url)
        self._toolset: Optional[MCPToolset] = None

    def _ensure_toolset(self) -> MCPToolset:
        if self._toolset is None:
            logger.debug(
                f"Create MCPToolset for tunneled server `{self.descriptor.name}` "
                f"via proxy {self.proxy_base_url}"
            )
            self._toolset = MCPToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url=self.proxy_base_url,
                ),
                tool_filter=self.descriptor.tool_filter,
            )
        return self._toolset

    async def get_tools(
        self, readonly_context: Optional[ReadonlyContext] = None
    ) -> list[BaseTool]:
        return await self._ensure_toolset().get_tools(readonly_context)

    async def close(self) -> None:
        if self._toolset is not None:
            try:
                await self._toolset.close()
            except Exception as e:  # pragma: no cover
                logger.warning(f"Close MCPToolset `{self.descriptor.name}` failed: {e}")
            self._toolset = None
