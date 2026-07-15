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

"""A tiny demo MCP server exposing one weather tool over stdio."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("piagent-weather-demo")

_DEFAULT = ("cloudy", "22 C")
_TABLE = {
    "北京": ("sunny", "28 C"),
    "beijing": ("sunny", "28 C"),
    "上海": ("rainy", "19 C"),
    "shanghai": ("rainy", "19 C"),
    "深圳": ("humid", "31 C"),
    "shenzhen": ("humid", "31 C"),
}


@mcp.tool()
def get_weather(city: str) -> str:
    """Return the current weather for a city as 'condition, temperature'."""
    condition, temp = _TABLE.get(city.strip().lower(), _DEFAULT)
    return f"{condition}, {temp}"


if __name__ == "__main__":
    mcp.run()
