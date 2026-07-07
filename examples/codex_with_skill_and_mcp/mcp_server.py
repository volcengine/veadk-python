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

"""A tiny demo MCP server exposing a single ``get_weather`` tool over stdio.

``main.py`` launches this as a subprocess via an MCP stdio transport, so the
example is self-contained (no separate server to start). Swap it for any real
MCP server — stdio or streamable-HTTP — by changing the connection params in
``main.py``.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather-demo")

# Canned data keeps the example deterministic and offline.
_DEFAULT = ("cloudy", "22°C")
_TABLE = {
    "beijing": ("sunny", "28°C"),
    "shanghai": ("rainy", "19°C"),
    "shenzhen": ("humid", "31°C"),
}


@mcp.tool()
def get_weather(city: str) -> str:
    """Return the current weather for a city as 'condition, temperature'."""
    condition, temp = _TABLE.get(city.strip().lower(), _DEFAULT)
    return f"{condition}, {temp}"


if __name__ == "__main__":
    mcp.run()  # stdio transport
