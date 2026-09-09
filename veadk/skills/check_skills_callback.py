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

"""Refresh legacy skills through the existing before-agent callback.

State belongs to each SkillsToolset. This callback does not serialize concurrent
invocations of a shared Agent; applications sharing mutable agents own that lock.
"""

import asyncio
import hashlib
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path

from veadk.skills.utils import load_skills_from_cloud, load_skills_from_directory
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class _RefreshState:
    sources: dict = field(default_factory=dict)
    fingerprints: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    section: str = ""
    instruction: object = None
    base_instruction: object = None


def _fingerprints(skills):
    result = {}
    for name, skill in skills.items():
        record = skill.model_dump(mode="json")
        if not skill.skill_space_id:
            record["readme"] = hashlib.sha256(
                (Path(skill.path) / "SKILL.md").read_bytes()
            ).hexdigest()
        result[name] = json.dumps(record, sort_keys=True, ensure_ascii=False)
    return result


def _load_sources(config, toolset):
    sources, issues = {}, []
    previous = toolset._refresh_state.sources
    for value in config:
        if not str(value).strip():
            continue
        selectors = [str(value)] if Path(value).is_dir() else str(value).split(",")
        for source in map(str.strip, selectors):
            if not source:
                continue
            try:
                sources[source] = (
                    load_skills_from_directory(Path(source))
                    if Path(source).is_dir()
                    else load_skills_from_cloud(source, raise_on_error=True)
                )
            except Exception as exc:
                issues.append({"source": source, "error": type(exc).__name__})
                logger.warning(
                    "Skill source refresh failed: source=%s error=%s",
                    source,
                    type(exc).__name__,
                )
                sources[source] = toolset.on_source_error(
                    source, exc, previous.get(source, [])
                )
    return sources, issues


def _flatten(sources):
    return {skill.name: skill for skills in sources.values() for skill in skills}


def _describe(skills, mode):
    if not skills:
        return ""
    lines = ["\nYou have the following skills:\n"]
    for name in sorted(skills):
        skill = skills[name]
        lines.append(f"- name: {skill.name}\n- description: {skill.description}\n\n")
    if any(skill.checklist for skill in skills.values()):
        lines.append(
            "Some skills have a checklist that you must complete step by step. "
            "Use the `update_check_list` tool to mark each item as completed.\n\n"
        )
    tool = {"local": "skills_tool", "skills_sandbox": "execute_skills"}.get(mode)
    if tool:
        lines.append(f"You can use the skills by calling the `{tool}` tool.\n\n")
    return "".join(lines)


def _instruction(agent, state, section):
    current = agent.instruction
    if isinstance(current, str):
        # Replace only our exact previous section, preserving appended content
        # from other callbacks. Never truncate at a generic user-visible marker.
        if state.section and state.section in current:
            return current.replace(state.section, section, 1)
        return current + section
    base = state.base_instruction if current is state.instruction else current

    async def instruction(context):
        value = base(context)
        if inspect.isawaitable(value):
            value = await value
        return value + section

    return instruction


def _apply(agent, toolset, skills, sources, issues):
    state = toolset._refresh_state
    skills = dict(sorted(skills.items()))
    fingerprints = _fingerprints(skills)
    section = _describe(skills, agent.skills_mode)
    if fingerprints != state.fingerprints or state.instruction is None:
        # Construct before publication; failure leaves the prior view intact.
        tools = toolset.build_tools(skills)
        instruction = agent.instruction
        if section != state.section:
            instruction = _instruction(agent, state, section)
        if callable(agent.instruction) and agent.instruction is not state.instruction:
            state.base_instruction = agent.instruction
        agent.instruction = instruction
        agent._skills_with_checklist.clear()
        agent._skills_with_checklist.update(skills)
        agent.skills_dict = skills
        toolset._tools = tools
        state.fingerprints = fingerprints
        state.section = section
        state.instruction = instruction
        logger.info("Skills refreshed: count=%d", len(skills))
    state.sources, state.issues = sources, issues


def initialize_skills(agent):
    from veadk.tools.skills_tools.skills_toolset import SkillsToolset

    if agent.skills_mode not in {"local", "skills_sandbox", "aio_sandbox"}:
        raise ValueError(f"Unsupported skill mode {agent.skills_mode}")
    toolset = SkillsToolset({}, agent.skills_mode)
    toolset._refresh_state = _RefreshState(base_instruction=agent.instruction)
    sources, issues = _load_sources(agent.skills, toolset)
    _apply(agent, toolset, _flatten(sources), sources, issues)
    agent.tools.append(toolset)


async def check_skills(callback_context):
    from veadk.tools.skills_tools.skills_toolset import SkillsToolset

    agent = callback_context._invocation_context.agent
    if not agent.enable_dynamic_load_skills:
        return
    for toolset in agent.tools:
        if not isinstance(toolset, SkillsToolset) or toolset._refresh_state is None:
            continue
        try:
            sources, issues = await asyncio.to_thread(
                _load_sources, agent.skills, toolset
            )
            skills = await toolset.prepare_skills(
                {
                    name: skill.model_copy(deep=True)
                    for name, skill in _flatten(sources).items()
                },
                callback_context,
            )
            _apply(agent, toolset, skills, sources, issues)
        except Exception as exc:
            toolset._refresh_state.issues = [
                {"source": "refresh", "error": type(exc).__name__}
            ]
            logger.warning(
                "Skills refresh retained previous view: error=%s", type(exc).__name__
            )
    return None
