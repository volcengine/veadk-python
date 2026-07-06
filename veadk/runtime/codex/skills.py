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

"""Materialize an agent's skills into Codex's on-disk skill directory.

Codex discovers skills by scanning ``$CODEX_HOME/skills/<name>/SKILL.md`` (the
"user" skill scope). The codex runtime already generates an isolated
``CODEX_HOME`` (under the system temp dir, i.e. ``/tmp`` on the cloud runtime,
which is the only writable location there), so we simply drop each skill into
its ``skills/`` subdirectory and let Codex's native skill system handle
discovery, injection and progressive loading. Because this is purely prompt- and
file-level, it is independent of the model backend and needs no config flag.

Two skill sources are bridged, both best-effort (a skill that fails to
materialize is logged and skipped, never aborting the turn):

- **ADK-native skills** attached via ``google.adk.tools.skill_toolset.SkillToolset``
  in ``agent.tools``. Each is a fully parsed ``google.adk.skills.models.Skill``
  (frontmatter + instructions + resources), reconstructed back into a
  ``SKILL.md`` plus its resource files.
- **Legacy VeADK skills** resolved onto ``agent.skills_dict`` (local directories
  or remote skill-space / SkillHub skills). Each carries a ``path``: a local
  skill directory is used as-is; a remote skill is downloaded on demand via
  :func:`veadk.skills.materializer.materialize_remote_skill` (which caches under
  the temp dir). The resulting directory tree is linked into ``skills/``.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, Any, Iterator

from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from veadk.agent import Agent

logger = get_logger(__name__)

_SKILLS_SUBDIR = "skills"
_SKILL_MANIFEST = "SKILL.md"


def sync_skills_to_codex_home(agent: "Agent", codex_home: str) -> int:
    """Materialize the agent's skills into ``<codex_home>/skills/``.

    The skills directory is rebuilt from scratch on every call so it always
    reflects the agent's current skills (the ``CODEX_HOME`` itself is cached and
    reused across runs). Returns the number of skills written.
    """
    root = os.path.join(codex_home, _SKILLS_SUBDIR)
    # Rebuild: clear only our managed subdir, never the rest of CODEX_HOME.
    shutil.rmtree(root, ignore_errors=True)

    seen: set[str] = set()
    written = 0
    for name, writer in _iter_skill_writers(agent):
        if name in seen:
            continue
        skill_dir = _safe_child(root, name)
        if skill_dir is None:
            logger.warning(f"codex: skipping skill with unsafe name {name!r}")
            continue
        try:
            os.makedirs(skill_dir, exist_ok=True)
            writer(skill_dir)
            seen.add(name)
            written += 1
        except Exception as e:  # noqa: BLE001 - one bad skill must not fail the turn
            logger.warning(f"codex: failed to materialize skill {name!r}: {e}")
            shutil.rmtree(skill_dir, ignore_errors=True)

    if written:
        logger.info(f"codex: materialized {written} skill(s) into {root}")
    return written


def _iter_skill_writers(agent: "Agent") -> Iterator[tuple[str, Any]]:
    """Yield ``(name, writer)`` pairs for every discoverable skill.

    ``writer`` is a callable ``(skill_dir) -> None`` that populates the target
    directory. ADK-native skills take precedence over legacy ones on a name
    clash (they are yielded first).
    """
    yield from _iter_adk_skill_writers(agent)
    yield from _iter_legacy_skill_writers(agent)


# --- ADK-native skills (google.adk SkillToolset) ---------------------------------


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
    """Serialize an ADK ``Frontmatter`` back into a ``SKILL.md`` YAML header."""
    data: dict[str, Any] = {}
    if hasattr(frontmatter, "model_dump"):
        data = frontmatter.model_dump(exclude_none=True, by_alias=True)
    # Drop empty containers to keep the header clean.
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
    """Write an ADK skill's L3 resources (references / assets / scripts) to disk."""
    if resources is None:
        return
    for attr in ("references", "assets"):
        for rel, content in (getattr(resources, attr, None) or {}).items():
            _write_child(skill_dir, str(rel), content)
    for rel, script in (getattr(resources, "scripts", None) or {}).items():
        _write_child(skill_dir, str(rel), str(script))


# --- Legacy VeADK skills (agent.skills_dict) -------------------------------------


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
                f"codex: skill {name!r} is remote but the materializer is "
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


# --- filesystem helpers ----------------------------------------------------------


def _safe_child(base: str, rel: str) -> str | None:
    """Join ``rel`` under ``base``, returning ``None`` on path traversal."""
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
        logger.warning(f"codex: skipping skill resource with unsafe path {rel!r}")
        return
    os.makedirs(os.path.dirname(dest) or base, exist_ok=True)
    if isinstance(content, (bytes, bytearray)):
        with open(dest, "wb") as f:
            f.write(content)
    else:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(str(content))


def _link_or_copy_tree(src: str, dest: str) -> None:
    """Mirror ``src`` into ``dest``: symlink when possible, else copy.

    ``dest`` was created empty by the caller; replace it with a symlink to the
    already-materialized source (zero-copy, keeps bundled scripts/resources), or
    fall back to a recursive copy if symlinking is not possible.
    """
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
