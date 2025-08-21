from typing import Any

from attr import dataclass
from google.adk.events import Event
from google.adk.tools import BaseTool


@dataclass
class ToolAttributesParams:
    tool: BaseTool
    args: dict[str, Any]
    function_response_event: Event


TOOL_ATTRIBUTES = {}
