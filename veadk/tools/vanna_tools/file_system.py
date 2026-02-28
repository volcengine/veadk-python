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
from vanna.tools.file_system import (
    WriteFileTool as VannaWriteFileTool,
    ReadFileTool as VannaReadFileTool,
    ListFilesTool as VannaListFilesTool,
    SearchFilesTool as VannaSearchFilesTool,
    EditFileTool as VannaEditFileTool,
)
from vanna.core.user import User
from vanna.core.tool import ToolContext as VannaToolContext


class WriteFileTool(BaseTool):
    """Write content to a file."""

    def __init__(
        self,
        file_system,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        """
        Initialize the write file tool with custom file_system.

        Args:
            agent_memory: A Vanna agent memory instance (e.g., DemoAgentMemory)
            file_system: A Vanna file system instance (e.g., LocalFileSystem)
            access_groups: List of user groups that can access this tool
        """
        self.file_system = file_system
        self.agent_memory = agent_memory
        self.vanna_tool = VannaWriteFileTool(file_system=file_system)
        self.access_groups = access_groups or ["admin", "user"]

        super().__init__(
            name="write_file",
            description="Write content to a file.",
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
                        description="Name of the file to write",
                    ),
                    "content": types.Schema(
                        type=types.Type.STRING,
                        description="Content to write to the file",
                    ),
                    "overwrite": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Whether to overwrite existing files (default: False)",
                    ),
                },
                required=["filename", "content"],
            ),
        )

    def _get_user_groups(self, tool_context: ToolContext) -> List[str]:
        user_groups = tool_context.state.get("user_groups", ["user"])
        return user_groups

    def _check_access(self, user_groups: List[str]) -> bool:
        return any(group in self.access_groups for group in user_groups)

    def _create_vanna_context(
        self, tool_context: ToolContext, user_groups: List[str]
    ) -> VannaToolContext:
        user_id = tool_context.user_id
        user_email = tool_context.state.get("user_email", "user@example.com")

        vanna_user = User(id=user_id, email=user_email, group_memberships=user_groups)
        return VannaToolContext(
            user=vanna_user,
            conversation_id=tool_context.session.id,
            request_id=tool_context.session.id,
            agent_memory=self.agent_memory,
        )

    async def run_async(
        self, *, args: Dict[str, Any], tool_context: ToolContext
    ) -> str:
        filename = args.get("filename", "").strip()
        content = args.get("content", "")
        overwrite = args.get("overwrite", False)

        if not filename:
            return "Error: No filename provided"

        try:
            user_groups = self._get_user_groups(tool_context)
            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)
            args_model = self.vanna_tool.get_args_schema()(
                filename=filename, content=content, overwrite=overwrite
            )
            result = await self.vanna_tool.execute(vanna_context, args_model)
            return str(result.result_for_llm)
        except Exception as e:
            return f"Error writing file: {str(e)}"


class ReadFileTool(BaseTool):
    """Read the contents of a file."""

    def __init__(
        self,
        file_system,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        self.file_system = file_system
        self.agent_memory = agent_memory
        self.vanna_tool = VannaReadFileTool(file_system=file_system)
        self.access_groups = access_groups or ["admin", "user"]

        super().__init__(
            name="read_file",
            description="Read the contents of a file.",
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
                        description="Name of the file to read",
                    ),
                },
                required=["filename"],
            ),
        )

    def _get_user_groups(self, tool_context: ToolContext) -> List[str]:
        user_groups = tool_context.state.get("user_groups", ["user"])
        return user_groups

    def _check_access(self, user_groups: List[str]) -> bool:
        return any(group in self.access_groups for group in user_groups)

    def _create_vanna_context(
        self, tool_context: ToolContext, user_groups: List[str]
    ) -> VannaToolContext:
        user_id = tool_context.user_id
        user_email = tool_context.state.get("user_email", "user@example.com")

        vanna_user = User(id=user_id, email=user_email, group_memberships=user_groups)
        return VannaToolContext(
            user=vanna_user,
            conversation_id=tool_context.session.id,
            request_id=tool_context.session.id,
            agent_memory=self.agent_memory,
        )

    async def run_async(
        self, *, args: Dict[str, Any], tool_context: ToolContext
    ) -> str:
        filename = args.get("filename", "").strip()

        if not filename:
            return "Error: No filename provided"

        try:
            user_groups = self._get_user_groups(tool_context)
            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)
            args_model = self.vanna_tool.get_args_schema()(filename=filename)
            result = await self.vanna_tool.execute(vanna_context, args_model)
            return str(result.result_for_llm)
        except Exception as e:
            return f"Error reading file: {str(e)}"


