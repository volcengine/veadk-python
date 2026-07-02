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

import io
import tempfile
import zipfile
from pathlib import Path

import pytest
from google.adk.skills import load_skill_from_dir

from veadk.skills import SkillMaterializeError
from veadk.skills import materializer
from veadk.skills.materializer import materialize_remote_skill, skill_version_key
from veadk.skills.skill import Skill as VeADKSkill


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def test_skillhub_skill_downloads_and_normalizes_root_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    remote_skill = VeADKSkill(
        name="hub-skill",
        description="Hub skill.",
        path="hub-skill",
        skill_space_id="sp-test",
        id="skill-id",
        source_type="skillhub",
        version_id="v1",
    )

    def download_skillhub_skill(skill: VeADKSkill, save_path: Path) -> bool:
        save_path.write_bytes(
            _zip_bytes(
                {
                    "SKILL.md": (
                        "---\nname: hub-skill\ndescription: Hub skill.\n---\n"
                        "Hub body.\n"
                    ),
                    "references/readme.txt": "reference",
                }
            )
        )
        return True

    monkeypatch.setattr(
        materializer,
        "download_skillhub_skill",
        download_skillhub_skill,
    )

    skill_dir = materialize_remote_skill(remote_skill, cache_dir=tmp_path)
    skill = load_skill_from_dir(skill_dir)

    assert skill.name == "hub-skill"
    assert skill.instructions == "Hub body."
    assert "readme.txt" in skill.resources.references
    assert (
        tmp_path / "skillhub" / "sp-test" / "hub-skill" / "v1" / "hub-skill"
    ).is_dir()


