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

import asyncio
from pathlib import Path

import pytest

from veadk.skills import VeSkillRegistry
from veadk.skills import registry as registry_module
from veadk.skills.skill import Skill as VeADKSkill


def _write_adk_skill(
    path: Path,
    *,
    name: str,
    description: str = "Demo skill.",
    body: str = "Skill body.",
) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}\n",
        encoding="utf-8",
    )


def test_registry_requires_one_skill_source_id():
    with pytest.raises(ValueError, match="exactly one skill_source_id"):
        VeSkillRegistry(skill_source_id="")

    with pytest.raises(ValueError, match="exactly one skill_source_id"):
        VeSkillRegistry(skill_source_id="sp-one,sp-two")


def test_registry_search_ignores_query_and_fetches_all_remote_skills(
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []
    remote_skills = [
        VeADKSkill(
            name="alpha",
            description="Alpha skill.",
            path="alpha",
            skill_space_id="sp-test",
            id="skill-alpha",
            slug="alpha-slug",
            source_type="skillhub",
            version_id="v1",
        ),
        VeADKSkill(
            name="beta",
            description="Beta skill.",
            path="skills/s-2/v3/beta.zip",
            skill_space_id="sp-test",
            id="skill-beta",
        ),
    ]

    def load_skills_from_cloud(skill_source_id: str) -> list[VeADKSkill]:
        calls.append(skill_source_id)
        return remote_skills

    monkeypatch.setattr(
        registry_module,
        "load_skills_from_cloud",
        load_skills_from_cloud,
    )

    registry = VeSkillRegistry(skill_source_id="sp-test")
    first = asyncio.run(registry.search_skills(query="alpha only"))
    second = asyncio.run(registry.search_skills(query=""))

    assert calls == ["sp-test", "sp-test"]
    assert [skill.name for skill in first] == ["alpha", "beta"]
    assert [skill.name for skill in second] == ["alpha", "beta"]
    assert first[0].metadata == {}
    assert first[1].metadata == {}


def test_registry_get_skill_refreshes_metadata_and_loads_requested_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[str] = []
    materialized: list[str] = []
    alpha = VeADKSkill(
        name="alpha",
        description="Alpha skill.",
        path="alpha",
        skill_space_id="sp-test",
        id="skill-alpha",
        source_type="skillhub",
        version_id="v1",
    )
    beta = VeADKSkill(
        name="beta",
        description="Beta skill.",
        path="beta",
        skill_space_id="sp-test",
        id="skill-beta",
        source_type="skillhub",
        version_id="v1",
    )

    def load_skills_from_cloud(skill_source_id: str) -> list[VeADKSkill]:
        calls.append(skill_source_id)
        return [alpha, beta]

    def materialize_remote_skill(
        skill: VeADKSkill,
        *,
        cache_dir: Path | None = None,
    ) -> Path:
        materialized.append(skill.name)
        skill_dir = (cache_dir or tmp_path) / skill.name
        _write_adk_skill(skill_dir, name=skill.name, body=f"{skill.name} body.")
        return skill_dir

    monkeypatch.setattr(
        registry_module,
        "load_skills_from_cloud",
        load_skills_from_cloud,
    )
    monkeypatch.setattr(
        registry_module,
        "materialize_remote_skill",
        materialize_remote_skill,
    )

    registry = VeSkillRegistry(skill_source_id="sp-test", cache_dir=tmp_path)
    skill = asyncio.run(registry.get_skill(name="beta"))

    assert calls == ["sp-test"]
    assert materialized == ["beta"]
    assert skill.name == "beta"
    assert skill.instructions == "beta body."


def test_registry_get_skill_fetches_remote_list_every_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls = 0
    version = "v1"

    def load_skills_from_cloud(skill_source_id: str) -> list[VeADKSkill]:
        nonlocal calls
        calls += 1
        return [
            VeADKSkill(
                name="alpha",
                description="Alpha skill.",
                path="alpha",
                skill_space_id=skill_source_id,
                id="skill-alpha",
                source_type="skillhub",
                version_id=version,
            )
        ]

    def materialize_remote_skill(
        skill: VeADKSkill,
        *,
        cache_dir: Path | None = None,
    ) -> Path:
        skill_dir = (cache_dir or tmp_path) / skill.version_id / skill.name
        _write_adk_skill(skill_dir, name=skill.name, body=f"Body {skill.version_id}.")
        return skill_dir

    monkeypatch.setattr(
        registry_module,
        "load_skills_from_cloud",
        load_skills_from_cloud,
    )
    monkeypatch.setattr(
        registry_module,
        "materialize_remote_skill",
        materialize_remote_skill,
    )

    registry = VeSkillRegistry(skill_source_id="sp-test", cache_dir=tmp_path)
    first = asyncio.run(registry.get_skill(name="alpha"))
    version = "v2"
    second = asyncio.run(registry.get_skill(name="alpha"))

    assert calls == 2
    assert first.instructions == "Body v1."
    assert second.instructions == "Body v2."


def test_registry_get_skill_raises_when_name_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        registry_module,
        "load_skills_from_cloud",
        lambda skill_source_id: [],
    )

    registry = VeSkillRegistry(skill_source_id="sp-test")

    with pytest.raises(ValueError, match="Skill 'missing' not found"):
        asyncio.run(registry.get_skill(name="missing"))
