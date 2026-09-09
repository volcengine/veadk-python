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
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

import pytest
from veadk.skills.skill import Skill
from veadk.tools.skills_tools.skills_tool import SkillsTool


@pytest.fixture
def invoke(tmp_path):
    (tmp_path / "skills").mkdir()

    def run(files, name="hello", source="skillspace", fail_publish=False):
        skill = Skill(
            name=name,
            description="test",
            path="sample.zip",
            skill_space_id="ss-test",
            source_type=source,
        )
        tool = SkillsTool({name: skill})

        def download(self, skill, save_path, region):
            if files is None:
                save_path.write_bytes(b"partial download")
                raise RuntimeError("download interrupted")
            if isinstance(files, bytes):
                save_path.write_bytes(files)
            else:
                with zipfile.ZipFile(save_path, "w") as archive:
                    for path, value in files.items():
                        archive.writestr(path, value)

        original = Path.rename

        def rename(path, target):
            if fail_publish and "extracted" in path.parts:
                raise OSError("publish interrupted")
            return original(path, target)

        with (
            patch(
                "veadk.tools.skills_tools.skills_tool.get_session_path",
                return_value=tmp_path,
            ),
            patch.object(SkillsTool, "_download_space_archive", download),
            patch.object(Path, "rename", rename),
        ):
            return tool._invoke_skill(
                name, SimpleNamespace(session=SimpleNamespace(id="test"))
            )

    return run


@pytest.mark.parametrize("source", ["skillspace", "skillhub"])
@pytest.mark.parametrize("prefix", ["", "hello/", "different-wrapper/"])
def test_layouts_install_under_name_and_remove_zips(tmp_path, invoke, source, prefix):
    legacy = tmp_path / "skills/hello.zip"
    legacy.write_bytes(b"old zip")
    result = invoke(
        {prefix + "SKILL.md": "instructions", prefix + "scripts/run.py": "sample"},
        source=source,
    )
    assert not result.startswith("Error"), result
    assert (tmp_path / "skills/hello/SKILL.md").read_text() == "instructions"
    assert (tmp_path / "skills/hello/scripts/run.py").read_text() == "sample"
    assert sorted(p.name for p in (tmp_path / "skills").iterdir()) == ["hello"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["skills"]


def test_separate_skills_and_successful_update(tmp_path, invoke):
    invoke({"SKILL.md": "one", "obsolete": "old"})
    invoke({"SKILL.md": "two"}, name="other")
    invoke({"hello/SKILL.md": "new"})
    assert (tmp_path / "skills/hello/SKILL.md").read_text() == "new"
    assert not (tmp_path / "skills/hello/obsolete").exists()
    assert (tmp_path / "skills/other/SKILL.md").read_text() == "two"
    assert not (tmp_path / "skills/SKILL.md").exists()


@pytest.mark.parametrize(
    "files",
    [
        None,
        b"invalid zip",
        {"file": "missing readme"},
        {"../escaped": "unsafe", "SKILL.md": "bad"},
        {"SKILL.md": b"\xff"},
    ],
)
def test_bad_updates_preserve_old_skill_and_clean_temp(tmp_path, invoke, files):
    invoke({"SKILL.md": "old", "resource": "retain"})
    assert invoke(files).startswith("Error")
    assert (tmp_path / "skills/hello/SKILL.md").read_text() == "old"
    assert (tmp_path / "skills/hello/resource").read_text() == "retain"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["skills"]
    assert not list((tmp_path / "skills").glob("*.zip"))


def test_failed_publish_rolls_back(tmp_path, invoke):
    invoke({"SKILL.md": "old"})
    assert invoke({"SKILL.md": "new"}, fail_publish=True).startswith("Error")
    assert (tmp_path / "skills/hello/SKILL.md").read_text() == "old"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["skills"]


def test_ambiguous_nested_layout_is_deterministic_and_logged(tmp_path, invoke):
    with patch("veadk.tools.skills_tools.skills_tool.logger") as logger:
        result = invoke(
            {"z/SKILL.md": "z", "a/SKILL.md": "a", "a/deeper/SKILL.md": "deep"}
        )
    assert not result.startswith("Error")
    assert (tmp_path / "skills/hello/SKILL.md").read_text() == "a"
    assert any(
        "3 SKILL.md candidates" in str(c) and "a/SKILL.md" in str(c)
        for c in logger.warning.call_args_list
    )


def test_deep_layout_falls_back_and_root_takes_precedence(tmp_path, invoke):
    assert not invoke({"wrapper/nested/SKILL.md": "nested"}).startswith("Error")
    assert (tmp_path / "skills/hello/SKILL.md").read_text() == "nested"
    invoke({"SKILL.md": "root", "example/SKILL.md": "example"})
    assert (tmp_path / "skills/hello/SKILL.md").read_text() == "root"
