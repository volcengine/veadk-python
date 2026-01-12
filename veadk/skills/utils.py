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

from pathlib import Path

import frontmatter

from veadk.skills.skill import Skill
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def load_skill_from_directory(skill_directory: Path) -> Skill:
    logger.info(f"Load skill from {skill_directory}")
    skill_readme = skill_directory / "SKILL.md"
    skill = frontmatter.load(str(skill_readme))

    skill_name = skill.get("name", "")
    skill_description = skill.get("description", "")

    if not skill_name or not skill_description:
        logger.error(
            f"Skill {skill_readme} is missing name or description. Please check the SKILL.md file."
        )
        raise ValueError(
            f"Skill {skill_readme} is missing name or description. Please check the SKILL.md file."
        )

    logger.info(
        f"Successfully loaded skill from {skill_readme}, name={skill['name']}, description={skill['description']}"
    )
    return Skill(
        name=skill_name,  # type: ignore
        description=skill_description,  # type: ignore
        path=str(skill_directory),
    )


def load_skills_from_directory(skills_directory: Path) -> list[Skill]:
    skills = []
    logger.info(f"Load skills from {skills_directory}")
    for skill_directory in skills_directory.iterdir():
        if skill_directory.is_dir():
            skill = load_skill_from_directory(skill_directory)
            skills.append(skill)
    return skills


def load_skills_from_cloud(space_name: str) -> list[Skill]: ...
