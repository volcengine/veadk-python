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

"""A tiny on-prem MCP server to try the tunnel locally (stands in for an
enterprise's real internal MCP server). Streamable-HTTP at /mcp on port 9000.

Run: `python local_mcp_server.py`  (requires `pip install fastmcp`)
"""

import os

from fastmcp import FastMCP

mcp = FastMCP("enterprise-ops")

_EMPLOYEES = {
    "1001": {"name": "Xiao Ming", "dept": "Platform", "leave_days": 12},
    "1002": {"name": "Xiao Hong", "dept": "Sales", "leave_days": 7},
}


@mcp.tool
def get_employee(emp_id: str) -> dict:
    """Look up an employee record by id (e.g. "1001")."""
    return _EMPLOYEES.get(emp_id, {"error": f"no employee {emp_id}"})


@mcp.tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers and return the sum."""
    return a + b


if __name__ == "__main__":
    port = int(os.getenv("LOCAL_MCP_PORT", "9000"))
    mcp.run(transport="http", host="127.0.0.1", port=port, path="/mcp")
