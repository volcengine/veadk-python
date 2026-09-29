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

"""Read-only filesystem tools with familiar shell names and scoped permissions

These tools implement a subset of shell utilities using the Python standard
library, without starting a shell or accepting command-line options
"""

from __future__ import annotations

import asyncio
import difflib
import json
import math
import os
import stat as stat_module
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from fnmatch import fnmatchcase
from itertools import islice
from pathlib import Path

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import BaseTool, FunctionTool
from google.adk.tools.base_toolset import BaseToolset

__all__ = ["BashToolset"]

_TOOLS = ("cat", "find", "grep", "ls", "pwd", "head", "tail", "wc", "stat", "diff")
_DEFAULT_EXCLUDES = (".env", ".env.*", ".ssh", ".aws", "*.pem", "*.key")


@dataclass(frozen=True)
class _Permissions:
    working_directory: Path
    allowed_directories: tuple[Path, ...]
    allowed_tools: frozenset[str]
    exclude_patterns: tuple[str, ...]


class _Execution:
    def __init__(self, timeout: float, max_read_bytes: int, max_entries: int):
        self.deadline = time.monotonic() + timeout
        self.cancelled = threading.Event()
        self.remaining_bytes = max_read_bytes
        self.remaining_entries = max_entries

    def check(self) -> None:
        if self.cancelled.is_set() or time.monotonic() >= self.deadline:
            raise TimeoutError("Tool execution timed out")


