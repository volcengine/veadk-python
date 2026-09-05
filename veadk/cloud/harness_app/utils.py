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
  agent and applies a per-request override (configured tools/skills replace the
  base harness selection).
* :func:`spawn_harness_run_agent` — per-turn clone that also attaches dynamic
  registry-discovered remote A2A tools for the current user message.
"""

import inspect
import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import frontmatter
import httpx
from google.adk.code_executors import UnsafeLocalCodeExecutor
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from veadk import Agent
from veadk.cloud.harness_app.types import (
    HarnessBuiltinTool,
    HarnessConfig,
    HarnessMcpServer,
    HarnessOverrides,
    HarnessRegistryOverride,
    HarnessResourceOverride,
    HarnessSelectedSkill,
)
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.skills.materializer import materialize_remote_skill
from veadk.skills.utils import _load_skills_from_space_id
from veadk.tools import get_builtin_tool, list_builtin_tools
from veadk.tools.builtin_tools.load_knowledgebase import LoadKnowledgebaseTool
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
_SAMPLING_OVERRIDE_FIELDS = {
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "penalty",
}
_KNOWLEDGEBASE_TOOL_NAMES = {"load_knowledgebase", "load_kb_queries"}
_LONGTERM_MEMORY_TOOL_NAMES = {"load_memory"}
_SKILL_CENTER_SPACE_PREFIX = "space:"

__all__ = [
    "HarnessConfig",
    "HarnessOverrides",
    "HarnessResourceResolver",
    "ResourceResolutionError",
    "SkillLoadError",
    "ToolLoadError",
    "agent_name_from_harness",
    "build_skill_toolset",
    "config_from_env",
    "harness_overrides_from_env",
    "has_a2a_registry_config",
    "init_harness_agent",
    "merge_harness_overrides",
    "normalize_harness_overrides",
    "set_harness_mcp_router_resolver",
    "set_harness_resource_resolver",
    "spawn_harness_agent",
    "spawn_harness_run_agent",
    "split_csv",
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


class ResourceResolutionError(RuntimeError):
    """A control-plane resource id could not be resolved into runtime config."""


HarnessResourceResolver = Callable[
    [str, HarnessResourceOverride],
    HarnessResourceOverride | Mapping[str, Any] | None,
]
McpRouterResolver = Callable[[str, dict[str, Any]], Mapping[str, Any] | None]

_resource_resolver: HarnessResourceResolver | None = None
_mcp_router_resolver: McpRouterResolver | None = None


def set_harness_resource_resolver(
    resolver: HarnessResourceResolver | None,
) -> None:
    """Register a resolver for AgentKit resource ids.

    The resolver receives a resource kind (``"knowledgebase"`` or
    ``"longterm_memory"``) and the request/env resource override. It may return
    another :class:`HarnessResourceOverride` or a mapping with ``type``, ``id``
    and ``config`` keys. Flat mappings are treated as ``config`` for convenience.
    Passing ``None`` clears the resolver and keeps the built-in id-as-index
    fallback.
    """
    global _resource_resolver
    _resource_resolver = resolver


def set_harness_mcp_router_resolver(resolver: McpRouterResolver | None) -> None:
    """Register a resolver for AgentKit MCP toolset ids."""

    global _mcp_router_resolver
    _mcp_router_resolver = resolver


def _ensure_default_resource_resolver() -> None:
    global _resource_resolver
    if _resource_resolver is not None:
        return
    try:
        from veadk.cloud.harness_app.agentkit_resources import (
            default_agentkit_resource_resolver,
        )
    except ImportError as e:
        logger.warning("AgentKit resource resolver is unavailable: %s", e)
        return
    _resource_resolver = default_agentkit_resource_resolver()


def _ensure_default_mcp_router_resolver() -> None:
    global _mcp_router_resolver
    if _mcp_router_resolver is not None:
        return
    try:
        from veadk.cloud.harness_app.agentkit_resources import (
            default_agentkit_mcp_router_resolver,
        )
    except ImportError as e:
        logger.warning("AgentKit MCP router resolver is unavailable: %s", e)
        return
    _mcp_router_resolver = default_agentkit_mcp_router_resolver()


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
    "model_name": ("MODEL_AGENT_NAME", "MODEL_NAME"),
    "tools": ("TOOLS",),
    "mcp_router_id": ("MCP_ROUTER_ID", "MCP_TOOLSET_ID"),
    "skills": ("SKILLS",),
    "system_prompt": ("SYSTEM_PROMPT",),
    "description": ("DESCRIPTION",),
    "runtime": ("RUNTIME",),
    "temperature": ("MODEL_AGENT_TEMPERATURE",),
    "top_p": ("MODEL_AGENT_TOP_P",),
    "structured_tool_calls": ("STRUCTURED_TOOL_CALLS",),
    "include_tools_every_turn": ("INCLUDE_TOOLS_EVERY_TURN",),
    "name": ("HARNESS_NAME",),
    "knowledgebase_type": ("KNOWLEDGEBASE_TYPE",),
    "longterm_memory_type": ("LONG_TERM_MEMORY_TYPE",),
    "shortterm_memory_type": ("SHORT_TERM_MEMORY_TYPE",),
    "max_llm_calls": ("MAX_LLM_CALLS",),
    "registry_type": ("REGISTRY_TYPE",),
    "registry_space_id": ("REGISTRY_SPACE_ID",),
    "registry_endpoint": ("REGISTRY_ENDPOINT",),
    "registry_version": ("REGISTRY_VERSION",),
    "registry_service_name": ("REGISTRY_SERVICE_NAME",),
    "registry_region": ("REGISTRY_REGION",),
    "registry_top_k": ("REGISTRY_TOP_K",),
    "registry_timeout_ms": ("REGISTRY_TIMEOUT_MS",),
    "registry_poll_interval_ms": ("REGISTRY_POLL_INTERVAL_MS",),
}
_HARNESS_BUILTIN_TOOL_ID_ATTR = "_veadk_harness_builtin_tool_id"
_HARNESS_MCP_SERVER_ATTR = "_veadk_harness_mcp_server"
_RUN_CODE_TOOL_ENVS = {
    "run_code": "AGENTKIT_TOOL_ID_SCRIPT",
    "coding": "AGENTKIT_TOOL_ID_OPENCODE",
}
_RESOURCE_DIRECT_FIELDS = {
    "name",
    "description",
    "top_k",
    "app_name",
    "index",
    "enable_profile",
    "query_with_user_profile",
    "user_id",
}


def split_csv(value: str) -> list[str]:
    """Split a comma-separated string into trimmed, non-empty names.

    ``"web_search, web_fetch"`` -> ``["web_search", "web_fetch"]``; ``""`` -> ``[]``.
    """
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_value(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None:
            return value
    return None


def _json_env(name: str, key: str) -> Any:
    raw = os.environ.get(name)
    if not raw or not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {name}: {e}") from e
    if isinstance(value, dict):
        return value.get(key)
    return value


def _json_object_env(name: str) -> dict[str, Any]:
    raw = os.environ.get(name)
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {name}: {e}") from e
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a JSON object.")
    return value


def _builtin_tool_from_name(name: str) -> HarnessBuiltinTool:
    return HarnessBuiltinTool(id=name)


def _skill_from_legacy_ref(skill: str) -> HarnessSelectedSkill:
    if _is_skill_center_space_ref(skill):
        return HarnessSelectedSkill(
            source="skillspace",
            skill_space_id=_skill_center_space_id(skill),
        )
    return HarnessSelectedSkill(source="skillhub", slug=skill)


def _selected_skill_ref(skill: HarnessSelectedSkill) -> str:
    if skill.source == "skillspace":
        return f"{_SKILL_CENTER_SPACE_PREFIX}{skill.skill_space_id or ''}".strip()
    return (skill.slug or "").strip()


def _dedupe_builtin_tools(
    entries: list[HarnessBuiltinTool],
) -> list[HarnessBuiltinTool]:
    ordered: dict[str, HarnessBuiltinTool] = {}
    for entry in entries:
        tool_id = entry.id.strip()
        if not tool_id:
            continue
        ordered[tool_id] = entry.model_copy(update={"id": tool_id})
    return list(ordered.values())


def _dedupe_selected_skills(
    entries: list[HarnessSelectedSkill],
) -> list[HarnessSelectedSkill]:
    ordered: dict[str, HarnessSelectedSkill] = {}
    for entry in entries:
        ref = _selected_skill_ref(entry)
        if ref:
            ordered[ref] = entry
    return list(ordered.values())


def _builtin_tool_entries(
    config: HarnessOverrides,
    *,
    only_set: bool,
) -> list[HarnessBuiltinTool]:
    set_fields = config.model_fields_set
    entries: list[HarnessBuiltinTool] = []
    if (not only_set or "tools" in set_fields) and config.tools:
        entries.extend(
            _builtin_tool_from_name(name) for name in split_csv(config.tools)
        )
    if (not only_set or "builtin_tools" in set_fields) and config.builtin_tools:
        entries.extend(config.builtin_tools)
    if (not only_set or "mcp_router_id" in set_fields) and config.mcp_router_id:
        entries = _add_mcp_router_id_entry(entries, config.mcp_router_id)
    return _dedupe_builtin_tools(entries)


def _add_mcp_router_id_entry(
    entries: list[HarnessBuiltinTool],
    mcp_router_id: str,
) -> list[HarnessBuiltinTool]:
    updated: list[HarnessBuiltinTool] = []
    found = False
    for entry in entries:
        if entry.id.strip() == "mcp_router":
            config = {"mcp_router_id": mcp_router_id, **(entry.config or {})}
            updated.append(entry.model_copy(update={"config": config}))
            found = True
        else:
            updated.append(entry)
    if not found:
        updated.append(
            HarnessBuiltinTool(
                id="mcp_router",
                config={"mcp_router_id": mcp_router_id},
            )
        )
    return updated


def _selected_skill_entries(
    config: HarnessOverrides,
    *,
    only_set: bool,
) -> list[HarnessSelectedSkill]:
    set_fields = config.model_fields_set
    entries: list[HarnessSelectedSkill] = []
    if (not only_set or "skills" in set_fields) and config.skills:
        entries.extend(
            _skill_from_legacy_ref(skill) for skill in split_csv(config.skills)
        )
    if (not only_set or "selected_skills" in set_fields) and config.selected_skills:
        entries.extend(config.selected_skills)
    return _dedupe_selected_skills(entries)


def normalize_harness_overrides(overrides: HarnessOverrides) -> HarnessOverrides:
    """Return a canonical override using AgentKit's structured field names."""
    data = overrides.model_dump(
        mode="json",
        exclude_unset=True,
        exclude_none=False,
    )
    if "registry" in overrides.model_fields_set:
        data.update(_registry_override_delta(overrides.registry))
        data.pop("registry", None)
    builtin_tools = _builtin_tool_entries(overrides, only_set=True)
    if builtin_tools or "tools" in overrides.model_fields_set:
        data["builtin_tools"] = [
            item.model_dump(mode="json", exclude_none=True) for item in builtin_tools
        ]
        data.pop("tools", None)
    selected_skills = _selected_skill_entries(overrides, only_set=True)
    if selected_skills or "skills" in overrides.model_fields_set:
        data["selected_skills"] = [
            item.model_dump(mode="json", exclude_none=True) for item in selected_skills
        ]
        data.pop("skills", None)
    return HarnessOverrides.model_validate(data)


