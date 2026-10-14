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
import httpx
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


class _FakeStreamResponse:
    def __init__(
        self,
        url: str,
        content: bytes,
        *,
        final_url: str | None = None,
        chunk_size: int = 8192,
        is_redirect: bool = False,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = final_url or url
        self._content = content
        self._chunk_size = chunk_size
        self.is_redirect = is_redirect
        self.headers = headers or {}

    def __enter__(self) -> "_FakeStreamResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def close(self) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self):
        for offset in range(0, len(self._content), self._chunk_size):
            yield self._content[offset : offset + self._chunk_size]


class _FakeHttpClient:
    def __init__(self, responses: list[_FakeStreamResponse]) -> None:
        self._responses = responses
        self.requested: list[str] = []

    def __enter__(self) -> "_FakeHttpClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def build_request(self, method: str, url: str) -> tuple[str, str]:
        assert method == "GET"
        self.requested.append(url)
        return method, url

    def send(self, request: tuple[str, str], *, stream: bool) -> _FakeStreamResponse:
        assert stream is True
        return self._responses.pop(0)


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


def test_findskill_skill_downloads_by_public_slug(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    remote_skill = VeADKSkill(
        name="public-skill",
        description="Public skill.",
        path="public/example/public-skill",
        id="public/example/public-skill",
        slug="public/example/public-skill",
        source_type="findskill",
        version_id="v2",
    )
    requested: list[str] = []

    def get(url: str, **kwargs):
        requested.append(url)
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            content=_zip_bytes(
                {
                    "SKILL.md": (
                        "---\nname: public-skill\ndescription: Public skill.\n---\n"
                        "Public body.\n"
                    )
                }
            ),
        )

    monkeypatch.setattr(materializer.httpx, "get", get)

    skill_dir = materialize_remote_skill(remote_skill, cache_dir=tmp_path)

    assert load_skill_from_dir(skill_dir).name == "public-skill"
    assert requested == [
        "https://skills.volces.com/v1/skills/download/public/example/public-skill"
    ]


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


def test_materialize_tos_skill_uri_downloads_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[dict[str, object]] = []

    class FakeVeTOS:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)

        def download_directory(
            self, bucket_name: str, prefix: str, local_dir: str, **kwargs: object
        ) -> bool:
            calls.append(
                {
                    "bucket_name": bucket_name,
                    "prefix": prefix,
                    "local_dir": local_dir,
                    **kwargs,
                }
            )
            skill_dir = Path(local_dir)
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: reporting\ndescription: Reporting skill.\n---\nBody.\n",
                encoding="utf-8",
            )
            return True

    monkeypatch.setattr("veadk.integrations.ve_tos.ve_tos.VeTOS", FakeVeTOS)
    monkeypatch.setattr(
        materializer,
        "_get_cloud_credentials",
        lambda: ("runtime-ak", "runtime-sk", "runtime-sts"),
    )

    skill_dir = materializer.materialize_tos_skill_source(
        uri="tos://customer-bucket/skills/reporting/",
        cache_dir=tmp_path,
        region="cn-beijing",
    )

    assert load_skill_from_dir(skill_dir).name == "reporting"
    assert calls[0]["bucket_name"] == "customer-bucket"
    assert calls[0]["region"] == "cn-beijing"
    assert calls[1]["bucket_name"] == "customer-bucket"
    assert calls[1]["prefix"] == "skills/reporting/"
    assert calls[1]["raise_on_error"] is True
    assert calls[1]["max_files"] == materializer._MAX_TOS_DIRECTORY_OBJECTS
    assert calls[1]["max_bytes"] == materializer._MAX_TOS_DIRECTORY_BYTES


def test_materialize_tos_skill_uri_rejects_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeVeTOS:
        def __init__(self, **kwargs: object) -> None:
            pass

        def download_directory(
            self, bucket_name: str, prefix: str, local_dir: str, **kwargs: object
        ) -> bool:
            root = Path(local_dir)
            (root / "reporting").mkdir(parents=True)
            (root / "reporting" / "SKILL.md").write_text(
                "---\nname: reporting\ndescription: Reporting skill.\n---\nBody.\n",
                encoding="utf-8",
            )
            (root / "search").mkdir()
            (root / "search" / "SKILL.md").write_text(
                "---\nname: search\ndescription: Search skill.\n---\nBody.\n",
                encoding="utf-8",
            )
            return True

    monkeypatch.setattr("veadk.integrations.ve_tos.ve_tos.VeTOS", FakeVeTOS)
    monkeypatch.setattr(
        materializer,
        "_get_cloud_credentials",
        lambda: ("runtime-ak", "runtime-sk", "runtime-sts"),
    )

    with pytest.raises(SkillMaterializeError, match="has no SKILL.md"):
        materializer.materialize_tos_skill_source(
            uri="tos://customer-bucket/skills/",
            cache_dir=tmp_path,
        )


