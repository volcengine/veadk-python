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

import io
import json
import os
import re
import stat
import subprocess
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veadk.cli.frontend_skill_creator import _MODEL_BASE_URL, _runner_source
from veadk.cli.frontend_skill_workbench import (
    _BOOTSTRAP,
    CreateSkillTaskBody,
    PublishSkillTaskBody,
    RefineSkillTaskBody,
    SkillWorkbenchError,
    SkillWorkbenchService,
    StopSkillTaskBody,
    build_delegation_brief,
    mount_skill_workbench_routes,
    validate_skill_archive,
)


def skill_zip(
    name: str = "release-notes",
    *,
    description: str = "Create concise release notes.",
    extra: dict[str, str] | None = None,
    member_prefix: str = "",
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{member_prefix}{name}/SKILL.md",
            f"---\nname: {name}\ndescription: {description}\n---\n\n# Instructions\n",
        )
        for path, content in (extra or {}).items():
            archive.writestr(f"{member_prefix}{name}/{path}", content)
    return output.getvalue()


def test_delegation_brief_delegates_outcome_without_dictating_steps() -> None:
    brief = build_delegation_brief(
        "optimize",
        "Make failures actionable while preserving the public contract.",
        source_path="/workspace/source.zip",
        source_name="release-notes",
        source_sha256="a" * 64,
        source_files=[
            {"path": "SKILL.md", "size": 128},
            {"path": "references/contract.md", "size": 256},
        ],
        revision=2,
    )

    assert "$skill-creator" in brief
    assert "Make failures actionable" in brief
    assert "Independently inspect" in brief
    assert "current workspace is `/workspace/source.zip`" in brief
    assert "Source Skill name: release-notes" in brief
    assert f"Source archive SHA-256: {'a' * 64}" in brief
    assert '"path":"SKILL.md","size":128' in brief
    assert '"path":"references/contract.md","size":256' in brief
    assert "run this command" not in brief.lower()
    assert "step 1" not in brief.lower()
    assert "cat >" not in brief
    assert ".veadk-output/result.json" in brief
    assert '"skillRoot"' in brief
    assert "only new or changed Skill candidate" in brief
    assert "Handoff protocol" in brief
    assert "Acceptance checks" in brief
    assert "Do not report completion before" in brief
    assert "Detect the user's language" in brief
    assert "same language as the user" in brief
    assert "no more than 100 files" in brief
    assert re.search(r"no more\s+than 2 MiB", brief)


def test_optimization_runner_packages_the_only_changed_skill_from_real_layout(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = tmp_path / "runner.py"
    runner.write_text(_runner_source(), encoding="utf-8")
    (tmp_path / "prompt.txt").write_text("Optimize the Skill", encoding="utf-8")
    (tmp_path / "request.json").write_text(
        json.dumps(
            {
                "operation": "optimize",
                "revision": 1,
            }
        ),
        encoding="utf-8",
    )
    source = tmp_path / "work" / "xiaohongshu-copy-generator"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\n"
        "name: xiaohongshu-copy-generator\n"
        "description: Generate social copy.\n"
        "---\n\n"
        "# Original\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import shutil\n"
        "import sys\n"
        "work = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])\n"
        "source = work / 'xiaohongshu-copy-generator'\n"
        "shutil.copytree(source, work / 'source_skill' / source.name)\n"
        "result = work / 'optimized-xiaohongshu-copy-generator'\n"
        "result.mkdir()\n"
        "(result / 'SKILL.md').write_text(\n"
        "    '---\\nname: xiaohongshu-copy-generator\\n'\n"
        "    'description: Generate reliable social copy.\\n---\\n\\n# Optimized\\n',\n"
        "    encoding='utf-8',\n"
        ")\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    subprocess.run(
        [__import__("sys").executable, str(runner)],
        check=True,
        timeout=10,
    )

    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "succeeded"
    assert status["name"] == "xiaohongshu-copy-generator"
    revision_archive = tmp_path / "artifacts" / "revision-1.zip"
    assert revision_archive.read_bytes() == (tmp_path / "skill.zip").read_bytes()
    assert status["artifact"] == {
        "revision": 1,
        "path": "artifacts/revision-1.zip",
        "sha256": __import__("hashlib")
        .sha256(revision_archive.read_bytes())
        .hexdigest(),
        "size": revision_archive.stat().st_size,
    }
    assert not list(tmp_path.glob(".skill-*.tmp"))
    with zipfile.ZipFile(tmp_path / "skill.zip") as archive:
        assert archive.namelist() == [
            "xiaohongshu-copy-generator/SKILL.md",
        ]
        assert "# Optimized" in archive.read(
            "xiaohongshu-copy-generator/SKILL.md"
        ).decode("utf-8")


def test_optimization_runner_rejects_ambiguous_changed_skills(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = tmp_path / "runner.py"
    runner.write_text(_runner_source(), encoding="utf-8")
    (tmp_path / "prompt.txt").write_text("Optimize the Skill", encoding="utf-8")
    (tmp_path / "request.json").write_text(
        json.dumps({"operation": "optimize", "revision": 1}),
        encoding="utf-8",
    )
    source = tmp_path / "work" / "release-notes"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: release-notes\ndescription: Original notes.\n---\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        "work = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])\n"
        "for folder, name in [('optimized-one', 'release-notes-one'), "
        "('optimized-two', 'release-notes-two')]:\n"
        "    root = work / folder\n"
        "    root.mkdir()\n"
        "    (root / 'SKILL.md').write_text(\n"
        "        f'---\\nname: {name}\\ndescription: Changed notes.\\n---\\n',\n"
        "        encoding='utf-8',\n"
        "    )\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    subprocess.run(
        [__import__("sys").executable, str(runner)],
        check=True,
        timeout=10,
    )

    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["error"] == "优化结果必须只包含一个发生变更的 Skill"
    assert not (tmp_path / "skill.zip").exists()


def test_create_runner_still_rejects_multiple_skill_roots(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = tmp_path / "runner.py"
    runner.write_text(_runner_source(), encoding="utf-8")
    (tmp_path / "prompt.txt").write_text("Create a Skill", encoding="utf-8")
    (tmp_path / "request.json").write_text(
        json.dumps({"operation": "create", "revision": 1}),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        "work = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])\n"
        "for name in ('one-skill', 'two-skill'):\n"
        "    root = work / name\n"
        "    root.mkdir(parents=True)\n"
        "    (root / 'SKILL.md').write_text(\n"
        "        f'---\\nname: {name}\\ndescription: Generated Skill.\\n---\\n',\n"
        "        encoding='utf-8',\n"
        "    )\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    subprocess.run(
        [__import__("sys").executable, str(runner)],
        check=True,
        timeout=10,
    )

    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["error"] == "生成结果必须只包含一个 Skill 根目录"
    assert not (tmp_path / "skill.zip").exists()


def test_create_follow_up_packages_the_only_changed_manifest_handoff(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = tmp_path / "runner.py"
    runner.write_text(_runner_source(), encoding="utf-8")
    (tmp_path / "prompt.txt").write_text("Refine the Skill", encoding="utf-8")
    (tmp_path / "request.json").write_text(
        json.dumps({"operation": "create", "revision": 2}),
        encoding="utf-8",
    )
    previous = tmp_path / "work" / "release-notes"
    previous.mkdir(parents=True)
    (previous / "SKILL.md").write_text(
        "---\nname: release-notes\ndescription: Original notes.\n---\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import pathlib\n"
        "import sys\n"
        "work = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])\n"
        "root = work / '.veadk-output' / 'release-notes'\n"
        "root.mkdir(parents=True)\n"
        "(root / 'SKILL.md').write_text(\n"
        "    '---\\nname: release-notes\\n'\n"
        "    'description: Actionable release notes.\\n---\\n\\n# Refined\\n',\n"
        "    encoding='utf-8',\n"
        ")\n"
        "(root.parent / 'result.json').write_text(\n"
        "    json.dumps({'skillRoot': '.veadk-output/release-notes'}),\n"
        "    encoding='utf-8',\n"
        ")\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    subprocess.run(
        [__import__("sys").executable, str(runner)],
        check=True,
        timeout=10,
    )

    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "succeeded"
    with zipfile.ZipFile(tmp_path / "skill.zip") as archive:
        assert archive.namelist() == ["release-notes/SKILL.md"]
        assert "# Refined" in archive.read("release-notes/SKILL.md").decode("utf-8")


def test_runner_never_overwrites_one_revision_with_different_content(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = tmp_path / "runner.py"
    runner.write_text(_runner_source(), encoding="utf-8")
    (tmp_path / "prompt.txt").write_text("Create the Skill", encoding="utf-8")
    (tmp_path / "request.json").write_text(
        json.dumps({"operation": "create", "revision": 1}),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"

    def write_fake_codex(instructions: str) -> None:
        fake_codex.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import pathlib\n"
            "import sys\n"
            "work = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])\n"
            "root = work / '.veadk-output' / 'release-notes'\n"
            "root.mkdir(parents=True)\n"
            "(root / 'SKILL.md').write_text(\n"
            "    '---\\nname: release-notes\\n"
            "description: Deterministic release notes.\\n---\\n\\n"
            f"{instructions}\\n',\n"
            "    encoding='utf-8',\n"
            ")\n"
            "(root.parent / 'result.json').write_text(\n"
            "    json.dumps({'skillRoot': '.veadk-output/release-notes'}),\n"
            "    encoding='utf-8',\n"
            ")\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)

    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    write_fake_codex("# First")
    subprocess.run(
        [__import__("sys").executable, str(runner)],
        check=True,
        timeout=10,
    )
    revision_archive = tmp_path / "artifacts" / "revision-1.zip"
    first = revision_archive.read_bytes()

    __import__("shutil").rmtree(tmp_path / "work")
    write_fake_codex("# Different")
    subprocess.run(
        [__import__("sys").executable, str(runner)],
        check=True,
        timeout=10,
    )

    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["error"] == "同一 Skill 版本的产物内容发生冲突"
    assert revision_archive.read_bytes() == first
    assert (tmp_path / "skill.zip").read_bytes() == first
    assert not list(tmp_path.glob(".skill-*.tmp"))


def test_runner_rejects_manifest_with_undeclared_fields(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = tmp_path / "runner.py"
    runner.write_text(_runner_source(), encoding="utf-8")
    (tmp_path / "prompt.txt").write_text("Create the Skill", encoding="utf-8")
    (tmp_path / "request.json").write_text(
        json.dumps({"operation": "create", "revision": 1}),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import pathlib\n"
        "import sys\n"
        "work = pathlib.Path(sys.argv[sys.argv.index('-C') + 1])\n"
        "root = work / '.veadk-output' / 'release-notes'\n"
        "root.mkdir(parents=True)\n"
        "(root / 'SKILL.md').write_text(\n"
        "    '---\\nname: release-notes\\n'\n"
        "    'description: Release notes.\\n---\\n',\n"
        "    encoding='utf-8',\n"
        ")\n"
        "(root.parent / 'result.json').write_text(\n"
        "    json.dumps({\n"
        "        'skillRoot': '.veadk-output/release-notes',\n"
        "        'alternateRoot': 'release-notes',\n"
        "    }),\n"
        "    encoding='utf-8',\n"
        ")\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    subprocess.run(
        [__import__("sys").executable, str(runner)],
        check=True,
        timeout=10,
    )

    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["error"] == "Skill 交付清单字段不符合协议"
    assert not (tmp_path / "skill.zip").exists()


def test_follow_up_brief_refuses_non_skill_intent_without_modifying_files() -> None:
    brief = build_delegation_brief(
        "create",
        "Tell me tomorrow's weather",
        source_path="/workspace/work",
        revision=2,
        previous_intents=[
            "Create a release-notes Skill",
            "Add a concise incident summary format",
        ],
    )

    assert "Create a release-notes Skill" in brief
    assert "Add a concise incident summary format" in brief
    assert "outside creating, reviewing, testing, documenting, packaging" in brief
    assert "do not modify any files" in brief
    assert "keep the previous Skill unchanged" in brief


def test_create_request_rejects_an_optimization_source() -> None:
    with pytest.raises(ValueError, match="不接受来源"):
        CreateSkillTaskBody.model_validate(
            {
                "operation": "create",
                "intent": "Create it",
                "source": {
                    "kind": "skill-center",
                    "skillId": "s",
                    "version": "1",
                },
            }
        )


def test_request_models_trim_strings_and_reject_blank_refinement() -> None:
    request = CreateSkillTaskBody.model_validate(
        {
            "operation": "optimize",
            "intent": "  Improve it  ",
            "source": {
                "kind": "skill-center",
                "skillId": "  skill-1  ",
                "skillName": "   ",
                "version": "  3  ",
                "projectName": "  default  ",
                "skillSpaceId": "  space-1  ",
                "skillSpaceName": "  Shared  ",
            },
        }
    )

    assert request.intent == "Improve it"
    assert request.source is not None
    assert request.source.skill_id == "skill-1"
    assert request.source.skill_name is None
    assert request.source.version == "3"
    assert request.source.project_name == "default"
    assert request.source.skill_space_id == "space-1"
    assert request.source.skill_space_name == "Shared"
    with pytest.raises(ValueError, match="请描述希望 Skill 达成的目标"):
        RefineSkillTaskBody(intent=" \n ", expectedRevision=1)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            CreateSkillTaskBody,
            {"operation": "create", "intent": "Create it", "unexpected": True},
        ),
        (
            RefineSkillTaskBody,
            {"intent": "Improve it", "expectedRevision": 1, "unexpected": True},
        ),
        (
            StopSkillTaskBody,
            {"expectedRevision": 1, "unexpected": True},
        ),
        (
            PublishSkillTaskBody,
            {
                "disposition": "create-new",
                "expectedRevision": 1,
                "unexpected": True,
            },
        ),
    ],
)
def test_request_models_reject_unknown_fields(model, payload) -> None:
    with pytest.raises(ValueError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    "expected_revision",
    [True, 1.0, "1"],
    ids=["boolean", "float", "string"],
)
def test_mutation_requests_require_a_strict_integer_revision(
    expected_revision: object,
) -> None:
    with pytest.raises(ValueError):
        PublishSkillTaskBody.model_validate(
            {
                "disposition": "create-new",
                "expectedRevision": expected_revision,
            }
        )


@pytest.mark.parametrize(
    "skill_space_ids",
    [
        [" "],
        ["space-1", " space-1 "],
        ["x" * 257],
        [f"space-{index}" for index in range(101)],
    ],
    ids=["blank", "duplicate", "too-long", "too-many"],
)
def test_publish_request_rejects_invalid_skill_space_ids(
    skill_space_ids: list[str],
) -> None:
    with pytest.raises(ValueError):
        PublishSkillTaskBody(
            disposition="create-new",
            expectedRevision=1,
            skillSpaceIds=skill_space_ids,
        )


def test_optimization_requires_a_center_source_or_uploaded_archive() -> None:
    service = SkillWorkbenchService(tool_id="tool")
    body = CreateSkillTaskBody(operation="optimize", intent="Improve it")

    with pytest.raises(SkillWorkbenchError, match="必须选择来源或上传 ZIP") as caught:
        service.create_task(body, "alice", "Alice")

    assert caught.value.code == "SKILL_SOURCE_REQUIRED"
    assert caught.value.status_code == 422


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            RefineSkillTaskBody,
            {"intent": "Improve it", "expectedRevision": 1_000_001},
        ),
        (
            StopSkillTaskBody,
            {"expectedRevision": 1_000_001},
        ),
        (
            PublishSkillTaskBody,
            {"disposition": "create-new", "expectedRevision": 1_000_001},
        ),
    ],
)
def test_mutation_requests_reject_unbounded_revisions(model, payload) -> None:
    with pytest.raises(ValueError):
        model.model_validate(payload)