class ListFilesTool(BaseTool):
    """List files in a directory."""

    def __init__(
        self,
        file_system,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        self.file_system = file_system
        self.agent_memory = agent_memory
        self.vanna_tool = VannaListFilesTool(file_system=file_system)
        self.access_groups = access_groups or ["admin", "user"]

        super().__init__(
            name="list_files",
            description="List files in a directory.",
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "directory": types.Schema(
                        type=types.Type.STRING,
                        description="Directory to list (defaults to current directory)",
                    ),
                },
                required=[],
            ),
        )

    def _get_user_groups(self, tool_context: ToolContext) -> List[str]:
        user_groups = tool_context.state.get("user_groups", ["user"])
        return user_groups

    def _check_access(self, user_groups: List[str]) -> bool:
        return any(group in self.access_groups for group in user_groups)

    def _create_vanna_context(
        self, tool_context: ToolContext, user_groups: List[str]
    ) -> VannaToolContext:
        user_id = tool_context.user_id
        user_email = tool_context.state.get("user_email", "user@example.com")

        vanna_user = User(id=user_id, email=user_email, group_memberships=user_groups)
        return VannaToolContext(
            user=vanna_user,
            conversation_id=tool_context.session.id,
            request_id=tool_context.session.id,
            agent_memory=self.agent_memory,
        )

    async def run_async(
        self, *, args: Dict[str, Any], tool_context: ToolContext
    ) -> str:
        directory = args.get("directory", ".")

        try:
            user_groups = self._get_user_groups(tool_context)
            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)
            args_model = self.vanna_tool.get_args_schema()(directory=directory)
            result = await self.vanna_tool.execute(vanna_context, args_model)
            return str(result.result_for_llm)
        except Exception as e:
            return f"Error listing files: {str(e)}"


class SearchFilesTool(BaseTool):
    """Search for files by name or content."""

    def __init__(
        self,
        file_system,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        self.file_system = file_system
        self.agent_memory = agent_memory
        self.vanna_tool = VannaSearchFilesTool(file_system=file_system)
        self.access_groups = access_groups or ["admin", "user"]

        super().__init__(
            name="search_files",
            description="Search for files by name or content.",
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description="Text to search for in file names or contents",
                    ),
                    "include_content": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Whether to search within file contents (default: True)",
                    ),
                    "max_results": types.Schema(
                        type=types.Type.INTEGER,
                        description="Maximum number of matches to return (default: 20)",
                    ),
                },
                required=["query"],
            ),
        )

    def _get_user_groups(self, tool_context: ToolContext) -> List[str]:
        user_groups = tool_context.state.get("user_groups", ["user"])
        return user_groups

    def _check_access(self, user_groups: List[str]) -> bool:
        return any(group in self.access_groups for group in user_groups)

    def _create_vanna_context(
        self, tool_context: ToolContext, user_groups: List[str]
    ) -> VannaToolContext:
        user_id = tool_context.user_id
        user_email = tool_context.state.get("user_email", "user@example.com")

        vanna_user = User(id=user_id, email=user_email, group_memberships=user_groups)
        return VannaToolContext(
            user=vanna_user,
            conversation_id=tool_context.session.id,
            request_id=tool_context.session.id,
            agent_memory=self.agent_memory,
        )

    async def run_async(
        self, *, args: Dict[str, Any], tool_context: ToolContext
    ) -> str:
        query = args.get("query", "").strip()
        include_content = args.get("include_content", True)
        max_results = args.get("max_results", 20)

        if not query:
            return "Error: No search query provided"

        try:
            user_groups = self._get_user_groups(tool_context)
            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)
            args_model = self.vanna_tool.get_args_schema()(
                query=query, include_content=include_content, max_results=max_results
            )
            result = await self.vanna_tool.execute(vanna_context, args_model)
            return str(result.result_for_llm)
        except Exception as e:
            return f"Error searching files: {str(e)}"


class EditFileTool(BaseTool):
    """Modify specific lines within a file."""

    def __init__(
        self,
        file_system,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        self.file_system = file_system
        self.agent_memory = agent_memory
        self.vanna_tool = VannaEditFileTool(file_system=file_system)
        self.access_groups = access_groups or ["admin", "user"]

        super().__init__(
            name="edit_file",
            description="Modify specific lines within a file.",
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
                        description="Path to the file to edit",
                    ),
                    "edits": types.Schema(
                        type=types.Type.ARRAY,
                        description="List of edits to apply",
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "start_line": types.Schema(
                                    type=types.Type.INTEGER,
                                    description="First line (1-based) affected by this edit",
                                ),
                                "end_line": types.Schema(
                                    type=types.Type.INTEGER,
                                    description="Last line (1-based, inclusive) to replace",
                                ),
                                "new_content": types.Schema(
                                    type=types.Type.STRING,
                                    description="Replacement text",
                                ),
                            },
                        ),
                    ),
                },
                required=["filename", "edits"],
            ),
        )

    def _get_user_groups(self, tool_context: ToolContext) -> List[str]:
        user_groups = tool_context.state.get("user_groups", ["user"])
        return user_groups

    def _check_access(self, user_groups: List[str]) -> bool:
        return any(group in self.access_groups for group in user_groups)

    def _create_vanna_context(
        self, tool_context: ToolContext, user_groups: List[str]
    ) -> VannaToolContext:
        user_id = tool_context.user_id
        user_email = tool_context.state.get("user_email", "user@example.com")

        vanna_user = User(id=user_id, email=user_email, group_memberships=user_groups)
        return VannaToolContext(
            user=vanna_user,
            conversation_id=tool_context.session.id,
            request_id=tool_context.session.id,
            agent_memory=self.agent_memory,
        )

    async def run_async(
        self, *, args: Dict[str, Any], tool_context: ToolContext
    ) -> str:
        filename = args.get("filename", "").strip()
        edits = args.get("edits", [])

        if not filename:
            return "Error: No filename provided"

        if not edits:
            return "Error: No edits provided"

        try:
            user_groups = self._get_user_groups(tool_context)
            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)
            args_model = self.vanna_tool.get_args_schema()(
                filename=filename, edits=edits
            )
            result = await self.vanna_tool.execute(vanna_context, args_model)
            return str(result.result_for_llm)
        except Exception as e:
            return f"Error editing file: {str(e)}"
