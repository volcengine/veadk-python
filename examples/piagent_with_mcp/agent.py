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

"""A PiAgent-runtime agent with multiple local stdio MCP toolsets.

The agent uses VeADK's normal model configuration from `.env`, `config.yaml`,
or environment variables such as MODEL_AGENT_NAME and MODEL_AGENT_API_KEY. The
Pi-specific deployment requirement is a platform-matching Pi binary.
"""

from __future__ import annotations

import sys
from pathlib import Path

from google.adk.tools.mcp_tool.mcp_session_manager import StdioServerParameters
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from veadk import Agent

_HERE = Path(__file__).resolve().parent
_WEATHER_MCP_SERVER = _HERE / "mcp_server.py"
_AIR_MCP_SERVER = _HERE / "mcp_air_server.py"
_ORDER_MCP_SERVER = _HERE / "mcp_order_server.py"


def _stdio_mcp(script: Path) -> MCPToolset:
    return MCPToolset(
        connection_params=StdioServerParameters(
            command=sys.executable,
            args=[str(script)],
        )
    )


weather_mcp = _stdio_mcp(_WEATHER_MCP_SERVER)
air_mcp = _stdio_mcp(_AIR_MCP_SERVER)
order_mcp = _stdio_mcp(_ORDER_MCP_SERVER)

root_agent = Agent(
    name="piagent_mcp_agent",
    description="A PiAgent-runtime agent with several local MCP toolsets.",
    instruction=(
        "Answer concisely. Use the available MCP tools before answering when "
        "the user asks about weather, air quality, or order status. Do not "
        "invent those values without calling the relevant tool."
    ),
    runtime="piagent",
    tools=[weather_mcp, air_mcp, order_mcp],
)

# Common alias used by direct scripts and examples.
agent = root_agent
