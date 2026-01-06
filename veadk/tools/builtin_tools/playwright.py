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

from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioConnectionParams,
    StdioServerParameters,
)
import subprocess
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def check_env():
    try:
        result = subprocess.run(
            ["npx", "-v"], capture_output=True, text=True, check=True
        )
        version = result.stdout.strip()
        logger.info(f"Check `npx` command done, version: {version}")
    except Exception as e:
        raise Exception(
            "Check `npx` command failed. Please install `npx` command manually."
        ) from e


check_env()

playwright_tools = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=[
                "-y",
                "@playwright/mcp@latest",
            ],
        ),
        timeout=30,
    ),
    # tool_filter=['browser_navigate', 'browser_screenshot', 'browser_fill', 'browser_click']
)
