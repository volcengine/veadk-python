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

from typing import Any, Dict, Optional, List
from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from vanna.tools import RunSqlTool as VannaRunSqlTool
from vanna.core.user import User
from vanna.core.tool import ToolContext as VannaToolContext


class RunSqlTool(BaseTool):
    """Execute SQL queries against a database."""

    def __init__(
        self,
        sql_runner,
        file_system,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        """
        Initialize the SQL tool with custom sql_runner and file_system.

        Args:
            sql_runner: A Vanna SQL runner instance (e.g., SqliteRunner, PostgresRunner)
            file_system: A Vanna file system instance (e.g., LocalFileSystem)
            agent_memory: A Vanna agent memory instance (e.g., DemoAgentMemory)
            access_groups: List of user groups that can access this tool (e.g., ['admin', 'user'])
        """
        self.sql_runner = sql_runner
        self.file_system = file_system
        self.agent_memory = agent_memory
        self.vanna_tool = VannaRunSqlTool(
            sql_runner=sql_runner, file_system=file_system
        )
        self.access_groups = access_groups or ["admin", "user"]  # Default: all groups

        super().__init__(
            name="run_sql",  # Keep the same name as Vanna
            description="Execute a SQL query against the database and return results as a CSV file.",
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "sql": types.Schema(
                        type=types.Type.STRING,
                        description="The SQL query to execute",
                    ),
                },
                required=["sql"],
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
        """Execute the SQL query."""
        sql = args.get("sql", "").strip()

        if not sql:
            return "Error: No SQL query provided"

        try:
            # Get user groups and check access
            user_groups = self._get_user_groups(tool_context)

            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            # Create Vanna context once per request
            vanna_context = self._create_vanna_context(tool_context, user_groups)

            # Execute using Vanna tool
            args_model = self.vanna_tool.get_args_schema()(sql=sql)
            result = await self.vanna_tool.execute(vanna_context, args_model)

            return str(result.result_for_llm)
        except Exception as e:
            return f"Error executing SQL query: {str(e)}"
