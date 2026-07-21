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

"""Materialize selected skills into backend-generated projects."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode

import httpx

from veadk.cli.generated_agent_codegen import (
    AgentDraft,
    GeneratedFile,
    GeneratedProject,
    SelectedSkill,
)
from veadk.cli.generated_agent_security import DebugPolicyError


SkillSpaceResolver = Callable[..., Awaitable[str]]

SKILLHUB_BASE = "https://skills.volces.com/v1/skills"
MAX_SKILL_FILES = 80
MAX_SKILL_FILE_BYTES = 256 * 1024
MAX_SKILL_TOTAL_BYTES = 2 * 1024 * 1024
_SKILL_MD_RE = re.compile(r"(^|/)skill\.md$", re.IGNORECASE)
_FOLDER_RE = re.compile(r"^[A-Za-z0-9_-]+$")


async def materialize_selected_skills(
    draft: AgentDraft,
    project: GeneratedProject,
    *,
    resolve_skillspace_detail: SkillSpaceResolver | None = None,
) -> None:
    existing = {file.path for file in project.files}
    for skill in _collect_selected_skills(draft):
        if skill.source == "skillhub":
            files = await _download_skillhub_skill(skill)
        elif skill.source == "skillspace":
            if resolve_skillspace_detail is None:
                raise DebugPolicyError("SkillSpace resolver is not configured")
            files = await _materialize_skillspace_skill(
                skill, resolve_skillspace_detail
            )
        else:
            files = _materialize_local_skill(skill)
        _append_skill_files(project, existing, files)


def _collect_selected_skills(draft: AgentDraft) -> list[SelectedSkill]:
    out: list[SelectedSkill] = []
    seen: set[str] = set()

    def visit(node: AgentDraft) -> None:
        for skill in node.selectedSkills:
            key = _skill_key(skill)
            if key not in seen:
                seen.add(key)
                out.append(skill)
        for sub in node.subAgents:
            visit(sub)

    visit(draft)
    return out


def _skill_key(skill: SelectedSkill) -> str:
    if skill.source == "skillhub":
        return f"hub:{skill.namespace or 'public'}/{skill.slug}"
    if skill.source == "local":
        return f"local:{skill.folder}"
    return f"ss:{skill.skillSpaceId}/{skill.skillId}/{skill.version or ''}"


async def _download_skillhub_skill(skill: SelectedSkill) -> list[GeneratedFile]:
    slug = skill.slug.strip()
    if not slug:
        raise DebugPolicyError("Skill Hub skill is missing slug")
    namespace = skill.namespace or "public"
    url = (
        f"{SKILLHUB_BASE}/download/{quote(slug, safe='/')}"
        f"?{urlencode({'namespace': namespace})}"
    )
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        res = await client.get(url)
    if res.status_code >= 400:
        raise DebugPolicyError(
            f"Failed to download Skill Hub skill ({res.status_code})"
        )
    content = res.content
    if len(content) > MAX_SKILL_TOTAL_BYTES:
        raise DebugPolicyError("Skill Hub zip is too large")
    folder = _safe_folder(skill.folder or slug.rsplit("/", 1)[-1] or "skill")
    return _files_from_zip(content, folder, f"Skill Hub skill {slug}")


async def _materialize_skillspace_skill(
    skill: SelectedSkill,
    resolver: SkillSpaceResolver,
) -> list[GeneratedFile]:
    if not skill.skillSpaceId or not skill.skillId:
        raise DebugPolicyError("SkillSpace skill is missing ids")
    folder = _safe_folder(skill.folder or skill.name or skill.skillId)
    try:
        skill_md = await resolver(
            skill.skillSpaceId,
            skill.skillId,
            skill.version or None,
            skill.skillSpaceRegion or None,
        )
    except TypeError:
        skill_md = await resolver(
            skill.skillSpaceId,
            skill.skillId,
            skill.version or None,
        )
    _validate_skill_md(skill_md, f"SkillSpace skill {skill.skillId}")
    return [GeneratedFile(path=f"skills/{folder}/SKILL.md", content=skill_md)]


def _materialize_local_skill(skill: SelectedSkill) -> list[GeneratedFile]:
    folder = _safe_folder(skill.folder or skill.name)
    files = skill.localFiles
    if not files:
        raise DebugPolicyError(f"Local skill {folder} has no files")
    _enforce_file_limits(files)
    expected_prefix = f"skills/{folder}/"
    out: list[GeneratedFile] = []
    skill_md_content: str | None = None
    for file in files:
        path = _normalize_project_path(file.path)
        if not path.startswith(expected_prefix):
            raise DebugPolicyError(
                f"Local skill file must stay under {expected_prefix}: {file.path}"
            )
        if _SKILL_MD_RE.search(path):
            skill_md_content = file.content
        out.append(GeneratedFile(path=path, content=file.content))
    if skill_md_content is None:
        raise DebugPolicyError(f"Local skill {folder} is missing SKILL.md")
    declared_name = _validate_skill_md(skill_md_content, f"Local skill {folder}")
    if declared_name != folder:
        raise DebugPolicyError(
            f"Local skill folder '{folder}' does not match SKILL.md name '{declared_name}'"
        )
    return out


def _files_from_zip(content: bytes, folder: str, label: str) -> list[GeneratedFile]:
    files: list[GeneratedFile] = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_SKILL_FILES:
            raise DebugPolicyError(f"{label} contains too many files")
        skill_md_content: str | None = None
        for info in infos:
            if info.file_size > MAX_SKILL_FILE_BYTES:
                raise DebugPolicyError(f"{label} file is too large: {info.filename}")
            total += info.file_size
            if total > MAX_SKILL_TOTAL_BYTES:
                raise DebugPolicyError(f"{label} is too large")
            rel = _normalize_relative_path(info.filename)
            target = f"skills/{folder}/{rel}"
            with archive.open(info) as fh:
                text = _decode_skill_file(fh.read(), f"{label} file {info.filename}")
            if _SKILL_MD_RE.search(rel):
                skill_md_content = text
            files.append(GeneratedFile(path=target, content=text))
    if skill_md_content is None:
        raise DebugPolicyError(f"{label} is missing SKILL.md")
    _validate_skill_md(skill_md_content, label)
    return files


def _decode_skill_file(content: bytes, label: str) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise DebugPolicyError(f"{label} must be UTF-8 or GB18030 text")


def _append_skill_files(
    project: GeneratedProject,
    existing: set[str],
    files: list[GeneratedFile],
) -> None:
    _enforce_file_limits(files)
    for file in files:
        path = _normalize_project_path(file.path)
        if path in existing:
            raise DebugPolicyError(
                f"Skill file conflicts with generated project: {path}"
            )
        existing.add(path)
        project.files.append(GeneratedFile(path=path, content=file.content))


def _enforce_file_limits(files: list[GeneratedFile]) -> None:
    if len(files) > MAX_SKILL_FILES:
        raise DebugPolicyError("Skill contains too many files")
    total = 0
    for file in files:
        size = len(file.content.encode("utf-8"))
        if size > MAX_SKILL_FILE_BYTES:
            raise DebugPolicyError(f"Skill file is too large: {file.path}")
        total += size
        if total > MAX_SKILL_TOTAL_BYTES:
            raise DebugPolicyError("Skill files are too large")


def _safe_folder(folder: str) -> str:
    folder = (folder or "").strip()
    if not folder or not _FOLDER_RE.fullmatch(folder) or folder in {".", ".."}:
        raise DebugPolicyError(f"Invalid skill folder: {folder!r}")
    return folder


def _normalize_project_path(path: str) -> str:
    if not isinstance(path, str) or "\x00" in path:
        raise DebugPolicyError("Invalid skill file path")
    normalized = path.replace("\\", "/")
    if normalized.startswith("/"):
        raise DebugPolicyError(f"Illegal skill file path: {path}")
    parts = PurePosixPath(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise DebugPolicyError(f"Illegal skill file path: {path}")
    return "/".join(parts)


def _normalize_relative_path(path: str) -> str:
    normalized = _normalize_project_path(path)
    if normalized.startswith("skills/"):
        raise DebugPolicyError(f"Skill zip must not contain generated path: {path}")
    return normalized


def _validate_skill_md(text: str, where: str) -> str:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise DebugPolicyError(f"{where} SKILL.md must start with frontmatter")
    end_idx = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx < 0:
        raise DebugPolicyError(f"{where} SKILL.md frontmatter is not closed")
    meta: dict[str, str] = {}
    for line in lines[1:end_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]
        meta[key.strip()] = value
    name = (meta.get("name") or "").strip()
    description = (meta.get("description") or "").strip()
    if not name:
        raise DebugPolicyError(f"{where} SKILL.md is missing name")
    if len(name) > 64 or not re.fullmatch(r"[a-z0-9-]+", name):
        raise DebugPolicyError(f"{where} SKILL.md name is invalid")
    if not description:
        raise DebugPolicyError(f"{where} SKILL.md is missing description")
    if len(description) > 1024 or re.search(r"<[^>]+>", description):
        raise DebugPolicyError(f"{where} SKILL.md description is invalid")
    return name
