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
"""Rebuilding an overlay must not resurrect deselected base-image Skills."""

import json
from types import SimpleNamespace

import pytest

from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from veadk.cli.legacy_runtime_recovery import _SITECUSTOMIZE


def skill(directory, name):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Offline update fixture.\n---\n\n# {name}\n"
    )
    return load_skill_from_dir(directory)


@pytest.mark.parametrize("final", [["current"], []])
def test_rebuilt_overlay_never_resurrects_base_skill(tmp_path, monkeypatch, final):
    original = skill(tmp_path / "base", "base")
    overlay = tmp_path / "overlay"
    skill(overlay / "skills" / "current", "current")
    for filename, value in {
        "managed.json": ["previous"],
        "selected.json": final,
        "final.json": final,
    }.items():
        (overlay / filename).write_text(json.dumps(value))
    monkeypatch.setenv("VEADK_STUDIO_SKILL_OVERLAY", str(overlay))
    namespace = {}
    exec(
        compile(_SITECUSTOMIZE.rsplit("\n_install()", 1)[0], "overlay", "exec"),
        namespace,
    )
    toolset = SkillToolset(skills=[original], registry=None)
    root = SimpleNamespace(tools=[toolset])
    namespace["_apply_skills"](root)
    assert set(toolset._skills) == set(final)
    namespace["_apply_skills"](root)
    assert set(toolset._skills) == set(final)


def test_overlay_missing_preserved_skill_fails_instead_of_silent_removal(
    tmp_path, monkeypatch
):
    for filename, value in {
        "managed.json": [],
        "selected.json": [],
        "final.json": ["missing"],
    }.items():
        (tmp_path / filename).write_text(json.dumps(value))
    monkeypatch.setenv("VEADK_STUDIO_SKILL_OVERLAY", str(tmp_path))
    namespace = {}
    exec(
        compile(_SITECUSTOMIZE.rsplit("\n_install()", 1)[0], "overlay", "exec"),
        namespace,
    )
    with pytest.raises(RuntimeError, match="final selection is incomplete"):
        namespace["_apply_skills"](SimpleNamespace(tools=[]))
