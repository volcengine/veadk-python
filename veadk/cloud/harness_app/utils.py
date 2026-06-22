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

"""Helpers for assembling the harness agent.

Two factory functions cover the two creation paths:

* :func:`init_harness_agent` — first-time startup; reads the environment into a
  :class:`HarnessConfig` and builds the long-lived agent, downloading its skills
  from the skill hub and mounting them as an ADK skill toolset.
* :func:`spawn_harness_agent` — temporary, one-off creation that clones the base
  agent and applies a per-request override (incremental tools/skills on top).
"""

import io
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import frontmatter
import httpx
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from veadk import Agent
from veadk.cloud.harness_app.types import HarnessConfig, HarnessOverrides
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools import get_builtin_tool, list_builtin_tools
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    "HarnessConfig",
    "HarnessOverrides",
    "split_csv",
    "build_skill_toolset",
    "SkillLoadError",
    "ToolLoadError",
    "config_from_env",
    "init_harness_agent",
    "spawn_harness_agent",
]


class ToolLoadError(RuntimeError):
    """A requested built-in tool is not supported.

    Raised instead of failing with an opaque ``KeyError`` so the unsupported
    tool name surfaces — at server startup for a base tool, or in the invoke
    response for a per-call override.
    """


def _load_builtin_tool(name: str) -> Any:
    """Resolve a built-in tool by name, raising :class:`ToolLoadError` if unknown."""
    try:
        return get_builtin_tool(name)
    except KeyError as e:
        raise ToolLoadError(
            f"Tool '{name}' is not a supported built-in tool. "
            f"Available: {', '.join(list_builtin_tools())}"
        ) from e


# Skill hub endpoints. A harness lists a skill by its human *name* (e.g.
# "web-scraper"); the hub downloads by *slug* (e.g.
# "clawhub/yinanping-cpu/web-scraper"). We resolve name -> slug via the search
# API, then download by slug. Both are env-overridable.
SKILL_HUB_DOWNLOAD_URL = os.getenv(
    "SKILL_HUB_DOWNLOAD_URL", "https://skills.volces.com/v1/skills/download"
)
SKILL_HUB_SEARCH_URL = os.getenv(
    "SKILL_HUB_SEARCH_URL", "https://skills.volces.com/v1/skills"
)
# Top-N search results scanned for an exact name match. The top hit is not always
# the exact one (e.g. "web-scraper" ranks below "smart-web-scraper"), so we scan
# the whole (small) page rather than trusting the first result.
_SKILL_SEARCH_PAGE_SIZE = 3

# Maps HarnessConfig field names to their environment variables. ``app_name`` is
# populated via its "name" alias. Only variables that are set are passed, so the
# model's own defaults apply to everything else.
_ENV_FIELDS = {
    "model_name": "MODEL_NAME",
    "tools": "TOOLS",
    "skills": "SKILLS",
    "system_prompt": "SYSTEM_PROMPT",
    "runtime": "RUNTIME",
    "name": "HARNESS_NAME",
    "knowledgebase_type": "KNOWLEDGEBASE_TYPE",
    "longterm_memory_type": "LONG_TERM_MEMORY_TYPE",
    "shortterm_memory_type": "SHORT_TERM_MEMORY_TYPE",
    "max_llm_calls": "MAX_LLM_CALLS",
}


def split_csv(value: str) -> list[str]:
    """Split a comma-separated string into trimmed, non-empty names.

    ``"web_search, web_fetch"`` -> ``["web_search", "web_fetch"]``; ``""`` -> ``[]``.
    """
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_skill_slug(skill: str) -> str:
    """Resolve a skill *name* to its hub *slug* via the search API.

    A harness lists skills by name (e.g. ``"web-scraper"``) but the hub downloads
    by slug (e.g. ``"clawhub/yinanping-cpu/web-scraper"``). A value already given
    as a slug (contains ``"/"``) is used as-is. Otherwise the hub is searched and
    the result whose ``Name`` matches exactly is taken — the top hit is not always
    the exact one, so all results on the page are scanned.

    Raises:
        RuntimeError: the search failed, or no result's ``Name`` matched exactly.
    """
    name = skill.strip("/")
    if "/" in name:
        return name  # already a slug (e.g. "clawhub/org/skill")

    response = httpx.get(
        SKILL_HUB_SEARCH_URL,
        params={"query": name, "pageNumber": 1, "pageSize": _SKILL_SEARCH_PAGE_SIZE},
        timeout=60,
        follow_redirects=True,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Skill search for '{skill}' failed: HTTP {response.status_code}"
        )
    results = response.json().get("Skills") or []
    for entry in results:
        if entry.get("Name") == name and entry.get("Slug"):
            return str(entry["Slug"])
    seen = ", ".join(repr(e.get("Name")) for e in results) or "no results"
    raise RuntimeError(
        f"Skill '{skill}' not found in the skill hub (search returned: {seen}). "
        f"Check the skill name, or pass its full slug (e.g. 'clawhub/<org>/<name>')."
    )