def test_validate_skill_archive_returns_normalized_metadata() -> None:
    content = skill_zip(extra={"references/checklist.md": "# Checklist\n"})

    archive = validate_skill_archive(content)

    assert archive.name == "release-notes"
    assert archive.description == "Create concise release notes."
    assert archive.skill_md.startswith("---")
    assert archive.sha256
    assert archive.files == [
        {"path": "SKILL.md", "size": len(archive.skill_md.encode("utf-8"))},
        {
            "path": "references/checklist.md",
            "size": len(b"# Checklist\n"),
        },
    ]


@pytest.mark.parametrize(
    ("builder", "code"),
    [
        (
            lambda z: z.writestr("../SKILL.md", "bad"),
            "SKILL_ARCHIVE_UNSAFE_PATH",
        ),
        (
            lambda z: (
                z.writestr("one/SKILL.md", "---\nname: one\ndescription: One.\n---\n"),
                z.writestr("two/file.md", "bad"),
            ),
            "SKILL_ARCHIVE_MULTIPLE_ROOTS",
        ),
        (
            lambda z: (
                z.writestr("one/SKILL.md", "---\nname: one\ndescription: One.\n---\n"),
                _write_symlink(z, "one/link"),
            ),
            "SKILL_ARCHIVE_SYMLINK",
        ),
    ],
)
def test_validate_skill_archive_rejects_unsafe_boundaries(builder, code: str) -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        builder(archive)

    with pytest.raises(SkillWorkbenchError) as caught:
        validate_skill_archive(output.getvalue())

    assert caught.value.code == code


def test_validate_skill_archive_rejects_invalid_zip() -> None:
    with pytest.raises(SkillWorkbenchError) as caught:
        validate_skill_archive(b"not-a-zip")

    assert caught.value.code == "SKILL_ARCHIVE_INVALID"


def test_validate_skill_archive_rejects_suspicious_compression_ratio() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "compressed/SKILL.md",
            "---\nname: compressed\ndescription: Compressed input.\n---\n"
            + ("x" * (512 * 1024)),
        )

    with pytest.raises(SkillWorkbenchError) as caught:
        validate_skill_archive(output.getvalue())

    assert caught.value.code == "SKILL_ARCHIVE_SUSPICIOUS_COMPRESSION"
    assert caught.value.status_code == 413


def _write_symlink(archive: zipfile.ZipFile, name: str) -> None:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    archive.writestr(info, "target")


def _codex_tool_envs() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(key="CODEX_MODEL", value="doubao-seed-2-0-pro-260215"),
        SimpleNamespace(key="CODEX_API_KEY", value=os.urandom(24).hex()),
        SimpleNamespace(key="CODEX_BASE_URL", value=_MODEL_BASE_URL),
    ]


def test_capabilities_fail_closed_without_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SANDBOX_SKILL_WORKBENCH", raising=False)
    monkeypatch.delenv("SANDBOX_SKILL_CREATOR", raising=False)

    value = SkillWorkbenchService().capabilities()

    assert value == {
        "enabled": False,
        "reason": "DevEnv 暂不可用，请联系管理员检查配置。",
        "operations": ["create", "optimize"],
    }


def test_capabilities_require_ready_devenv_and_optional_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VEADK_SKILL_DEVENV_IMAGE", "registry/dev:1")
    tools = SimpleNamespace(
        get_tool=lambda request: SimpleNamespace(
            tool_type="DevEnv",
            status="Ready",
            image_url="registry/dev:1",
            envs=_codex_tool_envs(),
        )
    )
    service = SkillWorkbenchService(
        tool_id="tool-1", tools_client_factory=lambda region: tools
    )

    value = service.capabilities()

    assert value["enabled"] is True
    assert value["reason"] == ""
    assert value["maxUploadBytes"] == 20 * 1024 * 1024


def test_get_tool_retries_one_transient_read_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    class Tools:
        def get_tool(self, request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise requests.ConnectTimeout("temporary")
            return SimpleNamespace(tool_type="DevEnv", status="Ready")

    service = SkillWorkbenchService(
        tool_id="tool-1",
        tools_client_factory=lambda region: Tools(),
    )
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    tool = service._get_tool("tool-1")

    assert tool.status == "Ready"
    assert attempts == 2


def test_capabilities_fail_closed_when_devenv_has_no_codex_credential() -> None:
    tools = SimpleNamespace(
        get_tool=lambda request: SimpleNamespace(
            tool_type="DevEnv",
            status="Ready",
            image_url="registry/dev:1",
            envs=[],
        )
    )
    service = SkillWorkbenchService(
        tool_id="tool-1",
        tools_client_factory=lambda region: tools,
    )

    value = service.capabilities()

    assert value["enabled"] is False
    assert value["reason"] == "DevEnv 模型配置不可用，请重新部署 Studio。"


def test_delete_session_non_transient_failure_is_actionable() -> None:
    class Tools:
        def delete_session(self, request) -> None:
            raise RuntimeError("upstream unavailable")

    service = SkillWorkbenchService(tool_id="tool-1")
    with pytest.raises(SkillWorkbenchError) as caught:
        service._delete_session(Tools(), "tool-1", "session-1")

    assert caught.value.code == "SKILL_TASK_CLEANUP_FAILED"
    assert str(caught.value) == (
        "删除 Skill 会话失败，临时 DevEnv 可能仍在运行，请稍后重试。"
    )
    assert caught.value.retryable is False


def test_delete_session_retries_transient_failure_idempotently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    class Tools:
        def delete_session(self, request) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise requests.ConnectTimeout("temporary")

    service = SkillWorkbenchService(tool_id="tool-1")
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    service._delete_session(Tools(), "tool-1", "session-1")

    assert attempts == 2


def test_reserve_task_returns_owner_bound_id_without_agentkit() -> None:
    service = SkillWorkbenchService(
        tool_id="tool",
        tools_client_factory=lambda region: pytest.fail("AgentKit must not be called"),
    )

    reservation = service.reserve_task("alice")

    reserved_at = reservation["reservedAt"]
    assert isinstance(reserved_at, int)
    assert reserved_at > 0
    SkillWorkbenchService._validate_job_owner(str(reservation["jobId"]), "alice")


def test_supplied_job_id_is_validated_before_source_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")

    def resolve_source(source):
        pytest.fail("source must not be resolved")

    monkeypatch.setattr(service, "_resolve_center_source", resolve_source)
    body = CreateSkillTaskBody.model_validate(
        {
            "operation": "optimize",
            "intent": "Improve it",
            "source": {
                "kind": "skill-center",
                "skillId": "skill",
                "version": "1",
            },
            "jobId": SkillWorkbenchService._new_job_id("bob"),
        }
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.create_task(body, "alice", "Alice")

    assert caught.value.code == "SKILL_TASK_NOT_FOUND"


def test_supplied_durable_job_id_returns_existing_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(
        tool_id="tool",
        tools_client_factory=lambda region: pytest.fail("must not create Session"),
    )
    existing = {"jobId": job_id, "state": "running"}
    monkeypatch.setattr(service, "get_task", lambda requested, owner: existing)
    body = CreateSkillTaskBody(operation="create", intent="Create", jobId=job_id)

    assert service.create_task(body, "alice", "Alice") is existing


def test_repeated_create_for_one_job_serializes_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    body = CreateSkillTaskBody(operation="create", intent="Create", jobId=job_id)
    first_entered = threading.Event()
    release_first = threading.Event()
    state_lock = threading.Lock()
    created = False
    side_effects = 0

    def create_once(*args, **kwargs):
        nonlocal created, side_effects
        with state_lock:
            if created:
                return {"jobId": job_id, "state": "running"}
        first_entered.set()
        assert release_first.wait(timeout=2)
        with state_lock:
            side_effects += 1
            created = True
        return {"jobId": job_id, "state": "running"}

    monkeypatch.setattr(service, "_create_task_once", create_once)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(service.create_task, body, "alice", "Alice")
            for _ in range(2)
        ]
        assert first_entered.wait(timeout=2)
        release_first.set()
        results = [future.result(timeout=2) for future in futures]

    assert [result["jobId"] for result in results] == [job_id, job_id]
    assert side_effects == 1


def test_create_returns_and_persists_devenv_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Tools:
        def get_tool(self, request):
            return SimpleNamespace(
                tool_type="DevEnv",
                status="Ready",
                image_url="registry/dev:1",
                envs=_codex_tool_envs(),
            )

        def create_session(self, request):
            return SimpleNamespace(
                session_id="session-1",
                endpoint="https://devenv.example",
                expire_at="2026-08-05T12:00:00Z",
            )

    service = SkillWorkbenchService(
        tool_id="tool-1",
        tools_client_factory=lambda region: Tools(),
    )
    launched_request: dict[str, object] = {}

    def post(url: str, **kwargs):
        if "VEADK_SKILL_REQUEST_B64" in kwargs.get("json", {}).get("env", {}):
            encoded = kwargs["json"]["env"]["VEADK_SKILL_REQUEST_B64"]
            launched_request.update(
                json.loads(__import__("base64").b64decode(encoded).decode("utf-8"))
            )
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"status": "completed", "exit_code": 0}},
        )

    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        post,
    )

    result = service.create_task(
        CreateSkillTaskBody(operation="create", intent="Create it"),
        "alice",
        "Alice",
    )

    assert result["toolId"] == "tool-1"
    assert result["sessionId"] == "session-1"
    assert launched_request["toolId"] == "tool-1"
    assert launched_request["sessionId"] == "session-1"


def test_create_retries_transient_idempotent_bootstrap_without_deleting_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch_attempts = 0
    deleted_sessions: list[str] = []

    class Tools:
        def create_session(self, request):
            return SimpleNamespace(
                session_id="session-1",
                endpoint="https://devenv.example",
                expire_at="2026-08-05T12:00:00Z",
            )

        def delete_session(self, request):
            deleted_sessions.append(request.session_id)

    service = SkillWorkbenchService(
        tool_id="tool-1",
        tools_client_factory=lambda region: Tools(),
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool-1")

    def post(url: str, **kwargs):
        nonlocal launch_attempts
        launch_attempts += 1
        if launch_attempts == 1:
            raise requests.ConnectTimeout("temporary bootstrap timeout")
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"status": "completed", "exit_code": 0}},
        )

    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        post,
    )
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    result = service.create_task(
        CreateSkillTaskBody(operation="create", intent="Create it"),
        "alice",
        "Alice",
    )

    assert result["sessionId"] == "session-1"
    assert launch_attempts == 2
    assert deleted_sessions == []


def test_create_retries_transient_idempotent_source_directory_prepare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_attempts = 0
    deleted_sessions: list[str] = []

    class Tools:
        def create_session(self, request):
            return SimpleNamespace(
                session_id="session-1",
                endpoint="https://devenv.example",
                expire_at="2026-08-05T12:00:00Z",
            )

        def delete_session(self, request):
            deleted_sessions.append(request.session_id)

    service = SkillWorkbenchService(
        tool_id="tool-1",
        tools_client_factory=lambda region: Tools(),
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool-1")
    monkeypatch.setattr(service, "_upload_file", lambda *args, **kwargs: None)

    def post(url: str, **kwargs):
        nonlocal prepare_attempts
        if str(kwargs.get("json", {}).get("command", "")).startswith("mkdir -p "):
            prepare_attempts += 1
            if prepare_attempts == 1:
                raise requests.ConnectTimeout("temporary directory prepare timeout")
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"status": "completed", "exit_code": 0}},
        )

    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        post,
    )
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    result = service.create_task(
        CreateSkillTaskBody(operation="optimize", intent="Improve it"),
        "alice",
        "Alice",
        uploaded_archive=skill_zip(),
    )

    assert result["sessionId"] == "session-1"
    assert prepare_attempts == 2
    assert deleted_sessions == []