class BashToolset(BaseToolset):
    """Ten read-only tools with permissions fixed when the toolset is created

    Example:
        from veadk import Agent
        from veadk.tools.builtin_tools.bash_toolset import BashToolset

        tools = BashToolset(
            working_directory="/workspace",
            allowed_tools=["cat", "find", "grep", "ls"],
            exclude_patterns=[".env", ".env.*", ".ssh", "private"],
        )
        agent = Agent(tools=[tools])

    Args:
        working_directory: Base directory for relative paths, defaulting to cwd
        allowed_directories: Accessible roots, defaulting to working_directory
            Relative roots are resolved against working_directory
        allowed_tools: Enabled tool names, defaulting to all ten tools
            An empty sequence disables every tool
        exclude_patterns: Case-sensitive glob patterns matched against names and
            root-relative paths, including ancestors to exclude whole directories
            None uses common credential-file exclusions; [] explicitly clears them
        timeout: Maximum caller wait in seconds, shared by an entire invocation
        max_output_bytes: Maximum UTF-8 bytes returned in the output field
        max_read_bytes: Maximum total input bytes read by one invocation
        max_entries: Maximum directory entries visited by one invocation

    Permissions apply to both the requested path and its resolved symlink target
    Recursive operations skip symlinks, excluded entries, and special files
    File opens use descriptor-relative traversal without following symlinks to
    reject replacements between path validation and opening, on Linux and macOS

    Each invocation returns output, error (None on success), and truncated
    Output may be partial when an error or a resource limit interrupts a request

    This is application-level access control, not an OS sandbox: the host must
    control directory renames, hard links and mounts inside the allowed roots
    Timeouts cancel the caller and cooperatively stop the read worker; a blocked
    filesystem call cannot be forcibly interrupted by a Python thread
    """

    def __init__(
        self,
        working_directory: str | Path | None = None,
        *,
        allowed_directories: Sequence[str | Path] | None = None,
        allowed_tools: Sequence[str] | None = None,
        exclude_patterns: Sequence[str] | None = None,
        timeout: float = 10.0,
        max_output_bytes: int = 32_768,
        max_read_bytes: int = 8 * 1024 * 1024,
        max_entries: int = 10_000,
    ) -> None:
        super().__init__()
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            raise NotImplementedError("BashToolset requires Linux or macOS")
        for name, values in (
            ("allowed_directories", allowed_directories),
            ("allowed_tools", allowed_tools),
            ("exclude_patterns", exclude_patterns),
        ):
            if isinstance(values, (str, bytes, Path)):
                raise TypeError(f"{name} must be a sequence, not a single value")
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and greater than zero")
        for name, value in (
            ("max_output_bytes", max_output_bytes),
            ("max_read_bytes", max_read_bytes),
            ("max_entries", max_entries),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        cwd = Path(working_directory or Path.cwd()).expanduser().resolve(strict=True)
        roots = tuple(
            (cwd / Path(root).expanduser()).resolve(strict=True)
            for root in (
                allowed_directories if allowed_directories is not None else [cwd]
            )
        )
        if not roots or not cwd.is_dir() or any(not root.is_dir() for root in roots):
            raise ValueError(
                "Working and allowed directories must be existing directories"
            )
        names = frozenset(_TOOLS if allowed_tools is None else allowed_tools)
        if not names.issubset(_TOOLS):
            raise ValueError(f"Unknown tools: {sorted(names.difference(_TOOLS))}")
        patterns = tuple(
            _DEFAULT_EXCLUDES if exclude_patterns is None else exclude_patterns
        )
        if any(not isinstance(pattern, str) or not pattern for pattern in patterns):
            raise ValueError("Exclusion patterns must be nonempty strings")
        self._permissions = _Permissions(cwd, roots, names, patterns)
        self._timeout = timeout
        self._max_output_bytes = max_output_bytes
        self._max_read_bytes = max_read_bytes
        self._max_entries = max_entries
        self._resolve(cwd)
        self._tools = tuple(
            FunctionTool(getattr(self, name)) for name in _TOOLS if name in names
        )

    async def get_tools(
        self, readonly_context: ReadonlyContext | None = None
    ) -> list[BaseTool]:
        return list(self._tools)

    async def close(self) -> None:
        """No persistent processes or file handles are retained"""

    def _check_path(self, path: Path) -> None:
        roots = self._permissions.allowed_directories
        if not any(path.is_relative_to(root) for root in roots):
            raise PermissionError("Path is outside the allowed directories")
        for root in roots:
            if not path.is_relative_to(root):
                continue
            for candidate in (path, *path.parents):
                if not candidate.is_relative_to(root):
                    break
                relative = candidate.relative_to(root).as_posix()
                if any(
                    fnmatchcase(candidate.name, pattern.rstrip("/"))
                    or fnmatchcase(relative, pattern.rstrip("/"))
                    for pattern in self._permissions.exclude_patterns
                ):
                    raise PermissionError("Path is excluded by the toolset permissions")

    def _resolve(self, path: str | Path) -> Path:
        requested = Path(path).expanduser()
        if not requested.is_absolute():
            requested = self._permissions.working_directory / requested
        # Check before normalization too, so excluded/../public cannot bypass policy
        self._check_path(requested)
        requested = Path(os.path.abspath(requested))
        self._check_path(requested)
        resolved = requested.resolve(strict=True)
        self._check_path(resolved)
        return resolved

    @contextmanager
    def _open(self, path: str | Path, *, directory: bool = False) -> Iterator[int]:
        resolved = self._resolve(path)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open(resolved.anchor, directory_flags)
        try:
            for index, part in enumerate(resolved.parts[1:]):
                is_directory = directory or index < len(resolved.parts) - 2
                flags = (
                    directory_flags
                    if is_directory
                    else os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                )
                child = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            mode = os.fstat(descriptor).st_mode
            if directory and not stat_module.S_ISDIR(mode):
                raise NotADirectoryError("Expected a directory")
            if not directory and not stat_module.S_ISREG(mode):
                raise ValueError("Only regular files can be read")
            yield descriptor
        finally:
            os.close(descriptor)

    async def _run(
        self, name: str, operation: Callable[[_Execution], Iterator[str]]
    ) -> dict:
        if name not in self._permissions.allowed_tools:
            return {
                "output": "",
                "error": f"Tool '{name}' is disabled",
                "truncated": False,
            }
        execution = _Execution(self._timeout, self._max_read_bytes, self._max_entries)

        def collect() -> dict:
            output = bytearray()
            truncated = False
            error = None
            try:
                with closing(operation(execution)) as chunks:
                    for chunk in chunks:
                        execution.check()
                        encoded = chunk.encode("utf-8")
                        remaining = self._max_output_bytes - len(output)
                        output.extend(encoded[:remaining])
                        if len(encoded) > remaining:
                            truncated = True
                            break
            except (OSError, ValueError, RuntimeError) as exc:
                error = str(exc)
            return {
                "output": output.decode("utf-8", errors="ignore"),
                "error": error,
                "truncated": truncated,
            }

        try:
            return await asyncio.wait_for(asyncio.to_thread(collect), self._timeout)
        except asyncio.TimeoutError:
            return {
                "output": "",
                "error": "Tool execution timed out",
                "truncated": False,
            }
        finally:
            execution.cancelled.set()

    def _lines(self, path: str, execution: _Execution) -> Iterator[bytes]:
        execution.check()
        with self._open(path) as descriptor:
            with os.fdopen(os.dup(descriptor), "rb") as stream:
                while True:
                    execution.check()
                    line = stream.readline(execution.remaining_bytes + 1)
                    if not line:
                        return
                    execution.remaining_bytes -= len(line)
                    if execution.remaining_bytes < 0:
                        raise ValueError(
                            "Input exceeds max_read_bytes; narrow the request"
                        )
                    yield line

    def _text(self, path: str, execution: _Execution) -> Iterator[str]:
        with closing(self._lines(path, execution)) as lines:
            for line in lines:
                yield line.decode("utf-8", errors="replace")

    def _walk(
        self, path: str, execution: _Execution, max_depth: int, show_hidden: bool = True
    ) -> Iterator[tuple[Path, bool]]:
        if type(max_depth) is not int or max_depth < 0 or max_depth > 100:
            raise ValueError("max_depth must be between 0 and 100")
        start = self._resolve(path)
        pending = [(start, 0)]
        while pending:
            execution.check()
            current, depth = pending.pop()
            if depth >= max_depth:
                continue
            with self._open(current, directory=True) as descriptor:
                with os.scandir(descriptor) as entries:
                    for entry in entries:
                        execution.check()
                        execution.remaining_entries -= 1
                        if execution.remaining_entries < 0:
                            raise ValueError(
                                "Search exceeds max_entries; narrow the request"
                            )
                        if not show_hidden and entry.name.startswith("."):
                            continue
                        child = current / entry.name
                        try:
                            self._check_path(child)
                            if entry.is_symlink():
                                continue
                            is_directory = entry.is_dir(follow_symlinks=False)
                            if not is_directory and not entry.is_file(
                                follow_symlinks=False
                            ):
                                continue
                        except (PermissionError, FileNotFoundError):
                            continue
                        yield child, is_directory
                        if is_directory:
                            pending.append((child, depth + 1))

    def _listing(
        self,
        path: str,
        execution: _Execution,
        max_depth: int,
        pattern: str = "*",
        file_type: str = "all",
        show_hidden: bool = True,
    ) -> Iterator[str]:
        if file_type not in ("all", "file", "directory"):
            raise ValueError("file_type must be all, file or directory")
        with closing(self._walk(path, execution, max_depth, show_hidden)) as entries:
            for child, is_directory in entries:
                kind = "directory" if is_directory else "file"
                if file_type in ("all", kind) and fnmatchcase(child.name, pattern):
                    yield f"{child}{'/' if is_directory else ''}\n"

    async def cat(self, path: str) -> dict:
        """Read a UTF-8 text file within the permitted directories

        Args:
            path: File path, absolute or relative to the working directory
        """
        return await self._run("cat", lambda execution: self._text(path, execution))

    async def pwd(self) -> dict:
        """Return the fixed working directory"""

        def output(execution: _Execution) -> Iterator[str]:
            yield str(self._resolve(self._permissions.working_directory)) + "\n"

        return await self._run("pwd", output)

    async def ls(self, path: str = ".", show_hidden: bool = False) -> dict:
        """List permitted children of a directory, without following symlinks

        Args:
            path: Directory to list
            show_hidden: Include dotfiles except those excluded by permissions
        """
        return await self._run(
            "ls",
            lambda execution: self._listing(
                path, execution, 1, show_hidden=show_hidden
            ),
        )

    async def find(
        self,
        path: str = ".",
        pattern: str = "*",
        file_type: str = "all",
        max_depth: int = 20,
    ) -> dict:
        """Find permitted descendants by filename glob, without following symlinks

        Args:
            path: Directory to search
            pattern: Filename glob such as *.py
            file_type: all, file or directory
            max_depth: Search depth from 0 to 100, with 1 listing direct children
        """
        return await self._run(
            "find",
            lambda execution: self._listing(
                path, execution, max_depth, pattern, file_type
            ),
        )

    async def grep(
        self,
        pattern: str,
        path: str = ".",
        recursive: bool = True,
        ignore_case: bool = False,
        file_pattern: str = "*",
        max_depth: int = 20,
    ) -> dict:
        """Search for literal text and return matching lines with path and line number

        Args:
            pattern: Literal text to find, not a regular expression
            path: File or directory to search
            recursive: Search descendant directories when path is a directory
            ignore_case: Use Unicode case-insensitive matching
            file_pattern: Filename glob used when searching a directory
            max_depth: Maximum recursive directory depth from 0 to 100
        """

        def output(execution: _Execution) -> Iterator[str]:
            resolved = self._resolve(path)
            needle = pattern.casefold() if ignore_case else pattern
            with self._open(resolved, directory=resolved.is_dir()) as descriptor:
                is_directory = stat_module.S_ISDIR(os.fstat(descriptor).st_mode)

            def files() -> Iterator[Path]:
                if not is_directory:
                    yield resolved
                    return
                with closing(
                    self._walk(str(resolved), execution, max_depth if recursive else 1)
                ) as entries:
                    for child, directory in entries:
                        if not directory and fnmatchcase(child.name, file_pattern):
                            yield child

            with closing(files()) as paths:
                for candidate in paths:
                    with closing(self._text(str(candidate), execution)) as lines:
                        for number, line in enumerate(lines, 1):
                            if needle in (line.casefold() if ignore_case else line):
                                yield f"{candidate}:{number}:{line.rstrip(chr(10))}\n"

        return await self._run("grep", output)

    async def head(self, path: str, lines: int = 10) -> dict:
        """Read the first lines of a text file

        Args:
            path: File to read
            lines: Number of lines, between 0 and 10000
        """
        return await self._run(
            "head", lambda execution: self._slice(path, lines, execution, last=False)
        )

    async def tail(self, path: str, lines: int = 10) -> dict:
        """Read the last lines of a text file once, without following updates

        Args:
            path: File to read
            lines: Number of lines, between 0 and 10000
        """
        return await self._run(
            "tail", lambda execution: self._slice(path, lines, execution, last=True)
        )

    def _slice(
        self, path: str, count: int, execution: _Execution, *, last: bool
    ) -> Iterator[str]:
        if type(count) is not int or not 0 <= count <= 10_000:
            raise ValueError("lines must be between 0 and 10000")
        self._resolve(path)
        if count == 0:
            return
        with closing(self._text(path, execution)) as lines:
            yield from deque(lines, maxlen=count) if last else islice(lines, count)

    async def wc(self, path: str) -> dict:
        """Count newline characters, whitespace-separated words and bytes in a file

        Args:
            path: File to count, subject to the total input byte limit
        """

        def output(execution: _Execution) -> Iterator[str]:
            newlines = words = size = 0
            with closing(self._lines(path, execution)) as lines:
                for line in lines:
                    newlines += line.count(b"\n")
                    words += len(line.decode("utf-8", errors="replace").split())
                    size += len(line)
            yield json.dumps({"lines": newlines, "words": words, "bytes": size}) + "\n"

        return await self._run("wc", output)

    async def stat(self, path: str) -> dict:
        """Return file or directory type, size, permissions and modification time

        Args:
            path: File or directory to inspect
        """

        def output(execution: _Execution) -> Iterator[str]:
            resolved = self._resolve(path)
            with self._open(resolved, directory=resolved.is_dir()) as descriptor:
                info = os.fstat(descriptor)
            yield (
                json.dumps(
                    {
                        "path": str(resolved),
                        "type": "directory"
                        if stat_module.S_ISDIR(info.st_mode)
                        else "file",
                        "size_bytes": info.st_size,
                        "permissions": stat_module.filemode(info.st_mode),
                        "modified_at": info.st_mtime,
                    }
                )
                + "\n"
            )

        return await self._run("stat", output)

    async def diff(self, path_a: str, path_b: str, context_lines: int = 3) -> dict:
        """Compare two text files using unified diff, with at most 2000 lines each

        Args:
            path_a: Original file
            path_b: Changed file
            context_lines: Surrounding unchanged lines to include, from 0 to 100
        """

        def output(execution: _Execution) -> Iterator[str]:
            if type(context_lines) is not int or not 0 <= context_lines <= 100:
                raise ValueError("context_lines must be between 0 and 100")
            contents = []
            for path in (path_a, path_b):
                with closing(self._text(path, execution)) as lines:
                    content = list(islice(lines, 2001))
                if len(content) > 2000:
                    raise ValueError("diff accepts at most 2000 lines per file")
                contents.append(content)
            for line in difflib.unified_diff(
                *contents, fromfile=path_a, tofile=path_b, n=context_lines
            ):
                execution.check()
                yield (
                    line
                    if line.endswith("\n")
                    else line + "\n\\ No newline at end of file\n"
                )

        return await self._run("diff", output)
