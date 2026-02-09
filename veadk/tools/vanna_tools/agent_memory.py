from typing import Any, Dict, Optional, List
from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from vanna.tools.agent_memory import (
    SaveQuestionToolArgsTool as VannaSaveQuestionToolArgsTool,
    SearchSavedCorrectToolUsesTool as VannaSearchSavedCorrectToolUsesTool,
    SaveTextMemoryTool as VannaSaveTextMemoryTool,
)
from vanna.core.user import User
from vanna.core.tool import ToolContext as VannaToolContext


class SaveQuestionToolArgsTool(BaseTool):
    """Save successful question-tool-argument combinations for future reference."""

    def __init__(
        self,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        """
        Initialize the save tool usage tool with custom agent_memory.

        Args:
            agent_memory: A Vanna agent memory instance (e.g., DemoAgentMemory)
            access_groups: List of user groups that can access this tool (e.g., ['admin'])
        """
        self.agent_memory = agent_memory
        self.vanna_tool = VannaSaveQuestionToolArgsTool()
        self.access_groups = access_groups or ["admin"]  # Default: only admin

        super().__init__(
            name="save_question_tool_args",  # Keep the same name as Vanna
            description="Save a successful question-tool-argument combination for future reference.",
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "question": types.Schema(
                        type=types.Type.STRING,
                        description="The original question that was asked",
                    ),
                    "tool_name": types.Schema(
                        type=types.Type.STRING,
                        description="The name of the tool that was used successfully",
                    ),
                    "args": types.Schema(
                        type=types.Type.OBJECT,
                        description="The arguments that were passed to the tool",
                    ),
                },
                required=["question", "tool_name", "args"],
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
        """Save a tool usage pattern."""
        question = args.get("question", "").strip()
        tool_name = args.get("tool_name", "").strip()
        tool_args = args.get("args", {})

        if not question:
            return "Error: No question provided"

        if not tool_name:
            return "Error: No tool name provided"

        try:
            user_groups = self._get_user_groups(tool_context)

            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)

            args_model = self.vanna_tool.get_args_schema()(
                question=question, tool_name=tool_name, args=tool_args
            )
            result = await self.vanna_tool.execute(vanna_context, args_model)

            return str(result.result_for_llm)
        except Exception as e:
            return f"Error saving tool usage: {str(e)}"


class SearchSavedCorrectToolUsesTool(BaseTool):
    """Search for similar tool usage patterns based on a question."""

    def __init__(
        self,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        """
        Initialize the search similar tools tool with custom agent_memory.

        Args:
            agent_memory: A Vanna agent memory instance (e.g., DemoAgentMemory)
            access_groups: List of user groups that can access this tool (e.g., ['admin', 'user'])
            user_group_resolver: Optional callable that takes ToolContext and returns user groups
        """
        self.agent_memory = agent_memory
        self.vanna_tool = VannaSearchSavedCorrectToolUsesTool()
        self.access_groups = access_groups or ["admin", "user"]

        super().__init__(
            name="search_saved_correct_tool_uses",  # Keep the same name as Vanna
            description="Search for similar tool usage patterns based on a question.",
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "question": types.Schema(
                        type=types.Type.STRING,
                        description="The question to find similar tool usage patterns for",
                    ),
                    "limit": types.Schema(
                        type=types.Type.INTEGER,
                        description="Maximum number of results to return (default: 10)",
                    ),
                },
                required=["question"],
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
        """Search for similar tool usage patterns."""
        question = args.get("question", "").strip()
        limit = args.get("limit", 10)

        if not question:
            return "Error: No question provided"

        try:
            user_groups = self._get_user_groups(tool_context)

            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)

            args_model = self.vanna_tool.get_args_schema()(
                question=question, limit=limit
            )
            result = await self.vanna_tool.execute(vanna_context, args_model)

            return str(result.result_for_llm)
        except Exception as e:
            return f"Error searching similar tools: {str(e)}"


class SaveTextMemoryTool(BaseTool):
    """Save free-form text memories for important insights, observations, or context."""

    def __init__(
        self,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        """
        Initialize the save text memory tool with custom agent_memory.

        Args:
            agent_memory: A Vanna agent memory instance (e.g., DemoAgentMemory)
            access_groups: List of user groups that can access this tool (e.g., ['admin', 'user'])
            user_group_resolver: Optional callable that takes ToolContext and returns user groups
        """
        self.agent_memory = agent_memory
        self.vanna_tool = VannaSaveTextMemoryTool()
        self.access_groups = access_groups or ["admin", "user"]

        super().__init__(
            name="save_text_memory",  # Keep the same name as Vanna
            description="Save free-form text memory for important insights, observations, or context.",
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "content": types.Schema(
                        type=types.Type.STRING,
                        description="The text content to save as a memory",
                    ),
                },
                required=["content"],
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
        """Save a text memory."""
        content = args.get("content", "").strip()

        if not content:
            return "Error: No content provided"

        try:
            user_groups = self._get_user_groups(tool_context)

            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)

            args_model = self.vanna_tool.get_args_schema()(content=content)
            result = await self.vanna_tool.execute(vanna_context, args_model)

            return str(result.result_for_llm)
        except Exception as e:
            return f"Error saving text memory: {str(e)}"
