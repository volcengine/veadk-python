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
"""Frontend-selected skill and sub-agent invocation support."""

from __future__ import annotations

import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.plugins import BasePlugin
from google.adk.tools.skill_toolset import SkillToolset

INVOCATION_METADATA_KEY = "veadkInvocation"

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_SKILL_TOOL_NAMES = ("load_skill", "skills_tool", "execute_skills")
_TRANSFER_TOOL_NAME = "transfer_to_agent"


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


def _add_skill_summary(summaries: dict[str, str], skill: object) -> None:
    name = getattr(skill, "name", None)
    description = getattr(skill, "description", None)
    if isinstance(name, str) and _SAFE_NAME.fullmatch(name):
        summaries.setdefault(name, str(description or ""))


class FrontendInvocationPlugin(BasePlugin):
    """Translate structured composer selections into ADK tool directives."""

    def __init__(self, name: str = "veadk_frontend_invocation") -> None:
        super().__init__(name=name)

    async def before_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> None:
        metadata = _invocation_metadata(callback_context)
        if not metadata:
            return

        target = metadata.get("targetAgent")
        target_name, target_path = _target_agent(target)
        current_name = callback_context.agent_name

        if target_name and current_name != target_name:
            next_agent = _next_agent(callback_context, target_path)
            transfer_tool = _matching_tool_name(llm_request, (_TRANSFER_TOOL_NAME,))
            if next_agent and transfer_tool:
                llm_request.append_instructions(
                    [
                        "The user explicitly selected "
                        f"@{target_name} in the frontend. Call "
                        f"`{transfer_tool}` with agent_name=`{next_agent}` as "
                        "your first and only action. Do not answer the user or "
                        "call another tool before transferring."
                    ]
                )
            return

        skill_names = _skill_names(metadata.get("skills"))
        skill_tool = _matching_tool_name(llm_request, _SKILL_TOOL_NAMES)
        if not skill_names or not skill_tool:
            return

        formatted_names = ", ".join(f"`{name}`" for name in skill_names)
        llm_request.append_instructions(
            [
                "The user explicitly selected the following frontend slash "
                f"skills: {formatted_names}. Before answering, you MUST invoke "
                f"`{skill_tool}` for each selected skill in order, using the "
                "tool's declared argument schema. Do not merely describe the "
                "skill or skip loading it."
            ]
        )


def _invocation_metadata(
    callback_context: CallbackContext,
) -> dict[str, Any]:
    run_config = callback_context.run_config
    custom_metadata = run_config.custom_metadata if run_config else None
    if not isinstance(custom_metadata, dict):
        return {}
    metadata = custom_metadata.get(INVOCATION_METADATA_KEY)
    return metadata if isinstance(metadata, dict) else {}


def _skill_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and _SAFE_NAME.fullmatch(name) and name not in names:
            names.append(name)
    return names


def _target_agent(value: object) -> tuple[str, list[str]]:
    if not isinstance(value, dict):
        return "", []
    name = value.get("name")
    raw_path = value.get("path")
    if not isinstance(name, str) or not _SAFE_NAME.fullmatch(name):
        return "", []
    path = (
        [
            item
            for item in raw_path
            if isinstance(item, str) and _SAFE_NAME.fullmatch(item)
        ]
        if isinstance(raw_path, list)
        else []
    )
    if not path or path[-1] != name or len(path) != len(set(path)):
        return "", []
    return name, path


def _next_agent(
    callback_context: CallbackContext,
    target_path: list[str],
) -> str:
    current_name = callback_context.agent_name
    if current_name in target_path:
        index = target_path.index(current_name)
        return target_path[index + 1] if index + 1 < len(target_path) else ""

    invocation_context = getattr(callback_context, "_invocation_context", None)
    current_agent = getattr(invocation_context, "agent", None)
    parent_agent = getattr(current_agent, "parent_agent", None)
    parent_name = getattr(parent_agent, "name", None)
    return parent_name if isinstance(parent_name, str) else ""


def _matching_tool_name(
    llm_request: LlmRequest,
    expected_names: tuple[str, ...],
) -> str:
    for expected in expected_names:
        for actual in llm_request.tools_dict:
            if actual == expected or actual.endswith(f"_{expected}"):
                return actual
    return ""
