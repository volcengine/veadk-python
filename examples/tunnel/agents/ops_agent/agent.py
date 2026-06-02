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

"""Cloud agent that uses on-prem MCP servers via the tunnel.

`enable_tunnel=True` appends a `TunnelToolset`, so any MCP server an enterprise
connector registers to this agent (by its name, "ops_agent") shows up as tools
at run time — no redeploy needed.
"""

from veadk import Agent

agent = Agent(
    name="ops_agent",
    description="Ops assistant backed by the enterprise's on-prem MCP servers.",
    instruction=(
        "You are an enterprise ops assistant. Use the connected on-prem tools "
        "to answer. If no tool is connected yet, say so."
    ),
    enable_tunnel=True,
)

# Required by the Google ADK agent loader.
root_agent = agent