def test_default_cache_dir_uses_temp_dir(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("VEADK_SKILLS_CACHE_DIR", raising=False)

    assert materializer._default_cache_dir() == (
        Path(tempfile.gettempdir()) / "veadk" / "skills"
    )


def test_default_cache_dir_can_be_overridden_by_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("VEADK_SKILLS_CACHE_DIR", str(tmp_path / "custom-cache"))

    assert materializer._default_cache_dir() == tmp_path / "custom-cache"


def test_legacy_skillspace_skill_uses_tos_path_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    remote_skill = VeADKSkill(
        name="legacy-skill",
        description="Legacy skill.",
        path="skills/s-123/v1/legacy-skill.zip",
        skill_space_id="space-1",
        bucket_name="bucket",
        id="s-123",
    )

    def download_legacy_skill(skill: VeADKSkill, zip_path: Path) -> bool:
        zip_path.write_bytes(
            _zip_bytes(
                {
                    "legacy-skill/SKILL.md": (
                        "---\nname: legacy-skill\ndescription: Legacy skill.\n---\n"
                        "Legacy body.\n"
                    )
                }
            )
        )
        return True

    monkeypatch.setattr(
        materializer,
        "_download_legacy_skill_space_skill",
        download_legacy_skill,
    )

    skill_dir = materialize_remote_skill(remote_skill, cache_dir=tmp_path)
    skill = load_skill_from_dir(skill_dir)

    assert skill_version_key(remote_skill) == "v1"
    assert skill.name == "legacy-skill"
    assert skill.instructions == "Legacy body."
    assert skill_dir == (
        tmp_path / "skillspace" / "space-1" / "legacy-skill" / "v1" / "legacy-skill"
    )


def test_remote_skill_reuses_cache_when_version_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    remote_skill = VeADKSkill(
        name="hub-skill",
        description="Hub skill.",
        path="hub-skill",
        skill_space_id="sp-test",
        id="skill-id",
        source_type="skillhub",
        version_id="v1",
    )
    calls = 0

    def download_skillhub_skill(skill: VeADKSkill, save_path: Path) -> bool:
        nonlocal calls
        calls += 1
        save_path.write_bytes(
            _zip_bytes(
                {
                    "SKILL.md": (
                        "---\nname: hub-skill\ndescription: Hub skill.\n---\n"
                        "Hub body.\n"
                    )
                }
            )
        )
        return True

    monkeypatch.setattr(
        materializer,
        "download_skillhub_skill",
        download_skillhub_skill,
    )

    first_dir = materialize_remote_skill(remote_skill, cache_dir=tmp_path)
    second_dir = materialize_remote_skill(remote_skill, cache_dir=tmp_path)

    assert first_dir == second_dir
    assert calls == 1


def test_remote_skill_downloads_new_version_when_version_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    version = "v1"

    def make_skill(version_id: str) -> VeADKSkill:
        return VeADKSkill(
            name="hub-skill",
            description="Hub skill.",
            path="hub-skill",
            skill_space_id="sp-test",
            id="skill-id",
            source_type="skillhub",
            version_id=version_id,
        )

    def download_skillhub_skill(skill: VeADKSkill, save_path: Path) -> bool:
        save_path.write_bytes(
            _zip_bytes(
                {
                    "SKILL.md": (
                        "---\nname: hub-skill\ndescription: Hub skill.\n---\n"
                        f"Body {version}.\n"
                    )
                }
            )
        )
        return True

    monkeypatch.setattr(
        materializer,
        "download_skillhub_skill",
        download_skillhub_skill,
    )

    first_dir = materialize_remote_skill(make_skill("v1"), cache_dir=tmp_path)
    version = "v2"
    second_dir = materialize_remote_skill(make_skill("v2"), cache_dir=tmp_path)
    skill = load_skill_from_dir(second_dir)

    assert first_dir != second_dir
    assert skill.instructions == "Body v2."
    assert not first_dir.exists()


def test_remote_skill_redownloads_when_cached_skill_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    remote_skill = VeADKSkill(
        name="hub-skill",
        description="Hub skill.",
        path="hub-skill",
        skill_space_id="sp-test",
        id="skill-id",
        source_type="skillhub",
        version_id="v1",
    )
    cached_dir = tmp_path / "skillhub" / "sp-test" / "hub-skill" / "v1" / "hub-skill"
    cached_dir.mkdir(parents=True)
    (cached_dir / "SKILL.md").write_text("not-frontmatter", encoding="utf-8")
    calls = 0

    def download_skillhub_skill(skill: VeADKSkill, save_path: Path) -> bool:
        nonlocal calls
        calls += 1
        save_path.write_bytes(
            _zip_bytes(
                {
                    "SKILL.md": (
                        "---\nname: hub-skill\ndescription: Hub skill.\n---\n"
                        "Recovered.\n"
                    )
                }
            )
        )
        return True

    monkeypatch.setattr(
        materializer,
        "download_skillhub_skill",
        download_skillhub_skill,
    )

    skill_dir = materialize_remote_skill(remote_skill, cache_dir=tmp_path)
    skill = load_skill_from_dir(skill_dir)

    assert calls == 1
    assert skill.instructions == "Recovered."


def test_remote_skill_fails_fast_on_bad_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    remote_skill = VeADKSkill(
        name="bad-zip",
        description="Bad zip.",
        path="bad-zip",
        skill_space_id="sp-test",
        id="skill-id",
        source_type="skillhub",
    )

    def download_skillhub_skill(skill: VeADKSkill, save_path: Path) -> bool:
        save_path.write_bytes(b"not a zip")
        return True

    monkeypatch.setattr(
        materializer,
        "download_skillhub_skill",
        download_skillhub_skill,
    )

    with pytest.raises(SkillMaterializeError, match="valid zip archive"):
        materialize_remote_skill(remote_skill, cache_dir=tmp_path)


def test_remote_skill_reports_cache_dir_creation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    remote_skill = VeADKSkill(
        name="cache-skill",
        description="Cache skill.",
        path="cache-skill",
        skill_space_id="sp-test",
        id="skill-id",
        source_type="skillhub",
    )

    monkeypatch.setattr(
        materializer.Path,
        "mkdir",
        lambda self, **kwargs: (_ for _ in ()).throw(
            PermissionError("permission denied")
        ),
    )

    with pytest.raises(SkillMaterializeError, match="VEADK_SKILLS_CACHE_DIR"):
        materialize_remote_skill(remote_skill, cache_dir=tmp_path / "cache")


def test_remote_skill_rejects_zip_slip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    remote_skill = VeADKSkill(
        name="unsafe-skill",
        description="Unsafe skill.",
        path="unsafe-skill",
        skill_space_id="sp-test",
        id="skill-id",
        source_type="skillhub",
    )

    def download_skillhub_skill(skill: VeADKSkill, save_path: Path) -> bool:
        save_path.write_bytes(_zip_bytes({"../escape.txt": "nope"}))
        return True

    monkeypatch.setattr(
        materializer,
        "download_skillhub_skill",
        download_skillhub_skill,
    )

    with pytest.raises(SkillMaterializeError, match="Unsafe path"):
        materialize_remote_skill(remote_skill, cache_dir=tmp_path)
