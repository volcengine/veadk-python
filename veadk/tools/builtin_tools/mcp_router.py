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

from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from veadk.config import getenv
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)

url = getenv("TOOL_MCP_ROUTER_URL")
api_key = getenv("TOOL_MCP_ROUTER_API_KEY")

mcp_router = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=url, headers={"Authorization": f"Bearer {api_key}"}
    ),
)
