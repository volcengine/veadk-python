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

"""Tunnel protocol registry: detect the protocol type and pick a handler class.

Add a new protocol by subclassing :class:`BaseProtocol` and registering it here.
"""

from veadk.tunnel.protocol.base import BaseProtocol
from veadk.tunnel.protocol.mcp import McpProtocol

PROTOCOLS: dict[str, type[BaseProtocol]] = {
    McpProtocol.type: McpProtocol,
}


def get_protocol(protocol_type: str) -> type[BaseProtocol]:
    """Return the protocol handler class for ``protocol_type``.

    Raises:
        ValueError: If the protocol type is not supported.
    """
    try:
        return PROTOCOLS[protocol_type]
    except KeyError:
        raise ValueError(
            f"Unsupported tunnel protocol `{protocol_type}`. "
            f"Supported: {sorted(PROTOCOLS)}"
        )


__all__ = ["BaseProtocol", "McpProtocol", "PROTOCOLS", "get_protocol"]
