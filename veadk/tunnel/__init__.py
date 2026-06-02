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

"""VeADK Tunnel: connect on-prem resource servers (e.g. MCP) to a cloud agent.

Cloud side (mount onto the ADK FastAPI app):

    from veadk.tunnel import mount_tunnel_if_enabled
    mount_tunnel_if_enabled(app, agents=[root_agent], token="my-token")

Agent side (opt in):

    agent = Agent(name="ops", enable_tunnel=True)

Enterprise side (run inside your network):

    from veadk.tunnel import TunnelConnector, LocalServer
    await TunnelConnector(
        cloud_url="https://<agent-endpoint>",
        agent="ops",
        token="my-token",
        servers=[LocalServer(name="db", address="http://mcp.internal:9000/mcp")],
    ).start()
"""

from veadk.tunnel.connector import LocalServer, TunnelConnector
from veadk.tunnel.registry import ServerDescriptor, TunnelRegistry, get_registry
from veadk.tunnel.server import mount_tunnel, mount_tunnel_if_enabled
from veadk.tunnel.toolset import TunnelToolset

__all__ = [
    "LocalServer",
    "TunnelConnector",
    "ServerDescriptor",
    "TunnelRegistry",
    "get_registry",
    "mount_tunnel",
    "mount_tunnel_if_enabled",
    "TunnelToolset",
]
