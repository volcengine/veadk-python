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

"""A tiny demo MCP server exposing one order-status tool over stdio."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("piagent-order-demo")

_ORDERS = {
    "A10086": {
        "order_id": "A10086",
        "status": "paid",
        "shipping": "will arrive tomorrow",
    },
    "B20001": {
        "order_id": "B20001",
        "status": "processing",
        "shipping": "not shipped yet",
    },
}


@mcp.tool()
def get_order_status(order_id: str) -> dict[str, str]:
    """Return deterministic status data for a demo order."""
    normalized = order_id.strip().upper()
    return _ORDERS.get(
        normalized,
        {
            "order_id": normalized,
            "status": "unknown",
            "shipping": "no matching demo order",
        },
    )


if __name__ == "__main__":
    mcp.run()
