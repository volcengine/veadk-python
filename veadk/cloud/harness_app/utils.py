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
* :func:`spawn_harness_run_agent` — per-turn clone that also attaches dynamic
  registry-discovered remote A2A tools for the current user message.
"""

import io
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

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

_REGISTRY_CONFIG_ATTR = "_veadk_a2a_registry_config"
_REGISTRY_TOOL_NAMES = {
    "a2a_registry_search_agent_cards",
    "a2a_registry_task_create",
    "a2a_registry_task_poll",
}
_REGISTRY_OVERRIDE_FIELDS = {
    "registry_space_id",
    "registry_endpoint",
    "registry_region",
    "registry_top_k",
}

__all__ = [
    "HarnessConfig",
    "HarnessOverrides",
    "split_csv",
    "agent_name_from_harness",
    "build_skill_toolset",
    "SkillLoadError",
    "ToolLoadError",
    "config_from_env",
    "init_harness_agent",
    "spawn_harness_agent",
    "spawn_harness_run_agent",
    "has_a2a_registry_config",
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


# Skill hub download endpoint. A skill name in a harness is the path after
# `/download/`, e.g. "namespace/owner/skill-name".
SKILL_HUB_DOWNLOAD_URL = os.getenv(
    "SKILL_HUB_DOWNLOAD_URL", "https://skills.volces.com/v1/skills/download"
)
SKILL_HUB_SEARCH_URL = os.getenv(
    "SKILL_HUB_SEARCH_URL", "https://skills.volces.com/v1/skills"
)

# Maps HarnessConfig field names to their environment variables. ``app_name`` is
# populated via its "name" alias. Only variables that are set are passed, so the
# model's own defaults apply to everything else.
_ENV_FIELDS = {
    "model_name": "MODEL_NAME",
    "tools": "TOOLS",
    "skills": "SKILLS",
    "system_prompt": "SYSTEM_PROMPT",
    "description": "DESCRIPTION",
    "runtime": "RUNTIME",
    "structured_tool_calls": "STRUCTURED_TOOL_CALLS",
    "include_tools_every_turn": "INCLUDE_TOOLS_EVERY_TURN",
    "name": "HARNESS_NAME",
    "knowledgebase_type": "KNOWLEDGEBASE_TYPE",
    "longterm_memory_type": "LONG_TERM_MEMORY_TYPE",
    "shortterm_memory_type": "SHORT_TERM_MEMORY_TYPE",
    "max_llm_calls": "MAX_LLM_CALLS",
    "registry_type": "REGISTRY_TYPE",
    "registry_space_id": "REGISTRY_SPACE_ID",
    "registry_endpoint": "REGISTRY_ENDPOINT",
    "registry_version": "REGISTRY_VERSION",
    "registry_service_name": "REGISTRY_SERVICE_NAME",
    "registry_region": "REGISTRY_REGION",
    "registry_top_k": "REGISTRY_TOP_K",
    "registry_timeout_ms": "REGISTRY_TIMEOUT_MS",
    "registry_poll_interval_ms": "REGISTRY_POLL_INTERVAL_MS",
}


def split_csv(value: str) -> list[str]:
    """Split a comma-separated string into trimmed, non-empty names.

    ``"web_search, web_fetch"`` -> ``["web_search", "web_fetch"]``; ``""`` -> ``[]``.
    """
    return [item.strip() for item in value.split(",") if item.strip()]


def agent_name_from_harness(harness_name: str) -> str:
    """Derive a valid ADK agent name from the harness name.

    The agent name becomes the A2A agent card's ``name``, so it should reflect
    the harness rather than a shared constant. ADK requires the agent ``name``
    to be a Python identifier (letters, digits, underscores; not starting with a
    digit) and forbids ``"user"``, while harness names also allow ``-`` and may
    start with a digit. Normalize: map every non-identifier char to ``_`` and
    prefix a digit-leading or empty name with ``_``.

    ``"oauth-test"`` -> ``"oauth_test"``; ``"2048-bot"`` -> ``"_2048_bot"``.
    """
    name = re.sub(r"[^0-9A-Za-z_]", "_", harness_name or "")
    if not name or name[0].isdigit():
        name = f"_{name}"
    return f"{name}_" if name == "user" else name


def _download_and_extract_skill(skill: str, dest_dir: Path) -> Path:
    """Download a skill zip from the skill hub and extract it.

    Args:
        skill: Skill identifier — the hub path after ``/download/``
            (e.g. ``"namespace/owner/skill-name"``).
        dest_dir: Base directory to extract into; the skill is placed in a
            subdirectory named after its declared name in ``SKILL.md``.

    Returns:
        The directory the skill was extracted to. Its name matches the skill's
        declared name in ``SKILL.md`` (required by ``load_skill_from_dir``).
    """
    name, archive = _download_skill_archive(skill)

    # Extract to a staging dir first; the final directory must be named after
    # the skill's declared name (ADK's load_skill_from_dir enforces this).
    staging = dest_dir / f"{name.split('/')[-1]}__staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    staging_root = staging.resolve()
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
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


def _download_skill_archive(skill: str) -> tuple[str, bytes]:
    name = skill.strip("/")
    response = _download_skill_response(name)
    if response.status_code == 200 and _looks_like_zip(response.content):
        return name, response.content

    resolved_name = _resolve_skill_download_name(name)
    if resolved_name and resolved_name != name:
        response = _download_skill_response(resolved_name)
        if response.status_code == 200 and _looks_like_zip(response.content):
            return resolved_name, response.content

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to download skill '{skill}': HTTP {response.status_code}"
        )
    raise RuntimeError(
        f"Failed to download skill '{skill}': response is not a zip archive"
    )


def _download_skill_response(name: str) -> httpx.Response:
    url = f"{SKILL_HUB_DOWNLOAD_URL.rstrip('/')}/{name}"
    logger.info(f"Downloading skill '{name}' from {url}")
    return httpx.get(url, timeout=60, follow_redirects=True)


def _looks_like_zip(content: bytes) -> bool:
    return content.startswith(b"PK\x03\x04") or content.startswith(b"PK\x05\x06")


def _resolve_skill_download_name(name: str) -> str | None:
    if "/" in name:
        return None

    query = urlencode({"query": name, "pageNumber": 1, "pageSize": 10})
    url = f"{SKILL_HUB_SEARCH_URL.rstrip('/')}?{query}"
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        if response.status_code != 200:
            return None
        data = response.json()
    except Exception:
        return None

    for item in _skill_search_items(data):
        slug = _skill_item_text(item, "Slug")
        if slug and _skill_item_matches(name, item):
            logger.info(f"Resolved skill short name '{name}' to '{slug}'")
            return slug.strip("/")
    return None


def _skill_search_items(data: object) -> list[dict[str, object]]:
    if not isinstance(data, dict):
        return []
    items = data.get("Skills") or data.get("Items") or data.get("skills")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _skill_item_matches(name: str, item: dict[str, object]) -> bool:
    normalized = _normalize_skill_token(name)
    tokens = {
        _normalize_skill_token(_skill_item_text(item, "Name")),
        _normalize_skill_token(_skill_item_text(item, "Slug")),
        _normalize_skill_token(_skill_item_text(item, "Slug").rsplit("/", 1)[-1]),
        _normalize_skill_token(_skill_item_text(item, "SourceRepo")),
        _normalize_skill_token(_skill_item_text(item, "SourceRepo").rsplit("/", 1)[-1]),
    }
    return normalized in tokens


def _skill_item_text(item: dict[str, object], key: str) -> str:
    value = item.get(key) or item.get(key.lower())
    return value if isinstance(value, str) else ""


def _normalize_skill_token(value: str) -> str:
    return value.strip().lower().replace("_", "-")


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

    registry_config = None
    if config.registry_type:
        from veadk.a2a.registry_client import AgentKitA2ARegistryConfig
        from veadk.tools.builtin_tools.a2a_registry import (
            build_a2a_registry_tools,
        )

        logger.info(f"Mounting A2A registry tools: type={config.registry_type}")
        registry_config = AgentKitA2ARegistryConfig(
            space_id=config.registry_space_id,
            endpoint=config.registry_endpoint,
            version=config.registry_version,
            service_name=config.registry_service_name,
            region=config.registry_region,
            top_k=config.registry_top_k,
            timeout_ms=config.registry_timeout_ms,
            poll_interval_ms=config.registry_poll_interval_ms,
        )
        tools.extend(build_a2a_registry_tools(registry_config))

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
        name=agent_name_from_harness(config.app_name),
        model_name=config.model_name,
        instruction=config.system_prompt,
        description=config.description,
        tools=tools,
        runtime=config.runtime,
        enable_responses=config.structured_tool_calls,
        enable_responses_cache=not config.include_tools_every_turn,
        knowledgebase=knowledgebase,
        long_term_memory=long_term_memory,
        short_term_memory=short_term_memory,
    )
    if registry_config is not None:
        setattr(agent, _REGISTRY_CONFIG_ATTR, registry_config)
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


def _remove_a2a_registry_tools(agent: Agent) -> None:
    agent.tools = [
        tool for tool in agent.tools if _tool_name(tool) not in _REGISTRY_TOOL_NAMES
    ]


def _apply_registry_overrides(
    agent: Agent,
    base_config,
    overrides: HarnessOverrides,
) -> None:
    set_fields = overrides.model_fields_set
    if not (_REGISTRY_OVERRIDE_FIELDS & set_fields):
        return

    from veadk.a2a.registry_client import AgentKitA2ARegistryConfig
    from veadk.tools.builtin_tools.a2a_registry import build_a2a_registry_tools

    config = base_config or AgentKitA2ARegistryConfig()
    updates: dict[str, Any] = {}
    if "registry_space_id" in set_fields:
        updates["space_id"] = overrides.registry_space_id
    if "registry_endpoint" in set_fields:
        updates["endpoint"] = overrides.registry_endpoint
    if "registry_region" in set_fields:
        updates["region"] = overrides.registry_region
    if "registry_top_k" in set_fields:
        updates["top_k"] = overrides.registry_top_k

    overridden_config = replace(config, **updates)
    _remove_a2a_registry_tools(agent)
    agent.tools.extend(build_a2a_registry_tools(overridden_config))
    setattr(agent, _REGISTRY_CONFIG_ATTR, overridden_config)


def _apply_registry_tip_token(agent: Agent, tip_token: str = "") -> None:
    cleaned_tip_token = (tip_token or "").strip()
    if not cleaned_tip_token:
        return

    from veadk.tools.builtin_tools.a2a_registry import build_a2a_registry_tools

    config = getattr(agent, _REGISTRY_CONFIG_ATTR, None)
    if config is None:
        return

    updated_config = replace(config, upstream_tip_token=cleaned_tip_token)
    _remove_a2a_registry_tools(agent)
    agent.tools.extend(build_a2a_registry_tools(updated_config))
    setattr(agent, _REGISTRY_CONFIG_ATTR, updated_config)


def has_a2a_registry_config(agent: Agent) -> bool:
    """Return whether ``agent`` has an AgentKit A2A registry configured."""

    return getattr(agent, _REGISTRY_CONFIG_ATTR, None) is not None


def _add_dynamic_a2a_agent_tools(agent: Agent, prompt: str) -> None:
    registry_config = getattr(agent, _REGISTRY_CONFIG_ATTR, None)
    if registry_config is None or not prompt or not prompt.strip():
        return

    from veadk.tools.builtin_tools.a2a_registry import build_remote_a2a_agent_tools

    dynamic_tools = build_remote_a2a_agent_tools(prompt, registry_config)
    if not dynamic_tools:
        return

    existing = {name for tool in agent.tools if (name := _tool_name(tool))}
    attached = 0
    for tool in dynamic_tools:
        name = _tool_name(tool)
        if not name or name in existing:
            continue
        agent.tools.append(tool)
        existing.add(name)
        attached += 1
    if attached:
        logger.info(f"Attached {attached} dynamic A2A agent tools for this turn.")


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

    _apply_registry_overrides(
        cloned,
        getattr(base_agent, _REGISTRY_CONFIG_ATTR, None),
        overrides,
    )

    return cloned


def spawn_harness_run_agent(
    base_agent: Agent,
    prompt: str,
    overrides: HarnessOverrides | None = None,
    download_dir: Path | None = None,
    registry_tip_token: str = "",
) -> Agent:
    """Clone a harness agent for one run and attach per-turn dynamic tools."""

    if overrides is not None:
        cloned = spawn_harness_agent(base_agent, overrides, download_dir=download_dir)
    else:
        cloned = base_agent.clone(update={})

    _apply_registry_tip_token(cloned, registry_tip_token)
    _add_dynamic_a2a_agent_tools(cloned, prompt)
    return cloned