def _download_and_extract_skill(skill: str, dest_dir: Path) -> Path:
    """Resolve a skill name to its hub slug, download the zip, and extract it.

    Args:
        skill: Skill name (e.g. ``"web-scraper"``) or full hub slug (e.g.
            ``"clawhub/lgwventrue/system-file-handler"``).
        dest_dir: Base directory to extract into; the skill is placed in a
            subdirectory named after its declared name in ``SKILL.md``.

    Returns:
        The directory the skill was extracted to. Its name matches the skill's
        declared name in ``SKILL.md`` (required by ``load_skill_from_dir``).
    """
    slug = _resolve_skill_slug(skill)
    url = f"{SKILL_HUB_DOWNLOAD_URL.rstrip('/')}/{slug}"
    logger.info(f"Downloading skill '{skill}' (slug='{slug}') from {url}")

    response = httpx.get(url, timeout=60, follow_redirects=True)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to download skill '{skill}': HTTP {response.status_code}"
        )
    # The hub may answer 200 with a JSON error body instead of a zip; surface that
    # clearly rather than letting zipfile fail with "File is not a zip file".
    if response.content[:2] != b"PK":
        ct = response.headers.get("content-type", "")
        raise RuntimeError(
            f"Skill '{skill}' (slug='{slug}') download did not return a zip "
            f"(content-type={ct!r}, {len(response.content)} bytes)"
        )

    # Extract to a staging dir first; the final directory must be named after
    # the skill's declared name (ADK's load_skill_from_dir enforces this).
    staging = dest_dir / f"{slug.split('/')[-1]}__staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    staging_root = staging.resolve()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        for member in zf.namelist():
            # Guard against path traversal (zip-slip).
            if not (staging / member).resolve().is_relative_to(staging_root):
                raise RuntimeError(f"Unsafe path in skill '{skill}' zip: {member}")
        zf.extractall(staging)

    skill_md = staging / "SKILL.md"
    if not skill_md.exists():
        skill_md = staging / "skill.md"
    if not skill_md.exists():
        raise RuntimeError(f"Skill '{skill}' has no SKILL.md")
    declared_name = frontmatter.loads(
        skill_md.read_text(encoding="utf-8")
    ).metadata.get("name")
    if not declared_name:
        raise RuntimeError(f"Skill '{skill}' SKILL.md has no 'name' in frontmatter")

    skill_dir = dest_dir / str(declared_name)
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
    staging.rename(skill_dir)

    logger.info(f"Extracted skill '{skill}' (name='{declared_name}') to {skill_dir}")
    return skill_dir


class SkillLoadError(RuntimeError):
    """A skill failed to download or load (e.g. a malformed ``SKILL.md``).

    Raised instead of silently skipping so the failure surfaces — at the server
    startup for a base skill, or in the invoke response for a per-call override.
    """


def build_skill_toolset(
    skills: list[str], download_dir: Path | None = None
) -> SkillToolset | None:
    """Download each skill from the hub and load them as a single ADK toolset.

    Skills are downloaded into ``download_dir`` (a fresh temp dir when omitted)
    and loaded via ``load_skill_from_dir``. The directory is **not** cleaned up
    here: a skill's scripts/assets are read from disk while the agent runs, so
    the caller owns the directory's lifetime (the base agent keeps its skills for
    the server's lifetime; a per-invoke override cleans up after the run).

    Fast-fail: if *any* skill fails to download or load (e.g. a ``SKILL.md`` whose
    description exceeds ADK's limit), a :class:`SkillLoadError` is raised naming
    the skill and the reason — the whole call is aborted rather than running with
    a partial skill set.

    Returns:
        A :class:`SkillToolset` of the loaded skills, or ``None`` for no skills.
    """
    if not skills:
        return None
    if download_dir is None:
        download_dir = Path(tempfile.mkdtemp(prefix="harness_skills_"))
    loaded_skills = []
    for skill in skills:
        try:
            loaded_skills.append(
                load_skill_from_dir(_download_and_extract_skill(skill, download_dir))
            )
        except Exception as e:
            raise SkillLoadError(f"Skill '{skill}' failed to load: {e}") from e
    return SkillToolset(skills=loaded_skills)


def config_from_env() -> HarnessConfig:
    """Parse the environment into a :class:`HarnessConfig` (validated by pydantic)."""
    kwargs: dict[str, Any] = {
        field: os.environ[env]
        for field, env in _ENV_FIELDS.items()
        if env in os.environ
    }
    return HarnessConfig(**kwargs)


