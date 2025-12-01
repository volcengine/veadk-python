from google.adk.tools.tool_registry import register_tool
from . import models
from . import tools

register_tool(tools.create_ticket)
register_tool(tools.query_cmdb)
