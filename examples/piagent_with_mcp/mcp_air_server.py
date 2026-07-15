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

"""A tiny demo MCP server exposing one air-quality tool over stdio."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("piagent-air-demo")

_DEFAULT = {"aqi": 58, "level": "moderate", "primary_pollutant": "PM2.5"}
_TABLE = {
    "北京": {"aqi": 42, "level": "good", "primary_pollutant": "PM2.5"},
    "beijing": {"aqi": 42, "level": "good", "primary_pollutant": "PM2.5"},
    "上海": {"aqi": 61, "level": "moderate", "primary_pollutant": "O3"},
    "shanghai": {"aqi": 61, "level": "moderate", "primary_pollutant": "O3"},
    "深圳": {"aqi": 35, "level": "good", "primary_pollutant": "PM10"},
    "shenzhen": {"aqi": 35, "level": "good", "primary_pollutant": "PM10"},
}


@mcp.tool()
def get_air_quality(city: str) -> dict[str, object]:
    """Return deterministic air-quality data for a city."""
    return _TABLE.get(city.strip().lower(), _TABLE.get(city.strip(), _DEFAULT))


if __name__ == "__main__":
    mcp.run()