def test_materialize_tos_skill_uri_rejects_bucket_root(tmp_path: Path):
    with pytest.raises(SkillMaterializeError, match="must point to a Skill directory"):
        materializer.materialize_tos_skill_source(
            uri="tos://customer-bucket",
            cache_dir=tmp_path,
        )


def test_materialize_tos_skill_uri_rejects_path_traversal(tmp_path: Path):
    with pytest.raises(SkillMaterializeError, match="safe Skill directory"):
        materializer.materialize_tos_skill_source(
            uri="tos://customer-bucket/skills/../secret/",
            cache_dir=tmp_path,
        )


def test_materialize_public_tos_zip_downloads_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_client = _FakeHttpClient(
        [
            _FakeStreamResponse(
                "https://customer-bucket.tos-cn-beijing.volces.com/skills/reporting.zip",
                _zip_bytes(
                    {
                        "reporting/SKILL.md": (
                            "---\nname: reporting\ndescription: Reporting skill.\n---\n"
                            "Public body.\n"
                        )
                    }
                ),
            )
        ]
    )

    monkeypatch.setattr(materializer.httpx, "Client", lambda **kwargs: fake_client)

    skill_dir = materializer.materialize_tos_skill_source(
        public_url="https://customer-bucket.tos-cn-beijing.volces.com/skills/reporting.zip",
        cache_dir=tmp_path,
    )

    assert fake_client.requested == [
        "https://customer-bucket.tos-cn-beijing.volces.com/skills/reporting.zip"
    ]
    assert load_skill_from_dir(skill_dir).name == "reporting"


def test_materialize_public_tos_zip_accepts_split_zip_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_client = _FakeHttpClient(
        [
            _FakeStreamResponse(
                "https://bucket.tos-cn-beijing.volces.com/reporting.zip",
                _zip_bytes(
                    {
                        "SKILL.md": (
                            "---\nname: reporting\ndescription: Reporting skill.\n---\n"
                            "Body.\n"
                        )
                    }
                ),
                chunk_size=1,
            )
        ]
    )

    monkeypatch.setattr(materializer.httpx, "Client", lambda **kwargs: fake_client)

    skill_dir = materializer.materialize_tos_skill_source(
        public_url="https://bucket.tos-cn-beijing.volces.com/reporting.zip",
        cache_dir=tmp_path,
    )

    assert load_skill_from_dir(skill_dir).name == "reporting"


def test_materialize_public_tos_zip_validates_each_redirect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_client = _FakeHttpClient(
        [
            _FakeStreamResponse(
                "https://bucket.tos-cn-beijing.volces.com/reporting.zip",
                b"",
                is_redirect=True,
                headers={"location": "https://169.254.169.254/latest/meta-data"},
            )
        ]
    )

    monkeypatch.setattr(materializer.httpx, "Client", lambda **kwargs: fake_client)

    with pytest.raises(SkillMaterializeError, match="host is not a TOS endpoint"):
        materializer.materialize_tos_skill_source(
            public_url="https://bucket.tos-cn-beijing.volces.com/reporting.zip",
            cache_dir=tmp_path,
        )


def test_materialize_public_tos_zip_rejects_userinfo(tmp_path: Path):
    credential = "ak" + ":" + "sk"
    with pytest.raises(SkillMaterializeError, match="must not include credentials"):
        materializer.materialize_tos_skill_source(
            public_url=(
                f"https://{credential}@bucket.tos-cn-beijing.volces.com/reporting.zip"
            ),
            cache_dir=tmp_path,
        )


def test_materialize_public_tos_zip_rejects_signed_query(tmp_path: Path):
    with pytest.raises(SkillMaterializeError, match="must not include credentials"):
        materializer.materialize_tos_skill_source(
            public_url=(
                "https://bucket.tos-cn-beijing.volces.com/reporting.zip"
                "?X-Tos-Signature=secret"
            ),
            cache_dir=tmp_path,
        )


def test_materialize_public_tos_zip_rejects_fake_tos_host(tmp_path: Path):
    with pytest.raises(SkillMaterializeError, match="host is not a TOS endpoint"):
        materializer.materialize_tos_skill_source(
            public_url="https://evil.tos-cn-beijing.volces.com.example.com/reporting.zip",
            cache_dir=tmp_path,
        )


