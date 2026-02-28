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
from vanna.tools.python import (
    RunPythonFileTool as VannaRunPythonFileTool,
    PipInstallTool as VannaPipInstallTool,
)
from vanna.core.user import User
from vanna.core.tool import ToolContext as VannaToolContext


class RunPythonFileTool(BaseTool):
    """Execute a Python file using the workspace interpreter."""

    def __init__(
        self,
        file_system,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        """
        Initialize the run Python file tool with custom file_system.

        Args:
            file_system: A Vanna file system instance (e.g., LocalFileSystem)
            agent_memory: A Vanna agent memory instance (e.g., DemoAgentMemory)
            access_groups: List of user groups that can access this tool
        """
        self.file_system = file_system
        self.agent_memory = agent_memory
        self.vanna_tool = VannaRunPythonFileTool(file_system=file_system)
        self.access_groups = access_groups or ["admin", "user"]

        super().__init__(
            name="run_python_file",
            description="Execute a Python file using the workspace interpreter.",
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
                        description="Python file to execute (relative to the workspace root)",
                    ),
                    "arguments": types.Schema(
                        type=types.Type.ARRAY,
                        description="Optional arguments to pass to the Python script",
                        items=types.Schema(type=types.Type.STRING),
                    ),
                    "timeout_seconds": types.Schema(
                        type=types.Type.NUMBER,
                        description="Optional timeout for the command in seconds",
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
        """Create Vanna context from Veadk ToolContext."""
        user_id = tool_context.user_id
        session_id = tool_context.session.id
        user_email = tool_context.state.get("user_email", "user@example.com")

        vanna_user = User(
            id=user_id + "_" + session_id,
            email=user_email,
            group_memberships=user_groups,
        )

        vanna_context = VannaToolContext(
            user=vanna_user,
            conversation_id=session_id,
            request_id=session_id,
            agent_memory=self.agent_memory,
        )

        return vanna_context

    async def run_async(
        self, *, args: Dict[str, Any], tool_context: ToolContext
    ) -> str:
        filename = args.get("filename", "").strip()
        arguments = args.get("arguments", [])
        timeout_seconds = args.get("timeout_seconds")

        if not filename:
            return "Error: No filename provided"

        try:
            user_groups = self._get_user_groups(tool_context)
            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)
            args_model = self.vanna_tool.get_args_schema()(
                filename=filename, arguments=arguments, timeout_seconds=timeout_seconds
            )
            result = await self.vanna_tool.execute(vanna_context, args_model)
            return str(result.result_for_llm)
        except Exception as e:
            return f"Error running Python file: {str(e)}"


class PipInstallTool(BaseTool):
    """Install Python packages using pip."""

    def __init__(
        self,
        file_system,
        agent_memory,
        access_groups: Optional[List[str]] = None,
    ):
        """
        Initialize the pip install tool with custom file_system.

        Args:
            file_system: A Vanna file system instance (e.g., LocalFileSystem)
            agent_memory: A Vanna agent memory instance (e.g., DemoAgentMemory)
            access_groups: List of user groups that can access this tool
        """
        self.file_system = file_system
        self.agent_memory = agent_memory
        self.vanna_tool = VannaPipInstallTool(file_system=file_system)
        self.access_groups = access_groups or ["admin", "user"]

        super().__init__(
            name="pip_install",
            description="Install Python packages using pip.",
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "packages": types.Schema(
                        type=types.Type.ARRAY,
                        description="Packages (with optional specifiers) to install",
                        items=types.Schema(type=types.Type.STRING),
                    ),
                    "upgrade": types.Schema(
                        type=types.Type.BOOLEAN,
                        description="Whether to include --upgrade in the pip invocation (default: False)",
                    ),
                    "extra_args": types.Schema(
                        type=types.Type.ARRAY,
                        description="Additional arguments to pass to pip install",
                        items=types.Schema(type=types.Type.STRING),
                    ),
                    "timeout_seconds": types.Schema(
                        type=types.Type.NUMBER,
                        description="Optional timeout for the command in seconds",
                    ),
                },
                required=["packages"],
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
        """Create Vanna context from Veadk ToolContext."""
        user_id = tool_context.user_id
        session_id = tool_context.session.id
        user_email = tool_context.state.get("user_email", "user@example.com")

        vanna_user = User(
            id=user_id + "_" + session_id,
            email=user_email,
            group_memberships=user_groups,
        )

        vanna_context = VannaToolContext(
            user=vanna_user,
            conversation_id=session_id,
            request_id=session_id,
            agent_memory=self.agent_memory,
        )

        return vanna_context

    async def run_async(
        self, *, args: Dict[str, Any], tool_context: ToolContext
    ) -> str:
        packages = args.get("packages", [])
        upgrade = args.get("upgrade", False)
        extra_args = args.get("extra_args", [])
        timeout_seconds = args.get("timeout_seconds")

        if not packages:
            return "Error: No packages provided"

        try:
            user_groups = self._get_user_groups(tool_context)
            if not self._check_access(user_groups):
                return f"Error: Access denied. This tool requires one of the following groups: {', '.join(self.access_groups)}"

            vanna_context = self._create_vanna_context(tool_context, user_groups)
            args_model = self.vanna_tool.get_args_schema()(
                packages=packages,
                upgrade=upgrade,
                extra_args=extra_args,
                timeout_seconds=timeout_seconds,
            )
            result = await self.vanna_tool.execute(vanna_context, args_model)
            return str(result.result_for_llm)
        except Exception as e:
            return f"Error installing packages: {str(e)}"