def test_create_optimization_brief_uses_the_extracted_source_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Tools:
        def create_session(self, request):
            return SimpleNamespace(
                session_id="session-1",
                endpoint="https://devenv.example",
                expire_at="2026-08-05T12:00:00Z",
            )

    service = SkillWorkbenchService(
        tool_id="tool-1",
        tools_client_factory=lambda region: Tools(),
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool-1")
    uploaded_paths: list[str] = []
    monkeypatch.setattr(
        service,
        "_upload_file",
        lambda endpoint, path, content, **kwargs: uploaded_paths.append(path),
    )
    launched_prompt = ""

    def post(url: str, **kwargs):
        nonlocal launched_prompt
        environment = kwargs.get("json", {}).get("env", {})
        if "VEADK_SKILL_PROMPT_B64" in environment:
            launched_prompt = (
                __import__("base64")
                .b64decode(environment["VEADK_SKILL_PROMPT_B64"])
                .decode("utf-8")
            )
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"status": "completed", "exit_code": 0}},
        )

    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        post,
    )

    service.create_task(
        CreateSkillTaskBody(operation="optimize", intent="Improve it"),
        "alice",
        "Alice",
        uploaded_archive=skill_zip(
            extra={"references/contract.md": "Preserve this contract."}
        ),
    )

    assert uploaded_paths[0].endswith("/source.zip")
    assert "extracted in the current workspace at `./release-notes`" in launched_prompt
    assert "/source.zip`" not in launched_prompt
    assert '"path":"SKILL.md"' in launched_prompt
    assert '"path":"references/contract.md"' in launched_prompt