def _assemble_agent(config: HarnessConfig) -> tuple[Agent, ShortTermMemory]:
    """Build an agent and its short-term memory from a :class:`HarnessConfig`.

    Skills are downloaded from the skill hub and mounted as an ADK
    :class:`SkillToolset` tool. An empty backend string disables the knowledge
    base / long-term memory. Backend values are validated by each component's
    pydantic model (fast-fail on an unknown value).
    """
    tools = [_load_builtin_tool(name) for name in split_csv(config.tools)]

    skills = split_csv(config.skills)
    if skills:
        logger.info(f"Loading skills {skills} for harness.")
        skill_toolset = build_skill_toolset(skills)
        if skill_toolset is not None:
            tools.append(skill_toolset)

    knowledgebase = None
    if config.knowledgebase_type:
        logger.info(
            f"Initializing knowledge base: backend={config.knowledgebase_type} "
            f"index={config.app_name}"
        )
        knowledgebase = KnowledgeBase(
            backend=config.knowledgebase_type,  # type: ignore[arg-type]
            app_name=config.app_name,
        )

    long_term_memory = None
    if config.longterm_memory_type:
        logger.info(
            f"Initializing long-term memory: backend={config.longterm_memory_type} "
            f"index={config.app_name}"
        )
        long_term_memory = LongTermMemory(
            backend=config.longterm_memory_type,  # type: ignore[arg-type]
            app_name=config.app_name,
        )

    logger.info(
        f"Initializing short-term memory: backend={config.shortterm_memory_type}"
    )
    short_term_memory = ShortTermMemory(
        backend=config.shortterm_memory_type  # type: ignore[arg-type]
    )

    agent = Agent(
        name="harness_agent",
        model_name=config.model_name,
        instruction=config.system_prompt,
        tools=tools,
        runtime=config.runtime,
        knowledgebase=knowledgebase,
        long_term_memory=long_term_memory,
        short_term_memory=short_term_memory,
    )
    return agent, short_term_memory


def init_harness_agent() -> tuple[Agent, ShortTermMemory]:
    """Create the long-lived agent on first startup by reading the environment.

    Returns:
        A ``(agent, short_term_memory)`` tuple. The short-term memory is returned
        separately so the server can share the same instance with its ``Runner``.
    """
    return _assemble_agent(config_from_env())


def _tool_name(tool: Any) -> str | None:
    """The dispatch name of a tool (function ``__name__`` or tool/toolset ``name``)."""
    return getattr(tool, "__name__", None) or getattr(tool, "name", None)


def _add_incremental_tools(agent: Agent, tool_names: list[str]) -> None:
    """Append the requested built-in tools, skipping ones already on the agent."""
    existing = {name for tool in agent.tools if (name := _tool_name(tool))}
    for name in tool_names:
        if name in existing:
            logger.info(f"Tool '{name}' already on the agent; skipping.")
            continue
        agent.tools.append(_load_builtin_tool(name))
        existing.add(name)


def _add_incremental_skills(
    agent: Agent, skill_ids: list[str], download_dir: Path | None = None
) -> None:
    """Mount the requested skills, skipping ones whose name is already loaded.

    Skills already present are dropped (deduped by skill name). Any genuinely new
    skills are merged into the agent's existing :class:`SkillToolset` so the agent
    keeps a single toolset (two would expose duplicate ``list_skills``/``load_skill``
    tools); if the agent has none yet, a new toolset is mounted. ``download_dir``
    is where the skills are downloaded (cleaned up by the caller after the run).
    """
    toolset = build_skill_toolset(skill_ids, download_dir=download_dir)
    if toolset is None:
        return
    new_skills = toolset._list_skills()

    existing_toolset = next(
        (tool for tool in agent.tools if isinstance(tool, SkillToolset)), None
    )
    if existing_toolset is None:
        agent.tools.append(toolset)
        return

    existing_skills = existing_toolset._list_skills()
    existing_names = {skill.name for skill in existing_skills}
    new_skills = [skill for skill in new_skills if skill.name not in existing_names]
    if not new_skills:
        logger.info("All requested skills already loaded; skipping.")
        return

    agent.tools.remove(existing_toolset)
    agent.tools.append(SkillToolset(skills=existing_skills + new_skills))


def spawn_harness_agent(
    base_agent: Agent, overrides: HarnessOverrides, download_dir: Path | None = None
) -> Agent:
    """Clone the base agent for a one-off invocation and apply per-request overrides.

    Uses ADK's :meth:`~google.adk.agents.base_agent.BaseAgent.clone`, so the clone
    inherits the base agent's knowledge base and memory — these are never
    overridable. Only the fields the request actually set are applied: ``model_name``,
    ``system_prompt`` and ``runtime`` replace the base value, while ``tools`` and
    ``skills`` are mounted *incrementally* — anything already on the agent (same
    tool name / skill name) is skipped, so only the delta is added.

    ``download_dir`` is where any incremental skills are downloaded; the caller
    owns it and should remove it once the invocation finishes.
    """
    set_fields = overrides.model_fields_set

    update: dict[str, Any] = {}
    if "system_prompt" in set_fields:
        update["instruction"] = overrides.system_prompt
    if "runtime" in set_fields:
        update["runtime"] = overrides.runtime
    cloned = base_agent.clone(update=update)

    if "model_name" in set_fields:
        cloned.update_model(overrides.model_name)

    if "tools" in set_fields:
        _add_incremental_tools(cloned, split_csv(overrides.tools))

    if "skills" in set_fields:
        _add_incremental_skills(cloned, split_csv(overrides.skills), download_dir)

    return cloned
