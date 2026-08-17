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

"""Local Coding Agent discovery and bundled Skill configuration routes."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import frontmatter
from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

CodingAgentId = Literal["trae", "claude-code", "codex"]
BundledSkillId = Literal["agentkit-cli"]

_MAX_FILES_PER_SKILL = 500
_MAX_FILE_BYTES = 5 * 1024 * 1024
_MAX_TOTAL_BYTES = 20 * 1024 * 1024
_MAX_PREVIEW_FILE_BYTES = 256 * 1024


class _AgentSpec(BaseModel):
    name: str
    commands: tuple[str, ...]
    global_skills: str
    home_markers: tuple[str, ...]


class _BundledSkillSpec(BaseModel):
    name: str
    description: str


_AGENT_SPECS: dict[CodingAgentId, _AgentSpec] = {
    "trae": _AgentSpec(
        name="Trae",
        commands=("trae", "trae-cn"),
        global_skills=".trae/skills",
        home_markers=(".trae", ".trae-cn"),
    ),
    "claude-code": _AgentSpec(
        name="Claude Code",
        commands=("claude",),
        global_skills=".claude/skills",
        home_markers=(".claude",),
    ),
    "codex": _AgentSpec(
        name="Codex",
        commands=("codex",),
        global_skills=".agents/skills",
        home_markers=(".codex", ".agents"),
    ),
}

_BUNDLED_SKILLS: dict[BundledSkillId, _BundledSkillSpec] = {
    "agentkit-cli": _BundledSkillSpec(
        name="AgentKit 平台操作技能",
        description="使用 AgentKit CLI 管理部署、运行时与平台资源。",
    ),
}


class _InstallBody(BaseModel):
    agents: list[CodingAgentId] = Field(min_length=1, max_length=3)
    skills: list[BundledSkillId] = Field(min_length=1, max_length=2)


class CodingAgentError(RuntimeError):
    """A bounded local integration error safe to return to the browser."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _default_bundled_skills_dir() -> Path:
    module_path = Path(__file__).resolve()
    candidates = (
        module_path.parents[1] / "webui" / "coding-agent-skills",
        module_path.parents[2] / "frontend" / "public" / "coding-agent-skills",
    )
    return next(
        (candidate for candidate in candidates if candidate.is_dir()), candidates[0]
    )


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


