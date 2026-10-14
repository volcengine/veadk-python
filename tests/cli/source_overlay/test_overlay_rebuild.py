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
"""Exercise the actual build script when CR cannot export previous Skill files."""

import json
import os
import sys

import pytest

from veadk.cli.generated_agent_codegen import GeneratedFile
from veadk.cli.generated_agent_skills import CanonicalSkillSnapshot
from veadk.cli.legacy_runtime_recovery import build_source_preserving_overlay


def _files(action="keep", digest="a"):
    item = {
        "name": "runbook",
        "folder": "runbook",
        "description": "Offline runbook",
        "source": "runtime",
    }
    published = {"name": "database", "selectedSkills": [item]}
    edited = {**published, "selectedSkills": [] if action == "remove" else [item]}
    snapshots = ()
    if action == "replace":
        edited["selectedSkills"] = [{**item, "source": "local"}]
        snapshots = (
            CanonicalSkillSnapshot(
                name="runbook",
                description="Offline runbook",
                files=(
                    GeneratedFile(
                        path="skills/runbook/SKILL.md",
                        content="# explicit replacement\n",
                    ),
                ),
                content_digest="a" * 64,
            ),
        )
    return {
        f["path"]: f["content"]
        for f in build_source_preserving_overlay(
            source_image="example-cn-shanghai.cr.volces.com/agentkit/db@sha256:"
            + digest * 64,
            published_draft=published,
            edited_draft=edited,
            canonical_skills=snapshots,
            application_mcp=True,
        )
    }


def _previous(root):
    skill = root / "skills/runbook"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# previous update marker\n")
    (skill / "references").mkdir()
    (skill / "references/query.sql").write_text("SELECT 1;\n")
    for name in ("managed", "selected", "final"):
        (root / (name + ".json")).write_text(json.dumps(["runbook"]))
    return root


def _prepare(tmp_path, monkeypatch, previous, files):
    source = tmp_path / "input"
    output = tmp_path / "output"
    for name, content in files.items():
        if name.startswith(".veadk-studio-overlay/"):
            p = source / name.removeprefix(".veadk-studio-overlay/")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
    for p in source.rglob("*"):
        p.chmod(0o555 if p.is_dir() else 0o444)
    source.chmod(0o555)
    monkeypatch.setenv("VEADK_STUDIO_SKILL_OVERLAY", str(previous))
    monkeypatch.setattr(sys, "argv", ["build-script", str(source), str(output)])
    exec(
        compile(files[".veadk-studio-validate.py"], "generated-build-script", "exec"),
        {},
    )
    return output


def test_mcp_only_rebuild_carries_previous_overlay_skill(tmp_path, monkeypatch):
    previous = _previous(tmp_path / "previous")
    output = _prepare(tmp_path, monkeypatch, previous, _files())
    assert json.loads((output / "selected.json").read_text()) == ["runbook"]
    assert (
        output / "skills/runbook/SKILL.md"
    ).read_text() == "# previous update marker\n"
    assert (output / "skills/runbook/references/query.sql").read_text() == "SELECT 1;\n"
    assert (
        previous / "skills/runbook/SKILL.md"
    ).read_text() == "# previous update marker\n"
    again = tmp_path / "again"
    again.mkdir()
    second = _prepare(again, monkeypatch, output, _files(digest="b"))
    assert (second / "skills/runbook/SKILL.md").read_bytes() == (
        output / "skills/runbook/SKILL.md"
    ).read_bytes()


@pytest.mark.parametrize("action", ["replace", "remove"])
def test_rebuild_respects_explicit_replacement_and_removal(
    tmp_path, monkeypatch, action
):
    output = _prepare(
        tmp_path, monkeypatch, _previous(tmp_path / "previous"), _files(action)
    )
    selected = json.loads((output / "selected.json").read_text())
    if action == "replace":
        assert selected == ["runbook"]
        assert (
            output / "skills/runbook/SKILL.md"
        ).read_text() == "# explicit replacement\n"
        assert not (output / "skills/runbook/references/query.sql").exists()
    else:
        assert selected == []
        assert not (output / "skills/runbook").exists()


def test_revision_is_bound_to_source_digest_for_opaque_content():
    assert (
        _files(digest="a")[".veadk-studio-layout.json"]
        != _files(digest="b")[".veadk-studio-layout.json"]
    )


@pytest.mark.parametrize(
    "bad",
    ["symlink", "missing", "manifest", "oversize", "fifo", "hardlink", "file_limit"],
)
def test_rebuild_rejects_unsafe_inherited_files(tmp_path, monkeypatch, bad):
    previous = _previous(tmp_path / "previous")
    skill = previous / "skills/runbook"
    if bad == "symlink":
        (skill / "link").symlink_to(tmp_path / "outside")
    elif bad == "missing":
        (skill / "SKILL.md").unlink()
    elif bad == "manifest":
        (previous / "final.json").write_text("[]")
    elif bad == "oversize":
        (skill / "huge").write_bytes(b"x" * (1024 * 1024 + 1))
    elif bad == "fifo":
        os.mkfifo(skill / "pipe")
    elif bad == "hardlink":
        os.link(skill / "SKILL.md", skill / "linked")
    else:
        for index in range(257):
            (skill / str(index)).write_text("x")
    with pytest.raises(RuntimeError, match="legacy_overlay_|legacy_skill_"):
        _prepare(tmp_path, monkeypatch, previous, _files())


def test_rebuild_preserves_opaque_base_skill_without_an_old_overlay(
    tmp_path, monkeypatch
):
    output = _prepare(tmp_path, monkeypatch, tmp_path / "absent", _files())
    assert json.loads((output / "selected.json").read_text()) == []
    assert json.loads((output / "final.json").read_text()) == ["runbook"]
    assert not (output / "skills/runbook").exists()


def test_rebuild_enforces_combined_uploaded_and_inherited_file_limit(
    tmp_path, monkeypatch
):
    previous = _previous(tmp_path / "previous")
    for index in range(60):
        (previous / "skills/runbook" / str(index)).write_text("retained")
    files = _files()
    files[".veadk-studio-overlay/selected.json"] = '["new"]'
    files[".veadk-studio-overlay/final.json"] = '["new", "runbook"]'
    files[".veadk-studio-overlay/skills/new/SKILL.md"] = "# Uploaded"
    for index in range(200):
        files[f".veadk-studio-overlay/skills/new/{index}"] = "uploaded"
    with pytest.raises(RuntimeError, match="legacy_skill_total_too_large"):
        _prepare(tmp_path, monkeypatch, previous, files)


def test_rebuild_enforces_inherited_total_bytes(tmp_path, monkeypatch):
    previous = _previous(tmp_path / "previous")
    for index in range(8):
        (previous / "skills/runbook" / str(index)).write_bytes(b"x" * 1024 * 1024)
    with pytest.raises(RuntimeError, match="legacy_skill_total_too_large"):
        _prepare(tmp_path, monkeypatch, previous, _files())
