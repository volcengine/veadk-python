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

"""Base class for tunnel resource protocols.

The cloud detects the ``protocol`` field of a registered server and instantiates
the matching :class:`BaseProtocol` subclass (see
:func:`veadk.tunnel.protocol.get_protocol`). The protocol's job is to turn a
tunneled resource into ADK tools the agent can call. The very first
implementation is :class:`veadk.tunnel.protocol.mcp.McpProtocol`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Optional

if TYPE_CHECKING:
    from google.adk.agents.readonly_context import ReadonlyContext
    from google.adk.tools.base_tool import BaseTool

    from veadk.tunnel.registry import ServerDescriptor


class BaseProtocol(ABC):
    """Turns one tunneled server into ADK tools.

    Args:
        descriptor: The registered server descriptor.
        proxy_base_url: Loopback base URL of the in-process tunnel proxy that
            forwards requests to the connector, e.g.
            ``http://127.0.0.1:8000/tunnel/mcp/<agent>/<server>``.
    """

    #: Protocol type discriminator, matched against ``descriptor.protocol``.
    type: ClassVar[str]

    def __init__(self, descriptor: "ServerDescriptor", proxy_base_url: str) -> None:
        self.descriptor = descriptor
        self.proxy_base_url = proxy_base_url

    @abstractmethod
    async def get_tools(
        self, readonly_context: Optional["ReadonlyContext"] = None
    ) -> list["BaseTool"]:
        """Return the ADK tools exposed by this server (called per agent turn)."""

    async def close(self) -> None:  # pragma: no cover - default no-op
        """Release any session/connection held by this protocol handler."""
        return None
