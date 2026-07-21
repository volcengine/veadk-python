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
"""Stable, JSON-safe metadata extracted from an agent instance."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.skill_toolset import SkillToolset

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_SKILL_TOOLSET_CLASS_NAMES = {"SkillsToolset"}


def agent_skill_summaries(agent: object) -> list[dict[str, str]]:
    """Return deduplicated local skill metadata mounted on one agent."""
    summaries: dict[str, str] = {}

    legacy_skills = getattr(agent, "skills_dict", None)
    if isinstance(legacy_skills, dict):
        for skill in legacy_skills.values():
            _add_skill_summary(summaries, skill)

    for tool in getattr(agent, "tools", []) or []:
        if not isinstance(tool, SkillToolset):
            continue
        skills = getattr(tool, "_skills", None)
        if not isinstance(skills, dict):
            continue
        for skill in skills.values():
            _add_skill_summary(summaries, skill)

    return [
        {"name": name, "description": summaries[name]} for name in sorted(summaries)
    ]


def agent_component_summaries(agent: object) -> list[dict[str, str]]:
    """Return mounted components without duplicating models, tools, or skills.

    The output intentionally uses a small stable set of lower-case ``kind``
    values. Unknown agent attributes are ignored rather than exposing arbitrary
    object state.
    """
    components: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    _add_attribute_component(components, seen, "knowledgebase", agent, "knowledgebase")
    _add_attribute_component(components, seen, "memory", agent, "short_term_memory")
    _add_attribute_component(components, seen, "memory", agent, "long_term_memory")
    _add_attribute_component(
        components, seen, "prompt_manager", agent, "prompt_manager"
    )
    _add_attribute_component(components, seen, "example_store", agent, "example_store")

    run_processor = getattr(agent, "run_processor", None)
    if run_processor is not None and type(run_processor).__name__ != "NoOpRunProcessor":
        _add_component(components, seen, "run_processor", run_processor)

    for tracer in _as_components(getattr(agent, "tracers", None)):
        _add_component(components, seen, "tracer", tracer)

    for tool in getattr(agent, "tools", []) or []:
        if not isinstance(tool, BaseToolset) or _is_skill_toolset(tool):
            continue
        _add_component(components, seen, "toolset", tool)

    for plugin in _as_components(getattr(agent, "plugins", None)):
        _add_component(components, seen, "plugin", plugin)

    return components


def _add_skill_summary(summaries: dict[str, str], skill: object) -> None:
    name = getattr(skill, "name", None)
    description = getattr(skill, "description", None)
    if isinstance(name, str) and _SAFE_NAME.fullmatch(name):
        summaries.setdefault(name, str(description or ""))


def _add_attribute_component(
    components: list[dict[str, str]],
    seen: set[tuple[str, str]],
    kind: str,
    agent: object,
    attribute: str,
) -> None:
    component = getattr(agent, attribute, None)
    if component is not None:
        _add_component(components, seen, kind, component)


def _add_component(
    components: list[dict[str, str]],
    seen: set[tuple[str, str]],
    kind: str,
    component: object,
) -> None:
    name = _component_name(component)
    key = (kind, name)
    if key in seen:
        return
    seen.add(key)

    summary = {"kind": kind, "name": name}
    description = _component_description(component)
    if description:
        summary["description"] = description
    components.append(summary)


def _component_name(component: object) -> str:
    for attribute in ("name", "index"):
        value = getattr(component, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return type(component).__name__


def _component_description(component: object) -> str:
    description = getattr(component, "description", None)
    if isinstance(description, str) and description.strip():
        return description.strip()
    backend = getattr(component, "backend", None)
    if isinstance(backend, str) and backend.strip():
        return f"backend: {backend.strip()}"
    return ""


def _as_components(value: Any) -> Iterable[object]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return value
    return (value,)


def _is_skill_toolset(tool: BaseToolset) -> bool:
    return isinstance(tool, SkillToolset) or (
        type(tool).__name__ in _SKILL_TOOLSET_CLASS_NAMES
    )
