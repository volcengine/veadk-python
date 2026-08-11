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

"""Deterministic, narrowly scoped repairs for generated Skill packages."""

from __future__ import annotations

import inspect

from veadk.cli.frontend_skill_creator import _runner_source


def repair_generated_skill(root):
    """Repair safe frontmatter and root-name mistakes without changing behavior."""
    import json
    import re

    changes = []
    skill_md_path = root / "SKILL.md"
    if not skill_md_path.is_file():
        return root, changes

    original = skill_md_path.read_text(encoding="utf-8")
    text = original
    if text.startswith("\ufeff"):
        text = text.removeprefix("\ufeff")
        changes.append("移除 SKILL.md 的 UTF-8 BOM")

    lines = text.splitlines()
    first_content = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )
    if (
        first_content is not None
        and first_content > 0
        and lines[first_content].strip() == "---"
    ):
        lines = lines[first_content:]
        changes.append("移除 SKILL.md frontmatter 前的空行")

    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == "---"
        ),
        None,
    )
    repaired_name = ""

    def quoted_value(raw):
        if len(raw) < 2 or raw[0] != raw[-1] or raw[0] not in {"'", '"'}:
            return None
        if raw[0] == "'":
            return raw[1:-1].replace("''", "'")
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        return value if isinstance(value, str) else None

    def safe_plain_description(value):
        lowered = value.casefold()
        return bool(
            value
            and value == value.strip()
            and len(value) <= 1024
            and "\n" not in value
            and "\r" not in value
            and not re.search(r"<[^>]+>", value)
            and not re.search(r":\s|\s#", value)
            and value[0] not in "-?:,[]{}#&*!|>'\"%@`"
            and lowered
            not in {
                "null",
                "~",
                "true",
                "false",
                "yes",
                "no",
                "on",
                "off",
            }
            and not re.fullmatch(
                r"[-+]?(?:\d[\d_]*)(?:\.\d+)?(?:[eE][-+]?\d+)?",
                value,
            )
            and not re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}(?:[Tt ].*)?", value)
        )

    if closing_index is not None:
        field_pattern = re.compile(r"^(\s*)(name|description)(\s*:\s*)(.*?)(\s*)$")
        for index in range(1, closing_index):
            match = field_pattern.fullmatch(lines[index])
            if match is None:
                continue
            indent, key, separator, raw, trailing = match.groups()
            candidate = quoted_value(raw)
            if candidate is not None:
                safe = (
                    re.fullmatch(r"[a-z0-9-]{1,64}", candidate) is not None
                    if key == "name"
                    else safe_plain_description(candidate)
                )
                if safe:
                    lines[index] = f"{indent}{key}{separator}{candidate}{trailing}"
                    changes.append(f"移除 {key} 外层引号")
                    raw = candidate
            if key == "name" and re.fullmatch(r"[a-z0-9-]{1,64}", raw):
                repaired_name = raw

    repaired = "\n".join(lines)
    if original.endswith(("\n", "\r")):
        repaired += "\n"
    if repaired != original:
        skill_md_path.write_text(repaired, encoding="utf-8")

    if repaired_name and root.name != repaired_name:
        destination = root.with_name(repaired_name)
        if not destination.exists():
            root.rename(destination)
            root = destination
            changes.append("使 Skill 根目录名与 frontmatter name 一致")
    return root, changes


def skill_workbench_runner_source() -> str:
    """Inject deterministic repair into the workbench-only DevEnv runner."""
    source = _runner_source()
    definition_anchor = "def metadata(skill_md):"
    validation_anchor = """    skill_md = skill_md_path.read_text(encoding=\"utf-8\")
    name, description = metadata(skill_md)
"""
    if source.count(definition_anchor) != 1 or source.count(validation_anchor) != 1:
        raise RuntimeError("Skill runner repair anchors are no longer unique")

    repair_source = inspect.getsource(repair_generated_skill).strip()
    source = source.replace(
        definition_anchor,
        f"{repair_source}\n\n\n{definition_anchor}",
        1,
    )
    return source.replace(
        validation_anchor,
        """    root, repair_changes = repair_generated_skill(root)
    if repair_changes:
        add_tool_activity(
            \"自动修复 Skill 格式\",
            {\"changes\": repair_changes},
            {\"status\": \"completed\"},
            stage=\"validating\",
        )
    skill_md_path = root / \"SKILL.md\"
    skill_md = skill_md_path.read_text(encoding=\"utf-8\")
    name, description = metadata(skill_md)
""",
        1,
    )


__all__ = ["repair_generated_skill", "skill_workbench_runner_source"]
