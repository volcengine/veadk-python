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
import yaml

from veadk.cli.generated_agent_codegen import (
    AgentDraft,
    GeneratedFile,
    GeneratedProject,
    SelectedSkill,
)
from veadk.cli.generated_agent_security import DebugPolicyError


SkillSpaceResolverResult = str | list[GeneratedFile]
SkillSpaceResolver = Callable[..., Awaitable[SkillSpaceResolverResult]]

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
        original_folder = skill.folder
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
        if (
            skill.source != "local"
            and original_folder
            and original_folder != skill.folder
        ):
            _replace_project_skill_folder(project, original_folder, skill.folder)
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
    folder = _safe_folder_or_default(
        skill.folder or slug.rsplit("/", 1)[-1] or "skill"
    )
    files = _files_from_zip(content, folder, f"Skill Hub skill {slug}")
    skill.folder = _folder_from_generated_files(files) or folder
    return files


async def _materialize_skillspace_skill(
    skill: SelectedSkill,
    resolver: SkillSpaceResolver,
) -> list[GeneratedFile]:
    if not skill.skillSpaceId or not skill.skillId:
        raise DebugPolicyError("SkillSpace skill is missing ids")
    folder = _safe_folder_or_default(skill.folder or skill.name or skill.skillId)
    try:
        resolved = await resolver(
            skill.skillSpaceId,
            skill.skillId,
            skill.version or None,
            skill.skillSpaceRegion or None,
            skill_space_name=skill.skillSpaceName or None,
            skill_name=skill.name or None,
        )
    except TypeError:
        resolved = await resolver(
            skill.skillSpaceId,
            skill.skillId,
            skill.version or None,
        )
    if isinstance(resolved, str):
        skill_md = _normalize_skill_md_frontmatter(
            resolved, f"SkillSpace skill {skill.skillId}"
        )
        folder = _skill_md_folder_name(skill_md) or folder
        skill.folder = folder
        return [GeneratedFile(path=f"skills/{folder}/SKILL.md", content=skill_md)]

    files = _normalize_skillspace_files(
        resolved,
        folder,
        f"SkillSpace skill {skill.skillId}",
    )
    skill.folder = _folder_from_generated_files(files) or folder
    return files


def _normalize_skillspace_files(
    files: list[GeneratedFile],
    folder: str,
    label: str,
) -> list[GeneratedFile]:
    if not files:
        raise DebugPolicyError(f"{label} has no files")
    skill_md_content: str | None = None
    current_folder: str | None = None
    for file in files:
        path = _normalize_project_path(file.path)
        parts = PurePosixPath(path).parts
        if len(parts) < 3 or parts[0] != "skills":
            raise DebugPolicyError(f"{label} file must be under skills/: {file.path}")
        if current_folder is None:
            current_folder = parts[1]
        if _SKILL_MD_RE.search(path):
            skill_md_content = file.content
    if skill_md_content is None:
        raise DebugPolicyError(f"{label} is missing SKILL.md")
    skill_md = _normalize_skill_md_frontmatter(
        skill_md_content,
        label,
    )
    target_folder = _skill_md_folder_name(skill_md) or current_folder or folder
    out: list[GeneratedFile] = []
    for file in files:
        path = _normalize_project_path(file.path)
        parts = PurePosixPath(path).parts
        if len(parts) >= 3 and parts[0] == "skills":
            path = "/".join(("skills", target_folder, *parts[2:]))
        content = skill_md if _SKILL_MD_RE.search(path) else file.content
        out.append(GeneratedFile(path=path, content=content))
    return out


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
    return out