class CodingAgentService:
    def __init__(
        self,
        *,
        home_dir: Path | None = None,
        bundled_skills_dir: Path | None = None,
    ) -> None:
        self.home_dir = Path(home_dir).resolve() if home_dir else Path.home().resolve()
        source = bundled_skills_dir or _default_bundled_skills_dir()
        self.bundled_skills_dir = Path(source).resolve()

    @staticmethod
    def _platform_id() -> str:
        return {
            "Darwin": "macos",
            "Linux": "linux",
            "Windows": "windows",
        }.get(platform.system(), "other")

    @staticmethod
    def _executable(agent_id: CodingAgentId) -> str | None:
        for command in _AGENT_SPECS[agent_id].commands:
            executable = shutil.which(command)
            if executable:
                return executable
        return None

    @staticmethod
    def _version(executable: str) -> str:
        try:
            result = subprocess.run(
                [executable, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        lines = [
            line.strip() for line in f"{result.stdout}\n{result.stderr}".splitlines()
        ]
        return next((line for line in lines if line), "")[:120]

    def _platform_app_candidates(self, agent_id: CodingAgentId) -> tuple[Path, ...]:
        system = platform.system()
        if system == "Darwin":
            names: dict[CodingAgentId, tuple[str, ...]] = {
                "trae": ("Trae.app", "Trae CN.app"),
                "claude-code": (),
                "codex": ("ChatGPT.app", "Codex.app"),
            }
            return tuple(
                base / name
                for base in (Path("/Applications"), self.home_dir / "Applications")
                for name in names[agent_id]
            )
        if system == "Windows":
            local_app_data = Path(
                os.environ.get("LOCALAPPDATA", self.home_dir / "AppData/Local")
            )
            program_files = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
            candidates: dict[CodingAgentId, tuple[Path, ...]] = {
                "trae": (
                    local_app_data / "Programs/Trae/Trae.exe",
                    program_files / "Trae/Trae.exe",
                ),
                "claude-code": (),
                "codex": (
                    local_app_data / "Programs/ChatGPT/ChatGPT.exe",
                    local_app_data / "Microsoft/WindowsApps/ChatGPT.exe",
                ),
            }
            return candidates[agent_id]
        return ()

    def _is_available(
        self, agent_id: CodingAgentId, executable: str | None = None
    ) -> bool:
        spec = _AGENT_SPECS[agent_id]
        if executable or self._executable(agent_id):
            return True
        if any((self.home_dir / marker).exists() for marker in spec.home_markers):
            return True
        return any(
            candidate.exists() for candidate in self._platform_app_candidates(agent_id)
        )

    @staticmethod
    def _display_global_path(relative: str) -> str:
        if platform.system() == "Windows":
            windows_relative = relative.replace("/", "\\")
            return f"%USERPROFILE%\\{windows_relative}"
        return f"~/{relative}"

    def _skills_root(self, agent_id: CodingAgentId) -> Path:
        relative = _AGENT_SPECS[agent_id].global_skills
        root = self.home_dir / relative
        current = self.home_dir
        for part in Path(relative).parts:
            current /= part
            if current.is_symlink():
                raise CodingAgentError(
                    f"Skills 安装目录不能包含符号链接：{relative}",
                    status_code=409,
                )
        return root

    def _load_bundled_skill(self, skill_id: BundledSkillId) -> dict[str, bytes]:
        skill_root = self.bundled_skills_dir / skill_id
        if not skill_root.is_dir() or skill_root.is_symlink():
            raise CodingAgentError(
                f"内置 Skill 资源缺失：{skill_id}",
                status_code=500,
            )

        files: dict[str, bytes] = {}
        total_bytes = 0
        for source in sorted(skill_root.rglob("*")):
            if source.is_symlink():
                raise CodingAgentError(
                    f"内置 Skill 包含符号链接：{skill_id}",
                    status_code=500,
                )
            if not source.is_file():
                continue
            if len(files) >= _MAX_FILES_PER_SKILL:
                raise CodingAgentError(
                    f"内置 Skill 文件数量超过限制：{skill_id}",
                    status_code=500,
                )
            content = source.read_bytes()
            if len(content) > _MAX_FILE_BYTES:
                raise CodingAgentError(
                    f"内置 Skill 单文件超过大小限制：{skill_id}",
                    status_code=500,
                )
            total_bytes += len(content)
            if total_bytes > _MAX_TOTAL_BYTES:
                raise CodingAgentError(
                    f"内置 Skill 总大小超过限制：{skill_id}",
                    status_code=500,
                )
            files[source.relative_to(skill_root).as_posix()] = content

        skill_md = files.get("SKILL.md")
        if skill_md is None:
            raise CodingAgentError(
                f"内置 Skill 缺少 SKILL.md：{skill_id}",
                status_code=500,
            )
        try:
            metadata = frontmatter.loads(skill_md.decode("utf-8")).metadata
        except Exception as error:
            raise CodingAgentError(
                f"内置 Skill 格式不正确：{skill_id}",
                status_code=500,
            ) from error
        if metadata.get("name") != skill_id:
            raise CodingAgentError(
                f"内置 Skill 名称不匹配：{skill_id}",
                status_code=500,
            )
        return files

    def capabilities(self) -> dict[str, Any]:
        skills = []
        for skill_id, spec in _BUNDLED_SKILLS.items():
            self._load_bundled_skill(skill_id)
            skills.append(
                {
                    "id": skill_id,
                    "name": spec.name,
                    "description": spec.description,
                }
            )

        agents = []
        for agent_id, spec in _AGENT_SPECS.items():
            executable = self._executable(agent_id)
            available = self._is_available(agent_id, executable)
            agents.append(
                {
                    "id": agent_id,
                    "name": spec.name,
                    "available": available,
                    "version": self._version(executable) if executable else "",
                    "reason": "" if available else f"未检测到 {spec.name}",
                    "globalSkillsPath": self._display_global_path(spec.global_skills),
                }
            )
        return {
            "platform": self._platform_id(),
            "agents": agents,
            "skills": skills,
        }

    def preview(self, skill_id: BundledSkillId) -> dict[str, Any]:
        files = self._load_bundled_skill(skill_id)
        preview_files = []
        for relative_path, content in files.items():
            text: str | None = None
            if len(content) <= _MAX_PREVIEW_FILE_BYTES:
                try:
                    decoded = content.decode("utf-8")
                except UnicodeDecodeError:
                    pass
                else:
                    if "\0" not in decoded:
                        text = decoded
            preview_files.append(
                {
                    "path": relative_path,
                    "size": len(content),
                    "previewable": text is not None,
                    "content": text,
                }
            )
        return {
            "id": skill_id,
            "name": _BUNDLED_SKILLS[skill_id].name,
            "files": preview_files,
        }

    def install(self, body: _InstallBody) -> dict[str, Any]:
        if len(set(body.agents)) != len(body.agents):
            raise CodingAgentError("选择的 Coding Agents 包含重复项")
        if len(set(body.skills)) != len(body.skills):
            raise CodingAgentError("选择的 Skills 包含重复项")

        for agent_id in body.agents:
            if not self._is_available(agent_id):
                raise CodingAgentError(
                    f"未检测到 {_AGENT_SPECS[agent_id].name}",
                    status_code=409,
                )

        prepared_skills: dict[BundledSkillId, dict[str, bytes]] = {
            skill_id: self._load_bundled_skill(skill_id) for skill_id in body.skills
        }
        destinations: list[
            tuple[CodingAgentId, BundledSkillId, dict[str, bytes], Path]
        ] = [
            (
                agent_id,
                skill_id,
                files,
                self._skills_root(agent_id) / skill_id,
            )
            for agent_id in body.agents
            for skill_id, files in prepared_skills.items()
        ]

        staged: list[tuple[Path, Path]] = []
        committed: list[tuple[Path, Path | None]] = []
        try:
            for _, skill_id, files, destination in destinations:
                destination.parent.mkdir(parents=True, exist_ok=True)
                stage = Path(
                    tempfile.mkdtemp(
                        prefix=f".{skill_id}.veadk-stage-",
                        dir=destination.parent,
                    )
                )
                for relative_path, content in files.items():
                    target = stage / relative_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                staged.append((stage, destination))

            for stage, destination in staged:
                backup: Path | None = None
                if destination.exists() or destination.is_symlink():
                    backup = destination.with_name(
                        f".{destination.name}.veadk-backup-{uuid.uuid4().hex}"
                    )
                    destination.rename(backup)
                committed.append((destination, backup))
                stage.rename(destination)
        except Exception as error:
            for destination, backup in reversed(committed):
                _remove_path(destination)
                if backup is not None and backup.exists():
                    backup.rename(destination)
            for stage, _ in staged:
                _remove_path(stage)
            if isinstance(error, CodingAgentError):
                raise
            raise CodingAgentError("配置 Skill 失败，请检查用户目录权限") from error

        for _, backup in committed:
            if backup is not None:
                _remove_path(backup)

        installations = []
        for agent_id, skill_id, _, _ in destinations:
            relative = f"{_AGENT_SPECS[agent_id].global_skills}/{skill_id}"
            installations.append(
                {
                    "agent": agent_id,
                    "agentName": _AGENT_SPECS[agent_id].name,
                    "skill": _BUNDLED_SKILLS[skill_id].name,
                    "skillId": skill_id,
                    "displayPath": self._display_global_path(relative),
                }
            )
        return {"installations": installations}


def mount_coding_agent_routes(
    app: Any,
    *,
    authorize: Callable[[Request], object],
    home_dir: Path | None = None,
    bundled_skills_dir: Path | None = None,
) -> CodingAgentService:
    """Mount fixed local Coding Agent configuration actions on Studio."""
    service = CodingAgentService(
        home_dir=home_dir,
        bundled_skills_dir=bundled_skills_dir,
    )

    def _http_error(error: CodingAgentError) -> HTTPException:
        return HTTPException(status_code=error.status_code, detail=str(error))

    @app.get("/web/coding-agents/capabilities")
    async def _coding_agent_capabilities(request: Request) -> dict[str, Any]:
        authorize(request)
        try:
            return await run_in_threadpool(service.capabilities)
        except CodingAgentError as error:
            raise _http_error(error) from error

    @app.post("/web/coding-agents/install")
    async def _install_coding_agent_skills(
        body: _InstallBody,
        request: Request,
    ) -> dict[str, Any]:
        authorize(request)
        try:
            return await run_in_threadpool(service.install, body)
        except CodingAgentError as error:
            raise _http_error(error) from error

    @app.get("/web/coding-agents/skills/{skill_id}/preview")
    async def _preview_coding_agent_skill(
        skill_id: BundledSkillId,
        request: Request,
    ) -> dict[str, Any]:
        authorize(request)
        try:
            return await run_in_threadpool(service.preview, skill_id)
        except CodingAgentError as error:
            raise _http_error(error) from error

    return service