def _registry_override_delta(
    registry: HarnessRegistryOverride | None,
) -> dict[str, Any]:
    if registry is None:
        return {}

    updates: dict[str, Any] = {}
    if "space_id" in registry.model_fields_set:
        updates["registry_space_id"] = registry.space_id
    if "endpoint" in registry.model_fields_set:
        updates["registry_endpoint"] = registry.endpoint
    if "region" in registry.model_fields_set:
        updates["registry_region"] = registry.region
    if "top_k" in registry.model_fields_set:
        updates["registry_top_k"] = registry.top_k
    return updates


def merge_harness_overrides(
    *overrides_list: HarnessOverrides | Mapping[str, Any] | None,
) -> HarnessOverrides:
    """Merge Harness override layers in order, keeping AgentKit field names.

    This represents the runtime precedence used by HarnessApp:
    ``env/base agent < session latest < current request``. The env/base layer is
    already materialized into ``base_agent``; this helper merges the request
    overlay layers without injecting unset defaults.
    """
    merged: dict[str, Any] = {}
    for overrides in overrides_list:
        if overrides is None:
            continue
        if isinstance(overrides, HarnessOverrides):
            normalized = normalize_harness_overrides(overrides)
        else:
            normalized = normalize_harness_overrides(
                HarnessOverrides.model_validate(overrides)
            )
        delta = normalized.model_dump(
            mode="json",
            exclude_unset=True,
            exclude_none=False,
        )
        if "builtin_tools" in delta:
            merged.pop("tools", None)
        if "selected_skills" in delta:
            merged.pop("skills", None)
        merged.update(delta)
    return HarnessOverrides.model_validate(merged)


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
    return content.startswith((b"PK\x03\x04", b"PK\x05\x06"))


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
    except (httpx.HTTPError, ValueError):
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


