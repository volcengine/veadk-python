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

"""Google ADK skill registry backed by a VeADK remote skill space."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from google.adk.skills import Frontmatter
from google.adk.skills import Skill as ADKSkill
from google.adk.skills import models as adk_skill_models
from google.adk.skills import _utils as adk_skill_utils

try:
    from google.adk.skills import SkillRegistry
except ImportError:  # google-adk 1.32 does not export the registry base yet.

    class SkillRegistry:  # type: ignore[no-redef]
        pass


from veadk.skills.materializer import materialize_remote_skill
from veadk.skills.skill import Skill as VeADKSkill
from veadk.skills.utils import load_skills_from_cloud


class VeSkillRegistry(SkillRegistry):
    """ADK ``SkillRegistry`` implementation for one remote VeADK skill space."""

    def __init__(
        self,
        *,
        skill_source_id: str,
        cache_dir: Path | None = None,
    ) -> None:
        normalized_skill_source_id = skill_source_id.strip()
        if not normalized_skill_source_id or "," in normalized_skill_source_id:
            raise ValueError("VeSkillRegistry requires exactly one skill_source_id.")

        self.skill_source_id = normalized_skill_source_id
        self.cache_dir = cache_dir

    async def search_skills(self, *, query: str) -> list[Frontmatter]:
        """Return all remote skills in this skill space, ignoring ``query``."""
        del query
        skills = await asyncio.to_thread(
            load_skills_from_cloud,
            self.skill_source_id,
        )
        return [self._to_frontmatter(skill) for skill in skills]

    async def get_skill(self, *, name: str) -> ADKSkill:
        """Refresh remote metadata, then load the requested skill on demand."""
        remote_skills = await asyncio.to_thread(
            load_skills_from_cloud,
            self.skill_source_id,
        )
        skill = self._find_skill(remote_skills, name)
        if skill is None:
            raise ValueError(f"Skill '{name}' not found in '{self.skill_source_id}'.")

        skill_dir = await asyncio.to_thread(
            materialize_remote_skill,
            skill,
            cache_dir=self.cache_dir,
        )
        return await asyncio.to_thread(load_compatible_adk_skill_from_dir, skill_dir)

    def search_tool_description(self) -> str | None:
        return (
            "Search all skills available in the configured VeADK remote skill space. "
            "The query is ignored; every remote skill is returned for discovery."
        )

    def _to_frontmatter(self, skill: VeADKSkill) -> Frontmatter:
        return Frontmatter(
            name=skill.name,
            description=skill.description,
        )

    def _find_skill(
        self,
        remote_skills: list[VeADKSkill],
        name: str,
    ) -> VeADKSkill | None:
        for skill in remote_skills:
            if skill.name == name:
                return skill
        return None


def load_compatible_adk_skill_from_dir(skill_dir: str | Path) -> ADKSkill:
    """Load an ADK skill while tolerating community frontmatter extensions."""
    resolved_skill_dir = Path(skill_dir).resolve()
    parsed, body, _ = adk_skill_utils._parse_skill_md(resolved_skill_dir)
    frontmatter = _compatible_frontmatter(parsed)

    if resolved_skill_dir.name != frontmatter.name:
        raise ValueError(
            f"Skill name '{frontmatter.name}' does not match directory"
            f" name '{resolved_skill_dir.name}'."
        )

    references = adk_skill_utils._load_dir(resolved_skill_dir / "references")
    assets = adk_skill_utils._load_dir(resolved_skill_dir / "assets")
    raw_scripts = adk_skill_utils._load_dir(resolved_skill_dir / "scripts")
    scripts = {
        name: adk_skill_models.Script(src=content)
        for name, content in raw_scripts.items()
    }

    return adk_skill_models.Skill(
        frontmatter=frontmatter,
        instructions=body,
        resources=adk_skill_models.Resources(
            references=references,
            assets=assets,
            scripts=scripts,
        ),
    )


def _compatible_frontmatter(parsed: dict[str, Any]) -> Frontmatter:
    metadata = parsed.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    else:
        metadata = dict(metadata)

    frontmatter_data: dict[str, Any] = {
        "name": parsed.get("name"),
        "description": parsed.get("description"),
        "metadata": metadata,
    }
    for key in ("license", "compatibility", "allowed-tools"):
        value = parsed.get(key)
        if isinstance(value, str):
            frontmatter_data[key] = value
        elif value is not None:
            metadata.setdefault(key, value)

    for key, value in parsed.items():
        if key not in frontmatter_data and key not in metadata:
            metadata[key] = value

    return Frontmatter.model_validate(frontmatter_data)
