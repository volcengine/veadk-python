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

from __future__ import annotations

from pathlib import Path
from typing import List, Optional


try:
    from typing_extensions import override
except ImportError:
    from typing import override

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import BaseTool, FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from veadk.tools.skills_tools import (
    SkillsTool,
    read_file_tool,
    write_file_tool,
    edit_file_tool,
    bash_tool,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class SkillsToolset(BaseToolset):
    """Toolset that provides Skills functionality for domain expertise execution.

    This toolset provides skills access through specialized tools:
    1. SkillsTool - Discover and load skill instructions
    2. ReadFileTool - Read files with line numbers
    3. WriteFileTool - Write/create files
    4. EditFileTool - Edit files with precise replacements
    5. BashTool - Execute shell commands

    Skills provide specialized domain knowledge and scripts that the agent can use
    to solve complex tasks. The toolset enables discovery of available skills,
    file manipulation, and command execution.

    Note: For file upload/download, use the ArtifactsToolset separately.
    """

    def __init__(self, skills_directory: str | Path, skills_space_name: Optional[str]):
        """Initialize the skills toolset.

        Args:
          skills_directory: Path to directory containing skill folders.
        """
        super().__init__()
        self.skills_directory = Path(skills_directory)

        # Create skills tools
        self.skills_tool = SkillsTool(self.skills_directory, skills_space_name)
        self.read_file_tool = FunctionTool(func=read_file_tool)
        self.write_file_tool = FunctionTool(write_file_tool)
        self.edit_file_tool = FunctionTool(edit_file_tool)
        self.bash_tool = FunctionTool(bash_tool)

    @override
    async def get_tools(
        self, readonly_context: Optional[ReadonlyContext] = None
    ) -> List[BaseTool]:
        """Get all skills tools.

        Returns:
          List containing all skills tools: skills, read, write, edit, and bash.
        """
        return [
            self.skills_tool,
            self.read_file_tool,
            self.write_file_tool,
            self.edit_file_tool,
            self.bash_tool,
        ]