def test_create_session_timeout_is_not_blindly_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_attempts = 0

    class Tools:
        def get_tool(self, request):
            return SimpleNamespace(
                tool_type="DevEnv",
                status="Ready",
                image_url="",
                envs=_codex_tool_envs(),
            )

        def create_session(self, request):
            nonlocal create_attempts
            create_attempts += 1
            raise requests.ReadTimeout("ambiguous create response")

        def list_sessions(self, request):
            return SimpleNamespace(session_infos=[], next_token=None)

    service = SkillWorkbenchService(
        tool_id="tool-1",
        tools_client_factory=lambda region: Tools(),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.create_task(
            CreateSkillTaskBody(operation="create", intent="Create it"),
            "alice",
            "Alice",
        )

    assert create_attempts == 1
    assert caught.value.code == "SKILL_DEVENV_PROVISIONING_FAILED"
    assert caught.value.retryable is False


def test_job_id_hides_cross_owner_resources() -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")

    SkillWorkbenchService._validate_job_owner(job_id, "alice")
    with pytest.raises(SkillWorkbenchError) as caught:
        SkillWorkbenchService._validate_job_owner(job_id, "bob")

    assert caught.value.code == "SKILL_TASK_NOT_FOUND"
    assert caught.value.status_code == 404


def test_list_tasks_filters_owner_projects_summaries_and_sorts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice_new = SkillWorkbenchService._new_job_id("alice")
    alice_old = SkillWorkbenchService._new_job_id("alice")
    bob_job = SkillWorkbenchService._new_job_id("bob")
    requests = []
    pages = [
        SimpleNamespace(
            session_infos=[
                _session(alice_old, "alice", "old-endpoint"),
                _session(bob_job, "bob", "bob-endpoint"),
                _session("unrelated", "alice", "other-endpoint"),
            ],
            next_token="page-2",
        ),
        SimpleNamespace(
            session_infos=[_session(alice_new, "alice", "new-endpoint")],
            next_token=None,
        ),
    ]

    class Tools:
        def list_sessions(self, request):
            requests.append(request)
            return pages.pop(0)

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    tasks = {
        alice_old: {
            "jobId": alice_old,
            "operation": "create",
            "intent": "Old intent",
            "revision": 1,
            "state": "running",
            "stage": "generating",
            "createdAt": 10,
            "activities": [{"private": True}],
            "skillMd": "secret detail",
            "files": [{"path": "SKILL.md"}],
        },
        alice_new: {
            "jobId": alice_new,
            "operation": "optimize",
            "intent": "New intent",
            "revision": 2,
            "state": "ready",
            "stage": "packaging",
            "createdAt": 20,
            "name": "new-skill",
            "source": {"name": "source-skill", "sha256": "private"},
            "validation": {"valid": True},
        },
    }
    monkeypatch.setattr(
        service,
        "_task_and_request_from_session",
        lambda endpoint, job_id: (tasks[job_id], tasks[job_id]),
    )
    monkeypatch.setattr(
        service,
        "_ensure_recovery_snapshot",
        lambda *args, **kwargs: True,
    )

    result = service.list_tasks("alice")

    assert [task["jobId"] for task in result["tasks"]] == [alice_new, alice_old]
    assert result["tasks"][0] == {
        "jobId": alice_new,
        "operation": "optimize",
        "intent": "New intent",
        "revision": 2,
        "state": "ready",
        "stage": "packaging",
        "createdAt": 20,
        "name": "new-skill",
        "sourceName": "source-skill",
        "recoveryAvailable": True,
    }
    assert "activities" not in result["tasks"][1]
    assert "skillMd" not in result["tasks"][1]
    assert "files" not in result["tasks"][1]
    assert requests[0].metadata[0].key == "Username"
    assert requests[0].metadata[0].value == "alice"
    assert requests[1].next_token == "page-2"


def test_list_tasks_skips_one_invalid_session_without_losing_valid_tasks(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    invalid_job = SkillWorkbenchService._new_job_id("alice")
    valid_job = SkillWorkbenchService._new_job_id("alice")
    response = SimpleNamespace(
        session_infos=[
            _session(invalid_job, "alice", "private-invalid-endpoint"),
            _session(valid_job, "alice", "valid-endpoint"),
        ],
        next_token=None,
    )
    tools = SimpleNamespace(list_sessions=lambda request: response)
    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: tools
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")

    def read_task(endpoint, job_id):
        if job_id == invalid_job:
            raise SkillWorkbenchError(
                "SKILL_TASK_STATE_INVALID",
                "Skill 会话状态异常，请稍后重试。",
                status_code=502,
            )
        task = {
            "jobId": valid_job,
            "operation": "optimize",
            "intent": "Keep this task",
            "revision": 1,
            "state": "running",
            "stage": "generating",
            "createdAt": 20,
        }
        return task, task

    monkeypatch.setattr(service, "_task_and_request_from_session", read_task)

    result = service.list_tasks("alice")

    assert [task["jobId"] for task in result["tasks"]] == [valid_job]
    assert invalid_job in caplog.text
    assert "SKILL_TASK_STATE_INVALID" in caplog.text
    assert "private-invalid-endpoint" not in caplog.text


def test_list_tasks_skips_a_session_while_bootstrap_files_are_initializing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    response = SimpleNamespace(
        session_infos=[_session(job_id, "alice", "initializing-endpoint")],
        next_token=None,
    )
    service = SkillWorkbenchService(
        tool_id="tool",
        tools_client_factory=lambda region: SimpleNamespace(
            list_sessions=lambda request: response
        ),
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")

    def initializing(endpoint, requested_job_id):
        raise SkillWorkbenchError(
            "SKILL_TASK_INITIALIZING",
            "DevEnv 已就绪，正在初始化 Skill 工作区",
            status_code=409,
            retryable=True,
        )

    monkeypatch.setattr(service, "_task_and_request_from_session", initializing)

    assert service.list_tasks("alice") == {"tasks": []}


def test_list_tasks_keeps_transport_failure_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    class Tools:
        def list_sessions(self, request):
            nonlocal attempts
            attempts += 1
            raise requests.ConnectTimeout("transport unavailable")

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    with pytest.raises(SkillWorkbenchError) as caught:
        service.list_tasks("alice")

    assert attempts == 2
    assert caught.value.code == "SKILL_TASK_LIST_FAILED"
    assert caught.value.retryable is True


def test_list_tasks_does_not_mark_non_transient_failure_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Tools:
        def list_sessions(self, request):
            raise ValueError("invalid request")

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")

    with pytest.raises(SkillWorkbenchError) as caught:
        service.list_tasks("alice")

    assert caught.value.code == "SKILL_TASK_LIST_FAILED"
    assert caught.value.retryable is False


def test_list_tasks_rejects_repeated_pagination_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(session_infos=[], next_token="same-token")
    tools = SimpleNamespace(list_sessions=lambda request: response)
    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: tools
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")

    with pytest.raises(SkillWorkbenchError) as caught:
        service.list_tasks("alice")

    assert caught.value.code == "SKILL_TASK_LIST_INVALID"
    assert caught.value.retryable is False


def test_list_tasks_returns_expired_session_without_reading_released_devenv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    response = SimpleNamespace(
        session_infos=[
            _session(
                job_id,
                "alice",
                "released-endpoint",
                status="Ready",
                expire_at="2000-01-01T00:00:00Z",
                created_at="1999-12-31T23:00:00Z",
            )
        ],
        next_token=None,
    )
    tools = SimpleNamespace(list_sessions=lambda request: response)
    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: tools
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr(
        service,
        "_task_from_session",
        lambda endpoint, requested_job_id: pytest.fail(
            "an expired DevEnv must not be contacted"
        ),
    )

    result = service.list_tasks("alice")

    assert result == {
        "tasks": [
            {
                "jobId": job_id,
                "operation": "create",
                "intent": "Skill 会话",
                "revision": 1,
                "state": "expired",
                "stage": "expired",
                "createdAt": 946681200,
            }
        ]
    }


def test_center_source_falls_back_to_skill_info_with_space_identity() -> None:
    requests = []

    class Skills:
        def get_skill_version(self, request):
            raise RuntimeError("interface type mismatch")

        def get_skill_info(self, request):
            requests.append(request)
            return SimpleNamespace(
                skill_name="release-notes",
                skill_md=(
                    "---\n"
                    "name: release-notes\n"
                    "description: Create concise release notes.\n"
                    "---\n\n"
                    "# Instructions\n"
                ),
            )

    service = SkillWorkbenchService(
        tool_id="tool",
        skills_client_factory=lambda region: Skills(),
    )
    source = CreateSkillTaskBody.model_validate(
        {
            "operation": "optimize",
            "intent": "Improve it",
            "source": {
                "kind": "skill-center",
                "skillId": "skill-id",
                "skillName": "release-notes",
                "version": "version-id",
                "region": "cn-shanghai",
                "projectName": "default",
                "skillSpaceId": "space-id",
                "skillSpaceName": "Production Skills",
            },
        }
    ).source
    assert source is not None

    archive, metadata = service._resolve_center_source(source)

    assert archive.name == "release-notes"
    assert len(requests) == 1
    assert requests[0].skill_name == "release-notes"
    assert requests[0].skill_space_name == "Production Skills"
    assert requests[0].skill_space_id == "space-id"
    assert metadata["skillName"] == "release-notes"
    assert metadata["skillSpaceName"] == "Production Skills"


def test_center_source_returns_bounded_error_when_both_reads_fail() -> None:
    class Skills:
        def get_skill_version(self, request):
            raise RuntimeError("private version failure")

        def get_skill_info(self, request):
            raise RuntimeError("private info failure")

    service = SkillWorkbenchService(
        tool_id="tool",
        skills_client_factory=lambda region: Skills(),
    )
    source = CreateSkillTaskBody.model_validate(
        {
            "operation": "optimize",
            "intent": "Improve it",
            "source": {
                "kind": "skill-center",
                "skillId": "skill-id",
                "skillName": "release-notes",
                "version": "version-id",
                "skillSpaceId": "space-id",
                "skillSpaceName": "Production Skills",
            },
        }
    ).source
    assert source is not None

    with pytest.raises(SkillWorkbenchError) as caught:
        service._resolve_center_source(source)

    assert caught.value.code == "SKILL_SOURCE_NOT_FOUND"
    assert caught.value.status_code == 404
    assert str(caught.value) == "无法读取指定 Skill 版本"


def test_center_source_transient_version_failure_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version_attempts = 0
    info_attempts = 0

    class Skills:
        def get_skill_version(self, request):
            nonlocal version_attempts
            version_attempts += 1
            raise requests.ConnectTimeout("temporary")

        def get_skill_info(self, request):
            nonlocal info_attempts
            info_attempts += 1
            raise AssertionError(
                "transient version failures must not become fallback reads"
            )

    service = SkillWorkbenchService(
        tool_id="tool",
        skills_client_factory=lambda region: Skills(),
    )
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)
    source = CreateSkillTaskBody.model_validate(
        {
            "operation": "optimize",
            "intent": "Improve it",
            "source": {
                "kind": "skill-center",
                "skillId": "skill-id",
                "skillName": "release-notes",
                "version": "version-id",
                "skillSpaceId": "space-id",
                "skillSpaceName": "Production Skills",
            },
        }
    ).source
    assert source is not None

    with pytest.raises(SkillWorkbenchError) as caught:
        service._resolve_center_source(source)

    assert version_attempts == 2
    assert info_attempts == 0
    assert caught.value.code == "SKILL_SOURCE_READ_FAILED"
    assert caught.value.status_code == 502
    assert caught.value.retryable is True


def test_find_session_distinguishes_expired_from_missing() -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    response = SimpleNamespace(
        session_infos=[
            _session(
                job_id,
                "alice",
                "released-endpoint",
                status="Expired",
                expire_at="2000-01-01T00:00:00Z",
            )
        ]
    )
    tools = SimpleNamespace(list_sessions=lambda request: response)
    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: tools
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service._find_session("tool", job_id)

    assert caught.value.code == "SKILL_TASK_EXPIRED"
    assert caught.value.status_code == 410
    assert str(caught.value) == "DevEnv 已到期并自动释放"


def test_find_session_prefers_resumed_active_session_over_expired_copy() -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    response = SimpleNamespace(
        session_infos=[
            _session(
                job_id,
                "alice",
                "released-endpoint",
                status="Expired",
                expire_at="2000-01-01T00:00:00Z",
            ),
            _session(
                job_id,
                "alice",
                "active-endpoint",
                status="Ready",
                expire_at="2099-01-01T00:00:00Z",
            ),
        ]
    )
    tools = SimpleNamespace(list_sessions=lambda request: response)
    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: tools
    )

    session = service._find_session("tool", job_id)

    assert session["endpoint"] == "active-endpoint"
    assert session["instanceId"] == f"session-{job_id}"


def test_find_session_does_not_mark_non_transient_failure_retryable() -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")

    class Tools:
        def list_sessions(self, request):
            raise ValueError("invalid request")

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service._find_session("tool", job_id)

    assert caught.value.code == "SKILL_TASK_LOOKUP_FAILED"
    assert caught.value.retryable is False


def test_find_session_rejects_a_repeated_pagination_token() -> None:
    calls = 0

    class Tools:
        def list_sessions(self, request):
            nonlocal calls
            calls += 1
            return SimpleNamespace(session_infos=[], next_token="same-token")

    service = SkillWorkbenchService(
        tool_id="tool",
        tools_client_factory=lambda region: Tools(),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service._find_session("tool", service._new_job_id("alice"))

    assert calls == 2
    assert caught.value.code == "SKILL_TASK_LOOKUP_INVALID"
    assert caught.value.retryable is False


def test_delete_task_is_idempotent_after_devenv_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(
        tool_id="tool",
        tools_client_factory=lambda region: pytest.fail(
            "an expired Session has no remote resource to delete"
        ),
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")

    def expired_session(tool_id: str, requested_job_id: str) -> dict[str, str]:
        raise SkillWorkbenchError(
            "SKILL_TASK_EXPIRED",
            "DevEnv 已到期并自动释放",
            status_code=410,
        )

    monkeypatch.setattr(service, "_find_session", expired_session)

    service.delete_task(job_id, "alice")


def test_task_state_normalization_is_shared_by_detail_and_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    payloads = {
        "request.json": {
            "jobId": job_id,
            "operation": "create",
            "intent": "Create it",
            "revision": 1,
            "createdAt": 1,
        },
        "status.json": {"status": "succeeded", "stage": "packaging"},
    }
    monkeypatch.setattr(
        service,
        "_remote_task_payload",
        lambda endpoint, requested_job_id: (
            payloads["request.json"],
            payloads["status.json"],
        ),
    )

    detail = service._task_from_session("endpoint", job_id)

    assert detail["state"] == "ready"
    assert detail["sessionTtlSeconds"] == 3600
    assert service._task_summary(detail)["state"] == "ready"


@pytest.mark.parametrize(
    ("request_update", "status_update"),
    [
        ({"jobId": "sw-000000000000-000000000000000000000000"}, {}),
        ({"operation": "delete"}, {}),
        ({"intent": " \n "}, {}),
        ({"revision": 0}, {}),
        ({}, {"status": "mystery"}),
        ({}, {"stage": "x" * 129}),
    ],
    ids=[
        "mismatched-job",
        "operation",
        "blank-intent",
        "revision",
        "state",
        "stage",
    ],
)
def test_task_state_rejects_malformed_remote_payload(
    monkeypatch: pytest.MonkeyPatch,
    request_update: dict[str, object],
    status_update: dict[str, object],
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    request_data: dict[str, object] = {
        "jobId": job_id,
        "operation": "create",
        "intent": "Create it",
        "revision": 1,
        "createdAt": 1,
        **request_update,
    }
    status: dict[str, object] = {
        "status": "running",
        "stage": "generating",
        **status_update,
    }
    monkeypatch.setattr(
        service,
        "_remote_task_payload",
        lambda endpoint, requested_job_id: (request_data, status),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service._task_from_session("https://devenv.example", job_id)

    assert caught.value.code == "SKILL_TASK_STATE_INVALID"
    assert caught.value.status_code == 502
    assert caught.value.retryable is False
    assert str(caught.value) == "Skill 会话状态异常，请稍后重试。"


def test_task_state_rejects_artifact_metadata_for_a_different_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    monkeypatch.setattr(
        service,
        "_remote_task_payload",
        lambda endpoint, requested_job_id: (
            {
                "jobId": job_id,
                "operation": "create",
                "intent": "Create release notes",
                "revision": 2,
                "createdAt": 1,
            },
            {
                "status": "succeeded",
                "stage": "completed",
                "artifact": {
                    "revision": 1,
                    "path": "artifacts/revision-1.zip",
                    "sha256": "a" * 64,
                    "size": 100,
                },
            },
        ),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service._task_from_session("https://devenv.example", job_id)

    assert caught.value.code == "SKILL_TASK_STATE_INVALID"


def test_task_status_cannot_override_immutable_request_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    request_data = {
        "jobId": job_id,
        "operation": "create",
        "intent": "Create it",
        "revision": 2,
        "createdAt": 1,
    }
    status = {
        "jobId": "untrusted",
        "operation": "optimize",
        "intent": "Replace it",
        "revision": 99,
        "createdAt": 99,
        "status": "running",
        "stage": "generating",
    }
    monkeypatch.setattr(
        service,
        "_remote_task_payload",
        lambda endpoint, requested_job_id: (request_data, status),
    )

    detail = service._task_from_session("https://devenv.example", job_id)

    assert detail["jobId"] == job_id
    assert detail["operation"] == "create"
    assert detail["intent"] == "Create it"
    assert detail["revision"] == 2
    assert detail["createdAt"] == 1


def test_task_state_uses_one_remote_exec_for_request_and_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    calls: list[dict[str, object]] = []
    remote_payload = {
        "request": {
            "jobId": job_id,
            "operation": "create",
            "intent": "Create it",
            "revision": 1,
            "createdAt": 1,
        },
        "status": {"status": "succeeded", "stage": "packaging"},
        "publication": {
            "revision": 1,
            "skillId": "skill-1",
            "version": "2",
            "skillSpaceIds": [],
            "disposition": "create-new",
            "region": "cn-beijing",
            "projectName": "default",
        },
    }

    def post(url: str, *, json: dict[str, object], timeout: int) -> SimpleNamespace:
        calls.append({"url": url, "json": json, "timeout": timeout})
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "data": {
                    "status": "completed",
                    "exit_code": 0,
                    "output": __import__("json").dumps(remote_payload),
                }
            },
        )

    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        post,
    )

    detail = service._task_from_session("https://devenv.example", job_id)

    assert detail["state"] == "published"
    assert len(calls) == 1
    assert calls[0]["timeout"] == (5, 12)
    request_json = calls[0]["json"]
    assert isinstance(request_json, dict)
    command = str(request_json["command"])
    assert "request.json" in command
    assert "status.json" in command
    assert "publication.json" in command
    assert "\n" not in command
    assert "<<" not in command


def test_concurrent_task_state_reads_share_one_remote_exec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    first_entered = threading.Event()
    both_entered = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def remote_payload(endpoint, requested_job_id):
        nonlocal calls
        with calls_lock:
            calls += 1
            if calls == 1:
                first_entered.set()
            if calls == 2:
                both_entered.set()
        assert release.wait(timeout=2)
        return (
            {
                "jobId": requested_job_id,
                "operation": "create",
                "intent": "Create it",
                "revision": 1,
                "createdAt": 1,
            },
            {"status": "running", "stage": "generating"},
        )

    monkeypatch.setattr(service, "_remote_task_payload", remote_payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            service._task_and_request_from_session,
            "https://devenv.example",
            job_id,
        )
        assert first_entered.wait(timeout=2)
        second = executor.submit(
            service._task_and_request_from_session,
            "https://devenv.example",
            job_id,
        )
        both_entered.wait(timeout=0.2)
        release.set()
        first_result = first.result(timeout=2)
        second_result = second.result(timeout=2)

    assert calls == 1
    assert first_result == second_result
    assert first_result is not second_result


def test_task_state_reports_bootstrap_files_as_initializing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")

    def post(url: str, *, json: dict[str, object], timeout) -> SimpleNamespace:
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "data": {
                    "status": "completed",
                    "exit_code": 0,
                    "output": __import__("json").dumps({"initializing": True}),
                }
            },
        )

    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        post,
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service._remote_task_payload("https://devenv.example", job_id)

    assert caught.value.code == "SKILL_TASK_INITIALIZING"
    assert caught.value.status_code == 409
    assert caught.value.retryable is True


def test_get_task_returns_the_live_session_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr(
        service,
        "_find_session",
        lambda tool_id, requested_job_id: {
            "instanceId": "session-1",
            "endpoint": "https://devenv.example",
            "expireAt": "2026-08-05T12:00:00Z",
        },
    )
    monkeypatch.setattr(
        service,
        "_task_and_request_from_session",
        lambda endpoint, requested_job_id: (
            {
                "jobId": requested_job_id,
                "operation": "create",
                "intent": "Create it",
                "revision": 1,
                "state": "running",
            },
            {
                "jobId": requested_job_id,
                "operation": "create",
                "intent": "Create it",
                "revision": 1,
            },
        ),
    )

    detail = service.get_task(job_id, "alice")

    assert detail["expiresAt"] == "2026-08-05T12:00:00Z"
    assert detail["toolId"] == "tool"
    assert detail["sessionId"] == "session-1"


def test_get_task_waits_for_snapshot_get_before_marking_recovery_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    snapshots = []
    snapshot_reads = []
    persisted: dict[str, object] = {}
    snapshot_statuses = iter(("Pending", "Ready"))

    class Tools:
        def create_session_snapshot(self, request):
            snapshots.append(request)
            return SimpleNamespace(snapshot_id="snapshot-1", status="Pending")

        def get_session_snapshot(self, request):
            snapshot_reads.append(request)
            return SimpleNamespace(
                snapshot=SimpleNamespace(
                    snapshot_id="snapshot-1",
                    session_id="session-1",
                    tool_id="tool",
                    status=next(snapshot_statuses),
                )
            )

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr(
        service,
        "_find_session",
        lambda tool_id, requested_job_id: {
            "instanceId": "session-1",
            "endpoint": "https://devenv.example",
            "expireAt": "2026-08-05T12:00:00Z",
        },
    )
    task = {
        "jobId": job_id,
        "operation": "create",
        "intent": "Create it",
        "revision": 2,
        "createdAt": 1,
    }

    def claim_snapshot(
        endpoint: str,
        requested_job_id: str,
        revision: int,
        request_token: str,
    ) -> tuple[bool, dict[str, object]]:
        del endpoint
        assert requested_job_id == job_id
        assert revision == 2
        if persisted:
            return False, dict(persisted)
        persisted.update(
            {
                "recoverySnapshotRevision": revision,
                "recoverySnapshotStatus": "requesting",
                "recoverySnapshotRequestedAt": int(time.time()),
                "recoverySnapshotRequestToken": request_token,
            }
        )
        return True, dict(persisted)

    def persist_snapshot(
        endpoint: str,
        requested_job_id: str,
        revision: int,
        request_token: str,
        *,
        snapshot_id: str,
        status: str,
    ) -> dict[str, object]:
        del endpoint
        assert requested_job_id == job_id
        assert revision == 2
        assert request_token == persisted["recoverySnapshotRequestToken"]
        persisted.update(
            {
                "recoverySnapshotId": snapshot_id,
                "recoverySnapshotStatus": status,
            }
        )
        return dict(persisted)

    def remote_command(
        endpoint: str,
        command: str,
        *,
        job_id: str = "",
    ) -> dict[str, object]:
        del job_id
        assert endpoint == "https://devenv.example"
        if "status.json" in command:
            return {
                "request": {**task, **persisted},
                "status": {"status": "succeeded", "stage": "packaging"},
            }
        return {**task, **persisted}

    monkeypatch.setattr(
        service,
        "_remote_command_json",
        remote_command,
    )
    monkeypatch.setattr(
        service,
        "_claim_recovery_snapshot",
        claim_snapshot,
        raising=False,
    )
    monkeypatch.setattr(
        service,
        "_persist_recovery_snapshot_state",
        persist_snapshot,
        raising=False,
    )

    pending = service.get_task(job_id, "alice")
    ready = service.get_task(job_id, "alice")

    assert "recoveryAvailable" not in pending
    assert pending["recoveryStatus"] == "pending"
    assert ready["recoveryAvailable"] is True
    assert ready["recoveryStatus"] == "ready"
    assert len(snapshots) == 1
    assert len(snapshot_reads) == 2
    assert snapshots[0].session_id == "session-1"
    assert snapshot_reads[0].snapshot_id == "snapshot-1"
    assert persisted["recoverySnapshotId"] == "snapshot-1"
    assert persisted["recoverySnapshotRevision"] == 2
    assert persisted["recoverySnapshotStatus"] == "ready"


@pytest.mark.parametrize(
    ("create_result", "expected_status"),
    [
        (requests.ReadTimeout("ambiguous snapshot response"), "unknown"),
        (SimpleNamespace(snapshot_id="", status="Pending"), "unknown"),
    ],
)
def test_snapshot_unknown_outcome_is_not_created_again_for_the_same_revision(
    monkeypatch: pytest.MonkeyPatch,
    create_result: object,
    expected_status: str,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    create_calls = 0
    persisted: dict[str, object] = {}

    class Tools:
        def create_session_snapshot(self, request):
            nonlocal create_calls
            del request
            create_calls += 1
            if isinstance(create_result, BaseException):
                raise create_result
            return create_result

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )
    task = {
        "jobId": job_id,
        "operation": "create",
        "intent": "Create it",
        "revision": 2,
        "createdAt": 1,
    }

    def claim_snapshot(
        endpoint: str,
        requested_job_id: str,
        revision: int,
        request_token: str,
    ) -> tuple[bool, dict[str, object]]:
        del endpoint, requested_job_id
        if persisted:
            return False, dict(persisted)
        persisted.update(
            {
                "recoverySnapshotRevision": revision,
                "recoverySnapshotStatus": "requesting",
                "recoverySnapshotRequestedAt": int(time.time()),
                "recoverySnapshotRequestToken": request_token,
            }
        )
        return True, dict(persisted)

    def persist_snapshot(
        endpoint: str,
        requested_job_id: str,
        revision: int,
        request_token: str,
        *,
        snapshot_id: str,
        status: str,
    ) -> dict[str, object]:
        del endpoint, requested_job_id, revision
        assert request_token == persisted["recoverySnapshotRequestToken"]
        persisted.update(
            {
                "recoverySnapshotId": snapshot_id,
                "recoverySnapshotStatus": status,
            }
        )
        return dict(persisted)

    monkeypatch.setattr(
        service, "_claim_recovery_snapshot", claim_snapshot, raising=False
    )
    monkeypatch.setattr(
        service,
        "_persist_recovery_snapshot_state",
        persist_snapshot,
        raising=False,
    )

    for _ in range(2):
        observed = dict(task)
        observed.update(persisted)
        available = service._ensure_recovery_snapshot(
            "tool",
            {
                "instanceId": "session-1",
                "endpoint": "https://devenv.example",
            },
            observed,
            request_data=observed,
        )
        assert available is None
        assert observed["recoverySnapshotStatus"] == expected_status

    assert create_calls == 1


def test_failed_snapshot_is_terminal_and_not_created_or_read_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    create_calls = 0
    get_calls = 0
    persisted: dict[str, object] = {}

    class Tools:
        def create_session_snapshot(self, request):
            nonlocal create_calls
            del request
            create_calls += 1
            return SimpleNamespace(snapshot_id="snapshot-1", status="Pending")

        def get_session_snapshot(self, request):
            nonlocal get_calls
            del request
            get_calls += 1
            return SimpleNamespace(
                snapshot=SimpleNamespace(
                    snapshot_id="snapshot-1",
                    session_id="session-1",
                    tool_id="tool",
                    status="Failed",
                    reason="snapshot capacity unavailable",
                )
            )

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )
    task = {
        "jobId": job_id,
        "operation": "create",
        "intent": "Create it",
        "revision": 2,
        "createdAt": 1,
    }

    def claim_snapshot(
        endpoint: str,
        requested_job_id: str,
        revision: int,
        request_token: str,
    ) -> tuple[bool, dict[str, object]]:
        del endpoint, requested_job_id
        if persisted:
            return False, dict(persisted)
        persisted.update(
            {
                "recoverySnapshotRevision": revision,
                "recoverySnapshotStatus": "requesting",
                "recoverySnapshotRequestedAt": int(time.time()),
                "recoverySnapshotRequestToken": request_token,
            }
        )
        return True, dict(persisted)

    def persist_snapshot(
        endpoint: str,
        requested_job_id: str,
        revision: int,
        request_token: str,
        *,
        snapshot_id: str,
        status: str,
    ) -> dict[str, object]:
        del endpoint, requested_job_id, revision
        assert request_token == persisted["recoverySnapshotRequestToken"]
        persisted.update(
            {
                "recoverySnapshotId": snapshot_id,
                "recoverySnapshotStatus": status,
            }
        )
        return dict(persisted)

    monkeypatch.setattr(service, "_claim_recovery_snapshot", claim_snapshot)
    monkeypatch.setattr(
        service,
        "_persist_recovery_snapshot_state",
        persist_snapshot,
    )

    for _ in range(2):
        observed = {**task, **persisted}
        available = service._ensure_recovery_snapshot(
            "tool",
            {
                "instanceId": "session-1",
                "endpoint": "https://devenv.example",
            },
            observed,
            request_data=observed,
        )
        assert available is False
        assert observed["recoverySnapshotStatus"] == "failed"

    assert create_calls == 1
    assert get_calls == 1


