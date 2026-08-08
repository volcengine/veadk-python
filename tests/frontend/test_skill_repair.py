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

from pathlib import Path

from frontend.server.skills.repair import (
    repair_generated_skill,
    skill_workbench_runner_source,
)


def test_repair_generated_skill_normalizes_safe_frontmatter_and_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wrong-root"
    root.mkdir()
    (root / "SKILL.md").write_text(
        '\ufeff\n\n---\nname: "fixed-skill"\n'
        "description: 'Create a concise checklist.'\n---\n\n# Skill\n",
        encoding="utf-8",
    )

    repaired_root, changes = repair_generated_skill(root)

    assert repaired_root == tmp_path / "fixed-skill"
    assert not root.exists()
    assert (repaired_root / "SKILL.md").read_text(encoding="utf-8") == (
        "---\nname: fixed-skill\n"
        "description: Create a concise checklist.\n---\n\n# Skill\n"
    )
    assert changes == [
        "移除 SKILL.md 的 UTF-8 BOM",
        "移除 SKILL.md frontmatter 前的空行",
        "移除 name 外层引号",
        "移除 description 外层引号",
        "使 Skill 根目录名与 frontmatter name 一致",
    ]


def test_repair_generated_skill_leaves_unsafe_quoted_description_for_validator(
    tmp_path: Path,
) -> None:
    root = tmp_path / "safe-name"
    root.mkdir()
    content = '---\nname: safe-name\ndescription: "Input: output"\n---\n\n# Skill\n'
    (root / "SKILL.md").write_text(content, encoding="utf-8")

    repaired_root, changes = repair_generated_skill(root)

    assert repaired_root == root
    assert changes == []
    assert (root / "SKILL.md").read_text(encoding="utf-8") == content


def test_skill_workbench_runner_executes_repair_before_validation() -> None:
    source = skill_workbench_runner_source()

    assert source.count("def repair_generated_skill(root):") == 1
    assert source.count("root, repair_changes = repair_generated_skill(root)") == 1
    assert source.index("root, repair_changes = repair_generated_skill(root)") < (
        source.index("name, description = metadata(skill_md)")
    )
    compile(source, "runner.py", "exec")