def _files_from_zip(content: bytes, folder: str, label: str) -> list[GeneratedFile]:
    extracted: list[tuple[str, str]] = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_SKILL_FILES:
            raise DebugPolicyError(f"{label} contains too many files")
        skill_md_candidates: list[tuple[str, str]] = []
        for info in infos:
            if info.file_size > MAX_SKILL_FILE_BYTES:
                raise DebugPolicyError(f"{label} file is too large: {info.filename}")
            total += info.file_size
            if total > MAX_SKILL_TOTAL_BYTES:
                raise DebugPolicyError(f"{label} is too large")
            rel = _normalize_relative_path(info.filename)
            with archive.open(info) as fh:
                text = _decode_skill_file(fh.read(), f"{label} file {info.filename}")
            if _SKILL_MD_RE.search(rel):
                skill_md_candidates.append((rel, text))
            extracted.append((rel, text))
    if not skill_md_candidates:
        raise DebugPolicyError(f"{label} is missing SKILL.md")
    skill_md_rel, skill_md_content = sorted(
        skill_md_candidates,
        key=lambda item: (len(PurePosixPath(item[0]).parts), item[0]),
    )[0]
    skill_md_content = _normalize_skill_md_frontmatter(skill_md_content, label)
    extracted = [
        (rel, skill_md_content if rel == skill_md_rel else text)
        for rel, text in extracted
    ]
    extracted = _strip_skill_zip_prefix(extracted, skill_md_rel)
    folder = _skill_md_folder_name(skill_md_content) or folder
    return [
        GeneratedFile(path=f"skills/{folder}/{rel}", content=text)
        for rel, text in extracted
    ]


def _strip_skill_zip_prefix(
    files: list[tuple[str, str]], skill_md_rel: str
) -> list[tuple[str, str]]:
    base_parts = PurePosixPath(skill_md_rel).parent.parts
    if not base_parts:
        return files
    out: list[tuple[str, str]] = []
    for rel, text in files:
        parts = PurePosixPath(rel).parts
        if parts[: len(base_parts)] == base_parts:
            stripped = "/".join(parts[len(base_parts) :])
            if stripped:
                out.append((stripped, text))
        else:
            out.append((rel, text))
    return out


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


def _safe_folder_or_default(folder: str, default: str = "skill") -> str:
    folder = (folder or "").strip()
    if _FOLDER_RE.fullmatch(folder) and folder not in {".", ".."}:
        return folder
    sanitized = re.sub(r"[^A-Za-z0-9_-]+", "-", folder).strip("-")
    if sanitized and sanitized not in {".", ".."}:
        return sanitized[:64]
    return default


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
    return _normalize_project_path(path)


def _skill_md_folder_name(text: str) -> str | None:
    try:
        meta, _ = _parse_skill_md(text, "SKILL.md")
    except DebugPolicyError:
        return None
    name = str(meta.get("name") or "").strip()
    if _FOLDER_RE.fullmatch(name) and name not in {".", ".."}:
        return name
    return None


def _folder_from_generated_files(files: list[GeneratedFile]) -> str | None:
    for file in files:
        parts = PurePosixPath(file.path).parts
        if len(parts) >= 3 and parts[0] == "skills":
            return parts[1]
    return None


def _py_string(value: str) -> str:
    escaped = (
        (value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _replace_project_skill_folder(
    project: GeneratedProject, old_folder: str, new_folder: str
) -> None:
    old_loader = f'/ "skills" / {_py_string(old_folder)}'
    new_loader = f'/ "skills" / {_py_string(new_folder)}'
    old_draft_folder = f"'folder': '{old_folder}'"
    new_draft_folder = f"'folder': '{new_folder}'"
    for file in project.files:
        if not file.path.endswith("/agent.py"):
            continue
        file.content = file.content.replace(old_loader, new_loader).replace(
            old_draft_folder, new_draft_folder
        )


def _parse_skill_md(text: str, where: str) -> tuple[dict[str, object], str]:
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
    try:
        parsed = yaml.safe_load("\n".join(lines[1:end_idx])) or {}
    except yaml.YAMLError as e:
        parsed = _parse_legacy_frontmatter_lines(lines[1:end_idx])
        if not parsed:
            raise DebugPolicyError(
                f"{where} SKILL.md frontmatter is invalid YAML: {e}"
            ) from e
    if not isinstance(parsed, dict):
        raise DebugPolicyError(f"{where} SKILL.md frontmatter must be a mapping")
    body = "\n".join(lines[end_idx + 1 :])
    return parsed, body


def _parse_legacy_frontmatter_lines(lines: list[str]) -> dict[str, object]:
    meta: dict[str, object] = {}
    for line in lines:
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
    return meta


def _normalize_skill_md_frontmatter(text: str, where: str) -> str:
    try:
        meta, body = _parse_skill_md(text, where)
    except DebugPolicyError:
        return text
    if "metadata" in meta and not isinstance(meta["metadata"], dict):
        meta["metadata"] = {}
    header = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{header}\n---\n{body}"