def test_snapshot_claim_is_reentrant_for_its_owner_and_exclusive_across_instances(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    job_dir = tmp_path / job_id
    job_dir.mkdir()
    request_path = job_dir / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "jobId": job_id,
                "operation": "create",
                "intent": "Create it",
                "revision": 2,
                "createdAt": 1,
            }
        ),
        encoding="utf-8",
    )
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(
        service,
        "_remote_dir",
        lambda requested_job_id: str(job_dir),
    )

    def execute_remote(
        endpoint: str,
        command: str,
        *,
        job_id: str = "",
    ) -> dict[str, object]:
        del endpoint, job_id
        completed = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return json.loads(completed.stdout)

    monkeypatch.setattr(service, "_remote_command_json", execute_remote)
    owner_token = "a" * 32
    competing_token = "b" * 32

    first_claim, _ = service._claim_recovery_snapshot(
        "https://devenv.example",
        job_id,
        2,
        owner_token,
    )
    replayed_claim, _ = service._claim_recovery_snapshot(
        "https://devenv.example",
        job_id,
        2,
        owner_token,
    )
    competing_claim, _ = service._claim_recovery_snapshot(
        "https://devenv.example",
        job_id,
        2,
        competing_token,
    )
    state = service._persist_recovery_snapshot_state(
        "https://devenv.example",
        job_id,
        2,
        owner_token,
        snapshot_id="snapshot-1",
        status="pending",
    )

    assert first_claim is True
    assert replayed_claim is True
    assert competing_claim is False
    assert state["recoverySnapshotId"] == "snapshot-1"
    assert state["recoverySnapshotStatus"] == "pending"
    stored = json.loads(request_path.read_text(encoding="utf-8"))
    assert stored["recoverySnapshotRequestToken"] == owner_token
    stored.pop("recoverySnapshotRequestToken")
    stored.pop("recoverySnapshotStatus")
    request_path.write_text(json.dumps(stored), encoding="utf-8")

    migrated = service._persist_recovery_snapshot_state(
        "https://devenv.example",
        job_id,
        2,
        "",
        snapshot_id="snapshot-1",
        status="ready",
    )

    assert migrated["recoverySnapshotStatus"] == "ready"


def test_pending_snapshot_timeout_stops_observation_without_another_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")

    class Tools:
        def create_session_snapshot(self, request):
            raise AssertionError("must not create a second snapshot")

        def get_session_snapshot(self, request):
            raise AssertionError("must stop polling an overdue snapshot")

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )
    task = {
        "jobId": job_id,
        "operation": "create",
        "intent": "Create it",
        "revision": 2,
        "createdAt": 1,
        "recoverySnapshotId": "snapshot-1",
        "recoverySnapshotRevision": 2,
        "recoverySnapshotStatus": "pending",
        "recoverySnapshotRequestedAt": int(time.time()) - 601,
        "recoverySnapshotRequestToken": "a" * 32,
    }

    def persist_snapshot(
        endpoint: str,
        requested_job_id: str,
        revision: int,
        request_token: str,
        *,
        snapshot_id: str,
        status: str,
    ) -> dict[str, object]:
        del endpoint
        assert requested_job_id == job_id
        assert revision == 2
        assert request_token == "a" * 32
        assert snapshot_id == "snapshot-1"
        assert status == "unknown"
        return {
            **task,
            "recoverySnapshotStatus": "unknown",
        }

    monkeypatch.setattr(
        service,
        "_persist_recovery_snapshot_state",
        persist_snapshot,
    )

    available = service._ensure_recovery_snapshot(
        "tool",
        {
            "instanceId": "session-1",
            "endpoint": "https://devenv.example",
        },
        task,
        request_data=task,
    )

    assert available is None
    assert task["recoverySnapshotStatus"] == "unknown"


@pytest.mark.parametrize(
    ("failure", "retryable"),
    [
        (requests.ConnectTimeout("temporary"), True),
        (ValueError("invalid launch response"), False),
    ],
)
def test_refine_only_marks_transient_idempotent_launch_failures_retryable(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    retryable: bool,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    session = {
        "instanceId": "session-1",
        "endpoint": "https://devenv.example",
        "expireAt": "2026-08-05T13:00:00Z",
    }
    monkeypatch.setattr(
        service,
        "_get_task_with_session",
        lambda requested_job_id, owner_id, **kwargs: (
            {
                "jobId": requested_job_id,
                "operation": "create",
                "intent": "Create release notes",
                "revision": 1,
                "state": "ready",
                "createdAt": 1,
            },
            session,
        ),
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.refine(
            job_id,
            "alice",
            RefineSkillTaskBody(
                intent="Add an error recovery section",
                expectedRevision=1,
            ),
        )

    assert caught.value.code == "SKILL_TASK_START_FAILED"
    assert caught.value.retryable is retryable


def test_refine_waits_until_the_current_recovery_snapshot_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr(
        service,
        "_get_task_with_session",
        lambda requested_job_id, owner_id, **kwargs: (
            {
                "jobId": requested_job_id,
                "operation": "create",
                "intent": "Create it",
                "revision": 2,
                "state": "ready",
                "recoveryStatus": "pending",
            },
            {
                "instanceId": "session-1",
                "endpoint": "https://devenv.example",
            },
        ),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.refine(
            job_id,
            "alice",
            RefineSkillTaskBody(
                intent="Change it",
                expectedRevision=2,
            ),
        )

    assert caught.value.code == "SKILL_TASK_RECOVERY_PENDING"
    assert caught.value.status_code == 409
    assert caught.value.retryable is True


def test_refine_resumes_an_expired_task_from_the_latest_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    resumed = []

    class Tools:
        def list_sessions(self, request):
            return SimpleNamespace(session_infos=[], next_token=None)

        def list_session_snapshots(self, request):
            return SimpleNamespace(
                snapshots=[
                    SimpleNamespace(
                        snapshot_id="snapshot-1",
                        status="Ready",
                        created_at="2026-08-05T10:00:00Z",
                    )
                ]
            )

        def resume_session_from_snapshot(self, request):
            resumed.append(request)
            return SimpleNamespace(session_id="session-resumed")

        def get_session(self, request):
            return SimpleNamespace(
                session_id="session-resumed",
                endpoint="https://resumed.example",
                status="Ready",
                expire_at="2026-08-05T13:00:00Z",
            )

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr(
        service,
        "_get_task_with_session",
        lambda requested_job_id, owner_id, **kwargs: (_ for _ in ()).throw(
            SkillWorkbenchError(
                "SKILL_TASK_EXPIRED",
                "DevEnv 已到期并自动释放",
                status_code=410,
            )
        ),
    )
    recovered_task = {
        "jobId": job_id,
        "operation": "create",
        "intent": "Create release notes",
        "revision": 3,
        "state": "cancelled",
        "activities": [],
    }
    monkeypatch.setattr(
        service,
        "_task_from_session",
        lambda endpoint, requested_job_id: dict(recovered_task),
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"status": "completed", "exit_code": 0}},
        ),
    )

    result = service.refine(
        job_id,
        "alice",
        RefineSkillTaskBody(
            intent="Add an error recovery section",
            expectedRevision=1,
        ),
    )

    assert result["state"] == "running"
    assert result["revision"] == 4
    assert result["recoveredFromSnapshot"] is True
    assert result["toolId"] == "tool"
    assert result["sessionId"] == "session-resumed"
    assert resumed[0].snapshot_id == "snapshot-1"
    assert resumed[0].create_new_instance is True
    assert resumed[0].ttl == 3600


def test_recovery_reuses_an_already_creating_resumed_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    session_reads = []

    class Tools:
        def list_sessions(self, request):
            return SimpleNamespace(
                session_infos=[
                    SimpleNamespace(
                        session_id="session-resumed",
                        user_session_id=job_id,
                        endpoint="",
                        status="Creating",
                        created_at="2099-08-05T12:00:00Z",
                        expire_at="2099-08-05T13:00:00Z",
                    )
                ],
                next_token=None,
            )

        def get_session(self, request):
            session_reads.append(request)
            return SimpleNamespace(
                session_id="session-resumed",
                endpoint="https://resumed.example",
                status="Ready",
                expire_at="2099-08-05T13:00:00Z",
            )

        def list_session_snapshots(self, request):
            raise AssertionError("must reconcile the creating Session first")

        def resume_session_from_snapshot(self, request):
            raise AssertionError("must not issue Resume twice")

    service = SkillWorkbenchService(
        tool_id="tool", tools_client_factory=lambda region: Tools()
    )

    session = service._resume_latest_snapshot("tool", job_id)

    assert session == {
        "instanceId": "session-resumed",
        "endpoint": "https://resumed.example",
        "expireAt": "2099-08-05T13:00:00Z",
    }
    assert len(session_reads) == 1
    assert session_reads[0].session_id == "session-resumed"