def _is_skill_center_space_ref(skill: str) -> bool:
    return skill.strip().startswith(_SKILL_CENTER_SPACE_PREFIX)


def _skill_center_space_id(skill: str) -> str:
    return skill.strip().removeprefix(_SKILL_CENTER_SPACE_PREFIX).strip()


class SkillLoadError(RuntimeError):
    """A skill failed to download or load (e.g. a malformed ``SKILL.md``).

    Raised instead of silently skipping so the failure surfaces — at the server
    startup for a base skill, or in the invoke response for a per-call override.
    """


def build_skill_toolset(
    skills: list[str], download_dir: Path | None = None
) -> SkillToolset | None:
    """Download each skill source and load them as a single ADK toolset.

    Plain entries are treated as SkillHub skill names/slugs. Entries prefixed
    with ``space:`` are treated as AgentKit skills-center space ids and loaded
    via ``_load_skills_from_space_id``.

    Materialized skills are stored under ``download_dir`` (a fresh temp dir when
    omitted) and loaded via ``load_skill_from_dir``. The directory is **not**
    cleaned up here: a skill's scripts/assets are read from disk while the agent
    runs, so the caller owns the directory's lifetime (the base agent keeps its
    skills for the server's lifetime; a per-invoke override cleans up after the
    run).

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
            if _is_skill_center_space_ref(skill):
                skill_space_id = _skill_center_space_id(skill)
                if not skill_space_id:
                    raise RuntimeError("skills-center space id is empty")

                remote_skills = _load_skills_from_space_id(skill_space_id)
                if not remote_skills:
                    raise RuntimeError(
                        f"No skills found in skills-center space '{skill_space_id}'"
                    )

                for remote_skill in remote_skills:
                    skill_dir = materialize_remote_skill(
                        remote_skill,
                        cache_dir=download_dir,
                    )
                    loaded_skills.append(load_skill_from_dir(skill_dir))
            else:
                loaded_skills.append(
                    load_skill_from_dir(
                        _download_and_extract_skill(skill, download_dir)
                    )
                )
        except Exception as e:
            raise SkillLoadError(f"Skill '{skill}' failed to load: {e}") from e
    return SkillToolset(
        skills=loaded_skills,
        code_executor=UnsafeLocalCodeExecutor(),
    )


def config_from_env() -> HarnessConfig:
    """Parse the environment into a :class:`HarnessConfig` (validated by pydantic)."""
    kwargs: dict[str, Any] = {
        field: value
        for field, env_names in _ENV_FIELDS.items()
        if (value := _env_value(*env_names)) is not None
    }
    selected_skills = _json_env("SELECTED_SKILLS_JSON", "selected_skills")
    if selected_skills is not None:
        kwargs["selected_skills"] = selected_skills
    mcp_servers = _json_env("MCP_SERVERS_JSON", "mcp")
    if mcp_servers is not None:
        kwargs["mcp"] = mcp_servers
    knowledgebase_id = os.environ.get("KNOWLEDGEBASE_ID")
    knowledgebase_config = _json_object_env("KNOWLEDGEBASE_CONFIG_JSON")
    if kwargs.get("knowledgebase_type") or knowledgebase_id:
        kwargs["knowledgebase"] = {
            "type": kwargs.get("knowledgebase_type", ""),
            "id": knowledgebase_id,
            "config": knowledgebase_config,
        }
    longterm_memory_id = os.environ.get("LONG_TERM_MEMORY_ID")
    longterm_memory_config = _json_object_env("LONG_TERM_MEMORY_CONFIG_JSON")
    if kwargs.get("longterm_memory_type") or longterm_memory_id:
        kwargs["longterm_memory"] = {
            "type": kwargs.get("longterm_memory_type", ""),
            "id": longterm_memory_id,
            "config": longterm_memory_config,
        }
    return HarnessConfig(**kwargs)


def harness_overrides_from_env() -> HarnessOverrides:
    """Expose startup env config using the same shape as ``run_sse.harness``.

    ``HarnessConfig`` includes creation-time fields such as app name and memory
    backend selectors. The runtime config endpoint only speaks the request-time
    ``HarnessOverrides`` contract, so this projects the startup env into that
    shape while preserving the model defaults for frontend initialization.
    """

    config = config_from_env()
    data = config.model_dump(
        mode="json",
        include=set(HarnessOverrides.model_fields),
        exclude_none=True,
    )
    return normalize_harness_overrides(HarnessOverrides.model_validate(data))


def _with_temporary_env(tool: Any, env: dict[str, str]) -> Any:
    if not env:
        return tool

    if inspect.iscoroutinefunction(tool):

        @wraps(tool)
        async def async_wrapped(*args, **kwargs):
            old = {key: os.environ.get(key) for key in env}
            os.environ.update(env)
            try:
                return await tool(*args, **kwargs)
            finally:
                _restore_env(old)

        return async_wrapped

    @wraps(tool)
    def wrapped(*args, **kwargs):
        old = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        try:
            return tool(*args, **kwargs)
        finally:
            _restore_env(old)

    return wrapped


def _restore_env(values: dict[str, str | None]) -> None:
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _configured_builtin_tool(entry: HarnessBuiltinTool) -> Any:
    name = entry.id.strip()
    config = dict(entry.config or {})
    if name == "mcp_router":
        tool = _mcp_router_tool(config)
    else:
        tool = _load_builtin_tool(name)
        env = _tool_env_overrides(name, config)
        tool = _with_temporary_env(tool, env)
    setattr(tool, _HARNESS_BUILTIN_TOOL_ID_ATTR, name)
    if config:
        tool._veadk_harness_tool_config = config
    return tool


def _tool_env_overrides(name: str, config: dict[str, Any]) -> dict[str, str]:
    env: dict[str, str] = {}
    tool_id_env = _RUN_CODE_TOOL_ENVS.get(name)
    tool_id = config.get("tool_id")
    if tool_id_env and tool_id:
        env[tool_id_env] = str(tool_id)
    region = config.get("region")
    if region:
        env["AGENTKIT_TOOL_REGION"] = str(region)
    return env


def _mcp_router_tool(config: dict[str, Any]) -> Any:
    from google.adk.tools.mcp_tool.mcp_session_manager import (
        StreamableHTTPConnectionParams,
    )
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

    config = _resolve_mcp_router_config(config)
    url = _config_or_env(config, "url", "url_env", "TOOL_MCP_ROUTER_URL")
    api_key = _config_or_env(
        config,
        "api_key",
        "api_key_env",
        "TOOL_MCP_ROUTER_API_KEY",
    ) or _config_or_env(config, "apikey", "apikey_env", "TOOL_MCP_ROUTER_API_KEY")
    if not url:
        raise ToolLoadError("Tool 'mcp_router' requires url or TOOL_MCP_ROUTER_URL.")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=url, headers=headers)
    )


def _resolve_mcp_router_config(config: dict[str, Any]) -> dict[str, Any]:
    mcp_router_id = (
        config.get("mcp_router_id")
        or config.get("mcp_toolset_id")
        or config.get("id")
        or config.get("_id")
        or os.environ.get("MCP_ROUTER_ID")
        or os.environ.get("MCP_TOOLSET_ID")
    )
    if not mcp_router_id:
        return config
    if _mcp_router_resolver is None:
        if not _config_or_env(config, "url", "url_env", "TOOL_MCP_ROUTER_URL"):
            logger.warning(
                "No Harness MCP router resolver configured for id=%s; "
                "falling back to explicit url/api_key config.",
                mcp_router_id,
            )
        return config
    try:
        resolved = _mcp_router_resolver(str(mcp_router_id), config)
    except Exception as e:
        raise ToolLoadError(
            f"Failed to resolve mcp_router_id '{mcp_router_id}': {e}"
        ) from e
    if resolved is None:
        return config
    merged = dict(resolved)
    merged.update(config)
    return merged


def _config_or_env(
    config: dict[str, Any],
    value_key: str,
    env_key: str,
    default_env: str,
) -> str:
    value = config.get(value_key)
    if value:
        return str(value)
    env_name = str(config.get(env_key) or default_env)
    return os.environ.get(env_name, "")


def _build_builtin_tools(entries: list[HarnessBuiltinTool]) -> list[Any]:
    return [_configured_builtin_tool(entry) for entry in _dedupe_builtin_tools(entries)]


def _add_or_replace_builtin_tools(
    agent: Agent,
    entries: list[HarnessBuiltinTool],
) -> None:
    entries = _dedupe_builtin_tools(entries)
    requested = {entry.id for entry in entries}
    agent.tools = [
        tool for tool in agent.tools if _builtin_tool_id(tool) not in requested
    ]
    agent.tools.extend(_build_builtin_tools(entries))


def _builtin_tool_id(tool: Any) -> str | None:
    return getattr(tool, _HARNESS_BUILTIN_TOOL_ID_ATTR, None) or _tool_name(tool)


def _mcp_server_key(server: HarnessMcpServer) -> str:
    return server.name.strip() or server.server_url.strip()


def _build_mcp_toolset(server: HarnessMcpServer) -> Any:
    from google.adk.tools.mcp_tool.mcp_session_manager import (
        StreamableHTTPConnectionParams,
    )
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

    url = server.server_url.strip()
    if not url:
        raise ToolLoadError("MCP server requires server_url.")
    headers = (
        {"Authorization": f"Bearer {server.bear_token}"} if server.bear_token else None
    )
    toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=url, headers=headers)
    )
    setattr(toolset, _HARNESS_MCP_SERVER_ATTR, _mcp_server_key(server))
    return toolset


def _build_mcp_toolsets(servers: list[HarnessMcpServer]) -> list[Any]:
    return [_build_mcp_toolset(server) for server in servers]


def _remove_harness_mcp_toolsets(agent: Agent) -> None:
    agent.tools = [
        tool for tool in agent.tools if not getattr(tool, _HARNESS_MCP_SERVER_ATTR, "")
    ]


def _add_mcp_toolsets(agent: Agent, servers: list[HarnessMcpServer]) -> None:
    if not servers:
        return
    agent.tools.extend(_build_mcp_toolsets(servers))


def _selected_skill_refs(skills: list[HarnessSelectedSkill]) -> list[str]:
    refs = [_selected_skill_ref(skill) for skill in skills]
    return [ref for ref in refs if ref]


def _assemble_agent(config: HarnessConfig) -> tuple[Agent, ShortTermMemory]:
    """Build an agent and its short-term memory from a :class:`HarnessConfig`.

    Skills are downloaded from the skill hub and mounted as an ADK
    :class:`SkillToolset` tool. An empty backend string disables the knowledge
    base / long-term memory. Backend values are validated by each component's
    pydantic model (fast-fail on an unknown value).
    """
    tools = _build_builtin_tools(_builtin_tool_entries(config, only_set=False))

    skills = _selected_skill_refs(_selected_skill_entries(config, only_set=False))
    if skills:
        logger.info(f"Loading skills {skills} for harness.")
        skill_toolset = build_skill_toolset(skills)
        if skill_toolset is not None:
            tools.append(skill_toolset)
    tools.extend(_build_mcp_toolsets(config.mcp))

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
    knowledgebase_override = config.knowledgebase
    if knowledgebase_override is None and config.knowledgebase_type:
        knowledgebase_override = HarnessResourceOverride(
            type=config.knowledgebase_type,
        )
    if knowledgebase_override:
        knowledgebase_override = _resolve_resource_override(
            "knowledgebase", knowledgebase_override
        )
    if knowledgebase_override and knowledgebase_override.type:
        logger.info(
            f"Initializing knowledge base: backend={knowledgebase_override.type} "
            f"index={config.app_name}"
        )
        knowledgebase = KnowledgeBase(
            backend=knowledgebase_override.type,  # type: ignore[arg-type]
            **_request_resource_config(
                "knowledgebase", knowledgebase_override, config.app_name, resolve=False
            ),
        )

    long_term_memory = None
    longterm_memory_override = config.longterm_memory
    if longterm_memory_override is None and config.longterm_memory_type:
        longterm_memory_override = HarnessResourceOverride(
            type=config.longterm_memory_type,
        )
    if longterm_memory_override:
        longterm_memory_override = _resolve_resource_override(
            "longterm_memory", longterm_memory_override
        )
    if longterm_memory_override and longterm_memory_override.type:
        logger.info(
            f"Initializing long-term memory: backend={longterm_memory_override.type} "
            f"index={config.app_name}"
        )
        long_term_memory = LongTermMemory(
            backend=longterm_memory_override.type,  # type: ignore[arg-type]
            **_request_resource_config(
                "longterm_memory",
                longterm_memory_override,
                config.app_name,
                resolve=False,
            ),
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
        auto_save_session=long_term_memory is not None,
        short_term_memory=short_term_memory,
    )
    _apply_sampling_overrides(agent, config)
    if registry_config is not None:
        setattr(agent, _REGISTRY_CONFIG_ATTR, registry_config)
    return agent, short_term_memory


def init_harness_agent() -> tuple[Agent, ShortTermMemory]:
    """Create the long-lived agent on first startup by reading the environment.

    Returns:
        A ``(agent, short_term_memory)`` tuple. The short-term memory is returned
        separately so the server can share the same instance with its ``Runner``.
    """
    _ensure_default_resource_resolver()
    _ensure_default_mcp_router_resolver()
    return _assemble_agent(config_from_env())


def _tool_name(tool: Any) -> str | None:
    """The dispatch name of a tool (function ``__name__`` or tool/toolset ``name``)."""
    return getattr(tool, "__name__", None) or getattr(tool, "name", None)


def _replace_builtin_tools(
    agent: Agent,
    entries: list[HarnessBuiltinTool],
) -> None:
    """Replace the harness-selected built-in tools with ``entries``."""

    agent.tools = [tool for tool in agent.tools if not _is_harness_builtin_tool(tool)]
    agent.tools.extend(_build_builtin_tools(entries))


def _is_harness_builtin_tool(tool: Any) -> bool:
    if getattr(tool, _HARNESS_BUILTIN_TOOL_ID_ATTR, None):
        return True
    name = _tool_name(tool)
    return bool(name and name in set(list_builtin_tools()))


def _replace_skills(
    agent: Agent, skill_ids: list[str], download_dir: Path | None = None
) -> None:
    """Replace the harness-selected skill toolset with ``skill_ids``."""

    agent.tools = [tool for tool in agent.tools if not isinstance(tool, SkillToolset)]
    toolset = build_skill_toolset(skill_ids, download_dir=download_dir)
    if toolset is not None:
        agent.tools.append(toolset)


def _remove_a2a_registry_tools(agent: Agent) -> None:
    agent.tools = [
        tool for tool in agent.tools if _tool_name(tool) not in _REGISTRY_TOOL_NAMES
    ]


def _request_resource_config(
    kind: str,
    resource: HarnessResourceOverride,
    app_name: str | None,
    *,
    resolve: bool = True,
) -> dict[str, Any]:
    if resolve:
        resource = _resolve_resource_override(kind, resource)
    config = dict(resource.config or {})
    configured_backend_config = config.pop("backend_config", None)
    if resource.id:
        config.setdefault("index", resource.id)
        config.setdefault("app_name", resource.id)
    elif app_name:
        config.setdefault("app_name", app_name)
    config.pop("type", None)
    config.pop("backend", None)
    direct = {
        key: value for key, value in config.items() if key in _RESOURCE_DIRECT_FIELDS
    }
    backend_config = {
        key: value
        for key, value in config.items()
        if key not in _RESOURCE_DIRECT_FIELDS
    }
    if isinstance(configured_backend_config, Mapping):
        backend_config = {**configured_backend_config, **backend_config}
    elif configured_backend_config:
        backend_config["backend_config"] = configured_backend_config
    if backend_config:
        if "index" in direct:
            backend_config.setdefault("index", direct["index"])
        if "app_name" in direct:
            backend_config.setdefault("app_name", direct["app_name"])
        direct["backend_config"] = backend_config
    return direct


def _resolve_resource_override(
    kind: str,
    resource: HarnessResourceOverride,
) -> HarnessResourceOverride:
    if not resource.id:
        return resource
    if _resource_resolver is None:
        if not resource.config:
            logger.warning(
                "No Harness resource resolver configured for %s id=%s; "
                "falling back to id as index/app_name.",
                kind,
                resource.id,
            )
        return resource
    try:
        resolved = _resource_resolver(kind, resource)
    except Exception as e:
        raise ResourceResolutionError(
            f"Failed to resolve {kind} resource '{resource.id}': {e}"
        ) from e
    if resolved is None:
        if resource.config:
            logger.warning(
                "Harness resource resolver returned no config for %s id=%s; "
                "using the explicit request config.",
                kind,
                resource.id,
            )
            return resource
        raise ResourceResolutionError(
            f"No runtime config found for {kind} resource '{resource.id}'. "
            "Provide config explicitly or register a Harness resource resolver."
        )
    return _merge_resolved_resource(resource, resolved)


def _merge_resolved_resource(
    requested: HarnessResourceOverride,
    resolved: HarnessResourceOverride | Mapping[str, Any],
) -> HarnessResourceOverride:
    resolved_resource = _coerce_resolved_resource(requested, resolved)
    config = dict(resolved_resource.config or {})
    config.update(requested.config or {})
    return HarnessResourceOverride(
        type=requested.type or resolved_resource.type,
        id=requested.id or resolved_resource.id,
        config=config,
    )


def _coerce_resolved_resource(
    requested: HarnessResourceOverride,
    resolved: HarnessResourceOverride | Mapping[str, Any],
) -> HarnessResourceOverride:
    if isinstance(resolved, HarnessResourceOverride):
        return resolved
    raw = dict(resolved)
    override_keys = {"type", "id", "_id", "config"}
    override_data = {key: raw[key] for key in override_keys if key in raw}
    flat_config = {key: value for key, value in raw.items() if key not in override_keys}
    if override_data:
        resolved_resource = HarnessResourceOverride.model_validate(override_data)
        if flat_config:
            config = dict(resolved_resource.config or {})
            config.update(flat_config)
            resolved_resource = resolved_resource.model_copy(update={"config": config})
        return resolved_resource
    return HarnessResourceOverride(
        type=requested.type,
        id=requested.id,
        config=flat_config,
    )


def _remove_knowledgebase_tools(agent: Agent) -> None:
    agent.tools = [
        tool
        for tool in agent.tools
        if not isinstance(tool, LoadKnowledgebaseTool)
        and _tool_name(tool) not in _KNOWLEDGEBASE_TOOL_NAMES
    ]


def _mount_knowledgebase_tools(agent: Agent) -> None:
    if not agent.knowledgebase:
        return

    agent.tools.append(LoadKnowledgebaseTool(knowledgebase=agent.knowledgebase))
    if agent.knowledgebase.enable_profile:
        from veadk.tools.builtin_tools.load_kb_queries import load_kb_queries

        agent.tools.append(load_kb_queries)


def _remove_longterm_memory_tools(agent: Agent) -> None:
    agent.tools = [
        tool
        for tool in agent.tools
        if _tool_name(tool) not in _LONGTERM_MEMORY_TOOL_NAMES
    ]


def _mount_longterm_memory_tools(agent: Agent) -> None:
    if agent.long_term_memory is None:
        return

    from google.adk.tools.load_memory_tool import LoadMemoryTool

    load_memory_tool = LoadMemoryTool()
    if hasattr(load_memory_tool, "custom_metadata"):
        if not load_memory_tool.custom_metadata:
            load_memory_tool.custom_metadata = {}
        load_memory_tool.custom_metadata["backend"] = agent.long_term_memory.backend
    agent.tools.append(load_memory_tool)


def _set_longterm_memory_auto_save(agent: Agent, enabled: bool) -> None:
    from veadk.memory.save_session_callback import save_session_to_long_term_memory

    agent.auto_save_session = enabled
    callback = getattr(agent, "after_agent_callback", None)

    if enabled:
        if callback is None:
            agent.after_agent_callback = save_session_to_long_term_memory
        elif isinstance(callback, list):
            if save_session_to_long_term_memory not in callback:
                callback.append(save_session_to_long_term_memory)
        elif callback is not save_session_to_long_term_memory:
            agent.after_agent_callback = [callback, save_session_to_long_term_memory]
        return

    if callback is save_session_to_long_term_memory:
        agent.after_agent_callback = None
    elif isinstance(callback, list):
        callbacks = [
            item for item in callback if item is not save_session_to_long_term_memory
        ]
        if not callbacks:
            agent.after_agent_callback = None
        elif len(callbacks) == 1:
            agent.after_agent_callback = callbacks[0]
        else:
            agent.after_agent_callback = callbacks


def _apply_resource_overrides(
    agent: Agent,
    overrides: HarnessOverrides,
    app_name: str | None,
) -> None:
    set_fields = overrides.model_fields_set

    if "knowledgebase" in set_fields:
        _remove_knowledgebase_tools(agent)
        knowledgebase_override = overrides.knowledgebase
        if knowledgebase_override:
            knowledgebase_override = _resolve_resource_override(
                "knowledgebase", knowledgebase_override
            )
        if knowledgebase_override and knowledgebase_override.type:
            agent.knowledgebase = KnowledgeBase(
                backend=knowledgebase_override.type,  # type: ignore[arg-type]
                **_request_resource_config(
                    "knowledgebase", knowledgebase_override, app_name, resolve=False
                ),
            )
            _mount_knowledgebase_tools(agent)
        else:
            agent.knowledgebase = None

    if "longterm_memory" in set_fields:
        _remove_longterm_memory_tools(agent)
        longterm_memory_override = overrides.longterm_memory
        if longterm_memory_override:
            longterm_memory_override = _resolve_resource_override(
                "longterm_memory", longterm_memory_override
            )
        if longterm_memory_override and longterm_memory_override.type:
            agent.long_term_memory = LongTermMemory(
                backend=longterm_memory_override.type,  # type: ignore[arg-type]
                **_request_resource_config(
                    "longterm_memory",
                    longterm_memory_override,
                    app_name,
                    resolve=False,
                ),
            )
            _mount_longterm_memory_tools(agent)
            _set_longterm_memory_auto_save(agent, True)
        else:
            agent.long_term_memory = None
            _set_longterm_memory_auto_save(agent, False)


def _apply_sampling_overrides(agent: Agent, overrides: HarnessOverrides) -> None:
    set_fields = overrides.model_fields_set
    if not (_SAMPLING_OVERRIDE_FIELDS & set_fields):
        return

    updates: dict[str, Any] = {}
    if "temperature" in set_fields and overrides.temperature is not None:
        updates["temperature"] = overrides.temperature
    if "top_p" in set_fields and overrides.top_p is not None:
        updates["top_p"] = overrides.top_p
    if "max_tokens" in set_fields and overrides.max_tokens is not None:
        updates["max_output_tokens"] = overrides.max_tokens
    if "presence_penalty" in set_fields and overrides.presence_penalty is not None:
        updates["presence_penalty"] = overrides.presence_penalty
    if "frequency_penalty" in set_fields and overrides.frequency_penalty is not None:
        updates["frequency_penalty"] = overrides.frequency_penalty
    if "penalty" in set_fields and overrides.penalty is not None:
        if "presence_penalty" not in updates:
            updates["presence_penalty"] = overrides.penalty
        if "frequency_penalty" not in updates:
            updates["frequency_penalty"] = overrides.penalty

    if not updates:
        return

    base_config = getattr(agent, "generate_content_config", None)
    generate_content_config = (
        base_config.model_copy(deep=True)
        if base_config is not None
        else types.GenerateContentConfig()
    )
    agent.generate_content_config = generate_content_config.model_copy(update=updates)


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


def _apply_registry_request_auth(
    agent: Agent, tip_token: str = "", authorization: str = ""
) -> None:
    cleaned_tip_token = (tip_token or "").strip()
    cleaned_authorization = (authorization or "").strip()
    if not cleaned_tip_token and not cleaned_authorization:
        return

    from veadk.tools.builtin_tools.a2a_registry import build_a2a_registry_tools

    config = getattr(agent, _REGISTRY_CONFIG_ATTR, None)
    if config is None:
        return

    updated_config = replace(
        config,
        upstream_tip_token=cleaned_tip_token or config.upstream_tip_token,
        upstream_authorization=cleaned_authorization or config.upstream_authorization,
    )
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
    base_agent: Agent,
    overrides: HarnessOverrides,
    download_dir: Path | None = None,
    app_name: str | None = None,
) -> Agent:
    """Clone the base agent for a one-off invocation and apply per-request overrides.

    Uses ADK's :meth:`~google.adk.agents.base_agent.BaseAgent.clone`, then applies
    only the fields the request actually set. ``model_name``, ``system_prompt``,
    ``runtime``, sampling params, tools, skills, knowledge base, and long-term
    memory replace the clone's value.

    ``download_dir`` is where any skills are downloaded; the caller owns it and
    should remove it once the invocation finishes.
    """
    overrides = normalize_harness_overrides(overrides)
    set_fields = overrides.model_fields_set

    update: dict[str, Any] = {}
    if "system_prompt" in set_fields:
        update["instruction"] = overrides.system_prompt
    if "runtime" in set_fields:
        update["runtime"] = overrides.runtime
    cloned = base_agent.clone(update=update)

    if "model_name" in set_fields:
        cloned.update_model(overrides.model_name)

    if "builtin_tools" in set_fields:
        _replace_builtin_tools(
            cloned,
            _builtin_tool_entries(overrides, only_set=True),
        )

    if "selected_skills" in set_fields:
        _replace_skills(
            cloned,
            _selected_skill_refs(_selected_skill_entries(overrides, only_set=True)),
            download_dir,
        )

    if "mcp" in set_fields:
        _remove_harness_mcp_toolsets(cloned)
        _add_mcp_toolsets(cloned, overrides.mcp)

    _apply_sampling_overrides(cloned, overrides)
    _apply_resource_overrides(cloned, overrides, app_name)
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
    app_name: str | None = None,
    registry_tip_token: str = "",
    registry_authorization: str = "",
    session_overrides: HarnessOverrides | Mapping[str, Any] | None = None,
    current_overrides: HarnessOverrides | Mapping[str, Any] | None = None,
) -> Agent:
    """Clone a harness agent for one run and attach per-turn dynamic tools."""

    if session_overrides is not None or current_overrides is not None:
        overrides = merge_harness_overrides(
            overrides,
            session_overrides,
            current_overrides,
        )

    if overrides is not None:
        cloned = spawn_harness_agent(
            base_agent,
            overrides,
            download_dir=download_dir,
            app_name=app_name,
        )
    else:
        cloned = base_agent.clone(update={})

    _apply_registry_request_auth(cloned, registry_tip_token, registry_authorization)
    _add_dynamic_a2a_agent_tools(cloned, prompt)
    return cloned
