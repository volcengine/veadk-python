# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Parse and validate Skill metadata with PyYAML's safe loader."""

from __future__ import annotations

import re

import yaml

_SKILL_NAME = re.compile(r"^[a-z0-9-]{1,64}$")


class SkillFrontmatterError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_skill_frontmatter(value: str) -> tuple[str, str]:
    lines = value.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillFrontmatterError(
            "SKILL_MD_FRONTMATTER_MISSING",
            "SKILL.md 第 1 行必须是 `---`，用于开始 frontmatter。",
        )

    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        ),
        None,
    )
    if closing_index is None:
        raise SkillFrontmatterError(
            "SKILL_MD_FRONTMATTER_UNCLOSED",
            "SKILL.md frontmatter 缺少结束行 `---`。",
        )

    source = "\n".join(lines[1:closing_index]) + "\n"
    try:
        metadata = yaml.safe_load(source)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = (
            f"（第 {mark.line + 2} 行，第 {mark.column + 1} 列）"
            if mark is not None
            else ""
        )
        problem = str(getattr(error, "problem", "") or error).splitlines()[0]
        raise SkillFrontmatterError(
            "SKILL_MD_FRONTMATTER_INVALID",
            f"SKILL.md frontmatter YAML 格式错误{location}：{problem}",
        ) from error

    if not isinstance(metadata, dict):
        raise SkillFrontmatterError(
            "SKILL_MD_FRONTMATTER_INVALID",
            "SKILL.md frontmatter 必须是 YAML 对象。",
        )

    name = metadata.get("name")
    description = metadata.get("description")
    if (
        not isinstance(name, str)
        or not _SKILL_NAME.fullmatch(name)
        or "agentkit" in name
    ):
        raise SkillFrontmatterError(
            "SKILL_MD_NAME_INVALID",
            "SKILL.md 的 name 必须为 1–64 位小写字母、数字或连字符。",
        )
    if (
        not isinstance(description, str)
        or not description
        or len(description) > 1024
        or re.search(r"<[^>]+>", description)
    ):
        raise SkillFrontmatterError(
            "SKILL_MD_DESCRIPTION_INVALID",
            "SKILL.md 的 description 必填、不能超过 1024 个字符，且不能包含 HTML/XML 标签。",
        )
    return name, description


__all__ = ["SkillFrontmatterError", "parse_skill_frontmatter"]