def test_refine_serializes_concurrent_expired_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    state_lock = threading.Lock()
    second_expired_read = threading.Event()
    start = threading.Barrier(3)
    state = {"active": False, "expiredReads": 0}
    resumed: list[str] = []
    launched: list[str] = []

    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")

    session = {
        "instanceId": "session-resumed",
        "endpoint": "https://resumed.example",
        "expireAt": "2026-08-05T13:00:00Z",
    }

    def get_task_with_session(
        requested_job_id: str,
        owner_id: str,
        **kwargs,
    ) -> tuple[dict[str, object], dict[str, str]]:
        with state_lock:
            if state["active"]:
                return (
                    {
                        "jobId": requested_job_id,
                        "operation": "create",
                        "intent": "Create release notes",
                        "revision": 4,
                        "state": "running",
                    },
                    session,
                )
            state["expiredReads"] += 1
            if state["expiredReads"] >= 2:
                second_expired_read.set()
        raise SkillWorkbenchError(
            "SKILL_TASK_EXPIRED",
            "DevEnv 已到期并自动释放",
            status_code=410,
        )

    def resume(tool_id: str, requested_job_id: str) -> dict[str, str]:
        second_expired_read.wait(timeout=0.2)
        with state_lock:
            state["active"] = True
            resumed.append(requested_job_id)
        return {
            "instanceId": "session-resumed",
            "endpoint": "https://resumed.example",
            "expireAt": "2026-08-05T13:00:00Z",
        }

    monkeypatch.setattr(service, "_get_task_with_session", get_task_with_session)
    monkeypatch.setattr(service, "_resume_latest_snapshot", resume)
    monkeypatch.setattr(
        service,
        "_task_from_session",
        lambda endpoint, requested_job_id: {
            "jobId": requested_job_id,
            "operation": "create",
            "intent": "Create release notes",
            "revision": 3,
            "state": "cancelled",
            "activities": [],
        },
    )

    def post(*args, **kwargs):
        launched.append("launch")
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"status": "completed", "exit_code": 0}},
        )

    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        post,
    )

    def refine() -> dict[str, object] | SkillWorkbenchError:
        start.wait()
        try:
            return service.refine(
                job_id,
                "alice",
                RefineSkillTaskBody(
                    intent="Add an error recovery section",
                    expectedRevision=1,
                ),
            )
        except SkillWorkbenchError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(refine) for _ in range(2)]
        start.wait()
        outcomes = [future.result(timeout=2) for future in futures]

    assert len(resumed) == 1
    assert len(launched) == 1
    assert (
        sum(
            isinstance(outcome, dict) and outcome.get("state") == "running"
            for outcome in outcomes
        )
        == 1
    )
    errors = [
        outcome for outcome in outcomes if isinstance(outcome, SkillWorkbenchError)
    ]
    assert [error.code for error in errors] == ["SKILL_TASK_NOT_READY"]


def test_resume_timeout_after_create_is_not_marked_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")

    class Tools:
        def list_sessions(self, request):
            return SimpleNamespace(session_infos=[], next_token=None)

        def list_session_snapshots(self, request):
            return SimpleNamespace(
                snapshots=[
                    SimpleNamespace(
                        snapshot_id="snapshot-1",
                        status="Ready",
                        created_at="2026-08-05T12:00:00Z",
                    )
                ],
                next_token=None,
            )

        def resume_session_from_snapshot(self, request):
            raise requests.ReadTimeout("ambiguous resume response")

    service = SkillWorkbenchService(
        tool_id="tool",
        tools_client_factory=lambda region: Tools(),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service._resume_latest_snapshot("tool", job_id)

    assert caught.value.code == "SKILL_TASK_RECOVERY_FAILED"
    assert caught.value.retryable is False


def test_stop_task_preserves_the_session_and_returns_cancelled_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    commands = []
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    session = {
        "instanceId": "session-1",
        "endpoint": "https://devenv.example",
        "expireAt": "2026-08-05T12:00:00Z",
    }
    monkeypatch.setattr(
        service,
        "_get_task_with_session",
        lambda requested_job_id, owner_id, **kwargs: (
            {
                "jobId": job_id,
                "operation": "create",
                "intent": "Create it",
                "revision": 2,
                "state": "running",
            },
            session,
        ),
    )

    def post(url, *, json, timeout):
        commands.append(json["command"])
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"data": {"status": "completed", "exit_code": 0}},
        )

    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        post,
    )
    monkeypatch.setattr(
        service,
        "_task_and_request_from_session",
        lambda endpoint, requested_job_id: (
            {
                "jobId": job_id,
                "operation": "create",
                "intent": "Create it",
                "revision": 2,
                "state": "cancelled",
                "activities": [],
            },
            {
                "jobId": job_id,
                "operation": "create",
                "intent": "Create it",
                "revision": 2,
            },
        ),
    )
    monkeypatch.setattr(
        service,
        "_ensure_recovery_snapshot",
        lambda *args, **kwargs: True,
    )

    result = service.stop(
        job_id,
        "alice",
        StopSkillTaskBody(expectedRevision=2),
    )

    assert result["state"] == "cancelled"
    assert "runner.pid" in commands[0]
    assert "os.killpg" in commands[0]


def test_stop_non_transient_failure_is_not_marked_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    session = {
        "instanceId": "session-1",
        "endpoint": "https://devenv.example",
        "expireAt": "2026-08-05T12:00:00Z",
    }
    monkeypatch.setattr(
        service,
        "_get_task_with_session",
        lambda requested_job_id, owner_id, **kwargs: (
            {
                "jobId": requested_job_id,
                "operation": "create",
                "intent": "Create it",
                "revision": 2,
                "state": "running",
            },
            session,
        ),
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("invalid stop request")
        ),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.stop(
            job_id,
            "alice",
            StopSkillTaskBody(expectedRevision=2),
        )

    assert caught.value.code == "SKILL_TASK_STOP_FAILED"
    assert caught.value.retryable is False


def test_stop_route_validates_the_revision_and_returns_the_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    job_id = SkillWorkbenchService._new_job_id("alice")
    captured: dict[str, object] = {}

    def stop(
        requested_job_id: str,
        owner_id: str,
        body: StopSkillTaskBody,
    ) -> dict[str, object]:
        captured.update(job_id=requested_job_id, owner_id=owner_id, body=body)
        return {
            "jobId": requested_job_id,
            "operation": "create",
            "intent": "Create it",
            "revision": body.expected_revision,
            "state": "cancelled",
            "stage": "cancelled",
            "activities": [],
            "files": [],
        }

    monkeypatch.setattr(service, "stop", stop)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/web/skill-workbench/tasks/{job_id}/stop",
            json={"expectedRevision": 2},
        )

    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"
    assert captured["job_id"] == job_id
    assert captured["owner_id"] == "alice"
    body = captured["body"]
    assert isinstance(body, StopSkillTaskBody)
    assert body.expected_revision == 2


def test_remote_status_timeout_is_retryable_and_preserves_user_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    attempts = 0

    def post(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise requests.Timeout("upstream timed out")

    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.post", post)
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    with pytest.raises(SkillWorkbenchError) as caught:
        service._remote_json("https://devenv.example", job_id, "status.json")

    assert attempts == 2
    assert caught.value.code == "SKILL_TASK_SYNC_FAILED"
    assert caught.value.retryable is True
    assert "已保留当前会话" in str(caught.value)


def test_remote_status_retries_timeout_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    attempts = 0

    def post(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.ConnectTimeout("temporary connect timeout")
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "data": {
                    "status": "completed",
                    "exit_code": 0,
                    "output": json.dumps({"status": "running"}),
                }
            },
        )

    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.post", post)
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    assert service._remote_command_json(
        "https://devenv.example?credential=must-not-log",
        "echo user-intent-must-not-log",
    ) == {"status": "running"}
    assert service._remote_json(
        "https://devenv.example",
        job_id,
        "status.json",
    ) == {"status": "running"}
    assert attempts == 3
    assert "must-not-log" not in caplog.text


def test_remote_status_reads_the_complete_output_when_inline_output_is_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    complete = json.dumps(
        {
            "request": {"jobId": job_id},
            "status": {
                "status": "succeeded",
                "activities": [{"id": f"activity-{index}"} for index in range(80)],
            },
        }
    )
    reads: list[tuple[str, dict[str, str], tuple[int, int]]] = []

    def post(*args, **kwargs):
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "data": {
                    "status": "completed",
                    "exit_code": 0,
                    "output": complete[:100]
                    + "\n... output truncated ...\n"
                    + complete[-100:],
                    "full_output_file_path": (
                        "/tmp/aio-sandbox-truncated-output/shell/state.log"
                    ),
                }
            },
        )

    def get(url: str, *, params: dict[str, str], timeout: tuple[int, int]):
        reads.append((url, params, timeout))
        return SimpleNamespace(status_code=200, content=complete.encode())

    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.post", post)
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.get", get)

    assert service._remote_command_json(
        "https://devenv.example?credential=secret",
        "read state",
        job_id=job_id,
    ) == json.loads(complete)
    assert reads == [
        (
            "https://devenv.example/v1/file/download?credential=secret",
            {
                "path": "/tmp/aio-sandbox-truncated-output/shell/state.log",
                "change_policy": "abort",
            },
            (10, 30),
        )
    ]


def test_remote_status_retries_complete_output_transport_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    reads = 0

    def post(*args, **kwargs):
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "data": {
                    "status": "completed",
                    "exit_code": 0,
                    "output": """'{"status":"corrupted"}'""",
                    "full_output_file_path": "/tmp/complete-state.log",
                }
            },
        )

    def get(*args, **kwargs):
        nonlocal reads
        reads += 1
        if reads == 1:
            raise requests.ConnectTimeout("temporary connect timeout")
        return SimpleNamespace(
            status_code=200,
            content=b'{"status":"running"}',
        )

    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.post", post)
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.get", get)
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    assert service._remote_command_json(
        "https://devenv.example",
        "read state",
        job_id=job_id,
    ) == {"status": "running"}
    assert reads == 2


