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

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from veadk import Agent
from veadk.prompts.agent_default_prompt import DEFAULT_INSTRUCTION
from veadk.skills import utils as skill_utils
from veadk.skills.skill import Skill as VeADKSkill
from veadk.tools.skills_tools.skills_toolset import SkillsToolset


def _write_skill(path: Path, *, name: str, description: str = "Demo skill.") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nSkill body.\n",
        encoding="utf-8",
    )


def test_adk_skill_toolset_path_does_not_mount_legacy_skills_toolset(tmp_path: Path):
    skill_dir = tmp_path / "adk-skill"
    _write_skill(skill_dir, name="adk-skill")
    skill_toolset = SkillToolset(skills=[load_skill_from_dir(skill_dir)])

    agent = Agent(
        name="adk_skill_agent",
        model_api_key="test-key",
        tools=[skill_toolset],
    )

    assert skill_toolset in agent.tools
    assert not any(isinstance(tool, SkillsToolset) for tool in agent.tools)
    assert agent.instruction == DEFAULT_INSTRUCTION


def test_legacy_agent_skills_path_warns_and_keeps_legacy_behavior(tmp_path: Path):
    skills_root = tmp_path / "skills"
    _write_skill(skills_root / "legacy-skill", name="legacy-skill")

    with pytest.warns(DeprecationWarning, match=r"Agent\(skills=.*deprecated"):
        agent = Agent(
            name="legacy_skill_agent",
            model_api_key="test-key",
            skills=[str(skills_root)],
            skills_mode="local",
        )

    assert any(isinstance(tool, SkillsToolset) for tool in agent.tools)
    assert "You have the following skills" in agent.instruction
    assert "skills_tool" in agent.instruction


def test_sandbox_agent_skills_path_does_not_warn_as_deprecated(
    monkeypatch: pytest.MonkeyPatch,
):
    remote_skill = VeADKSkill(
        name="sandbox-skill",
        description="Sandbox skill.",
        path="sandbox-skill",
        skill_space_id="space-1",
    )
    monkeypatch.setattr(
        skill_utils,
        "load_skills_from_cloud",
        lambda source: [remote_skill],
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        agent = Agent(
            name="sandbox_skill_agent",
            model_api_key="test-key",
            skills=["space-1"],
            skills_mode="skills_sandbox",
        )

    assert any(isinstance(tool, SkillsToolset) for tool in agent.tools)
    assert "execute_skills" in agent.instruction
    assert not any(
        issubclass(item.category, DeprecationWarning)
        and "skills_mode='local'" in str(item.message)
        for item in caught
    )
