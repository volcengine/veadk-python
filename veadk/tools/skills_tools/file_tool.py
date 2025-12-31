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

from google.adk.tools import ToolContext
from veadk.tools.skills_tools.session_path import get_session_path

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def read_file_tool(file_path: str, offset: int, limit: int, tool_context: ToolContext):
    """Read files with line numbers for precise editing.

    Reads a file from the filesystem with line numbers.
    Usage:
    - Provide a path to the file (absolute or relative to your working directory)
    - Returns content with line numbers (format: LINE_NUMBER|CONTENT)
    - Optional offset and limit parameters for reading specific line ranges
    - Lines longer than 2000 characters are truncated
    - Always read a file before editing it
    - You can read from skills/ directory, uploads/, outputs/, or any file in your session

    Args:
        file_path: Path to the file to read (absolute or relative to working directory)
        offset: Optional line number to start reading from (1-indexed)
        limit: Optional number of lines to read
        tool_context: Context of the tool execution

    Returns:
        Content of the file with line numbers, or error message.
    """
    if not file_path:
        return "Error: No file path provided"

    # Resolve path relative to session working directory
    working_dir = get_session_path(session_id=tool_context.session.id)
    path = Path(file_path)
    if not path.is_absolute():
        path = working_dir / path
    path = path.resolve()

    if not path.exists():
        return f"Error: File not found: {file_path}"

    if not path.is_file():
        return f"Error: Path is not a file: {file_path}\nThis tool can only read files, not directories."

    try:
        lines = path.read_text().splitlines()
    except Exception as e:
        return f"Error reading file {file_path}: {e}"

    # Handle offset and limit
    start = (offset - 1) if offset and offset > 0 else 0
    end = (start + limit) if limit else len(lines)

    # Format with line numbers
    result_lines = []
    for i, line in enumerate(lines[start:end], start=start + 1):
        # Truncate long lines
        if len(line) > 2000:
            line = line[:2000] + "..."
        result_lines.append(f"{i:6d}|{line}")

    if not result_lines:
        return "File is empty."

    return "\n".join(result_lines)


def write_file_tool(file_path: str, content: str, tool_context: ToolContext):
    """Write content to files (overwrites existing files).

    Writes content to a file on the filesystem.
    Usage:
    - Provide a path (absolute or relative to working directory) and content to write
    - Overwrites existing files
    - Creates parent directories if needed
    - For existing files, read them first using read_file
    - Prefer editing existing files over writing new ones
    - You can write to your working directory, outputs/, or any writable location
    - Note: skills/ directory is read-only

    Args:
        file_path: Path to the file to write (absolute or relative to working directory)
        content: Content to write to the file
        tool_context: Context of the tool execution

    Returns:
        Success message or error message.
    """
    if not file_path:
        return "Error: No file path provided"

    # Resolve path relative to session working directory
    working_dir = get_session_path(session_id=tool_context.session.id)
    path = Path(file_path)
    if not path.is_absolute():
        path = working_dir / path
    path = path.resolve()

    try:
        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        logger.info(f"Successfully wrote to {file_path}")
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        error_msg = f"Error writing file {file_path}: {e}"
        logger.error(error_msg)
        return error_msg


def edit_file_tool(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool,
    tool_context: ToolContext,
):
    """Edit files by replacing exact string matches.

    Performs exact string replacements in files.
    Usage:
    - You must read the file first using read_file
    - Provide path (absolute or relative to working directory)
    - When editing, preserve exact indentation from the file content
    - Do NOT include line number prefixes in old_string or new_string
    - old_string must be unique unless replace_all=true
    - Use replace_all to rename variables/strings throughout the file
    - old_string and new_string must be different
    - Note: skills/ directory is read-only

    Args:
        file_path: Path to the file to edit (absolute or relative to working directory)
        old_string: The exact text to replace (must exist in file)
        new_string: The text to replace it with (must be different from old_string)
        replace_all: Replace all occurrences (default: false, only replaces first occurrence)
        tool_context: Context of the tool execution

    Returns:
        Success message or error message.
    """
    if not file_path:
        return "Error: No file path provided"

    if old_string == new_string:
        return "Error: old_string and new_string must be different"

    # Resolve path relative to session working directory
    working_dir = get_session_path(session_id=tool_context.session.id)
    path = Path(file_path)
    if not path.is_absolute():
        path = working_dir / path
    path = path.resolve()

    if not path.exists():
        return f"Error: File not found: {file_path}"

    if not path.is_file():
        return f"Error: Path is not a file: {file_path}"

    try:
        content = path.read_text()
    except Exception as e:
        return f"Error reading file {file_path}: {e}"

    # Check if old_string exists
    if old_string not in content:
        return (
            f"Error: old_string not found in {file_path}.\n"
            f"Make sure you've read the file first and are using the exact string."
        )

    # Count occurrences
    count = content.count(old_string)

    if not replace_all and count > 1:
        return (
            f"Error: old_string appears {count} times in {file_path}.\n"
            f"Either provide more context to make it unique, or set "
            f"replace_all=true to replace all occurrences."
        )

    # Perform replacement
    if replace_all:
        new_content = content.replace(old_string, new_string)
    else:
        new_content = content.replace(old_string, new_string, 1)

    try:
        path.write_text(new_content)
        logger.info(f"Successfully replaced {count} occurrence(s) in {file_path}")
        return f"Successfully replaced {count} occurrence(s) in {file_path}"
    except Exception as e:
        error_msg = f"Error writing file {file_path}: {e}"
        logger.error(error_msg)
        return error_msg
