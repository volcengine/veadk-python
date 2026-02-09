import pandas as pd
import io
from typing import Any, Dict, Optional, List
from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from vanna.core.user import User
from vanna.core.tool import ToolContext as VannaToolContext


class SummarizeDataTool(BaseTool):
    """Generate statistical summaries of CSV data files."""

    def __init__(
        self,
        file_system,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        """
        Initialize the summarize data tool with custom file_system.

        Args:
            agent_memory: A Vanna agent memory instance (e.g., DemoAgentMemory)
            file_system: A Vanna file system instance (e.g., LocalFileSystem)
            access_groups: List of user groups that can access this tool (e.g., ['admin', 'user'])
        """
        self.agent_memory = agent_memory
        self.file_system = file_system
        self.access_groups = access_groups or ["admin", "user"]

        super().__init__(
            name="summarize_data",
            description="Generate a statistical summary of data from a CSV file.",
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "filename": types.Schema(
                        type=types.Type.STRING,
                        description="The name of the CSV file to summarize",
                    ),
                },
                required=["filename"],
            ),
        )

    def _get_user_groups(self, tool_context: ToolContext) -> List[str]:
        """Get user groups from context."""
        user_groups = tool_context.state.get("user_groups", ["user"])
        return user_groups

    def _check_access(self, user_groups: List[str]) -> bool:
        """Check if user has access to this tool."""
        return any(group in self.access_groups for group in user_groups)

    def _create_vanna_context(
        self, tool_context: ToolContext, user_groups: List[str]
    ) -> VannaToolContext:
        """Create Vanna context from Veadk ToolContext."""
        user_id = tool_context.user_id
        user_email = tool_context.state.get("user_email", "user@example.com")

        vanna_user = User(id=user_id, email=user_email, group_memberships=user_groups)

        vanna_context = VannaToolContext(
            user=vanna_user,
            conversation_id=tool_context.session.id,
            request_id=tool_context.session.id,
            agent_memory=self.agent_memory,
        )

        return vanna_context

    async def run_async(
        self, *, args: Dict[str, Any], tool_context: ToolContext
    ) -> str:
        """Generate a statistical summary of CSV data."""
        filename = args.get("filename", "").strip()

        if not filename:
            return "Error: No filename provided"

        try:
            user_groups = self._get_user_groups(tool_context)

            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)

            # Read the file content
            content = await self.file_system.read_file(filename, vanna_context)

            # Parse into DataFrame
            df = pd.read_csv(io.StringIO(content))

            # Generate summary stats
            description = df.describe().to_markdown()
            head = df.head().to_markdown()
            info = f"Rows: {len(df)}, Columns: {len(df.columns)}\nColumn Names: {', '.join(df.columns)}"

            summary = f"**Data Summary for {filename}**\n\n**Info:**\n{info}\n\n**First 5 Rows:**\n{head}\n\n**Statistical Description:**\n{description}"
            return summary
        except Exception as e:
            return f"Failed to summarize data: {str(e)}"