def test_materialize_public_tos_zip_rejects_redirect_to_non_tos_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_client = _FakeHttpClient(
        [
            _FakeStreamResponse(
                "https://bucket.tos-cn-beijing.volces.com/reporting.zip",
                b"",
                is_redirect=True,
                headers={"location": "https://example.com/reporting.zip"},
            )
        ]
    )

    monkeypatch.setattr(materializer.httpx, "Client", lambda **kwargs: fake_client)

    with pytest.raises(SkillMaterializeError, match="host is not a TOS endpoint"):
        materializer.materialize_tos_skill_source(
            public_url="https://bucket.tos-cn-beijing.volces.com/reporting.zip",
            cache_dir=tmp_path,
        )


def test_materialize_public_tos_zip_streams_size_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(materializer, "_MAX_TOS_PUBLIC_ARCHIVE_BYTES", 4)

    fake_client = _FakeHttpClient(
        [
            _FakeStreamResponse(
                "https://bucket.tos-cn-beijing.volces.com/reporting.zip",
                b"PK\x03\x04too-large",
                chunk_size=2,
            )
        ]
    )

    monkeypatch.setattr(materializer.httpx, "Client", lambda **kwargs: fake_client)

    with pytest.raises(SkillMaterializeError, match="exceeds 64 MiB"):
        materializer.materialize_tos_skill_source(
            public_url="https://bucket.tos-cn-beijing.volces.com/reporting.zip",
            cache_dir=tmp_path,
        )


def test_materialize_public_tos_zip_rejects_uncompressed_size_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(materializer, "_MAX_TOS_PUBLIC_UNCOMPRESSED_BYTES", 4)
    fake_client = _FakeHttpClient(
        [
            _FakeStreamResponse(
                "https://bucket.tos-cn-beijing.volces.com/reporting.zip",
                _zip_bytes(
                    {
                        "SKILL.md": "---\nname: reporting\n---\nBody.\n",
                        "large.txt": "12345",
                    }
                ),
            )
        ]
    )

    monkeypatch.setattr(materializer.httpx, "Client", lambda **kwargs: fake_client)

    with pytest.raises(SkillMaterializeError, match="uncompressed size limit"):
        materializer.materialize_tos_skill_source(
            public_url="https://bucket.tos-cn-beijing.volces.com/reporting.zip",
            cache_dir=tmp_path,
        )


def test_materialize_public_tos_zip_rejects_file_count_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(materializer, "_MAX_TOS_PUBLIC_ARCHIVE_FILES", 1)
    fake_client = _FakeHttpClient(
        [
            _FakeStreamResponse(
                "https://bucket.tos-cn-beijing.volces.com/reporting.zip",
                _zip_bytes(
                    {
                        "SKILL.md": "---\nname: reporting\n---\nBody.\n",
                        "extra.txt": "extra",
                    }
                ),
            )
        ]
    )

    monkeypatch.setattr(materializer.httpx, "Client", lambda **kwargs: fake_client)

    with pytest.raises(SkillMaterializeError, match="file count limit"):
        materializer.materialize_tos_skill_source(
            public_url="https://bucket.tos-cn-beijing.volces.com/reporting.zip",
            cache_dir=tmp_path,
        )


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


def test_legacy_skillspace_download_uses_explicit_region(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_skill = VeADKSkill(
        name="regional-skill",
        description="Regional skill.",
        path="skills/s-123/v1/regional-skill.zip",
        skill_space_id="space-1",
        bucket_name="bucket",
        id="s-123",
    )
    calls: list[dict[str, object]] = []

    class FakeVeTOS:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)

        def download(self, **kwargs: object) -> bool:
            calls.append(kwargs)
            return True

    monkeypatch.setattr(
        materializer,
        "_get_cloud_credentials",
        lambda: pytest.fail("explicit credentials should be reused"),
    )
    monkeypatch.setattr("veadk.integrations.ve_tos.ve_tos.VeTOS", FakeVeTOS)

    assert materializer._download_legacy_skill_space_skill(
        remote_skill,
        tmp_path / "skill.zip",
        region="cn-shanghai",
        credentials=("state-ak", "state-sk", "state-sts"),
        raise_on_error=True,
    )
    assert calls[0]["ak"] == "state-ak"
    assert calls[0]["sk"] == "state-sk"
    assert calls[0]["session_token"] == "state-sts"
    assert calls[0]["region"] == "cn-shanghai"
    assert calls[1]["raise_on_error"] is True


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
