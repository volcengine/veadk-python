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

"""Materialize an agent's skills for explicit Pi skill loading."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from veadk.agent import Agent

logger = get_logger(__name__)

_SKILL_MANIFEST = "SKILL.md"


@dataclass
class PiSkillBundle:
    """Per-turn Pi skill materialization result."""

    root: Path | None = None
    paths: tuple[str, ...] = ()
    count: int = 0
    _tmpdir: tempfile.TemporaryDirectory[str] | None = field(default=None, repr=False)

    def close(self) -> None:
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None


def materialize_skills_for_pi(agent: "Agent") -> PiSkillBundle:
    """Materialize agent skills into isolated directories for ``pi --skill``.

    Pi supports ambient skill discovery, but VeADK keeps runtime behavior
    deterministic by passing only these explicit skill directories to Pi.
    """

    tmpdir = tempfile.TemporaryDirectory(prefix="veadk-piagent-skills-")
    root = Path(tmpdir.name)
    seen: set[str] = set()
    paths: list[str] = []

    for name, writer in _iter_skill_writers(agent):
        if name in seen:
            continue
        skill_dir = _safe_child(str(root), name)
        if skill_dir is None:
            logger.warning(f"piagent: skipping skill with unsafe name {name!r}")
            continue
        try:
            os.makedirs(skill_dir, exist_ok=True)
            writer(skill_dir)
            seen.add(name)
            paths.append(skill_dir)
        except Exception as e:  # noqa: BLE001 - one bad skill must not fail the turn
            logger.warning(f"piagent: failed to materialize skill {name!r}: {e}")
            shutil.rmtree(skill_dir, ignore_errors=True)

    if not paths:
        tmpdir.cleanup()
        return PiSkillBundle()

    logger.info(f"piagent: materialized {len(paths)} skill(s) into {root}")
    return PiSkillBundle(
        root=root,
        paths=tuple(paths),
        count=len(paths),
        _tmpdir=tmpdir,
    )


def _iter_skill_writers(agent: "Agent") -> Iterator[tuple[str, Any]]:
    yield from _iter_adk_skill_writers(agent)
    yield from _iter_legacy_skill_writers(agent)


def _iter_adk_skill_writers(agent: "Agent") -> Iterator[tuple[str, Any]]:
    try:
        from google.adk.tools.skill_toolset import SkillToolset
    except Exception:  # noqa: BLE001 - ADK skills optional / version-dependent
        return

    for tool in getattr(agent, "tools", None) or []:
        if not isinstance(tool, SkillToolset):
            continue
        for name, skill in (getattr(tool, "_skills", None) or {}).items():
            yield str(name), _make_adk_skill_writer(skill)


def _make_adk_skill_writer(skill: Any) -> Any:
    def _write(skill_dir: str) -> None:
        frontmatter = _dump_frontmatter(skill.frontmatter)
        body = getattr(skill, "instructions", "") or ""
        with open(os.path.join(skill_dir, _SKILL_MANIFEST), "w", encoding="utf-8") as f:
            f.write(f"{frontmatter}\n{body}\n" if body else frontmatter)
        _write_resources(skill_dir, getattr(skill, "resources", None))

    return _write


def _dump_frontmatter(frontmatter: Any) -> str:
    data: dict[str, Any] = {}
    if hasattr(frontmatter, "model_dump"):
        data = frontmatter.model_dump(exclude_none=True, by_alias=True)
    data = {k: v for k, v in data.items() if v not in ({}, [], "")}
    try:
        import yaml

        header = yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()
    except Exception:  # noqa: BLE001 - fall back to a minimal valid header
        name = data.get("name", "skill")
        desc = str(data.get("description", "")).replace("\n", " ")
        header = f'name: {name}\ndescription: "{desc}"'
    return f"---\n{header}\n---\n"


def _write_resources(skill_dir: str, resources: Any) -> None:
    if resources is None:
        return
    for attr in ("references", "assets"):
        for rel, content in (getattr(resources, attr, None) or {}).items():
            _write_child(skill_dir, str(rel), content)
    for rel, script in (getattr(resources, "scripts", None) or {}).items():
        _write_child(skill_dir, str(rel), str(script))


def _iter_legacy_skill_writers(agent: "Agent") -> Iterator[tuple[str, Any]]:
    skills_dict = getattr(agent, "skills_dict", None)
    if not skills_dict:
        return

    materialize = None
    try:
        from veadk.skills.materializer import materialize_remote_skill

        materialize = materialize_remote_skill
    except Exception:  # noqa: BLE001 - remote materializer optional
        materialize = None

    for name, skill in skills_dict.items():
        path = getattr(skill, "path", "") or ""
        if os.path.isdir(path):
            yield str(name), _make_dir_link_writer(path)
        elif materialize is not None:
            yield str(name), _make_remote_skill_writer(skill, materialize)
        else:
            logger.warning(
                f"piagent: skill {name!r} is remote but the materializer is "
                "unavailable; skipping"
            )


def _make_dir_link_writer(src_dir: str) -> Any:
    def _write(skill_dir: str) -> None:
        _link_or_copy_tree(src_dir, skill_dir)

    return _write


def _make_remote_skill_writer(skill: Any, materialize: Any) -> Any:
    def _write(skill_dir: str) -> None:
        resolved = str(materialize(skill))
        _link_or_copy_tree(resolved, skill_dir)

    return _write


def _safe_child(base: str, rel: str) -> str | None:
    rel = str(rel).lstrip("/\\")
    if not rel:
        return None
    dest = os.path.abspath(os.path.join(base, rel))
    base_abs = os.path.abspath(base)
    if dest == base_abs or dest.startswith(base_abs + os.sep):
        return dest
    return None


def _write_child(base: str, rel: str, content: Any) -> None:
    dest = _safe_child(base, rel)
    if dest is None:
        logger.warning(f"piagent: skipping skill resource with unsafe path {rel!r}")
        return
    os.makedirs(os.path.dirname(dest) or base, exist_ok=True)
    if isinstance(content, (bytes, bytearray)):
        with open(dest, "wb") as f:
            f.write(content)
    else:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(str(content))


def _link_or_copy_tree(src: str, dest: str) -> None:
    src = os.path.abspath(src)
    try:
        if os.path.islink(dest) or os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True) if not os.path.islink(
                dest
            ) else os.unlink(dest)
        os.symlink(src, dest, target_is_directory=True)
    except OSError:
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, dirs_exist_ok=True)
