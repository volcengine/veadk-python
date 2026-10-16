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

"""Materialize resources referenced by a frozen Managed Agent Session."""

from __future__ import annotations

import asyncio
import atexit
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import anthropic
import httpx2
from anthropic.lib.tools._skills import _download_and_extract
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

_ACTIVE_TEMP_DIRS: set[Path] = set()


def _cleanup_all_active_temp_dirs() -> None:
    for path in list(_ACTIVE_TEMP_DIRS):
        try:
            shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
        _ACTIVE_TEMP_DIRS.discard(path)


atexit.register(_cleanup_all_active_temp_dirs)


class SessionSkillMaterializationError(RuntimeError):
    """A Session cannot run until its frozen Skill package is available."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class ManagedMcpToolset(McpToolset):
    """Keep the owning server name on resolved tools for event attribution."""

    def __init__(
        self, *, server_name: str, identity_headers: Any = None, **kwargs: Any
    ) -> None:
        self.managed_agents_server_name = server_name
        self.identity_headers = identity_headers
        super().__init__(**kwargs)

    async def get_tools(self, readonly_context: Any = None) -> list[Any]:
        if self.identity_headers is not None:
            await self.identity_headers.prepare()
        tools = await super().get_tools(readonly_context)
        for tool in tools:
            tool.managed_agents_mcp_server_name = self.managed_agents_server_name
        return tools


def field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def session_workdir(root: Path, session_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id).strip("._")
    if not safe_id or safe_id != session_id:
        raise ValueError(
            "Managed Session id must contain only letters, numbers, underscores, dots or hyphens"
        )
    result = (root.resolve() / "sessions" / safe_id).resolve()
    result.relative_to(root.resolve())
    result.mkdir(parents=True, exist_ok=True, mode=0o700)
    return result


async def materialize_session_skills(
    session: Any,
    workdir: Path | None = None,
    *,
    client: anthropic.AsyncAnthropic,
) -> list[Path]:
    """Materialize every pinned Session Skill through the Anthropic SDK."""
    references = list(field(field(session, "agent"), "skills", []) or [])
    if not references:
        return []

    session_id = str(field(session, "id") or "session")
    safe_prefix = re.sub(r"[^A-Za-z0-9_]", "_", session_id)[:8] or "skills"
    if workdir is not None:
        workdir = workdir.resolve()
        workdir.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Keep each invocation isolated, but inside the file tools' workspace.
    work_root = Path(
        tempfile.mkdtemp(prefix=f"ma_session_skills_{safe_prefix}_", dir=workdir)
    ).resolve()
    _ACTIVE_TEMP_DIRS.add(work_root)

    try:
        result = await download_session_skills(
            client, workdir=work_root, session=session
        )
        if len(result) != len(references):
            raise RuntimeError(
                f"Anthropic SDK materialized {len(result)} of {len(references)} Session Skills"
            )
        for directory in result:
            if not (directory / "SKILL.md").is_file():
                raise RuntimeError(
                    f"Anthropic SDK materialized Skill without SKILL.md: {directory}"
                )
        return result
    except (Exception, asyncio.CancelledError) as error:
        await asyncio.to_thread(shutil.rmtree, work_root, True)
        _ACTIVE_TEMP_DIRS.discard(work_root)
        if isinstance(error, asyncio.CancelledError):
            raise
        if isinstance(error, SessionSkillMaterializationError):
            raise
        raise SessionSkillMaterializationError(
            "failed to materialize pinned Session Skills",
            retryable=_skill_failure_retryable(error),
        ) from error


def _skill_failure_retryable(error: Exception) -> bool:
    if isinstance(
        error,
        (
            anthropic.APIConnectionError,
            httpx2.TransportError,
            ConnectionError,
            TimeoutError,
        ),
    ):
        return True
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status in (408, 429) or status >= 500
    return bool(getattr(error, "retryable", False))


async def download_session_skills(
    client: anthropic.AsyncAnthropic, *, workdir: Path, session: Any
) -> list[Path]:
    """Download all pinned skills, preserving SDK failures for retry decisions.

    The SDK's session helper logs and skips failures. Use its streaming download
    and safe archive extractor directly because every frozen skill is required.
    """
    skills_root = (workdir / "skills").resolve()
    downloaded: list[Path] = []
    for skill in field(field(session, "agent"), "skills", []) or []:
        skill_id = field(skill, "skill_id")
        version = await client.beta.skills.versions.retrieve(
            field(skill, "version"), skill_id=skill_id
        )
        dirname = os.path.basename(version.name.strip()) or skill_id
        if dirname in ("", ".", ".."):
            dirname = skill_id
        dest = (skills_root / dirname).resolve()
        if dest == skills_root or not dest.is_relative_to(skills_root):
            raise ValueError("Skill name escapes the skills directory")
        if dest in downloaded:
            raise ValueError("Session Skills have conflicting directory names")
        await _download_and_extract(client, skill_id, version.id, dest)
        downloaded.append(dest)
    return downloaded


async def cleanup_session_skills(skill_dirs: list[Path]) -> None:
    """Remove owned download roots without following agent-mutated symlinks."""
    roots = {
        root
        for root in _ACTIVE_TEMP_DIRS
        if any(directory.absolute().is_relative_to(root) for directory in skill_dirs)
    }
    for root in roots:
        if root.is_symlink():
            await asyncio.to_thread(root.unlink, missing_ok=True)
        else:
            await asyncio.to_thread(shutil.rmtree, root, True)
        _ACTIVE_TEMP_DIRS.discard(root)


def skill_instructions(skill_dirs: list[Path]) -> str:
    """Build model context from materialized pinned Skill packages."""
    blocks: list[str] = []
    for directory in skill_dirs:
        skill_file = directory / "SKILL.md"
        if not skill_file.is_file():
            raise RuntimeError(f"materialized Skill has no SKILL.md: {directory}")
        blocks.append(
            f"<skill name={directory.name!r} path={str(skill_file)!r}>\n"
            f"{skill_file.read_text(encoding='utf-8')}\n</skill>"
        )
    if not blocks:
        return ""
    return (
        "\n\n<managed_agent_skills>\n"
        "The following Session-pinned skills were materialized by the Worker. "
        "Follow their instructions when relevant. Supporting files are below each listed path.\n"
        + "\n\n".join(blocks)
        + "\n</managed_agent_skills>"
    )


def _enabled(config: Any, default: bool) -> bool:
    value = field(config, "enabled")
    return default if value is None else bool(value)


def mcp_toolsets(snapshot: Any, *, credential_keys: Any = None) -> list[McpToolset]:
    """Translate frozen URL MCP definitions and tool policies into ADK toolsets."""
    servers = {
        str(field(server, "name", "")): server
        for server in field(snapshot, "mcp_servers", []) or []
    }
    bindings = {}
    for reference in credential_keys or []:
        name = field(reference, "MCPServerName")
        if name is None:
            continue
        if name not in servers or name in bindings:
            raise ValueError("Invalid Session MCP credential binding")
        bindings[name] = reference
    result: list[McpToolset] = []
    for toolset in field(snapshot, "tools", []) or []:
        if field(toolset, "type") != "mcp_toolset":
            continue
        server_name = str(field(toolset, "mcp_server_name", ""))
        server = servers.get(server_name)
        if server is None:
            raise ValueError(f"MCP toolset references unknown server {server_name!r}")
        if field(server, "type") != "url":
            raise ValueError(f"MCP server {server_name!r} must use type=url")
        url = str(field(server, "url", ""))
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"MCP server {server_name!r} must use an HTTP(S) URL")

        default = field(toolset, "default_config", {}) or {}
        default_enabled = _enabled(default, True)
        configs = {
            str(field(item, "name", "")): item
            for item in field(toolset, "configs", []) or []
        }

        def selected(
            tool: Any,
            _context: Any,
            *,
            configs=configs,
            default_enabled=default_enabled,
        ) -> bool:
            config = configs.get(str(getattr(tool, "name", "")), {})
            return _enabled(config, default_enabled)

        identity_headers = None
        if field(server, "authorization") is not None:
            raise ValueError("MCP credentials must be associated with the Session")
        if reference := bindings.get(server_name):
            from veadk.runtime.managed_agents.identity import MCPIdentityHeaders

            identity_headers = MCPIdentityHeaders(reference)
        result.append(
            ManagedMcpToolset(
                server_name=server_name,
                identity_headers=identity_headers,
                header_provider=identity_headers,
                connection_params=StreamableHTTPConnectionParams(url=url),
                tool_filter=selected,
                tool_name_prefix=f"mcp__{server_name}_",
            )
        )
    return result


__all__ = [
    "SessionSkillMaterializationError",
    "cleanup_session_skills",
    "field",
    "materialize_session_skills",
    "mcp_toolsets",
    "session_workdir",
    "skill_instructions",
]
