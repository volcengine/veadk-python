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

import asyncio
import os

from google.adk.tools import ToolContext
from veadk.tools.skills_tools.session_path import get_session_path
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


async def bash_tool(
    command: str, description: str, tool_context: ToolContext, timeout: float = 600.0
) -> str:
    """Execute bash commands in the skills environment with local shell.

    This tool uses the local bash shell to execute commands with:
    - Filesystem restrictions (controlled read/write access)
    - Network restrictions (controlled domain access)
    - Process isolation at the OS level

    Use it for command-line operations like running scripts, installing packages, etc.
    For file operations (read/write/edit), use the dedicated file tools instead.

    Execute bash commands in the skills environment with local shell.
    Working Directory & Structure:
    - Commands run in a temporary session directory: /tmp/veadk/{session_id}/
    - Working directory structure:
        /tmp/veadk/{session_id}/
        ├── skills/     -> all skills are available here (read-only).
        ├── uploads/    -> staged user files (temporary)
        └── outputs/    -> generated files for return
    - Your current working directory is added to PYTHONPATH.

    Python Imports (CRITICAL):
    - To import from a skill, use the full path from the 'skills' root.
      Example: from skills.skills_name.module import function
    - If the skills name contains a dash '-', you need to use importlib to import it.
      Example:
        import importlib
        skill_module = importlib.import_module('skills.skill-name.module')

    For file operations:
    - Use read_file, write_file, and edit_file for interacting with the filesystem.

    Timeouts:
    - Default timeout is 600 seconds (10 minutes).
    - Adjust the 'timeout' parameter as needed for longer-running commands.

    Args:
        command: Bash command to execute. Use && to chain commands.
        description: Clear, concise description of what this command does (5-10 words)
        tool_context: The context of the tool execution, including session info.

    Returns:
        The output of the bash command or error message.
    """

    if not command:
        return "Error: No command provided"

    try:
        # Get session working directory (initialized by SkillsPlugin)
        working_dir = get_session_path(session_id=tool_context.session.id)
        logger.info(f"Session working directory: {working_dir}")

        # Prepare environment with PYTHONPATH including skills directory
        # This allows imports like: from skills.slack_gif_creator.core import something
        env = os.environ.copy()
        # Add root for 'from skills...' and working_dir for local scripts
        pythonpath_additions = [str(working_dir), "/"]
        if "PYTHONPATH" in env:
            pythonpath_additions.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = ":".join(pythonpath_additions)

        # Check for BASH_VENV_PATH to use a specific virtual environment
        provided = os.environ.get("BASH_VENV_PATH")
        if provided and os.path.isdir(provided):
            bash_venv_path = provided
            bash_venv_bin = os.path.join(bash_venv_path, "bin")
            logger.info(f"Using provided BASH_VENV_PATH: {bash_venv_path}")
            # Prepend bash venv to PATH so its python and pip are used
            env["PATH"] = f"{bash_venv_bin}:{env.get('PATH', '')}"
            env["VIRTUAL_ENV"] = bash_venv_path

        # Execute with local bash shell
        local_bash_command = f"{command}"

        process = await asyncio.create_subprocess_shell(
            local_bash_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
            env=env,  # Pass the modified environment
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return f"Error: Command timed out after {timeout}s"

        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        # Handle command failure
        if process.returncode != 0:
            error_msg = f"Command failed with exit code {process.returncode}"
            if stderr_str:
                error_msg += f":\n{stderr_str}"
            elif stdout_str:
                error_msg += f":\n{stdout_str}"
            return error_msg

        # Return output
        output = stdout_str
        if stderr_str and "WARNING" not in stderr_str:
            output += f"\n{stderr_str}"

        result = output.strip() if output.strip() else "Command completed successfully."

        logger.info(f"Executed bash command: {command}, description: {description}")
        logger.info(f"Command result: {result}")
        return result
    except Exception as e:
        error_msg = f"Error executing command '{command}': {e}"
        logger.error(error_msg)
        return error_msg
