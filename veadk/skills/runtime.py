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

"""Invocation-scoped refresh for legacy local-execution skills.

Space lookup remains in the existing provider; external sources can merge their
results through Agent.skills_transform before a single, consistent publication.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from pathlib import Path

from veadk.skills.skill import Skill
from veadk.skills.utils import load_skills_from_cloud, load_skills_from_directory
from veadk.tools.skills_tools.skills_toolset import SkillsToolset


class SkillRuntime:
    def __init__(self, agent):
        self.agent = agent
        self.lock = asyncio.Lock()
        self.base_instruction = agent.instruction
        self.sources: dict[str, list[Skill]] = {}
        self.issues: list[dict[str, str]] = []
        self.fingerprint: str | None = None
        self.toolset = None
        self.description = ""

    def _load(self):
        sources = {}
        issues = []
        for source in self.agent.skills:
            if not source.strip():
                continue
            path = Path(source)
            # A comma-separated space input preserves the provider's historical
            # behavior. Expand it here to isolate failures per space.
            selectors = [source] if path.is_dir() else source.split(",")
            for selector in selectors:
                selector = selector.strip()
                if not selector:
                    continue
                try:
                    loaded = (
                        load_skills_from_directory(Path(selector))
                        if Path(selector).is_dir()
                        else load_skills_from_cloud(selector, raise_on_error=True)
                    )
                    sources[selector] = loaded
                except Exception as exc:
                    issues.append({"source": selector, "error": type(exc).__name__})
                    sources[selector] = (
                        self.sources.get(selector, [])
                        if self.agent.skills_refresh_failure_policy == "retain"
                        else []
                    )
        return sources, issues

    def initialize(self):
        sources, issues = self._load()
        self._apply(self._flatten(sources))
        self.sources, self.issues = sources, issues

    @staticmethod
    def _flatten(sources):
        # Preserve configured precedence but render in canonical order later.
        by_name = {}
        for skills in sources.values():
            for skill in skills:
                by_name[skill.name] = skill
        return list(by_name.values())

    async def prepare(self, context):
        sources, issues = self.sources, self.issues
        if self.agent.enable_dynamic_load_skills:
            sources, issues = await asyncio.to_thread(self._load)
        skills = self._flatten(sources)
        transform = self.agent.skills_transform
        if transform is not None:
            # Copies prevent an extension from mutating our retained source state.
            skills = transform([s.model_copy(deep=True) for s in skills], context)
            if inspect.isawaitable(skills):
                skills = await skills
        self._apply(skills)
        self.sources, self.issues = sources, issues

    def _apply(self, skills):
        by_name = {}
        records = []
        for skill in sorted(skills, key=lambda item: item.name):
            if skill.name in by_name:
                raise ValueError(f"Duplicate skill name: {skill.name}")
            by_name[skill.name] = skill
            record = skill.model_dump(mode="json")
            if not skill.skill_space_id:
                readme = Path(skill.path) / "SKILL.md"
                record["content_digest"] = hashlib.sha256(
                    readme.read_bytes()
                ).hexdigest()
            records.append(record)
        fingerprint = hashlib.sha256(
            json.dumps(records, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        if fingerprint == self.fingerprint:
            return
        description = self._describe(by_name)
        # All potentially failing construction precedes publication. An existing
        # toolset and prompt remain valid if a wrapper rejects the candidate.
        toolset = SkillsToolset(
            by_name,
            self.agent.skills_mode,
            tool_wrapper=self.agent.skill_tool_wrapper,
        )
        instruction = self.base_instruction
        if isinstance(instruction, str):
            instruction = instruction + description
        else:
            base = instruction

            async def instruction(context):
                value = base(context)
                if inspect.isawaitable(value):
                    value = await value
                return value + description

        tools = [tool for tool in self.agent.tools if tool is not self.toolset]
        self.agent.instruction = instruction
        # Preserve the dictionary identity captured by checklist callbacks.
        self.agent._skills_with_checklist.clear()
        self.agent._skills_with_checklist.update(by_name)
        self.agent.skills_dict = by_name
        self.agent.tools = [*tools, toolset]
        self.toolset = toolset
        self.description = description
        self.fingerprint = fingerprint

    @staticmethod
    def _describe(skills):
        if not skills:
            return ""
        lines = ["\nYou have the following skills:\n"]
        for skill in skills.values():
            lines.append(
                f"- name: {skill.name}\n- description: {skill.description}\n\n"
            )
        if any(skill.checklist for skill in skills.values()):
            lines.append(
                "Use `update_check_list` to mark completed skill checklist items.\n"
            )
        lines.append(
            "Use `skills_tool` to load skill instructions for the current turn. "
            "Instructions returned in earlier turns may be outdated.\n"
        )
        return "".join(lines)

    def status(self):
        return {
            "ready": self.fingerprint is not None,
            "issues": list(self.issues),
            "loaded_skills": [
                {"name": skill.name, "id": skill.id, "version": skill.version_id}
                for skill in self.agent.skills_dict.values()
            ],
        }
