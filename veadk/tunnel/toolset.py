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

"""The single toolset that makes tunneled servers show up as agent tools.

An agent created with ``enable_tunnel=True`` gets one ``TunnelToolset`` appended
to its tools. ADK calls ``get_tools()`` on every turn (see
``base_llm_flow.py`` -> ``canonical_tools``), so this toolset reads the registry
each time and returns the tools of whatever servers are currently online for
this agent. Registering/removing a server therefore takes effect on the next
turn with no agent reload.
"""

from __future__ import annotations

import os
from typing import Optional

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset

from veadk.tunnel.protocol import get_protocol
from veadk.tunnel.protocol.base import BaseProtocol
from veadk.tunnel.registry import TunnelRegistry, get_registry
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _self_base_url() -> str:
    """Loopback base URL of the in-process tunnel proxy.

    The toolset runs in the same process as the tunnel server, so it reaches the
    proxy over loopback. Override the port via ``TUNNEL_SELF_PORT`` (defaults to
    ``PORT`` then 8000).
    """
    port = os.getenv("TUNNEL_SELF_PORT") or os.getenv("PORT") or "8000"
    return f"http://127.0.0.1:{port}"


class TunnelToolset(BaseToolset):
    """Aggregates tools of all online tunneled servers for one agent."""

    def __init__(
        self, agent_name: str, registry: Optional[TunnelRegistry] = None
    ) -> None:
        super().__init__()
        self.agent_name = agent_name
        self._registry = registry or get_registry()
        # server_name -> protocol handler (cached so we don't rebuild MCP
        # sessions every turn)
        self._handlers: dict[str, BaseProtocol] = {}

    async def get_tools(
        self, readonly_context: Optional[ReadonlyContext] = None
    ) -> list[BaseTool]:
        servers = self._registry.list_servers(self.agent_name)
        online_names = {s.name for s in servers}

        # Drop handlers whose server went offline.
        for stale in [n for n in self._handlers if n not in online_names]:
            await self._safe_close(self._handlers.pop(stale))

        tools: list[BaseTool] = []
        for server in servers:
            handler = self._handlers.get(server.name)
            if handler is None:
                proxy_url = (
                    f"{_self_base_url()}/tunnel/mcp/{self.agent_name}/{server.name}"
                )
                handler = get_protocol(server.protocol)(server, proxy_url)
                self._handlers[server.name] = handler
            try:
                tools.extend(await handler.get_tools(readonly_context))
            except Exception as e:
                logger.warning(
                    f"Failed to load tools from tunneled server `{server.name}` "
                    f"(agent `{self.agent_name}`): {e}"
                )
        return tools

    async def close(self) -> None:
        for handler in list(self._handlers.values()):
            await self._safe_close(handler)
        self._handlers.clear()

    @staticmethod
    async def _safe_close(handler: BaseProtocol) -> None:
        try:
            await handler.close()
        except Exception as e:  # pragma: no cover
            logger.warning(f"Close tunnel protocol handler failed: {e}")
