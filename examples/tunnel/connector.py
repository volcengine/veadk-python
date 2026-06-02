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

"""Enterprise side: connect on-prem MCP server(s) to the cloud agent.

Run this *inside your network* (only outbound access to the cloud is needed).
It registers the local server(s) to the cloud agent `ops_agent` and bridges
calls. Per-server auth (headers / query) stays here — secrets never leave the
enterprise.

Env:
  CLOUD_URL      cloud agent base URL (e.g. https://<endpoint>); default localhost:8000
  TUNNEL_TOKEN   tunnel-layer token issued for the agent
"""

import asyncio
import os

from veadk.tunnel import LocalServer, TunnelConnector

CLOUD_URL = os.getenv("CLOUD_URL", "http://127.0.0.1:8000")
TOKEN = os.getenv("TUNNEL_TOKEN")
AGENT = "ops_agent"


async def main() -> None:
    servers = [
        LocalServer(
            name="ops",
            address=os.getenv("LOCAL_MCP_URL", "http://127.0.0.1:9000/mcp"),
            # Per-server auth to reach YOUR MCP server (filled by you, stays local):
            # headers={"Authorization": "Bearer <your-mcp-token>"},
            # query={"api_key": "<your-key>"},
            # tool_filter=["get_employee"],   # optionally expose a subset
        ),
    ]
    connector = TunnelConnector(
        cloud_url=CLOUD_URL,
        agent=AGENT,
        token=TOKEN,
        servers=servers,
    )
    print(
        f"Connecting {[s.name for s in servers]} to agent `{AGENT}` at {CLOUD_URL} ..."
    )
    await connector.start()  # runs until interrupted


if __name__ == "__main__":
    asyncio.run(main())
