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

from typing import Dict, List, Optional

try:
    from typing_extensions import override
except ImportError:
    from typing import override

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import BaseTool, FunctionTool
from google.adk.tools.base_toolset import BaseToolset

from veadk.skills.skill import Skill
from veadk.tools.skills_tools import (
    SkillsTool,
    read_file_tool,
    write_file_tool,
    edit_file_tool,
    bash_tool,
    register_skills_tool,
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
    6. RegisterSkillsTool - Register new skills into the remote skill space

    Skills provide specialized domain knowledge and scripts that the agent can use
    to solve complex tasks. The toolset enables discovery of available skills,
    file manipulation, and command execution.
    """

    def __init__(self, skills: Dict[str, Skill], skills_mode: str) -> None:
        """Initialize the skills toolset.

        Args:
            skills: A dictionary of skill.
            skills_mode: The mode of skills operation, e.g., "skills_sandbox".
        """
        super().__init__()

        self.skills_mode = skills_mode

        self._tools = {
            "skills": SkillsTool(skills),
            "read_file": FunctionTool(read_file_tool),
            "write_file": FunctionTool(write_file_tool),
            "edit_file": FunctionTool(edit_file_tool),
            "bash": FunctionTool(bash_tool),
            "register_skills": FunctionTool(register_skills_tool),
        }

    @override
    async def get_tools(
        self, readonly_context: Optional[ReadonlyContext] = None
    ) -> List[BaseTool]:
        """Return tools according to selected skills_mode."""

        match self.skills_mode:
            case "local":
                return list(self._tools.values())

            case "skills_sandbox":
                return []

            case "aio_sandbox":
                return []

            case _:
                logger.warning(
                    f"Unknown skills_mode: {self.skills_mode}, returning empty tool list."
                )
                return []
