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

"""A demo assistant backed by local deterministic data sources.

The agent uses VeADK's normal model configuration from `.env`, `config.yaml`,
or environment variables such as MODEL_AGENT_NAME and MODEL_AGENT_API_KEY. The
Pi-specific deployment requirement is a platform-matching Pi binary.
"""

from __future__ import annotations

import sys
from pathlib import Path

from google.adk.skills import load_skill_from_dir
from google.adk.tools.mcp_tool.mcp_session_manager import StdioServerParameters
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.skill_toolset import SkillToolset

from veadk import Agent

_HERE = Path(__file__).resolve().parent
_WEATHER_MCP_SERVER = _HERE / "mcp_server.py"
_AIR_MCP_SERVER = _HERE / "mcp_air_server.py"
_ORDER_MCP_SERVER = _HERE / "mcp_order_server.py"
_SKILL_DIR = _HERE / "skills" / "piagent-e2e-style"


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
style_skill = SkillToolset(skills=[load_skill_from_dir(_SKILL_DIR)])

root_agent = Agent(
    name="piagent_mcp_agent",
    description=(
        "An assistant that answers demo questions about weather, air quality, "
        "and order status using the available data sources."
    ),
    instruction=(
        "Answer concisely. When the user asks about weather, air quality, or "
        "order status, look up the relevant data before answering and do not "
        "invent values. If the user asks for the verification marker, include "
        "the exact marker requested by the loaded guidance."
    ),
    runtime="piagent",
    tools=[style_skill, weather_mcp, air_mcp, order_mcp],
)

# Common alias used by direct scripts and examples.
agent = root_agent
