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

"""Process-global registry of tunneled resource servers, keyed by agent name.

A local connector registers one or more resource servers (e.g. MCP servers) to a
*named* cloud agent. The agent's :class:`~veadk.tunnel.toolset.TunnelToolset`
reads this registry on every turn to know which servers are currently online and
mount their tools dynamically.

The registry is intentionally a single in-process object: the connector's
WebSocket and the agent run must live in the same process to share it (see the
module docstring of :mod:`veadk.tunnel.server` for the multi-replica caveat).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from veadk.tunnel.server import ConnectorConnection

logger = get_logger(__name__)


class ServerDescriptor(BaseModel):
    """A resource server advertised by a connector.

    Attributes:
        name: Unique name (within the target agent) the agent sees as the tool
            source.
        protocol: Resource protocol type, used to pick a handler class via
            :func:`veadk.tunnel.protocol.get_protocol` (e.g. ``"mcp"``).
        address: How the *connector* reaches the local server (e.g. the
            streamable-HTTP MCP endpoint URL). Stays connector-side; the cloud
            only uses it for display.
        tool_filter: Optional allowlist of tool names to expose.
        headers: User-provided auth headers the connector attaches when calling
            the local server (e.g. ``{"Authorization": "Bearer ..."}``).
        query: User-provided querystring params the connector appends.
    """

    name: str
    protocol: str = "mcp"
    address: str = ""
    tool_filter: Optional[list[str]] = None
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)


class TunnelRegistry:
    """In-process registry mapping ``agent_name`` -> online connector(s)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # connector_id -> connection
        self._connections: dict[str, "ConnectorConnection"] = {}

    def add_connection(self, conn: "ConnectorConnection") -> None:
        with self._lock:
            self._connections[conn.connector_id] = conn
            logger.info(
                f"Connector {conn.connector_id} registered to agent "
                f"`{conn.agent_name}` with servers: {[s.name for s in conn.servers]}"
            )

    def remove_connection(self, connector_id: str) -> None:
        with self._lock:
            conn = self._connections.pop(connector_id, None)
            if conn:
                logger.info(
                    f"Connector {connector_id} (agent `{conn.agent_name}`) removed"
                )

    def list_servers(self, agent_name: str) -> list[ServerDescriptor]:
        """All online server descriptors registered to ``agent_name``."""
        with self._lock:
            servers: list[ServerDescriptor] = []
            for conn in self._connections.values():
                if conn.agent_name == agent_name:
                    servers.extend(conn.servers)
            return servers

    def find_connection(
        self, agent_name: str, server_name: str
    ) -> Optional["ConnectorConnection"]:
        """Connector serving ``server_name`` for ``agent_name`` (for proxying)."""
        with self._lock:
            for conn in self._connections.values():
                if conn.agent_name == agent_name and any(
                    s.name == server_name for s in conn.servers
                ):
                    return conn
            return None

    def has_agent(self, agent_name: str) -> bool:
        with self._lock:
            return any(c.agent_name == agent_name for c in self._connections.values())


_REGISTRY: Optional[TunnelRegistry] = None


def get_registry() -> TunnelRegistry:
    """Return the process-global :class:`TunnelRegistry` (created on first use)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = TunnelRegistry()
    return _REGISTRY
