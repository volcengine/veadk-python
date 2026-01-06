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