def test_remote_status_does_not_retry_non_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    attempts = 0

    def post(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid request")

    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.post", post)

    with pytest.raises(SkillWorkbenchError) as caught:
        service._remote_json("https://devenv.example", job_id, "status.json")

    assert attempts == 1
    assert caught.value.code == "SKILL_TASK_SYNC_FAILED"
    assert caught.value.retryable is False


def test_remote_file_write_retries_transient_failure_idempotently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def post(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.ConnectTimeout("temporary")
        return SimpleNamespace(status_code=200)

    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.post", post)
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    service._upload_file(
        "https://devenv.example",
        "/home/gem/task/request.json",
        b"{}",
        media_type="application/json",
    )

    assert attempts == 2


def test_remote_file_write_rejects_non_transient_response_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def post(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return SimpleNamespace(status_code=403)

    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.post", post)

    with pytest.raises(SkillWorkbenchError) as caught:
        service._upload_file(
            "https://devenv.example",
            "/home/gem/task/request.json",
            b"{}",
            media_type="application/json",
        )

    assert attempts == 1
    assert caught.value.code == "SKILL_REMOTE_WRITE_FAILED"
    assert caught.value.retryable is False


def test_bootstrap_is_idempotent_for_one_running_revision(tmp_path) -> None:
    job = tmp_path / "job"
    runner = (
        "from pathlib import Path\n"
        "import os, time\n"
        "job = Path(os.environ['VEADK_SKILL_JOB_DIR'])\n"
        "counter = job / 'launch-count'\n"
        "counter.write_text(str(int(counter.read_text() or '0') + 1) "
        "if counter.exists() else '1')\n"
        "time.sleep(30)\n"
    )
    request = {
        "jobId": SkillWorkbenchService._new_job_id("alice"),
        "operation": "create",
        "intent": "Create it",
        "revision": 1,
        "createdAt": 1,
    }
    env = {
        **os.environ,
        "VEADK_SKILL_JOB_DIR": str(job),
        "VEADK_SKILL_PROMPT_B64": __import__("base64").b64encode(b"prompt").decode(),
        "VEADK_SKILL_RUNNER_B64": __import__("base64")
        .b64encode(runner.encode())
        .decode(),
        "VEADK_SKILL_REQUEST_B64": __import__("base64")
        .b64encode(json.dumps(request).encode())
        .decode(),
    }

    first = subprocess.run(
        ["bash", "-c", _BOOTSTRAP],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    second = subprocess.run(
        ["bash", "-c", _BOOTSTRAP],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    try:
        assert first.returncode == 0, first.stderr
        assert second.returncode == 0, second.stderr
        deadline = __import__("time").monotonic() + 2
        while (
            not (job / "launch-count").exists()
            and __import__("time").monotonic() < deadline
        ):
            __import__("time").sleep(0.02)
        assert (job / "launch-count").read_text() == "1"
    finally:
        if (job / "runner.pid").exists():
            pid = int((job / "runner.pid").read_text())
            try:
                os.killpg(os.getpgid(pid), 15)
            except ProcessLookupError:
                pass


def test_task_with_current_revision_publication_reopens_as_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = SkillWorkbenchService._new_job_id("alice")
    service = SkillWorkbenchService(tool_id="tool")
    payloads = {
        "request.json": {
            "jobId": job_id,
            "operation": "create",
            "intent": "Create actionable incident summaries",
            "revision": 2,
            "createdAt": 1,
            "publication": {
                "revision": 2,
                "skillId": "skill-1",
                "version": "3",
                "skillSpaceIds": ["space-1"],
                "disposition": "create-new",
                "region": "cn-beijing",
                "projectName": "default",
            },
        },
        "status.json": {"status": "succeeded", "stage": "packaging"},
    }
    monkeypatch.setattr(
        service,
        "_remote_task_payload",
        lambda endpoint, requested_job_id: (
            payloads["request.json"],
            payloads["status.json"],
        ),
    )

    detail = service._task_from_session("endpoint", job_id)

    assert detail["state"] == "published"
    assert service._task_summary(detail)["state"] == "published"


def _session(
    job_id: str,
    owner: str,
    endpoint: str,
    *,
    status: str = "Ready",
    expire_at: str = "2099-01-01T00:00:00Z",
    created_at: str = "2026-01-01T00:00:00Z",
) -> SimpleNamespace:
    return SimpleNamespace(
        session_id=f"session-{job_id}",
        user_session_id=job_id,
        endpoint=endpoint,
        status=status,
        expire_at=expire_at,
        created_at=created_at,
        metadata=[{"Key": "Username", "Value": owner}],
    )


def test_upload_source_is_allowed_only_for_optimization() -> None:
    service = SkillWorkbenchService(tool_id="tool")
    body = CreateSkillTaskBody(operation="create", intent="Build a Skill")

    with pytest.raises(SkillWorkbenchError, match="仅可作为优化来源") as caught:
        service.create_task(body, "alice", "Alice", uploaded_archive=skill_zip())

    assert caught.value.status_code == 422


def test_publish_update_requires_trusted_center_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(
        service,
        "_get_task_with_session",
        lambda job_id, owner_id: (
            {
                "jobId": job_id,
                "state": "ready",
                "revision": 1,
                "source": {"kind": "upload", "name": "release-notes"},
            },
            {"instanceId": "session-1", "endpoint": "https://devenv.example"},
        ),
    )
    body = PublishSkillTaskBody(
        disposition="update-source",
        expectedRevision=1,
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.publish(service._new_job_id("alice"), "alice", body)

    assert caught.value.code == "SKILL_UPDATE_NOT_ALLOWED"
    assert caught.value.status_code == 409


def test_publish_rejects_stale_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(
        service,
        "_get_task_with_session",
        lambda job_id, owner_id: (
            {
                "jobId": job_id,
                "state": "ready",
                "revision": 3,
                "source": None,
            },
            {"instanceId": "session-1", "endpoint": "https://devenv.example"},
        ),
    )
    body = PublishSkillTaskBody(
        disposition="create-new",
        expectedRevision=2,
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.publish(service._new_job_id("alice"), "alice", body)

    assert caught.value.code == "SKILL_TASK_REVISION_CONFLICT"


def test_publish_reuses_one_authoritative_devenv_state_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentkit.toolkit.cli import cli_skills_workflow
    from agentkit.toolkit.config import GlobalConfigManager

    job_id = SkillWorkbenchService._new_job_id("alice")
    session = {
        "instanceId": "session-1",
        "endpoint": "https://devenv.example",
        "expireAt": "2099-01-01T00:00:00Z",
    }
    calls = {"find_session": 0, "read_state": 0}
    archive_content = skill_zip()
    archive_sha256 = __import__("hashlib").sha256(archive_content).hexdigest()
    downloaded_paths: list[str] = []

    class Skills:
        def create_skill(self, request):
            return SimpleNamespace(id="skill-1")

    service = SkillWorkbenchService(
        tool_id="tool",
        skills_client_factory=lambda region: Skills(),
    )
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")

    def find_session(tool_id: str, requested_job_id: str) -> dict[str, str]:
        calls["find_session"] += 1
        assert tool_id == "tool"
        assert requested_job_id == job_id
        return session

    def remote_task_payload(endpoint: str, requested_job_id: str):
        calls["read_state"] += 1
        assert endpoint == session["endpoint"]
        assert requested_job_id == job_id
        return (
            {
                "jobId": job_id,
                "operation": "create",
                "intent": "Create release notes",
                "revision": 1,
                "createdAt": 1,
            },
            {
                "status": "succeeded",
                "stage": "packaging",
                "artifact": {
                    "revision": 1,
                    "path": "artifacts/revision-1.zip",
                    "sha256": archive_sha256,
                    "size": len(archive_content),
                },
            },
        )

    monkeypatch.setattr(service, "_find_session", find_session)
    monkeypatch.setattr(service, "_remote_task_payload", remote_task_payload)
    monkeypatch.setattr(
        service, "_ensure_recovery_snapshot", lambda *args, **kwargs: False
    )

    def get_archive(*args, **kwargs):
        downloaded_paths.append(kwargs["params"]["path"])
        return SimpleNamespace(status_code=200, content=archive_content)

    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.get", get_archive)
    monkeypatch.setattr(
        cli_skills_workflow,
        "_ensure_bucket_ready",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        cli_skills_workflow,
        "_make_content_hashed_zip_copy",
        lambda archive_path, name, directory: archive_path,
    )
    monkeypatch.setattr(
        cli_skills_workflow,
        "_tos_upload",
        lambda *args, **kwargs: "tos://bucket/release-notes.zip",
    )
    monkeypatch.setattr(
        cli_skills_workflow,
        "_wait_for_running_version",
        lambda **kwargs: SimpleNamespace(version="1"),
    )
    monkeypatch.setattr(
        GlobalConfigManager,
        "load",
        lambda self: SimpleNamespace(
            tos=SimpleNamespace(bucket="bucket", prefix="agentkit/skills")
        ),
    )
    monkeypatch.setattr(service, "_persist_publication", lambda *args, **kwargs: None)

    result = service.publish(
        job_id,
        "alice",
        PublishSkillTaskBody(
            disposition="create-new",
            expectedRevision=1,
            expectedArtifactSha256=archive_sha256,
        ),
    )

    assert result["skillId"] == "skill-1"
    assert calls == {"find_session": 1, "read_state": 1}
    assert downloaded_paths == [
        f"{service._remote_dir(job_id)}/artifacts/revision-1.zip"
    ]


def test_preview_materializes_one_legacy_archive_for_the_requested_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    content = skill_zip()
    digest = __import__("hashlib").sha256(content).hexdigest()
    responses = iter(
        [
            SimpleNamespace(status_code=404, content=b""),
            SimpleNamespace(status_code=200, content=content),
        ]
    )
    paths: list[str] = []
    materialized: list[tuple[str, str, int]] = []
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr(
        service,
        "_find_session",
        lambda tool_id, requested_job_id: {
            "instanceId": "session-1",
            "endpoint": "https://devenv.example",
        },
    )

    def get_archive(*args, **kwargs):
        paths.append(kwargs["params"]["path"])
        return next(responses)

    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.get", get_archive)

    def materialize(endpoint: str, requested_job_id: str, revision: int) -> str:
        materialized.append((endpoint, requested_job_id, revision))
        return digest

    monkeypatch.setattr(
        service,
        "_materialize_legacy_revision_artifact",
        materialize,
        raising=False,
    )

    artifact = service.artifact(job_id, "alice", expected_revision=2)

    assert artifact["jobId"] == job_id
    assert artifact["revision"] == 2
    assert artifact["sha256"] == digest
    assert materialized == [("https://devenv.example", job_id, 2)]
    expected_path = f"{service._remote_dir(job_id)}/artifacts/revision-2.zip"
    assert paths == [expected_path, expected_path]


def test_legacy_materialization_is_atomic_and_keeps_the_first_revision(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    job = tmp_path / "job"
    job.mkdir()
    first = skill_zip(description="First accepted artifact.")
    second = skill_zip(description="Later mutable legacy artifact.")
    (job / "request.json").write_text(
        json.dumps({"revision": 4}),
        encoding="utf-8",
    )
    (job / "status.json").write_text(
        json.dumps({"status": "succeeded", "stage": "completed"}),
        encoding="utf-8",
    )
    (job / "skill.zip").write_bytes(first)
    monkeypatch.setattr(service, "_remote_dir", lambda requested_job_id: str(job))

    def execute(endpoint: str, command: str, *, job_id: str = ""):
        completed = subprocess.run(
            ["bash", "-c", command],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return json.loads(completed.stdout)

    monkeypatch.setattr(service, "_remote_command_json", execute)

    first_digest = service._materialize_legacy_revision_artifact(
        "https://devenv.example",
        job_id,
        4,
    )
    (job / "skill.zip").write_bytes(second)
    second_digest = service._materialize_legacy_revision_artifact(
        "https://devenv.example",
        job_id,
        4,
    )

    revision_archive = job / "artifacts" / "revision-4.zip"
    assert revision_archive.read_bytes() == first
    assert first_digest == __import__("hashlib").sha256(first).hexdigest()
    assert second_digest == first_digest
    assert not list((job / "artifacts").glob("*.tmp"))


def test_artifact_download_retries_a_file_change_conflict_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    content = skill_zip()
    responses = iter(
        [
            SimpleNamespace(status_code=409, content=b""),
            SimpleNamespace(status_code=200, content=content),
        ]
    )
    attempts = 0

    def get_archive(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return next(responses)

    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.get", get_archive)
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    archive = service._download_archive_from_session(
        job_id,
        {"endpoint": "https://devenv.example", "instanceId": "session-1"},
        revision=1,
    )

    assert archive.content == content
    assert attempts == 2


def test_artifact_download_reports_an_exhausted_conflict_without_saying_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    attempts = 0

    def get_archive(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return SimpleNamespace(status_code=409, content=b"")

    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.requests.get", get_archive)
    monkeypatch.setattr("veadk.cli.frontend_skill_workbench.time.sleep", lambda _: None)

    with pytest.raises(SkillWorkbenchError) as caught:
        service._download_archive_from_session(
            job_id,
            {"endpoint": "https://devenv.example", "instanceId": "session-1"},
            revision=1,
        )

    assert attempts == 3
    assert caught.value.code == "SKILL_ARTIFACT_DOWNLOAD_CONFLICT"
    assert caught.value.retryable is True
    assert "尚未准备完成" not in str(caught.value)


def test_artifact_download_rejects_a_preview_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    content = skill_zip()
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200, content=content),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service._download_archive_from_session(
            service._new_job_id("alice"),
            {"endpoint": "https://devenv.example", "instanceId": "session-1"},
            revision=1,
            expected_sha256="0" * 64,
        )

    assert caught.value.code == "SKILL_ARTIFACT_REVISION_CONFLICT"
    assert caught.value.retryable is False


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (requests.ConnectTimeout("temporary"), False),
        (ValueError("private invalid configuration"), False),
    ],
)
def test_publish_wraps_dependency_failures_without_blind_retry(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    retryable: bool,
) -> None:
    calls = 0

    def publish_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise error

    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(service, "_publish_once", publish_once)

    with pytest.raises(SkillWorkbenchError) as caught:
        service.publish(
            service._new_job_id("alice"),
            "alice",
            PublishSkillTaskBody(
                disposition="create-new",
                expectedRevision=1,
            ),
        )

    assert calls == 1
    assert caught.value.code == "SKILL_PUBLISH_FAILED"
    assert caught.value.status_code == 502
    assert caught.value.retryable is retryable
    assert "private invalid configuration" not in caplog.text


def test_publish_does_not_expose_retryable_after_an_unknown_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(
        service,
        "_publish_once",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SkillWorkbenchError(
                "SKILL_REMOTE_WRITE_FAILED",
                "写入 Skill 会话数据失败",
                status_code=502,
                retryable=True,
            )
        ),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.publish(
            service._new_job_id("alice"),
            "alice",
            PublishSkillTaskBody(
                disposition="create-new",
                expectedRevision=1,
            ),
        )

    assert caught.value.code == "SKILL_PUBLISH_FAILED"
    assert caught.value.retryable is False
    assert str(caught.value) == (
        "发布 Skill 失败，无法确认本次发布结果，请刷新 Skill 中心确认。"
    )


def test_publish_preserves_a_retryable_preflight_artifact_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(
        service,
        "_publish_once",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SkillWorkbenchError(
                "SKILL_ARTIFACT_DOWNLOAD_CONFLICT",
                "Skill 产物传输期间发生文件冲突，请稍后重新读取。",
                status_code=502,
                retryable=True,
            )
        ),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.publish(
            service._new_job_id("alice"),
            "alice",
            PublishSkillTaskBody(
                disposition="create-new",
                expectedRevision=1,
            ),
        )

    assert caught.value.code == "SKILL_ARTIFACT_DOWNLOAD_CONFLICT"
    assert caught.value.retryable is True


def test_publish_reuses_the_persisted_result_for_the_same_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    result = {
        "skillId": "skill-1",
        "version": "2",
        "skillSpaceIds": ["space-1"],
        "disposition": "create-new",
        "region": "cn-beijing",
        "projectName": "default",
    }
    monkeypatch.setattr(
        service,
        "_get_task_with_session",
        lambda job_id, owner_id: (
            {
                "jobId": job_id,
                "state": "published",
                "revision": 3,
                "source": None,
                "publication": {"revision": 3, **result},
            },
            {"instanceId": "session-1", "endpoint": "https://devenv.example"},
        ),
    )
    monkeypatch.setattr(
        service,
        "download",
        lambda *args, **kwargs: pytest.fail(
            "an idempotent retry must have no side effects"
        ),
    )

    actual = service.publish(
        service._new_job_id("alice"),
        "alice",
        PublishSkillTaskBody(
            disposition="create-new",
            expectedRevision=3,
            skillSpaceIds=["a-different-current-selection"],
        ),
    )

    assert actual == result


def test_publish_serializes_concurrent_requests_for_the_same_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    body = PublishSkillTaskBody(
        disposition="create-new",
        expectedRevision=3,
        skillSpaceIds=["space-1"],
    )
    result = {
        "skillId": "skill-1",
        "version": "2",
        "skillSpaceIds": ["space-1"],
        "disposition": "create-new",
        "region": "cn-beijing",
        "projectName": "default",
    }
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    publication: dict[str, object] | None = None
    calls = 0
    side_effects = 0

    def publish_once(requested_job_id, owner_id, requested_body, report_progress):
        nonlocal calls, publication, side_effects
        assert requested_job_id == job_id
        assert owner_id == "alice"
        assert requested_body == body
        calls += 1
        if publication is None:
            first_entered.set()
            assert release_first.wait(timeout=2)
            side_effects += 1
            publication = result
        else:
            second_entered.set()
        return publication

    monkeypatch.setattr(service, "_publish_once", publish_once)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.publish, job_id, "alice", body)
        assert first_entered.wait(timeout=2)
        second = pool.submit(service.publish, job_id, "alice", body)
        assert not second_entered.wait(timeout=0.1)
        release_first.set()

        assert first.result(timeout=2) == result
        assert second.result(timeout=2) == result

    assert calls == 2
    assert side_effects == 1
    assert second_entered.is_set()


def test_publish_rejects_a_different_disposition_after_revision_is_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    monkeypatch.setattr(
        service,
        "_get_task_with_session",
        lambda job_id, owner_id: (
            {
                "jobId": job_id,
                "state": "published",
                "revision": 3,
                "source": {"kind": "skill-center", "skillId": "source-1"},
                "publication": {
                    "revision": 3,
                    "skillId": "source-1",
                    "version": "4",
                    "skillSpaceIds": ["space-1"],
                    "disposition": "update-source",
                    "region": "cn-beijing",
                    "projectName": "default",
                },
            },
            {"instanceId": "session-1", "endpoint": "https://devenv.example"},
        ),
    )

    with pytest.raises(SkillWorkbenchError) as caught:
        service.publish(
            service._new_job_id("alice"),
            "alice",
            PublishSkillTaskBody(
                disposition="create-new",
                expectedRevision=3,
                skillSpaceIds=["space-1"],
            ),
        )

    assert caught.value.code == "SKILL_ALREADY_PUBLISHED"
    assert caught.value.status_code == 409


def test_persist_publication_writes_an_owner_bound_sidecar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = service._new_job_id("alice")
    uploaded: dict[str, object] = {}
    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")
    monkeypatch.setattr(
        service,
        "_find_session",
        lambda tool_id, requested_job_id: {
            "endpoint": "https://devenv.example",
            "instanceId": "session-1",
        },
    )

    def upload(endpoint, path, content, *, media_type="application/zip"):
        uploaded.update(
            endpoint=endpoint,
            path=path,
            body=json.loads(content),
            media_type=media_type,
        )

    monkeypatch.setattr(service, "_upload_file", upload)
    result = {
        "skillId": "skill-1",
        "version": "3",
        "skillSpaceIds": ["space-1"],
        "disposition": "create-new",
        "region": "cn-beijing",
        "projectName": "default",
    }

    service._persist_publication(job_id, "alice", 2, result)

    assert uploaded["endpoint"] == "https://devenv.example"
    assert uploaded["path"] == f"{service._remote_dir(job_id)}/publication.json"
    assert uploaded["media_type"] == "application/json"
    uploaded_body = uploaded["body"]
    assert isinstance(uploaded_body, dict)
    assert uploaded_body == {"revision": 2, **result}


def test_upload_route_accepts_a_valid_skill_zip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    captured: dict[str, object] = {}

    def create_task(body, owner_id, creator_name, *, uploaded_archive=None):
        captured.update(
            body=body,
            owner_id=owner_id,
            creator_name=creator_name,
            uploaded_archive=uploaded_archive,
        )
        return {
            "jobId": SkillWorkbenchService._new_job_id(owner_id),
            "operation": body.operation,
            "intent": body.intent,
            "revision": 1,
            "state": "running",
            "stage": "generating",
            "activities": [],
            "files": [],
        }

    monkeypatch.setattr(service, "create_task", create_task)
    archive = skill_zip(extra={"references/checklist.md": "# Checklist\n"})

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/web/skill-workbench/tasks/from-upload",
            params={"intent": "Improve error guidance"},
            content=archive,
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == 200
    assert captured["owner_id"] == "alice"
    assert captured["creator_name"] == "Alice"
    assert captured["uploaded_archive"] == archive
    body = captured["body"]
    assert isinstance(body, CreateSkillTaskBody)
    assert body.operation == "optimize"
    assert body.source is None


def test_upload_route_accepts_archive_at_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    content = b"x" * (20 * 1024 * 1024)
    captured: dict[str, object] = {}

    def create_task(body, owner_id, creator_name, *, uploaded_archive=None):
        captured["uploaded_archive"] = uploaded_archive
        return {
            "jobId": SkillWorkbenchService._new_job_id(owner_id),
            "operation": body.operation,
            "intent": body.intent,
            "revision": 1,
            "state": "running",
            "stage": "generating",
            "activities": [],
            "files": [],
        }

    monkeypatch.setattr(service, "create_task", create_task)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/web/skill-workbench/tasks/from-upload",
            params={"intent": "Improve error guidance"},
            content=content,
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == 200
    assert captured["uploaded_archive"] == content


@pytest.mark.parametrize(
    ("intent", "content", "status_code", "error_code"),
    [
        (" ", b"not-a-zip", 422, "SKILL_INTENT_REQUIRED"),
        (
            "Improve error guidance",
            b"x" * (20 * 1024 * 1024 + 1),
            413,
            "SKILL_ARCHIVE_TOO_LARGE",
        ),
    ],
    ids=["blank-intent", "oversized-archive"],
)
def test_upload_route_rejects_invalid_input_before_starting_a_task(
    monkeypatch: pytest.MonkeyPatch,
    intent: str,
    content: bytes,
    status_code: int,
    error_code: str,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    monkeypatch.setattr(
        service,
        "create_task",
        lambda *args, **kwargs: pytest.fail("invalid uploads must not start a task"),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/web/skill-workbench/tasks/from-upload",
            params={"intent": intent},
            content=content,
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == error_code


def test_upload_route_rejects_chunked_content_above_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    monkeypatch.setattr(
        service,
        "create_task",
        lambda *args, **kwargs: pytest.fail("oversized uploads must not start a task"),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/web/skill-workbench/tasks/from-upload",
            params={"intent": "Improve error guidance"},
            content=iter([b"x" * (20 * 1024 * 1024), b"x"]),
            headers={"content-type": "application/zip"},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == {
        "code": "SKILL_ARCHIVE_TOO_LARGE",
        "message": "Skill ZIP 不能超过 20 MiB",
        "retryable": False,
    }


@pytest.mark.parametrize(
    ("headers", "status_code", "error_code"),
    [
        (
            {"content-type": "application/zip", "content-length": "-1"},
            400,
            "SKILL_CONTENT_LENGTH_INVALID",
        ),
        (
            {"content-type": "application/zip", "content-length": "invalid"},
            400,
            "SKILL_CONTENT_LENGTH_INVALID",
        ),
        (
            {"content-type": "text/plain"},
            415,
            "SKILL_CONTENT_TYPE_INVALID",
        ),
    ],
    ids=["negative-length", "invalid-length", "wrong-media-type"],
)
def test_upload_route_rejects_invalid_transport_metadata_before_starting_task(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    status_code: int,
    error_code: str,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    monkeypatch.setattr(
        service,
        "create_task",
        lambda *args, **kwargs: pytest.fail(
            "invalid transport metadata must not start a task"
        ),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/web/skill-workbench/tasks/from-upload",
            params={"intent": "Improve error guidance"},
            content=b"not-used",
            headers=headers,
        )

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == error_code


def test_list_route_returns_bounded_error_and_logs_request_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    monkeypatch.setattr(
        service,
        "list_tasks",
        lambda owner_id, exclude_job_id=None: (_ for _ in ()).throw(
            RuntimeError("private dependency response")
        ),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/web/skill-workbench/tasks",
            headers={"x-request-id": "request-123"},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "code": "SKILL_WORKBENCH_INTERNAL",
        "message": "Skill 工作台服务异常，请稍后重试。",
        "retryable": False,
    }
    assert "operation=list_tasks" in caplog.text
    assert "request_id=request-123" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "private dependency response" not in caplog.text


def test_list_route_excludes_the_task_already_polled_by_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    active_job_id = SkillWorkbenchService._new_job_id("alice")
    captured: dict[str, object] = {}

    def list_tasks(owner_id, exclude_job_id=None):
        captured["owner_id"] = owner_id
        captured["exclude_job_id"] = exclude_job_id
        return {"tasks": []}

    monkeypatch.setattr(service, "list_tasks", list_tasks)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/web/skill-workbench/tasks",
            params={"exclude_job_id": active_job_id},
        )

    assert response.status_code == 200
    assert captured == {
        "owner_id": "alice",
        "exclude_job_id": active_job_id,
    }


def test_artifact_returns_every_validated_nested_text_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    content = skill_zip(
        extra={
            "references/checklist.md": "# Checklist\n",
            "scripts/render.py": "print('ready')\n",
        },
        member_prefix="./",
    )
    monkeypatch.setattr(
        service,
        "_download_archive",
        lambda job_id, owner_id, **kwargs: validate_skill_archive(content),
    )
    job_id = SkillWorkbenchService._new_job_id("alice")

    artifact = service.artifact(
        job_id,
        "alice",
        expected_revision=3,
    )

    assert artifact == {
        "jobId": job_id,
        "revision": 3,
        "sha256": __import__("hashlib").sha256(content).hexdigest(),
        "name": "release-notes",
        "description": "Create concise release notes.",
        "files": [
            {
                "path": "SKILL.md",
                "size": len(
                    (
                        b"---\n"
                        b"name: release-notes\n"
                        b"description: Create concise release notes.\n"
                        b"---\n\n"
                        b"# Instructions\n"
                    )
                ),
                "content": (
                    "---\n"
                    "name: release-notes\n"
                    "description: Create concise release notes.\n"
                    "---\n\n"
                    "# Instructions\n"
                ),
            },
            {
                "path": "references/checklist.md",
                "size": len(b"# Checklist\n"),
                "content": "# Checklist\n",
            },
            {
                "path": "scripts/render.py",
                "size": len(b"print('ready')\n"),
                "content": "print('ready')\n",
            },
        ],
    }


def test_artifact_handoff_does_not_resynchronize_ready_task_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SkillWorkbenchService(tool_id="tool")
    job_id = SkillWorkbenchService._new_job_id("alice")
    state_reads = 0
    session_lookups = 0

    monkeypatch.setattr(service, "_validated_tool_id", lambda: "tool")

    def find_session(tool_id: str, requested_job_id: str) -> dict[str, str]:
        nonlocal session_lookups
        session_lookups += 1
        assert tool_id == "tool"
        assert requested_job_id == job_id
        return {
            "instanceId": "session-1",
            "endpoint": "https://devenv.example",
            "expireAt": "2099-01-01T00:00:00Z",
        }

    def read_state(endpoint: str, requested_job_id: str):
        nonlocal state_reads
        state_reads += 1
        raise AssertionError("artifact handoff must not reread task state")

    monkeypatch.setattr(service, "_find_session", find_session)
    monkeypatch.setattr(service, "_task_and_request_from_session", read_state)
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_workbench.requests.get",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            content=skill_zip(),
        ),
    )

    artifact = service.artifact(job_id, "alice", expected_revision=1)

    assert artifact["name"] == "release-notes"
    assert artifact["revision"] == 1
    assert session_lookups == 1
    assert state_reads == 0


def test_artifact_route_forwards_the_expected_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    job_id = SkillWorkbenchService._new_job_id("alice")
    captured: dict[str, object] = {}

    def artifact(
        requested_job_id: str,
        owner_id: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, object]:
        captured.update(
            job_id=requested_job_id,
            owner_id=owner_id,
            expected_revision=expected_revision,
        )
        return {
            "jobId": requested_job_id,
            "revision": expected_revision,
            "sha256": "a" * 64,
            "name": "release-notes",
            "description": "Release notes.",
            "files": [],
        }

    monkeypatch.setattr(service, "artifact", artifact)

    with TestClient(app) as client:
        response = client.get(
            f"/web/skill-workbench/tasks/{job_id}/artifact",
            params={"expected_revision": 7},
        )

    assert response.status_code == 200
    assert response.json()["revision"] == 7
    assert captured == {
        "job_id": job_id,
        "owner_id": "alice",
        "expected_revision": 7,
    }


def test_download_route_rejects_an_invalid_expected_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    monkeypatch.setattr(
        service,
        "download",
        lambda *args, **kwargs: pytest.fail(
            "invalid artifact identity must fail at the HTTP boundary"
        ),
    )
    job_id = SkillWorkbenchService._new_job_id("alice")

    with TestClient(app) as client:
        response = client.get(
            f"/web/skill-workbench/tasks/{job_id}/download",
            params={"expected_revision": 1, "expected_sha256": "not-a-digest"},
        )

    assert response.status_code == 422


def test_publish_stream_reports_progress_and_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    job_id = SkillWorkbenchService._new_job_id("alice")

    def publish(requested_job_id, owner_id, body, report_progress=None):
        assert requested_job_id == job_id
        assert owner_id == "alice"
        assert body.region == "cn-shanghai"
        assert report_progress is not None
        report_progress(
            {
                "phase": "uploading",
                "message": "正在上传 Skill 包",
            }
        )
        report_progress(
            {
                "phase": "activating",
                "message": "正在等待版本生效",
            }
        )
        return {
            "skillId": "skill-1",
            "version": "2",
            "skillSpaceIds": ["space-1"],
            "disposition": "create-new",
            "region": "cn-shanghai",
            "projectName": "default",
        }

    monkeypatch.setattr(service, "publish", publish)

    with TestClient(app) as client:
        response = client.post(
            f"/web/skill-workbench/tasks/{job_id}/publish-stream",
            json={
                "disposition": "create-new",
                "skillSpaceIds": ["space-1"],
                "projectName": "default",
                "region": "cn-shanghai",
                "expectedRevision": 1,
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines() if line]
    assert events == [
        {
            "type": "progress",
            "phase": "uploading",
            "message": "正在上传 Skill 包",
        },
        {
            "type": "progress",
            "phase": "activating",
            "message": "正在等待版本生效",
        },
        {
            "type": "complete",
            "result": {
                "skillId": "skill-1",
                "version": "2",
                "skillSpaceIds": ["space-1"],
                "disposition": "create-new",
                "region": "cn-shanghai",
                "projectName": "default",
            },
        },
    ]


def test_publish_stream_unknown_failure_does_not_invite_a_blind_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    service = mount_skill_workbench_routes(
        app,
        lambda request: "alice",
        lambda request: "Alice",
    )
    job_id = SkillWorkbenchService._new_job_id("alice")
    monkeypatch.setattr(
        service,
        "publish",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("private publish failure")
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            f"/web/skill-workbench/tasks/{job_id}/publish-stream",
            json={
                "disposition": "create-new",
                "skillSpaceIds": ["space-1"],
                "projectName": "default",
                "region": "cn-beijing",
                "expectedRevision": 1,
            },
        )

    events = [json.loads(line) for line in response.text.splitlines() if line]
    assert events == [
        {
            "type": "error",
            "error": {
                "code": "SKILL_PUBLISH_FAILED",
                "message": "发布 Skill 失败，无法确认本次发布结果，请刷新 Skill 中心确认。",
                "retryable": False,
            },
        }
    ]
